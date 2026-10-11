#!/usr/bin/env python3
"""
audit.py: check and repair the JSON written by mh-scraper.

It compares the books and chapters in the JSON against the real Bible
(66 books, 1,189 chapters), proposes fixes one at a time, and ASKS FOR YOUR
PERMISSION before each one. Your original JSON is never modified; fixed data is
written to a new file, and only after a final confirmation.

Fixes it can propose (in this order)
  1. Remove front matter: every "book" that appears before Genesis
     (leftover table-of-contents entries such as OBADIAH, PHILEMON, JUDE ...).
  2. Merge stray fragments: an unnamed book that is really the missing first
     (or last) chapters of its neighbour, e.g. UNKNOWN_17 = chapter 1 of 1 Kings.
  3. Name unnamed books from their position and chapter count,
     e.g. UNKNOWN_21 (36 chapters, between 1 Chronicles and Ezra) = 2 Chronicles.
  4. Standardise book names ("FIRST CHRONILES" -> "1 Chronicles",
     "LEVITCUS" -> "Leviticus", trailing dots removed), keeping the original in
     "name_in_source" and adding an "order" number (1-66).

Afterwards it prints what it could NOT fix on its own (missing / duplicate /
extra chapters), with pages and text snippets, so those can be looked at.

Usage
    python3 audit.py                       # reads matthew_henry.json next to this script
    python3 audit.py -i my.json -o out.json
    python3 audit.py --dry-run             # preview every fix; nothing is written
"""

import argparse
import copy
import difflib
import json
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# The Protestant canon: (name, number of chapters)
# --------------------------------------------------------------------------
CANON = [
    ("Genesis", 50), ("Exodus", 40), ("Leviticus", 27), ("Numbers", 36), ("Deuteronomy", 34),
    ("Joshua", 24), ("Judges", 21), ("Ruth", 4), ("1 Samuel", 31), ("2 Samuel", 24),
    ("1 Kings", 22), ("2 Kings", 25), ("1 Chronicles", 29), ("2 Chronicles", 36), ("Ezra", 10),
    ("Nehemiah", 13), ("Esther", 10), ("Job", 42), ("Psalms", 150), ("Proverbs", 31),
    ("Ecclesiastes", 12), ("Song of Solomon", 8), ("Isaiah", 66), ("Jeremiah", 52),
    ("Lamentations", 5), ("Ezekiel", 48), ("Daniel", 12), ("Hosea", 14), ("Joel", 3),
    ("Amos", 9), ("Obadiah", 1), ("Jonah", 4), ("Micah", 7), ("Nahum", 3), ("Habakkuk", 3),
    ("Zephaniah", 3), ("Haggai", 2), ("Zechariah", 14), ("Malachi", 4),
    ("Matthew", 28), ("Mark", 16), ("Luke", 24), ("John", 21), ("Acts", 28), ("Romans", 16),
    ("1 Corinthians", 16), ("2 Corinthians", 13), ("Galatians", 6), ("Ephesians", 6),
    ("Philippians", 4), ("Colossians", 4), ("1 Thessalonians", 5), ("2 Thessalonians", 3),
    ("1 Timothy", 6), ("2 Timothy", 4), ("Titus", 3), ("Philemon", 1), ("Hebrews", 13),
    ("James", 5), ("1 Peter", 5), ("2 Peter", 3), ("1 John", 5), ("2 John", 1), ("3 John", 1),
    ("Jude", 1), ("Revelation", 22),
]
assert len(CANON) == 66 and sum(n for _, n in CANON) == 1189

ALIASES = {
    "Song of Songs": "Song of Solomon", "Canticles": "Song of Solomon",
    "Revelation of St John": "Revelation", "The Revelation": "Revelation",
    "Acts of the Apostles": "Acts", "Psalm": "Psalms",
}

# --------------------------------------------------------------------------
# Matching names ("FIRST CHRONILES", "LEVITCUS", "JEREMIAH.") to the canon
# --------------------------------------------------------------------------
NUM_WORDS = {"FIRST": 1, "1ST": 1, "I": 1, "1": 1, "SECOND": 2, "2ND": 2, "II": 2, "2": 2,
             "THIRD": 3, "3RD": 3, "III": 3, "3": 3}
NOISE = {"THE", "BOOK", "OF", "EPISTLE", "TO", "ST", "SAINT", "GENERAL"}


