import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { BiblicaService } from '../../core/biblica.service';
import { LoadState, withLoadState } from '../../core/load-state';
import { BookSummary, Overview } from '../../core/models';
import { BookAbbrevPipe, CompactPipe } from '../../shared/format';

/** All 66 books, split into Old and New Testament, with a quick filter. */
@Component({
  selector: 'app-books',
  imports: [RouterLink, CompactPipe, BookAbbrevPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './books.css',
  template: `
    <h1 class="page-title">Books</h1>
    <p class="page-sub">Every book in the commentary. Pick one to see its chapters.</p>

    <input
      class="filter"
      type="search"
      placeholder="Filter books…"
      aria-label="Filter books"
      [value]="filter()"
      (input)="filter.set($any($event.target).value)"
    />

    @let ov = overview();
    @if (ov.status === 'loading') {
      <p class="state"><span class="spinner"></span> Loading books…</p>
    } @else if (ov.status === 'error') {
      <p class="state error">{{ ov.error }}</p>
    } @else {
      @for (group of groups(); track group.name) {
        @if (group.books.length) {
          <section>
            <div class="section-head"><h2>{{ group.name }}</h2><span class="count">{{ group.books.length }} books</span></div>
            <div class="grid">
              @for (b of group.books; track b.order) {
                <a class="book" [routerLink]="['/book', b.order]">
                  <span class="abbr" [class.nt]="b.testament === 'NT'">{{ b.book | bookAbbrev }}</span>
                  <span class="info">
                    <strong>{{ b.book }}</strong>
                    <small>{{ b.chapters }} chapters · {{ b.chars | compact }} chars</small>
                  </span>
                </a>
              }
            </div>
          </section>
        }
      }
      @if (!groups()[0].books.length && !groups()[1].books.length) {
        <p class="state">No book matches “{{ filter() }}”.</p>
      }
    }
  `,
})
export class Books {
  private readonly api = inject(BiblicaService);

  protected readonly filter = signal('');
  protected readonly overview = toSignal(withLoadState(this.api.overview()), {
    initialValue: { status: 'loading' } as LoadState<Overview>,
  });

  protected readonly groups = computed(() => {
    const ov = this.overview();
    const all: BookSummary[] = ov.status === 'ok' ? ov.data.books : [];
    const f = this.filter().trim().toLowerCase();
    const shown = f ? all.filter((b) => b.book.toLowerCase().includes(f)) : all;
    return [
      { name: 'Old Testament', books: shown.filter((b) => b.testament === 'OT') },
      { name: 'New Testament', books: shown.filter((b) => b.testament === 'NT') },
    ];
  });
}
