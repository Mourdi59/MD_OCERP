// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The commitment screens as a reader meets them: the grid says "unknown"
// where a figure is not known, the release dialog shows who decides before
// anything is sent and shows the server's own words when it refuses, a
// disabled button says why, and a deferral is not sent without a reason.

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
import { exposure, item, matrix, precondition, preview, release, totals } from './fixtures';

const mocked = vi.mocked(api);
const labels: LabelContext = { t: enT, language: 'en', exists: () => false };
const names = (id: string | null | undefined) => (id === 'u-owner' ? 'Dana Weber' : null);
const editor = { userId: 'u1', role: 'editor' };
const viewer = { userId: 'u3', role: 'viewer' };

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.listReleases.mockResolvedValue([]);
  mocked.listAbortTerms.mockResolvedValue([]);
  mocked.listAbortBases.mockResolvedValue([]);
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
  it('stays visible, disabled, and says who can act', () => {
    wrap(
      <ReasonedButton verdict="role_manage" data-testid="btn">
        Put on hold
      </ReasonedButton>,
    );
    expect(screen.getByTestId('btn')).toBeDisabled();
    const reason = screen.getByTestId('disabled-reason');
    expect(reason.getAttribute('data-reason')).toBe('role_manage');
    expect(reason.textContent).toBe(enT('commitment.disabled.role_manage'));
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
    wrap(<ExposureBlock exposure={exposure({ note: 'nothing_committed', residual_loss: null })} labels={labels} />);
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

  it('a known residual is printed as money, not as "unknown"', () => {
    wrap(<ExposureBlock exposure={exposure()} labels={labels} />);
    const cell = screen.getByTestId('exposure-residual');
    expect(within(cell).queryByTestId('amount-unknown')).toBeNull();
    expect(cell.textContent).toMatch(/240[,.\s  ]?000/);
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
  });
});

describe('ItemPanel', () => {
  const panel = (over: Parameters<typeof item>[0], who = editor) => {
    const onChanged = vi.fn();
    wrap(
      <ItemPanel
        projectId="p1"
        item={item(over)}
        matrix={matrix()}
        viewer={who}
        labels={labels}
        personName={names}
        onBack={() => undefined}
        onChanged={onChanged}
      />,
    );
    return onChanged;
  };

  it('a viewer sees the buttons disabled with the reason', () => {
    panel({}, viewer);
    expect(screen.getByTestId('item-request-release')).toBeDisabled();
    expect(screen.getByTestId('item-edit')).toBeDisabled();
    const reasons = screen.getAllByTestId('disabled-reason').map((n) => n.getAttribute('data-reason'));
    expect(reasons).toContain('role_edit');
  });

  it('a pending request blocks a second one and can be withdrawn', async () => {
    mocked.withdrawRelease.mockResolvedValue(release({ outcome: 'withdrawn' }));
    const onChanged = panel({ status: 'release_requested', pending_release_id: 'rel1' });
    expect(screen.getByTestId('item-pending')).toBeInTheDocument();
    expect(screen.getByTestId('item-request-release')).toBeDisabled();
    fireEvent.click(screen.getByTestId('item-withdraw'));
    // A withdrawal may carry a reason but does not need one.
    expect(screen.getByTestId('item-action-send')).not.toBeDisabled();
    fireEvent.click(screen.getByTestId('item-action-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.withdrawRelease).toHaveBeenCalledWith('p1', 'i1', '');
  });

  it('a deferral is not sent without a reason', async () => {
    mocked.updateItem.mockResolvedValue(item({ deferred: true }));
    const onChanged = panel({});
    fireEvent.click(screen.getByTestId('item-defer'));
    expect(screen.getByTestId('item-action-send')).toBeDisabled();
    fireEvent.change(document.getElementById('item-action-reason')!, { target: { value: ' Waiting for the survey ' } });
    fireEvent.click(screen.getByTestId('item-action-send'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
    expect(mocked.updateItem).toHaveBeenCalledWith('p1', 'i1', { deferred: true, deferred_reason: 'Waiting for the survey' });
  });

  it('shows the server reason when an action is refused and keeps the form open', async () => {
    mocked.updateItem.mockRejectedValue(
      new ApiError(403, 'Forbidden', {
        detail: { code: 'not_item_owner', message_key: 'commitment.errors.not_item_owner', message: 'Only the item owner may do this' },
      }),
    );
    const onChanged = panel({});
    fireEvent.click(screen.getByTestId('item-defer'));
    fireEvent.change(document.getElementById('item-action-reason')!, { target: { value: 'Later' } });
    fireEvent.click(screen.getByTestId('item-action-send'));
    const alert = await screen.findByRole('alert');
    expect(alert.textContent?.trim().length).toBeGreaterThan(10);
    expect(alert.textContent).not.toContain('commitment.errors.');
    expect(screen.getByTestId('item-action-form')).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('warns when more is bound than released, with the difference', () => {
    panel({ status: 'committed', committed: '1700000.00', released: '1500000.00', over_release: true });
    const warning = screen.getByTestId('item-over-release');
    expect(warning.textContent).toMatch(/200[,.\s  ]?000/);
  });
});
