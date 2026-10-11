# Biblica

Matthew Henry's *Commentary on the Whole Bible* as structured JSON: 66 books,
1,188 chapters, about 39 million characters of commentary. It's split by book
and chapter, with the quoted verses pulled out where they could be detected.

This repo has the data and the Python scripts that produced it from the PDF.

## What's in here

| Path | What it is |
| --- | --- |
| `matthew_henry.json` | The full commentary as one document: `{ source, complete, audit_log, books: [...] }`. Already cleaned by `audit.py`. |
| `matthew_henry.chapters.json` | The same data as a JSON array with one document per chapter, ready to import into MongoDB. |
| `mh-scraper.py` | Reads the PDF page by page and writes the book → chapter JSON. |
| `audit.py` | Checks the JSON against the real Bible (66 books, 1,189 chapters) and fixes book names and stray fragments, asking before each fix. |
| `review.py` | Read-only report of every book and chapter, plus a `review.html` page for checking chapters by hand. |
| `split_for_mongo.py` | Turns the single big document into one small document per chapter (or per book). |
## Data format

### `matthew_henry.chapters.json` (one document per chapter)

```json
{
  "_id": "01-001",
  "book": "Genesis",
  "order": 1,
  "name_in_source": "GENESIS",
  "chapter": 1,
  "heading": "CHAP. I.",
  "title": "The Creation.  B. C. 4004.",
  "text": "The foundation of all religion being laid in our relation to God as our Creator, ...",
  "verse_numbers": [1, 2, 3],
  "verses": [{ "verse": 1, "text": "In the beginning God created the heaven and the earth." }],
  "chars": 60928
}
```

| Field | Notes |
| --- | --- |
| `_id` | `<book order>-<chapter>`, zero-padded, so it stays the same if you re-import. Two duplicate chapters get a suffix: `23-018-dup1`, `24-041-dup1`. |
| `book` | Standard English name ("1 Chronicles", "Song of Solomon"). |
| `order` | 1–66 in Protestant Bible order. 1–39 is the Old Testament, 40–66 the New. |
| `name_in_source` | The book name as printed in the PDF, before `audit.py` renamed it. |
| `heading` | Chapter heading exactly as printed (`CHAP. IV.`). |
| `title` | The running title under the heading, when there is one. |
| `text` | The full commentary for the chapter, untouched. Treat this as the source of truth. |
| `verse_numbers`, `verses` | Best-effort verse detection (see limitations). |
| `chars` | Length of `text`. |

### `matthew_henry.json` (single document)

Same chapter objects, nested inside books:

```json
{
  "source": "Matthew_Henrys_Commentary_on_the_Whole_Bible_-_Matthew_Henry.pdf",
  "complete": true,
  "audit_log": { "audited_at": "...", "applied": ["Remove 6 front-matter entries ...", "..."] },
  "books": [
    { "book": "Genesis", "order": 1, "name_in_source": "GENESIS", "chapters": [ ... ] }
  ]
}
```

At ~46 MB this is too large to import into MongoDB as a single document
(the limit is 16 MB). Use the chapters file for databases.

## Known limitations

**Missing and duplicated chapters.** The chapter count is 1,188, not 1,189.
These books don't match the Bible:

| Book | Found / expected | Problem |
| --- | --- | --- |
| Joshua | 23 / 24 | Chapter 15 missing |
| Job | 41 / 42 | Chapter 29 missing |
| Isaiah | 66 / 66 | Chapter 28 missing; chapter 18 appears twice |
| Jeremiah | 53 / 52 | Chapter 41 appears twice |

The missing chapters are probably merged into a neighbouring chapter's `text`,
where the PDF heading wasn't recognised. Run
`python3 review.py --book Joshua --text` to look at them.

**Verse detection is approximate.** The PDF is running text, so quoted scripture
isn't visually separated from commentary. Verse numbers are detected as an
ascending run of numbers in front of capitalised text, and each verse runs to
the next number or the end of the first sentence. Some verses get cut short.
The full chapter `text` is always kept, so nothing is lost.

## Rebuilding the data from the PDF

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt     # pypdf, rich
# optional, much faster: poppler's pdftotext (apt install poppler-utils / brew install poppler)

python3 mh-scraper.py -i Matthew_Henrys_Commentary_on_the_Whole_Bible_-_Matthew_Henry.pdf
python3 audit.py                     # asks before every fix → matthew_henry.fixed.json
python3 review.py                    # console report + review.html
python3 split_for_mongo.py           # → matthew_henry.chapters.json
```

The PDF isn't in the repo.

The scraper's default output is `matthew_henry.json`, so a rerun overwrites the
cleaned file with raw output. Write the raw output somewhere else instead, e.g.
`-o matthew_henry.raw.json`, then run `audit.py -i matthew_henry.raw.json`.

`split_for_mongo.py` options:

```bash
python3 split_for_mongo.py --by book        # one document per book instead of per chapter
python3 split_for_mongo.py --format jsonl   # one document per line
python3 split_for_mongo.py --no-verses      # drop the verses arrays (smaller)
```

## Loading into MongoDB

```bash
mongoimport --uri "<your Atlas URI>" --db Biblica --collection commentaries \
  --file matthew_henry.chapters.json --jsonArray
```

In Compass you can instead use *Add Data → Import JSON*.

Then, in mongosh, add indexes. The text index makes word search fast:

```js
use Biblica
db.commentaries.createIndex({ order: 1, chapter: 1 })
db.commentaries.createIndex({ title: "text", text: "text" }, { weights: { title: 5, text: 1 } })
```

## Source and license

The commentary was written by Matthew Henry in the early 1700s (he died in 1714)
and is in the public domain. The JSON was extracted from a PDF edition, so there
are text-extraction and layout errors in places. Corrections are welcome.