// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The roadmap, the two registers and the readiness checks, as a reader sees
// them: empty, filled, and when the server refuses.

import type { ReactElement } from 'react';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/features/cde/api', () => ({ fetchCDEContainers: vi.fn(async () => []) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    escalateConditions: vi.fn(),
    getApplication: vi.fn(),
    getCondition: vi.fn(),
    notifyStart: vi.fn(),
    recordInterruption: vi.fn(),
    recordResumption: vi.fn(),
    transitionPermit: vi.fn(),
  };
});

import * as cde from '@/features/cde/api';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ApplicationPanel } from '../ApplicationPanel';
import { ChecksPanel, sortReadinessItems } from '../ChecksPanel';
import { ConditionPanel } from '../ConditionPanel';
import { ConditionsRegister } from '../ConditionsRegister';
import { PermitsRegister } from '../PermitsRegister';
import { RoadmapTable } from '../RoadmapTable';
import { buildRoadmapRows } from '../rules';
import { application, condition, labels, loaded, permit, readiness, requirement, timelineRow } from './fixtures';
import { enT } from './i18nMock';

const mocked = vi.mocked(api);
const personName = (id: string | null | undefined) => (id === 'u1' ? 'Site manager' : null);

function renderIn(ui: ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

describe('RoadmapTable', () => {
  const handlers = { onOpen: vi.fn(), onAdd: vi.fn(), onPropose: vi.fn(), onSettings: vi.fn() };

  it('an empty roadmap says what it is for and offers one first step', () => {
    const onAdd = vi.fn();
    renderIn(<RoadmapTable rows={[]} binding={false} labels={labels} {...handlers} onAdd={onAdd} />);
    expect(screen.getByText('No permit on the roadmap yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Add permit' }));
    expect(onAdd).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('roadmap-propose')).toBeInTheDocument();
  });

  it('shows each permit with its state, the step of its application and the summary', () => {
    const rows = buildRoadmapRows(
      [requirement(), requirement({ id: 'r2', sort_order: 2, title: 'Road occupation', state: 'granted', applicant_role: 'contractor' })],
      [timelineRow()],
      [application()],
    );
    const onOpen = vi.fn();
    renderIn(<RoadmapTable rows={rows} binding={false} labels={labels} {...handlers} onOpen={onOpen} />);
    const [first, second] = screen.getAllByTestId('roadmap-row');
    expect(within(first!).getByText('In progress')).toBeInTheDocument();
    expect(within(first!).getByText('Under review')).toBeInTheDocument();
    expect(within(first!).getByText('Owner')).toBeInTheDocument();
    expect(within(second!).getByText('Granted')).toBeInTheDocument();
    expect(within(second!).getByText('Contractor')).toBeInTheDocument();
    expect(screen.getByTestId('roadmap-summary')).toHaveTextContent('Permits needed: 2. Granted: 1.');
    expect(screen.queryByTestId('roadmap-conflicts')).toBeNull();
    expect(screen.queryByTestId('roadmap-binding')).toBeNull();
    fireEvent.click(within(second!).getByRole('button', { name: 'Road occupation' }));
    expect(onOpen).toHaveBeenCalledWith('r2');
  });

  it('warns when a decision is forecast after the date the permit is needed', () => {
    const rows = buildRoadmapRows([requirement()], [timelineRow({ schedule_conflict: true, conflict_days: 12 })], []);
    renderIn(<RoadmapTable rows={rows} binding labels={labels} {...handlers} />);
    expect(screen.getByTestId('roadmap-conflicts')).toHaveTextContent('needed: 1.');
    expect(screen.getByTestId('row-conflict')).toHaveTextContent('decision 12 days late');
    expect(screen.getByTestId('roadmap-binding')).toBeInTheDocument();
  });

  it('writes one day late in the singular', () => {
    const rows = buildRoadmapRows([requirement()], [timelineRow({ schedule_conflict: true, conflict_days: 1 })], []);
    renderIn(<RoadmapTable rows={rows} binding={false} labels={labels} {...handlers} />);
    expect(screen.getByTestId('row-conflict')).toHaveTextContent('decision 1 day late');
  });
});

