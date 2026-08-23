// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A leveled total is written the way the column it sums is written.
//
// The bid-leveling matrix prints each line's leveled money in the body and the
// sum of exactly those lines in its `<tfoot>`. The two disagreed about how
// many decimals money has: the cells went through a formatter fixed at two
// while the footer built its own pinned to zero at both ends, so a euro
// package showed `1.235 €` directly beneath rows reading `1.234,56`. The total
// was rounded away from the very figures it sums, in the same column, and no
// unusual currency was needed to see it - EUR and USD did it too.
//
// The pair of literal zeroes was also a claim about every currency that can
// reach this screen, which is the same override commit 8bbd6daf3 took out of
// six other money surfaces. The fix is theirs: the surface asks the currency
// instead of pinning a digit count of its own, and how many minor units a
// currency has stays decided in one place.
//
// What is asserted here is agreement between the rendered strings rather than
// a digit count, because that is the defect. A total and a row are different
// amounts and will never be equal; what has to be equal is how they are
// written. The one absolute count carried below is on the yen, which nobody
// disputes. The forint's digit count is an open question reserved for a
// founder ruling, and a test is a bad place to settle it - so the forint is
// exercised for agreement only, which stays true whichever way that goes.
//
// Nor is the currency symbol compared. This column prints its code once, in
// the footer, and leaves the cells bare on purpose; that is a layout decision
// and it was never the complaint.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { usePreferencesStore, type NumberLocale } from '@/stores/usePreferencesStore';
import type { LevelingMatrix as LevelingMatrixData } from '../api';

/* -- Toast mock ------------------------------------------------------- */

const toastMocks = vi.hoisted(() => ({ addToast: vi.fn() }));
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToast }) => unknown) =>
      selector({ addToast: toastMocks.addToast }),
    { getState: () => ({ addToast: toastMocks.addToast }) },
  ),
}));

/* -- i18n shim - the component uses both the positional default and the
      options-object form, so the shim has to answer both. --------------- */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, second?: unknown) => {
      if (typeof second === 'string') return second;
      if (second && typeof second === 'object' && 'defaultValue' in second) {
        const opts = second as { defaultValue?: string } & Record<string, unknown>;
        let dv = String(opts.defaultValue ?? '');
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return key;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  I18nextProvider: ({ children }: { children: unknown }) => children,
  Trans: ({ children }: { children?: unknown }) => children ?? null,
}));

/* -- API mock --------------------------------------------------------- */

const apiMocks = vi.hoisted(() => ({
  getLevelingMatrix: vi.fn(),
  levelBids: vi.fn(),
}));
vi.mock('../api', () => apiMocks);

// Imported after the mocks so the component picks them up.
const { LevelingMatrix } = await import('../LevelingMatrix');

/* -- The column under test -------------------------------------------- */

// Two lines whose leveled money sums without a half-unit anywhere, so nothing
// here can turn on a rounding tie. The footer sums the unrounded values, which
// is a separate question from how either end is written and is not what this
// file is about.
const LINE_A = 1234.5;
const LINE_B = 1000.25;

function matrixIn(currency: string): LevelingMatrixData {
  const bidTotalA = 1300.75;
  const bidTotalB = 1100.5;
  return {
    package_id: 'pkg-1',
    package_name: 'Concrete works',
    currency,
    excluded_off_currency: 0,
    bid_summaries: [
      {
        bid_id: 'bid-1',
        company_name: 'Alpha Bau',
        raw_amount: bidTotalA + bidTotalB,
        leveled_amount: bidTotalA + bidTotalB,
        matched_lines: 2,
        scaled_lines: 0,
        imputed_lines: 0,
        currency,
      },
    ],
    rows: [
      {
        position_id: 'pos-1',
        line_code: '01.10',
        description: 'Reinforced slab',
        unit: 'm3',
        reference_quantity: 120,
        reference_rate: 10.2875,
        reference_total: LINE_A,
        cells: [
          {
            bid_id: 'bid-1',
            company_name: 'Alpha Bau',
            raw_total: bidTotalA,
            leveled_total: bidTotalA,
            status: 'matched',
            unit_rate: 10.84,
          },
        ],
      },
      {
        position_id: 'pos-2',
        line_code: '01.20',
        description: 'Blinding layer',
        unit: 'm2',
        reference_quantity: 80,
        reference_rate: 12.503125,
        reference_total: LINE_B,
        cells: [
          {
            bid_id: 'bid-1',
            company_name: 'Alpha Bau',
            raw_total: bidTotalB,
            leveled_total: bidTotalB,
            status: 'matched',
            unit_rate: 13.75,
          },
        ],
      },
    ],
  };
}

