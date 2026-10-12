// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The writes that take a document-blocked gate through without a seed: a frame
// document is added, gets its file, goes to review and comes back; a decided
// gate is reopened or takes a further condition; a held gate is resumed; the
// gate route is pinned. Each button follows the server's flag, and a refusal
// is said in words.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('@/features/cde/api', () => ({
  fetchCDEContainers: vi.fn(),
  createCDEContainer: vi.fn(),
  createContainerRevision: vi.fn(),
}));
vi.mock('@/features/documents/api', () => ({ uploadDocument: vi.fn() }));
vi.mock('@/features/approval-routes/api', () => ({ listRoutes: vi.fn() }));
vi.mock('@/features/approval-routes/ApprovalInstanceDetailDrawer', () => ({
  ApprovalInstanceDetailDrawer: ({ instanceId }: { instanceId: string | null }) =>
    instanceId ? <div data-testid="approval-drawer">{instanceId}</div> : null,
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getGate: vi.fn(),
    setCriterion: vi.fn(),
    decideGate: vi.fn(),
    reopenGate: vi.fn(),
    resumeGate: vi.fn(),
    updateArea: vi.fn(),
    submitGate: vi.fn(),
    addGateCondition: vi.fn(),
    createDocument: vi.fn(),
    attachDocument: vi.fn(),
    returnDocument: vi.fn(),
    submitDocument: vi.fn(),
    getDocumentHistory: vi.fn(),
    updateModelSettings: vi.fn(),
  };
});

import * as cde from '@/features/cde/api';
import * as documents from '@/features/documents/api';
import * as approvalRoutes from '@/features/approval-routes/api';
import { ApiError } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';
import * as api from '../api';
import type { GateDetail, GovernanceArea, GovernanceModel } from '../api';
import { AreaPanel } from '../AreaPanel';
import { GatePanel } from '../GatePanel';
import { RoutePin } from '../RoutePin';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';
import { area, decision, detail, frameDocument, gate, model } from './fixtures';

const mocked = vi.mocked(api);
const mockedCde = vi.mocked(cde);
const mockedDocuments = vi.mocked(documents);
const mockedRoutes = vi.mocked(approvalRoutes);

const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = () => null;

function refusal(status: number, code: string) {
  return new ApiError(status, 'Refused', { detail: { code, message_key: `governance.errors.${code}`, message: code } });
}

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function toastTitles(): string[] {
  return useToastStore.getState().toasts.map((x) => x.title);
}

beforeEach(() => {
  vi.resetAllMocks();
  useToastStore.setState({ toasts: [] });
});
afterEach(cleanup);

