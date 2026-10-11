#!/usr/bin/env python3
"""
mh-scraper: convert Matthew Henry's Commentary on the Whole Bible (PDF) to JSON.

The PDF is read ONE PAGE AT A TIME (streamed), never all at once, and a live
dashboard shows what is happening: progress, ETA, current book / chapter,
and a scrolling log of everything found or skipped.

Output structure
----------------
{
  "source": "<input file name>",
  "complete": true,                  # false if you pressed Ctrl+C (partial save)
  "books": [
    {
      "book": "GENESIS",
      "chapters": [
        {
          "chapter": 1,                 # normal number (CHAP. I. -> 1)
          "heading": "CHAP. I.",        # heading exactly as printed
          "title": "The Creation.",     # running title, if any ("The Creation.  B. C. 4004.")
          "text": "...",                # everything up to the next chapter heading
          "verse_numbers": [1, 2],      # verse numbers found in the quoted scripture
          "verses": [                   # best-effort verse text (see note below)
            {"verse": 1, "text": "In the beginning God created ..."},
            ...
          ]
        }
      ]
    }
  ]
}

Note on verses: the PDF is plain running text, so quoted scripture is not
visually separated from commentary. Verse *numbers* are detected as an
ascending run (1 2 3 ...) of numbers sitting in front of capitalised text.
Verse *text* runs to the next verse number, or to the end of the first line
that ends a sentence, whichever comes first. That is right for most verses but
can cut a verse short, so the full chapter `text` is always kept untouched.

Usage
-----
    python3 mh-scraper.py                        # PDF sitting next to this script
    python3 mh-scraper.py -i book.pdf -o out.json
    python3 mh-scraper.py --plain                # no dashboard, simple log lines
    python3 mh-scraper.py -i sample.txt          # plain text works too (pages split on form feeds)

Install:  pip install pypdf rich      (and poppler's `pdftotext`, which is much faster)
"""

import argparse
import codecs
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from bisect import bisect_right

try:  # live dashboard is optional
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import (BarColumn, MofNCompleteColumn, Progress,
                               TextColumn, TimeElapsedColumn, TimeRemainingColumn)
    from rich.table import Table
    from rich.text import Text
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

DEFAULT_PDF_NAME = "Matthew_Henrys_Commentary_on_the_Whole_Bible_-_Matthew_Henry.pdf"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT_CANDIDATES = [os.path.join(SCRIPT_DIR, DEFAULT_PDF_NAME)]  # PDF next to this script

EXPECTED_BOOKS = 66
EXPECTED_CHAPTERS = 1189  # Protestant canon, Psalms counted as 150 chapters

# --------------------------------------------------------------------------
# Roman numerals
# --------------------------------------------------------------------------
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s):
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = ROMAN_VALUES[ch]
        if v < prev:
            total -= v
        else:
            total += v
            prev = v
    return total


# --------------------------------------------------------------------------
# Line patterns
# --------------------------------------------------------------------------
# "CHAP. I."  "CHAP. XVIII."  "CHAPTER II"   (Psalms use "PSALM I.")
CHAPTER_RE = re.compile(r"^\s*(?:CHAP(?:TER)?|PSALM)\.?\s+([IVXLCDM]+)\.?\s*$", re.I)
# "G E N E S I S": three or more single capitals separated by spaces
SPACED_TITLE_RE = re.compile(r"^\s*(?:[A-Z]\s+){2,}[A-Z]\s*$")
# plain all-caps line ("GENESIS", "THE REVELATION OF ST. JOHN")
ALLCAPS_RE = re.compile(r"^\s*(?=.*[A-Z]{3})[A-Z0-9 .,'’:\-]{3,60}$")

RULE_RE = re.compile(r"^\s*_{5,}\s*$")
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")
WATERMARK_RE = re.compile(r"ocean\s*of\s*pdf\s*\.?\s*com", re.I)
PARA_START_RE = re.compile(r"^(?:\s{2,}\S|\(\d+\.\)|\d+\.\s|[IVX]+\.\s)")
TERMINAL_RE = re.compile(r"[.!?][\"'”’)]*$")
VERSE_TOKEN_RE = re.compile(r"(?<![\w.])(\d{1,3})\s+(?=[A-Z\"'“‘(\[])")


def is_title_line(line):
    return bool(SPACED_TITLE_RE.match(line) or ALLCAPS_RE.match(line))