/**
 * How many digits follow this locale's decimal separator.
 *
 * Read through the separator the locale actually uses rather than by looking
 * for a comma: the mark that separates the decimals in one language groups the
 * thousands in another, so "contains no comma" can pass while saying nothing.
 */
function fractionLength(text: string, locale: string): number {
  const decimal =
    new Intl.NumberFormat(locale).formatToParts(1.5).find((p) => p.type === 'decimal')?.value ?? '.';
  const at = text.lastIndexOf(decimal);
  return at < 0 ? 0 : (text.slice(at + 1).match(/^\d+/)?.[0].length ?? 0);
}

/** The string the defect produced: a total pinned to whole units whatever the
 *  currency and whatever the cells above it say. */
function pinnedToWholeUnits(value: number, currency: string, locale: string): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

/** Fraction digits the engine on this host really gives a currency. */
function engineFractionLength(value: number, currency: string, locale: string): number {
  return new Intl.NumberFormat(locale, { style: 'currency', currency })
    .formatToParts(value)
    .filter((p) => p.type === 'fraction')
    .reduce((n, p) => n + p.value.length, 0);
}

/**
 * Mount the matrix and read the reference-money column off the DOM.
 *
 * A correct helper nobody calls fixes nothing, which is the shape this bug
 * had: the tree already carried a formatter that reads the currency table and
 * the footer reached past it. So the component is rendered for real and the
 * two figures are read out of the cells a person would compare - the second
 * column of the first body row, and the second column of the footer, which is
 * the sum of exactly that column.
 */
async function renderColumn(currency: string) {
  apiMocks.getLevelingMatrix.mockResolvedValue(matrixIn(currency));
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <LevelingMatrix packageId="pkg-1" currency={currency} />
    </QueryClientProvider>,
  );
  await waitFor(() => {
    expect(view.container.querySelector('tfoot')).not.toBeNull();
  });
  const cell = view.container.querySelector('tbody tr td:nth-child(2)')!.textContent!.trim();
  const total = view.container.querySelector('tfoot td:nth-child(2)')!.textContent!.trim();
  const bidCell = view.container.querySelector('tbody tr td:nth-child(3)')!.textContent!.trim();
  const bidTotal = view.container.querySelector('tfoot td:nth-child(3)')!.textContent!.trim();
  return { cell, total, bidCell, bidTotal };
}

function speakNumbers(locale: NumberLocale) {
  usePreferencesStore.setState({ numberLocale: locale });
}

/** The resolved tag the component's own formatters will use. */
const LOCALE = 'de-DE';

beforeEach(() => {
  localStorage.clear();
  usePreferencesStore.getState().resetPreferences();
  speakNumbers(LOCALE);
  apiMocks.getLevelingMatrix.mockReset();
  apiMocks.levelBids.mockReset();
});

afterEach(() => {
  cleanup();
});