describe('GatePanel', () => {
  function open(gateDetail: GateDetail) {
    mocked.getGate.mockResolvedValue(gateDetail);
    return wrap(
      <GatePanel
        projectId="p1"
        gateId="g1"
        model={model()}
        viewer={{ userId: 'u-me' }}
        labels={labels}
        personName={names}
        onBack={() => undefined}
        onOpenArea={() => undefined}
      />,
    );
  }

  it('one refused decision does not lock the decision button', async () => {
    const inReview = detail({ gate: gate({ status: 'in_review' }) });
    let answerRefetch: (d: GateDetail) => void = () => undefined;
    mocked.getGate
      .mockResolvedValueOnce(inReview)
      .mockImplementationOnce(() => new Promise<GateDetail>((resolve) => (answerRefetch = resolve)));
    mocked.decideGate.mockRejectedValue(refusal(403, 'decider_is_area_owner'));
    wrap(
      <GatePanel
        projectId="p1"
        gateId="g1"
        model={model()}
        viewer={{ userId: 'u-me' }}
        labels={labels}
        personName={names}
        onBack={() => undefined}
        onOpenArea={() => undefined}
      />,
    );

    fireEvent.click(await screen.findByTestId('open-decision'));
    fireEvent.click(screen.getByRole('radio', { name: /^Go\b(?! with)/ }));
    fireEvent.click(screen.getByTestId('decision-submit'));

    // The server's reason shows on the button while its flags are asked for again.
    await waitFor(() => expect(screen.getByTestId('open-decision')).toBeDisabled());
    expect(mocked.decideGate).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocked.getGate).toHaveBeenCalledTimes(2));

    // The flags arrive and still allow a decision: the button is open again, with no remount.
    answerRefetch(detail({ gate: gate({ status: 'in_review' }) }));
    await waitFor(() => expect(screen.getByTestId('open-decision')).not.toBeDisabled());
  });

  it('a refusal about the content of the decision leaves the button alone', async () => {
    open(detail({ gate: gate({ status: 'in_review' }) }));
    mocked.decideGate.mockRejectedValue(refusal(422, 'required_document_not_approved'));
    fireEvent.click(await screen.findByTestId('open-decision'));
    fireEvent.click(screen.getByRole('radio', { name: /^Go\b(?! with)/ }));
    fireEvent.click(screen.getByTestId('decision-submit'));
    expect(await screen.findByRole('alert')).toHaveTextContent('A required frame document is not ready');
    expect(screen.getByTestId('open-decision')).not.toBeDisabled();
    expect(mocked.getGate).toHaveBeenCalledTimes(1);
  });

  describe('submitting with no approval route chosen', () => {
    const render = (m: GovernanceModel, onOpenModel: () => void) => {
      mocked.getGate.mockResolvedValue(detail({ gate: gate({ status: 'in_preparation' }) }));
      mocked.submitGate.mockRejectedValue(refusal(422, 'no_decision_route'));
      return wrap(
        <GatePanel
          projectId="p1"
          gateId="g1"
          model={m}
          viewer={{ userId: 'u-me' }}
          labels={labels}
          personName={names}
          onBack={() => undefined}
          onOpenArea={() => undefined}
          onOpenModel={onOpenModel}
        />,
      );
    };

    it('leads a manager to where the route is chosen', async () => {
      const onOpenModel = vi.fn();
      render(model(), onOpenModel);
      fireEvent.click(await screen.findByRole('button', { name: 'Submit for review' }));
      const notice = await screen.findByTestId('gate-no-route');
      expect(notice).toHaveTextContent('no approval route is chosen');
      fireEvent.click(within(notice).getByTestId('gate-open-route'));
      expect(onOpenModel).toHaveBeenCalledTimes(1);
      expect(toastTitles()).toEqual([]);
    });

    it('tells somebody who may not manage whom to ask', async () => {
      render(model({ can: { manage: false } }), () => undefined);
      fireEvent.click(await screen.findByRole('button', { name: 'Submit for review' }));
      const notice = await screen.findByTestId('gate-no-route');
      expect(notice).toHaveTextContent('A governance manager chooses it in the phase model settings.');
      expect(within(notice).queryByTestId('gate-open-route')).toBeNull();
    });
  });

  it('a gate that cannot be loaded still offers the way back', async () => {
    mocked.getGate.mockRejectedValue(new Error('offline'));
    const onBack = vi.fn();
    wrap(
      <GatePanel
        projectId="p1"
        gateId="g1"
        model={model()}
        viewer={{ userId: 'u-me' }}
        labels={labels}
        personName={names}
        onBack={onBack}
        onOpenArea={() => undefined}
      />,
    );
    expect(await screen.findByText('The gate could not be loaded')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Back to matrix' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('an outcome that waits for more approvers leads to the approval itself', async () => {
    open(
      detail({
        gate: gate({ status: 'in_review', approval_instance_id: 'inst-1' }),
        can: {
          edit: true,
          decide: true,
          outcomes: {
            go: { allowed: false, reason: 'route_needs_more_approvals' },
            go_with_conditions: { allowed: false, reason: 'route_needs_more_approvals' },
            hold: { allowed: true, reason: null },
            stop: { allowed: true, reason: null },
          },
        },
      }),
    );
    expect(await screen.findByTestId('open-approval')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('open-decision'));
    expect(screen.getByRole('radio', { name: /^Go\b(?! with)/ })).toBeDisabled();
    fireEvent.click(screen.getByTestId('outcome-go-open-approval'));
    expect(await screen.findByTestId('approval-drawer')).toHaveTextContent('inst-1');
    expect(screen.queryByTestId('decision-dialog')).toBeNull();
  });

  describe('evidence no module could confirm', () => {
    const unknown = {
      code: 'budget:no_answer',
      state: 'unknown' as const,
      label: { key: null, text: null },
      link: null,
      detail: '',
      provider: 'budget',
      blocking: true,
      error: false,
      needs_acknowledgement: true,
    };
    const asked = () =>
      detail({
        gate: gate({ status: 'in_review' }),
        areas: [{ code: 'cost_finance', evidence: [unknown] }],
        can: {
          edit: true,
          decide: true,
          go: true,
          acknowledge: [{ area_code: 'cost_finance', code: 'budget:no_answer', provider: 'budget' }],
        },
      });

    it('is marked in the readiness view', async () => {
      open(asked());
      expect(await screen.findByTestId('evidence-needs-acknowledgement')).toHaveTextContent('to confirm at the decision');
    });

    it('a go waits for the tick and then names the item to the server', async () => {
      open(asked());
      mocked.decideGate.mockResolvedValue(decision());
      fireEvent.click(await screen.findByTestId('open-decision'));
      expect(screen.queryByTestId('acknowledge-evidence')).toBeNull();
      fireEvent.click(screen.getByRole('radio', { name: /^Go\b(?! with)/ }));
      const box = within(screen.getByTestId('acknowledge-evidence'));
      expect(box.getByText('This evidence source gave no answer, so it counts as unknown.')).toBeInTheDocument();
      expect(screen.getByTestId('decision-submit')).toBeDisabled();
      expect(screen.getByTestId('decision-problems')).toHaveTextContent('Tick every evidence item');
      fireEvent.click(box.getByTestId('acknowledge-item'));
      expect(screen.getByTestId('decision-submit')).not.toBeDisabled();
      fireEvent.click(screen.getByTestId('decision-submit'));
      await waitFor(() => expect(mocked.decideGate).toHaveBeenCalledTimes(1));
      expect(mocked.decideGate.mock.calls[0]![2]).toMatchObject({
        outcome: 'go',
        acknowledged_evidence: [{ area_code: 'cost_finance', code: 'budget:no_answer' }],
      });
    });

    it('a stop does not ask for it', async () => {
      open(asked());
      fireEvent.click(await screen.findByTestId('open-decision'));
      fireEvent.click(screen.getByRole('radio', { name: /^Stop\b/ }));
      expect(screen.queryByTestId('acknowledge-evidence')).toBeNull();
    });
  });

  describe('readiness criteria of an area', () => {
    const criterion = (code: string, met: boolean) => ({
      code,
      name: { key: null, text: { en: `Criterion ${code}` } },
      met,
      note: '',
      ticked_by: met ? 'u-me' : null,
      ticked_at: met ? '2026-10-10T08:00:00Z' : null,
    });
    const withCriteria = (owner: string) =>
      detail({
        gate: gate({ status: 'in_preparation' }),
        areas: [{ area_id: 'a1', code: 'cost_finance', owner_user_id: owner, criteria: [criterion('one', true), criterion('two', false)] }],
      });

    it('is not shown for an area whose model defines none', async () => {
      open(detail({ gate: gate({ status: 'in_preparation' }), areas: [{ code: 'cost_finance' }] }));
      await screen.findAllByTestId('gate-area');
      expect(screen.queryByTestId('readiness-criteria')).toBeNull();
    });

    it('the owner ticks one and the server is asked with the opposite of what stands', async () => {
      open(withCriteria('u-me'));
      mocked.setCriterion.mockResolvedValue({} as never);
      const block = within(await screen.findByTestId('readiness-criteria'));
      expect(block.getByTestId('criteria-progress')).toHaveTextContent('1 of 2 met');
      const boxes = block.getAllByRole('checkbox');
      expect(boxes[0]).toBeChecked();
      expect(boxes[1]).not.toBeChecked();
      fireEvent.click(boxes[1]!);
      await waitFor(() =>
        expect(mocked.setCriterion).toHaveBeenCalledWith('p1', 'g1', 'a1', 'two', { met: true, note: '' }),
      );
      await waitFor(() => expect(mocked.getGate).toHaveBeenCalledTimes(2));
    });

    it('somebody who does not answer for the area can read it and not tick it', async () => {
      open(withCriteria('u-somebody'));
      const block = within(await screen.findByTestId('readiness-criteria'));
      for (const box of block.getAllByRole('checkbox')) expect(box).toBeDisabled();
    });

    it('a refused tick says why and leaves the list as the server has it', async () => {
      open(withCriteria('u-me'));
      mocked.setCriterion.mockRejectedValue(refusal(422, 'unknown_criterion'));
      const block = within(await screen.findByTestId('readiness-criteria'));
      fireEvent.click(block.getAllByRole('checkbox')[1]!);
      await waitFor(() => expect(toastTitles().join(' ')).toContain('This readiness criterion is not part of'));
      expect(block.getAllByRole('checkbox')[1]).not.toBeChecked();
    });
  });

  it('an evidence row leads to the screen its module registered, and is plain text without one', async () => {
    const item = (code: string, href: string | null) => ({
      code,
      state: 'met' as const,
      label: { key: null, text: { en: `Evidence ${code}` } },
      link: { kind: 'plant', id: 'x1', href },
      detail: '',
      provider: 'plant',
      blocking: false,
      error: false,
    });
    open(
      detail({
        gate: gate({ status: 'in_preparation' }),
        areas: [{ code: 'cost_finance', evidence: [item('linked', '/projects/p1/plant-register'), item('bare', null)] }],
      }),
    );
    const links = await screen.findAllByTestId('evidence-link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute('href', '/projects/p1/plant-register');
    expect(links[0]).toHaveTextContent('Evidence linked');
    expect(screen.getByText('Evidence bare').closest('a')).toBeNull();
  });

  it('a gate on hold offers to resume, not to decide', async () => {
    open(detail({ gate: gate({ status: 'on_hold', hold_resume_date: '2026-11-01', last_outcome: 'hold' }) }));
    await screen.findByTestId('resume-gate');
    expect(screen.queryByTestId('open-decision')).toBeNull();
  });

  it('the resume button follows can.resume', async () => {
    const held = gate({ status: 'on_hold', hold_resume_date: '2026-11-01', last_outcome: 'hold' });
    const view = open(detail({ gate: held, can: { edit: true, decide: true, resume: false, resume_reason: 'decider_not_entitled' } }));
    const button = await screen.findByTestId('resume-gate');
    expect(button).toBeDisabled();
    expect(screen.getAllByTestId('disabled-reason').some((r) => r.getAttribute('data-reason') === 'role_decide')).toBe(true);
    view.unmount();

    mocked.resumeGate.mockResolvedValue(held);
    open(detail({ gate: held, can: { edit: false, decide: false, resume: true } }));
    fireEvent.click(await screen.findByTestId('resume-gate'));
    await waitFor(() => expect(mocked.resumeGate).toHaveBeenCalledWith('p1', 'g1'));
  });

  describe('reopening', () => {
    const passed = () =>
      detail({
        gate: gate({ status: 'decided', last_outcome: 'go' }),
        decisions: [decision({ outcome: 'go' })],
      });

    it('needs a reason, and says that a passed gate takes the project back a phase', async () => {
      mocked.reopenGate.mockResolvedValue(gate({ status: 'in_preparation', attempt_no: 2 }));
      open(passed());
      fireEvent.click(await screen.findByTestId('open-reopen'));
      const dialog = await screen.findByTestId('reopen-dialog');
      expect(within(dialog).getByTestId('reopen-rewind')).toHaveAttribute('data-rewind', 'forced');
      expect(within(dialog).getByTestId('reopen-rewind')).toHaveTextContent('The project moves back to the phase "Strategy".');

      fireEvent.click(within(dialog).getByTestId('reopen-submit'));
      expect(within(dialog).getByTestId('reopen-problem')).toHaveTextContent('Write down why the gate is reopened.');
      expect(mocked.reopenGate).not.toHaveBeenCalled();

      fireEvent.change(within(dialog).getByLabelText(/Why the gate is reopened/), {
        target: { value: '  Scope changed after the client review ' },
      });
      fireEvent.click(within(dialog).getByTestId('reopen-submit'));
      await waitFor(() =>
        expect(mocked.reopenGate).toHaveBeenCalledWith('p1', 'g1', { rationale: 'Scope changed after the client review' }),
      );
      await waitFor(() => expect(screen.queryByTestId('reopen-dialog')).toBeNull());
      expect(toastTitles()).toContain('Gate reopened');
    });

    it('a stopped gate reopens without moving the phase', async () => {
      mocked.reopenGate.mockResolvedValue(gate({ status: 'in_preparation', attempt_no: 2 }));
      open(detail({ gate: gate({ status: 'decided', last_outcome: 'stop' }), decisions: [decision({ outcome: 'stop' })] }));
      fireEvent.click(await screen.findByTestId('open-reopen'));
      const dialog = await screen.findByTestId('reopen-dialog');
      expect(within(dialog).getByTestId('reopen-rewind')).toHaveAttribute('data-rewind', 'none');
      fireEvent.change(within(dialog).getByLabelText(/Why the gate is reopened/), { target: { value: 'Funding is back' } });
      fireEvent.click(within(dialog).getByTestId('reopen-submit'));
      await waitFor(() =>
        expect(mocked.reopenGate).toHaveBeenCalledWith('p1', 'g1', { rationale: 'Funding is back' }),
      );
    });

    it('shows the server refusal in the dialog and keeps what was written', async () => {
      mocked.reopenGate.mockRejectedValue(refusal(409, 'later_gate_active'));
      open(passed());
      fireEvent.click(await screen.findByTestId('open-reopen'));
      const dialog = await screen.findByTestId('reopen-dialog');
      fireEvent.change(within(dialog).getByLabelText(/Why the gate is reopened/), { target: { value: 'Scope changed' } });
      fireEvent.click(within(dialog).getByTestId('reopen-submit'));
      expect(await within(dialog).findByRole('alert')).toHaveTextContent(enT('governance.errors.later_gate_active'));
      expect(within(dialog).getByLabelText(/Why the gate is reopened/)).toHaveValue('Scope changed');
    });

    it('follows can.reopen and is not offered on a gate that is not decided', async () => {
      const view = open(
        detail({
          gate: gate({ status: 'decided', last_outcome: 'go' }),
          can: { edit: true, decide: true, reopen: false, reopen_reason: 'later_gate_active' },
        }),
      );
      expect(await screen.findByTestId('open-reopen')).toBeDisabled();
      // Other buttons on the gate carry reasons of their own; this is the one of the reopen button.
      const reason = screen
        .getAllByTestId('disabled-reason')
        .find((r) => r.getAttribute('data-reason') === 'server:later_gate_active');
      expect(reason).toBeDefined();
      expect(reason).toHaveTextContent(enT('governance.errors.later_gate_active'));
      view.unmount();

      open(detail({ gate: gate({ status: 'in_review' }) }));
      await screen.findByTestId('open-decision');
      expect(screen.queryByTestId('open-reopen')).toBeNull();
    });
  });

  describe('a further condition', () => {
    const withConditions = () =>
      detail({
        gate: gate({ status: 'decided', last_outcome: 'go_with_conditions' }),
        decisions: [decision({ outcome: 'go_with_conditions', rationale: 'Open points tracked' })],
      });

    it('is added with its area, and not without a text', async () => {
      mocked.addGateCondition.mockResolvedValue({} as never);
      open(withConditions());
      fireEvent.click(await screen.findByTestId('open-add-condition'));
      const form = screen.getByTestId('gate-condition-form');
      fireEvent.click(within(form).getByTestId('gate-condition-send'));
      expect(within(form).getByTestId('gate-condition-problem')).toHaveTextContent('Every condition needs a text');
      expect(mocked.addGateCondition).not.toHaveBeenCalled();

      fireEvent.change(within(form).getByLabelText('What must be done'), { target: { value: ' Confirm the funding letter ' } });
      fireEvent.change(within(form).getByLabelText('Area'), { target: { value: 'organisation' } });
      fireEvent.click(within(form).getByTestId('gate-condition-send'));
      await waitFor(() =>
        expect(mocked.addGateCondition).toHaveBeenCalledWith('p1', 'g1', {
          text: 'Confirm the funding letter',
          severity: 'essential',
          area_code: 'organisation',
          document_type: null,
          owner_user_id: null,
          due_date: null,
        }),
      );
      await waitFor(() => expect(screen.queryByTestId('gate-condition-form')).toBeNull());
      expect(toastTitles()).toContain('Condition added');
    });

    it('is not offered on a gate passed without conditions, and follows can.add_condition', async () => {
      const view = open(detail({ gate: gate({ status: 'decided', last_outcome: 'go' }), decisions: [decision()] }));
      await screen.findByTestId('open-reopen');
      expect(screen.queryByTestId('open-add-condition')).toBeNull();
      view.unmount();

      open({ ...withConditions(), can: { edit: true, decide: true, reopen: true, add_condition: false, add_condition_reason: 'decider_not_entitled' } });
      expect(await screen.findByTestId('open-add-condition')).toBeDisabled();
    });
  });
});

