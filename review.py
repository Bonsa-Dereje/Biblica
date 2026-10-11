#!/usr/bin/env python3
"""
review.py: read the fixed JSON written by audit.py and list every book and
chapter so you can fact-check it against the real Bible / the PDF.

Nothing is modified. It only reads the JSON and produces reports.

What you get
  1. A console listing: every book (order, name, name in source, chapters found vs
     expected, size, status) followed by every chapter (heading, running title,
     size, verses found) with warning flags where something looks off.
  2. review.html (next to the JSON): a self-contained page you open in a browser.
     Books on the left, chapters on the right, search box, "only flagged" filter,
     a tick-box on every chapter to mark it as checked (remembered in your
     browser), and the full chapter text + detected verses in a collapsible block.
  3. Optional --txt / --csv files with the same listing.

Flags it raises (these are things to look at, not proof of an error)
  Book:    wrong chapter count, missing / duplicate / extra chapter numbers,
           renamed from the source name, missing "order", out of Bible order,
           missing or duplicate books.
  Chapter: heading number differs from chapter number (CHAP. IV. stored as 5),
           very short text, empty text, no running title, no verses detected,
           verse numbers that do not start at 1 or have gaps.

Usage
    python3 review.py                          # matthew_henry.fixed.json next to this script
    python3 review.py -i matthew_henry.fixed.json
    python3 review.py --book "1 Kings"         # console listing for one book only
    python3 review.py --book Psalms --text     # ... including full chapter text
    python3 review.py --summary                # books table only (no chapter lines)
    python3 review.py --txt report.txt --csv chapters.csv
    python3 review.py --no-html                # console only
    python3 review.py --no-text                # smaller HTML: leave out full chapter text
"""

import argparse
import csv
import difflib
import html
import json
import os
import re
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHORT_TEXT = 400  # chapters with fewer characters than this are flagged

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
CANON_NAMES = [n for n, _ in CANON]

NUM_WORDS = {"FIRST": 1, "1ST": 1, "I": 1, "1": 1, "SECOND": 2, "2ND": 2, "II": 2, "2": 2,
             "THIRD": 3, "3RD": 3, "III": 3, "3": 3}
NOISE = {"THE", "BOOK", "OF", "EPISTLE", "TO", "ST", "SAINT", "GENERAL"}
ALIASES = {"Song of Songs": "Song of Solomon", "Canticles": "Song of Solomon",
           "Revelation of St John": "Revelation", "Acts of the Apostles": "Acts", "Psalm": "Psalms"}

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
HEADING_RE = re.compile(r"(?:CHAP(?:TER)?|PSALM)\.?\s+([IVXLCDM]+)", re.I)


def norm(name):
    toks = [t for t in re.sub(r"[^A-Za-z0-9 ]", " ", name).upper().split() if t not in NOISE]
    prefix = 0
    if len(toks) > 1 and toks[0] in NUM_WORDS:
        prefix, toks = NUM_WORDS[toks[0]], toks[1:]
    return prefix, "".join(toks)


CANON_KEYS = {norm(n): i for i, n in enumerate(CANON_NAMES)}
for _a, _t in ALIASES.items():
    CANON_KEYS[norm(_a)] = CANON_NAMES.index(_t)


def match_canon(name):
    """-> canon index or None (exact after normalising, else close spelling)."""
    if not name or name.upper().startswith("UNKNOWN"):
        return None
    key = norm(name)
    if not key[1]:
        return None
    if key in CANON_KEYS:
        return CANON_KEYS[key]
    pool = {k[1]: i for k, i in CANON_KEYS.items() if k[0] == key[0]}
    close = difflib.get_close_matches(key[1], list(pool), n=1, cutoff=0.8)
    return pool[close[0]] if close else None


def roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
def chapter_flags(ch):
    flags = []
    text = ch.get("text", "") or ""
    n = ch.get("chapter")
    m = HEADING_RE.search(ch.get("heading", "") or "")
    if m:
        try:
            if roman_to_int(m.group(1)) != n:
                flags.append("heading says %s but stored as %s" % (ch["heading"].strip(), n))
        except KeyError:
            pass
    if not text.strip():
        flags.append("empty text")
    elif len(text) < SHORT_TEXT:
        flags.append("very short text (%d chars)" % len(text))
    if not (ch.get("title") or "").strip():
        flags.append("no running title")
    vn = ch.get("verse_numbers") or []
    if not vn:
        flags.append("no verses detected")
    elif vn[0] != 1 or vn != list(range(1, len(vn) + 1)):
        flags.append("verse numbers not 1..n")
    return flags


