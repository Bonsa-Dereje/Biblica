import { Pipe, PipeTransform } from '@angular/core';

const compactFormat = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

/** 1234 -> "1.2K", 34200000 -> "34.2M" */
export function compact(n: number | null | undefined): string {
  return compactFormat.format(n ?? 0);
}

@Pipe({ name: 'compact' })
export class CompactPipe implements PipeTransform {
  transform(n: number | null | undefined): string {
    return compact(n);
  }
}

/** "Genesis" -> "Gen", "1 John" -> "1Jn"-style short labels for the round book chips. */
export function bookAbbrev(name: string): string {
  const m = name.match(/^(\d)\s*(.*)$/);
  if (m) return m[1] + m[2].slice(0, 2);
  return name.replace(/\s+/g, '').slice(0, 3);
}

@Pipe({ name: 'bookAbbrev' })
export class BookAbbrevPipe implements PipeTransform {
  transform(name: string): string {
    return bookAbbrev(name);
  }
}

/** Builds the same chapter id the database uses: order 43, chapter 3 -> "43-003". */
export function chapterId(order: number, chapter: number): string {
  return `${String(order).padStart(2, '0')}-${String(chapter).padStart(3, '0')}`;
}
