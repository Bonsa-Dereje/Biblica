#!/usr/bin/env python3
"""
split_for_mongo.py: turn the fixed Matthew Henry JSON into MongoDB-friendly files.

Why: audit.py / mh-scraper.py write ONE giant document ({"books": [ ...all 66 books... ]}).
MongoDB documents are limited to 16 MB and Compass warns about "possibly bloated
documents" long before that. This script writes one small document per chapter
(default) or per book, so each document is a few KB to a few hundred KB.

Each chapter document looks like:
{
  "_id": "01-001",                 # book order - chapter number (stable, so re-importing is safe)
  "book": "Genesis",
  "order": 1,                      # 1-66, Bible order
  "name_in_source": "G E N E S I S",   # only when the book was renamed by audit.py
  "chapter": 1,
  "heading": "CHAP. I.",
  "title": "The Creation.  B. C. 4004.",
  "text": "...",
  "verse_numbers": [1, 2, 3],
  "verses": [{"verse": 1, "text": "..."}],
  "chars": 12345
}

Usage
    python3 split_for_mongo.py                       # matthew_henry.fixed.json -> matthew_henry.chapters.json
    python3 split_for_mongo.py -i in.json -o out.json
    python3 split_for_mongo.py --by book             # one document per book instead
    python3 split_for_mongo.py --format jsonl        # one document per line (mongoimport's default)
    python3 split_for_mongo.py --no-verses           # drop the "verses" array to make documents smaller

Importing
    Compass:      Collection -> Add Data -> Import JSON -> pick the file (JSON array is the default format here)
    mongoimport:  mongoimport --uri "<your uri>" --db <db> --collection chapters \\
                      --file matthew_henry.chapters.json --jsonArray
                  (with --format jsonl leave out --jsonArray)

Suggested indexes afterwards (mongosh):
    db.chapters.createIndex({ book: 1, chapter: 1 })
    db.chapters.createIndex({ order: 1, chapter: 1 })
"""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MONGO_LIMIT = 16 * 1024 * 1024  # hard limit per document
WARN_AT = 1024 * 1024           # tell the user about anything over 1 MB


def size_of(doc):
    return len(json.dumps(doc, ensure_ascii=False).encode("utf-8"))


def chapter_docs(data, keep_verses):
    docs, used = [], {}
    for pos, b in enumerate(data["books"], 1):
        order = b.get("order") or pos
        for c in b.get("chapters", []):
            _id = "%02d-%03d" % (order, c.get("chapter", 0))
            used[_id] = used.get(_id, 0) + 1
            if used[_id] > 1:  # duplicate chapter number in the data: keep both, distinct ids
                _id += "-dup%d" % (used[_id] - 1)
            text = c.get("text", "") or ""
            doc = {"_id": _id, "book": b["book"], "order": order}
            if b.get("name_in_source"):
                doc["name_in_source"] = b["name_in_source"]
            doc.update({
                "chapter": c.get("chapter"),
                "heading": c.get("heading", ""),
                "title": c.get("title", ""),
                "text": text,
                "verse_numbers": c.get("verse_numbers", []),
            })
            if keep_verses:
                doc["verses"] = c.get("verses", [])
            doc["chars"] = len(text)
            docs.append(doc)
    return docs


def book_docs(data, keep_verses):
    docs = []
    for pos, b in enumerate(data["books"], 1):
        order = b.get("order") or pos
        chapters = []
        for c in b.get("chapters", []):
            ch = dict(c)
            if not keep_verses:
                ch.pop("verses", None)
            chapters.append(ch)
        doc = {"_id": "%02d" % order, "book": b["book"], "order": order}
        if b.get("name_in_source"):
            doc["name_in_source"] = b["name_in_source"]
        doc["chapter_count"] = len(chapters)
        doc["chapters"] = chapters
        docs.append(doc)
    return docs


def main():
    ap = argparse.ArgumentParser(description="Split the fixed Matthew Henry JSON into small MongoDB documents.")
    ap.add_argument("-i", "--input", help="default: matthew_henry.fixed.json next to this script")
    ap.add_argument("-o", "--output", help="default: <input>.chapters.json (or .books.json)")
    ap.add_argument("--by", choices=["chapter", "book"], default="chapter", help="one document per chapter (default) or per book")
    ap.add_argument("--format", choices=["array", "jsonl"], default="array",
                    help="array = one JSON array (default); jsonl = one document per line")
    ap.add_argument("--no-verses", action="store_true", help="leave out the detected \"verses\" arrays (smaller)")
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
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data.get("books"), list):
        sys.exit("This does not look like mh-scraper / audit output (no \"books\" list).")

    base = os.path.splitext(path)[0]
    if base.endswith(".fixed"):
        base = base[: -len(".fixed")]
    ext = ".jsonl" if args.format == "jsonl" else ".json"
    out = args.output or "%s.%ss%s" % (base, args.by, ext)

    keep = not args.no_verses
    docs = chapter_docs(data, keep) if args.by == "chapter" else book_docs(data, keep)

    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if args.format == "jsonl":
            for d in docs:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        else:
            f.write("[\n")
            for i, d in enumerate(docs):
                f.write(json.dumps(d, ensure_ascii=False))
                f.write(",\n" if i + 1 < len(docs) else "\n")
            f.write("]\n")
    os.replace(tmp, out)

    sizes = [size_of(d) for d in docs]
    big = max(zip(sizes, docs), key=lambda t: t[0]) if docs else (0, {})
    print("Read   %s" % path)
    print("Wrote  %s   (%.1f MB, %d documents, one per %s)" % (out, os.path.getsize(out) / 1e6, len(docs), args.by))
    print("Average document: %.1f KB    Largest: %.1f KB (%s)" % (
        sum(sizes) / max(len(sizes), 1) / 1024, big[0] / 1024,
        big[1].get("_id", "?") + " " + str(big[1].get("book", ""))))
    over = [(s, d) for s, d in zip(sizes, docs) if s > WARN_AT]
    if over:
        print("\nDocuments over 1 MB (MongoDB's hard limit is 16 MB):")
        for s, d in sorted(over, key=lambda t: -t[0])[:10]:
            print("   %-10s %-18s %.2f MB%s" % (d["_id"], d["book"], s / 1e6, "   <-- OVER THE LIMIT" if s > MONGO_LIMIT else ""))
        if args.by == "book":
            print("   Tip: use --by chapter to get smaller documents.")
    else:
        print("No document is over 1 MB, so the 'bloated documents' warning should be gone.")


if __name__ == "__main__":
    main()