def norm(name):
    """-> (number prefix, letters-only body) e.g. 'SECOND JOHN.' -> (2, 'JOHN')."""
    toks = [t for t in re.sub(r"[^A-Za-z0-9 ]", " ", name).upper().split() if t not in NOISE]
    prefix = 0
    if len(toks) > 1 and toks[0] in NUM_WORDS:
        prefix, toks = NUM_WORDS[toks[0]], toks[1:]
    return prefix, "".join(toks)


CANON_KEYS = {norm(n): i for i, (n, _) in enumerate(CANON)}
for _alias, _target in ALIASES.items():
    CANON_KEYS[norm(_alias)] = [n for n, _ in CANON].index(_target)


def match_canon(name):
    """-> (canon_index or None, fuzzy_flag)."""
    if not name or name.upper().startswith("UNKNOWN"):
        return None, False
    key = norm(name)
    if key[1] == "":
        return None, False
    if key in CANON_KEYS:
        return CANON_KEYS[key], False
    pool = {k[1]: i for k, i in CANON_KEYS.items() if k[0] == key[0]}
    close = difflib.get_close_matches(key[1], list(pool), n=1, cutoff=0.8)
    if close:
        return pool[close[0]], True
    return None, False


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def nums(book):
    return [c["chapter"] for c in book["chapters"]]


def is_run(ns):
    return bool(ns) and ns == list(range(ns[0], ns[0] + len(ns)))


def chap_span(ns):
    if not ns:
        return "no chapters"
    if is_run(ns):
        return "chapter %d" % ns[0] if len(ns) == 1 else "chapters %d-%d" % (ns[0], ns[-1])
    return "chapters %s" % ns


def first_page(book):
    pages = [c.get("page") for c in book["chapters"] if c.get("page")]
    return pages[0] if pages else None


def total_chars(book):
    return sum(len(c.get("text", "")) for c in book["chapters"])


def snippet(book, n=90):
    for c in book["chapters"]:
        t = " ".join(c.get("text", "").split())
        if t:
            return t[:n]
    return ""


def describe(book):
    pg = first_page(book)
    return "%-26s %4d chapters (%s)%s  ·  %s chars" % (
        repr(book["book"]), len(book["chapters"]), chap_span(nums(book)),
        ("  p.%d" % pg) if pg else "", format(total_chars(book), ","))


def recognised(books):
    return [match_canon(b["book"])[0] for b in books]


# --------------------------------------------------------------------------
# Fix proposals. Each returns a list of {"title", "details", "apply"}.
# --------------------------------------------------------------------------
def propose_front_matter(books):
    rec = recognised(books)
    if 0 not in rec:
        return []
    f = rec.index(0)  # first book that is Genesis
    if f == 0:
        return []
    doomed = books[:f]
    ids = {id(b) for b in doomed}

    def apply():
        books[:] = [b for b in books if id(b) not in ids]

    details = ["These %d entries come BEFORE Genesis, so they are front matter (table of contents etc.), not Bible books:" % f]
    details += ["   " + describe(b) for b in doomed]
    sn = snippet(doomed[0])
    if sn:
        details.append("   first entry starts: " + sn)
    details.append("   Total: %d chapters, %s chars would be removed." % (
        sum(len(b["chapters"]) for b in doomed), format(sum(total_chars(b) for b in doomed), ",")))
    return [{"title": "Remove %d front-matter entries that come before Genesis" % f,
             "details": details, "apply": apply}]


def propose_merges(books):
    rec = recognised(books)
    out = []
    for i, b in enumerate(books):
        if rec[i] is not None or i == 0 or i + 1 >= len(books):
            continue
        p, n = books[i - 1], books[i + 1]
        rp, rn = rec[i - 1], rec[i + 1]
        if rp is None or rn is None or rn - rp != 1:
            continue  # a whole book is missing here: that is a naming job, not a merge
        ub, un, up = nums(b), nums(n), nums(p)
        if is_run(ub) and ub[0] == 1 and un and un[0] == ub[-1] + 1:
            target, where = n, "front"
        elif is_run(ub) and up and ub[0] == up[-1] + 1:
            target, where = p, "end"
        else:
            continue

        def apply(b=b, target=target, where=where):
            if b not in books or target not in books:
                return
            if where == "front":
                target["chapters"][:0] = b["chapters"]
            else:
                target["chapters"].extend(b["chapters"])
            books.remove(b)

        tname = CANON[match_canon(target["book"])[0]][0]
        out.append({
            "title": "Merge %s into %s" % (b["book"], tname),
            "details": [
                "   " + describe(b),
                "   It sits between %s and %s, which are neighbours in the Bible, so it cannot be its own book." % (
                    CANON[rp][0], CANON[rn][0]),
                "   %s currently has %s; adding this gives %s." % (
                    tname, chap_span(nums(target)),
                    chap_span(sorted(nums(target) + ub))),
                "   starts: " + snippet(b)],
            "apply": apply})
    return out


