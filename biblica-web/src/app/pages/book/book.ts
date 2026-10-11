import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';

import { BiblicaService } from '../../core/biblica.service';
import { LoadState, withLoadState } from '../../core/load-state';
import { BookResponse } from '../../core/models';
import { CompactPipe } from '../../shared/format';
import { Icon } from '../../shared/icon';
import { LineChart } from '../../shared/line-chart';

/** /book/:order — every chapter of one book. */
@Component({
  selector: 'app-book',
  imports: [RouterLink, CompactPipe, LineChart, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './book.css',
  template: `
    @let s = state();
    <nav class="crumbs"><a routerLink="/books">Books</a> <app-icon name="chevron-right" /> <span>{{ s.status === 'ok' ? s.data.book.book : '…' }}</span></nav>

    @if (s.status === 'loading') {
      <p class="state"><span class="spinner"></span> Loading chapters…</p>
    } @else if (s.status === 'error') {
      <p class="state error">{{ s.error }}</p>
    } @else {
      <h1 class="page-title">{{ s.data.book.book }}</h1>
      <p class="page-sub">{{ s.data.book.chapters }} chapters of commentary</p>

      @if (s.data.chapters.length > 1) {
        <div class="card chart">
          <div class="section-head"><h2>Length by chapter</h2><span class="hint">Click a point to read it</span></div>
          <app-line-chart [points]="points()" [clickable]="true" ariaLabel="Characters per chapter" (pointClick)="open($event)" />
        </div>
      }

      <ol class="chapters">
        @for (c of s.data.chapters; track c.id) {
          <li>
            <a [routerLink]="['/read', c.id]">
              <span class="num">{{ c.chapter }}</span>
              <span class="text">
                <strong>{{ c.title || c.heading || 'Chapter ' + c.chapter }}</strong>
                <small>{{ c.verseCount ? c.verseCount + ' verses · ' : '' }}{{ c.chars | compact }} chars</small>
              </span>
              <app-icon name="chevron-right" />
            </a>
          </li>
        }
      </ol>
    }
  `,
})
export class BookPage {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);

  /** Filled from the :order route param (withComponentInputBinding). */
  readonly order = input.required<string>();

  protected readonly state = toSignal(
    toObservable(this.order).pipe(switchMap((o) => withLoadState(this.api.book(Number(o))))),
    { initialValue: { status: 'loading' } as LoadState<BookResponse> },
  );

  protected readonly points = computed(() => {
    const s = this.state();
    return s.status === 'ok' ? s.data.chapters.map((c) => ({ label: `Ch ${c.chapter}`, value: c.chars })) : [];
  });

  protected open(index: number): void {
    const s = this.state();
    if (s.status === 'ok') this.router.navigate(['/read', s.data.chapters[index].id]);
  }
}