def despace_title(line):
    """'G E N E S I S' -> 'GENESIS'; 'S O N G  O F  S O L O M O N' -> 'SONG OF SOLOMON'."""
    line = line.strip()
    if SPACED_TITLE_RE.match(line):
        words = re.split(r"\s{2,}", line)
        if len(words) > 1:
            return " ".join(w.replace(" ", "") for w in words)
        return line.replace(" ", "")
    return line


# --------------------------------------------------------------------------
# Chapter content
# --------------------------------------------------------------------------
def join_paragraphs(body_lines):
    paras, cur = [], []
    for ln in body_lines:
        if RULE_RE.match(ln):
            continue
        if not ln.strip():
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if cur and PARA_START_RE.match(ln):
            paras.append(" ".join(cur))
            cur = []
        cur.append(ln.strip())
    if cur:
        paras.append(" ".join(cur))
    return [re.sub(r"\s+", " ", p) for p in paras]


def locate_title(body_lines):
    """
    Running title such as 'The Creation.  B. C. 4004.' sits on the line above a
    rule line. Returns (title, index_of_that_rule) or ("", -1).
    """
    for k, ln in enumerate(body_lines):
        if RULE_RE.match(ln) and k > 0:
            cand = body_lines[k - 1].strip()
            if cand and not RULE_RE.match(cand) and len(cand) < 100:
                return cand, k
    return "", -1


def find_verses(body_lines, start_idx):
    """
    Detect scripture: an ascending run of verse numbers (1, 2, 3 ...) in the
    order they appear. Returns (verse_numbers, verses).
    """
    parts, term_pos, pos = [], [], 0
    for ln in body_lines[start_idx:]:
        s = ln.strip()
        if not s or RULE_RE.match(ln):
            continue
        parts.append(s + " ")
        pos += len(s) + 1
        if TERMINAL_RE.search(s):
            term_pos.append(pos)
    flat = "".join(parts)

    expected, found = 1, []
    for m in VERSE_TOKEN_RE.finditer(flat):
        n = int(m.group(1))
        if n == expected:
            found.append((n, m.start(), m.end()))
            expected += 1

    verses = []
    for idx, (n, _ms, ts) in enumerate(found):
        te = found[idx + 1][1] if idx + 1 < len(found) else len(flat)
        k = bisect_right(term_pos, ts + 1)
        if k < len(term_pos) and term_pos[k] < te:
            te = term_pos[k]
        verses.append({"verse": n, "text": re.sub(r"\s+", " ", flat[ts:te]).strip()})
    return [v["verse"] for v in verses], verses


def build_chapter(chap, heading, body_lines):
    title, rule_idx = locate_title(body_lines)
    nums, verses = find_verses(body_lines, rule_idx + 1 if rule_idx >= 0 else 0)
    return {
        "chapter": chap,
        "heading": heading,
        "title": title,
        "text": "\n\n".join(join_paragraphs(body_lines)),
        "verse_numbers": nums,
        "verses": verses,
    }


# --------------------------------------------------------------------------
# Shared state shown by the dashboard
# --------------------------------------------------------------------------
class State:
    def __init__(self):
        self.source = ""
        self.method = ""
        self.page = 0
        self.total = 0
        self.book = "-"
        self.chapter = "-"
        self.books = 0
        self.chapters = 0
        self.chars = 0
        self.toc_skipped = 0
        self.watermark = 0
        self.front_lines = 0
        self.warnings = 0
        self.phase = "Starting"
        self.t0 = time.time()


