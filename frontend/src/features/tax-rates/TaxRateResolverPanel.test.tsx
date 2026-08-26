// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <TaxRateResolverPanel /> - the screen the resolver answers onto.
//
// One claim is worth more than the rest here, and it is the one the backend
// was built around: Alberta answering five per cent and nobody having chosen a
// province must not render as the same cell. Both are Canada, and both come
// back carrying `federal_rate_pct: "5"`, so the payloads are one field apart.
// The mechanical form of the claim is that the slot a rate appears in holds no
// digit at all when there is no rate, and the negative control is the same
// assertion run against Alberta, where it must fail to hold.
//
// Every fixture that stands for a choice offers more than one candidate. A
// fixture carrying one province cannot tell "picked Ontario" from "combined
// everything it had".

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';

import type { TaxResolution } from './api';

/* ── i18n ──────────────────────────────────────────────────────────────────
   The panel and the shared chrome it renders inside both use the
   `t(key, { defaultValue })` form, and the interpolation matters: the copy
   under an unanswered slot names the country, and a stub that left `{{country}}`
   unfilled would make the prose assertions below pass for the wrong reason. */

vi.mock('react-i18next', () => {
  type Opts = Record<string, unknown>;
  const fill = (template: string, opts?: Opts): string => {
    if (!opts) return template;
    const scope = (opts.replace as Opts | undefined) ?? opts;
    return template.replace(/\{\{(\w+)\}\}/g, (_match, name: string) =>
      scope[name] === undefined ? `{{${name}}}` : String(scope[name]),
    );
  };
  return {
    useTranslation: () => ({
      t: (key: string, second?: string | Opts, third?: Opts) => {
        if (typeof second === 'string') return fill(second, third);
        const dflt = second?.defaultValue;
        return fill(typeof dflt === 'string' ? dflt : key, second);
      },
      i18n: { language: 'en', changeLanguage: vi.fn() },
    }),
    Trans: ({ children }: { children?: unknown }) => children ?? null,
    initReactI18next: { type: '3rdParty', init: () => undefined },
    I18nextProvider: ({ children }: { children?: unknown }) => children ?? null,
  };
});

const resolveTaxRate = vi.fn();

/* Spread the real module: `ApiError` is a runtime class the panel uses in an
   `instanceof` check, and a hand-written export list that stubs it out turns
   the refusal branch into a silent miss rather than a failure. */
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return {
    ...actual,
    listCountries: vi.fn(async () => ({
      // More than one country, so "shows Canada" is distinguishable from
      // "shows whatever came first".
      items: [
        { iso_code: 'CA', name_en: 'Canada' },
        { iso_code: 'DE', name_en: 'Germany' },
        { iso_code: 'US', name_en: 'United States' },
      ],
      total: 3,
    })),
    listSubdivisions: vi.fn(async (code: string) => ({
      country_code: code,
      items:
        code === 'CA'
          ? [
              { code: 'CA-AB', name: 'Alberta' },
              { code: 'CA-ON', name: 'Ontario' },
              { code: 'CA-QC', name: 'Quebec' },
            ]
          : [],
      total: code === 'CA' ? 3 : 0,
    })),
    listTaxConfigsByCountry: vi.fn(async () => ({ items: [], total: 0 })),
    resolveTaxRate: (...args: unknown[]) => resolveTaxRate(...args),
  };
});

import { TaxRateResolverPanel } from './TaxRateResolverPanel';

function answer(over: Partial<TaxResolution>): TaxResolution {
  return {
    country_code: 'CA',
    subdivision_code: null,
    subdivision_name: null,
    status: 'subdivision_unknown',
    resolved: false,
    combined_rate_pct: null,
    // Populated on the refusals as well as the answers. The panel must not
    // draw it on a refusal, which is what the Canada-wide test below pins.
    federal_rate_pct: '5',
    as_of: '2026-08-26',
    components: [],
    reason: null,
    ...over,
  };
}

const ONTARIO = answer({
  status: 'harmonised',
  resolved: true,
  subdivision_code: 'CA-ON',
  subdivision_name: 'Ontario',
  combined_rate_pct: '13',
  components: [
    {
      tax_code: 'HST_ON',
      tax_name: 'HST',
      rate_pct: '13',
      combination: 'replaces_federal',
      base: 'consideration',
      effective_rate_pct: '13',
    },
  ],
});