def verse_span(ch):
    vn = ch.get("verse_numbers") or []
    if not vn:
        return "-"
    return "v1" if len(vn) == 1 else "v%d-%d" % (vn[0], vn[-1])


def analyse(books):
    """Returns (rows, book_level_problems). rows[i] describes books[i]."""
    rows, seen = [], {}
    prev_idx = -1
    out_of_order = False
    for i, b in enumerate(books):
        idx = match_canon(b["book"])
        if idx is None and b.get("order"):
            idx = b["order"] - 1 if 1 <= b["order"] <= 66 else None
        chapters = b.get("chapters", [])
        ns = [c.get("chapter") for c in chapters]
        flags = []
        expected = CANON[idx][1] if idx is not None else None
        if idx is None:
            flags.append("book name not recognised")
        else:
            want, got = set(range(1, expected + 1)), set(ns)
            miss, extra = sorted(want - got), sorted(got - want)
            dups = sorted({n for n in ns if ns.count(n) > 1})
            if len(ns) != expected:
                flags.append("has %d chapters, should have %d" % (len(ns), expected))
            if miss:
                flags.append("missing chapter numbers: %s" % _short_list(miss))
            if extra:
                flags.append("chapter numbers beyond end of book: %s" % _short_list(extra))
            if dups:
                flags.append("duplicate chapter numbers: %s" % _short_list(dups))
            if ns != sorted(ns):
                flags.append("chapters not in ascending order")
            if idx in seen:
                flags.append("book appears twice (also entry #%d)" % (seen[idx] + 1))
            seen.setdefault(idx, i)
            if idx < prev_idx:
                out_of_order = True
                flags.append("out of Bible order")
            prev_idx = max(prev_idx, idx)
            if b.get("order") is None:
                flags.append('no "order" number')
            elif b["order"] != idx + 1:
                flags.append('"order" is %s but Bible position is %d' % (b["order"], idx + 1))
        if b.get("name_in_source") and b["name_in_source"] != b["book"]:
            flags.append("renamed from %r" % b["name_in_source"])
        rows.append({"book": b, "idx": idx, "expected": expected, "flags": flags,
                     "chars": sum(len(c.get("text", "") or "") for c in chapters)})
    problems = []
    missing = [CANON_NAMES[k] for k in range(66) if k not in seen]
    if missing:
        problems.append("Missing books: " + ", ".join(missing))
    return rows, problems


def _short_list(xs, limit=12):
    if len(xs) <= limit:
        return str(xs)
    return "[%s, ... +%d more]" % (", ".join(map(str, xs[:limit])), len(xs) - limit)


def is_problem_flag(f):
    """Flags that are information only, not necessarily an error."""
    return not f.startswith("renamed from")


# --------------------------------------------------------------------------
# Console / text listing
# --------------------------------------------------------------------------
def snippet(text, n):
    return " ".join((text or "").split())[:n]


