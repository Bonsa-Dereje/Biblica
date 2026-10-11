import { Pipe, PipeTransform } from '@angular/core';

const escapeHtml = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const escapeRegex = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Wraps every word of `query` found in `text` in <mark>.
 * Use with [innerHTML]: the text is HTML-escaped first, so commentary text can
 * never inject markup; only our own <mark> tags end up as HTML.
 *
 *   <p [innerHTML]="hit.snippet | highlight: query"></p>
 */
@Pipe({ name: 'highlight' })
export class HighlightPipe implements PipeTransform {
  transform(text: string | null | undefined, query: string | null | undefined): string {
    const safe = escapeHtml(text ?? '');
    const words = (query ?? '')
      .trim()
      .split(/\s+/)
      .filter((w) => w.length > 1)
      .map((w) => escapeRegex(escapeHtml(w)));
    if (!words.length) return safe;
    return safe.replace(new RegExp(`(${words.join('|')})`, 'gi'), '<mark>$1</mark>');
  }
}
