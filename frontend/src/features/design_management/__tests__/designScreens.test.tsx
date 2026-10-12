// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The design screens as a reader meets them: an empty list says what it is
// for and what to do first, a list reads in plain words, a form will not send
// a draft that lacks something, and a refused write shows the server's reason.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ id }: { id?: string }) => <input id={id} readOnly />,
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    createRole: vi.fn(),
    listApprovalPoints: vi.fn(),
    listUnresolvedWbs: vi.fn(),
    listPermits: vi.fn(),
    listReleases: vi.fn(),
    listDistributionRules: vi.fn(),
    listReports: vi.fn(),
    movePermit: vi.fn(),
  };
});

import { ApiError } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import * as api from '../api';
import { DrawingsPanel } from '../DrawingsPanel';
import { IssuePanel } from '../IssuePanel';
import { PermitsPanel } from '../PermitsPanel';
import { SchedulePanel } from '../SchedulePanel';
import { TeamPanel } from '../TeamPanel';
import { WbsPanel } from '../WbsPanel';
import { context, deliverable, drawing, permit, permitItem, release, role, wbsNode } from './fixtures';

const mocked = vi.mocked(api);

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.listApprovalPoints.mockResolvedValue([]);
  mocked.listUnresolvedWbs.mockResolvedValue([]);
  mocked.listPermits.mockResolvedValue([]);
  mocked.listReports.mockResolvedValue([]);
  mocked.listReleases.mockResolvedValue([]);
  mocked.listDistributionRules.mockResolvedValue([]);
  useToastStore.setState({ toasts: [] });
});
afterEach(cleanup);

describe('TeamPanel', () => {
  it('an empty team says who belongs here and offers the first step', () => {
    wrap(<TeamPanel ctx={context()} />);
    expect(screen.getByText('No design team yet')).toBeInTheDocument();
    expect(screen.getByText(/Add the parties that design this project/)).toBeInTheDocument();
    expect(screen.getAllByText('Add role').length).toBeGreaterThan(0);
  });

  it('lists a role with its party, originator code, person and state', () => {
    const ctx = context({
      roles: [role({ user_id: 'u1' }), role({ id: 'r2', code: 'R-02', title: 'Fire engineer', party_kind: 'specialist', originator_code: 'FIR', state: 'planned' })],
      personName: (id) => (id === 'u1' ? 'Dana Weber' : null),
    });
    wrap(<TeamPanel ctx={ctx} />);
    const rows = screen.getAllByTestId('role-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Architect');
    expect(rows[0]).toHaveTextContent('Lead designer');
    expect(rows[0]).toHaveTextContent('ARC');
    expect(rows[0]).toHaveTextContent('Dana Weber');
    expect(rows[0]).toHaveTextContent('Active');
    // nobody named must be said, not left blank
    expect(rows[1]).toHaveTextContent('Nobody named');
    expect(rows[1]).toHaveTextContent('Specialist');
  });

  it('does not send a role without its required fields', () => {
    wrap(<TeamPanel ctx={context()} />);
    fireEvent.click(screen.getByTestId('role-add'));
    fireEvent.click(screen.getByTestId('form-submit'));
    expect(screen.getByTestId('form-problems')).toHaveTextContent('Fill in:');
    expect(screen.getByTestId('form-problems')).toHaveTextContent('Kind of party');
    expect(mocked.createRole).not.toHaveBeenCalled();
  });

  it('sends only what was filled in and shows why the server refused', async () => {
    mocked.createRole.mockRejectedValue(
      new ApiError(422, 'Unprocessable', {
        detail: {
          code: 'originator_required',
          message: 'A discipline designer needs an originator code.',
          violations: [{ code: 'originator_required', field: 'originator_code', value: null }],
        },
      }),
    );
    const onChanged = vi.fn();
    wrap(<TeamPanel ctx={context({ onChanged })} />);
    fireEvent.click(screen.getByTestId('role-add'));
    fireEvent.change(screen.getByTestId('field-title'), { target: { value: 'Structural engineer' } });
    fireEvent.change(screen.getByTestId('field-party_kind'), { target: { value: 'discipline_designer' } });
    fireEvent.click(screen.getByTestId('form-submit'));
    const refusal = await screen.findByTestId('form-refusal');
    expect(refusal).toHaveTextContent('A discipline designer needs an originator code.');
    expect(refusal).toHaveTextContent('Originator code');
    expect(mocked.createRole).toHaveBeenCalledWith('p1', { title: 'Structural engineer', party_kind: 'discipline_designer' });
    // a refused write changes nothing, so nothing is refetched and the dialog stays
    expect(onChanged).not.toHaveBeenCalled();
    expect(screen.getByTestId('field-title')).toHaveValue('Structural engineer');
  });

  it('closes the dialog and refreshes after the server accepted the role', async () => {
    mocked.createRole.mockResolvedValue(role());
    const onChanged = vi.fn();
    wrap(<TeamPanel ctx={context({ onChanged })} />);
    fireEvent.click(screen.getByTestId('role-add'));
    fireEvent.change(screen.getByTestId('field-title'), { target: { value: 'Architect' } });
    fireEvent.change(screen.getByTestId('field-party_kind'), { target: { value: 'lead_designer' } });
    fireEvent.click(screen.getByTestId('form-submit'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByTestId('form-submit')).toBeNull());
  });
});

