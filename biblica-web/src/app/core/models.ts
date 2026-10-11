// Shapes of the JSON that /api/biblica returns.
// Keep these in sync with api/biblica.js on the backend.

export interface BookSummary {
  order: number;
  book: string;
  chapters: number;
  chars: number;
  testament: 'OT' | 'NT';
}

export interface Overview {
  books: BookSummary[];
  totals: { books: number; chapters: number; chars: number };
}

/** A chapter without its full text (used in lists). */
export interface ChapterMeta {
  id: string;
  book: string;
  order: number;
  chapter: number;
  heading: string;
  title: string;
  chars: number;
  verseCount: number;
}

export interface ChapterPreview extends ChapterMeta {
  preview: string;
}

export interface SearchHit extends ChapterMeta {
  snippet: string;
  hits: number;
}

export interface Reference {
  book: string;
  order: number;
  chapter: number | null;
  verse: number | null;
  id: string | null;
}

export interface SearchResponse {
  query: string;
  mode: 'regex' | 'text-index';
  page: number;
  limit: number;
  total: number;
  pages: number;
  ref: Reference | null;
  results: SearchHit[];
}

export interface BookResponse {
  book: { order: number; book: string; chapters: number };
  chapters: ChapterMeta[];
}

export interface ChapterLink {
  id: string;
  book: string;
  order: number;
  chapter: number;
}

export interface Chapter extends Omit<ChapterMeta, 'verseCount'> {
  name_in_source?: string;
  text: string;
  verse_numbers?: number[];
  verses?: { verse: number; text: string }[];
}

export interface ChapterResponse {
  chapter: Chapter;
  prev: ChapterLink | null;
  next: ChapterLink | null;
}
