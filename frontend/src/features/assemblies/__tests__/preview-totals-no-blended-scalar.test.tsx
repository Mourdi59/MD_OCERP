// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Work item #160 — the apply-template preview used to add an unconvertible
// component's face value into a target-currency total, so 100 EUR plus 1000 of
// a currency nothing could price was reported as "1100.00 EUR". The server no
// longer produces that number: `grand_total` is null whenever the preview spans
// more than one currency, and the per-currency breakdown carries the figures.
//
// A null total is only an improvement if the screen branches on it. The old
// footer read `Number(result.grand_total).toFixed(2)`, and `Number(null)` is 0,
// so the same cell would have printed a confident "0.00" — a fabricated total
// where the honest answer is that there isn't one. That is what these pin.
//
// The harness renders i18n KEYS rather than English, so the assertions below
// name keys. Cell text is compared exactly rather than by substring: "0.00 EUR"
// is a substring of "100.00 EUR", so a loose contains-check passes on a screen
// that is showing the fabricated zero.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
// Built with the formatter the footer uses, so the assertion states that each
// currency keeps its own figure rather than pinning how a language groups the
// thousands of it. Only the four-figure XOF total is affected.
import { fmtFixed } from '@/shared/lib/formatters';
import { PreviewTotalsFooter } from '../AssemblyLibraryPage';
import type { AppliedTemplateCurrencySubtotal } from '../api';

function renderFooter(
  grandTotal: number | null,
  buckets: AppliedTemplateCurrencySubtotal[],
  currencyLabel = 'EUR'
) {
  const view = render(
    <table>
      <PreviewTotalsFooter grandTotal={grandTotal} currencyLabel={currencyLabel} buckets={buckets} />
    </table>
  );
  const cellText = Array.from(view.container.querySelectorAll('td')).map((c) => (c.textContent ?? '').trim());
  return { ...view, cellText };
}

const MIXED: AppliedTemplateCurrencySubtotal[] = [
  { currency: 'EUR', amount: 100, component_count: 1, is_target: true },
  { currency: 'XOF', amount: 1000, component_count: 1, is_target: false },
];

describe('PreviewTotalsFooter', () => {
  it('never prints a fabricated zero when there is no single total', () => {
    const { cellText } = renderFooter(null, MIXED);

    // The exact cell the naive `Number(null).toFixed(2)` coercion produced.
    expect(cellText).not.toContain('0.00 EUR');
    expect(cellText).not.toContain('0.00');
    // And no "Grand total" caption, because there is no grand total.
    expect(cellText).not.toContain('assemblies.library.grand_total');
  });

  it('shows every currency on its own rather than one blended figure', () => {
    const { cellText } = renderFooter(null, MIXED);

    expect(cellText).toContain('100.00 EUR');
    // No decimals, and that is the point: XOF has no minor unit, so the two
    // digits this line used to expect were a quantity the currency cannot
    // express. Each bucket is now printed to its own currency's precision.
    expect(cellText).toContain(`${fmtFixed(1000, 0)} XOF`);
    // The blend this whole change removes: 100 + 1000 stamped as one currency.
    expect(cellText.join('|')).not.toContain(fmtFixed(1100, 2));
  });

  it('says why no total is shown', () => {
    renderFooter(null, MIXED);

    expect(screen.getByText('assemblies.library.no_single_total')).toBeTruthy();
  });

  it('still reports one total when only one currency is in play', () => {
    const { cellText } = renderFooter(500, [
      { currency: 'EUR', amount: 500, component_count: 2, is_target: true },
    ]);

    expect(cellText).toContain('500.00 EUR');
    expect(screen.getByText('assemblies.library.grand_total')).toBeTruthy();
  });

  it('labels a bucket with no currency rather than guessing one', () => {
    const { cellText } = renderFooter(null, [
      { currency: '', amount: 42, component_count: 1, is_target: false },
      { currency: 'USD', amount: 7, component_count: 1, is_target: false },
    ]);

    expect(screen.getByText('assemblies.library.subtotal_currency_not_set')).toBeTruthy();
    expect(cellText).toContain('42.00');
    // No silent EUR: the label passed in is never applied to a bucket that has
    // no currency of its own.
    expect(cellText.join('|')).not.toContain('EUR');
  });

  it('documents the coercion the null branch exists to prevent', () => {
    // Not an assertion about our code — a fact about the expression the footer
    // used before, so a future "simplification" back to it has to delete a test
    // that states plainly why it was wrong.
    expect(Number(null).toFixed(2)).toBe('0.00');
    expect(Number(undefined).toFixed(2)).toBe('NaN');
  });
});
