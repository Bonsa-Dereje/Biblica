import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type IconName =
  | 'home'
  | 'grid'
  | 'search'
  | 'shuffle'
  | 'book'
  | 'layers'
  | 'type'
  | 'chevron-right'
  | 'chevron-left'
  | 'arrow-left'
  | 'code'
  | 'close';

/** Small stroke icons, drawn inline so they pick up `color` from CSS. */
@Component({
  selector: 'app-icon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { 'aria-hidden': 'true' },
  styles: `
    :host { display: inline-flex; width: var(--icon-size, 20px); height: var(--icon-size, 20px); }
    svg { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 1.8;
          stroke-linecap: round; stroke-linejoin: round; }
  `,
  template: `
    <svg viewBox="0 0 24 24">
      @switch (name()) {
        @case ('home') {
          <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />
        }
        @case ('grid') {
          <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" />
          <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" />
          <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" />
          <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" />
        }
        @case ('search') {
          <circle cx="11" cy="11" r="6.5" />
          <path d="m16 16 4 4" />
        }
        @case ('shuffle') {
          <path d="M4 7h3.5c2 0 3.2 1 4.3 2.8l1.4 2.4c1.1 1.8 2.3 2.8 4.3 2.8H20" />
          <path d="M4 17h3.5c1.4 0 2.4-.5 3.2-1.4M13.3 8.4c.8-.9 1.8-1.4 3.2-1.4H20" />
          <path d="m17.5 4.5 2.5 2.5-2.5 2.5M17.5 12.5l2.5 2.5-2.5 2.5" />
        }
        @case ('book') {
          <path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v13H6.5A1.5 1.5 0 0 0 5 18.5z" />
          <path d="M5 18.5A1.5 1.5 0 0 0 6.5 20H19v-3" />
          <path d="M9 8h6" />
        }
        @case ('layers') {
          <path d="m12 4 8 4-8 4-8-4z" />
          <path d="m4 12 8 4 8-4" />
          <path d="m4 16 8 4 8-4" />
        }
        @case ('type') {
          <path d="M5 7V5h14v2M12 5v14M9 19h6" />
        }
        @case ('chevron-right') {
          <path d="m10 6 6 6-6 6" />
        }
        @case ('chevron-left') {
          <path d="m14 6-6 6 6 6" />
        }
        @case ('arrow-left') {
          <path d="M19 12H5M11 6l-6 6 6 6" />
        }
        @case ('code') {
          <path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14" />
        }
        @case ('close') {
          <path d="M6 6l12 12M18 6 6 18" />
        }
      }
    </svg>
  `,
})
export class Icon {
  readonly name = input.required<IconName>();
}
