// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The rules the permit screens apply before they send anything.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { permitErrorCode, permitErrorMessage } from '../api';
import { errorText, periodText, typeName, vocab, REQUIREMENT_STATE } from '../labels';
import {
  buildRoadmapRows,
  canNotifyStart,
  canStartApplication,
  changedOnly,
  clockEventKinds,
  clockEventProblems,
  conditionActions,
  conditionProblems,
  daysBetween,
  decisionProblems,
  dischargeModes,
  emptyDecision,
  inConditionView,
  isDecidable,
  newConditionDraft,
  permitTargets,
  summariseRoadmap,
  toClockEventInput,
  toConditionInput,
  toDecisionInput,
} from '../rules';
import { application, condition, labels, requirement, timelineRow } from './fixtures';
import { enT } from './i18nMock';

describe('changedOnly', () => {
  it('sends only what the reader changed, so a PATCH cannot clear an untouched field', () => {
    const before = { title: 'Crane road closure', applicant_role: 'owner', needed_by_date: null };
    expect(changedOnly(before, { title: 'Crane road closure', applicant_role: 'contractor', needed_by_date: null })).toEqual({
      applicant_role: 'contractor',
    });
  });

  it('treats a missing value and null as the same', () => {
    expect(changedOnly({ a: undefined }, { a: null })).toEqual({});
  });
});

describe('roadmap rows', () => {
  const reqs = [requirement({ id: 'r2', sort_order: 2 }), requirement({ id: 'r1', sort_order: 1 })];

  it('joins timeline and applications per requirement, in roadmap order, newest attempt first', () => {
    const rows = buildRoadmapRows(
      reqs,
      [timelineRow({ requirement_id: 'r2', forecast_decision: '2026-10-01' })],
      [application({ id: 'a1', attempt: 1, state: 'decided' }), application({ id: 'a2', attempt: 2 })],
    );
    expect(rows.map((r) => r.requirement.id)).toEqual(['r1', 'r2']);
    expect(rows[0]!.application?.id).toBe('a2');
    expect(rows[0]!.applications.map((a) => a.id)).toEqual(['a2', 'a1']);
    expect(rows[0]!.timeline).toBeNull();
    expect(rows[1]!.timeline?.forecast_decision).toBe('2026-10-01');
    expect(rows[1]!.application).toBeNull();
  });

  it('counts a conflict only while nobody accepted it and the permit still applies', () => {
    const rows = buildRoadmapRows(
      [
        requirement({ id: 'r1', state: 'granted' }),
        requirement({ id: 'r2', sort_order: 2 }),
        requirement({ id: 'r3', sort_order: 3 }),
        requirement({ id: 'r4', sort_order: 4, applicable: false, state: 'not_applicable' }),
      ],
      [
        timelineRow({ requirement_id: 'r2', schedule_conflict: true, conflict_days: 12 }),
        timelineRow({ requirement_id: 'r3', schedule_conflict: true, conflict_accepted: true }),
        timelineRow({ requirement_id: 'r4', schedule_conflict: true }),
      ],
      [],
    );
    expect(summariseRoadmap(rows)).toEqual({ total: 3, granted: 1, inProgress: 2, conflicts: 1 });
  });

  it('offers a new application only when none is still open', () => {
    const r = requirement();
    expect(canStartApplication({ requirement: r, applications: [] })).toBe(true);
    expect(canStartApplication({ requirement: r, applications: [application()] })).toBe(false);
    expect(canStartApplication({ requirement: r, applications: [application({ state: 'decided' })] })).toBe(true);
    expect(canStartApplication({ requirement: requirement({ applicable: false }), applications: [] })).toBe(false);
  });

  it('records a decision on a filed application only', () => {
    expect(isDecidable({ state: 'preparing' })).toBe(false);
    expect(isDecidable({ state: 'submitted' })).toBe(true);
    expect(isDecidable({ state: 'info_requested' })).toBe(true);
    expect(isDecidable({ state: 'decided' })).toBe(false);
  });
});