def propose_naming(books):
    rec = recognised(books)
    taken = {r for r in rec if r is not None}
    out = []
    for i, b in enumerate(books):
        if rec[i] is not None or i == 0 or i + 1 >= len(books):
            continue
        rp, rn = rec[i - 1], rec[i + 1]
        if rp is None or rn is None or rn - rp < 2:
            continue
        n_ch = len(b["chapters"])
        gap = [c for c in range(rp + 1, rn) if c not in taken]
        if len(gap) == 1:
            cand = gap[0]
            note = ("chapter count matches (%d)" % n_ch) if CANON[cand][1] == n_ch else \
                   ("WARNING: has %d chapters but %s has %d" % (n_ch, CANON[cand][0], CANON[cand][1]))
        else:
            fit = [c for c in gap if CANON[c][1] == n_ch]
            if len(fit) != 1:
                continue
            cand = fit[0]
            note = "%d books could fit here; only %s has %d chapters" % (len(gap), CANON[cand][0], n_ch)

        def apply(b=b, cand=cand):
            b["name_in_source"] = b["book"]
            b["book"] = CANON[cand][0]
            b["order"] = cand + 1

        out.append({
            "title": "Name %s as %s" % (b["book"], CANON[cand][0]),
            "details": [
                "   " + describe(b),
                "   It sits between %s and %s; %s." % (CANON[rp][0], CANON[rn][0], note),
                "   starts: " + snippet(b)],
            "apply": apply})
    return out


def propose_rename(books):
    rec = recognised(books)
    changes = []
    for b, r in zip(books, rec):
        if r is None:
            continue
        std = CANON[r][0]
        if b["book"] != std or b.get("order") != r + 1:
            changes.append((b, r, std))
    if not changes:
        return []
    shown = [(b["book"], std, match_canon(b["book"])[1]) for b, r, std in changes if b["book"] != std]

    def apply():
        for b, r, std in changes:
            if b["book"] != std:
                b.setdefault("name_in_source", b["book"])
                b["book"] = std
            b["order"] = r + 1

    typos = [x for x in shown if x[2]]
    plain = [x for x in shown if not x[2]]
    details = ["   %-26s -> %s   (typo fixed)" % (repr(a), s) for a, s, _ in typos]
    details += ["   %-26s -> %s" % (repr(a), s) for a, s, _ in plain[:5]]
    if len(plain) > 5:
        details.append("   ... and %d more (capitalisation, trailing dots, FIRST/SECOND -> 1/2)" % (len(plain) - 5))
    details.append("   Also adds an \"order\" number (1-66) to %d books. Original names are kept in \"name_in_source\"." % len(changes))
    return [{"title": "Standardise %d book names" % len(shown), "details": details, "apply": apply}]


STAGES = [propose_front_matter, propose_merges, propose_naming, propose_rename]


# --------------------------------------------------------------------------
# Report on what is still wrong (nothing here is changed automatically)
# --------------------------------------------------------------------------
def final_report(books):
    rec = recognised(books)
    problems = 0
    print("\n" + "=" * 72)
    print("REMAINING PROBLEMS (not changed by this script)")
    print("=" * 72)

    unknown = [b for b, r in zip(books, rec) if r is None]
    for b in unknown:
        problems += 1
        print("\n- Unrecognised book %r" % b["book"])
        print("    " + describe(b))
        print("    starts: " + snippet(b))

    seen, dup = {}, []
    for i, r in enumerate(rec):
        if r is None:
            continue
        if r in seen:
            dup.append((books[i], books[seen[r]]))
        seen.setdefault(r, i)
    for b, first in dup:
        problems += 1
        print("\n- %s appears twice (second: %s)" % (CANON[match_canon(b["book"])[0]][0], describe(b)))

    missing = [CANON[c][0] for c in range(66) if c not in seen]
    if missing:
        problems += 1
        print("\n- Missing books: %s" % ", ".join(missing))

    order = [r for r in rec if r is not None]
    if order != sorted(order):
        problems += 1
        print("\n- Books are not in Bible order")

    for b, r in zip(books, rec):
        if r is None:
            continue
        name, expect = CANON[r]
        ns = nums(b)
        want = set(range(1, expect + 1))
        got = set(ns)
        missing_ch = sorted(want - got)
        extra_ch = sorted(got - want)
        counts = {n: ns.count(n) for n in got}
        dups = sorted(n for n, k in counts.items() if k > 1)
        if not (missing_ch or extra_ch or dups):
            continue
        problems += 1
        print("\n- %s: has %d chapters, should have %d" % (name, len(ns), expect))
        if missing_ch:
            print("    missing chapter numbers: %s" % missing_ch)
        if extra_ch:
            print("    chapter numbers beyond the end of the book: %s" % extra_ch)
        if dups:
            print("    chapter numbers that appear more than once: %s" % dups)
        for c in b["chapters"]:
            if c["chapter"] in dups or c["chapter"] in extra_ch:
                t = " ".join(c.get("text", "").split())
                pg = c.get("page")
                print("      chapter %d%s  (%s chars): %s" % (
                    c["chapter"], (" p.%d" % pg) if pg else "", format(len(c.get("text", "")), ","), t[:90]))
        # show neighbours of a gap so the missing chapter can be hunted down
        for m in missing_ch[:3]:
            prev = next((c for c in b["chapters"] if c["chapter"] == m - 1), None)
            if prev and prev.get("page"):
                print("      chapter %d should follow chapter %d (p.%d)" % (m, m - 1, prev["page"]))

    if not problems:
        print("\nNone. All 66 books are present and every chapter count matches the Bible.")
    return problems


