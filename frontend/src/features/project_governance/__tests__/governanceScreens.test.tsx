// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The governance screens as a reader meets them: the matrix shows states and
// the next gate's blockers, the blocker list names each blocker, the decision
// dialog will not send a stop without a reason, a disabled button says why,
// and a waiver is refused without a written reason.

import { describe, expect, it, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));

import { GovernanceMatrix } from '../GovernanceMatrix';
import { BlockerList } from '../GatePanel';
import { DecisionDialog } from '../DecisionDialog';
import { ReasonedButton } from '../GovernanceBits';
import { ConditionsRegister } from '../ConditionsRegister';
import { buildMatrix } from '../matrix';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';
import type { GateDetail } from '../api';
import { blocker, condition, detail, gate, gateDocument, matrixArea, matrixResponse, model } from './fixtures';

const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = (id: string | null | undefined) => (id === 'u-owner' ? 'Area owner one' : null);

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

afterEach(cleanup);

describe('GovernanceMatrix', () => {
  const m = model();
  const decided = gate({ id: 'g1', from_phase: 'strategy', status: 'decided', last_outcome: 'go' });
  const next = gate({ id: 'g2', code: 'brief_to_concept', from_phase: 'brief', sort_order: 2, status: 'in_review' });
  const data = buildMatrix({
    phases: m.phases,
    currentPhase: 'brief',
    matrix: matrixResponse({
      gates: [decided, next],
      next: { id: 'g2', code: 'brief_to_concept', status: 'in_review', blocker_count: 2 },
      areas: [
        matrixArea({
          area_id: 'a1',
          cells: { brief_to_concept: { check_status: 'ready_with_risks', rag: 'amber', stale: false, documents: [] } },
        }),
        matrixArea({ area_id: 'a2', code: 'cost_finance', owner_user_id: null }),
      ],
    }),
  });

  it('renders outcome, readiness, owners and the next gate with its blocker count', () => {
    wrap(
      <GovernanceMatrix
        data={data}
        catalogueId="neutral"
        next={next}
        blockerCount={2}
        labels={labels}
        personName={names}
        onOpenGate={() => undefined}
        onOpenArea={() => undefined}
      />,
    );
    const rows = screen.getAllByTestId('matrix-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText('Go')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Ready with risks')).toBeInTheDocument();
    expect(within(rows[0]!).getByText('Area owner one')).toBeInTheDocument();
    // the second area has no owner, which the row must say rather than leave blank
    expect(within(rows[1]!).getByTestId('owner-missing')).toHaveTextContent('No owner');
    expect(screen.getByTestId('next-gate-blockers')).toHaveTextContent('2 blockers');
    expect(screen.getByText('Current phase')).toBeInTheDocument();
  });

  it('says so when every gate is decided', () => {
    wrap(
      <GovernanceMatrix
        data={data}
        catalogueId="neutral"
        next={null}
        blockerCount={0}
        labels={labels}
        personName={names}
        onOpenGate={() => undefined}
        onOpenArea={() => undefined}
      />,
    );
    expect(screen.getByText('Every gate of this phase model is decided.')).toBeInTheDocument();
  });
});

describe('BlockerList', () => {
  it('lists every blocker as a sentence with its area', () => {
    render(
      <BlockerList
        blockers={[blocker('area_without_owner', 'cost_finance'), blocker('condition_overdue')]}
        areaName={(c) => (c === 'cost_finance' ? 'Cost and finance' : c)}
      />,
    );
    const items = within(screen.getByTestId('blocker-list')).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('This management area has no owner');
    expect(items[0]).toHaveTextContent('(Cost and finance)');
    expect(items[1]).toHaveTextContent('A condition from an earlier gate is overdue');
  });

  it('says plainly when nothing blocks', () => {
    render(<BlockerList blockers={[]} areaName={(c) => c} />);
    expect(screen.getByTestId('no-blockers')).toHaveTextContent('Nothing blocks this gate.');
  });
});

