// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The commitment screens as a reader meets them: the grid says "unknown"
// where a figure is not known, the release dialog shows who decides before
// anything is sent and shows the server's own words when it refuses, a
// disabled button says the reason the server gave, a tier holder approves or
// rejects on the item, and stopping or handing over an item needs a reason.

import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    previewRelease: vi.fn(),
    requestRelease: vi.fn(),
    listReleases: vi.fn(),
    listAbortTerms: vi.fn(),
    listAbortBases: vi.fn(),
    updateItem: vi.fn(),
    holdItem: vi.fn(),
    withdrawRelease: vi.fn(),
    decideRelease: vi.fn(),
    requestAbort: vi.fn(),
    previewAbort: vi.fn(),
    transferItem: vi.fn(),
    listTransferTargets: vi.fn(),
    getReferences: vi.fn(),
  };
});

import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ReasonedButton } from '../CommitmentBits';
import { CommitmentGrid } from '../CommitmentGrid';
import { ExposureBlock, ItemPanel, ReleaseHistory } from '../ItemPanel';
import { ReleaseDialog, approverNames } from '../ReleaseDialog';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';
import {
  READER_CAN,
  abortPreview,
  can,
  exposure,
  item,
  link,
  matrix,
  nothingBound,
  precondition,
  preview,
  release,
  totals,
} from './fixtures';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = (id: string | null | undefined) => (id === 'u-owner' ? 'Dana Weber' : null);
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.listReleases.mockResolvedValue(page([]));
  mocked.listAbortTerms.mockResolvedValue(page([]));
  mocked.listAbortBases.mockResolvedValue(page([]));
  mocked.listTransferTargets.mockResolvedValue([]);
  mocked.previewAbort.mockResolvedValue(abortPreview());
  mocked.getReferences.mockResolvedValue({
    has_model: false,
    gates: [],
    areas: [],
    frame_documents: [],
    funding_applications: [],
  });
});
afterEach(cleanup);

describe('CommitmentGrid', () => {
  const works = item();
  const lifts = item({
    id: 'i2',
    code: 'CR-002',
    title: 'Lift order',
    commitment_type: 'supplies',
    status: 'committed',
    committed: '1700000.00',
    released: '1500000.00',
    over_release: true,
    decision_overdue: true,
    open_preconditions: 2,
    exposure: exposure({ residual_loss: null, reason: 'abort_terms_missing' }),
  });

  it('shows each item with its type, tier and state in words', () => {
    wrap(<CommitmentGrid items={[works, lifts]} totals={totals()} matrix={matrix()} labels={labels} onOpenItem={() => undefined} />);
    const rows = screen.getAllByTestId('grid-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByText('Structural works package')).toBeInTheDocument();
    expect(within(rows[0]!).getByTestId('grid-status').textContent).toBe(enT('commitment.status.planned'));
    expect(within(rows[1]!).getByTestId('grid-open-preconditions').textContent).toContain('2');
    expect(within(rows[1]!).getByTestId('grid-overdue')).toBeInTheDocument();
  });

  it('says why the abort cost is unknown instead of printing a zero', () => {
    wrap(<CommitmentGrid items={[works, lifts]} totals={totals()} matrix={matrix()} labels={labels} onOpenItem={() => undefined} />);
    const cells = screen.getAllByTestId('grid-residual');
    expect(cells[0]!.textContent).toBe('Nothing committed');
    expect(cells[1]!.textContent).toBe('Unknown: abort terms missing');
  });

  it('the released column is what is in force, with the lapsed part as a second line, per row and in the totals', () => {
    const renewed = item({ id: 'i9', released: '800000.00', released_in_force: '500000.00', released_lapsed: '300000.00' });
    wrap(
      <CommitmentGrid
        items={[renewed, works]}
        totals={totals({ released: '840000.00', released_in_force: '540000.00', released_lapsed: '300000.00' })}
        matrix={matrix()}
        labels={labels}
        onOpenItem={() => undefined}
      />,
    );
    const rows = screen.getAllByTestId('grid-row');
    expect(rows[0]!.textContent).toMatch(/500[,.\s]?000/);
    expect(rows[0]!.textContent).not.toMatch(/800[,.\s]?000/);
    expect(within(rows[0]!).getByTestId('grid-released-lapsed').textContent).toMatch(/300[,.\s]?000/);
    expect(within(rows[1]!).queryByTestId('grid-released-lapsed')).toBeNull();
    const total = screen.getByTestId('grid-totals');
    expect(total.textContent).toMatch(/540[,.\s]?000/);
    expect(total.textContent).not.toMatch(/840[,.\s]?000/);
    expect(within(total).getByTestId('grid-totals-lapsed').textContent).toMatch(/300[,.\s]?000/);
  });

  it('names the column a total leaves an item out of', () => {
    wrap(
      <CommitmentGrid
        items={[works]}
        totals={totals({ mixed_currency: true, incomplete: ['planned'] })}
        matrix={matrix()}
        labels={labels}
        onOpenItem={() => undefined}
      />,
    );
    expect(screen.getByTestId('grid-mixed-currency')).toBeInTheDocument();
    expect(screen.getByTestId('grid-totals-incomplete').textContent).toContain('Planned');
  });

  it('an in-force total that leaves an item out is said once under the released column, and no lapsed sum is invented', () => {
    wrap(
      <CommitmentGrid
        items={[works]}
        totals={totals({
          released_in_force: null,
          released_lapsed: null,
          committed: null,
          incomplete: ['released', 'released_in_force', 'committed'],
        })}
        matrix={matrix()}
        labels={labels}
        onOpenItem={() => undefined}
      />,
    );
    const lines = within(screen.getByTestId('grid-totals-incomplete')).getAllByRole('listitem');
    expect(lines.map((li) => li.textContent)).toEqual([
      enT('commitment.grid.total_incomplete', { column: enT('commitment.grid.released') }),
      enT('commitment.grid.total_incomplete', { column: enT('commitment.grid.committed') }),
    ]);
    expect(screen.queryByTestId('grid-totals-lapsed')).toBeNull();
  });

  it('opens the item that was clicked and groups by type on request', () => {
    const onOpen = vi.fn();
    wrap(<CommitmentGrid items={[works, lifts]} totals={totals()} matrix={matrix()} labels={labels} onOpenItem={onOpen} />);
    fireEvent.click(screen.getByText('Lift order'));
    expect(onOpen).toHaveBeenCalledWith('i2');
    expect(screen.queryAllByTestId('grid-group')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: enT('commitment.grid.group_by_type') }));
    expect(screen.getAllByTestId('grid-group')).toHaveLength(2);
  });
});

