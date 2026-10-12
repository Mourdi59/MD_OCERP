// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The logistics plan as a reader meets it: what an empty plan says, what a
// filled one shows, what a form sends, and how a refusal by the server reads.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ id }: { id?: string }) => <input id={id} readOnly />,
}));
vi.mock('../../api', () => ({
  fetchGates: vi.fn(async () => [{ id: 'g1', name: 'North gate' }]),
  updateGate: vi.fn(async () => ({})),
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  const names = [
    'getCatalogue',
    'listCatalogueChoices',
    'pinCatalogue',
    'listStages',
    'listAreas',
    'getBalance',
    'putAllocations',
    'listMedia',
    'listDemands',
    'getConcept',
    'putConcept',
    'listTransports',
    'listPermits',
    'listCustoms',
    'listLines',
    'listDocuments',
    'getNeighbourhood',
    'putNeighbourhood',
    'listComplaints',
    'listCoordination',
    'getReadiness',
    'runSweep',
    'exportRegister',
    'createItem',
    'updateItem',
    'deleteItem',
    'transitionItem',
  ];
  return { ...actual, ...Object.fromEntries(names.map((n) => [n, vi.fn()])) };
});

import { ApiError } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import * as api from '../api';
import * as siteApi from '../../api';
import { GateLimits } from '../GateLimits';
import { LogisticsPlan, type PlanTab } from '../LogisticsPlan';
import {
  area,
  catalogue,
  craneDemand,
  heavyTransport,
  hiddenCase,
  media,
  notReady,
  officeDemand,
  openBalance,
  overdueComplaint,
  page,
  permit,
  stage,
} from './fixtures';

const mocked = vi.mocked(api);

function renderPlan(initialTab: PlanTab = 'balance') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LogisticsPlan projectId="p1" initialTab={initialTab} />
    </QueryClientProvider>,
  );
}

function refusal(status: number, code: string, message: string, violations?: { code: string }[]) {
  return new ApiError(status, 'Refused', {
    detail: { code, message_key: `site_logistics.errors.${code}`, message, violations },
  });
}

beforeEach(() => {
  vi.resetAllMocks();
  useToastStore.setState({ toasts: [] });
  mocked.getCatalogue.mockResolvedValue(catalogue);
  mocked.listStages.mockResolvedValue(page([stage]));
  mocked.listAreas.mockResolvedValue(page([area]));
  mocked.getBalance.mockResolvedValue(page([openBalance]));
  mocked.listMedia.mockResolvedValue(page([media]));
  mocked.listDemands.mockResolvedValue(page([craneDemand, officeDemand]));
  mocked.listTransports.mockResolvedValue(page([heavyTransport]));
  mocked.listPermits.mockResolvedValue(page([permit]));
  mocked.listCustoms.mockResolvedValue(page([hiddenCase]));
  mocked.listLines.mockResolvedValue(page([]));
  mocked.listDocuments.mockResolvedValue(page([]));
  mocked.getNeighbourhood.mockResolvedValue(null);
  mocked.listComplaints.mockResolvedValue(page([overdueComplaint]));
  mocked.listCoordination.mockResolvedValue(page([]));
  mocked.getReadiness.mockResolvedValue(notReady);
  mocked.getConcept.mockResolvedValue({
    id: 'k1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    strategy: [],
    delivery_open: null,
    delivery_close: null,
    max_deliveries_per_hour: null,
    rules_text: '',
    document_ref: '',
    updated_at: null,
  });
});
afterEach(cleanup);

describe('area balance', () => {
  it('says by how much a stage is open, what is missing and which utility is short', async () => {
    renderPlan();
    const card = await screen.findByTestId('plan-balance-stage');
    expect(within(card).getByTestId('plan-balance-verdict')).toHaveTextContent('Balance open by 800 m2');
    expect(within(card).getByText('Stage Shell works has no site setup area.')).toBeInTheDocument();
    expect(within(card).getByTestId('plan-balance-media')).toHaveTextContent('Power');
    expect(within(card).getByTestId('plan-balance-media')).toHaveTextContent('Capacity too low');
  });

  it('an empty plan says what the balance is for and leads to the areas', async () => {
    mocked.getBalance.mockResolvedValue(
      page([{ ...openBalance, area: { ...openBalance.area, site_total_m2: '0', counted_m2: '0' }, gaps: [], media: [] }]),
    );
    mocked.listAreas.mockResolvedValue(page([]));
    renderPlan();
    expect(await screen.findByText('Nothing to balance yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add area' }));
    expect(await screen.findByText('No site areas yet')).toBeInTheDocument();
  });

  it('a failed request shows the error with a retry, not an empty plan', async () => {
    mocked.getBalance.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPlan();
    expect(await screen.findByText('This part of the logistics plan could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('database unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Nothing to balance yet')).toBeNull();
    mocked.getBalance.mockResolvedValue(page([openBalance]));
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByTestId('plan-balance-stage')).toBeInTheDocument();
  });
});

