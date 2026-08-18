// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A total is written the way the column it sums is written.
//
// Measured on the published frames of /finance and /contracts, in German: the
// footer read `225.297,6 $` while the rows above it read `133.794,64 $`. One
// decimal against two, in the same column, on the two figures a reader is most
// likely to compare. On a euro project the same cell instead collapsed to
// `9,4 Mio. €`, and a four-figure total came out as `3088,4 $` - one decimal
// and no thousands separator - two rows under `3.013,85 $`.
//
// All three are one cause. The footers asked <MoneyDisplay> for `compact`, and
// that prop does two things at once: it turns on `notation: 'compact'` and it
// replaces the currency's own minor units with `[0, 1]` fraction digits. German
// has no short currency form below a million, so under a million the notation
// changes nothing and the digit override is all that survives - a full-length
// number written to one decimal, and, below ten thousand, without its grouping.
// Above a million the notation does fire and the figure collapses. Which of the
// three shapes a reader sees depends on the size of the total, so the same
// column disagrees with itself at different times of the project.
//
// The fix is not to make `compact` cleverer. It is that a column is compact all
// the way down or not at all, and a money column in a wide register is not.
//
// Two halves:
//
//   * the mechanism, rendered rather than argued: a compacted footer cannot
//     agree with the column above it, and this is stated as a property of the
//     rendered strings rather than as a quoted example, so it keeps meaning the
//     same thing when the amounts change;
//   * the census, because fixing the eleven footers that were wrong would leave
//     the twelfth free to be written the same way tomorrow.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { render, cleanup } from '@testing-library/react';

import { MoneyDisplay } from './MoneyDisplay';
import { MultiCurrencyTotal } from './MultiCurrencyTotal';
import { usePreferencesStore, type NumberLocale } from '@/stores/usePreferencesStore';

const FEATURES = join(__dirname, '..', '..', 'features');

/**
 * A budget column and its total, in the shape the register holds them: rows
 * that each carry their own currency, and a footer that sums them.
 */
const ROWS = [133_794.64, 91_502.96];
/** The same column an order of magnitude up, where compact notation fires. */
const LARGE_ROWS = [4_700_000, 4_700_000];

/**
 * Three of the locales the number-format preference actually offers, chosen
 * because they disagree about all three things that could hide the defect:
 * the decimal mark, the group separator, and which side the currency symbol
 * sits on. A locale outside that union is not a reader this product has.
 */
const READERS: NumberLocale[] = ['de-DE', 'en-US', 'fr-FR'];

interface Shape {
  /** How many digits follow the decimal separator of this locale. */
  fraction: number;
  /** The words in the string: a magnitude term like "Mio" shows up here. */
  words: string;
}

/**
 * The two things that differed on the frame, read off a rendered string.
 *
 * Deliberately not a comparison of the strings themselves - a total and a row
 * are different amounts and will never be equal. What has to be equal is how
 * they are written.
 */
function shapeOf(text: string, locale: string): Shape {
  const decimal =
    new Intl.NumberFormat(locale).formatToParts(1.5).find((p) => p.type === 'decimal')?.value ?? '.';
  const at = text.lastIndexOf(decimal);
  const fraction = at < 0 ? 0 : (text.slice(at + 1).match(/^\d+/)?.[0].length ?? 0);
  return { fraction, words: (text.match(/\p{L}+/gu) ?? []).join(' ') };
}

function speakNumbers(locale: NumberLocale) {
  usePreferencesStore.setState({ numberLocale: locale });
}

beforeEach(() => {
  localStorage.clear();
  usePreferencesStore.getState().resetPreferences();
});

afterEach(() => {
  cleanup();
});

