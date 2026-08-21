// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Reported from a self-hosted install in Chile: a unit price analysis totalled
// "82000.00 CLP". The Chilean peso has no minor unit, so those two digits are
// not a rounding choice, they are a quantity the currency cannot express, and
// this is the figure that goes into a public tender.
//
// Both currency tables in the tree already knew it - `money.py` carries CLP at
// zero decimals, `currencyMinorUnits.ts` lists it under ZERO_DECIMAL, and
// `formatCurrency` asks the CLDR data directly. The assembly screens reached
// past all three and wrote a literal 2, so the one number a Chilean estimator
// actually reads was the one place none of that applied.
//
// The tests are split deliberately. The first pins the helper, which is cheap
// and covers every currency at once. The second renders the screen, because a
// correct helper nobody calls fixes nothing - that was the shape of the bug.

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { currencyFractionDigits } from '@/shared/lib/money';
// The expected totals are built with the same formatter the footer uses, so
// they state the thing under test - how many decimal places a currency gets -
// without also pinning how the reader's language groups the thousands. Written
// out as `'82000 CLP'` these assertions failed the day those figures started
// being grouped, which is a different question and one this file never asked.
import { fmtFixed } from '@/shared/lib/formatters';
import { PreviewTotalsFooter } from '../AssemblyLibraryPage';
import type { AppliedTemplateCurrencySubtotal } from '../api';

describe('currencyFractionDigits', () => {
  it('gives a zero-decimal currency no decimals', () => {
    // CLP is the reported one. The others are here so a regression that
    // special-cases Chile instead of reading the table still fails.
    expect(currencyFractionDigits('CLP')).toBe(0);
    expect(currencyFractionDigits('JPY')).toBe(0);
    expect(currencyFractionDigits('KRW')).toBe(0);
    expect(currencyFractionDigits('XOF')).toBe(0);
  });

  it('leaves the ordinary two-decimal currencies alone', () => {
    expect(currencyFractionDigits('EUR')).toBe(2);
    expect(currencyFractionDigits('USD')).toBe(2);
    expect(currencyFractionDigits('BRL')).toBe(2);
  });

  it('reads three-decimal currencies rather than assuming two is the maximum', () => {
    expect(currencyFractionDigits('KWD')).toBe(3);
    expect(currencyFractionDigits('BHD')).toBe(3);
  });

  it('answers two when there is nothing to read', () => {
    // A blank currency is the honest "not set" the library page already
    // renders; it must not throw and must not invent a currency's precision.
    expect(currencyFractionDigits('')).toBe(2);
    expect(currencyFractionDigits(undefined)).toBe(2);
    expect(currencyFractionDigits(null)).toBe(2);
    expect(currencyFractionDigits('not-a-code')).toBe(2);
  });

  it('does not care about case or surrounding space', () => {
    expect(currencyFractionDigits(' clp ')).toBe(0);
  });
});

describe('the assembly preview total in a zero-decimal currency', () => {
  function cells(grandTotal: number | null, buckets: AppliedTemplateCurrencySubtotal[], label: string) {
    const view = render(
      <table>
        <PreviewTotalsFooter grandTotal={grandTotal} currencyLabel={label} buckets={buckets} />
      </table>
    );
    return Array.from(view.container.querySelectorAll('td')).map((c) => (c.textContent ?? '').trim());
  }

  it('prints whole pesos, not pesos and cents', () => {
    const cellText = cells(82000, [{ currency: 'CLP', amount: 82000, component_count: 3, is_target: true }], 'CLP');

    expect(cellText).toContain(`${fmtFixed(82000, 0)} CLP`);
    // The shape the report came in about: the same figure carrying cents.
    expect(cellText.join('|')).not.toContain(fmtFixed(82000, 2));
  });

  it('gives each bucket the precision of its own currency in a mixed preview', () => {
    const cellText = cells(
      null,
      [
        { currency: 'CLP', amount: 82000, component_count: 2, is_target: true },
        { currency: 'USD', amount: 91.5, component_count: 1, is_target: false },
      ],
      'CLP'
    );

    // One row rounds to whole units and the next keeps its cents, from the
    // same render. A single page-wide digit setting cannot produce this.
    expect(cellText).toContain(`${fmtFixed(82000, 0)} CLP`);
    expect(cellText).toContain(`${fmtFixed(91.5, 2)} USD`);
  });
});
