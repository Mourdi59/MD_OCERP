// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Who may press which commitment button, and in words why not.
//
// For everything done to an item the server decides and says so: each item
// carries `can`, computed by the same function that enforces the write, with
// the refusal code when the answer is no. The screens read that flag and never
// work the answer out again from a role, an owner or a state.
//
// Two things have no flag yet because they are not about an item: adding an
// item and changing the approval setup. For those the role is read as a
// prediction only, and a refusal still comes back as the server's sentence.

import type { CanFlag, CommitmentItem, ItemAction } from './api';
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

/**
 * null means allowed; otherwise the code of the reason that stops the action.
 * For an item action that is the server's refusal code.
 */
export type Verdict = string | null;

/** The server did not send the flag. The action stays off: an absent answer is not a yes. */
export const UNAVAILABLE = 'unavailable';

/**
 * Why a button is off, where a sentence written for the button reads better
 * than the refusal sentence of the same code. A code that is not here is shown
 * with its refusal sentence (`commitment.errors.<code>`).
 */
export const DISABLED_REASON: Record<string, KeyText> = {
  role_edit: [
    'commitment.disabled.role_edit',
    'Your role can view the commitments but not change them. An editor or manager can.',
  ],
  role_manage: ['commitment.disabled.role_manage', 'Only a project manager can change this.'],
  manage_required: ['commitment.disabled.manage_required', 'Only a project manager can do this.'],
  not_item_owner: ['commitment.disabled.not_item_owner', 'Only the owner of this item or a project manager can do this.'],
  not_requester: [
    'commitment.disabled.not_requester',
    'Only the person who made the request or a project manager can withdraw it.',
  ],
  release_pending: [
    'commitment.disabled.release_pending',
    'A request for this item is waiting for a decision. Wait for it or withdraw it first.',
  ],
  no_pending_release: ['commitment.disabled.no_pending_release', 'There is no request waiting for a decision.'],
  invalid_transition: ['commitment.disabled.invalid_transition', 'This is not possible in the current state of the item.'],
  item_closed: ['commitment.disabled.item_closed', 'This item was aborted or transferred and can no longer change.'],
  not_entitled_decider: [
    'commitment.disabled.not_entitled_decider',
    'You are not an approver of the tier this request needs.',
  ],
  four_eyes_violation: [
    'commitment.disabled.four_eyes_violation',
    'Four eyes: whoever made the request, owns the item or confirmed one of its preconditions cannot decide it.',
  ],
  field_frozen: ['commitment.disabled.field_frozen', 'This can change only while the item is still planned.'],
  [UNAVAILABLE]: ['commitment.disabled.unavailable', 'The server did not say whether this is allowed.'],
};

/** Every refusal code the server puts into a `can` flag. A test holds each of them to a sentence in both locales. */
export const CAN_REASONS = [
  'not_item_owner',
  'item_closed',
  'release_pending',
  'invalid_transition',
  'no_pending_release',
  'not_requester',
  'manage_required',
  'not_entitled_decider',
  'four_eyes_violation',
] as const;

export interface Viewer {
  userId: string | null;
  role: string | null;
}

/** Read one capability flag. A missing flag or a refusal without a code both deny. */
export function verdictOf(flag: CanFlag | null | undefined): Verdict {
  if (!flag) return UNAVAILABLE;
  if (flag.allowed) return null;
  return flag.reason || UNAVAILABLE;
}

export function itemVerdict(item: Pick<CommitmentItem, 'can'>, action: ItemAction): Verdict {
  return verdictOf(item.can?.[action]);
}

/** Put on hold or resume: one button, two server flags. */
export function holdVerdict(item: Pick<CommitmentItem, 'can' | 'status'>): Verdict {
  return itemVerdict(item, item.status === 'on_hold' ? 'resume' : 'hold');
}

/**
 * Deferring the decision. The server has no flag for it: it asks for the
 * manage permission and for an item that is still planned, and answers
 * `manage_required` or `field_frozen` otherwise. Whether the caller manages is
 * read from the transfer flag, which the server refuses with `manage_required`
 * before it looks at anything else.
 */
export function deferVerdict(item: Pick<CommitmentItem, 'can' | 'status'>): Verdict {
  const transfer = item.can?.transfer;
  if (!transfer) return UNAVAILABLE;
  if (transfer.reason === 'manage_required') return 'manage_required';
  return item.status === 'planned' ? null : 'field_frozen';
}

/* ── No server flag yet: predicted from the role ──────────────────────── */

export function canManage(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'manage') ? null : 'role_manage';
}

export function canAddItem(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}