const ALBERTA = answer({
  status: 'federal_only',
  resolved: true,
  subdivision_code: 'CA-AB',
  subdivision_name: 'Alberta',
  combined_rate_pct: '5',
  components: [
    {
      tax_code: 'GST',
      tax_name: 'GST',
      rate_pct: '5',
      combination: 'federal',
      base: 'consideration',
      effective_rate_pct: '5',
    },
  ],
});

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TaxRateResolverPanel />
    </QueryClientProvider>,
  );
}

/* Wait for the option, not for the select.
   The select is on screen from the first paint with only its placeholder in
   it, so `findByLabelText` resolves immediately and `fireEvent.change` to a
   value no `<option>` carries yet is silently a no-op: the select keeps its
   old value and the panel never re-renders. Waiting for the option is waiting
   for the query behind it. */
async function pickCountry(code: string, name: string) {
  await screen.findByRole('option', { name });
  fireEvent.change(screen.getByLabelText('Country'), { target: { value: code } });
}

const pickCanada = () => pickCountry('CA', 'Canada');

async function pickRegion(code: string, name: string) {
  await screen.findByRole('option', { name });
  fireEvent.change(screen.getByLabelText('Region'), { target: { value: code } });
}

beforeEach(() => {
  resolveTaxRate.mockReset();
});
afterEach(cleanup);