describe('conditions', () => {
  it('asks for what the trigger needs', () => {
    const d = newConditionDraft();
    expect(conditionProblems(d)).toEqual(['number_required', 'text_required']);
    const full = { ...d, number: '3', text: 'Keep the noise log.' };
    expect(conditionProblems(full)).toEqual([]);
    expect(conditionProblems({ ...full, trigger: 'before_stage' })).toEqual(['stage_required']);
    expect(conditionProblems({ ...full, trigger: 'by_date' })).toEqual(['due_date_required']);
    expect(conditionProblems({ ...full, trigger: 'on_event' })).toEqual(['event_required']);
    expect(conditionProblems({ ...full, kind: 'information', trigger: 'by_date' })).toEqual([]);
  });

  it('drops the fields that do not belong to the kind and trigger', () => {
    const d = { ...newConditionDraft('4'), text: ' Note. ', kind: 'information' as const, stage_ref: 'Shell', purpose: 'security' as const };
    const out = toConditionInput(d);
    expect(out).toMatchObject({ number: '4', text: 'Note.', trigger: '', stage_ref: '', purpose: '', due_date: null, owner_user_id: null });
  });

  it('offers the steps the state leaves open', () => {
    expect(conditionActions(condition({ confirmed: false }))).toEqual(['confirm']);
    expect(conditionActions(condition({ kind: 'information' }))).toEqual([]);
    expect(conditionActions(condition())).toEqual(['add_evidence', 'submit_evidence', 'discharge', 'edit', 'link_requirement']);
    expect(conditionActions(condition({ trigger: 'ongoing', requirement_id: 'q1' }))).toEqual([
      'add_evidence',
      'in_compliance',
      'breach',
      'discharge',
      'edit',
    ]);
    expect(conditionActions(condition({ state: 'evidence_submitted' }))).toEqual(['discharge', 'add_evidence']);
    expect(conditionActions(condition({ state: 'breach' }))).toEqual(['in_compliance']);
    expect(conditionActions(condition({ state: 'discharged' }))).toEqual([]);
  });

  it('never offers self-certification where the authority has to approve', () => {
    expect(dischargeModes({ state: 'evidence_submitted', requires_authority_approval: false })).toEqual([
      'self_certified',
      'waived_by_authority',
    ]);
    expect(dischargeModes({ state: 'evidence_submitted', requires_authority_approval: true })).toEqual(['waived_by_authority']);
    expect(dischargeModes({ state: 'open', requires_authority_approval: false })).toEqual(['not_triggered', 'waived_by_authority']);
    expect(dischargeModes({ state: 'discharged', requires_authority_approval: false })).toEqual([]);
  });

  it('keeps an unconfirmed proposal out of every view but its own', () => {
    const proposal = condition({ confirmed: false, overdue: true, owner_user_id: 'u1' });
    expect(inConditionView(proposal, 'proposals', 'u1')).toBe(true);
    for (const view of ['all', 'before_start', 'overdue', 'mine'] as const) {
      expect(inConditionView(proposal, view, 'u1')).toBe(false);
    }
  });

  it('files a condition under the views a site team asks for', () => {
    const noise = condition({ trigger: 'ongoing', topic: 'noise' });
    expect(inConditionView(noise, 'ongoing_hse', null)).toBe(true);
    expect(inConditionView(noise, 'before_start', null)).toBe(false);
    expect(inConditionView(condition({ hse_relevant: true }), 'ongoing_hse', null)).toBe(true);
    expect(inConditionView(condition({ overdue: true }), 'overdue', null)).toBe(true);
    expect(inConditionView(condition(), 'mine', 'u1')).toBe(true);
    expect(inConditionView(condition(), 'mine', 'u2')).toBe(false);
    expect(inConditionView(condition(), 'mine', null)).toBe(false);
    expect(inConditionView(condition({ state: 'superseded' }), 'before_start', null)).toBe(false);
  });
});