# --------------------------------------------------------------------------
# Streaming parser: fed one cleaned line at a time
# --------------------------------------------------------------------------
class Parser:
    """
    Needs one non-blank line of look-ahead to tell real chapter headings from
    table-of-contents entries, so candidate lines are held in `pending` until
    the next non-blank line arrives.
    """

    def __init__(self, state, ui):
        self.st = state
        self.ui = ui
        self.books = []
        self.book = None
        self.cur = None       # chapter being collected
        self.pending = []     # held-back candidate title/heading lines (+ blanks)
        self.page = 0

    # ---- input
    def feed_page(self, page_no, lines):
        self.page = page_no
        for ln in lines:
            self._feed(ln)

    def finish(self):
        nonblank = [p for p in self.pending if p.strip()]
        if nonblank and CHAPTER_RE.match(nonblank[-1]):
            self._confirm(nonblank)
        else:
            self._flush_pending_as_body()
        self.pending = []
        self._close_current()

    # ---- internals
    def _feed(self, ln):
        if not self.pending:
            if CHAPTER_RE.match(ln) or is_title_line(ln):
                self.pending = [ln]
            else:
                self._body(ln)
            return
        if not ln.strip():
            self.pending.append(ln)
            return
        self._resolve(ln)

    def _resolve(self, nxt):
        nonblank = [p for p in self.pending if p.strip()]
        last_is_head = bool(CHAPTER_RE.match(nonblank[-1]))

        if not last_is_head:  # a possible book title; only counts if a heading follows
            if CHAPTER_RE.match(nxt):
                self.pending.append(nxt)
                return
            if SPACED_TITLE_RE.match(nonblank[-1]):
                self.ui.log("Spaced title %r on p.%d has no chapter heading after it "
                            "(single-chapter book?)" % (despace_title(nonblank[-1]), self.page), "warn")
                self.st.warnings += 1
            self._flush_pending_as_body()
            self._feed(nxt)
            return

        if CHAPTER_RE.match(nxt) or is_title_line(nxt):  # table-of-contents entry
            self.st.toc_skipped += 1
            self.pending = []
            self._feed(nxt)
            return

        self.pending = []
        self._confirm(nonblank)
        self._body(nxt)

    def _flush_pending_as_body(self):
        held, self.pending = self.pending, []
        for p in held:
            self._body(p)

    def _body(self, ln):
        if self.cur is None:
            if ln.strip():
                self.st.front_lines += 1
            return
        self.cur["lines"].append(ln)

    def _close_current(self):
        if self.cur is None:
            return
        ch = build_chapter(self.cur["chapter"], self.cur["heading"], self.cur["lines"])
        self.book["chapters"].append(ch)
        self.st.chapters += 1
        self.st.chars += len(ch["text"])
        self.ui.log("%s %d  ·  %d verse numbers  ·  %s chars" % (
            self.book["book"], ch["chapter"], len(ch["verse_numbers"]), format(len(ch["text"]), ",")), "chap")
        self.cur = None

    def _confirm(self, nonblank):
        head = nonblank[-1]
        chap = roman_to_int(CHAPTER_RE.match(head).group(1))
        title_line = nonblank[-2] if len(nonblank) > 1 else None

        book_title = None
        if title_line is not None:
            if SPACED_TITLE_RE.match(title_line):
                book_title = despace_title(title_line)
            elif chap == 1:
                book_title = title_line.strip()
            else:
                self._body(title_line)  # an all-caps line that is just text
        self._close_current()

        if book_title:
            self._new_book(book_title)
            if chap != 1:
                self._warn("%s starts at chapter %d, not 1 (p.%d)" % (book_title, chap, self.page))
        elif self.book is None:
            self._new_book("UNKNOWN")
        elif chap == 1 and self.book["chapters"]:
            name = "UNKNOWN_%d" % (len(self.books) + 1)
            self._warn("Chapter numbers restarted at 1 with no book title on p.%d, started %s" % (self.page, name))
            self._new_book(name)
        else:
            last = self.book["chapters"][-1]["chapter"] if self.book["chapters"] else 0
            if chap != last + 1:
                self._warn("%s: expected chapter %d, found %d (p.%d)" % (self.book["book"], last + 1, chap, self.page))

        self.cur = {"chapter": chap, "heading": head.strip(), "lines": []}
        self.st.book = self.book["book"]
        self.st.chapter = "%d  (p.%d)" % (chap, self.page)

    def _new_book(self, name):
        self.book = {"book": name, "chapters": []}
        self.books.append(self.book)
        self.st.books += 1
        self.ui.log("BOOK  %s  (p.%d)" % (name, self.page), "book")

    def _warn(self, msg):
        self.st.warnings += 1
        self.ui.log(msg, "warn")


# --------------------------------------------------------------------------
# Page sources (all yield one page of text at a time)
# --------------------------------------------------------------------------
def count_pdf_pages(path):
    if shutil.which("pdfinfo"):
        try:
            out = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=60).stdout
            m = re.search(r"^Pages:\s+(\d+)", out, re.M)
            if m:
                return int(m.group(1))
        except (subprocess.SubprocessError, OSError):
            pass
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except Exception:
        return 0