describe('SchedulePanel', () => {
  it('an empty schedule explains the list with an example', async () => {
    wrap(<SchedulePanel ctx={context()} />);
    expect(screen.getByText('No design schedule yet')).toBeInTheDocument();
    expect(screen.getByText(/List what each designer has to deliver in each phase/)).toBeInTheDocument();
    expect(await screen.findByText(/No approval points yet/)).toBeInTheDocument();
  });

  it('shows each line with its phase, designer, drawings against plan and state', () => {
    const ctx = context({
      roles: [role()],
      deliverables: [deliverable(), deliverable({ id: 'd2', code: 'DL-002', title: 'Models', waived: true, waived_rationale: 'Not in scope', state: 'waived', role_id: null })],
      drawings: [drawing()],
    });
    wrap(<SchedulePanel ctx={ctx} />);
    const rows = screen.getAllByTestId('schedule-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Permit drawings');
    expect(rows[0]).toHaveTextContent('Permit design');
    expect(rows[0]).toHaveTextContent('Architect');
    expect(within(rows[0]!).getByTestId('schedule-progress')).toHaveTextContent('1 of 3');
    expect(rows[0]).toHaveTextContent('In progress');
    expect(rows[1]).toHaveTextContent('Waived because: Not in scope');
    expect(within(rows[1]!).getByTestId('schedule-progress')).toHaveTextContent('0 of 3');
  });
});

