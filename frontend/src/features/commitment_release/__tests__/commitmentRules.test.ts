// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The rules behind the commitment screens: exact amounts, the checks of the
// three forms, who may press which button, how a code is named, and how a
// row of another module becomes a line in the document picker.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import {
  CAN_REASONS,
  UNAVAILABLE,
  canAddItem,
  canManage,
  deferVerdict,
  holdVerdict,
  itemVerdict,
  roleAllows,
  verdictOf,
} from '../access';
import { reasonText } from '../CommitmentBits';
import { commitmentErrorCode, commitmentErrorMessage, commitmentViolations } from '../api';
import { documentLabel, toDocumentOptions } from '../documents';
import { exposureCounts } from '../ExposurePanel';
import {
  ERROR_TEXT,
  ITEM_STATUS,
  catalogueName,
  codeName,
  errorText,
  humanizeCode,
  rationaleText,
  vocab,
  type LabelContext,
} from '../labels';
import {
  abortTermsProblems,
  changedItemInput,
  compareAmounts,
  draftOfItem,
  fractionToPercent,
  groupItems,
  isPositiveAmount,
  itemProblems,
  matrixCounts,
  normalizeAmount,
  overRelease,
  percentToFraction,
  releaseProblems,
  remainingToRelease,
  toAbortTermsInput,
  toItemInput,
  toReleaseInput,
  type AbortTermsDraft,
  type ItemDraft,
  type ReleaseDraft,
} from '../rules';
import { untouchedAssignments } from '../SetupPanel';
import { READER_CAN, can, exposure, item } from './fixtures';

const noKeys: LabelContext = { t: (k) => k, language: 'en', exists: () => false };

describe('amounts', () => {
  it('accepts only the wire spelling of a decimal', () => {
    expect(normalizeAmount(' 1250.50 ')).toBe('1250.50');
    expect(normalizeAmount('1,250.50')).toBeNull();
    expect(normalizeAmount('1 250')).toBeNull();
    expect(normalizeAmount('1e3')).toBeNull();
    expect(normalizeAmount('')).toBeNull();
  });

  it('compares exactly, beyond what a float can hold', () => {
    expect(compareAmounts('9007199254740993.01', '9007199254740993.02')).toBe(-1);
    expect(compareAmounts('0.10', '0.1')).toBe(0);
    expect(compareAmounts('2', '1.999999999999999999')).toBe(1);
    expect(compareAmounts(null, '1')).toBeNull();
    expect(compareAmounts('abc', '1')).toBeNull();
  });

  it('zero and negatives are not positive, and neither is an unknown', () => {
    expect(isPositiveAmount('0.00')).toBe(false);
    expect(isPositiveAmount('-5')).toBe(false);
    expect(isPositiveAmount('0.01')).toBe(true);
    expect(isPositiveAmount(null)).toBe(false);
  });

  it('what is still to release is planned less released', () => {
    expect(remainingToRelease({ planned_in_schedule_currency: '260000.00', released: '40000.00' })).toBe('220000.00');
  });

  it('an unknown planned amount leaves the remainder unknown, not zero', () => {
    expect(remainingToRelease({ planned_in_schedule_currency: null, released: '40000.00' })).toBeNull();
  });

  it('a release above the plan shows as a negative remainder instead of being clamped', () => {
    expect(remainingToRelease({ planned_in_schedule_currency: '100.00', released: '250.00' })).toBe('-150.00');
  });

  it('over-release is the amount bound beyond the release, and null when within it', () => {
    expect(overRelease({ committed: '1700000.00', released: '1500000.00' })).toBe('200000.00');
    expect(overRelease({ committed: '1500000.00', released: '1500000.00' })).toBeNull();
    expect(overRelease({ committed: null, released: '0' })).toBeNull();
  });

  it('a typed percentage becomes the stored fraction and back', () => {
    expect(percentToFraction('50')).toBe('0.5');
    expect(percentToFraction('12.5')).toBe('0.125');
    expect(percentToFraction('5')).toBe('0.05');
    expect(percentToFraction('100')).toBe('1');
    expect(percentToFraction('0')).toBe('0');
    expect(percentToFraction('-5')).toBeNull();
    expect(percentToFraction('half')).toBeNull();
    expect(fractionToPercent('0.5')).toBe('50');
    expect(fractionToPercent('0.125')).toBe('12.5');
    expect(fractionToPercent('0.10')).toBe('10');
    expect(fractionToPercent('0.95')).toBe('95');
    expect(fractionToPercent('1')).toBe('100');
    expect(fractionToPercent(null)).toBe('');
  });

  it.each(['10', '50', '95', '12.5', '0.5', '100'])('%s percent survives a round trip', (pct) => {
    expect(fractionToPercent(percentToFraction(pct))).toBe(pct);
  });
});