# --------------------------------------------------------------------------
# Asking permission
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, dry):
        self.dry = dry
        self.yes_all = False
        self.stop = False
        self.n = 0
        self.log = []


def ask(prompt):
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        print()
        return "n"
    return ans[:1] if ans else "n"


def review(fixes, ctx):
    for fx in fixes:
        if ctx.stop:
            return
        ctx.n += 1
        print("\n[%d] PROPOSED FIX: %s" % (ctx.n, fx["title"]))
        for d in fx["details"]:
            print(d)
        if ctx.dry:
            choice = "y"
        elif ctx.yes_all:
            choice = "y"
        else:
            choice = ask("\n    Apply this fix?  [y]es / [N]o / [a]ll remaining / [q]uit reviewing: ")
        if choice == "a":
            ctx.yes_all, choice = True, "y"
        if choice == "q":
            ctx.stop = True
            print("    -> stopped reviewing; remaining fixes skipped")
            return
        if choice == "y":
            fx["apply"]()
            ctx.log.append(fx["title"])
            print("    -> applied" + (" (in memory only, dry run)" if ctx.dry else ""))
        else:
            print("    -> skipped")


def overview(label, books):
    ch = sum(len(b["chapters"]) for b in books)
    print("%s: %d books, %d chapters   (the Bible has 66 books, 1189 chapters)" % (label, len(books), ch))


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Audit and repair mh-scraper JSON (asks before changing anything).")
    ap.add_argument("-i", "--input", default=os.path.join(SCRIPT_DIR, "matthew_henry.json"))
    ap.add_argument("-o", "--output", help="where to write the fixed JSON (default: <input>.fixed.json)")
    ap.add_argument("--dry-run", action="store_true", help="preview every fix in memory; write nothing")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit("Input not found: %s\nRun mh-scraper.py first, or pass -i path/to/file.json" % args.input)
    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    out_path = args.output or os.path.splitext(args.input)[0] + ".fixed.json"
    books = copy.deepcopy(data["books"])  # work on a copy; the original file is never touched

    print("Auditing %s" % args.input)
    overview("Before", books)
    if args.dry_run:
        print("DRY RUN: every fix is applied in memory only so you can preview the result. Nothing will be written.")
    else:
        print("Nothing is changed until you say yes. Your original file is never modified.")

    ctx = Ctx(args.dry_run)
    for stage in STAGES:
        if ctx.stop:
            break
        review(stage(books), ctx)

    if ctx.n == 0:
        print("\nNo automatic fixes to propose.")
    print()
    overview("After ", books)
    final_report(books)

    if args.dry_run:
        print("\nDry run finished. Nothing was written.")
        return
    if not ctx.log:
        print("\nNo fixes were applied, so no file was written.")
        return

    print("\nApplied %d fix(es):" % len(ctx.log))
    for t in ctx.log:
        print("  - " + t)
    if os.path.exists(out_path):
        print("\nNote: %s already exists and would be overwritten." % out_path)
    if ask("\nWrite the fixed JSON to %s ?  [y/N]: " % out_path) != "y":
        print("Not written. Nothing on disk was changed.")
        return
    data = dict(data)
    data["books"] = books
    data["audit_log"] = {"audited_at": datetime.now().isoformat(timespec="seconds"), "applied": ctx.log}
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    print("Wrote %s" % out_path)


if __name__ == "__main__":
    main()
