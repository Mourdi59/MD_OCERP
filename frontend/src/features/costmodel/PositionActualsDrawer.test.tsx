// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <PositionActualsDrawer>.
//
// These guard the three facts the panel exists to keep apart, and each one is
// written as a PAIR. A test that only checks the interesting case passes just
// as happily when the component has collapsed both cases into one rendering,
// which is the exact bug being guarded against, so every claim here is paired
// with its opposite:
//
//   1. never reported vs reported as zero
//   2. ordered beyond the estimate vs estimate still uncommitted
//   3. no cost line at all vs a cost line with nothing against it yet
//
// The i18n shim below returns the KEY, and the assertions are written against
// keys rather than English wording on purpose: the question these tests ask is
// "which sentence did the component choose", and a key answers that exactly
// while a wording can be reworded without touching the choice.

import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { PositionActualsRow, PositionActualsResponse } from './api';

/* ── i18n shim ────────────────────────────────────────────────────────────
 * Returns the key. The component passes no defaultValue anywhere (deliberate:
 * a key carrying one is invisible to every locale gate we have), so the key is
 * all there is, and that is what makes these assertions precise. Must export
 * the whole react-i18next surface because the drawer reaches app/i18n.ts
 * through the shared UI barrel. */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
  I18nextProvider: ({ children }: { children: React.ReactNode }) => children,
}));

/* ── API mock ─────────────────────────────────────────────────────────── */

const apiMocks = vi.hoisted(() => ({ getPositionActualsMock: vi.fn() }));
vi.mock('./api', () => ({
  costModelApi: { getPositionActuals: apiMocks.getPositionActualsMock },
}));

import { PositionActualsDrawer } from './PositionActualsDrawer';

const { getPositionActualsMock } = apiMocks;

/** A position with nothing remarkable about it; each test bends one field. */
function makeRow(overrides: Partial<PositionActualsRow> = {}): PositionActualsRow {
  return {
    boq_position_id: 'p-1',
    ordinal: '1.1',
    description: 'Concrete C25/30 to foundations',
    unit: 'm3',
    cost_line_id: 'cl-1',
    cost_line_code: 'CL-001',
    on_cost_spine: true,
    estimate_quantity: '120.0000',
    estimate_unit_rate: '180.00',
    estimate_amount: '21600.00',
    budget_planned: '21000.00',
    budget_actual: '0.00',
    committed_amount: '1800.00',
    contracted_amount: '0.00',
    claimed_amount: '0.00',
    uncommitted_amount: '19800.00',
    installed_percent: '40.00',
    installed_amount: '8640.00',
    consumed_quantity: '55.0000',
    consumed_amount: '9900.00',
    ...overrides,
  };
}

function respond(row: PositionActualsRow | null, currency = 'EUR'): PositionActualsResponse {
  return {
    currency,
    rows: row ? [row] : [],
    totals: {},
    positions_off_spine: row && !row.on_cost_spine ? 1 : 0,
  };
}

async function renderDrawer(response: PositionActualsResponse) {
  getPositionActualsMock.mockResolvedValue(response);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PositionActualsDrawer
        open
        onClose={() => {}}
        projectId="proj-1"
        positionId="p-1"
        positionOrdinal="1.1"
        positionDescription="Concrete C25/30 to foundations"
      />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText('costmodel.actuals.section_estimate')).toBeTruthy());
}