def write_listing(out, data, rows, problems, args, only=None):
    books = data["books"]
    total_ch = sum(len(b.get("chapters", [])) for b in books)
    flagged_books = sum(1 for r in rows if any(is_problem_flag(f) for f in r["flags"]))
    flagged_ch = sum(1 for r in rows for c in r["book"].get("chapters", []) if chapter_flags(c))
    p = lambda s="": print(s, file=out)

    p("=" * 78)
    p("REVIEW OF %s" % data.get("_path", ""))
    p("source PDF: %s    scraped complete: %s" % (data.get("source", "?"), data.get("complete", "?")))
    if data.get("audit_log"):
        al = data["audit_log"]
        p("audited at %s, fixes applied:" % al.get("audited_at", "?"))
        for t in al.get("applied", []):
            p("   - " + t)
    p("=" * 78)
    p("Books: %d of 66     Chapters: %d of 1189     Books with flags: %d     Chapters with flags: %d"
      % (len(books), total_ch, flagged_books, flagged_ch))
    for pr in problems:
        p("!! " + pr)
    p()
    p("%3s  %-18s %-22s %9s %9s %11s  %s" % ("#", "Book", "Name in source", "Chapters", "Expected", "Chars", "Status"))
    p("-" * 78)
    for i, r in enumerate(rows):
        b = r["book"]
        bad = [f for f in r["flags"] if is_problem_flag(f)]
        p("%3s  %-18s %-22s %9d %9s %11s  %s" % (
            b.get("order", "?"), b["book"][:18], (b.get("name_in_source") or "")[:22],
            len(b.get("chapters", [])), r["expected"] if r["expected"] else "?", format(r["chars"], ","),
            "OK" if not bad else "CHECK"))

    for r in ([] if args.summary else rows):
        b = r["book"]
        if only and only.lower() not in (b["book"].lower(), (b.get("name_in_source") or "").lower()):
            continue
        p()
        p("=" * 78)
        p("%s%s   (%d chapters, expected %s)" % (
            b["book"], ("   [source name: %s]" % b["name_in_source"]) if b.get("name_in_source") else "",
            len(b.get("chapters", [])), r["expected"] if r["expected"] else "?"))
        for f in r["flags"]:
            p("   ! " + f)
        p("-" * 78)
        for c in b.get("chapters", []):
            fl = chapter_flags(c)
            p("  %3s  %-12s %-44s %8s chars  %-8s %s" % (
                c.get("chapter"), (c.get("heading") or "").strip()[:12], (c.get("title") or "")[:44],
                format(len(c.get("text", "") or ""), ","), verse_span(c), "  <-- " + "; ".join(fl) if fl else ""))
            if args.text:
                p()
                p(_indent(c.get("text", "") or "", "       "))
                p()
            elif args.preview:
                p("       " + snippet(c.get("text", ""), args.preview))

    # ---- one giant list at the very end: book and chapter count only
    p()
    p("=" * 78)
    p("ALL BOOKS AND NUMBER OF CHAPTERS")
    p("=" * 78)
    for r in rows:
        p("%-20s %d" % (r["book"]["book"], len(r["book"].get("chapters", []))))
    p("-" * 78)
    p("%-20s %d" % ("TOTAL (%d books)" % len(books), total_ch))


def _indent(text, pad):
    return "\n".join(pad + ln for ln in text.splitlines())


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["order", "book", "name_in_source", "chapter", "heading", "title", "chars",
                    "verses_found", "verse_range", "flags", "starts_with"])
        for r in rows:
            b = r["book"]
            for c in b.get("chapters", []):
                w.writerow([b.get("order", ""), b["book"], b.get("name_in_source", ""), c.get("chapter"),
                            (c.get("heading") or "").strip(), c.get("title", ""), len(c.get("text", "") or ""),
                            len(c.get("verse_numbers") or []), verse_span(c), "; ".join(chapter_flags(c)),
                            snippet(c.get("text", ""), 120)])