def pdftotext_pages(path):
    """Stream pages from a single pdftotext process (pages are separated by form feeds)."""
    err = tempfile.TemporaryFile()
    proc = subprocess.Popen(["pdftotext", "-enc", "UTF-8", path, "-"],
                            stdout=subprocess.PIPE, stderr=err)
    dec = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buf = ""
    try:
        while True:
            chunk = os.read(proc.stdout.fileno(), 1 << 16)
            if not chunk:
                break
            buf += dec.decode(chunk)
            while "\f" in buf:
                page, buf = buf.split("\f", 1)
                yield page
        buf += dec.decode(b"", final=True)
        if buf.strip():
            yield buf
        if proc.wait() != 0:
            err.seek(0)
            raise RuntimeError("pdftotext failed: " + err.read().decode("utf-8", "replace").strip())
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        err.close()


def pypdf_pages(path):
    from pypdf import PdfReader
    for page in PdfReader(path).pages:
        yield page.extract_text() or ""


def open_pages(path, state):
    """Returns (total_pages, iterator_of_page_texts)."""
    if path.lower().endswith(".pdf"):
        total = count_pdf_pages(path)
        if shutil.which("pdftotext"):
            state.method = "pdftotext (streaming)"
            return total, pdftotext_pages(path)
        try:
            import pypdf  # noqa: F401
        except ImportError:
            sys.exit("Need poppler's `pdftotext` or `pip install pypdf`.")
        state.method = "pypdf"
        return total, pypdf_pages(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        pages = f.read().split("\f")
    state.method = "text file"
    return len(pages), iter(pages)


def clean_page(text, state):
    """Remove OceanofPDF.com watermark text and bare page-number lines."""
    out = []
    for ln in text.replace("\r", "").split("\n"):
        if WATERMARK_RE.search(ln):
            state.watermark += 1
            ln = WATERMARK_RE.sub("", ln)
            if not ln.strip():
                continue
        if PAGE_NUMBER_RE.match(ln):
            continue
        out.append(ln.rstrip())
    return out


# --------------------------------------------------------------------------
# User interfaces
# --------------------------------------------------------------------------
def fmt_time(sec):
    sec = int(sec)
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


class PlainUI:
    """Simple log lines plus a single progress line."""

    def __init__(self, state):
        self.st = state
        self.tty = sys.stdout.isatty()
        self._last = 0.0

    def start(self):
        print("mh-scraper  ·  %s  ·  %s pages  ·  via %s" % (
            self.st.source, self.st.total or "?", self.st.method))

    def log(self, msg, level="info"):
        tag = {"warn": "WARN", "error": "ERR "}.get(level, "    ")
        if self.tty:
            sys.stdout.write("\r\033[K")
        print("%s %s" % (tag, msg))

    def tick(self):
        now = time.time()
        if self.tty:
            if now - self._last < 0.25:
                return
            self._last = now
            s = self.st
            pct = (100.0 * s.page / s.total) if s.total else 0
            sys.stdout.write("\r\033[K[%5.1f%%] page %d/%s  %s ch %s  books %d  chapters %d" % (
                pct, s.page, s.total or "?", s.book, s.chapter, s.books, s.chapters))
            sys.stdout.flush()
        elif self.st.page % 50 == 0:
            print("  page %d/%s" % (self.st.page, self.st.total or "?"))

    def stop(self):
        if self.tty:
            sys.stdout.write("\r\033[K")


class RichUI:
    """Live dashboard: progress bar, stats and a scrolling log."""

    STYLES = {"info": "dim", "book": "bold cyan", "chap": "green", "warn": "yellow", "error": "bold red"}

    def __init__(self, state):
        self.st = state
        self.logs = collections.deque(maxlen=14)
        self.console = Console()
        self.progress = Progress(
            TextColumn("[bold]{task.description}"), BarColumn(bar_width=None),
            MofNCompleteColumn(), TimeElapsedColumn(), TextColumn("ETA"), TimeRemainingColumn(),
            expand=True)
        self.task = self.progress.add_task("Pages", total=None)
        self.live = Live(get_renderable=self._render, console=self.console, refresh_per_second=10)

    def start(self):
        self.live.start()

    def stop(self):
        self.live.stop()

    def tick(self):
        pass  # the Live display refreshes itself from shared state

    def log(self, msg, level="info"):
        self.logs.append((level, "%s  %s" % (time.strftime("%H:%M:%S"), msg)))

    def _render(self):
        s = self.st
        self.progress.update(self.task, completed=s.page, total=s.total or None)
        elapsed = max(time.time() - s.t0, 0.001)

        grid = Table.grid(padding=(0, 2))
        for _ in range(4):
            grid.add_column(style="dim", justify="right")
            grid.add_column(justify="left")
        grid.add_row("Book", Text(str(s.book), style="bold cyan"), "Chapter", str(s.chapter),
                     "Speed", "%.1f pages/s" % (s.page / elapsed), "Reader", s.method)
        grid.add_row("Books", "%d / %d" % (s.books, EXPECTED_BOOKS),
                     "Chapters", "%d / %d" % (s.chapters, EXPECTED_CHAPTERS),
                     "Text kept", "%.2f MB" % (s.chars / 1e6), "Warnings", Text(str(s.warnings), style="yellow" if s.warnings else ""))
        grid.add_row("Watermark", "%d lines removed" % s.watermark,
                     "TOC", "%d entries skipped" % s.toc_skipped,
                     "Front matter", "%d lines dropped" % s.front_lines, "Status", s.phase)

        log = Text()
        for level, msg in self.logs:
            log.append(msg + "\n", style=self.STYLES.get(level, ""))
        return Group(
            Panel(self.progress, title="mh-scraper  ·  %s" % s.source, border_style="cyan"),
            Panel(grid, title="Now", border_style="blue"),
            Panel(log, title="Log", border_style="dim", height=18),
        )


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Convert Matthew Henry's Commentary PDF to JSON.")
    ap.add_argument("-i", "--input", help="PDF (or .txt) to read; default: the PDF next to this script")
    ap.add_argument("-o", "--output", default=os.path.join(SCRIPT_DIR, "matthew_henry.json"),
                    help="JSON file to write (default: next to this script)")
    ap.add_argument("--plain", action="store_true", help="no live dashboard, just log lines")
    args = ap.parse_args()

    path = args.input or next((p for p in DEFAULT_INPUT_CANDIDATES if os.path.exists(p)), None)
    if not path:
        sys.exit("Could not find the PDF. Tried:\n  " + "\n  ".join(DEFAULT_INPUT_CANDIDATES)
                 + "\nPut it next to this script or pass it with -i /path/to/file.pdf")
    if not os.path.exists(path):
        sys.exit("Input not found: %s" % path)

    state = State()
    state.source = os.path.basename(path)
    use_rich = HAVE_RICH and not args.plain and sys.stdout.isatty()
    if not HAVE_RICH and not args.plain:
        print("(tip: `pip install rich` for the live dashboard)")
    ui = RichUI(state) if use_rich else PlainUI(state)

    state.phase = "Opening PDF"
    total, pages = open_pages(path, state)
    state.total = total
    ui.start()

    parser = Parser(state, ui)
    interrupted = False
    error = None
    state.phase = "Reading pages"
    try:
        for i, text in enumerate(pages, 1):
            state.page = i
            parser.feed_page(i, clean_page(text, state))
            ui.tick()
            if state.total and i > state.total:
                state.total = i
    except KeyboardInterrupt:
        interrupted = True
        ui.log("Ctrl+C received, saving what has been parsed so far", "warn")
    except Exception as e:  # keep partial work on any failure
        error = e
        ui.log("Stopped by error: %s" % e, "error")

    state.phase = "Finishing"
    parser.finish()

    state.phase = "Writing JSON"
    ui.log("Writing %s" % args.output)
    data = {"source": state.source, "complete": not (interrupted or error), "books": parser.books}
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, args.output)
    state.phase = "Done" if data["complete"] else "Stopped early (partial)"
    ui.log("Saved %d books, %d chapters" % (state.books, state.chapters), "chap")
    time.sleep(0.3)  # let the dashboard draw its last frame
    ui.stop()

    print("\nWrote %s%s" % (args.output, "" if data["complete"] else "   (PARTIAL)"))
    print("Pages read: %d/%s   Time: %s   Watermark lines removed: %d   Warnings: %d" % (
        state.page, state.total or "?", fmt_time(time.time() - state.t0), state.watermark, state.warnings))
    print("Books: %d (expected %d)   Chapters: %d (expected %d)\n" % (
        state.books, EXPECTED_BOOKS, state.chapters, EXPECTED_CHAPTERS))
    for b in parser.books:
        print("  %-30s %4d chapters" % (b["book"], len(b["chapters"])))
    if error:
        sys.exit(1)


if __name__ == "__main__":
    main()