describe('TaxRateResolverPanel', () => {
  it('asks for a country before it says anything about a rate', async () => {
    resolveTaxRate.mockResolvedValue(ONTARIO);
    renderPanel();
    expect(await screen.findByText('No country chosen')).toBeTruthy();
    expect(screen.queryByTestId('tax-rates-combined')).toBeNull();
  });

  it('prices Ontario at the harmonised rate and shows the layer it came from', async () => {
    resolveTaxRate.mockResolvedValue(ONTARIO);
    renderPanel();
    await pickCanada();
    await pickRegion('CA-ON', 'Ontario');

    const rate = await screen.findByTestId('tax-rates-combined');
    expect(rate.textContent).toBe('13%');
    expect(screen.getByText('Replaces the federal rate')).toBeTruthy();
  });

  it('prices Alberta at the federal rate and says that is the whole answer', async () => {
    resolveTaxRate.mockResolvedValue(ALBERTA);
    renderPanel();
    await pickCanada();
    await pickRegion('CA-AB', 'Alberta');

    const rate = await screen.findByTestId('tax-rates-combined');
    expect(rate.textContent).toBe('5%');
    // Not "no rate found". A region that charges nothing of its own is an
    // answer, and the screen says so rather than leaving the reader to guess
    // whether five is a figure or a fallback.
    expect(
      screen.getByText(/This region charges nothing of its own/),
    ).toBeTruthy();
  });

  it('puts no number at all where the province was never chosen', async () => {
    resolveTaxRate.mockResolvedValue(answer({}));
    renderPanel();
    await pickCanada();

    const slot = await screen.findByTestId('tax-rates-answer-slot');
    // The claim, mechanically: nothing in the rate slot can be read as a rate.
    expect(slot.textContent ?? '').not.toMatch(/\d/);
    expect(screen.queryByTestId('tax-rates-combined')).toBeNull();

    // And the federal rate the payload carries is nowhere on the panel. It is
    // a real five per cent, correct for Alberta, and standing it next to an
    // unanswered question is the precise failure this screen exists to stop.
    const panel = screen.getByTestId('tax-rates-unanswered');
    expect(panel.textContent ?? '').not.toMatch(/\d/);

    // It reads as a question, not as a failure.
    expect(screen.getByText('Which region is this project in?')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Choose a region' })).toBeTruthy();
  });

  it('holds the digit check to a standard Alberta cannot meet', async () => {
    // Negative control for the assertion above. The same selector, the same
    // matcher, against the answer that does carry a number: if this passes
    // too, the check is measuring the absence of the slot rather than the
    // absence of a digit in it.
    resolveTaxRate.mockResolvedValue(ALBERTA);
    renderPanel();
    await pickCanada();
    await pickRegion('CA-AB', 'Alberta');

    const slot = await screen.findByTestId('tax-rates-answer-slot');
    expect(slot.textContent ?? '').toMatch(/\d/);
    expect(screen.queryByTestId('tax-rates-unanswered')).toBeNull();
  });

  it('gives the three unanswerable cases three different panels', async () => {
    // Same status on two of them, and they must still not be the same panel.
    const cases: [TaxResolution, string, RegExp][] = [
      [answer({}), 'needs_subdivision', /Which region is this project in\?/],
      [
        answer({ country_code: 'US', subdivision_code: 'US-TX', subdivision_name: null }),
        'subdivision_not_carried',
        /No rate on file for this region/,
      ],
      [
        answer({ subdivision_code: 'CA-ON', subdivision_name: 'Ontario' }),
        'rates_unlabelled',
        /The regional rates are not labelled yet/,
      ],
    ];

    const seen = new Set<string>();
    for (const [payload, kind, copy] of cases) {
      resolveTaxRate.mockResolvedValue(payload);
      renderPanel();
      await pickCanada();

      const panel = await screen.findByTestId('tax-rates-unanswered');
      expect(panel.getAttribute('data-kind')).toBe(kind);
      expect(panel.textContent ?? '').toMatch(copy);
      seen.add(kind);
      cleanup();
    }
    // Three distinct panels, not one panel reached three times.
    expect(seen.size).toBe(3);
  });

  it('does not carry a province across a change of country', async () => {
    // A stale CA-ON against Germany would resolve to something, and whatever
    // it resolved to would be nobody's intention.
    resolveTaxRate.mockResolvedValue(ONTARIO);
    renderPanel();
    await pickCanada();
    await pickRegion('CA-ON', 'Ontario');
    await screen.findByTestId('tax-rates-combined');

    const country = screen.getByLabelText('Country');
    fireEvent.change(country, { target: { value: 'DE' } });

    await waitFor(() => {
      const last = resolveTaxRate.mock.calls.at(-1);
      expect(last?.[0]).toBe('DE');
      expect(last?.[1]).toBeNull();
    });
  });

  it('shows a refused lookup as a defect, still with no number in the slot', async () => {
    // The server raises this one rather than returning it, so it arrives as a
    // thrown ApiError and not as a status on a payload. It is the one branch
    // that reaches the rate slot without going through the classifier, which
    // makes it the branch where a stray figure would not be caught by any of
    // the assertions above.
    resolveTaxRate.mockRejectedValue(
      new ApiError(409, 'Conflict', {
        detail: { code: 'multiple_replacing_rates', message: 'Two rates replace the federal one.' },
      }),
    );
    renderPanel();
    await pickCanada();
    await pickRegion('CA-ON', 'Ontario');

    const panel = await screen.findByTestId('tax-rates-unanswered');
    expect(panel.getAttribute('data-kind')).toBe('refused');
    expect(screen.getByText('Two rates both replace the federal one')).toBeTruthy();

    const slot = screen.getByTestId('tax-rates-answer-slot');
    expect(slot.textContent ?? '').not.toMatch(/\d/);
    expect(screen.queryByTestId('tax-rates-combined')).toBeNull();
  });

  it('reads the code inside the refusal rather than treating every 409 alike', async () => {
    // `refusalCodeOf` narrows an unknown body two levels down to reach the
    // code. If either level is wrong every refusal falls to the general text,
    // which still renders a refusal panel and still passes the test above. So
    // the claim has to be that two refusals read differently: one title would
    // be the finding.
    const titles: string[] = [];
    for (const body of [
      { detail: { code: 'rate_not_numeric' } },
      { detail: { code: 'something_else_entirely' } },
    ]) {
      resolveTaxRate.mockRejectedValue(new ApiError(409, 'Conflict', body));
      renderPanel();
      await pickCanada();

      const panel = await screen.findByTestId('tax-rates-unanswered');
      titles.push(panel.querySelector('h3')?.textContent ?? '');
      cleanup();
    }

    expect(titles[0]).toBe('A rate on file is not a number');
    expect(titles[0]).not.toBe(titles[1]);
  });
});