describe('release request', () => {
  const draft = (over: Partial<ReleaseDraft> = {}): ReleaseDraft => ({
    amount: '40000',
    currency: 'eur',
    trancheNote: ' First tranche ',
    externalRef: '',
    ...over,
  });

  it('a positive amount is enough when the tier is inside the schedule', () => {
    expect(releaseProblems(draft(), { escalate_outside: false })).toEqual([]);
    expect(releaseProblems(draft(), null)).toEqual([]);
  });

  it('names a missing, a malformed and a non-positive amount apart', () => {
    expect(releaseProblems(draft({ amount: '  ' }), null)).toEqual(['amount_missing']);
    expect(releaseProblems(draft({ amount: '40.000,00' }), null)).toEqual(['amount_invalid']);
    expect(releaseProblems(draft({ amount: '0' }), null)).toEqual(['amount_not_positive']);
  });

  it('asks for the external reference only once the preview says the amount is above every tier', () => {
    expect(releaseProblems(draft(), { escalate_outside: true })).toEqual(['external_ref_required']);
    expect(releaseProblems(draft({ externalRef: 'Board 2026-14' }), { escalate_outside: true })).toEqual([]);
  });

  it('sends the amount as a string, the currency upper-cased and the texts trimmed', () => {
    expect(toReleaseInput(draft())).toEqual({
      amount: '40000',
      currency: 'EUR',
      tranche_note: 'First tranche',
      external_approval_ref: '',
    });
  });
});

describe('item form', () => {
  const draft = (over: Partial<ItemDraft> = {}): ItemDraft => ({ ...draftOfItem(null, 'EUR'), ...over });
  const complete = draft({ code: 'CR-005', title: 'Lift installation', commitmentType: 'works', plannedAmount: '95000' });

  it('a new item needs a code, a title, a type and an estimate with a currency', () => {
    expect(itemProblems(draft(), 'create')).toEqual(['code_missing', 'title_missing', 'type_missing', 'amount_needs_currency']);
    expect(itemProblems(complete, 'create')).toEqual([]);
  });

  it('an edit does not ask for the code again', () => {
    expect(itemProblems({ ...complete, code: '' }, 'edit')).toEqual([]);
  });

  it('tells a malformed amount from a missing one', () => {
    expect(itemProblems({ ...complete, plannedAmount: '95 000' }, 'create')).toEqual(['amount_invalid']);
    expect(itemProblems({ ...complete, plannedAmount: '0' }, 'create')).toEqual(['amount_needs_currency']);
    expect(itemProblems({ ...complete, currency: 'EU' }, 'create')).toEqual(['amount_needs_currency']);
  });

  it('an item whose amount comes from a budget line needs no estimate', () => {
    expect(itemProblems({ ...complete, plannedSource: 'budget_line', plannedAmount: '' }, 'edit')).toEqual([]);
  });

  it('refuses days that are not whole numbers', () => {
    expect(itemProblems({ ...complete, leadTimeDays: '4.5' }, 'create')).toEqual(['days_invalid']);
    expect(itemProblems({ ...complete, decisionBufferDays: '-1' }, 'create')).toEqual(['days_invalid']);
  });

  it('sends the estimate as a string and leaves it out when the amount is derived', () => {
    const input = toItemInput({ ...complete, leadTimeDays: '45', ownerUserId: 'u1' }, 'create');
    expect(input).toMatchObject({
      code: 'CR-005',
      title: 'Lift installation',
      commitment_type: 'works',
      planned_source: 'manual',
      planned_manual_amount: '95000',
      currency: 'EUR',
      lead_time_days: 45,
      decision_buffer_days: null,
      owner_user_id: 'u1',
    });
    const derived = toItemInput({ ...complete, plannedSource: 'cost_line' }, 'edit');
    expect('planned_manual_amount' in derived).toBe(false);
    expect('code' in derived).toBe(false);
  });

  it('opens an existing item with its own values', () => {
    const d = draftOfItem(item({ flags: ['novel_contentious'], split_group: 'facade' }), 'USD');
    expect(d).toMatchObject({ code: 'CR-001', plannedAmount: '1850000.00', currency: 'EUR', leadTimeDays: '45', flags: ['novel_contentious'], splitGroup: 'facade' });
  });
});

