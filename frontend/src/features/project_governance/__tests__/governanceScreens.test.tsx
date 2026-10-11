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
import { area, blocker, condition, detail, gate, model } from './fixtures';

const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = (id: string | null | undefined) => (id === 'u-owner' ? 'Dana Weber' : null);

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

afterEach(cleanup);

describe('GovernanceMatrix', () => {
  const m = model();
  const decided = gate({ id: 'g1', from_phase: 'strategy', status: 'decided', last_outcome: 'go' });
  const next = gate({ id: 'g2', code: 'brief_to_concept', from_phase: 'brief', sort_order: 2, status: 'in_review' });
  const nextDetail = detail({
    gate: next,
    areas: [{ area_id: 'a1', check: 'ready_with_risks' }],
    blockers: [blocker('area_without_owner', 'cost_finance'), blocker('required_document_not_approved', 'organisation')],
  });
  const data = buildMatrix({
    phases: m.phases,
    currentPhase: 'brief',
    areas: [area({ id: 'a1' }), area({ id: 'a2', code: 'cost_finance', owner_user_id: null, sort_order: 2 })],
    gates: [decided, next],
    documents: [],
    nextDetail,
  });

  it('renders outcome, readiness, owners and the next gate with its blocker count', () => {
    wrap(
      <GovernanceMatrix
        data={data}
        catalogueId="neutral"
        next={next}
        nextDetail={nextDetail}
        nextDetailLoading={false}
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
    expect(within(rows[0]!).getByText('Dana Weber')).toBeInTheDocument();
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
        nextDetail={null}
        nextDetailLoading={false}
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
  function open(onSubmit = vi.fn()) {
    wrap(
      <DecisionDialog
        open
        onClose={() => undefined}
        projectId="p1"
        detail={detail({ gate: gate({ status: 'in_review' }) })}
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
});

describe('ReasonedButton', () => {
  it('stays visible, is disabled and says why', () => {
    render(<ReasonedButton verdict="four_eyes">Record decision</ReasonedButton>);
    const button = screen.getByRole('button', { name: 'Record decision' });
    expect(button).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveTextContent('Four-eyes rule');
    expect(button).toHaveAttribute('aria-describedby', screen.getByTestId('disabled-reason').id);
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
    wrap(<ConditionsRegister {...props} conditions={[]} viewer={{ userId: 'u', role: 'manager' }} />);
    expect(screen.getByText('No conditions yet')).toBeInTheDocument();
  });

  it('filters by state', () => {
    wrap(
      <ConditionsRegister
        {...props}
        viewer={{ userId: 'u', role: 'manager' }}
        conditions={[condition({ id: 'c1' }), condition({ id: 'c2', status: 'overdue' }), condition({ id: 'c3', status: 'waived' })]}
      />,
    );
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: /^Overdue/ }));
    expect(screen.getAllByTestId('condition-entry')).toHaveLength(1);
  });

  it('refuses a waiver without a written reason', () => {
    wrap(<ConditionsRegister {...props} viewer={{ userId: 'u', role: 'manager' }} conditions={[condition()]} />);
    fireEvent.click(screen.getByRole('button', { name: 'Waive' }));
    fireEvent.click(screen.getByTestId('condition-action-send'));
    expect(screen.getByTestId('waiver-error')).toHaveTextContent('A waiver needs a written reason');
  });

  it('shows an editor why waiving is not theirs', () => {
    wrap(<ConditionsRegister {...props} viewer={{ userId: 'u-owner', role: 'editor' }} conditions={[condition()]} />);
    expect(screen.getByRole('button', { name: 'Waive' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Clear with evidence' })).not.toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'role_decide');
  });
});
