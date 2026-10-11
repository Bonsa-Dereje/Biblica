import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';

import { BiblicaService } from '../../core/biblica.service';
import { LoadState, withLoadState } from '../../core/load-state';
import { BookResponse, ChapterPreview, Overview } from '../../core/models';
import { BookAbbrevPipe, CompactPipe, bookAbbrev } from '../../shared/format';
import { Icon } from '../../shared/icon';
import { ChartPoint, LineChart } from '../../shared/line-chart';

/** Genesis 1, Psalm 23, John 3: a good first taste of the commentary. */
const FEATURED_IDS = ['01-001', '19-023', '43-003'];
const EXAMPLE_SEARCHES = ['grace', 'the love of God', 'Psalm 23', 'covenant'];

@Component({
  selector: 'app-dashboard',
  imports: [RouterLink, Icon, LineChart, CompactPipe, BookAbbrevPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class Dashboard {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);

  protected readonly examples = EXAMPLE_SEARCHES;

  protected readonly overview = toSignal(withLoadState(this.api.overview()), {
    initialValue: { status: 'loading' } as LoadState<Overview>,
  });

  protected readonly featured = toSignal(withLoadState(this.api.previews(FEATURED_IDS)), {
    initialValue: { status: 'loading' } as LoadState<{ chapters: ChapterPreview[] }>,
  });

  /** The middle featured card is drawn black, like "Typography" in the design. */
  protected readonly highlightedCard = signal(1);

  /* ---- Chart: whole Bible by book, or one book by chapter ------------- */
  protected readonly chartMode = signal<'books' | 'chapters'>('books');
  protected readonly chartBook = signal(43); // John

  protected readonly bookChapters = toSignal(
    toObservable(this.chartBook).pipe(switchMap((order) => withLoadState(this.api.book(order)))),
    { initialValue: { status: 'loading' } as LoadState<BookResponse> },
  );

  protected readonly chartPoints = computed<ChartPoint[]>(() => {
    if (this.chartMode() === 'books') {
      const o = this.overview();
      return o.status === 'ok' ? o.data.books.map((b) => ({ label: bookAbbrev(b.book), value: b.chars })) : [];
    }
    const c = this.bookChapters();
    return c.status === 'ok' ? c.data.chapters.map((ch) => ({ label: `Ch ${ch.chapter}`, value: ch.chars })) : [];
  });

  protected readonly chartLoading = computed(() =>
    this.chartMode() === 'books' ? this.overview().status === 'loading' : this.bookChapters().status === 'loading',
  );

  protected readonly chartBookName = computed(() => {
    const c = this.bookChapters();
    return c.status === 'ok' ? c.data.book.book : '';
  });

  protected onChartPoint(index: number): void {
    if (this.chartMode() === 'books') {
      const o = this.overview();
      if (o.status !== 'ok') return;
      this.chartBook.set(o.data.books[index].order);
      this.chartMode.set('chapters');
    } else {
      const c = this.bookChapters();
      if (c.status === 'ok') this.router.navigate(['/read', c.data.chapters[index].id]);
    }
  }

  protected onBookSelect(value: string): void {
    this.chartBook.set(Number(value));
    this.chartMode.set('chapters');
  }

  /* ---- Hero ----------------------------------------------------------- */
  protected readonly greeting = (() => {
    const h = new Date().getHours();
    return h < 12 ? 'Good morning.' : h < 18 ? 'Good afternoon.' : 'Good evening.';
  })();

  protected readonly randomLoading = signal(false);

  protected openRandom(): void {
    this.randomLoading.set(true);
    this.api.random().subscribe({
      next: ({ chapter }) => this.router.navigate(['/read', chapter.id]),
      error: () => this.randomLoading.set(false),
    });
  }

  /* ---- Book strip on the right ----------------------------------------- */
  protected scrollStrip(strip: HTMLElement): void {
    strip.scrollBy({ left: strip.clientWidth * 0.8, behavior: 'smooth' });
  }
}
