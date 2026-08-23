// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A design-option comparison is written the way its currency is written.
//
// Every money figure on this table - the by-trade cells, the direct cost, the
// markups, the grand total and the cost per area - went through one private
// formatter pinned to zero decimals. Because every one of them used it, the
// column agreed with itself perfectly and agreed with nothing else: a euro set
// showed its costs without cents from top to bottom, and a set priced in
// dinars lost a thousandth that currency actually has.
//
// That is why "the rows and the total match" is not the property worth
// asserting here. They always matched. What was wrong is the thing they
// matched on - a literal digit count standing in for a question only the
// currency can answer. CLDR keeps the answer in `currencyData`, the shared
// formatter reads it from there, and commit 8bbd6daf3 took the same override
// out of six other money surfaces for the same reason.
//
// Both polarities are exercised against the rendered DOM of the real
// component, because a formatter can be made to look right in isolation and
// still be reached by nothing. The yen carries the zero-decimal case: it has
// no minor unit at all, nobody disputes that, and under the old formatter it
// was the one currency the table was accidentally right about. The euro
// carries the negative control, and it is the polarity that actually failed
// before the fix - two decimals have to survive, or "ask the currency" would
// have been satisfied by rounding everything to whole units and calling it
// consistent.
//
// The forint is deliberately absent. How many decimals it should print is an
// open question reserved for a founder ruling, and a test is a bad place to
// settle one.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import { usePreferencesStore, type NumberLocale } from '@/stores/usePreferencesStore';
import type { DesignOptionComparisonResponse } from '../api';

/* -- i18n shim - the component uses the options-object form throughout, and
      the positional form is answered too so the shim cannot be the reason a
      label goes missing. ------------------------------------------------- */

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

/* -- The benchmark strip fetches its own comparables and is not what this
      file is about. ---------------------------------------------------- */

vi.mock('@/features/boq/CostPerAreaBenchmark', () => ({
  CostPerAreaBenchmark: () => null,
  default: () => null,
}));

import { DesignOptionComparisonTable } from '../DesignOptionComparisonTable';

/**
 * Two options in one currency, with amounts that carry a non-zero minor part.
 *
 * The cents matter: an amount ending in `.00` renders identically whether the
 * currency was asked or ignored, so a fixture built on round numbers would
 * pass against the very formatter this file exists to reject.
 */
function comparisonIn(currency: string): DesignOptionComparisonResponse {
  const option = (id: string, name: string, direct: string, markup: string, total: string) => ({
    option_id: id,
    name,
    direct_cost: direct,
    markups_total: markup,
    grand_total: total,
    delta_vs_baseline: '0',
    delta_pct: null,
    cost_per_m2: '1234.56',
    gfa: '1000',
    currency,
    element_count: 12,
    position_count: 34,
    validation_status: 'passed' as const,
    boq_source: 'generated' as const,
    has_programme: false,
    duration_days: '0',
    finish_date: '',
    delta_days_vs_baseline: null,
    has_carbon: false,
    embodied_carbon_kg: '0',
    carbon_per_m2: '0',
    carbon_unit: 'kgCO2e',
    delta_carbon_vs_baseline: null,
  });

  return {
    set_id: 'set-1',
    set_name: 'Facade study',
    comparison_currency: currency,
    baseline_option_id: 'opt-a',
    options: [
      option('opt-a', 'Option A', '1000.25', '234.50', '1234.75'),
      option('opt-b', 'Option B', '2000.25', '234.50', '2234.75'),
    ],
    by_trade: [
      {
        key: 'facade',
        label: 'Facade',
        classification_system: 'din276',
        baseline_quantity: '100',
        baseline_cost: '1234.75',
        per_option: [
          { option_id: 'opt-a', quantity: '100', unit: 'm2', cost: '1234.75' },
          { option_id: 'opt-b', quantity: '100', unit: 'm2', cost: '2234.75' },
        ],
      },
    ],
    recommendation: { option_id: 'opt-a', confidence: '0.5', reason_key: 'cheapest' },
    fairness: { status: 'ok', warnings: [] },
  };
}

/**
 * How many digits follow this locale's decimal separator.
 *
 * The separator is read out of `Intl` rather than assumed to be a comma or a
 * point, so the reading does not quietly depend on which locale the test runs
 * under.
 */
function fractionLength(text: string, locale: string): number {
  const decimal =
    new Intl.NumberFormat(locale).formatToParts(1.5).find((p) => p.type === 'decimal')?.value ?? '.';
  const at = text.lastIndexOf(decimal);
  return at < 0 ? 0 : (text.slice(at + 1).match(/^\d+/)?.[0].length ?? 0);
}