describe('DecisionDialog', () => {
  function open(onSubmit = vi.fn(), gateDetail: GateDetail = detail({ gate: gate({ status: 'in_review' }) })) {
    wrap(
      <DecisionDialog
        open
        onClose={() => undefined}
        projectId="p1"
        detail={gateDetail}
        catalogueId="neutral"
        labels={labels}
        today="2026-10-11"
        busy={false}
        serverViolations={[]}
        serverError={null}
        onSubmit={onSubmit}
      />,
    );
    return onSubmit;
  }

  it('will not send a stop without a rationale', () => {
    const onSubmit = open();
    fireEvent.click(screen.getByRole('radio', { name: /^Stop/ }));
    const submit = screen.getByTestId('decision-submit');
    expect(submit).toBeDisabled();
    expect(screen.getByTestId('decision-problems')).toHaveTextContent('Write down the reason');
    fireEvent.click(submit);
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: 'Funding withdrawn by the client' } });
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ outcome: 'stop', rationale: 'Funding withdrawn by the client', conditions: [] }),
    );
  });

  it('sends a plain go without a rationale', () => {
    const onSubmit = open();
    fireEvent.click(screen.getByRole('radio', { name: /^Go\b(?! with)/ }));
    fireEvent.click(screen.getByTestId('decision-submit'));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'go' }));
  });

  it('go with conditions opens a condition row and needs its text', () => {
    open();
    fireEvent.click(screen.getByRole('radio', { name: /^Go with conditions/ }));
    fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: 'Open points tracked' } });
    expect(screen.getAllByTestId('condition-row')).toHaveLength(1);
    expect(screen.getByTestId('decision-submit')).toBeDisabled();
    expect(screen.getByTestId('decision-problems')).toHaveTextContent('Every condition needs a text.');
  });

  it('disables each outcome by its own server flag and says why', () => {
    // The final approver already approved on the route: a go is still theirs, a stop is not.
    const approved = detail({
      gate: gate({ status: 'in_review' }),
      can: {
        edit: true,
        decide: true,
        outcomes: {
          go: { allowed: true },
          go_with_conditions: { allowed: true },
          hold: { allowed: false, reason: 'route_not_pending' },
          recycle: { allowed: false, reason: 'route_not_pending' },
          stop: { allowed: false, reason: 'route_not_pending' },
        },
      },
    });
    const onSubmit = open(vi.fn(), approved);
    expect(screen.getByRole('radio', { name: /^Go\b(?! with)/ })).not.toBeDisabled();
    expect(screen.getByRole('radio', { name: /^Go with conditions/ })).not.toBeDisabled();
    for (const name of [/^Stop/, /^Hold/, /^Recycle/]) expect(screen.getByRole('radio', { name })).toBeDisabled();
    expect(within(screen.getByTestId('outcome-stop')).getByTestId('disabled-reason')).toHaveTextContent(
      'The approval route of this gate is no longer pending',
    );
    expect(within(screen.getByTestId('outcome-go')).queryByTestId('disabled-reason')).toBeNull();

    fireEvent.click(screen.getByRole('radio', { name: /^Stop/ }));
    expect(screen.getByTestId('decision-submit')).toBeDisabled();
    fireEvent.click(screen.getByRole('radio', { name: /^Go\b(?! with)/ }));
    fireEvent.click(screen.getByTestId('decision-submit'));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'go' }));
  });

  describe('a missing required document', () => {
    const blocked = () =>
      detail({
        gate: gate({ status: 'in_review' }),
        areas: [
          { code: 'organisation', documents: [gateDocument({ doc_type: 'business_case' })] },
          { area_id: 'a2', code: 'cost_finance', documents: [gateDocument({ document_id: 'd2', doc_type: 'cost_plan' })] },
        ],
        blockers: [blocker('required_document_not_approved', 'organisation', 'business_case')],
      });

    it('becomes a condition that carries the area and the document type', () => {
      const onSubmit = open(vi.fn(), blocked());
      const missing = screen.getByTestId('missing-document');
      expect(missing).toHaveTextContent('Business case');
      fireEvent.click(within(missing).getByRole('button', { name: 'Turn into a condition' }));

      // The outcome follows, and the one row is the document's, not an empty one beside it.
      expect(screen.getByRole('radio', { name: /^Go with conditions/ })).toBeChecked();
      const rows = screen.getAllByTestId('condition-row');
      expect(rows).toHaveLength(1);
      expect(within(rows[0]!).getByLabelText('Area')).toHaveValue('organisation');
      expect(within(rows[0]!).getByLabelText('Frame document')).toHaveValue('business_case');
      expect(screen.getByTestId('missing-document')).toHaveTextContent('Covered by a condition');

      fireEvent.change(screen.getByLabelText(/Rationale/), { target: { value: 'Business case follows after funding' } });
      fireEvent.click(screen.getByTestId('decision-submit'));
      expect(onSubmit).toHaveBeenCalledTimes(1);
      const body = onSubmit.mock.calls[0]![0];
      expect(body.outcome).toBe('go_with_conditions');
      expect(body.conditions).toEqual([
        expect.objectContaining({ area_code: 'organisation', document_type: 'business_case' }),
      ]);
      expect(body.conditions[0].text).toContain('Business case');
    });

    it('offers only the documents of the chosen area, and forgets the document when the area changes', () => {
      open(vi.fn(), blocked());
      fireEvent.click(screen.getByRole('radio', { name: /^Go with conditions/ }));
      const row = screen.getByTestId('condition-row');
      const documentSelect = within(row).getByLabelText('Frame document');
      // Whole gate: there is no area, so no document can be named.
      expect(documentSelect).toBeDisabled();

      fireEvent.change(within(row).getByLabelText('Area'), { target: { value: 'organisation' } });
      expect(documentSelect).not.toBeDisabled();
      expect(within(documentSelect).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['', 'business_case']);
      fireEvent.change(documentSelect, { target: { value: 'business_case' } });
      expect(screen.getByTestId('missing-document')).toHaveTextContent('Covered by a condition');

      fireEvent.change(within(row).getByLabelText('Area'), { target: { value: 'cost_finance' } });
      expect(documentSelect).toHaveValue('');
      expect(within(documentSelect).getAllByRole('option').map((o) => o.getAttribute('value'))).toEqual(['', 'cost_plan']);
      expect(screen.getByTestId('missing-document')).not.toHaveTextContent('Covered by a condition');
    });
  });
});