describe('the fixtures these tests rest on', () => {
  // A host built with a trimmed ICU answers every currency with two decimals,
  // and on such a host the comparisons below would pass by agreeing with an
  // engine that cannot tell the currencies apart. Say so out loud rather than
  // going green on a machine that cannot see the difference.
  it('has an engine that tells a zero-decimal currency from a two-decimal one', () => {
    expect(engineFractionLength(1234, 'JPY', LOCALE)).toBe(0);
    expect(engineFractionLength(1234, 'EUR', LOCALE)).toBe(2);
    expect(engineFractionLength(1234, 'USD', LOCALE)).toBe(2);
  });

  it('reads a fraction through the separator this locale actually uses', () => {
    expect(fractionLength((1234.56).toLocaleString(LOCALE), LOCALE)).toBe(2);
    // The group separator of de-DE is the decimal separator of en-US. A reader
    // that looked for a character rather than for the locale's own mark would
    // call this two.
    expect(fractionLength((1234).toLocaleString(LOCALE), LOCALE)).toBe(0);
  });
});

describe('the leveled money column', () => {
  it('writes its total the way it writes its cells, in a zero-decimal currency', async () => {
    const { cell, total, bidCell, bidTotal } = await renderColumn('JPY');
    // The yen has no minor unit, and nobody disputes that, so this one carries
    // the absolute count as well as the agreement.
    expect(fractionLength(cell, LOCALE), `cell "${cell}"`).toBe(0);
    expect(fractionLength(total, LOCALE), `total "${total}" against cell "${cell}"`).toBe(
      fractionLength(cell, LOCALE),
    );
    expect(fractionLength(bidTotal, LOCALE), `bid total "${bidTotal}" against "${bidCell}"`).toBe(
      fractionLength(bidCell, LOCALE),
    );
  });

  // The negative control. A fix that reached the agreement by rounding every
  // column to whole units would satisfy the test above and be a worse bug, so
  // the two-decimal currency has to still carry both of its decimals.
  it('still gives a two-decimal currency both decimals, in cells and in total', async () => {
    const { cell, total, bidCell, bidTotal } = await renderColumn('EUR');
    expect(fractionLength(cell, LOCALE), `cell "${cell}"`).toBe(2);
    expect(fractionLength(total, LOCALE), `total "${total}" against cell "${cell}"`).toBe(2);
    expect(fractionLength(bidCell, LOCALE), `bid cell "${bidCell}"`).toBe(2);
    expect(fractionLength(bidTotal, LOCALE), `bid total "${bidTotal}"`).toBe(2);
  });

  it('agrees with itself in a currency whose digit count is still an open question', async () => {
    // The forint is here for agreement only. How many decimals it gets is
    // reserved for a founder ruling; that a column may not contradict itself
    // is not, and stays true whichever way the ruling goes.
    const { cell, total, bidCell, bidTotal } = await renderColumn('HUF');
    expect(fractionLength(total, LOCALE), `total "${total}" against cell "${cell}"`).toBe(
      fractionLength(cell, LOCALE),
    );
    expect(fractionLength(bidTotal, LOCALE), `bid total "${bidTotal}" against "${bidCell}"`).toBe(
      fractionLength(bidCell, LOCALE),
    );
  });

  // Guards the guard, and states the defect. If a total pinned to whole units
  // were a neutral choice the assertions above would pass either way and this
  // file would be proving nothing. It is not neutral: against a currency that
  // has minor units it writes a different number of decimals than the cells it
  // sums, which is the reported symptom.
  it('could not have been written like them while the total was pinned to whole units', async () => {
    const { cell } = await renderColumn('EUR');
    const pinned = pinnedToWholeUnits(LINE_A + LINE_B, 'EUR', LOCALE);
    expect(fractionLength(pinned, LOCALE), `old total "${pinned}"`).not.toBe(
      fractionLength(cell, LOCALE),
    );
    // And that the old shape is harmless on a currency with no minor unit is
    // exactly why the defect went unreported for the currencies it did not
    // touch - it is a statement about EUR/USD, not about JPY.
    const pinnedYen = pinnedToWholeUnits(LINE_A + LINE_B, 'JPY', LOCALE);
    expect(fractionLength(pinnedYen, LOCALE)).toBe(0);
  });
});
