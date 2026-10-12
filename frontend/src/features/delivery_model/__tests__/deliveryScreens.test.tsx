// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The delivery model screens as a reader meets them: the comparison shows
// which form leads and what is still missing, a proposal is not sent without
// a reason, the risk matrix tells an unconfirmed row from a confirmed one, a
// shared risk must add up to 100, the package plan says where it does not fit
// the form, and a disabled button says why.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('../linkTargets', () => ({ fetchLinkTargets: vi.fn() }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    closeReopening: vi.fn(),
    proposeDecision: vi.fn(),
    putScores: vi.fn(),
    patchWeights: vi.fn(),
    confirmAllocations: vi.fn(),
    putAllocation: vi.fn(),
    setOfiStatus: vi.fn(),
    linkPackage: vi.fn(),
    withdrawDecision: vi.fn(),
  };
});

import { ApiError } from '@/shared/lib/api';

import * as api from '../api';
import { ProposeDialog } from '../ComparisonDialogs';
import { ComparisonPanel } from '../ComparisonPanel';
import { DecisionRecordPanel } from '../DecisionRecordPanel';
import { FindingList, ReasonedButton, ReviewMark } from '../DeliveryBits';
import type { LabelContext } from '../labels';
import * as linkTargets from '../linkTargets';
import { OfiPanel } from '../OfiPanel';
import { LinkPackageDialog, PackagePlanPanel } from '../PackagePlanPanel';
import { AllocationDialog, RiskMatrixPanel } from '../RiskMatrixPanel';
import { allocation, allocationItem, catalogue, comparison, decision, matrix, model, ofi, option, pkg } from './fixtures';
import { enExists, enT } from './i18nMock';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT, language: 'en', exists: enExists };
const noop = () => undefined;

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe('ComparisonPanel', () => {
  const props = { projectId: 'p1', catalogue: catalogue(), packages: [], labels, onChanged: noop };

  it('shows the forms, their weighted totals and which one leads', () => {
    wrap(<ComparisonPanel {...props} model={model()} comparison={comparison()} />);
    const columns = screen.getAllByTestId('option-column');
    expect(columns).toHaveLength(2);
    expect(columns[0]).toHaveTextContent('Single main contractor');
    expect(columns[1]).toHaveTextContent('Design and build');
    expect(within(columns[1]!).getByTestId('leading-option')).toHaveTextContent('Highest score');
    expect(within(columns[0]!).queryByTestId('leading-option')).toBeNull();
    expect(screen.getAllByTestId('option-total').map((n) => n.textContent)).toEqual(['3.40', '4.20']);
    expect(screen.getByTestId('weights-total')).toHaveTextContent('100');
    // a criterion the catalogue does not name is written out, never shown as a key
    expect(screen.getAllByTestId('criterion-row')[1]).toHaveTextContent('Schedule');
    expect(screen.queryByTestId('comparison-open-points')).toBeNull();
  });

  it('lists what still stops a proposal', () => {
    const c = comparison({ options: [option('o1', 'design_build', null)], scores: [], weights_total: '90' });
    wrap(<ComparisonPanel {...props} model={model()} comparison={c} />);
    const open = within(screen.getByTestId('comparison-open-points')).getAllByRole('listitem');
    expect(open.map((n) => n.textContent)).toEqual([
      'A decision needs at least two compared forms.',
      'Criterion weights must add up to 100.',
      'Every option needs a score on every criterion.',
    ]);
    expect(screen.getByTestId('option-total')).toHaveTextContent('Not fully scored');
    expect(screen.getByTestId('prefill-button')).toBeInTheDocument();
  });

  it('shows the weight total turning wrong while the reader types, before anything is saved', () => {
    wrap(<ComparisonPanel {...props} model={model()} comparison={comparison()} />);
    expect(screen.queryByTestId('weights-save-bar')).toBeNull();
    fireEvent.change(screen.getByLabelText('Weight of Schedule'), { target: { value: '30' } });
    expect(screen.getByTestId('weights-total')).toHaveTextContent('90');
    expect(screen.getByTestId('weights-problem')).toHaveTextContent('Criterion weights must add up to 100.');
    expect(mocked.patchWeights).not.toHaveBeenCalled();
  });

  it('saves one score with the rationale that cell already had', async () => {
    mocked.putScores.mockResolvedValue(comparison());
    wrap(<ComparisonPanel {...props} model={model()} comparison={comparison()} />);
    fireEvent.change(screen.getByLabelText('Score of Design and build on Cost certainty at award'), { target: { value: '4' } });
    await waitFor(() => expect(mocked.putScores).toHaveBeenCalled());
    expect(mocked.putScores).toHaveBeenCalledWith('p1', [
      { option_id: 'o2', criterion_code: 'cost_certainty_at_award', score: 4, rationale: 'fixed price' },
    ]);
  });

  it('is read-only while a decision waits for the gate, and says so', () => {
    wrap(<ComparisonPanel {...props} model={model({ status: 'proposed', selected_form_code: 'design_build' })} comparison={comparison()} />);
    expect(screen.getByTestId('propose-button')).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'decision_pending');
    expect(screen.queryByTestId('add-form-button')).toBeNull();
    expect(screen.getAllByTestId('score-cell').every((n) => (n as HTMLSelectElement).disabled)).toBe(true);
    expect(screen.getByTestId('chosen-option')).toHaveTextContent('Chosen');
  });

  it('a project without a frame document for the decision cannot propose, and the button says which step is missing', () => {
    const noCarrier = model();
    noCarrier.can.propose = { allowed: false, reason: 'governance_model_missing' };
    wrap(<ComparisonPanel {...props} model={noCarrier} comparison={comparison()} />);
    expect(screen.getByTestId('propose-button')).toBeDisabled();
    expect(screen.getByTestId('add-form-button')).toBeEnabled();
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('governance model first');
  });

  it('marks a form the project adjusted', () => {
    const c = comparison();
    c.options[1] = option('o2', 'design_build', '4.20', { customised: ['price_basis_at_award'] });
    wrap(<ComparisonPanel {...props} model={model()} comparison={c} />);
    expect(screen.getAllByTestId('customised-option')).toHaveLength(1);
  });

  it('a viewer sees the comparison but no way to change it', () => {
    wrap(<ComparisonPanel {...props} model={model({}, 'viewer')} comparison={comparison()} />);
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'permission_missing');
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('You do not have the permission for this.');
    expect(screen.queryByTestId('add-form-button')).toBeNull();
  });

  it('an empty comparison says what to do first', () => {
    wrap(<ComparisonPanel {...props} model={model({ status: 'draft' })} comparison={comparison({ options: [], scores: [] })} />);
    expect(screen.getByText('No forms to compare yet')).toBeInTheDocument();
    expect(screen.getByTestId('add-form-button')).toBeEnabled();
  });
});