describe('abort terms form', () => {
  const draft = (over: Partial<AbortTermsDraft> = {}): AbortTermsDraft => ({
    basisCode: 'supply_cancellation_schedule',
    basisSource: 'shipped',
    progressPercent: '',
    parameters: {},
    steps: [],
    transferable: 'resale',
    transferValue: '',
    salvageValue: '60000',
    savedCost: '',
    otherCharge: '',
    noticeDays: '',
    sourceNote: ' Supplier quotation ',
    ...over,
  });
  const step = { rowId: 's1', milestone: 'fabrication', fromDate: '2026-12-01', progressPercent: '', chargePercent: '50', chargeAmount: '' };

  it('a step needs a name, a date or a progress, and exactly one charge', () => {
    expect(abortTermsProblems(draft({ steps: [step] }))).toEqual([]);
    expect(abortTermsProblems(draft({ steps: [{ ...step, fromDate: '' }] }))).toEqual(['step_incomplete']);
    expect(abortTermsProblems(draft({ steps: [{ ...step, fromDate: '', progressPercent: '90' }] }))).toEqual([]);
    expect(abortTermsProblems(draft({ steps: [{ ...step, chargeAmount: '1000' }] }))).toEqual(['step_incomplete']);
    expect(abortTermsProblems(draft({ steps: [{ ...step, chargePercent: '' }] }))).toEqual(['step_incomplete']);
  });

  it('refuses a malformed estimate and a fractional notice period', () => {
    expect(abortTermsProblems(draft({ salvageValue: '60k' }))).toEqual(['amount_invalid']);
    expect(abortTermsProblems(draft({ noticeDays: '1.5' }))).toEqual(['days_invalid']);
  });

  it('sends percentages as fractions, empty estimates as null and keeps what the form does not edit', () => {
    const input = toAbortTermsInput(
      draft({ steps: [step, { ...step, rowId: 's2', milestone: 'shipped', fromDate: '', progressPercent: '90', chargePercent: '95' }], parameters: { fee_pct: '0.05' }, progressPercent: '40', noticeDays: '30' }),
    );
    expect(input).toEqual({
      link_id: null,
      basis_code: 'supply_cancellation_schedule',
      basis_source: 'shipped',
      cancellation_schedule: [
        { milestone: 'fabrication', from_date: '2026-12-01', progress_pct: null, charge_pct: '0.5', charge_amount: null },
        { milestone: 'shipped', from_date: null, progress_pct: '0.9', charge_pct: '0.95', charge_amount: null },
      ],
      transferable: 'resale',
      transfer_value_estimate: null,
      salvage_value_estimate: '60000',
      saved_cost_estimate: null,
      other_charge_estimate: null,
      progress_pct: '0.4',
      parameters: { fee_pct: '0.05' },
      notice_days: 30,
      source_note: 'Supplier quotation',
    });
  });
});

