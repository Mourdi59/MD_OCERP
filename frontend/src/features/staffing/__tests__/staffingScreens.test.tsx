// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The staffing screens as a reader meets them: the plan shows positions,
// people and what blocks submission; a plan in review is locked and says so;
// a refused submission lists every blocker; a file opens only where the
// server allows it; the compliance matrix shows states and nothing else; a
// reason dialog will not send an empty reason; a full document number is
// refused before it leaves the browser; a document is recorded in the file
// itself and never picked from the credentials register; what a gate reads
// of a position and who its line manager is follow the server's flags;
// ending a file sends no date.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    submitPlan: vi.fn(),
    recordDocument: vi.fn(),
    holdFile: vi.fn(),
    endFile: vi.fn(),
    createPosition: vi.fn(),
    updatePosition: vi.fn(),
  };
});

import en from '@/app/locales/en';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { DocumentDialog, EndFileDialog } from '../FileDialogs';
import type { LabelContext } from '../labels';
import { PeoplePanel } from '../PeoplePanel';
import { PlanPanel } from '../PlanPanel';
import { PositionDialog } from '../PositionDialogs';
import { ComplianceView, OrgChartView, PlannedVsActualView, UpcomingView } from '../ReadViews';
import { ClearedBadge, ReasonDialog } from '../StaffingBits';
import { enT } from './i18nMock';
import { catalogue, compliance, fileDocument, fileRow, fill, handover, no, plan, position, upcoming } from './fixtures';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT, language: 'en', exists: (k) => k in en.translation };
const names = (id: string | null | undefined) => (id === 'u-lead' ? 'Mara Lindqvist' : null);

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

function renderPlan(over: Partial<Parameters<typeof PlanPanel>[0]> = {}) {
  const onChanged = vi.fn();
  const filled = position({
    id: 'pos-1',
    status: 'filled',
    covered_fte: '1.00',
    owner_user_id: 'u-lead',
    fills: [fill(), fill({ id: 'fill-2', name: null, status: 'proposed', cleared_to_work: null })],
  });
  const vacant = position({ id: 'pos-2', role_code: 'site_manager', key_role: false, fte: '0.50', headcount: 2 });
  const operation = position({ id: 'pos-3', role_code: 'operator_plant_manager', organisation: 'operator', phase: 'operation' });
  wrap(
    <PlanPanel
      projectId="p1"
      plan={plan()}
      catalogue={catalogue()}
      positions={[filled, vacant, operation]}
      handovers={[handover()]}
      findings={[]}
      labels={labels}
      personName={names}
      onChanged={onChanged}
      {...over}
    />,
  );
  return { onChanged };
}

