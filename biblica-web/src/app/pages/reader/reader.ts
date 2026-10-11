import { ChangeDetectionStrategy, Component, ElementRef, computed, inject, input, viewChild } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { switchMap } from 'rxjs';

import { BiblicaService } from '../../core/biblica.service';
import { LoadState, withLoadState } from '../../core/load-state';
import { ChapterResponse } from '../../core/models';
import { CompactPipe } from '../../shared/format';
import { HighlightPipe } from '../../shared/highlight.pipe';
import { Icon } from '../../shared/icon';

/** /read/:id?q=word — one chapter of commentary, with the search words marked. */
@Component({
  selector: 'app-reader',
  imports: [RouterLink, HighlightPipe, CompactPipe, Icon],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reader.html',
  styleUrl: './reader.css',
  host: { '(document:keydown)': 'onKey($event)' },
})
export class Reader {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);
  private readonly body = viewChild<ElementRef<HTMLElement>>('body');

  readonly id = input.required<string>();
  readonly q = input<string>();

  protected readonly query = computed(() => (this.q() ?? '').trim());

  protected readonly state = toSignal(
    toObservable(this.id).pipe(switchMap((id) => withLoadState(this.api.chapter(id)))),
    { initialValue: { status: 'loading' } as LoadState<ChapterResponse> },
  );

  /** How many times the search words appear in this chapter. */
  protected readonly matchCount = computed(() => {
    const s = this.state();
    const words = this.query().split(/\s+/).filter((w) => w.length > 1);
    if (s.status !== 'ok' || !words.length) return 0;
    const re = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'gi');
    return s.data.chapter.text.match(re)?.length ?? 0;
  });

  private markIndex = -1;

  /** Scrolls to the next <mark> in the text, wrapping around at the end. */
  protected nextMatch(): void {
    const marks = this.body()?.nativeElement.querySelectorAll('mark');
    if (!marks?.length) return;
    marks[this.markIndex]?.classList.remove('current');
    this.markIndex = (this.markIndex + 1) % marks.length;
    marks[this.markIndex].classList.add('current');
    marks[this.markIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  /** ← and → page through chapters. */
  protected onKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return;
    const s = this.state();
    if (s.status !== 'ok') return;
    const link = event.key === 'ArrowLeft' ? s.data.prev : event.key === 'ArrowRight' ? s.data.next : null;
    if (link) {
      this.markIndex = -1;
      this.router.navigate(['/read', link.id], { queryParams: { q: this.query() || null } });
    }
  }
}