describe('grid', () => {
  const works = item({ id: 'a', code: 'CR-010', commitment_type: 'works', gate_code: 'brief_to_concept' });
  const design = item({ id: 'b', code: 'CR-2', commitment_type: 'design', status: 'release_requested', decision_overdue: true });
  const facade = item({
    id: 'c',
    code: 'CR-003',
    commitment_type: 'works',
    over_release: true,
    exposure: exposure({ residual_loss: null, reason: 'abort_terms_missing' }),
  });

  it('orders items by code the way a reader counts, not as text', () => {
    expect(groupItems([works, design, facade], 'none')[0]!.items.map((i) => i.code)).toEqual(['CR-2', 'CR-003', 'CR-010']);
    expect(groupItems([], 'none')).toEqual([]);
  });

  it('groups by type and by gate, with items without a gate together', () => {
    expect(groupItems([works, design, facade], 'type').map((g) => [g.key, g.items.length])).toEqual([['design', 1], ['works', 2]]);
    expect(groupItems([works, design, facade], 'gate').map((g) => [g.key, g.items.length])).toEqual([['', 2], ['brief_to_concept', 1]]);
  });

  it('counts what needs attention', () => {
    expect(matrixCounts([works, design, facade])).toEqual({
      items: 3,
      waitingForDecision: 1,
      decisionOverdue: 1,
      overRelease: 1,
      unknownExposure: 1,
    });
  });

  it('an item with nothing committed is not counted as an unknown abort cost', () => {
    expect(matrixCounts([works]).unknownExposure).toBe(0);
    expect(exposureCounts([{ residual_loss: null, note: 'nothing_committed' }, { residual_loss: null }, { residual_loss: '10' }])).toEqual({
      known: 1,
      unknown: 1,
    });
  });
});

describe('access', () => {
  const editor = { userId: 'u1', role: 'editor' };
  const manager = { userId: 'u2', role: 'manager' };
  const viewer = { userId: 'u3', role: 'viewer' };

  it('reads the server flag and passes its refusal code through unchanged', () => {
    expect(verdictOf({ allowed: true, reason: null })).toBeNull();
    expect(verdictOf({ allowed: false, reason: 'four_eyes_violation' })).toBe('four_eyes_violation');
    expect(itemVerdict(item({ can: READER_CAN }), 'request_release')).toBe('not_item_owner');
    expect(itemVerdict(item(), 'request_release')).toBeNull();
  });

  it('a missing flag denies: an absent answer is not a yes', () => {
    expect(verdictOf(undefined)).toBe(UNAVAILABLE);
    expect(verdictOf({ allowed: false, reason: null })).toBe(UNAVAILABLE);
    expect(itemVerdict(item({ can: {} }), 'edit')).toBe(UNAVAILABLE);
    expect(deferVerdict(item({ can: {} }))).toBe(UNAVAILABLE);
  });

  it('never allows what the server refused, whatever the role or state suggests', () => {
    // A planned item with nothing pending looks requestable; only the flag decides.
    const refused = item({ status: 'planned', can: can({ request_release: 'invalid_transition' }) });
    expect(itemVerdict(refused, 'request_release')).toBe('invalid_transition');
  });

  it('the hold button reads the resume flag while the item is on hold', () => {
    const flags = can({ hold: 'invalid_transition' });
    expect(holdVerdict(item({ status: 'on_hold', can: flags }))).toBeNull();
    expect(holdVerdict(item({ status: 'planned', can: flags }))).toBe('invalid_transition');
    expect(holdVerdict(item({ can: READER_CAN }))).toBe('manage_required');
  });

  it('deferring needs a manager and an item that is still planned', () => {
    expect(deferVerdict(item())).toBeNull();
    expect(deferVerdict(item({ can: READER_CAN }))).toBe('manage_required');
    expect(deferVerdict(item({ status: 'released' }))).toBe('field_frozen');
    // A manager whose transfer is refused for another reason still manages.
    expect(deferVerdict(item({ can: can({ transfer: 'release_pending' }) }))).toBeNull();
  });

  it('every refusal code a flag can carry has a sentence for the button', () => {
    const english = (k: string, o?: Record<string, unknown>) => String(o?.defaultValue ?? k);
    for (const code of [...CAN_REASONS, UNAVAILABLE, 'field_frozen']) {
      const text = reasonText(english, code);
      expect(text, code).toMatch(/ /);
      expect(text, code).not.toBe(humanizeCode(code));
    }
    // A code nobody wrote a button sentence for still reads as its refusal sentence.
    expect(reasonText(english, 'fx_rate_missing')).toBe(ERROR_TEXT.fx_rate_missing);
  });

  it('ranks roles by the backend hierarchy and denies an unknown or absent role', () => {
    expect(roleAllows('estimator', 'edit')).toBe(true);
    expect(roleAllows('viewer', 'edit')).toBe(false);
    expect(roleAllows('admin', 'manage')).toBe(true);
    expect(roleAllows('somebody', 'read')).toBe(false);
    expect(roleAllows(null, 'read')).toBe(false);
  });

  it('adding an item and the approval setup have no flag and are predicted from the role', () => {
    expect(canAddItem(editor)).toBeNull();
    expect(canAddItem(viewer)).toBe('role_edit');
    expect(canManage(editor)).toBe('role_manage');
    expect(canManage(manager)).toBeNull();
  });
});

