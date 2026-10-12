// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The arithmetic and the form checks of the commitment screens, kept apart
// from React so each one is a plain unit test.
//
// Amounts are decimal strings on the wire and stay strings here: they are
// compared and subtracted exactly, never through a float. An amount that is
// unknown stays null all the way to the screen, which then says "unknown"
// rather than printing a zero.

import { isDecimalString, subtractDecimalStrings } from '@/shared/lib/exactDecimal';

import type {
  AbortTermsInput,
  CommitmentItem,
  ItemInput,
  PlannedSource,
  PreconditionKind,
  ReleaseInput,
  ReleasePreview,
  ScheduleStep,
  Transferable,
} from './api';
import type { KeyText } from './labels';

/** What the reader typed, tidied into the wire spelling: "1 250,50" is not accepted, "1250.50" is. */
export function normalizeAmount(raw: string): string | null {
  const text = raw.trim();
  if (!text) return null;
  return isDecimalString(text) ? text : null;
}

/** -1, 0 or 1 for two wire decimals; null when either is not one. */
export function compareAmounts(left: string | null | undefined, right: string | null | undefined): number | null {
  if (left == null || right == null) return null;
  const diff = subtractDecimalStrings(left, right);
  if (diff === null) return null;
  if (!/[1-9]/.test(diff)) return 0;
  return diff.startsWith('-') ? -1 : 1;
}

export function isPositiveAmount(value: string | null | undefined): boolean {
  return compareAmounts(value, '0') === 1;
}

/**
 * What is still to release on an item: planned less released, in the schedule
 * currency. Null when the planned amount is unknown. A negative result is
 * returned as it is, because "released more than planned" is a finding the
 * reader has to see and a clamp to zero would hide how large it is.
 */
export function remainingToRelease(item: Pick<CommitmentItem, 'planned_in_schedule_currency' | 'released'>): string | null {
  if (item.planned_in_schedule_currency == null) return null;
  return subtractDecimalStrings(item.planned_in_schedule_currency, item.released ?? '0');
}

/** How far the linked documents bind beyond the release; null when not over or not known. */
export function overRelease(item: Pick<CommitmentItem, 'committed' | 'released'>): string | null {
  if (item.committed == null) return null;
  const diff = subtractDecimalStrings(item.committed, item.released ?? '0');
  return diff !== null && isPositiveAmount(diff) ? diff : null;
}

/* ── Release request ──────────────────────────────────────────────────── */

export interface ReleaseDraft {
  amount: string;
  currency: string;
  trancheNote: string;
  externalRef: string;
}

export type ReleaseProblem = 'amount_missing' | 'amount_invalid' | 'amount_not_positive' | 'external_ref_required';

export const RELEASE_PROBLEM: Record<ReleaseProblem, KeyText> = {
  amount_missing: ['commitment.release.problem.amount_missing', 'Enter the amount to release.'],
  amount_invalid: [
    'commitment.release.problem.amount_invalid',
    'Write the amount as digits with a point for decimals, for example 125000.50.',
  ],
  amount_not_positive: ['commitment.release.problem.amount_not_positive', 'The amount must be greater than zero.'],
  external_ref_required: [
    'commitment.release.problem.external_ref_required',
    'This amount is above every tier. Enter the reference of the approval given outside the schedule.',
  ],
};

/**
 * What stops a release request from being sent. The external reference is
 * asked for only once the server's preview said the amount is above every
 * tier; the server repeats every check on the request itself.
 */
export function releaseProblems(draft: ReleaseDraft, preview: Pick<ReleasePreview, 'escalate_outside'> | null): ReleaseProblem[] {
  const problems: ReleaseProblem[] = [];
  if (!draft.amount.trim()) problems.push('amount_missing');
  else {
    const amount = normalizeAmount(draft.amount);
    if (amount === null) problems.push('amount_invalid');
    else if (!isPositiveAmount(amount)) problems.push('amount_not_positive');
  }
  if (preview?.escalate_outside && !draft.externalRef.trim()) problems.push('external_ref_required');
  return problems;
}