describe('ProposeDialog', () => {
  const base = { open: true, onClose: noop, projectId: 'p1', labels, onDone: noop };

  it('preselects the leading form and will not send without a reason', () => {
    wrap(<ProposeDialog {...base} comparison={comparison()} packages={[]} />);
    const options = screen.getAllByTestId('propose-option');
    expect(within(options[1]!).getByRole('radio')).toBeChecked();
    fireEvent.click(screen.getByTestId('propose-send'));
    expect(screen.getByTestId('propose-problems')).toHaveTextContent('A decision needs a rationale.');
    expect(mocked.proposeDecision).not.toHaveBeenCalled();
  });

  it('sends the chosen option with the trimmed reason', async () => {
    mocked.proposeDecision.mockResolvedValue(decision());
    const onDone = vi.fn();
    wrap(<ProposeDialog {...base} onDone={onDone} comparison={comparison()} packages={[]} />);
    fireEvent.click(within(screen.getAllByTestId('propose-option')[0]!).getByRole('radio'));
    fireEvent.change(screen.getByTestId('propose-rationale'), { target: { value: '  Keeps design control.  ' } });
    fireEvent.click(screen.getByTestId('propose-send'));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(mocked.proposeDecision).toHaveBeenCalledWith('p1', { option_id: 'o1', rationale: 'Keeps design control.', dispositions: {} });
  });

  it('asks what happens to each package the change affects, then sends the answers', async () => {
    mocked.proposeDecision.mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable', {
        detail: {
          code: 'form_change_impacts_packages',
          message: 'Packages already in procurement or awarded need a disposition before the form can change.',
          violations: [{ code: 'disposition_missing', severity: 'error', ref: 'SHELL', effective_status: 'awarded' }],
        },
      }),
    );
    mocked.proposeDecision.mockResolvedValueOnce(decision());
    const packages = [pkg('shell', { title: 'Shell and core', effective_status: 'awarded' }), pkg('fitout')];
    wrap(<ProposeDialog {...base} comparison={comparison()} packages={packages} />);
    fireEvent.change(screen.getByTestId('propose-rationale'), { target: { value: 'Fixed price.' } });
    fireEvent.click(screen.getByTestId('propose-send'));

    const block = await screen.findByTestId('propose-dispositions');
    expect(screen.getByTestId('server-refusal')).toHaveTextContent('need a disposition');
    expect(block).toHaveTextContent('Shell and core');
    expect(block).toHaveTextContent('Awarded');
    expect(block).not.toHaveTextContent('Package fitout');

    fireEvent.change(screen.getByLabelText('What happens to Shell and core'), { target: { value: 're_scope' } });
    fireEvent.click(screen.getByTestId('propose-send'));
    await waitFor(() => expect(mocked.proposeDecision).toHaveBeenCalledTimes(2));
    expect(mocked.proposeDecision.mock.calls[1]![1].dispositions).toEqual({ shell: 're_scope' });
  });
});