# --------------------------------------------------------------------------
# HTML report
# --------------------------------------------------------------------------
CSS = """
:root{--bg:#fbfaf7;--fg:#222;--mut:#6b6b6b;--card:#fff;--line:#e3dfd6;--acc:#1f5f8b;--warn:#b45309;--warnbg:#fff4e0;--ok:#2f7d4f;--bad:#b3261e;--badbg:#fde8e6}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--fg:#e6e6e6;--mut:#9aa0a6;--card:#1e2125;--line:#33373d;--acc:#7ab7e6;--warn:#f0b35a;--warnbg:#3a2e17;--ok:#6fcf97;--bad:#ff8a80;--badbg:#3d1f1d}}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:flex;flex-direction:column}
header{padding:12px 18px;border-bottom:1px solid var(--line);background:var(--card);display:flex;flex-wrap:wrap;gap:12px 22px;align-items:center}
header h1{font-size:17px;margin:0}
header .stat{color:var(--mut);font-size:13px}header .stat b{color:var(--fg)}
header input[type=search]{flex:1;min-width:180px;max-width:360px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg)}
header label{font-size:13px;color:var(--mut);cursor:pointer}
main{flex:1;display:flex;min-height:0}
nav{width:270px;flex:none;overflow:auto;border-right:1px solid var(--line);background:var(--card);padding:6px 0}
nav a{display:flex;gap:8px;align-items:baseline;padding:5px 14px;color:var(--fg);text-decoration:none;font-size:14px;border-left:3px solid transparent}
nav a:hover{background:var(--bg)}nav a.active{border-left-color:var(--acc);background:var(--bg)}
nav .n{color:var(--mut);width:22px;text-align:right;flex:none;font-variant-numeric:tabular-nums}
nav .c{margin-left:auto;color:var(--mut);font-size:12px;font-variant-numeric:tabular-nums}
nav .dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--ok)}nav .dot.bad{background:var(--bad)}
section.chapters{flex:1;overflow:auto;padding:18px 24px 80px}
.book{display:none}.book.show{display:block}
.book h2{margin:0 0 4px;font-size:22px}.book .sub{color:var(--mut);font-size:13px;margin-bottom:10px}
.pill{display:inline-block;font-size:12px;padding:2px 8px;border-radius:99px;margin:2px 4px 2px 0;background:var(--warnbg);color:var(--warn)}
.pill.bad{background:var(--badbg);color:var(--bad)}.pill.info{background:var(--bg);color:var(--mut);border:1px solid var(--line)}
.ch{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0}
.ch.flagged{border-color:var(--warn)}.ch.done{opacity:.55}
.ch>summary{list-style:none;cursor:pointer;display:flex;gap:12px;align-items:baseline;padding:9px 12px}
.ch>summary::-webkit-details-marker{display:none}
.ch .num{font-weight:600;min-width:34px;color:var(--acc);font-variant-numeric:tabular-nums}
.ch .ttl{flex:1}.ch .ttl small{color:var(--mut)}
.ch .meta{color:var(--mut);font-size:12.5px;white-space:nowrap}
.ch .body{padding:0 14px 14px;border-top:1px solid var(--line)}
.ch .kv{display:grid;grid-template-columns:110px 1fr;gap:3px 12px;font-size:13.5px;margin:10px 0}.ch .kv dt{color:var(--mut)}.ch .kv dd{margin:0}
.ch .starts,.ch .ends{font-size:13.5px;border-left:3px solid var(--line);padding:2px 10px;margin:8px 0;color:var(--mut)}
.verses{font-size:13.5px}.verses div{padding:1px 0}.verses b{color:var(--acc);margin-right:6px}
details.sub2>summary{cursor:pointer;color:var(--acc);font-size:13.5px;margin:8px 0}
pre.full{white-space:pre-wrap;word-wrap:break-word;font:14px/1.55 Georgia,serif;background:var(--bg);padding:10px 12px;border-radius:6px;max-height:480px;overflow:auto}
.ck{margin-left:6px}
mark{background:#ffe58a;color:#000}
.empty{color:var(--mut);padding:30px}
@media (max-width:760px){main{flex-direction:column}nav{width:100%;max-height:34vh;border-right:0;border-bottom:1px solid var(--line)}}
"""

JS = """
(function(){
var KEY='mh-review-checked:'+document.body.dataset.key;
var done={};try{done=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(done))}catch(e){}}
var navs=[].slice.call(document.querySelectorAll('nav a')),books=[].slice.call(document.querySelectorAll('.book'));
var q=document.getElementById('q'),only=document.getElementById('only'),hideDone=document.getElementById('hidedone');
var cur=null;
function show(id){cur=id;books.forEach(function(b){b.classList.toggle('show',b.id===id)});
 navs.forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+id)});
 apply();var s=document.querySelector('section.chapters');if(s)s.scrollTop=0}
function apply(){var t=q.value.trim().toLowerCase(),f=only.checked,hd=hideDone.checked;
 document.querySelectorAll('.ch').forEach(function(c){
  var ok=true;if(f&&!c.classList.contains('flagged'))ok=false;
  if(hd&&c.classList.contains('done'))ok=false;
  if(t&&c.dataset.search.indexOf(t)<0)ok=false;
  c.style.display=ok?'':'none'});
 books.forEach(function(b){var any=[].some.call(b.querySelectorAll('.ch'),function(c){return c.style.display!=='none'});
  var e=b.querySelector('.empty');if(e)e.style.display=any?'none':''});
 updateCount()}
function updateCount(){var n=Object.keys(done).filter(function(k){return done[k]}).length;
 document.getElementById('donecount').textContent=n}
navs.forEach(function(a){a.addEventListener('click',function(e){e.preventDefault();history.replaceState(null,'',a.getAttribute('href'));show(a.getAttribute('href').slice(1))})});
document.querySelectorAll('.ck input').forEach(function(cb){var c=cb.closest('.ch');
 if(done[c.id]){cb.checked=true;c.classList.add('done')}
 cb.addEventListener('click',function(e){e.stopPropagation()});
 cb.addEventListener('change',function(){if(cb.checked){done[c.id]=1;c.classList.add('done')}else{delete done[c.id];c.classList.remove('done')}save();apply()})});
document.querySelectorAll('.ck').forEach(function(l){l.addEventListener('click',function(e){e.stopPropagation()})});
[q,only,hideDone].forEach(function(el){el.addEventListener('input',apply)});
var start=(location.hash||'').slice(1);if(!document.getElementById(start))start=books[0]&&books[0].id;if(start)show(start);
})();
"""


