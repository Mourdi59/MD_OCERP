// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Who may press which commitment button, and in words why not.
//
// The server decides; this only predicts, so a button is disabled with a
// reason instead of answering with a 403 after the click. The commitment API
// sends no capability flags yet, so the prediction reads what the client has:
// the role (backend `commitment.*` permissions are viewer / editor / manager,
// see commitment_release/permissions.py) and the item state.
// Who may DECIDE a release is not predicted at all: that is whoever the
// approval route of the tier names, and they decide in the approvals inbox.

import type { CommitmentItem, ItemStatus } from './api';
import type { KeyText } from './labels';
import { ROLE_ALIASES, ROLE_RANK } from '@/shared/lib/roles';

export type CommitmentLevel = 'read' | 'edit' | 'manage';

const LEVEL_RANK: Record<CommitmentLevel, number> = { read: 0, edit: 1, manage: 2 };

/**
 * Whether a role reaches a commitment level, ranked by the shared mirror of the
 * backend hierarchy. No role and an unknown role both deny.
 */
export function roleAllows(role: string | null | undefined, level: CommitmentLevel): boolean {
  if (!role) return false;
  const r = role.trim().toLowerCase();
  const canonical = ROLE_ALIASES[r] ?? r;
  const rank = (ROLE_RANK as Record<string, number>)[canonical];
  if (rank === undefined) return false;
  return rank >= LEVEL_RANK[level];
}

export type DisabledReason =
  | 'role_edit'
  | 'role_manage'
  | 'release_pending'
  | 'item_ended'
  | 'item_on_hold'
  | 'item_closed'
  | 'no_pending_release'
  | 'hold_not_possible';

export const DISABLED_REASON: Record<DisabledReason, KeyText> = {
  role_edit: [
    'commitment.disabled.role_edit',
    'Your role can view the commitments but not change them. An editor or manager can.',
  ],
  role_manage: ['commitment.disabled.role_manage', 'Only a project manager can change this.'],
  release_pending: [
    'commitment.disabled.release_pending',
    'A release request for this item is waiting for a decision. Wait for it or withdraw it first.',
  ],
  item_ended: ['commitment.disabled.item_ended', 'This item was aborted or transferred and can no longer change.'],
  item_on_hold: ['commitment.disabled.item_on_hold', 'This item is on hold. A manager resumes it first.'],
  item_closed: ['commitment.disabled.item_closed', 'All linked documents are completed, so the item is closed.'],
  no_pending_release: ['commitment.disabled.no_pending_release', 'There is no release request to withdraw.'],
  hold_not_possible: [
    'commitment.disabled.hold_not_possible',
    'An item can be put on hold only while no release request is running.',
  ],
};

/** null means allowed; otherwise the first reason that stops the action. */
export type Verdict = DisabledReason | null;

export interface Viewer {
  userId: string | null;
  role: string | null;
}

const ENDED: readonly ItemStatus[] = ['aborted', 'transferred'];
const REQUESTABLE: readonly ItemStatus[] = ['planned', 'partially_released', 'released', 'committed', 're_release_required'];
const HOLDABLE: readonly ItemStatus[] = ['planned', 'released', 'partially_released', 'committed', 're_release_required'];

type ItemFacts = Pick<CommitmentItem, 'status' | 'pending_release_id'>;

export function canManage(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'manage') ? null : 'role_manage';
}

export function canAddItem(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}

/**
 * Whether the viewer may ask for a release on this item. The item state
 * explains first, because it holds for everyone.
 */
export function canRequestRelease(viewer: Viewer, item: ItemFacts): Verdict {
  if (ENDED.includes(item.status)) return 'item_ended';
  if (item.status === 'release_requested' || item.pending_release_id) return 'release_pending';
  if (item.status === 'on_hold') return 'item_on_hold';
  if (item.status === 'closed') return 'item_closed';
  if (!REQUESTABLE.includes(item.status)) return 'item_closed';
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}

/** Only the server knows who requested; an editor is offered the button and the server names a refusal. */
export function canWithdraw(viewer: Viewer, item: ItemFacts): Verdict {
  if (!item.pending_release_id) return 'no_pending_release';
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}

/**
 * Editing the item, its links, preconditions and abort terms. The server
 * also asks for the owner, the creator or a manager, and the client cannot
 * see who created the item, so an editor is offered the button and a refusal
 * comes back as the server's own sentence (`not_item_owner`).
 */
export function canEditItem(viewer: Viewer, item: ItemFacts): Verdict {
  if (ENDED.includes(item.status)) return 'item_ended';
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}

export function canHold(viewer: Viewer, item: ItemFacts): Verdict {
  if (ENDED.includes(item.status)) return 'item_ended';
  if (!roleAllows(viewer.role, 'manage')) return 'role_manage';
  if (item.status === 'on_hold') return null;
  return HOLDABLE.includes(item.status) ? null : 'hold_not_possible';
}