describe('ReasonedButton', () => {
  it('stays visible, is disabled and says why', () => {
    render(<ReasonedButton verdict="four_eyes">Record decision</ReasonedButton>);
    const button = screen.getByRole('button', { name: 'Record decision' });
    expect(button).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('Four-eyes rule');
    expect(button).toHaveAttribute('aria-describedby', screen.getByTestId('disabled-reason').id);
  });

  it('an unknown server code reads neutral and shows the code, not a guessed reason', () => {
    render(<ReasonedButton verdict={{ server: 'budget_frozen_by_board' }}>Record decision</ReasonedButton>);
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
    const reason = screen.getByTestId('disabled-reason');
    expect(reason).toHaveTextContent('This decision is not available right now.');
    expect(reason).not.toHaveTextContent('approval route');
    expect(screen.getByTestId('disabled-reason-code')).toHaveTextContent('budget_frozen_by_board');
  });

  it('a known server code resolves through governance.errors', () => {
    render(<ReasonedButton verdict={{ server: 'route_not_at_final_step' }}>Record decision</ReasonedButton>);
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('The approval route has not reached its final step yet');
    expect(screen.queryByTestId('disabled-reason-code')).toBeNull();
  });

  it('is enabled with no reason when allowed', () => {
    render(<ReasonedButton verdict={null}>Record decision</ReasonedButton>);
    expect(screen.getByRole('button', { name: 'Record decision' })).not.toBeDisabled();
    expect(screen.queryByTestId('disabled-reason')).toBeNull();
  });
});

describe('ConditionsRegister', () => {
  const props = {
    projectId: 'p1',
    catalogueId: 'neutral',
    labels,
    personName: names,
    onChanged: () => undefined,
  };

  it('shows the next step when there are no conditions', () => {
    wrap(<ConditionsRegister {...props} conditions={[]} />);
    expect(screen.getByText('No conditions yet')).toBeInTheDocument();
  });

  it('filters by state', () => {
    wrap(
      <ConditionsRegister
        {...props}
        conditions={[condition({ id: 'c1' }), condition({ id: 'c2', status: 'overdue' }), condition({ id: 'c3', status: 'waived' })]}
      />,
    );
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: /^Overdue/ }));
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(1);
  });

  it('counts a condition the server reports as overdue under Overdue, escalated or not', () => {
    // Nobody ran the escalation: escalated_at is empty, and the server still says overdue.
    wrap(
      <ConditionsRegister
        {...props}
        conditions={[
          condition({ id: 'c1', status: 'overdue', escalated_at: null, due_date: '2026-09-01' }),
          condition({ id: 'c2', status: 'open', due_date: '2027-01-01' }),
        ]}
      />,
    );
    expect(screen.getByRole('button', { name: /^Overdue/ })).toHaveTextContent('1');
    expect(screen.getByRole('button', { name: /^Open/ })).toHaveTextContent('1');
    fireEvent.click(screen.getByRole('button', { name: /^Overdue/ }));
    const shown = screen.getAllByTestId('condition-entry');
    expect(shown).toHaveLength(1);
    // An overdue condition is still open work: both actions stay on offer.
    expect(within(shown[0]!).getByRole('button', { name: 'Clear with evidence' })).not.toBeDisabled();
    expect(within(shown[0]!).getByRole('button', { name: 'Waive' })).not.toBeDisabled();
  });

  it('refuses a waiver without a written reason', () => {
    wrap(<ConditionsRegister {...props} conditions={[condition()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Waive' }));
    fireEvent.click(screen.getByTestId('condition-action-send'));
    expect(screen.getByTestId('waiver-error')).toHaveTextContent('A waiver needs a written reason');
  });

  it('follows the flags of each condition, and says why an action is not open', () => {
    wrap(
      <ConditionsRegister
        {...props}
        conditions={[
          condition({ id: 'c1', can: { clear: true, waive: false, waive_reason: 'missing_permission' } }),
          condition({ id: 'c2', can: { clear: false, clear_reason: 'not_condition_owner', waive: true } }),
        ]}
      />,
    );
    const [first, second] = screen.getAllByTestId('condition-entry');
    expect(within(first!).getByRole('button', { name: 'Clear with evidence' })).not.toBeDisabled();
    expect(within(first!).getByRole('button', { name: 'Waive' })).toBeDisabled();
    expect(within(first!).getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'role_decide');
    expect(within(second!).getByRole('button', { name: 'Clear with evidence' })).toBeDisabled();
    expect(within(second!).getByRole('button', { name: 'Waive' })).not.toBeDisabled();
    expect(within(second!).getByTestId('disabled-reason')).toHaveTextContent('Only the condition owner or a manager can clear it.');
  });
});