describe('decisions', () => {
  const ctx = { today: '2026-06-10', deemedNeedsNotice: false };

  it('asks for an outcome first', () => {
    expect(decisionProblems(emptyDecision('2026-06-10'), ctx)).toEqual(['outcome_required']);
  });

  it('refuses a decision dated in the future', () => {
    const d = { ...emptyDecision('2026-06-11'), outcome: 'granted' as const };
    expect(decisionProblems(d, ctx)).toEqual(['date_in_future']);
  });

  it('needs conditions, or the word that they follow, when granted with conditions', () => {
    const d = { ...emptyDecision('2026-06-10'), outcome: 'granted_with_conditions' as const };
    expect(decisionProblems(d, ctx)).toEqual(['conditions_required']);
    expect(decisionProblems({ ...d, conditions_pending: true }, ctx)).toEqual([]);
  });

  it('names each condition problem once and catches a repeated number', () => {
    const a = { ...newConditionDraft('1'), text: 'First.' };
    const b = { ...newConditionDraft('1'), text: '' };
    const c = { ...newConditionDraft('2'), text: '' };
    const d = { ...emptyDecision('2026-06-10'), outcome: 'granted_with_conditions' as const, conditions: [a, b, c] };
    expect(decisionProblems(d, ctx).sort()).toEqual(['number_repeated', 'text_required']);
  });

  it('needs the covered scope for a partial grant and the notice for a deemed one', () => {
    expect(decisionProblems({ ...emptyDecision('2026-06-10'), outcome: 'partially_granted' }, ctx)).toEqual(['scope_required']);
    const deemed = { ...emptyDecision('2026-06-10'), outcome: 'deemed_granted' as const };
    expect(decisionProblems(deemed, ctx)).toEqual([]);
    expect(decisionProblems(deemed, { ...ctx, deemedNeedsNotice: true })).toEqual(['notice_required']);
  });

  it('checks the security as an exact amount with a currency', () => {
    const d = { ...emptyDecision('2026-06-10'), outcome: 'granted' as const, security_amount: '25,000' };
    expect(decisionProblems(d, ctx).sort()).toEqual(['security_amount_invalid', 'security_currency_required']);
    expect(decisionProblems({ ...d, security_amount: '25000.00', security_currency: 'eur' }, ctx)).toEqual([]);
  });

  it('sends the amount as the string that was typed, never as a float', () => {
    const d = { ...emptyDecision('2026-06-10', 'BA-1'), outcome: 'granted' as const, security_amount: '25000.10', security_currency: 'eur' };
    const out = toDecisionInput(d);
    expect(out.security_amount).toBe('25000.10');
    expect(out.security_currency).toBe('EUR');
    expect(out.conditions).toEqual([]);
    expect(out.discharged_condition_ids).toBeNull();
    expect(out.removed_condition_numbers).toEqual([]);
  });

  it('sends no conditions and no security with a refusal', () => {
    const d = {
      ...emptyDecision('2026-06-10'),
      outcome: 'refused' as const,
      conditions: [{ ...newConditionDraft('1'), text: 'Left over.' }],
      conditions_pending: true,
      security_amount: '100',
      security_currency: 'EUR',
    };
    const out = toDecisionInput(d);
    expect(out.conditions).toEqual([]);
    expect(out.conditions_pending).toBe(false);
    expect(out.security_amount).toBeNull();
    expect(out.security_currency).toBe('');
  });

  it('names the discharged conditions only when the authority discharged some of them', () => {
    const shape = { listed: ['c1', 'c2'], varies: false };
    const all = { ...emptyDecision('2026-06-10', '', ['c1', 'c2']), outcome: 'granted' as const };
    expect(toDecisionInput(all, shape).discharged_condition_ids).toBeNull();
    expect(toDecisionInput({ ...all, discharged: ['c2'] }, shape).discharged_condition_ids).toEqual(['c2']);
  });

  it('lists the dropped condition numbers of a variation', () => {
    const d = { ...emptyDecision('2026-06-10'), outcome: 'granted' as const, removed_numbers: ' 3, 7 ,, ' };
    expect(toDecisionInput(d, { listed: [], varies: true }).removed_condition_numbers).toEqual(['3', '7']);
    expect(toDecisionInput(d, { listed: [], varies: false }).removed_condition_numbers).toEqual([]);
  });
});