/** Text of the whole row a label sits in, so the value can be inspected. */
function valueOf(labelKey: string): string {
  const label = screen.getByText(labelKey);
  return label.parentElement?.textContent ?? '';
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('PositionActualsDrawer, never reported against reported as zero', () => {
  it('says nobody has reported when installed_percent is null, and shows no percentage at all', async () => {
    await renderDrawer(respond(makeRow({ installed_percent: null, installed_amount: '0.00' })));

    expect(screen.getByText('costmodel.actuals.never_reported')).toBeTruthy();
    expect(screen.getByText('costmodel.actuals.never_reported_hint')).toBeTruthy();

    // The derived value is suppressed too. installed_amount is computed from
    // the very null being reported here, so printing it would state the
    // absence a second time in the shape of a measurement.
    expect(screen.queryByText('costmodel.actuals.installed_amount')).toBeNull();

    // And no percentage is drawn anywhere. An empty bar or a "0.00%" is
    // indistinguishable from a crew that walked the position and found
    // nothing done, which is a different fact.
    const installedRow = valueOf('costmodel.actuals.installed_percent');
    expect(installedRow).not.toMatch(/%/);
    expect(installedRow).not.toMatch(/0/);
  });

  it('shows an actual zero percent when the crew HAS reported none', async () => {
    await renderDrawer(respond(makeRow({ installed_percent: '0.00', installed_amount: '0.00' })));

    // The opposite of the test above, and the reason it is here: without it,
    // a component that rendered "not reported" for both cases would pass.
    expect(screen.queryByText('costmodel.actuals.never_reported')).toBeNull();
    expect(screen.queryByText('costmodel.actuals.never_reported_hint')).toBeNull();
    expect(screen.getByText('costmodel.actuals.installed_amount')).toBeTruthy();
    expect(valueOf('costmodel.actuals.installed_percent')).toMatch(/%/);
  });
});

describe('PositionActualsDrawer, overrun is not clamped', () => {
  it('labels a negative remaining as ordered beyond the estimate and keeps the sign', async () => {
    await renderDrawer(
      respond(makeRow({ committed_amount: '25000.00', uncommitted_amount: '-3400.00' })),
    );

    expect(screen.getByText('costmodel.actuals.over_ordered')).toBeTruthy();
    // Not merely relabelled: the amount itself still reads as a shortfall
    // rather than being floored to zero to make the row look finished.
    const text = valueOf('costmodel.actuals.over_ordered');
    expect(text).toMatch(/[-−]/);
    expect(text).toMatch(/3.?400/);

    // The two labels are mutually exclusive; showing both would be two
    // answers to one question.
    expect(screen.queryByText('costmodel.actuals.uncommitted')).toBeNull();
  });

  it('labels a positive remaining as not yet committed', async () => {
    await renderDrawer(respond(makeRow({ uncommitted_amount: '19800.00' })));

    expect(screen.getByText('costmodel.actuals.uncommitted')).toBeTruthy();
    expect(screen.queryByText('costmodel.actuals.over_ordered')).toBeNull();
    expect(valueOf('costmodel.actuals.uncommitted')).not.toMatch(/[-−]/);
  });
});

describe('PositionActualsDrawer, structural zero against recorded zero', () => {
  it('explains the missing cost line instead of drawing a column of zeros', async () => {
    await renderDrawer(
      respond(
        makeRow({
          on_cost_spine: false,
          cost_line_id: null,
          cost_line_code: '',
          budget_planned: '0.00',
          committed_amount: '0.00',
          contracted_amount: '0.00',
          claimed_amount: '0.00',
          uncommitted_amount: '21600.00',
        }),
      ),
    );

    expect(screen.getByText('costmodel.actuals.off_spine_title')).toBeTruthy();
    expect(screen.getByText('costmodel.actuals.off_spine_body')).toBeTruthy();

    // No money row at all. A zero here would be a claim about the project
    // ("nothing was ordered") when the true statement is about the link
    // ("nothing could have been").
    expect(screen.queryByText('costmodel.actuals.committed')).toBeNull();
    expect(screen.queryByText('costmodel.actuals.contracted')).toBeNull();
    expect(screen.queryByText('costmodel.actuals.uncommitted')).toBeNull();
  });

  it('draws the money rows, zeros and all, when the position IS on the spine', async () => {
    await renderDrawer(
      respond(
        makeRow({
          committed_amount: '0.00',
          contracted_amount: '0.00',
          claimed_amount: '0.00',
        }),
      ),
    );

    // Here a zero is a real aggregate over real records, so it is shown.
    expect(screen.queryByText('costmodel.actuals.off_spine_title')).toBeNull();
    expect(screen.getByText('costmodel.actuals.committed')).toBeTruthy();
    expect(screen.getByText('costmodel.actuals.contracted')).toBeTruthy();
  });
});

describe('PositionActualsDrawer, the two spines stay apart', () => {
  it('shows quantity in the position unit and money in the project currency', async () => {
    await renderDrawer(respond(makeRow()));

    // Quantity carries its unit, never a currency.
    const quantity = valueOf('costmodel.actuals.estimate_quantity');
    expect(quantity).toMatch(/m3/);
    expect(quantity).not.toMatch(/€|EUR/);

    // Consumption is reported as a quantity AND as a value, side by side and
    // separately, because the two are only comparable when the store issues
    // in the position's own unit.
    expect(valueOf('costmodel.actuals.consumed_quantity')).toMatch(/m3/);
    expect(screen.getByText('costmodel.actuals.consumed_amount')).toBeTruthy();

    // And the panel says out loud that they are not addable.
    expect(screen.getByText('costmodel.actuals.money_note')).toBeTruthy();
  });

  it('keeps a four decimal unit rate instead of rounding it to the minor unit', async () => {
    // The one figure the backend deliberately does not quantise. Rounding a
    // rate of 0.0001 to 0.00 destroys it before it ever meets a quantity.
    await renderDrawer(respond(makeRow({ estimate_unit_rate: '0.0001' })));

    expect(valueOf('costmodel.actuals.estimate_unit_rate')).toMatch(/0\.0001/);
  });

  it('keeps a rate that arrives in exponent form', async () => {
    // Pydantic renders a Decimal with str(), and Python switches to exponent
    // notation once the exponent passes -6, so this is what the wire actually
    // sends for 0.0000001. Counting decimals in the TEXT sees none, falls back
    // to the currency's two and prints 0.00, silently destroying the rate.
    await renderDrawer(respond(makeRow({ estimate_unit_rate: '1E-7' })));

    const rendered = valueOf('costmodel.actuals.estimate_unit_rate');
    expect(rendered).toMatch(/0\.0000001/);
    expect(rendered).not.toMatch(/0\.00[^0]/);
  });

  it('still shows a whole rate at the currency minor unit', async () => {
    // The counterpart: raising the ceiling for small rates must not strip the
    // cents off an ordinary one.
    await renderDrawer(respond(makeRow({ estimate_unit_rate: '180' })));

    expect(valueOf('costmodel.actuals.estimate_unit_rate')).toMatch(/180\.00/);
  });

  it('says the currency is unknown rather than guessing one', async () => {
    // The endpoint returns "" on a project with no base currency, on purpose,
    // because a hardcoded default prints a wrong unit on every amount.
    await renderDrawer(respond(makeRow(), ''));

    expect(screen.getByText('costmodel.actuals.no_currency')).toBeTruthy();
  });

  it('does not claim the currency is unknown when it is known', async () => {
    await renderDrawer(respond(makeRow(), 'EUR'));

    expect(screen.queryByText('costmodel.actuals.no_currency')).toBeNull();
  });
});

describe('PositionActualsDrawer, a position that did not resolve', () => {
  it('separates an empty result from a position with nothing recorded', async () => {
    getPositionActualsMock.mockResolvedValue(respond(null));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PositionActualsDrawer open onClose={() => {}} projectId="proj-1" positionId="p-1" />
      </QueryClientProvider>,
    );

    // The endpoint drops positions whose BOQ belongs to another project, so
    // no row means the position did not resolve here. That is not the same
    // as a position with nothing against it, and it does not get a page of
    // zeros either.
    await waitFor(() => expect(screen.getByText('costmodel.actuals.not_found')).toBeTruthy());
    expect(screen.queryByText('costmodel.actuals.section_money')).toBeNull();
  });
});

describe('PositionActualsDrawer, the query is gated', () => {
  it('asks for nothing until it has both a project and a position', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PositionActualsDrawer open onClose={() => {}} projectId={undefined} positionId="p-1" />
      </QueryClientProvider>,
    );

    // projectId is read off the loaded BOQ and is undefined while it loads.
    // Letting that reach the URL fetches /projects/undefined/...
    await waitFor(() => expect(getPositionActualsMock).not.toHaveBeenCalled());
  });
});