describe('ReleaseDialog', () => {
  const open = (over: Parameters<typeof item>[0] = {}, m = matrix()) => {
    const onRequested = vi.fn();
    const onClose = vi.fn();
    wrap(
      <ReleaseDialog
        open
        onClose={onClose}
        projectId="p1"
        item={item({ planned: { amount: '260000.00', currency: 'EUR', note: null }, planned_in_schedule_currency: '260000.00', ...over })}
        matrix={m}
        labels={labels}
        personName={names}
        onRequested={onRequested}
      />,
    );
    return { onRequested, onClose };
  };
  const amountInput = () => document.getElementById('release-amount') as HTMLInputElement;

  it('offers the whole remaining amount and shows the tier and the approver before sending', async () => {
    mocked.previewRelease.mockResolvedValue(preview({ required_tier: 'sponsor', approvers: ['u-owner', 'role:board'] }));
    open({ released: '40000.00' });
    expect(amountInput().value).toBe('220000.00');
    expect((await screen.findByTestId('release-tier')).textContent).toBe(enT('commitment.tier.sponsor'));
    expect(screen.getByTestId('release-approvers').textContent).toBe('Dana Weber and Board');
    expect(mocked.previewRelease).toHaveBeenCalledWith('p1', 'i1', expect.objectContaining({ amount: '220000.00', currency: 'EUR' }));
    expect(screen.getByTestId('release-submit')).not.toBeDisabled();
  });

  it('will not send an amount it cannot read, and says so', () => {
    open();
    fireEvent.change(amountInput(), { target: { value: '40.000,00' } });
    expect(screen.getByTestId('release-submit')).toBeDisabled();
    expect(screen.getByTestId('release-problems').querySelector('[data-problem="amount_invalid"]')).not.toBeNull();
    expect(mocked.requestRelease).not.toHaveBeenCalled();
  });

  it('asks for the external reference when the amount is above every tier', async () => {
    mocked.previewRelease.mockResolvedValue(preview({ escalate_outside: true, required_tier: null, approvers: [] }));
    open();
    expect((await screen.findByTestId('release-tier')).textContent).toContain('outside the schedule');
    expect(screen.getByTestId('release-submit')).toBeDisabled();
    fireEvent.change(document.getElementById('release-external-ref')!, { target: { value: 'Board 2026-14' } });
    expect(screen.getByTestId('release-submit')).not.toBeDisabled();
  });

  it('says that nobody is assigned instead of leaving the approver empty', async () => {
    mocked.previewRelease.mockResolvedValue(preview({ approvers: [] }));
    open();
    expect((await screen.findByTestId('release-approvers')).textContent).toContain('Nobody is assigned');
  });

  it('lists the open preconditions the approver will see', async () => {
    mocked.previewRelease.mockResolvedValue(preview({ open_preconditions: [precondition()] }));
    open();
    const box = await screen.findByTestId('release-open-preconditions');
    expect(box.textContent).toContain('Client brief signed off');
    expect(box.textContent).toContain('The approver will see them');
  });

  it('sends the request once and closes', async () => {
    mocked.previewRelease.mockResolvedValue(preview());
    mocked.requestRelease.mockResolvedValue(release());
    const { onRequested, onClose } = open();
    await screen.findByTestId('release-tier');
    fireEvent.click(screen.getByTestId('release-submit'));
    await waitFor(() => expect(onRequested).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mocked.requestRelease).toHaveBeenCalledWith('p1', 'i1', {
      amount: '260000.00',
      currency: 'EUR',
      tranche_note: '',
      external_approval_ref: '',
    });
  });

  it('shows the server reason and the blocking precondition when the request is refused', async () => {
    mocked.previewRelease.mockResolvedValue(preview());
    mocked.requestRelease.mockRejectedValue(
      new ApiError(409, 'Conflict', {
        detail: {
          code: 'preconditions_open',
          message_key: 'commitment.errors.preconditions_open',
          message: 'Open preconditions block this release',
          violations: [{ code: 'precondition_open', ref: 'pre1', kind: 'manual' }],
        },
      }),
    );
    const { onClose } = open({ preconditions: [precondition()] });
    await screen.findByTestId('release-tier');
    fireEvent.click(screen.getByTestId('release-submit'));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.preconditions_open'));
    expect(alert.textContent).toContain('Client brief signed off');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('names approvers by person, by role, and never by id', () => {
    expect(approverNames(['u-owner', 'role:finance_director', 'u-gone'], names, 'Project member')).toBe(
      'Dana Weber, Finance director, and Project member',
    );
  });
});

describe('ReasonedButton', () => {
  it('says the server reason in the words written for the button', () => {
    wrap(
      <ReasonedButton verdict="four_eyes_violation" data-testid="btn">
        Approve
      </ReasonedButton>,
    );
    expect(screen.getByTestId('btn')).toBeDisabled();
    expect(screen.getByTestId('disabled-reason').textContent).toBe(enT('commitment.disabled.four_eyes_violation'));
  });

  it('a code without a button sentence reads as its refusal sentence, never as a raw code', () => {
    wrap(
      <ReasonedButton verdict="fx_rate_missing" data-testid="btn">
        Request release
      </ReasonedButton>,
    );
    expect(screen.getByTestId('disabled-reason').textContent).toBe(enT('commitment.errors.fx_rate_missing'));
  });

  it('stays visible, disabled, and says who can act', () => {
    wrap(
      <ReasonedButton verdict="manage_required" data-testid="btn">
        Put on hold
      </ReasonedButton>,
    );
    expect(screen.getByTestId('btn')).toBeDisabled();
    const reason = screen.getByTestId('disabled-reason');
    expect(reason.getAttribute('data-reason')).toBe('manage_required');
    expect(reason.textContent).toBe(enT('commitment.disabled.manage_required'));
    expect(screen.getByTestId('btn').getAttribute('aria-describedby')).toBe(reason.id);
  });

  it('carries no reason when the action is allowed', () => {
    wrap(
      <ReasonedButton verdict={null} data-testid="btn">
        Put on hold
      </ReasonedButton>,
    );
    expect(screen.getByTestId('btn')).not.toBeDisabled();
    expect(screen.queryByTestId('disabled-reason')).toBeNull();
  });
});

describe('ExposureBlock and ReleaseHistory', () => {
  it('an item with nothing committed says so in a sentence', () => {
    wrap(<ExposureBlock exposure={nothingBound()} labels={labels} />);
    expect(screen.getByTestId('exposure-nothing')).toBeInTheDocument();
    expect(screen.queryByTestId('exposure-residual')).toBeNull();
  });

  it('an unknown residual names its reason, and an unconfirmed basis is marked', () => {
    wrap(
      <ExposureBlock
        exposure={exposure({ residual_loss: null, reason: 'abort_terms_missing', basis_review_status: 'ai_drafted_unverified' })}
        labels={labels}
      />,
    );
    expect(screen.getByTestId('exposure-residual').textContent).toBe('Unknown: abort terms missing');
    expect(screen.getByTestId('exposure-unconfirmed')).toBeInTheDocument();
  });

  it('explains the residual with the money already spent, without rows of zeros', () => {
    wrap(
      <ExposureBlock
        exposure={exposure({
          lines: [
            { code: 'paid', amount: '200000.00' },
            { code: 'invoiced_unpaid', amount: '0' },
            { code: 'schedule_milestone', milestone: 'fabrication', amount: '40000.00' },
          ],
        })}
        labels={labels}
      />,
    );
    const list = screen.getByTestId('exposure-lines');
    expect(list.querySelectorAll('li')).toHaveLength(2);
    expect(list.textContent).toContain(enT('commitment.exposure.line.paid'));
    expect(list.textContent).not.toContain(enT('commitment.exposure.line.invoiced_unpaid'));
    expect(list.textContent).toContain('fabrication');
  });

  it('a known residual is printed as money, not as "unknown"', () => {
    wrap(<ExposureBlock exposure={exposure()} labels={labels} />);
    const cell = screen.getByTestId('exposure-residual');
    expect(within(cell).queryByTestId('amount-unknown')).toBeNull();
    expect(cell.textContent).toMatch(/240[,.\s]?000/);
    expect(screen.queryByTestId('exposure-unconfirmed')).toBeNull();
  });

  it('the history is empty in words, and a row carries outcome, tier and note', () => {
    const { unmount } = wrap(<ReleaseHistory releases={[]} matrix={matrix()} labels={labels} personName={names} />);
    expect(screen.getByTestId('history-empty')).toBeInTheDocument();
    unmount();
    wrap(
      <ReleaseHistory
        releases={[release({ outcome: 'released', decided_by: 'u-owner', decided_at: '2026-10-11T10:00:00Z' })]}
        matrix={matrix()}
        labels={labels}
        personName={names}
      />,
    );
    const row = screen.getByTestId('history-row');
    expect(row.textContent).toContain(enT('commitment.release.outcome.released'));
    expect(row.textContent).toContain(enT('commitment.tier.project_manager'));
    expect(row.textContent).toContain('First tranche: concept design');
    expect(row.textContent).toContain('Dana Weber');
    expect(screen.getByTestId('history-purpose').textContent).toBe(enT('commitment.release.purpose.release'));
  });

  it('an abort row is told apart from a release row, and a coded rationale reads as words', () => {
    wrap(
      <ReleaseHistory
        releases={[release({ purpose: 'abort', outcome: 'rejected', rationale: 'decider_not_tier_holder' })]}
        matrix={matrix()}
        labels={labels}
        personName={names}
      />,
    );
    const row = screen.getByTestId('history-row');
    expect(screen.getByTestId('history-purpose').textContent).toBe(enT('commitment.release.purpose.abort'));
    expect(row.textContent).not.toContain('decider_not_tier_holder');
    expect(row.textContent).toContain('holder of the required tier');
  });
});

describe('ItemPanel', () => {
  const pendingCan = can({
    request_release: 'release_pending',
    request_abort: 'release_pending',
    hold: 'invalid_transition',
    resume: 'invalid_transition',
    transfer: 'release_pending',
  });
  const waiting = { status: 'release_requested', pending_release_id: 'rel1', pending_purpose: 'release' } as const;
  const other = item({ id: 'i2', code: 'CR-002', title: 'Lift order' });

  const panel = (over: Parameters<typeof item>[0] = {}, others = [other]) => {
    const onChanged = vi.fn();
    const onOpenItem = vi.fn();
    wrap(
      <ItemPanel
        projectId="p1"
        item={item(over)}
        matrix={matrix()}
        otherItems={others}
        labels={labels}
        personName={names}
        onBack={() => undefined}
        onOpenItem={onOpenItem}
        onChanged={onChanged}
      />,
    );
    return { onChanged, onOpenItem };
  };
  const reasonOf = (testId: string) =>
    screen.getByTestId(testId).parentElement!.querySelector('[data-testid="disabled-reason"]')?.getAttribute('data-reason') ?? null;

  it('a button the server refuses is disabled and carries the server reason', () => {
    panel({ can: READER_CAN });
    expect(screen.getByTestId('item-request-release')).toBeDisabled();
    expect(reasonOf('item-request-release')).toBe('not_item_owner');
    expect(screen.getByTestId('item-edit')).toBeDisabled();
    expect(reasonOf('item-hold')).toBe('manage_required');
    expect(reasonOf('item-transfer')).toBe('manage_required');
    expect(reasonOf('item-abort')).toBe('not_item_owner');
  });

  it('an owner of a planned item may request, edit, hold, stop and hand over', () => {
    panel();
    for (const id of ['item-request-release', 'item-edit', 'item-hold', 'item-defer', 'item-abort', 'item-transfer']) {
      expect(screen.getByTestId(id), id).not.toBeDisabled();
    }
    expect(screen.queryByTestId('item-pending')).toBeNull();
  });

  it('a pending request blocks a second one and can be withdrawn', async () => {
    mocked.withdrawRelease.mockResolvedValue(release({ outcome: 'withdrawn' }));
    const { onChanged } = panel({ ...waiting, can: pendingCan });
    expect(screen.getByTestId('item-pending')).toBeInTheDocument();
    expect(screen.getByTestId('item-request-release')).toBeDisabled();
    expect(reasonOf('item-request-release')).toBe('release_pending');
    fireEvent.click(screen.getByTestId('item-withdraw'));
    // A withdrawal may carry a reason but does not need one.
    expect(screen.getByTestId('item-action-send')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('item-action-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.withdrawRelease).toHaveBeenCalledWith('p1', 'i1', '');
  });

  it('shows the decider what was asked and sends an approval with its conditions', async () => {
    mocked.listReleases.mockResolvedValue(
      page([release({ snapshot: { four_eyes: true, preconditions: [precondition()] } })]),
    );
    mocked.decideRelease.mockResolvedValue(release({ outcome: 'released' }));
    const { onChanged } = panel({ ...waiting, can: pendingCan });
    expect((await screen.findByTestId('pending-tier')).textContent).toBe(enT('commitment.tier.project_manager'));
    expect(screen.getByTestId('pending-open-preconditions').textContent).toContain('Client brief signed off');
    expect(screen.getByTestId('pending-four-eyes')).toBeInTheDocument();
    fireEvent.click(await screen.findByTestId('decide-approve'));
    // An approval needs no comment.
    expect(screen.getByTestId('decide-send')).not.toBeDisabled();
    fireEvent.change(document.getElementById('decide-conditions')!, { target: { value: ' Only after the survey ' } });
    fireEvent.change(document.getElementById('decide-valid-until')!, { target: { value: '2026-12-31' } });
    fireEvent.click(screen.getByTestId('decide-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.decideRelease).toHaveBeenCalledWith('p1', 'i1', {
      decision: 'approved',
      comment: '',
      conditions: 'Only after the survey',
      valid_until: '2026-12-31',
    });
  });

  it('a rejection is not sent without a written reason', async () => {
    mocked.decideRelease.mockResolvedValue(release({ outcome: 'rejected' }));
    const { onChanged } = panel({ ...waiting, can: pendingCan });
    fireEvent.click(await screen.findByTestId('decide-reject'));
    expect(screen.getByTestId('decide-send')).toBeDisabled();
    expect(document.getElementById('decide-conditions')).toBeNull();
    fireEvent.change(document.getElementById('decide-comment')!, { target: { value: 'The tender is not evaluated yet' } });
    fireEvent.click(screen.getByTestId('decide-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.decideRelease).toHaveBeenCalledWith('p1', 'i1', {
      decision: 'rejected',
      comment: 'The tender is not evaluated yet',
      conditions: '',
      valid_until: null,
    });
  });

  it.each(['four_eyes_violation', 'not_entitled_decider'])(
    'whoever may not decide sees why (%s) and gets no reject button',
    async (reason) => {
      panel({ ...waiting, can: { ...pendingCan, decide: { allowed: false, reason } } });
      expect(await screen.findByTestId('decide-approve')).toBeDisabled();
      expect(reasonOf('decide-approve')).toBe(reason);
      expect(screen.queryByTestId('decide-reject')).toBeNull();
    },
  );

  it('a refused decision shows the server sentence and keeps the form', async () => {
    mocked.decideRelease.mockRejectedValue(
      new ApiError(403, 'Forbidden', { detail: { code: 'four_eyes_violation', message: 'Four eyes' } }),
    );
    const { onChanged } = panel({ ...waiting, can: pendingCan });
    fireEvent.click(await screen.findByTestId('decide-approve'));
    fireEvent.click(screen.getByTestId('decide-send'));
    const alert = await within(screen.getByTestId('decide-form')).findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.four_eyes_violation'));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('a request to stop the item reads as one, down to the amount label', async () => {
    mocked.listReleases.mockResolvedValue(page([release({ purpose: 'abort', tranche_note: 'Client cancelled the wing' })]));
    panel({ ...waiting, pending_purpose: 'abort', can: pendingCan });
    const box = screen.getByTestId('item-pending');
    expect(box.textContent).toContain('A request to stop this item is waiting for a decision.');
    expect((await screen.findByTestId('pending-summary')).textContent).toContain('Residual loss');
    expect(screen.getByTestId('pending-summary').textContent).toContain('Client cancelled the wing');
    fireEvent.click(await screen.findByTestId('decide-approve'));
    expect(screen.getByTestId('decide-send').textContent).toBe('Approve the abort');
    expect(document.getElementById('decide-conditions')).toBeNull();
  });

  it('a deferral is not sent without a reason', async () => {
    mocked.updateItem.mockResolvedValue(item({ deferred: true }));
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-defer'));
    expect(screen.getByTestId('item-action-send')).toBeDisabled();
    fireEvent.change(document.getElementById('item-action-reason')!, { target: { value: ' Waiting for the survey ' } });
    fireEvent.click(screen.getByTestId('item-action-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.updateItem).toHaveBeenCalledWith('p1', 'i1', { deferred: true, deferred_reason: 'Waiting for the survey' });
  });

  it('deferring is off for an item that left the planned state', () => {
    panel({ status: 'released', can: can({ defer: 'field_frozen' }) });
    expect(screen.getByTestId('item-defer')).toBeDisabled();
    expect(reasonOf('item-defer')).toBe('field_frozen');
  });

  it('shows the server reason when an action is refused and keeps the form open', async () => {
    mocked.updateItem.mockRejectedValue(
      new ApiError(403, 'Forbidden', {
        detail: { code: 'manage_required', message_key: 'commitment.errors.manage_required', message: 'Manage required' },
      }),
    );
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-defer'));
    fireEvent.change(document.getElementById('item-action-reason')!, { target: { value: 'Later' } });
    fireEvent.click(screen.getByTestId('item-action-send'));
    const alert = await within(screen.getByTestId('item-action-form')).findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.manage_required'));
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('an abort request needs a reason and goes to the server without a date', async () => {
    mocked.requestAbort.mockResolvedValue(release({ purpose: 'abort' }));
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-abort'));
    // Who decides is shown before anything is sent: the loss, the tier and the person.
    await screen.findByTestId('abort-preview');
    expect(mocked.previewAbort).toHaveBeenCalledWith('p1', 'i1');
    expect(screen.getByTestId('abort-preview-loss').textContent).toMatch(/240[,.\s]?000/);
    expect(screen.getByTestId('abort-preview-tier').textContent).toBe(enT('commitment.tier.project_manager'));
    expect(screen.getByTestId('abort-preview-approvers').textContent).toBe('Dana Weber');
    expect(document.getElementById('end-external-ref')).toBeNull();
    expect(screen.getByTestId('end-send')).toBeDisabled();
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: ' Client cancelled the wing ' } });
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.requestAbort).toHaveBeenCalledWith('p1', 'i1', 'Client cancelled the wing', '');
  });

  it('an abort cannot be sent while who decides it is not known', async () => {
    let answer: (value: ReturnType<typeof abortPreview>) => void = () => undefined;
    mocked.previewAbort.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    panel();
    fireEvent.click(screen.getByTestId('item-abort'));
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: 'Stop' } });
    expect(screen.getByTestId('abort-preview-loading')).toBeInTheDocument();
    expect(screen.getByTestId('end-send')).toBeDisabled();
    answer(abortPreview());
    await screen.findByTestId('abort-preview');
    expect(screen.getByTestId('end-send')).not.toBeDisabled();
  });

  it('an abort above every tier asks for the external reference before the click, and sends it', async () => {
    mocked.previewAbort.mockResolvedValue(
      abortPreview({ escalate_outside: true, external_approval_required: true, required_tier: null, approvers: [] }),
    );
    mocked.requestAbort.mockResolvedValue(release({ purpose: 'abort' }));
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-abort'));
    await screen.findByTestId('abort-preview');
    expect(screen.getByTestId('abort-preview-tier').textContent).toBe(enT('commitment.release.escalate_outside'));
    expect(screen.queryByTestId('abort-preview-approvers')).toBeNull();
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: 'Client cancelled the wing' } });
    expect(screen.getByTestId('end-send')).toBeDisabled();
    fireEvent.change(document.getElementById('end-external-ref')!, { target: { value: ' Board 2026-14 ' } });
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.requestAbort).toHaveBeenCalledTimes(1);
    expect(mocked.requestAbort).toHaveBeenCalledWith('p1', 'i1', 'Client cancelled the wing', 'Board 2026-14');
  });

  it('a refusal of the request can still ask for the reference, when the loss moved after the preview', async () => {
    mocked.requestAbort.mockRejectedValueOnce(
      new ApiError(422, 'Unprocessable', {
        detail: { code: 'external_approval_required', message: 'The amount is above every tier' },
      }),
    );
    mocked.requestAbort.mockResolvedValueOnce(release({ purpose: 'abort' }));
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-abort'));
    await screen.findByTestId('abort-preview');
    expect(document.getElementById('end-external-ref')).toBeNull();
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: 'Client cancelled the wing' } });
    fireEvent.click(screen.getByTestId('end-send'));
    const alert = await within(screen.getByTestId('end-form')).findByRole('alert');
    expect(alert.textContent).toContain(enT('commitment.errors.external_approval_required'));
    // The reference is now required: the request cannot go again without it.
    expect(screen.getByTestId('end-send')).toBeDisabled();
    fireEvent.change(document.getElementById('end-external-ref')!, { target: { value: ' Board 2026-14 ' } });
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.requestAbort).toHaveBeenLastCalledWith('p1', 'i1', 'Client cancelled the wing', 'Board 2026-14');
  });

  it('an abort the server cannot size is refused in words that say what to do', async () => {
    mocked.previewAbort.mockRejectedValue(
      new ApiError(422, 'Unprocessable', { detail: { code: 'abort_exposure_unknown', message: 'unknown' } }),
    );
    panel();
    fireEvent.click(screen.getByTestId('item-abort'));
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: 'Stop' } });
    // It is said when the form opens, not after a click that could only be refused.
    const alert = await within(screen.getByTestId('end-form')).findByRole('alert');
    expect(alert.textContent).toContain('Complete the abort terms first');
    expect(screen.getByTestId('abort-preview-retry')).toBeInTheDocument();
    expect(screen.getByTestId('end-send')).toBeDisabled();
    expect(mocked.requestAbort).not.toHaveBeenCalled();
  });

  const here = (items: Array<{ id: string; code: string; title: string }>) => [
    { project_id: 'p1', project_name: 'Riverside offices', same_project: true, can: { allowed: true, reason: null }, items },
  ];

  it('a hand-over needs a target item and a reason', async () => {
    mocked.listTransferTargets.mockResolvedValue(here([{ id: 'i2', code: 'CR-002', title: 'Lift order' }]));
    mocked.transferItem.mockResolvedValue(item({ status: 'transferred' }));
    const { onChanged } = panel();
    fireEvent.click(screen.getByTestId('item-transfer'));
    fireEvent.change(document.getElementById('end-reason')!, { target: { value: 'Merged into the lift order' } });
    expect(screen.getByTestId('end-send')).toBeDisabled();
    await waitFor(() => expect(document.getElementById('end-target')).not.toBeNull());
    fireEvent.change(document.getElementById('end-target')!, { target: { value: 'i2' } });
    fireEvent.click(screen.getByTestId('end-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.transferItem).toHaveBeenCalledWith('p1', 'i1', {
      target_item_id: 'i2',
      reason: 'Merged into the lift order',
    });
  });

  it('a hand-over with no other open item says what to do first', async () => {
    // The server lists the open items; an ended one in the grid is not a target.
    mocked.listTransferTargets.mockResolvedValue(here([]));
    panel({}, [item({ id: 'i3', code: 'CR-003', status: 'aborted' })]);
    fireEvent.click(screen.getByTestId('item-transfer'));
    expect(await screen.findByTestId('transfer-no-target')).toBeInTheDocument();
    expect(document.getElementById('end-target')).toBeNull();
  });

  it('a stopped item shows what was decided and what is left to do by hand', () => {
    panel({
      status: 'aborted',
      can: can({ edit: 'item_closed', link: 'item_closed', request_release: 'invalid_transition', request_abort: 'invalid_transition' }),
      links: [link()],
      abort: {
        release_id: 'rel9',
        decided_at: '2026-10-11T10:00:00Z',
        decided_by: 'u-owner',
        reason: 'Client cancelled the wing',
        residual_loss: '240000.00',
        currency: 'EUR',
        follow_up: [{ kind: 'contract', document_id: 'doc1', action: 'terminate', status: 'active' }],
      },
    });
    const box = screen.getByTestId('abort-outcome');
    expect(box.textContent).toContain('Client cancelled the wing');
    expect(box.textContent).toContain('Dana Weber');
    expect(screen.getByTestId('abort-residual').textContent).toMatch(/240[,.\s]?000/);
    expect(screen.getByTestId('abort-follow-up').textContent).toContain(enT('commitment.abort.follow_up.terminate'));
    // An ended item offers neither a stop nor a hand-over.
    expect(screen.queryByTestId('end-item')).toBeNull();
  });

  it('a handed-over item names the item that took over and opens it', () => {
    const { onOpenItem } = panel({ status: 'transferred', transferred_to_item_id: 'i2' });
    expect(screen.getByTestId('item-transferred')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('item-successor'));
    expect(onOpenItem).toHaveBeenCalledWith('i2');
  });

  it('an item handed over to another project says so instead of pointing at nothing', () => {
    panel({ status: 'transferred', transferred_to_item_id: 'item-of-another-project' });
    expect(screen.getByTestId('item-transferred')).toHaveTextContent(enT('commitment.item.transferred_elsewhere'));
    expect(screen.queryByTestId('item-successor')).toBeNull();
  });

  const takenBy = (over: Partial<NonNullable<ReturnType<typeof item>['transferred_to']>> = {}) => ({
    project_id: 'p2',
    item_id: 'j1',
    same_project: false,
    can_open: true,
    project_name: 'Harbour depot',
    code: 'CR-101',
    title: 'Depot lifts',
    ...over,
  });

  it('an item handed to another project names that project and links the item there', () => {
    panel({ status: 'transferred', transferred_to_item_id: 'j1', transferred_to: takenBy() });
    expect(screen.getByTestId('item-transferred')).toHaveTextContent('Harbour depot');
    const there = screen.getByTestId('item-successor-elsewhere');
    expect(there).toHaveAttribute('href', '/projects/p2/commitments?item=j1');
    expect(there).toHaveTextContent('CR-101 Depot lifts');
    expect(screen.queryByTestId('item-successor')).toBeNull();
  });

  it('a receiving project the reader may not open is neither named nor linked', () => {
    panel({
      status: 'transferred',
      transferred_to_item_id: 'j1',
      transferred_to: takenBy({ can_open: false, project_name: null, code: null, title: null }),
    });
    expect(screen.getByTestId('item-transferred')).toHaveTextContent(enT('commitment.item.transferred_elsewhere'));
    expect(screen.queryByTestId('item-successor-elsewhere')).toBeNull();
    expect(screen.queryByTestId('item-successor')).toBeNull();
  });

  it('the successor the server names opens here even when the grid has not loaded it', () => {
    const { onOpenItem } = panel(
      {
        status: 'transferred',
        transferred_to_item_id: 'i9',
        transferred_to: takenBy({ project_id: 'p1', item_id: 'i9', same_project: true, code: 'CR-009', title: 'Lift order' }),
      },
      [],
    );
    fireEvent.click(screen.getByTestId('item-successor'));
    expect(onOpenItem).toHaveBeenCalledWith('i9');
  });

  it('a release past its validity date is said on the item, with the date and what is still in force', () => {
    panel({
      status: 'released',
      released: '500000.00',
      released_in_force: '200000.00',
      released_lapsed: '300000.00',
      release_expired: true,
      expired_release_dates: ['2026-08-31', '2026-09-30'],
    });
    const notice = screen.getByTestId('item-release-expired');
    expect(notice.textContent).toContain('nothing new can be bound');
    expect(notice.textContent).not.toContain('{{date}}');
    // The headline is what still authorises money; what lapsed is the line under it.
    expect(screen.getByTestId('item-released').textContent).toMatch(/200[,.\s]?000/);
    expect(screen.getByTestId('item-released-lapsed').textContent).toMatch(/300[,.\s]?000/);
  });

  it('after a renewal the lapsed part stays visible as a figure, without the warning', () => {
    panel({
      status: 'released',
      released: '800000.00',
      released_in_force: '500000.00',
      released_lapsed: '300000.00',
      release_expired: false,
      expired_release_dates: ['2026-09-30'],
    });
    expect(screen.queryByTestId('item-release-expired')).toBeNull();
    expect(screen.getByTestId('item-released').textContent).toMatch(/500[,.\s]?000/);
    expect(screen.getByTestId('item-released-lapsed').textContent).toMatch(/300[,.\s]?000/);
  });

  it('an item whose releases are all in date shows neither the notice nor a lapsed line', () => {
    panel({ status: 'released', released: '500000.00', released_in_force: '500000.00', release_expired: false });
    expect(screen.queryByTestId('item-release-expired')).toBeNull();
    expect(screen.getByTestId('item-released').textContent).toMatch(/500[,.\s]?000/);
    expect(screen.queryByTestId('item-released-lapsed')).toBeNull();
  });

  it('the lead time shown is the one in force, with whose it is, not the figure typed on the item', () => {
    panel({
      lead_time_days: 45,
      lead_time_in_force_days: 120,
      lead_time_source: 'plant_item',
      plant_item_id: 'pl1',
      plant_item_code: 'TC-01',
      date_basis: 'plant_item',
    });
    const figure = screen.getByTestId('item-lead-time');
    expect(figure.textContent).toBe('120');
    expect(screen.getByText(enT('commitment.lead_time_source.plant_item_named', { code: 'TC-01' }))).toBeInTheDocument();
    expect(screen.getByText(enT('commitment.date_basis.plant_item'))).toBeInTheDocument();
  });

  it('a plant item the register no longer knows is still named as the source, without a code', () => {
    panel({ lead_time_in_force_days: 120, lead_time_source: 'plant_item', plant_item_id: 'pl1', plant_item_code: null });
    expect(screen.getByText(enT('commitment.lead_time_source.plant_item'))).toBeInTheDocument();
  });

  it('an answer without a lead time in force shows no lead time figure', () => {
    panel();
    expect(screen.queryByTestId('item-lead-time')).toBeNull();
  });

  it('warns when more is bound than released, with the difference', () => {
    panel({ status: 'committed', committed: '1700000.00', released: '1500000.00', over_release: true });
    const warning = screen.getByTestId('item-over-release');
    expect(warning.textContent).toMatch(/200[,.\s]?000/);
  });
});
