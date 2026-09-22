// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// What a person can do to a contract they are still writing, and in what
// money a new contract and a new claim start.
//
// All four of these were walked on a running instance rather than read:
//   * the first line of every contract was saved with no unit, because the
//     add-line form that shows when there are no lines yet had no unit field,
//     and the compliance gate then refused to sign over it for ever;
//   * a line, once saved, could not be corrected or removed from the screen
//     at all, so the typo was permanent;
//   * a new claim was seeded in euros whatever the contract was in;
//   * a new contract was seeded in euros whatever the project was in.
//
// The API layer is exercised for real here (the mock is on apiGet/apiPost/
// apiPatch/apiDelete), so a wrong URL fails the test rather than passing it.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const api = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
}));

vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>('@/shared/lib/api');
  return { ...actual, ...api };
});

vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (sel: (s: { addToast: () => void }) => unknown) => sel({ addToast: vi.fn() }),
}));

import {
  ContractDetailDrawer,
  CreateContractModal,
  NewClaimModal,
} from './ContractsPage';
import type { ContractItem, ContractLine } from './api';

const CONTRACT_ID = 'ctr-1';
const LINE_ID = 'line-1';

function contract(overrides: Partial<ContractItem> = {}): ContractItem {
  return {
    id: CONTRACT_ID,
    code: 'C-001',
    title: 'Main works',
    contract_type: 'lump_sum',
    counterparty_type: 'subcontractor',
    counterparty_id: null,
    project_id: 'p-1',
    parent_contract_id: null,
    start_date: '2026-05-01',
    end_date: null,
    total_value: '1000',
    original_contract_value: null,
    currency: 'USD',
    retention_percent: '5',
    retention_release_event: 'substantial_completion',
    status: 'draft',
    signed_at: null,
    template_code: null,
    template_version: null,
    terms: {},
    created_by: null,
    metadata: {},
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  };
}

function line(overrides: Partial<ContractLine> = {}): ContractLine {
  return {
    id: LINE_ID,
    contract_id: CONTRACT_ID,
    parent_line_id: null,
    code: 'A1',
    description: 'Concrete',
    scope_section: null,
    line_type: 'work',
    unit: 'm3',
    quantity: '10',
    unit_rate: '100',
    total_value: '1000',
    order_index: 0,
    metadata: {},
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-05-01T00:00:00Z',
    ...overrides,
  };
}

/**
 * Answer the two reads these tests are about; `lines` is the schedule of
 * values. Everything else the drawer asks for - the dashboard, the analytics
 * panels, the retention ledger - is refused rather than answered with an
 * invented body: a panel given the wrong shape either throws or, worse,
 * renders something that reads like data. Refused, each panel shows its own
 * empty state and the schedule of values is left to be tested.
 */
function seedReads(lines: ContractLine[]) {
  api.apiGet.mockImplementation((path: string) => {
    if (path.endsWith('/lines')) return Promise.resolve(lines);
    if (path.startsWith('/v1/contracts/progress-claims/?'))
      return Promise.resolve({ items: [], total: 0, offset: 0, limit: 200 });
    return Promise.reject(new Error(`not mocked: ${path}`));
  });
}

function renderDrawer(c: ContractItem) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ContractDetailDrawer contractId={c.id} contracts={[c]} onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.apiGet.mockReset();
  api.apiPost.mockReset();
  api.apiPatch.mockReset();
  api.apiDelete.mockReset();
  seedReads([]);
});

afterEach(() => cleanup());