describe('RiskMatrixPanel', () => {
  const items = [
    allocationItem('design_errors', { allocation: allocation('design_errors', { risk_item_ids: ['r1'] }) }),
    allocationItem('ground_conditions', {
      allocation: allocation('ground_conditions', {
        party: 'shared',
        basis: 'ground_baseline',
        shares: { owner: '60', contractor: '40' },
        status: 'unconfirmed',
        source: 'edited',
        rationale: 'Shared on a baseline report.',
      }),
      findings: [{ code: 'allocation_deviates_from_default', severity: 'warning', ref: 'ground_conditions' }],
    }),
    allocationItem('price_escalation', {
      default: { party: 'owner', basis: 'contract', shares: null, rationale_key: null, source_url: 'https://example.org/s', review_status: 'unconfirmed' },
    }),
    allocationItem('schedule_delay', {
      default: null,
      findings: [{ code: 'risk_unallocated', severity: 'error', ref: 'schedule_delay' }],
    }),
  ];
  const props = { projectId: 'p1', catalogue: catalogue(), labels, onChanged: noop };

  it('tells confirmed, changed, usual and empty rows apart', () => {
    wrap(<RiskMatrixPanel {...props} model={model()} matrix={matrix(items)} />);
    const rows = screen.getAllByTestId('risk-row');
    expect(rows.map((r) => r.getAttribute('data-state'))).toEqual(['confirmed', 'unconfirmed', 'default', 'empty']);
    expect(rows[0]).toHaveTextContent('Design errors');
    expect(rows[0]).toHaveTextContent('Contractor');
    expect(within(rows[0]!).getByTestId('risk-linked')).toHaveTextContent('In the risk register');
    expect(within(rows[1]!).getByTestId('carrier-shares')).toHaveTextContent('Owner: 60 %');
    expect(rows[1]).toHaveTextContent('Ground baseline report');
    expect(rows[1]).toHaveTextContent('Differs from the usual allocation for this form.');
    expect(within(rows[2]!).getByTestId('risk-state')).toHaveTextContent('Usual, not confirmed');
    // an unverified catalogue fact carries its mark and its source next to it
    expect(within(rows[2]!).getByTestId('review-unconfirmed')).toHaveTextContent('Not verified');
    expect(within(rows[2]!).getByRole('link', { name: 'Source' })).toHaveAttribute('href', 'https://example.org/s');
    expect(rows[3]).toHaveTextContent('No party carries this risk yet.');
    expect(screen.getByTestId('matrix-summary')).toHaveTextContent('1 of 4 risks confirmed.');
    expect(screen.getByTestId('matrix-errors')).toHaveTextContent('To fix: 1');
  });

  it('confirm all sends no category list, so the server confirms every row', async () => {
    mocked.confirmAllocations.mockResolvedValue(matrix(items));
    wrap(<RiskMatrixPanel {...props} model={model()} matrix={matrix(items)} />);
    fireEvent.click(screen.getByTestId('confirm-all-button'));
    await waitFor(() => expect(mocked.confirmAllocations).toHaveBeenCalledWith('p1'));
  });

  it('confirming one row names that row only', async () => {
    mocked.confirmAllocations.mockResolvedValue(matrix(items));
    wrap(<RiskMatrixPanel {...props} model={model()} matrix={matrix(items)} />);
    fireEvent.click(within(screen.getAllByTestId('risk-row')[2]!).getByTestId('confirm-row'));
    await waitFor(() => expect(mocked.confirmAllocations).toHaveBeenCalledWith('p1', ['price_escalation']));
  });

  it('is read-only once the model is approved, with the reason', () => {
    wrap(<RiskMatrixPanel {...props} model={model({ status: 'binding' })} matrix={matrix(items)} />);
    expect(screen.queryByTestId('edit-row')).toBeNull();
    expect(screen.getAllByTestId('disabled-reason')[0]).toHaveAttribute('data-reason', 'model_not_editable');
  });

  it('offers the risk register only for confirmed risks that are not there yet', () => {
    const { unmount } = wrap(<RiskMatrixPanel {...props} model={model()} matrix={matrix(items)} />);
    expect(screen.queryByTestId('seed-risks-button')).toBeNull();
    unmount();
    wrap(<RiskMatrixPanel {...props} model={model()} matrix={matrix([allocationItem('design_errors', { allocation: allocation('design_errors') })])} />);
    expect(screen.getByTestId('seed-risks-button')).toBeEnabled();
    expect(screen.queryByTestId('confirm-all-button')).toBeNull();
  });
});