describe('AreaPanel documents', () => {
  const theArea = (over: Partial<GovernanceArea> = {}) =>
    area({
      document_types: [
        { code: 'business_case', required_at_gates: ['strategy_to_brief'], tracked: false },
        { code: 'charter', required_at_gates: [], tracked: false },
      ],
      ...over,
    });

  function open(docs = [frameDocument()], a = theArea(), m = model()) {
    return wrap(
      <AreaPanel
        projectId="p1"
        area={a}
        model={m}
        documents={docs}
        changeRequests={[]}
        gates={[gate()]}
        labels={labels}
        personName={names}
        onBack={() => undefined}
      />,
    );
  }

  it('whether the area applies is locked while a gate is in review, with the reason', () => {
    wrap(
      <AreaPanel
        projectId="p1"
        area={theArea({ na_rationale: 'Not part of this project' })}
        model={model()}
        documents={[]}
        changeRequests={[]}
        gates={[gate({ status: 'in_review' })]}
        labels={labels}
        personName={names}
        onBack={() => undefined}
      />,
    );
    expect(screen.getByRole('checkbox', { name: 'Applies to this project' })).toBeDisabled();
    expect(screen.getByText(enT('governance.errors.settings_frozen_in_review'))).toBeInTheDocument();
  });

  it('takes the owner off only through its own button', async () => {
    mocked.updateArea.mockResolvedValue(theArea());
    open();
    expect(screen.queryByTestId('unassign-deputy_user_id')).toBeNull();
    fireEvent.click(screen.getByTestId('unassign-owner_user_id'));
    await waitFor(() => expect(mocked.updateArea).toHaveBeenCalledWith('p1', 'a1', { owner_user_id: null }));
  });

  it('documents that are loading or failed never read as an empty area', () => {
    const render = (props: object) =>
      wrap(
        <AreaPanel
          projectId="p1"
          area={theArea()}
          model={model()}
          documents={[]}
          changeRequests={[]}
          gates={[gate()]}
          labels={labels}
          personName={names}
          onBack={() => undefined}
          {...props}
        />,
      );
    const loading = render({ documentsLoading: true });
    expect(screen.getByTestId('area-documents-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('area-no-documents')).toBeNull();
    expect(screen.queryByTestId('add-document')).toBeNull();
    loading.unmount();

    const onRetry = vi.fn();
    render({ documentsError: new Error('offline'), onRetryDocuments: onRetry });
    const failed = screen.getByTestId('area-documents-error');
    expect(failed).toHaveTextContent('The frame documents could not be loaded.');
    expect(screen.queryByTestId('area-no-documents')).toBeNull();
    fireEvent.click(within(failed).getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('a document without a file says so, cannot be submitted, and offers to attach one', () => {
    open();
    const row = screen.getByTestId('area-document');
    expect(within(row).getByTestId('document-no-file')).toHaveTextContent('No file yet.');
    expect(within(row).getByRole('button', { name: 'Submit for gate review' })).toBeDisabled();
    expect(within(row).getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'document_without_file');
    expect(within(row).getByRole('button', { name: 'Attach a file' })).not.toBeDisabled();
    // The dead end this replaces told the reader to go and attach something elsewhere.
    expect(row).not.toHaveTextContent('in the CDE, then');
  });

  it('uploads a file: document, container, revision and attachment, in that order', async () => {
    const order: string[] = [];
    mockedCde.fetchCDEContainers.mockResolvedValue([]);
    mockedDocuments.uploadDocument.mockImplementation(async () => {
      order.push('upload');
      return { id: 'file-1' } as never;
    });
    mockedCde.createCDEContainer.mockImplementation(async () => {
      order.push('container');
      return { id: 'k-new' } as never;
    });
    mockedCde.createContainerRevision.mockImplementation(async () => {
      order.push('revision');
      return {} as never;
    });
    mocked.attachDocument.mockImplementation(async () => {
      order.push('attach');
      return frameDocument({ container_id: 'k-new' });
    });
    open();
    fireEvent.click(screen.getByTestId('document-attach-open'));
    const panel = screen.getByTestId('document-attach');
    expect(within(panel).getByTestId('attach-send')).toBeDisabled();
    const file = new File(['pdf'], 'business-case.pdf', { type: 'application/pdf' });
    fireEvent.change(within(panel).getByTestId('attach-file-input'), { target: { files: [file] } });
    fireEvent.click(within(panel).getByTestId('attach-send'));

    await waitFor(() => expect(order).toEqual(['upload', 'container', 'revision', 'attach']));
    expect(mockedDocuments.uploadDocument).toHaveBeenCalledWith('p1', file, 'other');
    expect(mockedCde.createCDEContainer).toHaveBeenCalledWith({
      project_id: 'p1',
      container_code: 'FRAME-ORGANISATION-BUSINESS-CASE',
      title: 'Business case',
    });
    expect(mockedCde.createContainerRevision).toHaveBeenCalledWith(
      'k-new',
      expect.objectContaining({ file_name: 'business-case.pdf', document_id: 'file-1' }),
    );
    expect(mocked.attachDocument).toHaveBeenCalledWith('p1', 'd1', 'k-new');
    await waitFor(() => expect(screen.queryByTestId('document-attach')).toBeNull());
  });

  it('attaches a container the project already has', async () => {
    mockedCde.fetchCDEContainers.mockResolvedValue([
      { id: 'k1', container_code: 'PRJ-BC-001', title: 'Business case v1' } as never,
    ]);
    mocked.attachDocument.mockResolvedValue(frameDocument({ container_id: 'k1' }));
    open();
    fireEvent.click(screen.getByTestId('document-attach-open'));
    fireEvent.click(screen.getByRole('radio', { name: /Use a CDE container/ }));
    const select = await screen.findByLabelText('CDE container');
    expect(within(select).getByRole('option', { name: 'PRJ-BC-001: Business case v1' })).toBeInTheDocument();
    expect(screen.getByTestId('attach-send')).toBeDisabled();
    fireEvent.change(select, { target: { value: 'k1' } });
    fireEvent.click(screen.getByTestId('attach-send'));
    await waitFor(() => expect(mocked.attachDocument).toHaveBeenCalledWith('p1', 'd1', 'k1'));
    expect(mockedDocuments.uploadDocument).not.toHaveBeenCalled();
  });

  it('says what to do when the project has no container, and when the list fails', async () => {
    mockedCde.fetchCDEContainers.mockResolvedValue([]);
    const view = open();
    fireEvent.click(screen.getByTestId('document-attach-open'));
    fireEvent.click(screen.getByRole('radio', { name: /Use a CDE container/ }));
    expect(await screen.findByText(/This project has no CDE container yet/)).toBeInTheDocument();
    view.unmount();

    mockedCde.fetchCDEContainers.mockRejectedValue(new Error('CDE is down'));
    open();
    fireEvent.click(screen.getByTestId('document-attach-open'));
    fireEvent.click(screen.getByRole('radio', { name: /Use a CDE container/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The CDE containers could not be loaded.');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('a document with a container takes a new file as a revision, without a second attachment', async () => {
    mockedDocuments.uploadDocument.mockResolvedValue({ id: 'file-2' } as never);
    mockedCde.createContainerRevision.mockResolvedValue({} as never);
    open([frameDocument({ container_id: 'k1' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Add a new file' }));
    const panel = screen.getByTestId('document-attach');
    expect(within(panel).queryByRole('radio')).toBeNull();
    fireEvent.change(within(panel).getByTestId('attach-file-input'), {
      target: { files: [new File(['x'], 'rev-b.pdf', { type: 'application/pdf' })] },
    });
    fireEvent.click(within(panel).getByTestId('attach-send'));
    await waitFor(() =>
      expect(mockedCde.createContainerRevision).toHaveBeenCalledWith('k1', expect.objectContaining({ document_id: 'file-2' })),
    );
    expect(mockedCde.createCDEContainer).not.toHaveBeenCalled();
    expect(mocked.attachDocument).not.toHaveBeenCalled();
    expect(mockedCde.fetchCDEContainers).not.toHaveBeenCalled();
  });

  it('an empty container explains the refused submit in words', async () => {
    mocked.submitDocument.mockRejectedValue(refusal(422, 'no_pending_revision'));
    open([frameDocument({ container_id: 'k1' })]);
    fireEvent.click(screen.getByRole('button', { name: 'Submit for gate review' }));
    await waitFor(() =>
      expect(toastTitles()).toContain('This document has no file yet. Add a file, then submit it for gate review.'),
    );
  });

  it('a document in review goes back to draft, when the server allows it', async () => {
    mocked.returnDocument.mockResolvedValue(frameDocument());
    const view = open([frameDocument({ status: 'in_review', container_id: 'k1' })]);
    expect(screen.queryByRole('button', { name: 'Submit for gate review' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Return to draft' }));
    await waitFor(() => expect(mocked.returnDocument).toHaveBeenCalledWith('p1', 'd1'));
    view.unmount();

    open([
      frameDocument({
        status: 'in_review',
        container_id: 'k1',
        can: { attach: false, submit: false, return: false, return_reason: 'not_area_owner' },
      }),
    ]);
    expect(screen.getByRole('button', { name: 'Return to draft' })).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'not_area_owner');
  });

  it('adds a frame document of a type the area does not track yet', async () => {
    mocked.createDocument.mockResolvedValue(frameDocument({ id: 'd2', doc_type: 'charter' }));
    open();
    const box = screen.getByTestId('add-document');
    const select = within(box).getByLabelText('Document type');
    // business_case is tracked already, so only the charter is on offer.
    expect(within(select).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['', 'charter']);
    expect(within(box).getByTestId('add-document-send')).toBeDisabled();
    fireEvent.change(select, { target: { value: 'charter' } });
    expect(box).toHaveTextContent('Optional: no gate requires it.');
    fireEvent.click(within(box).getByTestId('add-document-send'));
    await waitFor(() => expect(mocked.createDocument).toHaveBeenCalledWith('p1', { area_id: 'a1', doc_type: 'charter' }));
  });

  it('leaves out a type the server reports as tracked, whatever the list on screen holds', () => {
    open(
      [],
      theArea({
        document_types: [
          { code: 'business_case', required_at_gates: ['strategy_to_brief'], tracked: true },
          { code: 'charter', required_at_gates: [], tracked: false },
        ],
      }),
    );
    const select = within(screen.getByTestId('add-document')).getByLabelText('Document type');
    expect(within(select).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['', 'charter']);
  });

  it('names the gates a document type is required at', () => {
    open([]);
    expect(screen.getByTestId('area-no-documents')).toHaveTextContent('Add the first one below');
    fireEvent.change(screen.getByLabelText('Document type'), { target: { value: 'business_case' } });
    expect(screen.getByTestId('add-document')).toHaveTextContent('Required at: Strategy to brief');
  });

  it('the change request button follows the flag of the document', () => {
    const can = { attach: true, submit: true, return: true };
    const binding = (over: object) => frameDocument({ status: 'binding', can: { ...can, ...over } });
    const view = open([binding({ change_request: false, change_request_reason: 'no_change_route' })]);
    expect(screen.getByRole('button', { name: 'Raise change request' })).toBeDisabled();
    expect(screen.getByText(enT('governance.errors.no_change_route'))).toBeInTheDocument();
    view.unmount();

    open([binding({ change_request: true })]);
    expect(screen.getByRole('button', { name: 'Raise change request' })).not.toBeDisabled();
  });

  it('says so when nothing is left to add, and follows the flag of the area', () => {
    const view = open([frameDocument(), frameDocument({ id: 'd2', doc_type: 'charter' })]);
    expect(screen.getByTestId('add-document-none')).toHaveTextContent('Every frame document the phase model names for this area is tracked.');
    view.unmount();

    const second = open([], theArea({ document_types: [] }));
    expect(screen.getByTestId('add-document-none')).toHaveTextContent('The phase model names no frame document type for this area.');
    second.unmount();

    open([frameDocument()], theArea({ can: { add_document: false, add_document_reason: 'not_area_owner' } }));
    fireEvent.change(screen.getByLabelText('Document type'), { target: { value: 'charter' } });
    expect(screen.getByTestId('add-document-send')).toBeDisabled();
    expect(within(screen.getByTestId('add-document')).getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'not_area_owner');
  });
});

describe('RoutePin', () => {
  const route = (id: string, name: string, project_id: string | null = 'p1') =>
    ({ id, name, project_id, target_kind: 'phase_gate', is_active: true, steps: [] }) as never;

  it('asks for the active routes of the project, by the kind of decision', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([]);
    const view = wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={() => undefined} />);
    await screen.findByTestId('route-pin-empty');
    expect(mockedRoutes.listRoutes).toHaveBeenCalledWith({ projectId: 'p1', targetKind: 'phase_gate', includeInactive: false });
    view.unmount();

    wrap(<RoutePin projectId="p1" model={model()} kind="change" onDone={() => undefined} />);
    await screen.findByTestId('route-pin-empty');
    expect(mockedRoutes.listRoutes).toHaveBeenLastCalledWith({ projectId: 'p1', targetKind: 'frame_change', includeInactive: false });
  });

  it('with no route of the project says where to create one', async () => {
    // A route shared across projects cannot be pinned, so it does not count.
    mockedRoutes.listRoutes.mockResolvedValue([route('r2', 'Steering group', null)]);
    wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={() => undefined} />);
    const empty = await screen.findByTestId('route-pin-empty');
    expect(empty).toHaveTextContent('This project has no active approval route of this kind yet.');
    expect(within(empty).getByRole('link', { name: 'Open approval routes' })).toHaveAttribute('href', '/governance?tab=approvals');
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('offers only the routes of this project and says that nothing is chosen yet', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([
      route('r1', 'Gate board'),
      route('r2', 'Steering group', null),
      route('r3', 'Other project board', 'p2'),
    ]);
    wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={() => undefined} />);
    const select = await screen.findByRole('combobox');
    expect(within(select).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['', 'r1']);
    expect(select).toHaveValue('');
    expect(screen.getByTestId('route-pin-none')).toHaveTextContent('no gate can be submitted for review');
  });

  it('pins a route and removes the pin', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([route('r1', 'Gate board')]);
    mocked.updateModelSettings.mockResolvedValue(model());
    const onDone = vi.fn();
    const view = wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={onDone} />);
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'r1' } });
    await waitFor(() => expect(mocked.updateModelSettings).toHaveBeenCalledWith('p1', { decision_route_id: 'r1' }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    view.unmount();

    wrap(<RoutePin projectId="p1" model={model({ decision_route_id: 'r1' })} kind="gate" onDone={onDone} />);
    const pinned = await screen.findByRole('combobox');
    expect(pinned).toHaveValue('r1');
    expect(screen.queryByTestId('route-pin-none')).toBeNull();
    fireEvent.change(pinned, { target: { value: '' } });
    await waitFor(() => expect(mocked.updateModelSettings).toHaveBeenLastCalledWith('p1', { decision_route_id: null }));
  });

  it('pins the route for changes to binding documents in its own field', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([route('r5', 'Change board')]);
    mocked.updateModelSettings.mockResolvedValue(model());
    wrap(<RoutePin projectId="p1" model={model()} kind="change" onDone={() => undefined} />);
    expect(await screen.findByTestId('route-pin-none')).toHaveTextContent('no change request can be raised');
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'r5' } });
    await waitFor(() => expect(mocked.updateModelSettings).toHaveBeenCalledWith('p1', { change_route_id: 'r5' }));
  });

  it('warns when the chosen route is no longer an active route of the project', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([route('r2', 'Steering group')]);
    wrap(<RoutePin projectId="p1" model={model({ decision_route_id: 'r-gone' })} kind="gate" onDone={() => undefined} />);
    expect(await screen.findByTestId('route-pin-missing')).toHaveTextContent('The chosen route is no longer an active route of this project');
    expect(screen.getByRole('combobox')).toHaveValue('');
  });

  it('shows the refusal of the server in words', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([route('r1', 'Gate board')]);
    mocked.updateModelSettings.mockRejectedValue(refusal(422, 'route_not_pinnable'));
    wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={() => undefined} />);
    fireEvent.change(await screen.findByRole('combobox'), { target: { value: 'r1' } });
    await waitFor(() => expect(toastTitles()).toEqual([enT('governance.errors.route_not_pinnable')]));
  });

  it('is read-only with a reason for somebody who may not manage', async () => {
    mockedRoutes.listRoutes.mockResolvedValue([route('r1', 'Gate board')]);
    wrap(<RoutePin projectId="p1" model={model({ can: { manage: false } })} kind="gate" onDone={() => undefined} />);
    expect(await screen.findByRole('combobox')).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'role_manage');
  });

  it('says when the routes could not be loaded', async () => {
    mockedRoutes.listRoutes.mockRejectedValue(new Error('offline'));
    wrap(<RoutePin projectId="p1" model={model()} kind="gate" onDone={() => undefined} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('The approval routes could not be loaded.');
  });
});