describe('PlanPanel', () => {
  it('shows positions per phase with status, share, line manager and the people on them', () => {
    renderPlan();
    const execution = screen.getByTestId('phase-execution');
    expect(within(execution).getByText('Execution')).toBeInTheDocument();
    const rows = within(execution).getAllByTestId('position-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText('Project manager')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Owner project lead')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Line manager: Mara Lindqvist')).toBeInTheDocument();
    expect(within(rows[0]!).getByTestId('position-status')).toHaveTextContent('Filled');
    expect(within(rows[0]!).getByTestId('key-role')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Dana Weber')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('Site manager')).toBeInTheDocument();
    expect(within(rows[1]!).getByText('0.5 FTE x 2')).toBeInTheDocument();
    expect(within(rows[1]!).getByTestId('position-vacant')).toHaveTextContent('Vacant');
    expect(within(screen.getByTestId('phase-operation')).getByText('Plant manager (operator)')).toBeInTheDocument();
  });

  it('never leaves a person blank and tells "no file" apart from "not cleared"', () => {
    renderPlan();
    const fills = screen.getAllByTestId('fill-row');
    expect(within(fills[0]!).getByTestId('cleared-yes')).toHaveTextContent('Cleared to work');
    expect(within(fills[1]!).getByText('Former team member')).toBeInTheDocument();
    expect(within(fills[1]!).getByTestId('cleared-unknown')).toHaveTextContent('No personnel file');
    expect(within(fills[1]!).getByTestId('fill-confirm')).toHaveTextContent('Confirm');
  });

  it('lists what blocks submission with the role named, errors only', () => {
    renderPlan({
      findings: [
        { code: 'key_role_missing', ref: 'site_manager', severity: 'error', detail: '' },
        { code: 'demobilisation_missing', ref: 'file', severity: 'warning', detail: '' },
      ],
    });
    const box = screen.getByTestId('plan-blockers');
    expect(within(box).getByText('Before you can submit')).toBeInTheDocument();
    expect(within(box).getByText('Key role Site manager has no position.')).toBeInTheDocument();
    expect(within(box).queryByText('No return travel is planned.')).toBeNull();
  });

  it('names the handover from the person and position to the position that takes over', () => {
    renderPlan();
    const row = screen.getByTestId('handover-row');
    expect(within(row).getByText('Dana Weber, Project manager')).toBeInTheDocument();
    expect(within(row).getByText('Site manager')).toBeInTheDocument();
    expect(within(row).getByText('30 days overlap')).toBeInTheDocument();
    expect(within(row).getByText('Planned')).toBeInTheDocument();
  });

  it('locks a plan in review, says why, and offers to return it', () => {
    renderPlan({ plan: plan({ status: 'in_review' }) });
    expect(screen.getByTestId('plan-status')).toHaveTextContent('In review');
    expect(screen.getByTestId('plan-locked-hint')).toBeInTheDocument();
    expect(screen.queryByTestId('plan-submit')).toBeNull();
    expect(screen.getByTestId('plan-return')).toHaveTextContent('Return to draft');
    for (const id of ['add-position', 'add-from-catalogue', 'plan-settings', 'add-handover']) {
      const button = screen.getByTestId(id);
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('title', 'The plan is in review. Return it to draft before editing.');
    }
    expect(screen.queryByTestId('fill-confirm')).toBeNull();
  });

  it('keeps every blocker of a refused submission on screen', async () => {
    mocked.submitPlan.mockRejectedValue(
      new ApiError(422, 'Unprocessable', {
        detail: {
          code: 'key_role_missing',
          message: 'Key role has no position.',
          violations: [
            { code: 'key_role_missing', ref: 'site_manager', severity: 'error', detail: '' },
            { code: 'handover_missing', ref: 'pos-1', severity: 'error', detail: 'project_manager' },
          ],
        },
      }),
    );
    const { onChanged } = renderPlan();
    fireEvent.click(screen.getByTestId('plan-submit'));
    const box = await screen.findByTestId('plan-blockers');
    expect(within(box).getByText('Key role Site manager has no position.')).toBeInTheDocument();
    expect(within(box).getByText('Role Project manager needs a handover.')).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('explains an empty plan and offers the catalogue roles as the first step', () => {
    renderPlan({ positions: [], handovers: [] });
    expect(screen.getByText('No positions yet')).toBeInTheDocument();
    expect(screen.queryByTestId('plan-submit')).toBeNull();
    expect(screen.queryByTestId('handovers')).toBeNull();
  });
});

describe('PeoplePanel', () => {
  it('opens a file only where the server allows it', () => {
    const onOpen = vi.fn();
    wrap(
      <PeoplePanel
        projectId="p1"
        files={[fileRow(), fileRow({ id: 'file-2', name: 'Ilya Novak', roles: ['site_manager'], cleared_to_work: false, can: { open: no('no_relationship_to_person') } })]}
        catalogue={catalogue()}
        labels={labels}
        onOpen={onOpen}
        onChanged={() => undefined}
      />,
    );
    const rows = screen.getAllByTestId('file-row');
    expect(within(rows[0]!).getByText('Project manager')).toBeInTheDocument();
    fireEvent.click(within(rows[0]!).getByTestId('open-file'));
    expect(onOpen).toHaveBeenCalledWith('file-1');
    expect(within(rows[1]!).queryByTestId('open-file')).toBeNull();
    // The reason is the server's, not a sentence the client made up.
    expect(within(rows[1]!).getByTestId('file-closed')).toHaveTextContent(en.translation['staffing.errors.no_relationship_to_person']!);
    expect(within(rows[1]!).getByTestId('cleared-no')).toHaveTextContent('Not cleared');
  });

  it('says what a personnel file is for when there is none', () => {
    wrap(<PeoplePanel projectId="p1" files={[]} catalogue={catalogue()} labels={labels} onOpen={() => undefined} onChanged={() => undefined} />);
    expect(screen.getByText('No personnel files yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open personnel file' })).toBeInTheDocument();
  });
});

describe('read views', () => {
  it('shows a state per compliance cell and the days left on an expiring one', () => {
    wrap(<ComplianceView projectId="p1" catalogue={catalogue()} labels={labels} compliance={compliance()} onOpenFile={() => undefined} />);
    expect(screen.getByRole('columnheader', { name: 'Work permit' })).toBeInTheDocument();
    const rows = screen.getAllByTestId('compliance-row');
    const states = (row: HTMLElement) => within(row).getAllByTestId('compliance-cell').map((c) => [c.dataset.state, c.textContent]);
    expect(states(rows[0]!)).toEqual([
      ['valid', 'Valid'],
      ['not_required', 'Not required'],
    ]);
    expect(states(rows[1]!)).toEqual([
      ['missing', 'Missing'],
      ['expiring', 'Expires in 20 days'],
    ]);
  });

  it('explains an empty compliance matrix', () => {
    wrap(
      <ComplianceView projectId="p1" catalogue={catalogue()} labels={labels} compliance={compliance({ items: [], total: 0 })} onOpenFile={() => undefined} />,
    );
    expect(screen.getByText('Nobody to check yet')).toBeInTheDocument();
  });

  it('lists what is coming up and says so where a list is empty', () => {
    const onOpenFile = vi.fn();
    wrap(<UpcomingView catalogue={catalogue()} labels={labels} upcoming={upcoming()} onOpenFile={onOpenFile} />);
    const row = screen.getByTestId('expiring-row');
    expect(within(row).getByText('Work permit')).toBeInTheDocument();
    expect(within(row).getByText('Expires in 20 days')).toBeInTheDocument();
    fireEvent.click(within(row).getByRole('button', { name: 'Ilya Novak' }));
    expect(onOpenFile).toHaveBeenCalledWith('file-2');
    expect(within(screen.getByTestId('upcoming-mobilisations')).getByText('Nobody arrives on site in the next 14 days.')).toBeInTheDocument();
    expect(within(screen.getByTestId('upcoming-leave')).getByText('No leave is requested or approved.')).toBeInTheDocument();
  });

  it('marks a vacant position on the organisation chart', () => {
    wrap(
      <OrgChartView
        projectId="p1"
        catalogue={catalogue()}
        labels={labels}
        chart={{
          phases: [
            {
              phase: 'execution',
              organisations: [
                {
                  organisation: 'owner_project_lead',
                  positions: [
                    { position_id: 'pos-1', role_code: 'project_manager', custom_label: null, title: null, key_role: true, vacant: false, people: [{ name: 'Dana Weber', fte_share: '1.00', status: 'confirmed' }] },
                    { position_id: 'pos-2', role_code: 'site_manager', custom_label: null, title: null, key_role: false, vacant: true, people: [] },
                  ],
                },
              ],
            },
          ],
        }}
      />,
    );
    const boxes = screen.getAllByTestId('org-position');
    expect(within(boxes[0]!).getByText('Dana Weber')).toBeInTheDocument();
    expect(within(boxes[1]!).getByTestId('org-vacant')).toHaveTextContent('Vacant');
  });

  it('shows no booked days for a position nobody is linked to, instead of a zero', () => {
    wrap(
      <PlannedVsActualView
        catalogue={catalogue()}
        labels={labels}
        positions={[position({ id: 'pos-9', role_code: 'custom', custom_label: 'Interface manager' })]}
        rows={[
          { position_id: 'pos-9', role_code: 'custom', planned_fte_days: '30.00', actual_hours: '0', actual_fte_days: '0.00', variance_fte_days: '-30.00', linked_resources: 0 },
        ]}
      />,
    );
    const row = screen.getByTestId('pva-row');
    expect(within(row).getByText('Interface manager')).toBeInTheDocument();
    expect(within(row).getByTestId('pva-unlinked')).toBeInTheDocument();
    expect(within(row).getByText('30.0')).toBeInTheDocument();
    expect(within(row).queryByText('-30.0')).toBeNull();
  });
});

describe('ClearedBadge', () => {
  it('has three answers', () => {
    wrap(
      <>
        <ClearedBadge cleared />
        <ClearedBadge cleared={false} />
        <ClearedBadge cleared={null} />
      </>,
    );
    expect(screen.getByTestId('cleared-yes')).toBeInTheDocument();
    expect(screen.getByTestId('cleared-no')).toBeInTheDocument();
    expect(screen.getByTestId('cleared-unknown')).toBeInTheDocument();
  });
});

describe('ReasonDialog', () => {
  it('does not send an empty reason and shows the server refusal in place', async () => {
    const onSubmit = vi.fn().mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'retention_hold_active', message: 'x' } }),
    );
    const onClose = vi.fn();
    wrap(<ReasonDialog open title="Erase personal data" label="Reason" confirmLabel="Erase personal data" danger onClose={onClose} onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('reason-send'));
    expect(screen.getByTestId('reason-required')).toHaveTextContent('Write down the reason.');
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId('reason-text'), { target: { value: '  Requested by the person.  ' } });
    fireEvent.click(screen.getByTestId('reason-send'));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith('Requested by the person.'));
    expect(await screen.findByTestId('reason-error')).toHaveTextContent('A retention hold is active. Release it first.');
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('DocumentDialog', () => {
  const open = (document = fileDocument({ id: null, document_kind: 'work_permit', status: null, issued_at: null })) =>
    wrap(
      <DocumentDialog
        open
        projectId="p1"
        labels={labels}
        fileId="file-2"
        catalogue={catalogue()}
        document={document}
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );

  it('refuses a full document number before anything is sent', async () => {
    open();
    expect(screen.getByText('Never enter the full number.')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('document-last4'), { target: { value: 'C01X4821' } });
    fireEvent.click(screen.getByTestId('document-save'));
    expect(screen.getByTestId('form-error')).toHaveTextContent('Enter only the last 4 characters of the number.');
    expect(mocked.recordDocument).not.toHaveBeenCalled();
  });

  it('records the dates in the file itself and offers nobody else documents to pick from', async () => {
    mocked.recordDocument.mockResolvedValue({});
    open();
    // No list of credentials of the project is shown: there is nothing to choose, only dates to enter.
    expect(screen.queryByTestId('document-credential')).toBeNull();
    expect(screen.queryByRole('option')).toBeNull();
    expect(screen.getByTestId('document-record-hint')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('document-issued'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByTestId('document-until'), { target: { value: '2026-11-01' } });
    fireEvent.change(screen.getByTestId('document-last4'), { target: { value: '4821' } });
    fireEvent.click(screen.getByTestId('document-save'));
    await waitFor(() =>
      expect(mocked.recordDocument).toHaveBeenCalledWith('p1', 'file-2', {
        document_kind: 'work_permit',
        issued_at: '2026-05-01',
        valid_until: '2026-11-01',
        number_last4: '4821',
        fit_for_role: null,
      }),
    );
  });

  it('does not send a document that expires before it was issued', () => {
    open();
    fireEvent.change(screen.getByTestId('document-issued'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByTestId('document-until'), { target: { value: '2026-04-01' } });
    fireEvent.click(screen.getByTestId('document-save'));
    expect(screen.getByTestId('form-error')).toHaveTextContent(en.translation['staffing.errors.validity_dates_invalid']!);
    expect(mocked.recordDocument).not.toHaveBeenCalled();
  });

  it('asks for the fit answer only on the kind the server marks, and for no number there', () => {
    open(fileDocument({ id: null, document_kind: 'health_certificate', status: null, special_category: true }));
    expect(screen.getByTestId('document-fit')).toBeInTheDocument();
    expect(screen.queryByTestId('document-last4')).toBeNull();
    cleanup();
    open();
    expect(screen.queryByTestId('document-fit')).toBeNull();
  });
});

describe('EndFileDialog', () => {
  it('ends the file today: no date is asked for and none is sent', async () => {
    mocked.endFile.mockResolvedValue({});
    const onDone = vi.fn();
    wrap(<EndFileDialog open projectId="p1" fileId="file-1" onClose={() => undefined} onDone={onDone} />);
    const dialog = screen.getByTestId('end-file-dialog');
    expect(within(dialog).getByTestId('end-file-today')).toHaveTextContent('The assignment ends today.');
    expect(dialog.querySelector('input')).toBeNull();
    fireEvent.click(screen.getByTestId('end-file-save'));
    await waitFor(() => expect(mocked.endFile).toHaveBeenCalledTimes(1));
    expect(mocked.endFile.mock.calls[0]).toEqual(['p1', 'file-1']);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });
});

describe('PositionDialog', () => {
  const open = (over: { plan?: ReturnType<typeof plan>; position?: ReturnType<typeof position> | null } = {}) =>
    wrap(
      <PositionDialog
        open
        projectId="p1"
        labels={labels}
        catalogue={catalogue()}
        position={over.position ?? null}
        plan={over.plan ?? plan()}
        phases={['development', 'execution', 'operation']}
        defaultPhase="execution"
        onClose={() => undefined}
        onDone={() => undefined}
      />,
    );

  it('lets a manager set what the gate reads and the line manager, and sends them', async () => {
    mocked.createPosition.mockResolvedValue(position());
    open();
    expect(screen.getByTestId('position-key-role')).not.toBeDisabled();
    expect(screen.queryByTestId('gate-fields-locked')).toBeNull();
    expect(screen.queryByTestId('owner-locked')).toBeNull();
    // The requirement comes from the catalogue role, as a tag of the phase model.
    expect(screen.getByTestId('position-required-before')).toHaveValue('construction_start');
    fireEvent.click(screen.getByTestId('position-save'));
    await waitFor(() => expect(mocked.createPosition).toHaveBeenCalledTimes(1));
    expect(mocked.createPosition.mock.calls[0]![1]).toMatchObject({
      role_code: 'project_manager',
      phase: 'execution',
      key_role: true,
      handover_role: true,
      required_before: 'construction_start',
    });
  });

  it('follows the server when it refuses: the fields are locked with its reason and left out of the request', async () => {
    mocked.createPosition.mockResolvedValue(position());
    open({ plan: plan({ can: { manage: no('manage_permission_required'), assign_owner: no('owner_assignment_forbidden') } }) });
    expect(screen.getByTestId('position-key-role')).toBeDisabled();
    expect(screen.getByTestId('position-required-before')).toBeDisabled();
    expect(screen.getByTestId('gate-fields-locked')).toHaveTextContent(en.translation['staffing.errors.manage_permission_required']!);
    expect(screen.getByTestId('owner-locked')).toHaveTextContent(en.translation['staffing.errors.owner_assignment_forbidden']!);
    fireEvent.click(screen.getByTestId('position-save'));
    await waitFor(() => expect(mocked.createPosition).toHaveBeenCalledTimes(1));
    const body = mocked.createPosition.mock.calls[0]![1];
    for (const field of ['key_role', 'handover_role', 'required_before', 'owner_user_id']) expect(body).not.toHaveProperty(field);
  });

  it('freezes what the gate reads on a position that has left its first state, for a manager too', async () => {
    mocked.updatePosition.mockResolvedValue(position());
    open({ position: position({ stored_status: 'recruiting', status: 'recruiting', can: { gate_fields: no('gate_fields_frozen') } }) });
    expect(screen.getByTestId('position-key-role')).toBeDisabled();
    expect(screen.getByTestId('gate-fields-locked')).toHaveTextContent(en.translation['staffing.errors.gate_fields_frozen']!);
    fireEvent.click(screen.getByTestId('position-save'));
    await waitFor(() => expect(mocked.updatePosition).toHaveBeenCalledTimes(1));
    const body = mocked.updatePosition.mock.calls[0]![2];
    expect(body).not.toHaveProperty('key_role');
    expect(body).toHaveProperty('owner_user_id', null);
  });
});
