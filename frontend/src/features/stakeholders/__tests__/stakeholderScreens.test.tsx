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
  updateCommitment: vi.fn(),
}));

import { transitionCommitment, updateCommitment } from '../api';
import { CommitmentsPanel } from '../CommitmentsPanel';
import { RegisterPanel, ReadinessStrip } from '../RegisterPanel';
import { GatedButton, RefusalBox } from '../StakeholderBits';
import { canOf, commitment, readiness, screen, settings, stakeholder } from './fixtures';

const transition = vi.mocked(transitionCommitment);
const update = vi.mocked(updateCommitment);

function mount(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const readOnly = () =>
  screen({ settings: settings({ can: { edit: false, read_personal: false, manage_organisation: false } }) });

beforeEach(() => {
  cleanup();
  transition.mockReset();
  update.mockReset();
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
    expect(page.queryByTestId('readiness-overdue')).toBeNull();
  });

  it('names the promises past their due date even while the commitments check is met', () => {
    mount(<ReadinessStrip readiness={readiness({ commitments_tracked: { status: 'met', overdue_refs: ['COM-002', 'COM-005'] } })} />);
    expect(page.getAllByTestId('readiness-check')[4]?.getAttribute('data-status')).toBe('met');
    expect(page.getByTestId('readiness-overdue').textContent).toContain('COM-002');
    expect(page.getByTestId('readiness-overdue').textContent).toContain('COM-005');
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
    expect(page.getByTestId('commitment-entry')).toBeTruthy();
    expect(page.queryByTestId('commitment-moves')).toBeNull();
  });

  it('leave it to the server whether editing exists: shown when it applies, even with no move left', () => {
    const can = canOf('verified', { edit: { applies: true, allowed: false, reason: 'no_permission' } });
    panel([commitment({ status: 'verified', can })]);
    fireEvent.click(page.getByTestId('commitment-filter-closed'));
    expect(moves()).toEqual(['commitment-edit']);
    expect((page.getByTestId('commitment-edit') as HTMLButtonElement).disabled).toBe(true);
    expect(within(page.getByTestId('commitment-blocked')).getByRole('listitem').getAttribute('data-move')).toBe('edit');
  });

  it('keep a move the server switched off visible, unpressable and explained', () => {
    const can = canOf('proposed', {
      agreed: { applies: true, allowed: false, reason: 'not_decider' },
      withdrawn: { applies: true, allowed: false, reason: 'not_decider' },
    });
    panel([commitment({ can })]);
    expect((page.getByTestId('commitment-move-agreed') as HTMLButtonElement).disabled).toBe(true);
    const lines = within(page.getByTestId('commitment-blocked')).getAllByRole('listitem');
    expect(lines.map((li) => li.getAttribute('data-reason'))).toEqual(['not_decider', 'not_decider']);
    expect(lines[0]?.textContent).toBe('Agree: Only whoever decides commitments to stakeholders can do this.');
    fireEvent.click(page.getByTestId('commitment-move-agreed'));
    expect(page.queryByTestId('transition-dialog')).toBeNull();
  });

  it('follow the flag of each commitment, not the role of the reader', () => {
    const viewer = { applies: true, allowed: false, reason: 'no_permission' };
    const can = canOf('proposed', { agreed: viewer, withdrawn: viewer, edit: viewer });
    panel([commitment({ can })], readOnly());
    expect((page.getByTestId('commitment-move-withdrawn') as HTMLButtonElement).disabled).toBe(true);
    // Editing applies here, so it stays visible, switched off, with the reason in words.
    expect((page.getByTestId('commitment-edit') as HTMLButtonElement).disabled).toBe(true);
    const lines = within(page.getByTestId('commitment-blocked')).getAllByRole('listitem');
    expect(lines.map((li) => li.getAttribute('data-move'))).toEqual(['agreed', 'withdrawn', 'edit']);
    expect(lines[2]?.textContent).toBe('Edit: Your role can view commitments but not change them.');
    expect((page.getByTestId('commitment-add') as HTMLButtonElement).disabled).toBe(true);
  });

  it('hides a move the server says does not apply, whatever this screen expects of the state', () => {
    const can = canOf('proposed', { withdrawn: { applies: false, allowed: false, reason: 'invalid_transition' } });
    panel([commitment({ can })]);
    expect(moves()).toEqual(['commitment-move-agreed', 'commitment-edit']);
    expect(page.queryByTestId('commitment-blocked')).toBeNull();
  });

  it('reads a reason it does not know as words, never as a code', () => {
    const can = canOf('fulfilled', { verified: { applies: true, allowed: false, reason: 'brand_new_reason' } });
    panel([commitment({ status: 'fulfilled', can })]);
    expect(within(page.getByTestId('commitment-blocked')).getByRole('listitem').textContent).toContain('Brand new reason');
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

  it('send every field of a proposed commitment on an edit', async () => {
    update.mockResolvedValue(commitment());
    panel([commitment()]);
    fireEvent.click(page.getByTestId('commitment-edit'));
    expect(page.queryByTestId('commitment-frozen')).toBeNull();
    fireEvent.click(page.getByTestId('commitment-save'));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    expect(update.mock.calls[0]?.[2]).toMatchObject({
      text: 'No deliveries before seven in the morning',
      owner_user_id: 'u-owner',
      cost_estimate: null,
    });
  });

  it('keep the wording, cost and owner of an agreed commitment out of an edit, and say why', async () => {
    update.mockResolvedValue(commitment({ status: 'agreed' }));
    panel([commitment({ status: 'agreed' })]);
    fireEvent.click(page.getByTestId('commitment-edit'));
    const dialog = page.getByTestId('commitment-dialog');
    expect(within(dialog).getByTestId('commitment-frozen')).toBeTruthy();
    expect((dialog.querySelector('#commitment-text') as HTMLTextAreaElement).disabled).toBe(true);
    expect((dialog.querySelector('#commitment-cost') as HTMLInputElement).disabled).toBe(true);
    fireEvent.change(dialog.querySelector('#commitment-due') as HTMLInputElement, { target: { value: '2026-12-15' } });
    fireEvent.click(page.getByTestId('commitment-save'));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(1));
    const sent = update.mock.calls[0]?.[2] ?? {};
    expect(sent).toMatchObject({ due_date: '2026-12-15' });
    expect(Object.keys(sent)).not.toEqual(expect.arrayContaining(['text']));
    expect('cost_estimate' in sent || 'currency' in sent || 'owner_user_id' in sent).toBe(false);
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