describe('AllocationDialog', () => {
  const item = allocationItem('ground_conditions');
  const open = () =>
    wrap(<AllocationDialog projectId="p1" item={item} matrix={matrix([item])} labels={labels} onClose={noop} onDone={noop} />);

  it('refuses shares that do not add up to 100 before sending', () => {
    open();
    fireEvent.change(screen.getByTestId('allocation-party'), { target: { value: 'shared' } });
    fireEvent.change(screen.getByLabelText('Share of Owner'), { target: { value: '60' } });
    fireEvent.change(screen.getByLabelText('Share of Contractor'), { target: { value: '30' } });
    fireEvent.click(screen.getByTestId('allocation-send'));
    expect(screen.getByTestId('allocation-problems')).toHaveTextContent('Shares of a shared risk must add up to 100.');
    expect(mocked.putAllocation).not.toHaveBeenCalled();
  });

  it('sends a shared risk with its shares as strings', async () => {
    mocked.putAllocation.mockResolvedValue(matrix([item]));
    open();
    fireEvent.change(screen.getByTestId('allocation-party'), { target: { value: 'shared' } });
    fireEvent.change(screen.getByLabelText('Share of Owner'), { target: { value: '60' } });
    fireEvent.change(screen.getByLabelText('Share of Contractor'), { target: { value: '40' } });
    fireEvent.click(screen.getByTestId('allocation-send'));
    await waitFor(() => expect(mocked.putAllocation).toHaveBeenCalled());
    expect(mocked.putAllocation).toHaveBeenCalledWith('p1', 'ground_conditions', {
      party: 'shared',
      // "by contract" is not a way to share a risk, so choosing Shared moved the basis
      basis: 'shared_pain_gain',
      shares: { owner: '60', contractor: '40' },
      rationale: '',
      not_applicable: false,
    });
    expect([...(screen.getByTestId('allocation-basis') as HTMLSelectElement).options].map((o) => o.value)).toEqual([
      'shared_pain_gain',
      'ground_baseline',
    ]);
  });

  it('not applicable needs a written reason', () => {
    open();
    fireEvent.click(screen.getByTestId('allocation-na'));
    fireEvent.click(screen.getByTestId('allocation-send'));
    expect(screen.getByTestId('allocation-problems')).toHaveTextContent('Not applicable needs a rationale.');
    expect(screen.queryByTestId('allocation-party')).toBeNull();
  });

  it('shows the refusal the server answered with', async () => {
    mocked.putAllocation.mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'model_not_editable', message: 'The delivery model cannot be changed in its current status.' } }),
    );
    open();
    fireEvent.click(screen.getByTestId('allocation-send'));
    expect(await screen.findByTestId('server-refusal')).toHaveTextContent('The delivery model cannot be changed in its current status.');
  });
});

