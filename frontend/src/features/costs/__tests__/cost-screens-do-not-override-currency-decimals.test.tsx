// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Every money formatter on the cost screens used to pass a literal 2 for both
// the floor and the ceiling of the fraction digits while the currency itself
// arrived as a variable. That is an override of the currency's own minor
// units, so a currency that has none was shown cents it cannot express: the
// reported symptom is the Hungarian forint printing "1 235,00 Ft" on a whole
// amount, and the same fault on the assembly screens is what put "82000.00
// CLP" into a Chilean tender.
//
// The assertions here are written against the yen rather than the forint on
// purpose. How many decimals the forint gets is a question that is still open
// and reserved, and a test is a bad place to settle it; the yen, the won and
// the Chilean peso are not disputed by anyone. Pinning an undisputed currency
// tests the thing that was actually wrong, which is a call site overriding the
// answer rather than the answer itself.
//
// Nor do these tests look for a decimal separator by character. The separator
// in one language is the grouping mark in another, so "contains no comma" can
// pass while saying nothing. Each call site is compared against what the
// engine prints for the same amount and currency with no digit policy imposed
// at all, which is exactly the answer the call sites used to contradict, and
// against the string the bug produced.

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { getNumberLocale } from '@/stores/usePreferencesStore';
import { formatPrice as formatVariantPrice } from '../VariantPicker';
import { formatPrice as formatSlotPrice, MultiVariantPicker, type VariantSlot } from '../MultiVariantPicker';
import { formatCostMoney } from '../CostsPage';
import type { CostVariant, VariantStats } from '../api';

/** The reader's locale, the same one every formatter under test resolves. */
const loc = getNumberLocale();

/** What the engine prints when nobody imposes a digit policy on it. This is
 *  the currency's own minor units, and it is the answer the literal 2 used to
 *  overrule. */
function engine(value: number, currency: string, max?: number): string {
  return new Intl.NumberFormat(loc, {
    style: 'currency',
    currency,
    ...(max === undefined ? {} : { maximumFractionDigits: max }),
  }).format(value);
}