describe('DrawingsPanel', () => {
  it('an empty register says where numbers and files come from', () => {
    wrap(<DrawingsPanel ctx={context()} />);
    expect(screen.getByText('No drawings yet')).toBeInTheDocument();
    expect(screen.getByText(/It gets its number from the scheme of the project/)).toBeInTheDocument();
  });

  it('shows number, revision, status and the warnings of a drawing, and filters by what is typed', () => {
    const ctx = context({
      roles: [role()],
      drawings: [
        drawing(),
        drawing({
          id: 'dr2',
          number: 'A-002',
          title: 'Section A',
          cde_state: 'wip',
          revision_code: 'P02',
          aliases: ['OLD-7'],
          legacy_scheme: true,
          title_block_mismatch: true,
          title_block_number: 'A-020',
        }),
      ],
    });
    wrap(<DrawingsPanel ctx={ctx} />);
    const rows = screen.getAllByTestId('drawing-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('A-001');
    expect(rows[0]).toHaveTextContent('Ground floor plan');
    expect(rows[0]).toHaveTextContent('P01');
    expect(rows[0]).toHaveTextContent('Shared');
    expect(rows[1]).toHaveTextContent('Formerly OLD-7');
    expect(rows[1]).toHaveTextContent('Number of an earlier scheme');
    expect(within(rows[1]!).getByTestId('title-block-mismatch')).toHaveTextContent('Title block shows A-020');
    expect(rows[1]).toHaveTextContent('Work in progress');

    fireEvent.change(screen.getByTestId('drawing-search'), { target: { value: 'A-002' } });
    expect(screen.getAllByTestId('drawing-row')).toHaveLength(1);
    fireEvent.change(screen.getByTestId('drawing-search'), { target: { value: 'no such drawing' } });
    expect(screen.queryAllByTestId('drawing-row')).toHaveLength(0);
    expect(screen.getByText('No drawing matches this search.')).toBeInTheDocument();
  });
});

describe('WbsPanel', () => {
  it('an empty breakdown shows how to start', () => {
    wrap(<WbsPanel ctx={context()} />);
    expect(screen.getByText('No work breakdown yet')).toBeInTheDocument();
    expect(screen.getByText(/Start with the top level/)).toBeInTheDocument();
  });

  it('lists parents before children and flags duplicates, use and dangling references', async () => {
    mocked.listUnresolvedWbs.mockResolvedValue([{ module: 'cost_model', table: 'cost_lines', row_id: 'x1', value: '9.9' }]);
    const ctx = context({
      wbs: [
        wbsNode({ id: 'w2', parent_id: 'w1', code: '1.1', name: 'Substructure', level: 2, references: { costs: 2, schedule: 3 }, duplicate_code: true }),
        wbsNode(),
      ],
    });
    wrap(<WbsPanel ctx={ctx} />);
    const rows = screen.getAllByTestId('wbs-row');
    expect(rows.map((r) => r.querySelector('td')?.textContent)).toEqual(['1', '1.1']);
    expect(rows[0]).toHaveTextContent('Not used yet');
    expect(rows[1]).toHaveTextContent('5 records');
    expect(within(rows[1]!).getByTestId('wbs-duplicate')).toHaveTextContent('Code used twice');
    const warning = await screen.findByTestId('wbs-unresolved');
    expect(warning).toHaveTextContent('1 record refers to a code that matches no node.');
    expect(warning).toHaveTextContent('Cost model refers to "9.9"');
  });
});

describe('IssuePanel', () => {
  it('an empty issue tab says what a release is and that recipients are needed', async () => {
    wrap(<IssuePanel ctx={context()} />);
    expect(await screen.findByText('No releases yet')).toBeInTheDocument();
    expect(await screen.findByText(/Without a recipient a release cannot be issued/)).toBeInTheDocument();
  });

  it('the Issue button follows the answer of the server and shows its reason', async () => {
    mocked.listReleases.mockResolvedValue([
      release({
        state: 'ready',
        approval_status: 'pending',
        can: { issue: { allowed: false, reason: 'release_not_approved' }, approve: { allowed: false, reason: 'release_four_eyes' } },
      }),
      release({
        id: 'rl2',
        code: 'REL-002',
        title: 'Tender set',
        state: 'ready',
        approval_status: 'approved',
        can: { issue: { allowed: true, reason: null }, approve: { allowed: false, reason: 'release_not_pending' } },
      }),
    ]);
    wrap(<IssuePanel ctx={context()} />);
    const rows = await screen.findAllByTestId('release-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByTestId('release-approval')).toHaveTextContent('Waiting for approval');
    expect(within(rows[0]!).getByTestId('release-issue')).toBeDisabled();
    expect(within(rows[0]!).getByTestId('release-blocked')).toHaveTextContent('The release has not been approved on its approval route yet.');
    expect(within(rows[1]!).getByTestId('release-approval')).toHaveTextContent('Approved for issue');
    expect(within(rows[1]!).getByTestId('release-issue')).toBeEnabled();
    expect(within(rows[1]!).queryByTestId('release-blocked')).toBeNull();
  });

  it('a recipient without a purpose receives releases of any purpose', async () => {
    mocked.listDistributionRules.mockResolvedValue([
      {
        id: 'ru1',
        recipient_list_id: null,
        recipient_role_id: 'r1',
        discipline_codes: [],
        form_codes: [],
        phase_codes: [],
        wbs_node_ids: [],
        min_suitability: null,
        purpose: '',
        format: 'pdf',
        copies_paper: 0,
        ack_required: false,
        active: true,
      },
    ]);
    wrap(<IssuePanel ctx={context({ roles: [role()] })} />);
    const row = await screen.findByTestId('rule-row');
    expect(row).toHaveTextContent('Architect');
    expect(row).toHaveTextContent('Any purpose');
  });
});

describe('PermitsPanel', () => {
  it('an empty permit tab says what the package is for', async () => {
    wrap(<PermitsPanel ctx={context()} />);
    expect(await screen.findByText('No permit package yet')).toBeInTheDocument();
    expect(screen.getByText(/You see at once which items are still missing/)).toBeInTheDocument();
  });

  it('a failing list is an error with a retry, not an empty package', async () => {
    mocked.listPermits.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    wrap(<PermitsPanel ctx={context()} />);
    expect(await screen.findByText('The permit packages could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No permit package yet')).toBeNull();
  });

  it('shows what is missing, and a refused step shows the reason of the server', async () => {
    mocked.listPermits.mockResolvedValue([
      permit({
        missing: ['i2'],
        items: [
          permitItem(),
          permitItem({ id: 'i2', kind: 'report', title: 'Fire safety concept', present: false, state_ok: false }),
          permitItem({ id: 'i3', kind: 'form', title: 'Application form', required: false, state_ok: false }),
        ],
      }),
    ]);
    mocked.movePermit.mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'permit_incomplete', message: 'Required items are missing or not shared yet.' } }),
    );
    wrap(<PermitsPanel ctx={context()} />);
    const card = await screen.findByTestId('permit-card');
    expect(card).toHaveTextContent('Building permit');
    expect(within(card).getByTestId('permit-state')).toHaveTextContent('Being assembled');
    expect(within(card).getByTestId('permit-missing')).toHaveTextContent('1 required item is missing or not shared yet.');
    const items = within(card).getAllByTestId('permit-item');
    expect(items.map((i) => i.getAttribute('data-state'))).toEqual(['ready', 'missing', 'not_shared']);
    expect(items[1]).toHaveTextContent('Document missing');
    expect(items[2]).toHaveTextContent('optional');

    fireEvent.click(within(card).getByTestId('permit-to-ready'));
    await waitFor(() => expect(mocked.movePermit).toHaveBeenCalledWith('p1', 'pm1', 'ready'));
    await waitFor(() =>
      expect(useToastStore.getState().toasts.map((toast) => toast.title)).toContain('Required items are missing or not shared yet.'),
    );
  });

  it('a submitted package offers no editing and only the step a person takes', async () => {
    mocked.listPermits.mockResolvedValue([permit({ state: 'submitted', items: [permitItem()], superseded_content: true })]);
    wrap(<PermitsPanel ctx={context()} />);
    const card = await screen.findByTestId('permit-card');
    expect(within(card).getByTestId('permit-superseded')).toBeInTheDocument();
    expect(within(card).queryByTestId('permit-item-add')).toBeNull();
    expect(within(card).queryByTestId('permit-to-ready')).toBeNull();
    expect(within(card).getByTestId('permit-to-withdrawn')).toHaveTextContent('Withdraw');
  });
});