export function toReleaseInput(draft: ReleaseDraft): ReleaseInput {
  const currency = draft.currency.trim().toUpperCase();
  return {
    amount: normalizeAmount(draft.amount) ?? draft.amount.trim(),
    ...(currency ? { currency } : {}),
    tranche_note: draft.trancheNote.trim(),
    external_approval_ref: draft.externalRef.trim(),
  };
}

/* ── Item form ────────────────────────────────────────────────────────── */

export interface ItemDraft {
  code: string;
  title: string;
  commitmentType: string;
  plannedSource: PlannedSource;
  plannedAmount: string;
  currency: string;
  ownerUserId: string;
  latestDecisionDate: string;
  leadTimeDays: string;
  decisionBufferDays: string;
  flags: string[];
  splitGroup: string;
}

export type ItemProblem =
  | 'code_missing'
  | 'title_missing'
  | 'type_missing'
  | 'amount_invalid'
  | 'amount_needs_currency'
  | 'days_invalid';

export const ITEM_PROBLEM: Record<ItemProblem, KeyText> = {
  code_missing: ['commitment.item_form.problem.code_missing', 'Give the item a short code, for example CR-005.'],
  title_missing: ['commitment.item_form.problem.title_missing', 'Say what is being committed.'],
  type_missing: ['commitment.item_form.problem.type_missing', 'Choose the commitment type. It decides who approves.'],
  amount_invalid: [
    'commitment.item_form.problem.amount_invalid',
    'Write the planned amount as digits with a point for decimals.',
  ],
  amount_needs_currency: [
    'commitment.item_form.problem.amount_needs_currency',
    'An estimate needs an amount above zero and a three-letter currency.',
  ],
  days_invalid: ['commitment.item_form.problem.days_invalid', 'Lead time and buffer are whole days, zero or more.'],
};

function wholeDays(raw: string): number | null | 'bad' {
  const text = raw.trim();
  if (!text) return null;
  if (!/^\d{1,4}$/.test(text)) return 'bad';
  const n = Number(text);
  return n <= 3650 ? n : 'bad';
}

export function itemProblems(draft: ItemDraft, mode: 'create' | 'edit'): ItemProblem[] {
  const problems: ItemProblem[] = [];
  if (mode === 'create' && !draft.code.trim()) problems.push('code_missing');
  if (!draft.title.trim()) problems.push('title_missing');
  if (!draft.commitmentType) problems.push('type_missing');
  if (draft.plannedSource === 'manual') {
    const amount = normalizeAmount(draft.plannedAmount);
    if (draft.plannedAmount.trim() && amount === null) problems.push('amount_invalid');
    else if (!isPositiveAmount(amount) || !/^[A-Za-z]{3}$/.test(draft.currency.trim())) {
      problems.push('amount_needs_currency');
    }
  }
  if (wholeDays(draft.leadTimeDays) === 'bad' || wholeDays(draft.decisionBufferDays) === 'bad') {
    problems.push('days_invalid');
  }
  return problems;
}

export function toItemInput(draft: ItemDraft, mode: 'create' | 'edit'): ItemInput {
  const days = (raw: string) => {
    const n = wholeDays(raw);
    return n === 'bad' ? null : n;
  };
  const input: ItemInput = {
    title: draft.title.trim(),
    commitment_type: draft.commitmentType,
    planned_source: draft.plannedSource,
    owner_user_id: draft.ownerUserId || null,
    latest_decision_date_fixed: draft.latestDecisionDate || null,
    lead_time_days: days(draft.leadTimeDays),
    decision_buffer_days: days(draft.decisionBufferDays),
    flags: draft.flags,
    split_group: draft.splitGroup.trim() || null,
  };
  if (mode === 'create') input.code = draft.code.trim();
  if (draft.plannedSource === 'manual') {
    input.planned_manual_amount = normalizeAmount(draft.plannedAmount);
    input.currency = draft.currency.trim().toUpperCase();
  }
  return input;
}

