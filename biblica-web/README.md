# Biblica web

Angular dashboard for searching Matthew Henry's commentary stored in MongoDB
(cluster **Tinker** → database **Biblica** → collection **commentaries**).
The data comes from the backend at `https://tinker-backend.vercel.app/api/biblica`.

## Run

```bash
npm install
npm start            # http://localhost:4200
npm run build        # output in dist/biblica-web/browser
```

The API URL lives in `src/app/core/api.config.ts`.

## Deploy on Vercel

Framework preset: Angular. Output directory: `dist/biblica-web/browser`.
`vercel.json` rewrites every path to `index.html` so deep links like `/read/43-003` work on refresh.

## How a search flows

```
type in the search bar (layout/search-box.ts)
  → signal → toObservable → debounceTime(250) → switchMap (cancels the old request)
  → BiblicaService.search()  GET /api/biblica?action=search&q=...
  → api/biblica.js: $match (regex or $text) → $facet { total, page of results + snippet }
  → dropdown; Enter → /search?q=...; click → /read/:id?q=...
```

## Pages

| Route          | File                              | API call             |
| -------------- | --------------------------------- | -------------------- |
| `/`            | pages/dashboard                   | overview, chapters, book |
| `/books`       | pages/books/books.ts              | overview             |
| `/book/:order` | pages/book/book.ts                | book                 |
| `/search?q=`   | pages/search                      | search               |
| `/read/:id?q=` | pages/reader                      | chapter              |
