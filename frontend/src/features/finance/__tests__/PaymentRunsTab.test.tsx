// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The payment runs tab.
 *
 * Pins the path an accounting team walks: the run is drawn up for the entity
 * that owns the active project in its currency, a draft can be edited and
 * approved, an approved one is paid only after a confirmation, and the server's
 * findings are shown rather than swallowed, both on the run and when it
 * refuses an action.
 *
 * Run:  npx vitest run src/features/finance/__tests__/PaymentRunsTab.test.tsx
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';
import { PaymentRunsTab } from '../PaymentRunsTab';
import type { PaymentRun } from '../api';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  updateItem: vi.fn(),
  removeItem: vi.fn(),
  approve: vi.fn(),
  execute: vi.fn(),
  cancel: vi.fn(),
  downloadBankFile: vi.fn(),
  listEntities: vi.fn(),
  projectEntity: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => {} },
  useTranslation: () => ({
    t: (_key: string, opts?: Record<string, unknown>) => {
      const text = String(opts?.defaultValue ?? _key);
      return text.replace(/\{\{(\w+)\}\}/g, (_m, name: string) => String(opts?.[name] ?? ''));
    },
    i18n: { language: 'en' },
  }),
}));

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  paymentRunsApi: {
    list: mocks.list,
    get: mocks.get,
    create: mocks.create,
    updateItem: mocks.updateItem,
    removeItem: mocks.removeItem,
    approve: mocks.approve,
    execute: mocks.execute,
    cancel: mocks.cancel,
    downloadBankFile: mocks.downloadBankFile,
  },
}));

vi.mock('@/features/legal-entities/api', () => ({
  legalEntitiesApi: { list: mocks.listEntities, projectEntity: mocks.projectEntity },
}));

const NORTH = { id: 'e-north', code: 'TGC', name: 'North Developments Inc.', functional_currency: 'CAD' };

function makeRun(over: Partial<PaymentRun> = {}): PaymentRun {
  return {
    id: 'run-1',
    run_number: 'PAY-0001',
    legal_entity_id: 'e-north',
    legal_entity_name: 'TGC - North Developments Inc.',
    currency_code: 'CAD',
    payment_date: '2026-10-23',
    due_by: '2026-10-23',
    status: 'draft',
    note: null,
    created_by: 'u1',
    approved_by: null,
    approved_at: null,
    executed_by: null,
    executed_at: null,
    created_at: '2026-10-16T10:00:00',
    total: '1300.00',
    item_count: 2,
    items: [
      {
        id: 'item-a',
        invoice_id: 'inv-a',
        invoice_number: 'AP-0042',
        project_id: 'proj-1',
        project_name: 'Upper Town',
        contact_id: 'c-steel',
        counterparty_name: 'Lakeshore Steel',
        due_date: '2026-10-06',
        amount: '1000.00',
        open_at_proposal: '1000.00',
        payment_id: null,
      },
      {
        id: 'item-b',
        invoice_id: 'inv-b',
        invoice_number: 'AP-0043',
        project_id: 'proj-1',
        project_name: 'Upper Town',
        contact_id: 'c-glass',
        counterparty_name: 'Bayview Glass',
        due_date: '2026-10-11',
        amount: '300.00',
        open_at_proposal: '300.00',
        payment_id: null,
      },
    ],
    issues: [],
    ...over,
  };
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PaymentRunsTab projectId="proj-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(mocks).forEach((fn) => fn.mockReset());
  mocks.listEntities.mockResolvedValue({ items: [NORTH], total: 1 });
  mocks.projectEntity.mockResolvedValue({ project_id: 'proj-1', legal_entity: NORTH, source: 'assigned' });
  mocks.list.mockResolvedValue({ items: [], total: 0 });
});