describe('PackagePlanPanel', () => {
  const plan = [
    pkg('main', { title: 'Design and build contract', kind: 'design_and_construction', designs: true, link: { kind: 'contract', id: 'c1', status: 'signed', missing: false }, effective_status: 'awarded' }),
    pkg('sub', { title: 'Facade', parent_id: 'main' }),
    pkg('lift', { title: 'Lift supply', kind: 'supply', builds: false, supplies: true, link: { kind: 'rfq', id: 'r1', status: null, missing: true } }),
  ];
  const consistency = {
    form_code: 'design_build',
    errors: 1,
    warnings: 0,
    items: [
      { code: 'packages_inconsistent_with_form', severity: 'error' as const, ref: 'SUB', params: { reason: 'one_design_and_construction_package' } },
      { code: 'risk_unallocated', severity: 'error' as const, ref: 'schedule_delay' },
    ],
    total: 2,
    offset: 0,
    limit: 2,
  };
  const props = { projectId: 'p1', catalogue: catalogue(), labels, onChanged: noop };
  const chosen = model({ selected_form_code: 'design_build' });

  it('lists the plan with duties, status from the linked record and a broken link', () => {
    wrap(<PackagePlanPanel {...props} model={chosen} packages={plan} consistency={null} />);
    const rows = screen.getAllByTestId('package-row');
    expect(rows.map((r) => within(r).getByRole('rowheader').textContent)).toEqual([
      expect.stringContaining('Design and build contract'),
      expect.stringContaining('Facade'),
      expect.stringContaining('Lift supply'),
    ]);
    expect(rows[0]).toHaveTextContent('Designs');
    expect(rows[0]).toHaveTextContent('Builds');
    expect(within(rows[0]!).getByTestId('package-status')).toHaveTextContent('Awarded');
    expect(within(rows[0]!).getByTestId('package-link')).toHaveTextContent('Linked: Contract');
    expect(within(rows[2]!).getByTestId('package-link')).toHaveTextContent('The linked record no longer exists');
  });

  it('the banner names plan findings only, with the package and the form rule', () => {
    wrap(<PackagePlanPanel {...props} model={chosen} packages={plan} consistency={consistency} />);
    const findings = within(screen.getByTestId('consistency-findings')).getAllByRole('listitem');
    expect(findings).toHaveLength(1);
    expect(findings[0]).toHaveTextContent('Facade');
    expect(findings[0]).toHaveTextContent('The package plan does not fit the chosen form.');
    expect(findings[0]).toHaveTextContent('This form needs exactly one design and construction package.');
  });

  it('says so when the plan fits', () => {
    wrap(<PackagePlanPanel {...props} model={chosen} packages={plan} consistency={{ ...consistency, items: [], errors: 0 }} />);
    expect(screen.getByTestId('consistency-ok')).toHaveTextContent('The plan fits the chosen form.');
  });

  it('answers who supplies', () => {
    wrap(<PackagePlanPanel {...props} model={chosen} packages={plan} consistency={null} />);
    fireEvent.click(screen.getByTestId('package-filter-supplies'));
    expect(screen.getAllByTestId('package-row')).toHaveLength(1);
    expect(screen.getByTestId('package-row')).toHaveTextContent('Lift supply');
  });

  it('an empty plan offers the usual packages already before a form is proposed', () => {
    wrap(<PackagePlanPanel {...props} model={model()} packages={[]} consistency={null} />);
    expect(screen.getByText('No packages yet')).toBeInTheDocument();
    expect(screen.getByTestId('derive-button')).toBeEnabled();
    expect(screen.getByTestId('add-package-button')).toBeEnabled();
  });

  it('the plan stays open while a decision is proposed and closes once it is approved', () => {
    const { unmount } = wrap(<PackagePlanPanel {...props} model={model({ status: 'proposed' })} packages={[]} consistency={null} />);
    expect(screen.getByTestId('derive-button')).toBeEnabled();
    unmount();
    wrap(<PackagePlanPanel {...props} model={model({ status: 'binding' })} packages={[]} consistency={null} />);
    expect(screen.getByTestId('derive-button')).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'model_not_editable');
  });

  it('a viewer gets no row actions', () => {
    wrap(<PackagePlanPanel {...props} model={model({ selected_form_code: 'design_build' }, 'viewer')} packages={plan} consistency={null} />);
    expect(screen.queryByTestId('package-edit')).toBeNull();
    expect(screen.getByTestId('add-package-button')).toBeDisabled();
  });
});