describe('item edit', () => {
  const original = item({ status: 'released', flags: ['novel_contentious'], split_group: 'facade' });
  const draft = () => draftOfItem(original, 'EUR');

  it('sends nothing when nothing changed', () => {
    expect(changedItemInput(draft(), original)).toEqual({});
  });

  it('sends only the field that changed, so a fixed type or a manager field does not travel', () => {
    expect(changedItemInput({ ...draft(), title: 'Structural works, phase 1' }, original)).toEqual({
      title: 'Structural works, phase 1',
    });
    expect(changedItemInput({ ...draft(), leadTimeDays: '60' }, original)).toEqual({ lead_time_days: 60 });
    expect(changedItemInput({ ...draft(), ownerUserId: 'u-new' }, original)).toEqual({ owner_user_id: 'u-new' });
  });

  it('an amount and its currency travel together', () => {
    expect(changedItemInput({ ...draft(), plannedAmount: '1900000' }, original)).toEqual({
      planned_manual_amount: '1900000',
      currency: 'EUR',
    });
  });

  it('clearing a field sends null, not nothing', () => {
    expect(changedItemInput({ ...draft(), splitGroup: '' }, original)).toEqual({ split_group: null });
  });
});

describe('labels', () => {
  it('names a code from the API label, then the locale, then the code itself', () => {
    const withKeys: LabelContext = { t: (k) => `T:${k}`, language: 'de-DE', exists: (k) => k === 'commitment.tier.sponsor' };
    expect(codeName(withKeys, 'tier', 'sponsor', { key: 'commitment.tier.sponsor', text: null })).toBe('T:commitment.tier.sponsor');
    expect(codeName(withKeys, 'tier', 'sponsor')).toBe('T:commitment.tier.sponsor');
    expect(codeName(withKeys, 'tier', 'cfo', { key: null, text: { en: 'Finance director', de: 'Finanzleitung' } })).toBe('Finanzleitung');
    expect(codeName(noKeys, 'type', 'claim_settlement')).toBe('Claim settlement');
    expect(codeName(noKeys, 'tier', null)).toBe('');
  });

  it('never shows a raw key for a catalogue, a status or a refusal it does not know', () => {
    expect(catalogueName(noKeys, 'uk_public_body')).toBe('Uk public body');
    expect(vocab((k, o) => String(o?.defaultValue ?? k), ITEM_STATUS, 'something_new' as never)).toBe('Something new');
    const english = (k: string, o?: Record<string, unknown>) => String(o?.defaultValue ?? k);
    expect(errorText(english, 'release_pending')).toBe('A release request for this item is already running');
    expect(errorText(english, 'brand_new_code', 'Server said so')).toBe('Server said so');
    expect(errorText(english, 'brand_new_code')).toBe('Brand new code');
    expect(humanizeCode('re_release-required')).toBe('Re release required');
  });

  it('a rationale the server wrote as a code reads as words, and a written one stays as written', () => {
    const english = (k: string, o?: Record<string, unknown>) => String(o?.defaultValue ?? k);
    expect(rationaleText(english, 'four_eyes_violation')).toContain('four eyes');
    expect(rationaleText(english, 'Too early, the survey is not back')).toBe('Too early, the survey is not back');
  });
});

