// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The two property-development money surfaces print the decimals the currency
// has, and they get that answer from the module that owns it.
//
// Both screens used to build their own `Intl.NumberFormat` with
// `maximumFractionDigits: 2` and no floor under it. That is not a rounding
// preference, it is a claim about every currency that can reach the call, and
// it is wrong in two directions at once:
//
//   * A currency with no minor unit inherits a floor of zero and keeps the
//     ceiling of two, so a yen amount of 1234.50 prints "1.234,5 ¥" - a
//     fraction of a unit the yen does not have.
//   * A currency with three inherits a floor of three, which cannot fit under
//     a ceiling of two. Modern engines clamp the pair and drop the third
//     digit; the pre-ES2023 engines `fractionDigits.ts` says we still ship to
//     throw `RangeError` instead, out of a React render, which costs the page
//     rather than the cell. That is the shape of issue #391.
//
// What it is NOT is a euro or dollar defect. Under `style: 'currency'` the
// engine defaults the minimum to the currency's own minor units, so EUR and
// USD render 1234.50 as "1.234,50 €" with the broken formatter and with the
// fixed one alike. A fixture in either currency would pass against the code
// this file exists to catch, so the fixtures below are JPY and KWD - the two
// families where the two formatters actually disagree, and both of them
// currencies whose minor-unit count ISO and CLDR agree on, so nothing here
// depends on how the open question about HUF and IDR is settled.
//
// Each assertion is written as agreement with `formatCurrency` rather than
// against a literal string, so a later ruling on any currency's decimals moves
// `money.ts` and these tests follow it. The literal the broken formatter would
// have produced is stated separately and required to be absent, because a test
// that only says "it equals the resolver" cannot show that the resolver and
// the old formatter differ at all on this fixture.

import type { ReactElement } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { formatCurrency } from '@/shared/lib/money';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

// `src/test/setup.ts` mocks `useParams` globally to `{}`, which would leave the
// pricing page with no development id and nothing to load.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ devId: 'dev-1' }),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    fetchContractTaxQuote: vi.fn(),
    listPriceLists: vi.fn(),
    listPlots: vi.fn(),
    quotePrice: vi.fn(),
  };
});

import { fetchContractTaxQuote, listPriceLists, listPlots, quotePrice } from '../api';
import type { ContractTaxQuote, PriceList, PriceQuote, Plot } from '../api';
import { TaxQuotePanel } from '../TaxQuotePanel';
import { PricingEnginePage } from '../PricingEnginePage';

const taxQuoteMock = vi.mocked(fetchContractTaxQuote);
const priceListsMock = vi.mocked(listPriceLists);
const plotsMock = vi.mocked(listPlots);
const quotePriceMock = vi.mocked(quotePrice);

/**
 * A locale that writes its own separators, pinned so the expected value and the
 * rendered one are read from the same preference rather than from the host.
 * German also puts the symbol after the amount behind a non-breaking space,
 * which English would have hidden.
 */
const LOCALE = 'de-DE';

/** An amount ending in a round ten, which is where a truncating ceiling shows. */
const AMOUNT = '1234.50';

/**
 * What the formatter these screens used to carry would have printed.
 *
 * Written out rather than described, so each test can require its absence. A
 * ceiling with no floor is the whole defect, and it is reproduced here exactly:
 * no `minimumFractionDigits`, the currency arriving as a variable.
 */
function asTheOldFormatterPrinted(amount: string, currency: string): string {
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number(amount));
}

function makeTaxQuote(currency: string, amount: string): ContractTaxQuote {
  return {
    jurisdiction: 'JP',
    region_subcode: null,
    currency,
    net: amount,
    vat: amount,
    stamp_duty: '0',
    transfer_fee: '0',
    registration_fee: '0',
    absd: '0',
    late_interest: '0',
    subtotal_taxes: amount,
    grand_total: amount,
    breakdown: [{ line: 'VAT (standard)', amount }],
  };
}

function makePriceQuote(currency: string, amount: string): PriceQuote {
  return {
    plot_id: 'plot-1',
    base_price: amount,
    lines: [
      {
        rule_id: 'rule-1',
        rule_name: 'Base price',
        rule_type: 'base',
        pct: null,
        fixed: null,
        amount,
      },
    ],
    total: amount,
    currency,
    computed_at: '2026-04-07T10:00:00Z',
    price_list_id: 'list-1',
  };
}

