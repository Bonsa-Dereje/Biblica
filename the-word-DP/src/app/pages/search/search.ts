import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { of, switchMap } from 'rxjs';

import { BiblicaService } from '../../core/biblica.service';
import { LoadState, withLoadState } from '../../core/load-state';
import { Overview, SearchResponse } from '../../core/models';
import { HighlightPipe } from '../../shared/highlight.pipe';
import { Icon } from '../../shared/icon';

type PageState = LoadState<SearchResponse> | { status: 'idle' };

/** /search?q=grace&page=2&order=43 — the full, paginated result list. */
@Component({
  selector: 'app-search-page',
  imports: [RouterLink, HighlightPipe, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search.html',
  styleUrl: './search.css',
})
export class SearchPage {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);

  // Query params arrive as inputs (always strings, or undefined when missing).
  readonly q = input<string>();
  readonly page = input<string>();
  readonly order = input<string>();

  protected readonly query = computed(() => (this.q() ?? '').trim());
  protected readonly pageNumber = computed(() => Math.max(1, Number(this.page()) || 1));
  protected readonly bookOrder = computed(() => Number(this.order()) || null);

  private readonly request = computed(() => ({ q: this.query(), page: this.pageNumber(), order: this.bookOrder() }));

  protected readonly state = toSignal(
    toObservable(this.request).pipe(
      switchMap(({ q, page, order }) =>
        q.length < 2 ? of<PageState>({ status: 'idle' }) : withLoadState(this.api.search(q, page, 20, order)),
      ),
    ),
    { initialValue: { status: 'loading' } as PageState },
  );

  protected readonly overview = toSignal(withLoadState(this.api.overview()), {
    initialValue: { status: 'loading' } as LoadState<Overview>,
  });

  protected filterByBook(value: string): void {
    this.router.navigate([], {
      queryParams: { order: value || null, page: null },
      queryParamsHandling: 'merge',
    });
  }
}
