import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, shareReplay, tap } from 'rxjs';

import { API_URL } from './api.config';
import {
  BookResponse,
  ChapterPreview,
  ChapterResponse,
  Overview,
  SearchResponse,
} from './models';

/** The only place in the app that knows about URLs and query parameters. */
@Injectable({ providedIn: 'root' })
export class BiblicaService {
  private readonly http = inject(HttpClient);

  // The overview (66 books + totals) is used on several pages, so fetch it once
  // and replay the answer to every later subscriber.
  private overview$?: Observable<Overview>;

  overview(): Observable<Overview> {
    this.overview$ ??= this.get<Overview>({ action: 'overview' }).pipe(
      // Don't cache a failure: the next caller should try again.
      tap({ error: () => (this.overview$ = undefined) }),
      shareReplay(1),
    );
    return this.overview$;
  }

  search(q: string, page = 1, limit = 20, order?: number | null): Observable<SearchResponse> {
    const params: Record<string, string | number> = { action: 'search', q, page, limit };
    if (order) params['order'] = order;
    return this.get<SearchResponse>(params);
  }

  book(order: number): Observable<BookResponse> {
    return this.get<BookResponse>({ action: 'book', order });
  }

  chapter(id: string): Observable<ChapterResponse> {
    return this.get<ChapterResponse>({ action: 'chapter', id });
  }

  previews(ids: string[]): Observable<{ chapters: ChapterPreview[] }> {
    return this.get<{ chapters: ChapterPreview[] }>({ action: 'chapters', ids: ids.join(',') });
  }

  random(): Observable<{ chapter: ChapterPreview }> {
    return this.get<{ chapter: ChapterPreview }>({ action: 'random' });
  }

  private get<T>(params: Record<string, string | number>): Observable<T> {
    return this.http.get<T>(API_URL, { params: new HttpParams({ fromObject: params }) });
  }
}