const ACTIVE_LIST = {
  id: 'list-1',
  development_id: 'dev-1',
  name: 'Launch prices',
  effective_from: '2026-01-01',
  effective_to: null,
  currency: 'JPY',
  status: 'active',
  created_by: null,
  notes: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} as unknown as PriceList;

const PLOT = {
  id: 'plot-1',
  plot_number: 'A-01',
  currency: 'JPY',
  status: 'planned',
  development_id: 'dev-1',
} as unknown as Plot;

/** The pricing page opens with a breadcrumb, so a router has to be above it. */
function renderWithQuery(node: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>{node}</QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usePreferencesStore.setState({ numberLocale: LOCALE });
  priceListsMock.mockResolvedValue([ACTIVE_LIST]);
  plotsMock.mockResolvedValue([PLOT]);
});

describe('the tax breakdown states the decimals the currency has', () => {
  it('rounds a yen line rather than inventing a tenth of a yen', async () => {
    taxQuoteMock.mockResolvedValue(makeTaxQuote('JPY', AMOUNT));
    renderWithQuery(<TaxQuotePanel contractId="contract-1" currency="JPY" />);

    const table = await screen.findByTestId('taxquote-breakdown');
    const text = table.textContent ?? '';

    expect(text).toContain(formatCurrency(AMOUNT, 'JPY', LOCALE));
    // The fixture has to be one the two formatters disagree on, or the
    // assertion above would hold against the code this test exists to catch.
    expect(asTheOldFormatterPrinted(AMOUNT, 'JPY')).not.toBe(
      formatCurrency(AMOUNT, 'JPY', LOCALE),
    );
    expect(text).not.toContain(asTheOldFormatterPrinted(AMOUNT, 'JPY'));
  });

  it('keeps the third decimal a dinar actually has', async () => {
    taxQuoteMock.mockResolvedValue(makeTaxQuote('KWD', AMOUNT));
    renderWithQuery(<TaxQuotePanel contractId="contract-1" currency="KWD" />);

    const table = await screen.findByTestId('taxquote-breakdown');
    const text = table.textContent ?? '';

    expect(text).toContain(formatCurrency(AMOUNT, 'KWD', LOCALE));
    expect(asTheOldFormatterPrinted(AMOUNT, 'KWD')).not.toBe(
      formatCurrency(AMOUNT, 'KWD', LOCALE),
    );
    expect(text).not.toContain(asTheOldFormatterPrinted(AMOUNT, 'KWD'));
  });
});

describe('the pricing simulator states the decimals the currency has', () => {
  it('quotes a yen unit at whole yen', async () => {
    quotePriceMock.mockResolvedValue(makePriceQuote('JPY', AMOUNT));
    const { container } = renderWithQuery(<PricingEnginePage />);

    // The tab bar carries `role="tab"`, and the mobile `<select>` beside it
    // renders in jsdom too, so the role is what tells the two apart. Both
    // controls are named by their key rather than their English text: this page
    // passes its default as a positional argument, `t(key, 'Simulator')`, and
    // the i18n mock in `src/test/setup.ts` only reads a default out of an
    // options object, so the key itself is what reaches the DOM here.
    fireEvent.click(await screen.findByRole('tab', { name: 'propdev.pricing.tab.sim' }));
    const compute = await screen.findByRole('button', { name: 'propdev.pricing.compute' });
    await waitFor(() => expect(compute).not.toBeDisabled());
    fireEvent.click(compute);

    // Read `textContent` rather than a text query. German separates the amount
    // from its symbol with a non-breaking space, and the query normalisers
    // collapse that to a plain space in the DOM only, leaving the expected
    // string carrying a U+00A0 that the comparison no longer has. The two
    // print identically in a failure message, so the mismatch reads as "the
    // page did not render the quote" about a page that rendered it correctly.
    await waitFor(() =>
      expect(container.textContent ?? '').toContain(formatCurrency(AMOUNT, 'JPY', LOCALE)),
    );
    expect(asTheOldFormatterPrinted(AMOUNT, 'JPY')).not.toBe(
      formatCurrency(AMOUNT, 'JPY', LOCALE),
    );
    expect(container.textContent ?? '').not.toContain(asTheOldFormatterPrinted(AMOUNT, 'JPY'));
  });
});