describe('stages and areas', () => {
  it('a new stage is not sent while a required field is empty', async () => {
    renderPlan('stages');
    await screen.findByTestId('plan-stage');
    fireEvent.click(screen.getByTestId('plan-add_stage'));
    fireEvent.click(screen.getByTestId('plan-form-save'));
    expect(await screen.findAllByText('Required')).toHaveLength(2);
    expect(mocked.createItem).not.toHaveBeenCalled();
  });

  it('a new stage sends what was typed and nothing else', async () => {
    mocked.createItem.mockResolvedValue({});
    renderPlan('stages');
    await screen.findByTestId('plan-stage');
    fireEvent.click(screen.getByTestId('plan-add_stage'));
    fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Fit-out' } });
    fireEvent.change(screen.getByLabelText('Short code'), { target: { value: 'fit_out' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() =>
      expect(mocked.createItem).toHaveBeenCalledWith('p1', 'stage', { title: 'Fit-out', code: 'fit_out' }, undefined),
    );
    await waitFor(() => expect(screen.queryByTestId('plan-form-save')).toBeNull());
  });

  it('a stage offers the move the server allows next', async () => {
    mocked.transitionItem.mockResolvedValue({});
    renderPlan('stages');
    fireEvent.click(await screen.findByRole('button', { name: 'Start stage' }));
    await waitFor(() => expect(mocked.transitionItem).toHaveBeenCalledWith('p1', 'stage', 's1', 'active'));
  });

  it('an area shows its allocation per stage, and saving replaces the whole list', async () => {
    mocked.putAllocations.mockResolvedValue({});
    renderPlan('areas');
    const card = await screen.findByTestId('plan-area');
    expect(card).toHaveTextContent('North store');
    expect(card).toHaveTextContent('Shell works');
    expect(card).toHaveTextContent('800 m2');
    fireEvent.click(within(card).getByTestId('plan-allocate'));
    fireEvent.change(screen.getByLabelText('Allocated m2'), { target: { value: '950,5' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() =>
      expect(mocked.putAllocations).toHaveBeenCalledWith('p1', 'a1', [
        { stage_id: 's1', area_kind: 'storage', allocated_m2: '950.5', use_note: 'Rebar' },
      ]),
    );
  });
});

describe('utilities', () => {
  it('a demand that comes from a plant position is shown but not changed here', async () => {
    renderPlan('media');
    const rows = await screen.findAllByTestId('plan-demand');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByTestId('plan-demand-from-plant')).toHaveTextContent('From a plant position');
    expect(within(rows[0]!).queryByRole('button', { name: 'Edit' })).toBeNull();
    expect(within(rows[0]!).queryByRole('button', { name: 'Delete' })).toBeNull();
    expect(within(rows[1]!).getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('a new demand is created under its connection', async () => {
    mocked.createItem.mockResolvedValue({});
    renderPlan('media');
    await screen.findAllByTestId('plan-demand');
    fireEvent.click(screen.getByTestId('plan-add-demand'));
    fireEvent.change(screen.getByLabelText('Consumer'), { target: { value: 'Concrete pump' } });
    fireEvent.change(screen.getByLabelText('Stage'), { target: { value: 's1' } });
    fireEvent.change(screen.getByLabelText('Peak demand'), { target: { value: '45' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() =>
      expect(mocked.createItem).toHaveBeenCalledWith(
        'p1',
        'demand',
        { consumer: 'Concrete pump', stage_id: 's1', peak_demand: '45' },
        'm1',
      ),
    );
  });
});

describe('transports and permits', () => {
  it('a heavy transport without a permit says so on its card', async () => {
    renderPlan('transports');
    const card = await screen.findByTestId('plan-transport');
    expect(within(card).getByTestId('plan-transport-heavy')).toHaveTextContent('Heavy transport');
    expect(within(card).getByTestId('plan-transport-blockers')).toHaveTextContent(
      'Heavy transport without a granted permit.',
    );
    expect(card).toHaveTextContent('No permit linked');
  });

  it("a refused scheduling shows the server's reason and every blocker", async () => {
    mocked.transitionItem.mockRejectedValue(
      refusal(422, 'heavy_without_permit', 'A heavy transport needs a granted permit.', [
        { code: 'heavy_without_permit' },
        { code: 'quiet_hours_conflict' },
      ]),
    );
    renderPlan('transports');
    fireEvent.click(await screen.findByRole('button', { name: 'Schedule' }));
    await waitFor(() => expect(useToastStore.getState().toasts).toHaveLength(1));
    const toast = useToastStore.getState().toasts[0]!;
    expect(toast.title).toBe('A heavy transport needs a granted permit.');
    expect(toast.message).toContain('Heavy transport without a granted permit.');
    expect(toast.message).toContain('The time window falls in the quiet hours.');
  });

  it('a change sends only the changed field, and a refusal stays in the dialog', async () => {
    mocked.updateItem.mockRejectedValue(refusal(409, 'transport_under_way', 'The transport is already under way.'));
    renderPlan('transports');
    const card = await screen.findByTestId('plan-transport');
    fireEvent.click(within(card).getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Gross weight (t)'), { target: { value: '70' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() => expect(mocked.updateItem).toHaveBeenCalledWith('p1', 'transport', 't1', { gross_weight_t: '70' }));
    expect(await screen.findByTestId('plan-form-problem')).toHaveTextContent('The transport is already under way.');
    expect(screen.getByTestId('plan-form-save')).toBeInTheDocument();
  });

  it('a permit lists its time windows by weekday', async () => {
    renderPlan('permits');
    const card = await screen.findByTestId('plan-permit');
    expect(card).toHaveTextContent('Oversize permit');
    expect(card).toHaveTextContent('OS-2026-044');
    expect(card).toHaveTextContent('22:00 to 05:00');
    expect(card).toHaveTextContent('Mon');
    expect(within(card).getByRole('button', { name: 'Mark as granted' })).toBeInTheDocument();
  });
});

describe('customs', () => {
  it('a reader without the customs permission is told why there are no values, and cannot enter one', async () => {
    renderPlan('customs');
    await screen.findByTestId('plan-customs-case');
    expect(screen.getByTestId('plan-values-hidden')).toHaveTextContent(
      'Values are visible to users with the customs permission.',
    );
    fireEvent.click(screen.getByTestId('plan-add_customs'));
    expect(screen.getByLabelText('Incoterm')).toBeInTheDocument();
    expect(screen.queryByLabelText('Customs value')).toBeNull();
  });

  it('opening a case shows its goods lines and documents with what to do first', async () => {
    renderPlan('customs');
    fireEvent.click(await screen.findByTestId('plan-customs-toggle'));
    expect(await screen.findByText('No goods lines yet. Add one line per commodity code.')).toBeInTheDocument();
    expect(screen.getByText('No documents listed yet.')).toBeInTheDocument();
    expect(mocked.listLines).toHaveBeenCalledWith('p1', 'c1');
  });
});

describe('neighbourhood', () => {
  it('an empty plan says what to set, an overdue complaint stands out and can be acknowledged', async () => {
    mocked.transitionItem.mockResolvedValue({});
    renderPlan('neighbourhood');
    expect(await screen.findByText('Neighbourhood plan not filled in')).toBeInTheDocument();
    const card = await screen.findByTestId('plan-complaint');
    expect(within(card).getByTestId('plan-complaint-overdue')).toHaveTextContent('Answer overdue');
    expect(card).toHaveTextContent('Noise');
    fireEvent.click(within(card).getByRole('button', { name: 'Acknowledge' }));
    await waitFor(() => expect(mocked.transitionItem).toHaveBeenCalledWith('p1', 'complaint', 'n1', 'acknowledged'));
    expect(screen.getByText('No coordination logged')).toBeInTheDocument();
  });

  it('quiet hours are sent as one pair', async () => {
    mocked.putNeighbourhood.mockResolvedValue({} as never);
    renderPlan('neighbourhood');
    fireEvent.click(await screen.findByRole('button', { name: 'Fill in the neighbourhood plan' }));
    fireEvent.change(screen.getByLabelText('Zone type'), { target: { value: 'residential' } });
    fireEvent.change(screen.getByLabelText('Quiet hours from'), { target: { value: '20:00' } });
    fireEvent.change(screen.getByLabelText('Quiet hours until'), { target: { value: '07:00' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() =>
      expect(mocked.putNeighbourhood).toHaveBeenCalledWith('p1', {
        zone_type: 'residential',
        quiet_hours: ['20:00', '07:00'],
      }),
    );
  });
});

describe('site entrance limits', () => {
  const gate = {
    id: 'g1',
    project_id: 'p1',
    name: 'North gate',
    open_time: '06:00',
    close_time: '18:00',
    capacity_per_slot: 2,
    notes: null,
    created_by: null,
    metadata: {},
    created_at: '',
    updated_at: '',
  };
  const renderLimits = (extra: object, canEdit = true) =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GateLimits gate={{ ...gate, ...extra }} canEdit={canEdit} />
      </QueryClientProvider>,
    );

  it('an entrance without limits says that transports cannot be checked, and takes limits', async () => {
    renderLimits({});
    expect(screen.getByTestId('gate-limits-none')).toHaveTextContent('No limits entered yet');
    fireEvent.click(screen.getByTestId('gate-limits-edit'));
    fireEvent.change(screen.getByLabelText('Max gross weight (t)'), { target: { value: '40' } });
    fireEvent.click(screen.getByTestId('plan-form-save'));
    await waitFor(() => expect(vi.mocked(siteApi.updateGate)).toHaveBeenCalledWith('g1', { max_gross_t: '40' }));
  });

  it('shows the limits it has, and no edit for a reader who may not change gates', () => {
    renderLimits({ max_gross_t: '40.00', max_height_m: '4.00', access_kind: 'road_gate' }, false);
    const block = screen.getByTestId('gate-limits');
    expect(block).toHaveTextContent('Road gate');
    expect(block).toHaveTextContent('Max gross weight (t)');
    expect(block).toHaveTextContent('40');
    expect(screen.queryByTestId('gate-limits-edit')).toBeNull();
    expect(screen.queryByTestId('gate-limits-none')).toBeNull();
  });
});

describe('gate readiness', () => {
  it('shows the verdict, each check and every finding as a sentence', async () => {
    renderPlan('readiness');
    const verdict = await screen.findByTestId('plan-ready-verdict');
    expect(verdict).toHaveTextContent('Not ready for the gate yet');
    const items = screen.getAllByTestId('plan-ready-item');
    expect(items[0]).toHaveTextContent('No open logistics errors');
    expect(items[0]).toHaveAttribute('data-state', 'not_met');
    expect(items[1]).toHaveAttribute('data-state', 'met');
    const findings = screen.getAllByTestId('plan-finding');
    expect(findings[0]).toHaveTextContent('Roof girder: heavy transport without a granted permit.');
    expect(findings[1]).toHaveTextContent('Laydown zone Zone B is not linked to a site area.');
    expect(await screen.findByTestId('plan-catalogue-unconfirmed')).toBeInTheDocument();
  });

  it('the sweep reports what it changed, and each register can be exported', async () => {
    mocked.runSweep.mockResolvedValue({ permits: { expired: 1, expiring: 2 }, complaints_overdue: 1, transports_arrived: 0 });
    mocked.exportRegister.mockResolvedValue();
    renderPlan('readiness');
    fireEvent.click(await screen.findByTestId('plan-sweep'));
    await waitFor(() => expect(useToastStore.getState().toasts).toHaveLength(1));
    expect(useToastStore.getState().toasts[0]!.message).toBe(
      'Permits flagged: 3. Complaints overdue: 1. Transports marked arrived: 0.',
    );
    fireEvent.click(screen.getByTestId('plan-export-transports-xlsx'));
    await waitFor(() => expect(mocked.exportRegister).toHaveBeenCalledWith('p1', 'transports', 'xlsx'));
  });
});