def build_html(data, rows, problems, include_text, src_name):
    e = html.escape
    books = data["books"]
    total_ch = sum(len(b.get("chapters", [])) for b in books)
    flagged_ch = sum(1 for r in rows for c in r["book"].get("chapters", []) if chapter_flags(c))
    bad_books = sum(1 for r in rows if any(is_problem_flag(f) for f in r["flags"]))

    nav, body = [], []
    for i, r in enumerate(rows):
        b = r["book"]
        bid = "b%d" % (i + 1)
        bad = [f for f in r["flags"] if is_problem_flag(f)]
        nav.append('<a href="#%s"><span class="dot%s"></span><span class="n">%s</span><span>%s</span>'
                   '<span class="c">%d/%s</span></a>' % (
                       bid, " bad" if bad else "", e(str(b.get("order", "?"))), e(b["book"]),
                       len(b.get("chapters", [])), r["expected"] or "?"))

        parts = ['<div class="book" id="%s">' % bid, "<h2>%s</h2>" % e(b["book"])]
        sub = "%d chapters found, %s expected &middot; %s characters" % (
            len(b.get("chapters", [])), r["expected"] or "?", format(r["chars"], ","))
        if b.get("name_in_source"):
            sub += " &middot; name in source: <b>%s</b>" % e(b["name_in_source"])
        parts.append('<div class="sub">%s</div>' % sub)
        for f in r["flags"]:
            parts.append('<span class="pill %s">%s</span>' % ("info" if not is_problem_flag(f) else "bad", e(f)))

        used = {}
        for c in b.get("chapters", []):
            cid = "%s-c%s" % (bid, c.get("chapter"))
            used[cid] = used.get(cid, 0) + 1
            if used[cid] > 1:  # a repeated chapter number still needs a unique id
                cid += "-dup%d" % (used[cid] - 1)
            fl = chapter_flags(c)
            text = c.get("text", "") or ""
            title = c.get("title", "") or ""
            hay = " ".join([str(c.get("chapter")), c.get("heading", "") or "", title, text if include_text else text[:600]]).lower()
            verses = c.get("verses") or []
            cls = "ch flagged" if fl else "ch"
            parts.append('<details class="%s" id="%s" data-search="%s"><summary>' % (cls, cid, e(hay, quote=True)))
            parts.append('<span class="num">%s</span><span class="ttl">%s<small> &nbsp;%s</small></span>' % (
                e(str(c.get("chapter"))), e(title) if title else "<i>(no title)</i>", e((c.get("heading") or "").strip())))
            parts.append('<span class="meta">%s chars &middot; %d verses &middot; %s</span>' % (
                format(len(text), ","), len(c.get("verse_numbers") or []), e(verse_span(c))))
            if fl:
                parts.append('<span class="pill">&#9888; %d</span>' % len(fl))
            parts.append('<label class="ck" title="mark as fact-checked"><input type="checkbox"></label></summary>')
            parts.append('<div class="body">')
            for f in fl:
                parts.append('<span class="pill">%s</span>' % e(f))
            parts.append('<dl class="kv"><dt>Heading</dt><dd>%s</dd><dt>Running title</dt><dd>%s</dd>'
                         '<dt>Characters</dt><dd>%s</dd><dt>Verses found</dt><dd>%d (%s)</dd></dl>' % (
                             e(c.get("heading", "") or ""), e(title) or "&mdash;", format(len(text), ","),
                             len(c.get("verse_numbers") or []), e(verse_span(c))))
            if text:
                parts.append('<div class="starts"><b>Starts:</b> %s</div>' % e(snippet(text, 300)))
                tail = " ".join(text.split())[-220:]
                parts.append('<div class="ends"><b>Ends:</b> &hellip;%s</div>' % e(tail))
            if verses:
                parts.append('<details class="sub2"><summary>Detected verses (%d)</summary><div class="verses">' % len(verses))
                for v in verses:
                    parts.append("<div><b>%s</b>%s</div>" % (e(str(v.get("verse"))), e(v.get("text", "") or "")))
                parts.append("</div></details>")
            if include_text and text:
                parts.append('<details class="sub2"><summary>Full chapter text</summary><pre class="full">%s</pre></details>' % e(text))
            parts.append("</div></details>")
        parts.append('<div class="empty" style="display:none">No chapters match the current search / filters.</div></div>')
        body.append("\n".join(parts))

    warn = "".join('<div class="pill bad">%s</div>' % e(p) for p in problems)
    key = re.sub(r"\W+", "", src_name)[:40] + str(len(books)) + "-" + str(total_ch)
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matthew Henry review</title><style>%s</style></head>
<body data-key="%s">
<header><h1>Matthew Henry &mdash; fact-check review</h1>
<span class="stat"><b>%d</b>/66 books</span><span class="stat"><b>%d</b>/1189 chapters</span>
<span class="stat"><b>%d</b> books flagged</span><span class="stat"><b>%d</b> chapters flagged</span>
<span class="stat"><b id="donecount">0</b> checked</span>
<input id="q" type="search" placeholder="search heading, title, text&hellip;">
<label><input id="only" type="checkbox"> only flagged</label>
<label><input id="hidedone" type="checkbox"> hide checked</label>%s</header>
<main><nav>%s</nav><section class="chapters">%s</section></main>
<script>%s</script></body></html>""" % (CSS, e(key), len(books), total_ch, bad_books, flagged_ch, warn,
                                        "\n".join(nav), "\n".join(body), JS)


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="List books/chapters from the audit-fixed JSON for fact-checking.")
    ap.add_argument("-i", "--input", help="JSON to read (default: matthew_henry.fixed.json next to this script)")
    ap.add_argument("--html", help="HTML report path (default: review.html next to the JSON)")
    ap.add_argument("--no-html", action="store_true", help="do not write the HTML report")
    ap.add_argument("--no-text", action="store_true", help="leave full chapter text out of the HTML (much smaller)")
    ap.add_argument("--txt", help="also write the console listing to this text file")
    ap.add_argument("--csv", help="also write one row per chapter to this CSV file")
    ap.add_argument("--book", help="console listing for one book only (e.g. \"1 Kings\")")
    ap.add_argument("--summary", action="store_true", help="console: books table only")
    ap.add_argument("--preview", type=int, nargs="?", const=160, default=0, metavar="N",
                    help="console: show the first N characters of every chapter (default 160)")
    ap.add_argument("--text", action="store_true", help="console: print full chapter text (use with --book)")
    args = ap.parse_args()

    path = args.input
    if not path:
        for cand in ("matthew_henry.fixed.json", "matthew_henry.json"):
            p = os.path.join(SCRIPT_DIR, cand)
            if os.path.exists(p):
                path = p
                break
    if not path or not os.path.exists(path):
        sys.exit("Could not find the JSON. Run audit.py first, or pass -i path/to/file.json")
    if os.path.basename(path) == "matthew_henry.json":
        print("(note: reading the UNFIXED file; run audit.py first for the corrected one)\n")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        sys.exit("This does not look like mh-scraper / audit output (no \"books\" list).")
    data["_path"] = path

    rows, problems = analyse(data["books"])

    write_listing(sys.stdout, data, rows, problems, args, only=args.book)
    if args.book and not any(args.book.lower() in (r["book"]["book"].lower(), (r["book"].get("name_in_source") or "").lower()) for r in rows):
        print("\nNo book called %r. Names are: %s" % (args.book, ", ".join(r["book"]["book"] for r in rows)))

    if args.txt:
        with open(args.txt, "w", encoding="utf-8") as f:
            write_listing(f, data, rows, problems, args, only=args.book)
        print("\nWrote %s" % args.txt)
    if args.csv:
        write_csv(args.csv, rows)
        print("Wrote %s" % args.csv)
    if not args.no_html:
        out = args.html or os.path.join(os.path.dirname(os.path.abspath(path)), "review.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(build_html(data, rows, problems, not args.no_text, os.path.basename(path)))
        print("Wrote %s  (open it in your browser; %.1f MB)" % (out, os.path.getsize(out) / 1e6))


if __name__ == "__main__":
    main()