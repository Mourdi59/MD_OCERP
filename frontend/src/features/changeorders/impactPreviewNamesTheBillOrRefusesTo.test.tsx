// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for the bill-of-quantities line of <ImpactSimulator />.
//
// The preview's job is to say what approving would do. It used to say one
// thing in three different situations: "Will add 1 new section with N
// positions to <bill>", falling back to the words "the project BOQ" whenever
// the backend could not name a bill. Two of those three situations write
// nothing at all - the project has several unlocked bills, so the approval
// refuses to choose, or it has none - and in both the preview was promising a
// write that the action would not make. A preview that promises what the
// action refuses is worse than one that guesses along with it, because the
// user acts on the promise.
//
// So the assertions here are about which of the three sentences is rendered,
// and the ambiguous case is checked twice: that it says what is true, and
// that the words the old fallback used are gone. The named-bill case is the
// control - without it an implementation that always warned would pass.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { SimulateImpactResponse } from './api';

const simulateImpact = vi.fn();
const publishScenario = vi.fn();

vi.mock('./api', () => ({
  simulateImpact: (...args: unknown[]) => simulateImpact(...args),
  publishScenario: (...args: unknown[]) => publishScenario(...args),
}));

import { ImpactSimulator } from './ImpactSimulator';

/** A complete projection; each case overrides only its `boq` block, so the
 *  rest of the panel is identical across them and cannot explain a diff. */
function projection(boq: Partial<SimulateImpactResponse['boq']>): SimulateImpactResponse {
  return {
    order_id: 'co-1',
    code: 'CO-001',
    base_currency: 'EUR',
    as_of: '2026-08-22T09:00:00',
    co_cost_native: '12500.00',
    co_currency: 'EUR',
    co_cost_base: '12500.00',
    fx_converted: false,
    cost: {
      budget_before: '1000000.00',
      budget_after: '1012500.00',
      delta: '12500.00',
      pct_of_budget: 1.25,
    },
    schedule: {
      current_end_date: '2027-03-01',
      projected_end_date: '2027-03-05',
      days_added: 4,
      finish_moves: true,
    },
    evm: {
      bac_before: '1000000.00',
      bac_after: '1012500.00',
      eac_before: '1010000.00',
      eac_after: '1022500.00',
      vac_before: '-10000.00',
      vac_after: '-10000.00',
      spi: '0.98',
      cpi: '0.99',
    },
    boq: {
      item_count: 2,
      sections_added: 1,
      positions_added: 12,
      target_boq_name: null,
      target_boq_ambiguous: false,
      ...boq,
    },
    notes: [],
  };
}

async function renderPreview(boq: Partial<SimulateImpactResponse['boq']>): Promise<void> {
  simulateImpact.mockResolvedValue(projection(boq));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ImpactSimulator orderId="co-1" defaultCost="12500.00" defaultDays={4} canPublish={false} />
    </QueryClientProvider>,
  );
  // The panel opens by default, so the projection is requested on mount. The
  // anchor is the section heading matched exactly: two of the four sentences
  // below contain the words "bill of quantities" themselves, so a loose match
  // here resolves to several elements and fails for the wrong reason.
  await screen.findByText('Bill of quantities');
}

describe('the impact preview and the bill it names', () => {
  beforeEach(() => {
    simulateImpact.mockReset();
    publishScenario.mockReset();
  });
  afterEach(cleanup);

  it('names the bill when the backend named one', async () => {
    await renderPreview({ target_boq_name: 'Variations bill', target_boq_ambiguous: false });

    expect(await screen.findByText(/Will add 1 new section with 12 positions to Variations bill\./)).toBeInTheDocument();
    // The control: nothing here should read as a refusal.
    expect(screen.queryByText(/cannot be placed automatically/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/would not be written/i)).not.toBeInTheDocument();
  });

  it('refuses to name one, and says why, when several bills are unlocked', async () => {
    await renderPreview({ target_boq_name: null, target_boq_ambiguous: true });

    expect(
      await screen.findByText(
        /more than one unlocked bill of quantities, so the 12 positions cannot be placed automatically/i,
      ),
    ).toBeInTheDocument();
    // And it leads somewhere: the thing that resolves it is naming the bill.
    expect(screen.getByText(/Name the bill when you approve this change order\./)).toBeInTheDocument();
    // The promise the old fallback made is gone. This is the assertion that
    // would have caught the half-finished state: the flag existed on both
    // sides of the wire and nothing read it, so the panel still said this.
    expect(screen.queryByText(/the project BOQ/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Will add 1 new section/i)).not.toBeInTheDocument();
  });

  it('says nothing would be written when the project has no unlocked bill', async () => {
    await renderPreview({ target_boq_name: null, target_boq_ambiguous: false });

    expect(
      await screen.findByText(/no unlocked bill of quantities, so the 12 positions would not be written into one/i),
    ).toBeInTheDocument();
    // Distinct from the ambiguous case: there is no bill to name, so the
    // preview must not send the user looking for one.
    expect(screen.queryByText(/Name the bill when you approve/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/the project BOQ/i)).not.toBeInTheDocument();
  });

  it('still reports an item-less change order as writing nothing', async () => {
    await renderPreview({ item_count: 0, positions_added: 0, target_boq_ambiguous: true });

    expect(await screen.findByText(/No line items yet, so nothing would be written to the BOQ\./)).toBeInTheDocument();
    // Ambiguity is irrelevant when there is nothing to place, and the backend
    // approves such a change order without asking - the preview agrees.
    expect(screen.queryByText(/cannot be placed automatically/i)).not.toBeInTheDocument();
  });
});