describe('server refusals', () => {
  const refusal = new ApiError(409, 'Conflict', {
    detail: {
      code: 'preconditions_open',
      message_key: 'commitment.errors.preconditions_open',
      message: 'Open preconditions block this release',
      violations: [{ code: 'precondition_open', ref: 'pre1', kind: 'manual' }, 'junk'],
    },
  });

  it('reads the code, the sentence and the violations of a refusal', () => {
    expect(commitmentErrorCode(refusal)).toBe('preconditions_open');
    expect(commitmentErrorMessage(refusal)).toBe('Open preconditions block this release');
    expect(commitmentViolations(refusal)).toEqual([{ code: 'precondition_open', ref: 'pre1', kind: 'manual' }]);
  });

  it('answers null for a failure that is not a commitment refusal', () => {
    expect(commitmentErrorCode(new ApiError(500, 'Server Error', { detail: 'boom' }))).toBeNull();
    expect(commitmentErrorCode(new Error('offline'))).toBeNull();
    expect(commitmentViolations(new Error('offline'))).toEqual([]);
  });
});

describe('document picker', () => {
  it('reads a page and a bare list alike, and labels a row by number and title', () => {
    expect(toDocumentOptions({ items: [{ id: 'c1', code: 'SC-014', title: 'Structural works' }], total: 1 })).toEqual([
      { id: 'c1', label: 'SC-014 Structural works' },
    ]);
    expect(toDocumentOptions([{ id: 'po1', po_number: 'PO-7' }, { id: 't1', name: 'Facade package' }])).toEqual([
      { id: 'po1', label: 'PO-7' },
      { id: 't1', label: 'Facade package' },
    ]);
  });

  it('skips rows without an id and falls back to the id when a row has no words', () => {
    expect(toDocumentOptions([{ title: 'No id' }, null, { id: 'x9' }])).toEqual([{ id: 'x9', label: 'x9' }]);
    expect(toDocumentOptions({ detail: 'nope' })).toEqual([]);
    expect(documentLabel({ rfq_number: 'RFQ-3', title: 'Lifts' })).toBe('RFQ-3 Lifts');
  });
});

describe('approver assignments', () => {
  it('sends back the assignments the form does not show', () => {
    const a = (id: string, role: string, user: string) => ({
      id,
      project_role: role,
      user_id: user,
      deputy_user_id: null,
      valid_from: '2026-09-01',
      valid_to: null,
    });
    expect(untouchedAssignments([a('1', 'sponsor', 'u1'), a('2', 'board', 'u2'), a('3', 'board', 'u3')])).toEqual([
      { project_role: 'board', user_id: 'u3', deputy_user_id: null, valid_from: '2026-09-01', valid_to: null },
    ]);
  });
});