describe('the footer of a money column', () => {
  it.each(READERS)('is written like the cells above it in %s', (locale) => {
    speakNumbers(locale);
    for (const amounts of [ROWS, LARGE_ROWS]) {
      const cell = render(<MoneyDisplay amount={amounts[0]!} currency="EUR" />).container.textContent!;
      cleanup();
      const total = render(
        <MultiCurrencyTotal
          items={amounts.map((amount) => ({ amount, currency: 'EUR' }))}
          variant="inline"
        />,
      ).container.textContent!;
      cleanup();

      expect(shapeOf(total, locale), `total "${total}" against cell "${cell}"`).toEqual(
        shapeOf(cell, locale),
      );
    }
  });

  // Guards the guard, and states the defect. If `compact` were a neutral
  // space-saving choice the assertion above would pass either way, and this
  // file would be proving nothing. It is not neutral: it changes the reading
  // under a million and the notation over one, in the same column.
  it('could not be written like them while it was compacted', () => {
    speakNumbers('de-DE');

    const cell = render(<MoneyDisplay amount={ROWS[0]!} currency="USD" />).container.textContent!;
    cleanup();
    const compactedSmall = render(
      <MoneyDisplay amount={ROWS[0]! + ROWS[1]!} currency="USD" compact />,
    ).container.textContent!;
    cleanup();
    const compactedLarge = render(
      <MoneyDisplay amount={LARGE_ROWS[0]! + LARGE_ROWS[1]!} currency="USD" compact />,
    ).container.textContent!;
    cleanup();

    // Under a million: the same length as the rows, to a different precision.
    expect(shapeOf(compactedSmall, 'de-DE').fraction).not.toBe(shapeOf(cell, 'de-DE').fraction);
    expect(shapeOf(compactedSmall, 'de-DE').words).toBe(shapeOf(cell, 'de-DE').words);
    // Over a million: a magnitude word the column never uses.
    expect(shapeOf(compactedLarge, 'de-DE').words).not.toBe(shapeOf(cell, 'de-DE').words);
  });

  it('loses the thousands separator on a four-figure total', () => {
    // The third shape from the frame, and the one that looks like a grouping
    // bug rather than a precision one. `3088,4 $` two rows under `3.013,85 $`
    // is the same `compact` prop, not a locale's grouping rule.
    speakNumbers('de-DE');
    const grouped = render(<MoneyDisplay amount={3088.4} currency="USD" />).container.textContent!;
    cleanup();
    const compacted = render(
      <MoneyDisplay amount={3088.4} currency="USD" compact />,
    ).container.textContent!;
    cleanup();

    const group = new Intl.NumberFormat('de-DE').formatToParts(1234).find((p) => p.type === 'group')!.value;
    expect(grouped).toContain(group);
    expect(compacted).not.toContain(group);
  });
});

/* ── The census ───────────────────────────────────────────────────────────── */

function tsxFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) tsxFiles(full, found);
    else if (entry.endsWith('.tsx') && !entry.endsWith('.test.tsx')) found.push(full);
  }
  return found;
}

/** Every `<tfoot>…</tfoot>` region in a file, with the line it starts on. */
function footers(source: string): { text: string; line: number }[] {
  return [...source.matchAll(/<tfoot[\s\S]*?<\/tfoot>/g)].map((m) => ({
    text: m[0],
    line: source.slice(0, m.index).split('\n').length,
  }));
}

describe('no table footer in the product', () => {
  it('asks for a compacted figure under a column that is not compacted', () => {
    const offenders: string[] = [];
    for (const file of tsxFiles(FEATURES)) {
      const source = readFileSync(file, 'utf8');
      for (const foot of footers(source)) {
        if (/\bcompact\b/.test(foot.text)) {
          offenders.push(`${relative(FEATURES, file).replace(/\\/g, '/')}:${foot.line}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  // The census walks a real tree and its reader really finds footers. Without
  // this, a wrong path or a regex that never matches is indistinguishable from
  // a clean codebase.
  it('really read the feature tree, and really recognises a footer', () => {
    expect(tsxFiles(FEATURES).length).toBeGreaterThan(200);
    const withFooter = tsxFiles(FEATURES).filter((f) => footers(readFileSync(f, 'utf8')).length > 0);
    expect(withFooter.length).toBeGreaterThan(5);
    expect(footers('<table><tfoot><td compact /></tfoot></table>')).toHaveLength(1);
  });
});
