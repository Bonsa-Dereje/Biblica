import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { compact } from './format';

export interface ChartPoint {
  label: string;
  value: number;
}

const W = 900;
const H = 200;
const PAD_X = 24;
const PAD_TOP = 40; // room for the hover bubble
const PAD_BOTTOM = 20;

/**
 * A smooth single-line chart in plain SVG (no chart library).
 * Hover shows the value in a small black bubble, like the design's "1.2k" tag.
 */
@Component({
  selector: 'app-line-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './line-chart.css',
  template: `
    @if (coords().length > 1) {
      <svg
        [attr.viewBox]="'0 0 ' + W + ' ' + H"
        role="img"
        [attr.aria-label]="ariaLabel()"
        (mousemove)="onMove($event)"
        (mouseleave)="active.set(null)"
        (click)="onClick()"
        [class.clickable]="clickable()"
      >
        <line class="base" [attr.x1]="PAD_X" [attr.x2]="W - PAD_X" [attr.y1]="H - PAD_BOTTOM" [attr.y2]="H - PAD_BOTTOM" />
        <path class="area" [attr.d]="areaPath()" />
        <path class="line" [attr.d]="linePath()" />

        @if (activePoint(); as p) {
          <line class="guide" [attr.x1]="p.x" [attr.x2]="p.x" [attr.y1]="p.y" [attr.y2]="H - PAD_BOTTOM" />
          <circle class="dot" [attr.cx]="p.x" [attr.cy]="p.y" r="5" />
          <g [attr.transform]="'translate(' + bubbleX(p.x) + ',' + (p.y - 34) + ')'">
            <rect class="bubble" x="-48" y="0" width="96" height="24" rx="6" />
            <text class="bubble-text" x="0" y="16">{{ p.label }} · {{ p.short }}</text>
          </g>
        }
      </svg>
    } @else {
      <p class="empty">Not enough data to draw a line.</p>
    }
  `,
})
export class LineChart {
  protected readonly W = W;
  protected readonly H = H;
  protected readonly PAD_X = PAD_X;
  protected readonly PAD_BOTTOM = PAD_BOTTOM;

  readonly points = input<ChartPoint[]>([]);
  readonly ariaLabel = input('Line chart');
  readonly clickable = input(false);
  /** Index of the point that was clicked. */
  readonly pointClick = output<number>();

  protected readonly active = signal<number | null>(null);

  protected readonly coords = computed(() => {
    const pts = this.points();
    if (pts.length < 2) return [];
    const max = Math.max(...pts.map((p) => p.value), 1);
    const min = Math.min(...pts.map((p) => p.value));
    const span = max - min || 1;
    const stepX = (W - PAD_X * 2) / (pts.length - 1);
    return pts.map((p, i) => ({
      x: PAD_X + i * stepX,
      y: PAD_TOP + (1 - (p.value - min) / span) * (H - PAD_TOP - PAD_BOTTOM),
      label: p.label,
      short: compact(p.value),
    }));
  });

  // Catmull-Rom spline turned into cubic Bézier segments: passes through every
  // point and gives the soft curve from the design.
  protected readonly linePath = computed(() => {
    const c = this.coords();
    if (c.length < 2) return '';
    let d = `M${c[0].x},${c[0].y}`;
    for (let i = 0; i < c.length - 1; i++) {
      const p0 = c[i - 1] ?? c[i];
      const p1 = c[i];
      const p2 = c[i + 1];
      const p3 = c[i + 2] ?? p2;
      const cp1x = p1.x + (p2.x - p0.x) / 6;
      const cp1y = p1.y + (p2.y - p0.y) / 6;
      const cp2x = p2.x - (p3.x - p1.x) / 6;
      const cp2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`;
    }
    return d;
  });

  protected readonly areaPath = computed(() => {
    const c = this.coords();
    if (c.length < 2) return '';
    const base = H - PAD_BOTTOM;
    return `${this.linePath()} L${c[c.length - 1].x},${base} L${c[0].x},${base} Z`;
  });

  protected readonly activePoint = computed(() => {
    const i = this.active();
    return i === null ? null : (this.coords()[i] ?? null);
  });

  protected onMove(event: MouseEvent): void {
    const svg = event.currentTarget as SVGSVGElement;
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * W;
    const n = this.coords().length;
    const i = Math.round(((x - PAD_X) / (W - PAD_X * 2)) * (n - 1));
    this.active.set(Math.min(Math.max(i, 0), n - 1));
  }

  protected onClick(): void {
    const i = this.active();
    if (i !== null && this.clickable()) this.pointClick.emit(i);
  }

  /** Keeps the bubble inside the chart at both ends. */
  protected bubbleX(x: number): number {
    return Math.min(Math.max(x, 52), W - 52);
  }
}
