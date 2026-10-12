// @vitest-environment jsdom
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The register and the commitments as a reader meets them: the empty state,
// buttons that follow the capability flags the server sent, the moves a
// commitment offers in each state, and a refused move showing the server's
// own sentence.

import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen as page, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { ApiError } from '@/shared/lib/api';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('@/shared/ui/ContactSearchInput', () => ({ ContactSearchInput: () => null }));
vi.mock('../api', async (original) => ({
  ...(await original<typeof import('../api')>()),
  transitionCommitment: vi.fn(),
}));

import { transitionCommitment } from '../api';
import { CommitmentsPanel } from '../CommitmentsPanel';
import { RegisterPanel, ReadinessStrip } from '../RegisterPanel';
import { GatedButton, RefusalBox } from '../StakeholderBits';
import { commitment, readiness, screen, settings, stakeholder } from './fixtures';

const transition = vi.mocked(transitionCommitment);

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const readOnly = () =>
  screen({ settings: settings({ can: { edit: false, read_personal: false, manage_organisation: false } }) });

beforeEach(() => {
  cleanup();
  transition.mockReset();
});

describe('a button that follows a server flag', () => {
  it('works when the flag is on and says nothing more', () => {
    const onClick = vi.fn();
    mount(
      <GatedButton allowed capability="edit" onClick={onClick}>
        Add
      </GatedButton>,
    );
    fireEvent.click(page.getByRole('button', { name: 'Add' }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(page.queryByTestId('disabled-reason')).toBeNull();
  });

  it('stays visible when the flag is off, cannot be pressed and says who can act', () => {
    const onClick = vi.fn();
    mount(
      <GatedButton allowed={false} capability="organisation" onClick={onClick}>
        Add
      </GatedButton>,
    );
    const button = page.getByRole('button', { name: 'Add' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    const reason = page.getByTestId('disabled-reason');
    expect(reason.textContent).toBe('Only a project manager can change the organisation and the mandates.');
    expect(button.getAttribute('aria-describedby')).toBe(reason.id);
  });
});

describe('a refused write', () => {
  it('shows the sentence and every blocker in words', () => {
    mount(
      <RefusalBox
        refusal={{
          code: 'two_deciders',
          message: 'A decision type may have only one deciding role or body per scope',
          violations: [{ decision_type: 'order_award', scope: 'lot_2' }, { unrelated: 1 }],
        }}
      />,
    );
    const box = page.getByRole('alert');
    expect(box.getAttribute('data-code')).toBe('two_deciders');
    expect(within(box).getByText('A decision type may have only one deciding role or body per scope')).toBeTruthy();
    expect(within(box).getAllByRole('listitem').map((li) => li.textContent)).toEqual(['Order award / Lot 2']);
  });

  it('renders nothing when nothing was refused', () => {
    const { container } = mount(<RefusalBox refusal={null} />);
    expect(container.textContent).toBe('');
  });
});

describe('the register', () => {
  const noop = () => undefined;

  it('explains itself when it is empty and offers the one action', () => {
    const onAdd = vi.fn();
    mount(<RegisterPanel screen={screen()} stakeholders={[]} readiness={undefined} onOpen={noop} onAdd={onAdd} />);
    expect(page.getByText('No stakeholders yet')).toBeTruthy();
    expect(page.queryByTestId('register-table')).toBeNull();
    fireEvent.click(page.getByTestId('stakeholder-add'));
    expect(onAdd).toHaveBeenCalledTimes(1);
  });

  it('a viewer sees the add button switched off with the reason', () => {
    mount(<RegisterPanel screen={readOnly()} stakeholders={[]} readiness={undefined} onOpen={noop} onAdd={noop} />);
    expect((page.getByTestId('stakeholder-add') as HTMLButtonElement).disabled).toBe(true);
    expect(page.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('edit');
  });

  it('names the class, the category, the engagement pair and the person who keeps the relationship', () => {
    mount(<RegisterPanel screen={screen()} stakeholders={[stakeholder()]} readiness={undefined} onOpen={noop} onAdd={noop} />);
    const row = page.getByTestId('register-row');
    expect(within(row).getByText('Building authority')).toBeTruthy();
    expect(within(row).getByText('Manage closely')).toBeTruthy();
    expect(within(row).getByText('Permitting authority')).toBeTruthy();
    expect(within(row).getByText('Dana Weber')).toBeTruthy();
    const pair = within(row).getByTestId('engagement-cell');
    expect(pair.textContent).toBe('Neutral / Supportive');
    expect(pair.getAttribute('data-gap')).toBe('true');
  });

  it('opens the stakeholder a row names', () => {
    const onOpen = vi.fn();
    mount(<RegisterPanel screen={screen()} stakeholders={[stakeholder({ id: 's7' })]} readiness={undefined} onOpen={onOpen} onAdd={noop} />);
    fireEvent.click(page.getByTestId('register-open'));
    expect(onOpen).toHaveBeenCalledWith('s7');
  });

  it('does not print the stored name of a person the reader may not see', () => {
    mount(
      <RegisterPanel
        screen={readOnly()}
        stakeholders={[stakeholder({ name: null, masked: true, display_name: 'Resident of number 12', category: 'neighbour' })]}
        readiness={undefined}
        onOpen={noop}
        onAdd={noop}
      />,
    );
    expect(page.getByTestId('register-open').textContent).toBe('Private person (name hidden)');
    expect(page.queryByText(/Resident of number 12/)).toBeNull();
  });

  it('says so when a stakeholder was never assessed', () => {
    mount(
      <RegisterPanel
        screen={screen()}
        stakeholders={[
          stakeholder({ classification: 'not_assessed', engagement_current: null, engagement_desired: null, engagement_gap: null, relationship_owner_user_id: null }),
        ]}
        readiness={undefined}
        onOpen={noop}
        onAdd={noop}
      />,
    );
    const row = page.getByTestId('register-row');
    expect(within(row).getByText('Not assessed')).toBeTruthy();
    expect(within(row).getByText('Not set')).toBeTruthy();
    expect(within(row).getByText('Nobody yet')).toBeTruthy();
  });

  it('filters by what needs attention and keeps archived rows out of the current list', () => {
    const rows = [
      stakeholder({ id: 'a', name: 'Authority', review_due: true, engagement_gap: 0 }),
      stakeholder({ id: 'b', name: 'Utility', review_due: false, engagement_gap: 2 }),
      stakeholder({ id: 'c', name: 'Former tenant', status: 'archived', review_due: true }),
    ];
    mount(<RegisterPanel screen={screen()} stakeholders={rows} readiness={undefined} onOpen={noop} onAdd={noop} />);
    const names = () => page.queryAllByTestId('register-open').map((b) => b.textContent);
    expect(names()).toEqual(['Authority', 'Utility']);
    fireEvent.click(page.getByTestId('register-filter-review_due'));
    expect(names()).toEqual(['Authority']);
    fireEvent.click(page.getByTestId('register-filter-gap'));
    expect(names()).toEqual(['Utility']);
    fireEvent.click(page.getByTestId('register-filter-archived'));
    expect(names()).toEqual(['Former tenant']);
  });

  it('says that a filter matched nothing instead of showing an empty table', () => {
    mount(<RegisterPanel screen={screen()} stakeholders={[stakeholder()]} readiness={undefined} onOpen={noop} onAdd={noop} />);
    fireEvent.click(page.getByTestId('register-filter-archived'));
    expect(page.getByText('No stakeholder matches this filter.')).toBeTruthy();
    expect(page.queryByTestId('register-table')).toBeNull();
  });

  it('lists what the next gate checks, each met or not, in a fixed order', () => {
    mount(<ReadinessStrip readiness={readiness()} />);
    expect(page.getAllByTestId('readiness-check').map((li) => li.getAttribute('data-status'))).toEqual([
      'met',
      'not_met',
      'met',
      'not_met',
      'met',
    ]);
  });
});

describe('the commitments', () => {
  const panel = (list: ReturnType<typeof commitment>[], s = screen()) =>
    mount(<CommitmentsPanel screen={s} commitments={list} stakeholders={[stakeholder()]} events={[]} />);

  const moves = () =>
    within(page.getByTestId('commitment-moves'))
      .getAllByRole('button')
      .map((b) => b.getAttribute('data-testid'));

  it('explain themselves when there are none', () => {
    panel([]);
    expect(page.getByText('No commitments yet')).toBeTruthy();
    expect(page.queryByTestId('commitment-list')).toBeNull();
    expect(page.getByTestId('commitment-add')).toBeTruthy();
  });

  it('show what was promised, to whom, by whom and by when', () => {
    panel([commitment({ overdue: true })]);
    const entry = page.getByTestId('commitment-entry');
    expect(within(entry).getByText('No deliveries before seven in the morning')).toBeTruthy();
    expect(within(entry).getByText('Promised to: Building authority')).toBeTruthy();
    expect(within(entry).getByText('Dana Weber')).toBeTruthy();
    expect(within(entry).getByTestId('commitment-status').textContent).toBe('Proposed');
    expect(within(entry).getByTestId('commitment-overdue')).toBeTruthy();
  });

  it('offer exactly the moves the state allows, plus editing', () => {
    panel([commitment({ status: 'proposed' })]);
    expect(moves()).toEqual(['commitment-move-agreed', 'commitment-move-withdrawn', 'commitment-edit']);
  });

  it('offer nothing on a closed commitment', () => {
    panel([commitment({ status: 'verified' })]);
    fireEvent.click(page.getByTestId('commitment-filter-closed'));
    expect(within(page.getByTestId('commitment-moves')).queryAllByRole('button')).toEqual([]);
  });

  it('offer no moves to a reader who may not edit', () => {
    panel([commitment()], readOnly());
    expect(page.queryByTestId('commitment-moves')).toBeNull();
    expect((page.getByTestId('commitment-add') as HTMLButtonElement).disabled).toBe(true);
  });

  it('say what a commitment waits for while an approval runs, and offer no second move', () => {
    panel([commitment({ pending_target: 'agreed', approval_instance_id: 'ap1' })]);
    expect(page.getByTestId('commitment-pending').textContent).toBe('Waiting for approval to become: Agreed');
    expect(page.queryByTestId('commitment-moves')).toBeNull();
  });

  it('keep the open ones first and count each group', () => {
    panel([commitment({ id: 'a' }), commitment({ id: 'b', status: 'withdrawn', withdraw_rationale: 'Design changed' })]);
    expect(page.getAllByTestId('commitment-entry')).toHaveLength(1);
    expect(page.getByTestId('commitment-filter-closed').textContent).toBe('Closed 1');
    fireEvent.click(page.getByTestId('commitment-filter-closed'));
    expect(page.getByText('Withdrawn because: Design changed')).toBeTruthy();
    fireEvent.click(page.getByTestId('commitment-filter-overdue'));
    expect(page.getByText('No commitment in this group.')).toBeTruthy();
  });

  it('will not send a withdrawal without a reason', () => {
    panel([commitment()]);
    fireEvent.click(page.getByTestId('commitment-move-withdrawn'));
    const dialog = page.getByTestId('transition-dialog');
    expect((within(dialog).getByTestId('transition-submit') as HTMLButtonElement).disabled).toBe(true);
    expect(within(dialog).getByTestId('transition-problems').querySelector('[data-problem="rationale_required"]')).not.toBeNull();
    expect(transition).not.toHaveBeenCalled();
  });

  it('send the move and report that it went for approval', async () => {
    const onChanged = vi.fn();
    transition.mockResolvedValue(commitment({ pending_target: 'agreed' }));
    panel([commitment()], screen({ onChanged }));
    fireEvent.click(page.getByTestId('commitment-move-agreed'));
    fireEvent.click(page.getByTestId('transition-submit'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(transition).toHaveBeenCalledWith('p1', 'c1', expect.objectContaining({ target: 'agreed', create_risk: false }));
    expect(page.queryByTestId('transition-dialog')).toBeNull();
  });

  it('show the reason of the server when it refuses, and keep the dialog open', async () => {
    const onChanged = vi.fn();
    transition.mockRejectedValue(
      new ApiError(403, 'Forbidden', {
        detail: {
          code: 'not_decider',
          message_key: 'stakeholders.errors.not_decider',
          message: 'Only the holder of the deciding role may agree this commitment',
        },
      }),
    );
    panel([commitment()], screen({ onChanged }));
    fireEvent.click(page.getByTestId('commitment-move-agreed'));
    fireEvent.click(page.getByTestId('transition-submit'));
    const refusal = await page.findByTestId('refusal');
    expect(refusal.getAttribute('data-code')).toBe('not_decider');
    expect(refusal.textContent).not.toBe('');
    expect(refusal.textContent).not.toContain('stakeholders.errors');
    expect(page.getByTestId('transition-dialog')).toBeTruthy();
    expect(onChanged).not.toHaveBeenCalled();
  });
});