const READER: NumberLocale = 'de-DE';

/**
 * Three readings of the same option: the grand total and the cost per area
 * from the foot, and one by-trade cell from the body.
 *
 * Cost per area is read as well as the total because it is the row most likely
 * to be left behind by a fix aimed at "the total": it sits below the total, it
 * is a derived figure rather than a sum, and it is money all the same.
 */
function renderComparison(currency: string) {
  const { container } = render(
    <DesignOptionComparisonTable comparison={comparisonIn(currency)} />,
  );
  const foot = container.querySelector('tfoot');
  const body = container.querySelector('tbody');
  if (!foot || !body) throw new Error('the comparison rendered without a table');
  // Second column of each: the first is the sticky label, so column two is the
  // baseline option and the same option in every place read here.
  const rows = foot.querySelectorAll('tr');
  const total = rows[2]?.querySelectorAll('td')[1]?.textContent ?? '';
  const perArea = rows[3]?.querySelectorAll('td')[1]?.textContent ?? '';
  const cell = body.querySelector('tr')?.querySelectorAll('td')[1]?.textContent ?? '';
  return { total, perArea, cell };
}

beforeEach(() => {
  localStorage.clear();
  usePreferencesStore.getState().resetPreferences();
  usePreferencesStore.setState({ numberLocale: READER });
});

afterEach(() => {
  cleanup();
});

describe('the fixture is capable of showing the defect', () => {
  it('runs on an engine that knows the yen has no minor unit', () => {
    // A host built with a trimmed ICU would answer 2 for every currency, and
    // every assertion below would then be measuring the host rather than the
    // component.
    const digits = (code: string) =>
      new Intl.NumberFormat('en-US', { style: 'currency', currency: code }).resolvedOptions()
        .maximumFractionDigits;
    expect(digits('JPY')).toBe(0);
    expect(digits('EUR')).toBe(2);
  });

  it('carries amounts whose minor part is not zero', () => {
    const c = comparisonIn('EUR');
    expect(c.options[0]!.grand_total).toMatch(/\.\d*[1-9]/);
    expect(c.by_trade[0]!.per_option[0]!.cost).toMatch(/\.\d*[1-9]/);
  });

  it('reads a fraction length out of the locale rather than assuming a comma', () => {
    expect(fractionLength('1.234,56', 'de-DE')).toBe(2);
    expect(fractionLength('1.235', 'de-DE')).toBe(0);
    expect(fractionLength('1,234.56', 'en-US')).toBe(2);
  });
});

describe('a design-option comparison', () => {
  it('writes a zero-decimal currency with no minor part at all', () => {
    const { total, perArea, cell } = renderComparison('JPY');
    expect(fractionLength(total, READER), `total "${total}"`).toBe(0);
    expect(fractionLength(perArea, READER), `cost per area "${perArea}"`).toBe(0);
    expect(fractionLength(cell, READER), `cell "${cell}"`).toBe(0);
  });

  it('keeps both decimals of a two-decimal currency', () => {
    // The negative control, and the polarity that was actually broken. Before
    // the fix this read `1.235 €` under `1.235 €`: consistent, and wrong.
    const { total, perArea, cell } = renderComparison('EUR');
    expect(fractionLength(total, READER), `total "${total}"`).toBe(2);
    expect(fractionLength(perArea, READER), `cost per area "${perArea}"`).toBe(2);
    expect(fractionLength(cell, READER), `cell "${cell}"`).toBe(2);
  });

  it('writes its total the way it writes the cells it sums', () => {
    for (const code of ['EUR', 'JPY']) {
      const { total, cell } = renderComparison(code);
      expect(
        fractionLength(total, READER),
        `${code}: total "${total}" against cell "${cell}"`,
      ).toBe(fractionLength(cell, READER));
      cleanup();
    }
  });

  it('could not have been right about both currencies while it pinned a count', () => {
    // Guards the guard. If a single hardcoded digit count could satisfy the two
    // assertions above, they would prove nothing about asking the currency -
    // any surface that pins the same number everywhere would pass. It cannot:
    // the two currencies demand different counts from the same code path.
    const euro = renderComparison('EUR');
    cleanup();
    const yen = renderComparison('JPY');
    expect(fractionLength(euro.total, READER)).not.toBe(fractionLength(yen.total, READER));
  });
});