/** The string the defect produced: two decimals, whatever the currency says. */
function withForcedCents(value: number, currency: string): string {
  return new Intl.NumberFormat(loc, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/** Fraction digits the engine actually gives a currency on this host. */
function engineFractionLength(value: number, currency: string): number {
  return new Intl.NumberFormat(loc, { style: 'currency', currency })
    .formatToParts(value)
    .filter((p) => p.type === 'fraction')
    .reduce((n, p) => n + p.value.length, 0);
}

describe('the fixtures these tests rest on', () => {
  // A host built with a trimmed ICU can answer every currency with two
  // decimals, and on such a host the comparisons below would pass by agreeing
  // with a wrong engine rather than by being right. This says so out loud
  // instead of letting the suite go green on a machine that cannot tell the
  // difference.
  it('has an engine that distinguishes a zero-decimal currency from a two-decimal one', () => {
    expect(engineFractionLength(1234, 'JPY')).toBe(0);
    expect(engineFractionLength(1234, 'KRW')).toBe(0);
    expect(engineFractionLength(1234, 'EUR')).toBe(2);
    expect(engineFractionLength(1234, 'USD')).toBe(2);
  });

  it('has a defect string that differs from the correct one', () => {
    expect(withForcedCents(1234, 'JPY')).not.toBe(engine(1234, 'JPY'));
  });
});

describe('the single-slot variant picker', () => {
  it('gives a zero-decimal currency no decimals', () => {
    expect(formatVariantPrice(1234, 'JPY')).toBe(engine(1234, 'JPY'));
    expect(formatVariantPrice(1234, 'JPY')).not.toBe(withForcedCents(1234, 'JPY'));
    expect(formatVariantPrice(1234, 'KRW')).toBe(engine(1234, 'KRW'));
  });

  it('still gives a two-decimal currency both of its decimals', () => {
    expect(formatVariantPrice(1234, 'EUR')).toBe(engine(1234, 'EUR'));
    expect(formatVariantPrice(1234, 'EUR')).toBe(withForcedCents(1234, 'EUR'));
    expect(formatVariantPrice(1234.5, 'USD')).toBe(engine(1234.5, 'USD'));
  });

  it('renders a bare number when the row carries no currency at all', () => {
    // The picker has always refused to substitute a currency it was not
    // given, and delegating must not have quietly introduced one.
    const bare = formatVariantPrice(1234.5, '');
    expect(bare).toBe((1234.5).toLocaleString(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  });
});

describe('the multi-slot variant picker', () => {
  it('gives a zero-decimal currency no decimals', () => {
    expect(formatSlotPrice(1234, 'JPY')).toBe(engine(1234, 'JPY'));
    expect(formatSlotPrice(1234, 'JPY')).not.toBe(withForcedCents(1234, 'JPY'));
  });

  it('still gives a two-decimal currency both of its decimals', () => {
    expect(formatSlotPrice(1234, 'EUR')).toBe(engine(1234, 'EUR'));
    expect(formatSlotPrice(1234, 'EUR')).toBe(withForcedCents(1234, 'EUR'));
  });
});

describe('the cost catalogue money formatter', () => {
  it('gives a zero-decimal currency no decimals', () => {
    expect(formatCostMoney(1234, 'JPY')).toBe(engine(1234, 'JPY'));
    expect(formatCostMoney(1234, 'JPY')).not.toBe(withForcedCents(1234, 'JPY'));
  });

  it('still gives a two-decimal currency both of its decimals', () => {
    expect(formatCostMoney(1234, 'EUR')).toBe(engine(1234, 'EUR'));
    expect(formatCostMoney(1234, 'EUR')).toBe(withForcedCents(1234, 'EUR'));
  });

  it('reads a lowercase or padded code the same way', () => {
    expect(formatCostMoney(1234, ' jpy ')).toBe(engine(1234, 'JPY'));
  });

  // The mass-pricing preview asks for a ceiling of four, because a rate
  // derived per kilogram is a working figure rather than a posted amount.
  // That is a statement about the ceiling only. The floor stays the
  // currency's own, which is the half that used to be overridden.
  it('keeps the extra precision of a unit-rate preview without inventing a floor', () => {
    expect(formatCostMoney(1234, 'JPY', { maximumFractionDigits: 4 })).toBe(engine(1234, 'JPY'));
    expect(formatCostMoney(1234.5678, 'JPY', { maximumFractionDigits: 4 })).toBe(
      engine(1234.5678, 'JPY', 4),
    );
    expect(formatCostMoney(1234, 'EUR', { maximumFractionDigits: 4 })).toBe(engine(1234, 'EUR'));
  });
});

// A correct helper nobody calls fixes nothing, and that was the shape of this
// bug: the tree already carried a formatter that reads the currency table, and
// the screens reached past it. So one of the pickers is mounted for real and
// the figure is read back off the DOM.
describe('the multi-slot picker as it is actually rendered', () => {
  function slot(currency: string): VariantSlot {
    const variants: CostVariant[] = [
      { index: 0, label: 'Grade A', price: 1000, price_per_unit: null },
      { index: 1, label: 'Grade B', price: 1234, price_per_unit: null },
      { index: 2, label: 'Grade C', price: 1500, price_per_unit: null },
    ];
    const stats: VariantStats = {
      min: 1000,
      max: 1500,
      mean: 1244.6667,
      median: 1234,
      unit: 'm3',
      group: '',
      count: 3,
    };
    return { slotId: 'slot-1', name: 'Concrete', unit: 'm3', quantity: 1, variants, stats, currency };
  }

  function textOf(currency: string): string {
    const view = render(
      <MultiVariantPicker
        positionTitle="Reinforced slab"
        slots={[slot(currency)]}
        onApply={() => {}}
        onCancel={() => {}}
      />,
    );
    // The modal portals itself into document.body so AG Grid cannot clip it,
    // which leaves `container` empty. `baseElement` is the body, where the
    // rendered figures actually are.
    const text = view.baseElement.textContent ?? '';
    view.unmount();
    return text;
  }

  it('prints a yen rate with no cents anywhere on the modal', () => {
    const text = textOf('JPY');
    expect(text).toContain(engine(1234, 'JPY'));
    // The load-bearing half. The correct string is a prefix of the broken one,
    // so only the absence of the broken one proves the decimals are gone.
    expect(text).not.toContain(withForcedCents(1234, 'JPY'));
  });

  it('still prints a euro rate with both decimals', () => {
    const text = textOf('EUR');
    expect(text).toContain(engine(1234, 'EUR'));
    expect(text).toContain(withForcedCents(1234, 'EUR'));
  });
});