describe('PermitsRegister', () => {
  const base = {
    projectId: 'p1',
    requirements: [requirement({ state: 'granted' })],
    labels,
    personName,
    onOpenRequirement: vi.fn(),
    onShowConditions: vi.fn(),
    onShowRoadmap: vi.fn(),
  };

  it('an empty register explains where permits come from', () => {
    const onShowRoadmap = vi.fn();
    renderIn(<PermitsRegister {...base} permits={[]} conditions={[]} onShowRoadmap={onShowRoadmap} />);
    expect(screen.getByText('No permit granted yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open the roadmap' }));
    expect(onShowRoadmap).toHaveBeenCalledTimes(1);
  });

  it('shows a permit in force with its security and its open conditions', () => {
    renderIn(
      <PermitsRegister
        {...base}
        permits={[permit({ security_amount: '25000.00', security_currency: 'EUR' })]}
        conditions={[condition(), condition({ id: 'c2', number: '2', state: 'discharged' }), condition({ id: 'c3', confirmed: false })]}
      />,
    );
    expect(screen.getByTestId('permit-state')).toHaveTextContent('In force');
    expect(screen.getByTestId('permit-security').textContent).toMatch(/25.?000/);
    expect(screen.getByTestId('permit-conditions-link')).toHaveTextContent('Conditions: 2, still open: 1');
    expect(screen.getByTestId('permit-start')).toBeInTheDocument();
    expect(screen.getByTestId('permit-add-condition')).toBeInTheDocument();
    expect(screen.getByTestId('permit-change')).toBeInTheDocument();
  });

  it('warns before a permit lapses for not being used', () => {
    renderIn(<PermitsRegister {...base} permits={[permit({ lapse_warning: { level: 'd30', days: 21 } })]} conditions={[]} />);
    expect(screen.getByTestId('lapse-warning')).toHaveTextContent('The permit lapses in 21 days');
    expect(screen.getByTestId('lapse-warning')).toHaveTextContent('unless work starts');
    cleanup();
    renderIn(
      <PermitsRegister
        {...base}
        permits={[permit({ start_notified_at: '2026-07-01', paused_since: '2026-09-01', lapse_warning: { level: 'd30', days: 21 } })]}
        conditions={[]}
      />,
    );
    expect(screen.getByTestId('lapse-warning')).toHaveTextContent('unless work resumes');
    expect(screen.getByText('Work must resume by')).toBeInTheDocument();
  });

  it('offers nothing to do on a lapsed permit and says how it returns', () => {
    renderIn(
      <PermitsRegister {...base} permits={[permit({ state: 'lapsed', lapse_warning: { level: 'lapsed', days: 0 } })]} conditions={[]} />,
    );
    expect(screen.getByTestId('permit-state')).toHaveTextContent('Lapsed');
    expect(screen.getByTestId('lapse-warning')).toHaveTextContent('extension decision');
    expect(screen.queryByTestId('permit-start')).toBeNull();
    expect(screen.queryByTestId('permit-change')).toBeNull();
    expect(screen.queryByTestId('permit-add-condition')).toBeNull();
  });

  it('shows the reason when the server refuses the start notice', async () => {
    mocked.notifyStart.mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'not_seen_by_client', message: 'A suspensive condition is still open.' } }),
    );
    renderIn(<PermitsRegister {...base} permits={[permit()]} conditions={[]} />);
    fireEvent.click(screen.getByTestId('permit-start'));
    fireEvent.click(await screen.findByTestId('start-notice-dialog-submit'));
    expect(await screen.findByTestId('start-notice-dialog-error')).toHaveTextContent('A suspensive condition is still open.');
    expect(mocked.notifyStart).toHaveBeenCalledWith('p1', 'pm1', expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/));
  });

  it('offers to record an interruption once work started, and the resumption while it is interrupted', async () => {
    mocked.recordResumption.mockResolvedValue(permit());
    renderIn(
      <PermitsRegister
        {...base}
        permits={[
          permit({ start_notified_at: '2026-07-01' }),
          permit({ id: 'pm2', start_notified_at: '2026-07-01', paused_since: '2026-09-01' }),
        ]}
        conditions={[]}
      />,
    );
    expect(screen.queryByTestId('permit-start')).toBeNull();
    expect(screen.getAllByTestId('permit-interruption')).toHaveLength(1);
    expect(screen.getAllByTestId('permit-paused')).toHaveLength(1);
    fireEvent.click(screen.getByTestId('permit-resumption'));
    expect(await screen.findByText('Record that work resumed')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('start-notice-dialog-submit'));
    await vi.waitFor(() => expect(mocked.recordResumption).toHaveBeenCalledWith('p1', 'pm2', expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/)));
    expect(mocked.notifyStart).not.toHaveBeenCalled();
  });

  it('asks what happened and why before it records a change to a permit', async () => {
    mocked.transitionPermit.mockResolvedValue(permit({ state: 'suspended' }));
    renderIn(<PermitsRegister {...base} permits={[permit()]} conditions={[]} />);
    fireEvent.click(screen.getByTestId('permit-change'));
    fireEvent.click(await screen.findByTestId('permit-transition-dialog-submit'));
    expect(await screen.findByTestId('permit-transition-dialog-problems')).toHaveTextContent('Choose what happened to the permit.');
    expect(mocked.transitionPermit).not.toHaveBeenCalled();
  });
});