export function draftOfItem(item: CommitmentItem | null, defaultCurrency: string): ItemDraft {
  return {
    code: item?.code ?? '',
    title: item?.title ?? '',
    commitmentType: item?.commitment_type ?? '',
    plannedSource: item?.planned_source ?? 'manual',
    plannedAmount: item?.planned_source === 'manual' ? item.planned.amount ?? '' : '',
    currency: item?.planned.currency || defaultCurrency,
    ownerUserId: item?.owner_user_id ?? '',
    latestDecisionDate: item?.latest_decision_date_fixed ?? '',
    leadTimeDays: item?.lead_time_days == null ? '' : String(item.lead_time_days),
    decisionBufferDays: item?.decision_buffer_days == null ? '' : String(item.decision_buffer_days),
    flags: item?.flags ?? [],
    splitGroup: item?.split_group ?? '',
  };
}

/* ── Abort terms form ─────────────────────────────────────────────────── */

export interface StepDraft {
  rowId: string;
  milestone: string;
  fromDate: string;
  /** The step applies once the work is this far along, typed as a percentage. */
  progressPercent: string;
  /** The charge as a share of the commitment, typed as a percentage: "50" means half. */
  chargePercent: string;
  chargeAmount: string;
}

export interface AbortTermsDraft {
  basisCode: string;
  basisSource: 'shipped' | 'tenant';
  /** How far the work has come, typed as a percentage. */
  progressPercent: string;
  /** Contract figures the basis asks for; not edited here, sent back as they were. */
  parameters: Record<string, string>;
  steps: StepDraft[];
  transferable: Transferable;
  transferValue: string;
  salvageValue: string;
  savedCost: string;
  otherCharge: string;
  noticeDays: string;
  sourceNote: string;
}

export type AbortTermsProblem = 'amount_invalid' | 'step_incomplete' | 'days_invalid';

export const ABORT_TERMS_PROBLEM: Record<AbortTermsProblem, KeyText> = {
  amount_invalid: ['commitment.abort_form.problem.amount_invalid', 'Write every amount as digits with a point for decimals.'],
  step_incomplete: [
    'commitment.abort_form.problem.step_incomplete',
    'Each cancellation step needs a name, a start date or a progress, and either a percentage or an amount, not both.',
  ],
  days_invalid: ['commitment.abort_form.problem.days_invalid', 'The notice period is whole days, zero or more.'],
};

/** A typed percentage as the fraction the API stores: "50" becomes "0.5". Null when it is not a percentage. */
export function percentToFraction(raw: string): string | null {
  const text = normalizeAmount(raw);
  if (text === null || text.startsWith('-')) return null;
  const [whole = '0', frac = ''] = text.split('.');
  const digits = `${whole.padStart(3, '0')}${frac}`;
  const cut = digits.length - frac.length - 2;
  const fraction = `${digits.slice(0, cut)}.${digits.slice(cut)}`.replace(/^0+(?=\d)/, '').replace(/\.?0+$/, '');
  return fraction === '' ? '0' : fraction;
}

/** The stored fraction as the percentage a reader types: "0.5" becomes "50". */
export function fractionToPercent(raw: string | null | undefined): string {
  if (raw == null || !isDecimalString(raw)) return '';
  const [whole = '0', frac = ''] = raw.split('.');
  const padded = frac.padEnd(2, '0');
  const text = `${whole}${padded.slice(0, 2)}${padded.length > 2 ? `.${padded.slice(2)}` : ''}`;
  return text.replace(/^0+(?=\d)/, '').replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
}

function optionalAmount(raw: string): string | null | 'bad' {
  if (!raw.trim()) return null;
  return normalizeAmount(raw) ?? 'bad';
}

