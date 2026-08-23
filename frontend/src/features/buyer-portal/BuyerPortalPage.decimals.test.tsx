// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What the buyer is shown owes them the decimals their currency has.
//
// This page is the one surface in the product with no operator behind it. A
// buyer who reads an instalment as a number their currency cannot express has
// nobody to ask, so the money here goes through `shared/lib/money` rather than
// through a formatter written out in the page.
//
// The one it replaces capped every currency at two decimals with no floor
// under it, which is a claim about every currency an instalment can arrive in
// rather than a rounding preference. A yen instalment of 1234.50 read
// "1.234,5 ¥" - a tenth of a unit the yen has no coin for - and a dinar
// instalment lost its third decimal, or on a pre-ES2023 engine threw
// `RangeError` out of the render and took the whole portal down with it,
// because a floor of three cannot fit under a ceiling of two.
//
// Note what is NOT a defect here, because it decides the fixtures: under
// `style: 'currency'` the engine defaults the floor to the currency's own
// minor units, so a euro or dollar instalment of 1234.50 reads "1.234,50 €"
// through the broken formatter and the fixed one alike. A euro fixture would
// have passed against the code this file exists to catch. JPY and KWD are the
// families where the two formatters disagree, and ISO and CLDR agree with each
// other on both, so nothing here rests on the open question about the
// currencies where they do not.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { formatCurrency } from '@/shared/lib/money';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

// `src/test/setup.ts` mocks `useParams` globally to `{}`, and this page reads
// its magic-link token out of the route: with no token it renders the
// "ask your agent for a new link" screen and never fetches anything.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ token: 'magic-link-token' }),
    useSearchParams: () => [new URLSearchParams(), vi.fn()],
  };
});

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return { ...actual, fetchPortalOverview: vi.fn() };
});

import { fetchPortalOverview } from './api';
import type { PortalOverviewResponse } from './api';
import { BuyerPortalPage } from './BuyerPortalPage';

const overviewMock = vi.mocked(fetchPortalOverview);

/** Pinned so the expectation and the page read one preference, not the host. */
const LOCALE = 'de-DE';

/** An amount ending in a round ten, which is where a truncating cap shows. */
const AMOUNT = '1234.50';

/** The formatter the page used to carry, kept so its output can be forbidden. */
function asTheOldFormatterPrinted(amount: string, currency: string): string {
  return new Intl.NumberFormat(LOCALE, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  }).format(Number(amount));
}

function makeOverview(currency: string, amount: string): PortalOverviewResponse {
  return {
    buyer_id: 'buyer-1',
    buyer_full_name: 'A Buyer',
    buyer_email: 'buyer@example.com',
    // Blank on purpose: a language here makes the page switch i18next on
    // mount, which is a different question from the one under test.
    buyer_language: '',
    development_name: 'Riverside Phase 2',
    reservation: null,
    sales_contract: null,
    payment_schedule_total: amount,
    payment_schedule_paid: '0',
    payment_schedule_outstanding: amount,
    payment_schedule_currency: currency,
    instalments: [
      {
        id: 'inst-1',
        sequence: 1,
        milestone_label: 'On signing',
        due_date: '2026-06-30',
        amount,
        amount_paid: '0',
        amount_outstanding: amount,
        status: 'due',
        paid_at: null,
        currency,
      },
    ],
    documents: [],
    kyc_requests: [],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  usePreferencesStore.setState({ numberLocale: LOCALE });
});

describe('the instalments a buyer is shown', () => {
  it('round a yen instalment instead of showing a tenth of a yen', async () => {
    overviewMock.mockResolvedValue(makeOverview('JPY', AMOUNT));
    const { container } = render(
      <MemoryRouter>
        <BuyerPortalPage />
      </MemoryRouter>,
    );

    await screen.findByTestId('payments-section');

    // `textContent` rather than a text query: German separates the amount from
    // its symbol with a non-breaking space, the query normalisers collapse it
    // on the DOM side only, and the resulting mismatch is invisible in the
    // failure output because both strings print the same.
    const text = container.textContent ?? '';
    expect(text).toContain(formatCurrency(AMOUNT, 'JPY', LOCALE));
    // The fixture has to be one the two formatters disagree on, or the line
    // above would hold against the code this test exists to catch.
    expect(asTheOldFormatterPrinted(AMOUNT, 'JPY')).not.toBe(
      formatCurrency(AMOUNT, 'JPY', LOCALE),
    );
    expect(text).not.toContain(asTheOldFormatterPrinted(AMOUNT, 'JPY'));
  });

  it('keep the third decimal a dinar instalment actually has', async () => {
    overviewMock.mockResolvedValue(makeOverview('KWD', AMOUNT));
    const { container } = render(
      <MemoryRouter>
        <BuyerPortalPage />
      </MemoryRouter>,
    );

    await screen.findByTestId('payments-section');

    const text = container.textContent ?? '';
    expect(text).toContain(formatCurrency(AMOUNT, 'KWD', LOCALE));
    expect(asTheOldFormatterPrinted(AMOUNT, 'KWD')).not.toBe(
      formatCurrency(AMOUNT, 'KWD', LOCALE),
    );
    expect(text).not.toContain(asTheOldFormatterPrinted(AMOUNT, 'KWD'));
  });
});