describe('ConditionsRegister', () => {
  const base = { projectId: 'p1', viewerId: 'u1', personName, onOpen: vi.fn(), onShowPermits: vi.fn() };

  it('an empty register says where conditions come from and leads to the permits', () => {
    const onShowPermits = vi.fn();
    renderIn(<ConditionsRegister {...base} conditions={[]} onShowPermits={onShowPermits} />);
    expect(screen.getByText('No permit condition yet')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open the permit register' }));
    expect(onShowPermits).toHaveBeenCalledTimes(1);
  });

  const list = [
    condition(),
    condition({ id: 'c2', number: '2', trigger: 'ongoing', topic: 'noise', owner_user_id: null, text: 'Keep noise below the limit.' }),
    condition({ id: 'c3', number: '3', trigger: 'by_date', due_date: '2026-05-01', overdue: true, owner_user_id: 'u2', text: 'Hand in the tree report.' }),
    condition({ id: 'c4', number: '4', kind: 'information', trigger: '', owner_user_id: null, text: 'The neighbour was heard.' }),
  ];

  it('lists the conditions and filters them by the view', () => {
    const onOpen = vi.fn();
    renderIn(<ConditionsRegister {...base} conditions={list} onOpen={onOpen} />);
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(4);
    expect(screen.getAllByTestId('condition-overdue')).toHaveLength(1);
    expect(screen.queryByTestId('view-proposals')).toBeNull();

    fireEvent.click(screen.getByTestId('view-overdue'));
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(1);
    expect(screen.getByText('Hand in the tree report.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('view-mine'));
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(1);
    fireEvent.click(screen.getByText('Submit the site traffic plan before work starts.'));
    expect(onOpen).toHaveBeenCalledWith('c1');

    fireEvent.click(screen.getByTestId('view-before_occupation'));
    expect(screen.getByTestId('conditions-none')).toBeInTheDocument();
  });

  it('offers to assign an owner only while a duty has none and is still open', () => {
    renderIn(<ConditionsRegister {...base} conditions={list} />);
    expect(screen.getByTestId('conditions-assign')).toBeInTheDocument();
    cleanup();
    // A note carries no duty, so a register of owned duties and notes needs no assignment.
    renderIn(<ConditionsRegister {...base} conditions={[list[0]!, list[3]!]} />);
    expect(screen.queryByTestId('conditions-assign')).toBeNull();
    cleanup();
    // The owner is fixed once a condition left the open state, so a batch must not carry such a row.
    renderIn(<ConditionsRegister {...base} conditions={[condition({ owner_user_id: null, state: 'evidence_submitted' })]} />);
    expect(screen.queryByTestId('conditions-assign')).toBeNull();
  });

  it('marks a proposal as waiting for a person and gives it its own view', () => {
    renderIn(<ConditionsRegister {...base} conditions={[...list, condition({ id: 'c5', number: '5', confirmed: false, source: 'extracted' })]} />);
    expect(screen.getByTestId('view-proposals')).toHaveTextContent('1');
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(4);
    fireEvent.click(screen.getByTestId('view-proposals'));
    expect(screen.getByTestId('condition-proposal')).toBeInTheDocument();
  });

  it('shows the reason when the server refuses to send reminders', async () => {
    mocked.escalateConditions.mockRejectedValue(
      new ApiError(403, 'Forbidden', { detail: { code: 'not_seen_by_client', message: 'Only the area owner may escalate.' } }),
    );
    renderIn(<ConditionsRegister {...base} conditions={list} />);
    fireEvent.click(screen.getByTestId('conditions-escalate'));
    expect(await screen.findByText('Only the area owner may escalate.')).toBeInTheDocument();
  });
});

describe('ApplicationPanel', () => {
  const clock = {
    start: null,
    base_due: null,
    forecast: null,
    reason: 'clock_not_started',
    stopped_days: 0,
    stopped_now: false,
    extensions: [],
    estimate: false,
    deemed_proposal: null,
    deemed_requires_notice: false,
    period: 3,
    unit: 'months' as const,
    start_event: null,
  };
  const props = {
    projectId: 'p1',
    applicationId: 'a1',
    requirementName: 'Main building permit',
    permits: [],
    conditions: [],
    labels,
    personName,
    onBack: vi.fn(),
  };

  it('shows the next step as the one button and keeps the rest behind More actions', async () => {
    mocked.getApplication.mockResolvedValue({
      ...application({ state: 'preparing', submitted_at: null }),
      clock,
      clock_events: [],
      decisions: [],
      allowed_targets: ['internal_review', 'submitted', 'withdrawn'],
    });
    renderIn(<ApplicationPanel {...props} internalReview={false} />);
    expect(await screen.findByTestId('application-step-submitted')).toHaveTextContent('Record submission');
    expect(screen.queryByTestId('application-decide')).toBeNull();
    expect(screen.queryByTestId('application-edit')).toBeNull();
    fireEvent.click(screen.getByTestId('application-more'));
    expect(screen.getByTestId('application-edit')).toBeInTheDocument();
    expect(screen.getByTestId('application-step-withdrawn')).toBeInTheDocument();
    // Internal release is off for this roadmap, so that branch is not offered at all.
    expect(screen.queryByTestId('application-step-internal_review')).toBeNull();
  });

  it('makes the decision the one button once the application is with the authority', async () => {
    mocked.getApplication.mockResolvedValue({
      ...application({ state: 'under_review' }),
      clock: { ...clock, start: '2026-05-04', forecast: '2026-08-04', reason: null },
      clock_events: [],
      decisions: [],
      allowed_targets: ['info_requested', 'withdrawn'],
    });
    renderIn(<ApplicationPanel {...props} internalReview />);
    expect(await screen.findByTestId('application-decide')).toBeInTheDocument();
    expect(screen.queryByTestId('application-step-info_requested')).toBeNull();
    fireEvent.click(screen.getByTestId('application-more'));
    expect(screen.getByTestId('application-step-info_requested')).toBeInTheDocument();
  });
});

describe('ConditionPanel', () => {
  const detail = {
    ...condition({ state: 'evidence_submitted' }),
    evidence: [
      { id: 'e1', condition_id: 'c1', kind: 'cde_revision' as const, ref_id: 'rev1', content_hash: '', note: '', added_by: 'u1', added_at: null },
    ],
    discharges: [],
  };

  it('says in words why the reader cannot close the condition', async () => {
    vi.mocked(cde.fetchCDEContainers).mockResolvedValue([]);
    mocked.getCondition.mockResolvedValue({
      ...detail,
      can: {
        discharge: {
          self_certified: { allowed: false, reason: 'verifier_is_owner' },
          waived_by_authority: { allowed: false, reason: 'verifier_is_owner' },
        },
      },
    });
    renderIn(<ConditionPanel projectId="p1" conditionId="c1" row={condition()} personName={personName} onBack={vi.fn()} />);
    expect(await screen.findByTestId('discharge-refusal')).toHaveTextContent(enT('permits.errors.verifier_is_owner'));
    expect(screen.getByTestId('condition-discharge')).toBeDisabled();
  });

  it('offers to close it when the server allows one way, and names the document given as evidence', async () => {
    vi.mocked(cde.fetchCDEContainers).mockResolvedValue([
      { id: 'k1', container_code: 'DOC-1', title: 'Traffic plan', current_revision_id: 'rev1' },
    ] as unknown as Awaited<ReturnType<typeof cde.fetchCDEContainers>>);
    mocked.getCondition.mockResolvedValue({
      ...detail,
      can: {
        discharge: {
          self_certified: { allowed: true, reason: null },
          waived_by_authority: { allowed: false, reason: 'verify_required' },
        },
      },
    });
    renderIn(<ConditionPanel projectId="p1" conditionId="c1" row={condition()} personName={personName} onBack={vi.fn()} />);
    expect(await screen.findByTestId('condition-discharge')).toBeEnabled();
    expect(screen.queryByTestId('discharge-refusal')).toBeNull();
    expect(await screen.findByText(/Traffic plan/)).toBeInTheDocument();
  });
});

describe('ChecksPanel', () => {
  it('puts what blocks first', () => {
    const items = sortReadinessItems([
      { code: 'permit_granted', state: 'met', detail: 'A', ref: null },
      { code: 'permit_missing', state: 'not_met', detail: 'B', ref: null },
      { code: 'permit_partial', state: 'at_risk', detail: 'C', ref: null },
    ]);
    expect(items.map((i) => i.detail)).toEqual(['B', 'C', 'A']);
  });

  it('shows each gate with its status and names what is missing', () => {
    renderIn(
      <ChecksPanel
        readiness={{
          start: loaded(
            readiness({
              status: 'not_ready',
              items: [
                { code: 'permit_granted', state: 'met', detail: 'Preliminary decision', ref: 'r0' },
                { code: 'permit_missing', state: 'not_met', detail: 'Main building permit', ref: 'r1' },
              ],
            }),
          ),
          handover: loaded(readiness({ gate: 'handover', status: 'at_risk' })),
          register: loaded(readiness({ gate: 'register', status: 'ready' })),
        }}
        validation={loaded([])}
      />,
    );
    expect(screen.getByTestId('readiness-start-status')).toHaveTextContent('Not ready');
    expect(screen.getByTestId('readiness-handover-status')).toHaveTextContent('At risk');
    expect(screen.getByTestId('readiness-register-status')).toHaveTextContent('Ready');
    const items = within(screen.getByTestId('readiness-start')).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('Main building permit: not granted yet');
    expect(items[1]).toHaveTextContent('Preliminary decision: granted');
    expect(screen.getByTestId('validation-clean')).toBeInTheDocument();
  });

  it('lists only the checks that failed, with what to do', () => {
    renderIn(
      <ChecksPanel
        readiness={{ start: loaded(readiness()), handover: loaded(readiness()), register: loaded(readiness()) }}
        validation={loaded([
          { rule_id: 'a', passed: true, severity: 'error', message: 'Passed check', element_ref: null, suggestion: null },
          { rule_id: 'b', passed: false, severity: 'warning', message: 'Condition 3 has no owner', element_ref: 'c3', suggestion: 'Assign an owner' },
        ])}
      />,
    );
    const failed = within(screen.getByTestId('validation-list')).getAllByRole('listitem');
    expect(failed).toHaveLength(1);
    expect(failed[0]).toHaveTextContent('Condition 3 has no owner');
    expect(failed[0]).toHaveTextContent('Assign an owner');
    expect(screen.queryByText('Passed check')).toBeNull();
  });

  it('a gate that failed to load says so and the others still show', () => {
    renderIn(
      <ChecksPanel
        readiness={{
          start: { data: undefined, isLoading: false, isError: true, error: new Error('offline'), refetch: () => undefined },
          handover: loaded(readiness()),
          register: loaded(readiness()),
        }}
        validation={loaded([])}
      />,
    );
    expect(screen.getByText('Readiness could not be loaded')).toBeInTheDocument();
    expect(screen.getByTestId('readiness-handover-status')).toHaveTextContent('Ready');
  });
});