describe('LinkPackageDialog', () => {
  const targets = vi.mocked(linkTargets.fetchLinkTargets);
  const open = () => wrap(<LinkPackageDialog projectId="p1" pkg={pkg('main')} labels={labels} onClose={noop} onDone={noop} />);

  it('picks a record by number and title and links it', async () => {
    targets.mockResolvedValue([{ id: 'c1', code: 'C-001', title: 'Main contract' }]);
    mocked.linkPackage.mockResolvedValue(pkg('main'));
    open();
    const picker = await screen.findByTestId('record-picker');
    expect(within(picker).getByRole('option', { name: 'C-001 · Main contract' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('link-send'));
    expect(screen.getByTestId('link-problems')).toHaveTextContent('Choose the record to link.');
    fireEvent.change(picker, { target: { value: 'c1' } });
    fireEvent.click(screen.getByTestId('link-send'));
    await waitFor(() => expect(mocked.linkPackage).toHaveBeenCalledWith('p1', 'main', { link_kind: 'contract', link_id: 'c1' }));
  });

  it('tells "no records yet" from "this type cannot be listed"', async () => {
    targets.mockResolvedValueOnce([]);
    open();
    expect(await screen.findByTestId('record-picker-empty')).toBeInTheDocument();
    targets.mockResolvedValueOnce(null);
    fireEvent.change(screen.getByTestId('link-kind'), { target: { value: 'rfq' } });
    expect(await screen.findByTestId('record-picker-unavailable')).toBeInTheDocument();
  });
});

describe('OfiPanel', () => {
  const items = [
    ofi('lift', {
      description: 'Passenger lift',
      findings: [{ code: 'ofi_without_route', severity: 'warning', ref: 'LIFT' }],
    }),
    ofi('chiller', {
      description: 'Chiller',
      procurement_route: 'purchase_order',
      status: 'route_set',
      install_by: 'package',
      package_id: 'mep',
      need_by_date: '2027-03-01',
      link: { kind: 'purchase_order', id: 'po1', status: 'issued', missing: false },
      findings: [{ code: 'ofi_late_for_installer', severity: 'warning', ref: 'CHILLER' }],
    }),
  ];
  const props = { projectId: 'p1', model: model(), packages: [pkg('mep', { title: 'Building services' })], labels, onChanged: noop };

  it('flags an item without a route and one that arrives late', () => {
    wrap(<OfiPanel {...props} items={items} />);
    const rows = screen.getAllByTestId('ofi-row');
    expect(within(rows[0]!).getByTestId('ofi-route')).toHaveTextContent('Not decided yet');
    expect(rows[0]).toHaveTextContent('Set a procurement route first.');
    expect(within(rows[0]!).getByTestId('ofi-route-action')).toHaveTextContent('Set route');
    expect(within(rows[0]!).queryByTestId('ofi-advance')).toBeNull();
    expect(rows[1]).toHaveTextContent('Building services');
    expect(rows[1]).toHaveTextContent('Linked: Purchase order');
    expect(rows[1]).toHaveTextContent('Arrives after the installer needs it.');
    expect(within(rows[1]!).getByTestId('ofi-status')).toHaveTextContent('Route set');
  });

  it('moves an item one step forward', async () => {
    mocked.setOfiStatus.mockResolvedValue(items[1]!);
    wrap(<OfiPanel {...props} items={items} />);
    const advance = within(screen.getAllByTestId('ofi-row')[1]!).getByTestId('ofi-advance');
    expect(advance).toHaveTextContent('Mark as ordered');
    fireEvent.click(advance);
    await waitFor(() => expect(mocked.setOfiStatus).toHaveBeenCalledWith('p1', 'chiller', 'ordered'));
  });

  it('an empty list says what belongs here and offers the first item', () => {
    wrap(<OfiPanel {...props} items={[]} />);
    expect(screen.getByText('No owner-furnished items yet')).toBeInTheDocument();
    expect(screen.getByTestId('add-ofi-button')).toBeEnabled();
  });
});

describe('DecisionRecordPanel', () => {
  const props = {
    projectId: 'p1',
    readiness: null,
    labels,
    personName: (id: string | null | undefined) => (id === 'u1' ? 'Dana Weber' : null),
    onChanged: noop,
    onOpenComparison: noop,
  };

  it('a proposed decision points to the gate and can be withdrawn by a manager', async () => {
    mocked.withdrawDecision.mockResolvedValue(model());
    wrap(<DecisionRecordPanel {...props} model={model({ status: 'proposed' })} decisions={[decision()]} />);
    expect(screen.getByRole('heading', { name: 'Design and build' })).toBeInTheDocument();
    expect(screen.getByTestId('decision-status')).toHaveTextContent('Proposed');
    expect(screen.getByTestId('decision-rationale')).toHaveTextContent('One point of responsibility');
    expect(screen.getByRole('link', { name: 'Approve at the gate' })).toHaveAttribute('href', '/projects/p1/governance');
    expect(screen.getByText(/by Dana Weber/)).toBeInTheDocument();
    expect(within(screen.getByTestId('decision-alternatives')).getAllByRole('listitem')).toHaveLength(2);
    fireEvent.click(screen.getByTestId('withdraw-button'));
    await waitFor(() => expect(mocked.withdrawDecision).toHaveBeenCalledWith('p1'));
  });

  it('never prints a user id for a person it cannot name', () => {
    wrap(<DecisionRecordPanel {...props} model={model({ status: 'proposed' })} decisions={[decision({ proposed_by: 'f3a1c0de-0000-4000-8000-000000000001' })]} />);
    expect(screen.getByTestId('current-decision')).not.toHaveTextContent('f3a1c0de');
  });

  it('warns when one person proposed and approved, and offers reopening on a binding model', () => {
    const approved = decision({ status: 'approved', approved_by: 'u1', approved_at: '2026-10-05T08:00:00+00:00', approval_source: 'gate', four_eyes_violated: true });
    wrap(<DecisionRecordPanel {...props} model={model({ status: 'binding' })} decisions={[approved]} />);
    expect(screen.getByTestId('four-eyes-warning')).toBeInTheDocument();
    expect(screen.getByText('Approved at the governance gate')).toBeInTheDocument();
    expect(screen.queryByTestId('approve-at-gate')).toBeNull();
    expect(screen.getByTestId('reopen-button')).toBeEnabled();
  });

  it('shows what the gate checks and keeps earlier decisions', () => {
    const readiness = { in_use: true, met: false, status: 'proposed' as const, decision_present: true, risks_allocated: false, errors: [{ code: 'risk_unallocated', severity: 'error' as const, ref: 'schedule_delay' }] };
    wrap(
      <DecisionRecordPanel
        {...props}
        readiness={readiness}
        model={model({ status: 'proposed' }, 'viewer')}
        decisions={[decision(), decision({ id: 'd0', status: 'withdrawn', is_current: false, form_code: 'cm_at_risk', snapshot: {}, rationale: 'First attempt.' })]}
      />,
    );
    const checks = within(screen.getByTestId('gate-readiness')).getAllByRole('listitem').slice(0, 3);
    expect(checks.map((n) => n.getAttribute('data-met'))).toEqual(['true', 'false', 'false']);
    expect(screen.getByTestId('readiness-errors')).toHaveTextContent('Schedule delay');
    expect(screen.getByTestId('earlier-decision')).toHaveTextContent('Withdrawn');
    expect(screen.getByTestId('withdraw-button')).toBeDisabled();
  });

  it('says what blocks the approval when the frame document is binding but the decision is not approved', () => {
    wrap(
      <DecisionRecordPanel
        {...props}
        model={model({ status: 'proposed' })}
        decisions={[decision({ approval_blocked_reason: 'approval_not_ready' })]}
      />,
    );
    expect(screen.getByTestId('approval-blocked')).toHaveTextContent('the delivery model has open errors');
  });

  it('a project whose governance names no frame document says so instead of pointing to a gate', () => {
    const noCarrier = model({ status: 'proposed', carrier: { document_id: null, document_type: null, document_status: null, missing_reason: 'carrier_missing' } });
    wrap(<DecisionRecordPanel {...props} model={noCarrier} decisions={[decision()]} />);
    expect(screen.getByTestId('carrier-missing')).toHaveTextContent('names no frame document');
    expect(screen.queryByTestId('approve-at-gate')).toBeNull();
  });

  it('a reopening can be given up after a confirmation', async () => {
    mocked.closeReopening.mockResolvedValue(model({ status: 'binding' }));
    const approved = decision({ status: 'approved', approved_at: '2026-10-05T08:00:00+00:00', approval_source: 'gate' });
    wrap(<DecisionRecordPanel {...props} model={model({ status: 'reopened' })} decisions={[approved]} />);
    fireEvent.click(screen.getByTestId('close-reopening-button'));
    expect(mocked.closeReopening).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Give up the reopening' }));
    await waitFor(() => expect(mocked.closeReopening).toHaveBeenCalledWith('p1'));
  });

  it('a record that no longer matches the bound revision is flagged, and a rejected decision reads as rejected', () => {
    const approved = decision({ status: 'approved', record_matches_bound_revision: false });
    const rejected = decision({ id: 'd0', status: 'rejected', is_current: false });
    wrap(<DecisionRecordPanel {...props} model={model({ status: 'binding' })} decisions={[approved, rejected]} />);
    expect(screen.getByTestId('record-differs')).toBeInTheDocument();
    expect(screen.getByTestId('earlier-decision')).toHaveTextContent('Rejected');
    expect(screen.queryByTestId('reopening')).toBeNull();
  });

  it('without any decision it sends the reader to the comparison', () => {
    const onOpenComparison = vi.fn();
    wrap(<DecisionRecordPanel {...props} onOpenComparison={onOpenComparison} model={model()} decisions={[]} />);
    expect(screen.getByText('No decision yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Go to the comparison' }));
    expect(onOpenComparison).toHaveBeenCalled();
  });
});

describe('shared pieces', () => {
  it('a disabled button stays visible and says why', () => {
    render(
      <ReasonedButton verdict="not_area_owner" onClick={noop}>
        Change
      </ReasonedButton>,
    );
    expect(screen.getByRole('button', { name: 'Change' })).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('Only a manager or the owner of the governance area');
  });

  it('only an unconfirmed fact carries the mark', () => {
    const { container } = render(<ReviewMark status="verified" sourceUrl="https://example.org" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('lists errors before warnings', () => {
    render(
      <FindingList
        findings={[
          { code: 'allocation_deviates_from_default', severity: 'warning', ref: 'a' },
          { code: 'risk_unallocated', severity: 'error', ref: 'b' },
        ]}
      />,
    );
    expect(within(screen.getByTestId('finding-list')).getAllByRole('listitem').map((n) => n.getAttribute('data-severity'))).toEqual(['error', 'warning']);
  });
});
