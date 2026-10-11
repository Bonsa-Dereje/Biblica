import { HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, map, of, startWith } from 'rxjs';

/**
 * Every request in the app is in one of three states. Using one union type
 * means the template can't show `data` while it's still loading:
 *
 *   @if (state().status === 'ok') { {{ state().data }} }
 */
export type LoadState<T> =
  | { status: 'loading' }
  | { status: 'ok'; data: T }
  | { status: 'error'; error: string };

/** Wraps an HTTP observable so it emits loading -> ok | error. */
export function withLoadState<T>(source: Observable<T>): Observable<LoadState<T>> {
  return source.pipe(
    map((data): LoadState<T> => ({ status: 'ok', data })),
    startWith<LoadState<T>>({ status: 'loading' }),
    catchError((err) => of<LoadState<T>>({ status: 'error', error: errorMessage(err) })),
  );
}

export function errorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    // status 0 = the request never got an answer (offline, CORS, wrong URL).
    if (err.status === 0) return "Couldn't reach the API. Check your connection or the API URL.";
    const body = err.error as { error?: string } | null;
    return body?.error ?? `The API answered ${err.status} ${err.statusText}`;
  }
  return err instanceof Error ? err.message : 'Something went wrong';
}