export function abortTermsProblems(draft: AbortTermsDraft): AbortTermsProblem[] {
  const problems = new Set<AbortTermsProblem>();
  for (const raw of [draft.transferValue, draft.salvageValue, draft.savedCost, draft.otherCharge]) {
    if (optionalAmount(raw) === 'bad') problems.add('amount_invalid');
  }
  for (const step of draft.steps) {
    const pct = step.chargePercent.trim();
    const amount = step.chargeAmount.trim();
    const progress = step.progressPercent.trim();
    if (!step.milestone.trim() || (!step.fromDate && !progress) || (!pct && !amount) || (pct && amount)) {
      problems.add('step_incomplete');
      continue;
    }
    if (progress && percentToFraction(progress) === null) problems.add('amount_invalid');
    if (pct && percentToFraction(pct) === null) problems.add('amount_invalid');
    if (amount && normalizeAmount(amount) === null) problems.add('amount_invalid');
  }
  if (draft.progressPercent.trim() && percentToFraction(draft.progressPercent) === null) problems.add('amount_invalid');
  if (wholeDays(draft.noticeDays) === 'bad') problems.add('days_invalid');
  return [...problems];
}

export function toAbortTermsInput(draft: AbortTermsDraft): AbortTermsInput {
  const amount = (raw: string) => {
    const value = optionalAmount(raw);
    return value === 'bad' ? null : value;
  };
  const notice = wholeDays(draft.noticeDays);
  const steps: ScheduleStep[] = draft.steps.map((s) => ({
    milestone: s.milestone.trim(),
    from_date: s.fromDate || null,
    progress_pct: s.progressPercent.trim() ? percentToFraction(s.progressPercent) : null,
    charge_pct: s.chargePercent.trim() ? percentToFraction(s.chargePercent) : null,
    charge_amount: s.chargeAmount.trim() ? normalizeAmount(s.chargeAmount) : null,
  }));
  return {
    link_id: null,
    basis_code: draft.basisCode || null,
    basis_source: draft.basisSource,
    cancellation_schedule: steps,
    transferable: draft.transferable,
    transfer_value_estimate: amount(draft.transferValue),
    salvage_value_estimate: amount(draft.salvageValue),
    saved_cost_estimate: amount(draft.savedCost),
    other_charge_estimate: amount(draft.otherCharge),
    progress_pct: draft.progressPercent.trim() ? percentToFraction(draft.progressPercent) : null,
    parameters: draft.parameters,
    notice_days: notice === 'bad' ? null : notice,
    source_note: draft.sourceNote.trim(),
  };
}

/* ── Grid ─────────────────────────────────────────────────────────────── */

export type GroupBy = 'none' | 'type' | 'gate';

export interface ItemGroup {
  /** The commitment type or gate code; empty for the ungrouped list and for items without a gate. */
  key: string;
  items: CommitmentItem[];
}

/** Items in code order, in one group or one group per type or gate, in order of first appearance. */
export function groupItems(items: readonly CommitmentItem[], by: GroupBy): ItemGroup[] {
  const sorted = [...items].sort((a, b) => a.code.localeCompare(b.code, undefined, { numeric: true }));
  if (by === 'none') return sorted.length ? [{ key: '', items: sorted }] : [];
  const groups = new Map<string, CommitmentItem[]>();
  for (const item of sorted) {
    const key = by === 'type' ? item.commitment_type : item.gate_code ?? '';
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return [...groups.entries()].map(([key, list]) => ({ key, items: list }));
}

export interface MatrixCounts {
  items: number;
  waitingForDecision: number;
  decisionOverdue: number;
  overRelease: number;
  unknownExposure: number;
}

export function matrixCounts(items: readonly CommitmentItem[]): MatrixCounts {
  return {
    items: items.length,
    waitingForDecision: items.filter((i) => i.status === 'release_requested').length,
    decisionOverdue: items.filter((i) => i.decision_overdue).length,
    overRelease: items.filter((i) => i.over_release).length,
    unknownExposure: items.filter((i) => i.exposure && i.exposure.residual_loss == null && !i.exposure.note).length,
  };
}

/** Precondition kinds a person ticks by hand; every other kind is read from its own module. */
export const TICKABLE_PRECONDITIONS: readonly PreconditionKind[] = ['manual', 'permit', 'public_commitment_appropriation'];

/** Kinds that can be added here without picking a record of another module. */
export const ADDABLE_PRECONDITIONS: readonly PreconditionKind[] = [
  'manual',
  'permit',
  'public_commitment_appropriation',
  'budget_available',
];