describe('decision clock', () => {
  it('lets a stopped clock only run again', () => {
    expect(clockEventKinds({ start: null, stopped_now: false })).toEqual([]);
    expect(clockEventKinds({ start: '2026-05-04', stopped_now: true })).toEqual(['resume']);
    expect(clockEventKinds({ start: '2026-05-04', stopped_now: false })).toEqual(['stop', 'extension_agreed', 'extension_by_authority']);
  });

  it('asks an extension for its length, and the authority for its reasons', () => {
    const base = { kind: 'extension_by_authority' as const, at: '2026-06-01', period: '', unit: 'months' as const, reason: '' };
    expect(clockEventProblems(base)).toEqual(['period_required', 'reason_required']);
    expect(clockEventProblems({ ...base, period: '1.5', reason: 'Complex case' })).toEqual(['period_required']);
    expect(clockEventProblems({ ...base, kind: 'stop', at: '' })).toEqual(['at_required']);
  });

  it('sends a period only with an extension', () => {
    const d = { kind: 'extension_agreed' as const, at: '2026-06-01', period: ' 2 ', unit: 'weeks' as const, reason: ' agreed ' };
    expect(toClockEventInput(d)).toEqual({ kind: 'extension_agreed', at: '2026-06-01', reason: 'agreed', period: 2, unit: 'weeks' });
    expect(toClockEventInput({ ...d, kind: 'stop' })).toEqual({ kind: 'stop', at: '2026-06-01', reason: 'agreed' });
  });
});

describe('permits', () => {
  it('moves by hand only where the state allows it', () => {
    expect(permitTargets({ state: 'in_force' })).toEqual(['suspended', 'revoked', 'expired']);
    expect(permitTargets({ state: 'suspended' })).toEqual(['in_force', 'revoked']);
    expect(permitTargets({ state: 'lapsed' })).toEqual([]);
    expect(permitTargets({ state: 'revoked' })).toEqual([]);
  });

  it('records the start of works once, on a permit in force', () => {
    expect(canNotifyStart({ state: 'in_force', start_notified_at: null })).toBe(true);
    expect(canNotifyStart({ state: 'in_force', start_notified_at: '2026-07-01' })).toBe(false);
    expect(canNotifyStart({ state: 'suspended', start_notified_at: null })).toBe(false);
  });

  it('counts whole days across a month end', () => {
    expect(daysBetween('2026-01-01', '2026-01-31')).toBe(30);
    expect(daysBetween('2026-02-27', '2026-03-01')).toBe(2);
    expect(daysBetween('2026-03-01', '2026-02-27')).toBe(-2);
  });
});

describe('labels and refusals', () => {
  it('translates a known code and makes an unknown one readable', () => {
    expect(vocab(enT, REQUIREMENT_STATE, 'in_progress')).toBe('In progress');
    expect(vocab(enT, REQUIREMENT_STATE, 'some_new_state')).not.toContain('_');
    expect(vocab(enT, REQUIREMENT_STATE, null)).toBe('');
  });

  it('counts a period in the singular and the plural', () => {
    expect(periodText(enT, 1, 'months')).toBe('1 month');
    expect(periodText(enT, 3, 'months')).toBe('3 months');
    expect(periodText(enT, null, 'months')).toBe('');
  });

  it('names a permit type the catalogue ships, and falls back to a readable code', () => {
    expect(typeName({ ...labels, exists: (k) => k === 'permits.type.building_permit' }, 'building_permit', null)).toBe(
      enT('permits.type.building_permit'),
    );
    expect(typeName(labels, 'tenant_special_consent', null)).not.toContain('_');
  });

  it('reads the code and the sentence out of a refusal', () => {
    const err = new ApiError(409, 'Conflict', {
      detail: { code: 'four_eyes_required', message_key: 'permits.errors.four_eyes_required', message: 'Server words' },
    });
    expect(permitErrorCode(err)).toBe('four_eyes_required');
    expect(permitErrorMessage(err)).toBe('Server words');
    expect(permitErrorCode(new ApiError(500, 'Server Error', { detail: 'boom' }))).toBeNull();
    expect(permitErrorCode(new Error('offline'))).toBeNull();
  });

  it('shows the server sentence for a code the client does not know', () => {
    expect(errorText(enT, 'brand_new_code', 'Said by the server')).toBe('Said by the server');
    expect(errorText(enT, 'roadmap_missing', null)).toBe(enT('permits.errors.roadmap_missing'));
  });
});
