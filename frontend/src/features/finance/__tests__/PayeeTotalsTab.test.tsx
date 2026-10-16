// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The supplier payments tab, read for a yearly payee return such as the T5018.
 *
 * Pins what the accounting team files from: the entity that owns the active
 * project and last calendar year are asked for, the return is named with its
 * due date, payees without a business number are flagged, payees below the
 * threshold are kept out of the list until asked for, and the CSV is the same
 * query.
 *
 * Run:  npx vitest run src/features/finance/__tests__/PayeeTotalsTab.test.tsx
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { PayeeTotalsTab } from '../PayeeTotalsTab';
import type { PayeeTotal, PayeeTotalsReport } from '../api';

const mocks = vi.hoisted(() => ({
  getPayeeTotals: vi.fn(),
  downloadPayeeTotalsCsv: vi.fn(),
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
  getPayeeTotals: mocks.getPayeeTotals,
  downloadPayeeTotalsCsv: mocks.downloadPayeeTotalsCsv,
}));

vi.mock('@/features/legal-entities/api', () => ({
  legalEntitiesApi: { list: mocks.listEntities, projectEntity: mocks.projectEntity },
}));

const NORTH = { id: 'e-north', code: 'TGC', name: 'North Developments Inc.', functional_currency: 'CAD' };
const SOUTH = { id: 'e-south', code: 'TUH', name: 'South Homes Ltd.', functional_currency: 'CAD' };
const YEAR = new Date().getFullYear() - 1;

function payee(over: Partial<PayeeTotal>): PayeeTotal {
  return {
    contact_id: 'c-steel',
    payee_name: 'Lakeshore Steel',
    payee_tax_id: '987654321RT0001',
    payee_address: '1 King St W, M5H 1A1, Toronto',
    payee_country_code: 'CA',
    currency_code: 'CAD',
    total: '8500.00',
    paid: '8500.00',
    refunded: '0.00',
    payment_count: 2,
    invoice_count: 2,
    project_count: 2,
    below_threshold: false,
    ...over,
  };
}

const REPORT: PayeeTotalsReport = {
  legal_entity_id: 'e-north',
  legal_entity_name: 'TGC - North Developments Inc.',
  legal_entity_tax_id: '123456789RT0001',
  country_code: 'CA',
  date_from: `${YEAR}-01-01`,
  date_to: `${YEAR}-12-31`,
  payee_return: {
    form: 'T5018',
    name: 'Statement of Contract Payments',
    threshold: '500',
    currency: 'CAD',
    reference: 'Income Tax Regulations, C.R.C., c. 945, s. 238',
    due_on: `${YEAR + 1}-06-30`,
    note: 'note',
  },
  items: [
    payee({}),
    payee({ contact_id: 'c-dry', payee_name: 'Drywall Co', payee_tax_id: null, total: '900.00' }),
    payee({ contact_id: 'c-small', payee_name: 'Small Fix', total: '300.00', below_threshold: true }),
  ],
  reportable_count: 2,
  missing_tax_id: 1,
};

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PayeeTotalsTab projectId="proj-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.getPayeeTotals.mockReset().mockResolvedValue(REPORT);
  mocks.downloadPayeeTotalsCsv.mockReset().mockResolvedValue(undefined);
  mocks.listEntities.mockReset().mockResolvedValue({ items: [NORTH, SOUTH], total: 2 });
  mocks.projectEntity.mockReset().mockResolvedValue({ project_id: 'proj-1', legal_entity: SOUTH });
});

describe('PayeeTotalsTab', () => {
  it('asks for the entity of the active project and last calendar year', async () => {
    renderTab();
    await screen.findByText('Lakeshore Steel');
    expect(mocks.getPayeeTotals).toHaveBeenLastCalledWith({
      legalEntityId: 'e-south',
      dateFrom: `${YEAR}-01-01`,
      dateTo: `${YEAR}-12-31`,
    });
  });

  it('names the return, flags a missing business number and keeps small payees out until asked', async () => {
    renderTab();
    expect(await screen.findByTestId('payee-return')).toHaveTextContent('T5018');
    expect(screen.getByText(/Payees without a tax or business number on their contact: 1/)).toBeInTheDocument();
    expect(screen.getByText('missing')).toBeInTheDocument();
    expect(screen.queryByText('Small Fix')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show payees below the threshold (1)' }));
    expect(screen.getByText('Small Fix')).toBeInTheDocument();
    expect(screen.getByText('Below the threshold')).toBeInTheDocument();
  });

  it('asks again for another entity and downloads the same query as CSV', async () => {
    renderTab();
    await screen.findByText('Lakeshore Steel');
    fireEvent.change(screen.getByDisplayValue('TUH · South Homes Ltd.'), { target: { value: 'e-north' } });
    await waitFor(() =>
      expect(mocks.getPayeeTotals).toHaveBeenLastCalledWith(expect.objectContaining({ legalEntityId: 'e-north' })),
    );
    await screen.findByText('Lakeshore Steel');
    fireEvent.click(screen.getByRole('button', { name: /Download CSV/ }));
    await waitFor(() =>
      expect(mocks.downloadPayeeTotalsCsv).toHaveBeenCalledWith(
        expect.objectContaining({ legalEntityId: 'e-north' }),
        `T5018_${YEAR}-01-01_${YEAR}-12-31.csv`,
      ),
    );
  });

  it('does not ask for a period that ends before it starts', async () => {
    renderTab();
    await screen.findByText('Lakeshore Steel');
    mocks.getPayeeTotals.mockClear();
    fireEvent.change(screen.getByDisplayValue(`${YEAR}-01-01`), { target: { value: `${YEAR + 1}-02-01` } });
    expect(await screen.findByText('The period has to start on or before the day it ends.')).toBeInTheDocument();
    expect(mocks.getPayeeTotals).not.toHaveBeenCalled();
  });

  it('explains that entities come first when there are none', async () => {
    mocks.listEntities.mockReset().mockResolvedValue({ items: [], total: 0 });
    mocks.projectEntity.mockReset().mockResolvedValue({ project_id: 'proj-1', legal_entity: null });
    renderTab();
    expect(await screen.findByText('No legal entity yet')).toBeInTheDocument();
    expect(mocks.getPayeeTotals).not.toHaveBeenCalled();
  });
});