describe('PaymentRunsTab', () => {
  it("draws up a run for the project's entity in its currency", async () => {
    const run = makeRun();
    mocks.create.mockResolvedValue(run);
    mocks.get.mockResolvedValue(run);
    renderTab();
    await screen.findByText('No payment runs yet');
    await waitFor(() => expect(screen.getByDisplayValue('CAD')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Draw up run' }));
    await waitFor(() =>
      expect(mocks.create).toHaveBeenCalledWith(
        expect.objectContaining({ legal_entity_id: 'e-north', currency_code: 'CAD' }),
      ),
    );
    expect(await screen.findByTestId('payrun-detail')).toBeInTheDocument();
    expect(screen.getByText('Lakeshore Steel')).toBeInTheDocument();
  });

  it('saves an edited amount on a draft and shows the findings it returns', async () => {
    const run = makeRun();
    mocks.list.mockResolvedValue({ items: [run], total: 1 });
    mocks.get.mockResolvedValue(run);
    mocks.updateItem.mockResolvedValue(
      makeRun({
        issues: [
          { severity: 'warning', code: 'same_person', message: 'The person approving this run also drew it up.', item_id: null, invoice_id: null },
        ],
      }),
    );
    renderTab();
    fireEvent.click(await screen.findByRole('button', { name: /PAY-0001/ }));
    const input = await screen.findByLabelText('Amount to pay on AP-0042');
    fireEvent.change(input, { target: { value: '600' } });
    fireEvent.blur(input);
    await waitFor(() => expect(mocks.updateItem).toHaveBeenCalledWith('run-1', 'item-a', '600'));
    expect(await screen.findByText('The person approving this run also drew it up.')).toBeInTheDocument();
  });

  it('will not offer to approve a run the server says is blocked', async () => {
    const run = makeRun({
      issues: [
        { severity: 'error', code: 'amount_over_open', message: 'Invoice AP-0043: 300.00 is more than the 0.00 still open on it.', item_id: 'item-b', invoice_id: 'inv-b' },
      ],
    });
    mocks.list.mockResolvedValue({ items: [run], total: 1 });
    mocks.get.mockResolvedValue(run);
    renderTab();
    fireEvent.click(await screen.findByRole('button', { name: /PAY-0001/ }));
    expect(await screen.findByText(/300\.00 is more than the 0\.00/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve run' })).toBeDisabled();
  });

  it('records the payments of an approved run only after a confirmation', async () => {
    const run = makeRun({ status: 'approved' });
    mocks.list.mockResolvedValue({ items: [run], total: 1 });
    mocks.get.mockResolvedValue(run);
    mocks.execute.mockResolvedValue(makeRun({ status: 'executed' }));
    renderTab();
    fireEvent.click(await screen.findByRole('button', { name: /PAY-0001/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Record payments' }));
    expect(mocks.execute).not.toHaveBeenCalled();
    expect(await screen.findByText('Record these payments?')).toBeInTheDocument();
    const buttons = screen.getAllByRole('button', { name: 'Record payments' });
    fireEvent.click(buttons[buttons.length - 1]!);
    await waitFor(() => expect(mocks.execute).toHaveBeenCalledWith('run-1'));
  });

  it('shows the findings of a refused execute', async () => {
    const run = makeRun({ status: 'approved' });
    mocks.list.mockResolvedValue({ items: [run], total: 1 });
    mocks.get.mockResolvedValue(run);
    mocks.execute.mockRejectedValue(
      new ApiError(422, 'Unprocessable', {
        detail: {
          message: 'Payment run PAY-0001 cannot be paid as it stands.',
          issues: [
            { severity: 'error', code: 'invoice_not_payable', message: 'Invoice AP-0042 is cancelled, so it cannot be paid in a run.', item_id: 'item-a', invoice_id: 'inv-a' },
          ],
        },
      }),
    );
    renderTab();
    fireEvent.click(await screen.findByRole('button', { name: /PAY-0001/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Record payments' }));
    const buttons = await screen.findAllByRole('button', { name: 'Record payments' });
    fireEvent.click(buttons[buttons.length - 1]!);
    expect(await screen.findByText('Invoice AP-0042 is cancelled, so it cannot be paid in a run.')).toBeInTheDocument();
  });

  it('says finance access is missing instead of an empty list', async () => {
    mocks.list.mockRejectedValue(new ApiError(403, 'Forbidden', { detail: 'forbidden' }));
    renderTab();
    expect(await screen.findByText('Finance access required')).toBeInTheDocument();
  });
});
