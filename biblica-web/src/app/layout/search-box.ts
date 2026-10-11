import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { debounceTime, distinctUntilChanged, map, of, switchMap } from 'rxjs';

import { BiblicaService } from '../core/biblica.service';
import { LoadState, withLoadState } from '../core/load-state';
import { SearchResponse } from '../core/models';
import { HighlightPipe } from '../shared/highlight.pipe';
import { Icon } from '../shared/icon';

type SearchState = LoadState<SearchResponse> | { status: 'idle' };

interface Option {
  kind: 'ref' | 'hit' | 'all';
  title: string;
  detail: string;
  commands: unknown[];
  queryParams?: Record<string, string>;
}

/**
 * The search bar in the top bar. Typing searches the commentaries collection
 * (debounced), shows the first few hits in a dropdown, and Enter opens the
 * full results page.
 */
@Component({
  selector: 'app-search-box',
  imports: [Icon, HighlightPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './search-box.html',
  styleUrl: './search-box.css',
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown)': 'onGlobalKey($event)',
  },
})
export class SearchBox {
  private readonly api = inject(BiblicaService);
  private readonly router = inject(Router);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly inputEl = viewChild.required<ElementRef<HTMLInputElement>>('input');

  protected readonly query = signal('');
  protected readonly open = signal(false);
  protected readonly activeIndex = signal(-1);

  // signal -> observable -> wait for typing to pause -> one request at a time
  // (switchMap cancels the previous request) -> back to a signal.
  protected readonly state = toSignal(
    toObservable(this.query).pipe(
      map((q) => q.trim()),
      debounceTime(250),
      distinctUntilChanged(),
      switchMap((q) =>
        q.length < 2 ? of<SearchState>({ status: 'idle' }) : withLoadState(this.api.search(q, 1, 6)),
      ),
    ),
    { initialValue: { status: 'idle' } as SearchState },
  );

  /** Everything the dropdown can show, in keyboard order. */
  protected readonly options = computed<Option[]>(() => {
    const s = this.state();
    if (s.status !== 'ok') return [];
    const { ref, results, total, query } = s.data;
    const opts: Option[] = [];

    if (ref?.id) {
      opts.push({ kind: 'ref', title: `Go to ${ref.book} ${ref.chapter}`, detail: 'Open this chapter', commands: ['/read', ref.id] });
    } else if (ref) {
      opts.push({ kind: 'ref', title: `Open ${ref.book}`, detail: 'See every chapter', commands: ['/book', ref.order] });
    }

    for (const hit of results) {
      opts.push({
        kind: 'hit',
        title: `${hit.book} ${hit.chapter}`,
        detail: hit.snippet,
        commands: ['/read', hit.id],
        queryParams: { q: query },
      });
    }

    if (total > 0) {
      opts.push({ kind: 'all', title: `See all ${total} results`, detail: '', commands: ['/search'], queryParams: { q: query } });
    }
    return opts;
  });

  protected onInput(value: string): void {
    this.query.set(value);
    this.open.set(true);
    this.activeIndex.set(-1);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const count = this.options().length;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.open.set(true);
        this.activeIndex.update((i) => (count ? (i + 1) % count : -1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.activeIndex.update((i) => (count ? (i - 1 + count) % count : -1));
        break;
      case 'Enter': {
        event.preventDefault();
        const chosen = this.options()[this.activeIndex()];
        if (chosen) this.choose(chosen);
        else if (this.query().trim().length >= 2) {
          this.go(['/search'], { q: this.query().trim() });
        }
        break;
      }
      case 'Escape':
        this.open.set(false);
        this.inputEl().nativeElement.blur();
        break;
    }
  }

  protected choose(option: Option): void {
    this.go(option.commands, option.queryParams);
  }

  protected clear(): void {
    this.query.set('');
    this.inputEl().nativeElement.focus();
  }

  private go(commands: unknown[], queryParams?: Record<string, string>): void {
    this.open.set(false);
    this.activeIndex.set(-1);
    this.router.navigate(commands, { queryParams });
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (!this.host.nativeElement.contains(event.target as Node)) this.open.set(false);
  }

  /** Press "/" anywhere to jump to the search bar. */
  protected onGlobalKey(event: KeyboardEvent): void {
    const target = event.target as HTMLElement | null;
    const typing = target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
    if (event.key === '/' && !typing) {
      event.preventDefault();
      this.inputEl().nativeElement.focus();
    }
  }
}