describe('the first line of a contract', () => {
  it('is asked for its unit, the same as every line after it', async () => {
    // Every contract starts with no lines, so this form is the one line one
    // always goes through. Without a unit here the compliance gate refuses
    // the signature with boq_quality.empty_unit and there is no way back.
    api.apiPost.mockResolvedValue(line());
    renderDrawer(contract());

    fireEvent.click(await screen.findByRole('button', { name: /Add line/i }));
    const unit = await screen.findByPlaceholderText('Unit');
    fireEvent.change(screen.getByPlaceholderText('Description'), {
      target: { value: 'Concrete' },
    });
    fireEvent.change(screen.getByPlaceholderText('Qty'), { target: { value: '10' } });
    fireEvent.change(unit, { target: { value: 'm3' } });
    fireEvent.change(screen.getByPlaceholderText('Rate'), { target: { value: '100' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(api.apiPost).toHaveBeenCalledTimes(1));
    expect(api.apiPost).toHaveBeenCalledWith(
      `/v1/contracts/contracts/${CONTRACT_ID}/lines`,
      expect.objectContaining({ unit: 'm3', description: 'Concrete' }),
    );
  });
});

describe('a line of the schedule of values', () => {
  it('can be corrected on the row, and only what changed is sent', async () => {
    seedReads([line()]);
    api.apiPatch.mockResolvedValue(line({ unit_rate: '120' }));
    renderDrawer(contract());

    const row = await screen.findByTestId(`sov-row-${LINE_ID}`);
    fireEvent.click(within(row).getByRole('button', { name: /^Edit$/i }));
    fireEvent.change(screen.getByLabelText('Rate'), { target: { value: '120' } });
    fireEvent.click(screen.getByRole('button', { name: /^Save$/i }));

    await waitFor(() => expect(api.apiPatch).toHaveBeenCalledTimes(1));
    // The description was not touched, so it is not sent back: another
    // person's correction to it is not undone by this one.
    expect(api.apiPatch).toHaveBeenCalledWith(`/v1/contracts/contracts/lines/${LINE_ID}`, {
      unit_rate: 120,
    });
  });

  it('is removed only after the question is asked', async () => {
    seedReads([line()]);
    api.apiDelete.mockResolvedValue(undefined);
    renderDrawer(contract());

    // Scoped to the row: the drawer carries its own Delete, for the contract.
    const row = await screen.findByTestId(`sov-row-${LINE_ID}`);
    fireEvent.click(within(row).getByRole('button', { name: /^Delete$/i }));
    expect(api.apiDelete).not.toHaveBeenCalled();

    // The question, not the row behind it: both carry a Delete.
    const dialog = await screen.findByRole('alertdialog', { name: /Remove this line/i });
    fireEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
    await waitFor(() => expect(api.apiDelete).toHaveBeenCalledTimes(1));
    expect(api.apiDelete).toHaveBeenCalledWith(`/v1/contracts/contracts/lines/${LINE_ID}`);
  });

  it('is left alone once the contract is signed, and says why', async () => {
    // A claim line is deleted with the SoV line it bills (the foreign key
    // cascades and the server does not refuse it), and a rate rewritten under
    // a certified claim changes what was already paid on.
    seedReads([line()]);
    renderDrawer(contract({ status: 'active' }));

    await screen.findByTestId('sov-lines-locked');
    const row = screen.getByTestId(`sov-row-${LINE_ID}`);
    expect(within(row).queryByRole('button', { name: /^Edit$/i })).toBeNull();
    expect(within(row).queryByRole('button', { name: /^Delete$/i })).toBeNull();
  });
});

describe('the money a new record starts in', () => {
  it('is the contract’s on a new claim, not a guess', async () => {
    api.apiPost.mockResolvedValue({ id: 'claim-1' });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <NewClaimModal
            contracts={[contract({ currency: 'USD' })]}
            defaultContractId={CONTRACT_ID}
            onClose={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect((screen.getByTestId('claim-currency') as HTMLInputElement).value).toBe('USD');
    fireEvent.click(screen.getByRole('button', { name: /Create/i }));
    await waitFor(() => expect(api.apiPost).toHaveBeenCalledTimes(1));
    // The certificate prints the contract's figures; the sign on them has to
    // be the contract's too.
    expect(api.apiPost).toHaveBeenCalledWith(
      '/v1/contracts/progress-claims/',
      expect.objectContaining({ currency: 'USD' }),
    );
  });

  it("is the project's on a new contract", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CreateContractModal projectId="p-1" defaultCurrency="GBP" onClose={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const field = screen
      .getAllByRole('textbox')
      .find((el) => (el as HTMLInputElement).maxLength === 3) as HTMLInputElement;
    expect(field.value).toBe('GBP');
  });
});
