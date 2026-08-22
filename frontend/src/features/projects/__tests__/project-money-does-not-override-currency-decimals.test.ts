// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The project dashboard formats a budget whose currency comes from the project
// record, so the code is a variable, and the formatter used to pass a literal
// 2 for both ends of the fraction digits regardless. Every tile on the page
// therefore showed cents to a project budgeted in a currency that has none:
// the reported symptom is the forint reading "1 235,00 Ft" on a whole amount.
//
// Asserted on the yen rather than the forint deliberately. Whether the forint
// should carry decimals is a reserved question, and this test has no business
// answering it; the yen and the won are undisputed, and what is under test is
// the call site's habit of overriding the answer rather than the answer.
//
// The em-dash branch is pinned in the same file because it is the other half
// of the same function's policy and delegating the formatting must not have
// disturbed it. A project with no currency configured has to keep showing a
// visible gap rather than acquiring a Euro sign it never earned.

import { describe, it, expect } from 'vitest';
import { getNumberLocale } from '@/stores/usePreferencesStore';
import { formatCurrency } from '../ProjectDetailPage';

const loc = getNumberLocale();

/** The currency's own minor units, with no policy imposed by us. */
function engine(value: number, currency: string): string {
  return new Intl.NumberFormat(loc, { style: 'currency', currency }).format(value);
}

/** The string the defect produced: two decimals whatever the currency says. */
function withForcedCents(value: number, currency: string): string {
  return new Intl.NumberFormat(loc, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function engineFractionLength(value: number, currency: string): number {
  return new Intl.NumberFormat(loc, { style: 'currency', currency })
    .formatToParts(value)
    .filter((p) => p.type === 'fraction')
    .reduce((n, p) => n + p.value.length, 0);
}

describe('the project budget figure', () => {
  it('rests on an engine that tells the two kinds of currency apart', () => {
    // Without this the comparisons below could pass on a trimmed-ICU host by
    // agreeing with an engine that answers every currency with two decimals.
    expect(engineFractionLength(1234, 'JPY')).toBe(0);
    expect(engineFractionLength(1234, 'EUR')).toBe(2);
  });

  it('gives a zero-decimal currency no decimals', () => {
    expect(formatCurrency(1234, 'JPY')).toBe(engine(1234, 'JPY'));
    expect(formatCurrency(1234, 'JPY')).not.toBe(withForcedCents(1234, 'JPY'));
    expect(formatCurrency(1234, 'KRW')).toBe(engine(1234, 'KRW'));
  });

  it('still gives a two-decimal currency both of its decimals', () => {
    expect(formatCurrency(1234, 'EUR')).toBe(engine(1234, 'EUR'));
    expect(formatCurrency(1234, 'EUR')).toBe(withForcedCents(1234, 'EUR'));
    expect(formatCurrency(1234.5, 'USD')).toBe(engine(1234.5, 'USD'));
  });

  it('keeps showing the configuration gap when the project has no currency', () => {
    // Spelled as an escape rather than the character, the way the page itself
    // writes this mark, so the expected value cannot be mistaken for prose or
    // lost to a paste that normalises punctuation.
    const gap = '\u2014';
    expect(formatCurrency(1234)).toBe(gap);
    expect(formatCurrency(1234, '')).toBe(gap);
    expect(formatCurrency(1234, 'eur')).toBe(gap);
    expect(formatCurrency(1234, 'not-a-code')).toBe(gap);
  });
});
