// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The AR / AP ageing tab.
 *
 * Pins what an accounting team reads first: one card per legal entity,
 * currency and direction, the five buckets of a counterparty line, the
 * invoices behind a line on demand, and filters that reach the server, so
 * "all my projects" and "one legal entity" are asked for rather than
 * filtered in the browser.
 *
 * Run:  npx vitest run src/features/finance/__tests__/AgeingTab.test.tsx
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';
import { AgeingTab } from '../AgeingTab';
import type { AgeingReport, AgeingRollup } from '../api';

const mocks = vi.hoisted(() => ({
  getAgeing: vi.fn(),
  listEntities: vi.fn(),
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
  getAgeing: mocks.getAgeing,
}));

vi.mock('@/features/legal-entities/api', () => ({
  legalEntitiesApi: { list: mocks.listEntities },
}));

const ZERO_BUCKETS = { current: '0.00', '1_30': '0.00', '31_60': '0.00', '61_90': '0.00', over_90: '0.00' };

function rollup(over: Partial<AgeingRollup>): AgeingRollup {
  return {
    legal_entity_id: 'e-north',
    legal_entity_name: 'North Developments Inc.',
    currency_code: 'CAD',
    direction: 'payable',
    contact_id: null,
    counterparty_name: null,
    buckets: { ...ZERO_BUCKETS },
    total_due: '0.00',
    credit: '0.00',
    retention_held: '0.00',
    retention_released: '0.00',
    invoice_count: 0,
    oldest_days_past_due: 0,
    invoices: [],
    ...over,
  };
}

const REPORT: AgeingReport = {
  as_of: '2026-10-15',
  buckets: ['current', '1_30', '31_60', '61_90', 'over_90'],
  drafts_excluded: 2,
  totals: [
    rollup({
      buckets: { ...ZERO_BUCKETS, '31_60': '600.00', current: '1800.00' },
      total_due: '2400.00',
      retention_held: '200.00',
      invoice_count: 2,
    }),
    rollup({
      legal_entity_id: 'e-south',
      legal_entity_name: 'South Homes Ltd.',
      direction: 'receivable',
      buckets: { ...ZERO_BUCKETS, over_90: '500.00' },
      total_due: '500.00',
      invoice_count: 1,
    }),
  ],
  groups: [
    rollup({
      contact_id: 'c-steel',
      counterparty_name: 'Lakeshore Steel',
      buckets: { ...ZERO_BUCKETS, '31_60': '600.00' },
      total_due: '600.00',
      invoice_count: 1,
      oldest_days_past_due: 45,
      invoices: [
        {
          invoice_id: 'inv-1',
          invoice_number: 'AP-0042',
          project_id: 'proj-1',
          invoice_date: '2026-07-31',
          due_date: '2026-08-31',
          days_past_due: 45,
          bucket: '31_60',
          total: '1000.00',
          paid: '400.00',
          due: '600.00',
          credit: '0.00',
          retention_held: '0.00',
          retention_released: '0.00',
        },
      ],
    }),
  ],
};

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AgeingTab projectId="proj-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.getAgeing.mockReset().mockResolvedValue(REPORT);
  mocks.listEntities.mockReset().mockResolvedValue({
    items: [
      { id: 'e-north', code: 'TGC', name: 'North Developments Inc.' },
      { id: 'e-south', code: 'TUH', name: 'South Homes Ltd.' },
    ],
    total: 2,
  });
});

describe('AgeingTab', () => {
  it('shows one total per legal entity and direction, with retention apart', async () => {
    renderTab();
    expect(await screen.findByText('Lakeshore Steel')).toBeInTheDocument();
    expect(screen.getAllByText('North Developments Inc.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('South Homes Ltd.').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Payable (AP)').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Receivable (AR)').length).toBeGreaterThan(0);
    expect(screen.getByText(/Retention held/)).toBeInTheDocument();
    expect(screen.getByText('Drafts not counted until approved: 2')).toBeInTheDocument();
  });

  it('asks for this project first, then for every project the reader can open', async () => {
    renderTab();
    await screen.findByText('Lakeshore Steel');
    expect(mocks.getAgeing).toHaveBeenLastCalledWith(expect.objectContaining({ projectId: 'proj-1' }));

    fireEvent.change(screen.getByDisplayValue('This project'), { target: { value: 'all' } });
    await waitFor(() =>
      expect(mocks.getAgeing).toHaveBeenLastCalledWith(expect.objectContaining({ projectId: undefined })),
    );
  });

  it('sends the legal entity and direction to the server', async () => {
    renderTab();
    await screen.findByText('Lakeshore Steel');
    fireEvent.change(await screen.findByDisplayValue('All entities'), { target: { value: 'e-south' } });
    fireEvent.change(screen.getByDisplayValue('AR and AP'), { target: { value: 'receivable' } });
    await waitFor(() =>
      expect(mocks.getAgeing).toHaveBeenLastCalledWith(
        expect.objectContaining({ legalEntityId: 'e-south', direction: 'receivable' }),
      ),
    );
  });

  it('opens a counterparty line onto its invoices', async () => {
    renderTab();
    const line = await screen.findByRole('button', { name: /Lakeshore Steel/ });
    expect(screen.queryByText('AP-0042')).not.toBeInTheDocument();
    fireEvent.click(line);
    expect(screen.getByText('AP-0042')).toBeInTheDocument();
    expect(line).toHaveAttribute('aria-expanded', 'true');
  });

  it('says finance access is missing instead of showing an empty report', async () => {
    mocks.getAgeing.mockReset().mockRejectedValue(new ApiError(403, 'Forbidden', { detail: 'forbidden' }));
    renderTab();
    expect(await screen.findByText('Finance access required')).toBeInTheDocument();
  });

  it('hides the entity filter when the workspace has no legal entities', async () => {
    mocks.listEntities.mockReset().mockResolvedValue({ items: [], total: 0 });
    renderTab();
    await screen.findByText('Lakeshore Steel');
    expect(screen.queryByDisplayValue('All entities')).not.toBeInTheDocument();
  });
});
