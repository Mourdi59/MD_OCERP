// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The logic behind the stakeholder screens, without a screen: how scores are
// classified, which moves a commitment offers and what each still needs, how
// a frequency is recognised, how the mandate grid turns into rows and back,
// and how codes and people are named.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { stakeholderErrorCode, stakeholderErrorMessage, stakeholderViolations, type MandateRow } from '../api';
import { errorText, humanizeCode, itemName, nameOf, vocab, COMMITMENT_STATUS, type LabelContext } from '../labels';
import {
  COMMITMENT_MOVES,
  EVENT_TRIGGERS,
  FREQUENCY_RULE,
  PLAN_MOVES,
  PLAN_START,
  cellKey,
  defaultScores,
  doubleDeciders,
  doubleScopedDeciders,
  gridAxes,
  joinMatrix,
  planStartOf,
  planStatusOptions,
  presetOfFrequency,
  previewClassification,
  splitMatrix,
  toTransitionInput,
  transitionProblems,
  triggerOf,
  type TransitionDraft,
} from '../rules';
import { namesOf, stakeholderName } from '../screen';
import { enExists, enT } from './i18nMock';
import { commitment, powerInterest, salience, stakeholder } from './fixtures';

const labels: LabelContext = { t: enT, language: 'en', exists: enExists };

describe('classification preview', () => {
  it('takes the first matching rule, in the order the framework lists them', () => {
    expect(previewClassification(powerInterest, { power: 4, interest: 5 })).toBe('manage_closely');
    expect(previewClassification(powerInterest, { power: 4, interest: 2 })).toBe('keep_satisfied');
    expect(previewClassification(powerInterest, { power: 2, interest: 3 })).toBe('keep_informed');
  });

  it('falls back to the default of the method when no rule matches', () => {
    expect(previewClassification(powerInterest, { power: 1, interest: 1 })).toBe('monitor');
    expect(previewClassification(salience, { power: false, legitimacy: true, urgency: true })).toBeNull();
  });

  it('reads a yes/no scale strictly: a missing answer is not a yes', () => {
    expect(previewClassification(salience, { power: true, legitimacy: true, urgency: true })).toBe('definitive');
    expect(previewClassification(salience, { power: true, legitimacy: true })).toBe('dormant');
  });

  it('a number rule does not fire on a yes/no answer', () => {
    expect(previewClassification(powerInterest, { power: true, interest: true })).toBe('monitor');
  });

  it('starts a form at the lowest value of each scale', () => {
    expect(defaultScores(powerInterest)).toEqual({ power: 1, interest: 1 });
    expect(defaultScores(salience)).toEqual({ power: false, legitimacy: false, urgency: false });
  });

  it('draws a square only for a method with two number scales, first scale on the vertical axis', () => {
    expect(gridAxes(powerInterest)).toEqual({ y: 'power', x: 'interest' });
    expect(gridAxes(salience)).toBeNull();
  });
});

describe('commitment moves', () => {
  it('closed commitments offer nothing', () => {
    expect(COMMITMENT_MOVES.verified).toEqual([]);
    expect(COMMITMENT_MOVES.withdrawn).toEqual([]);
  });

  it('a proposed commitment can only be agreed or withdrawn', () => {
    expect(COMMITMENT_MOVES.proposed).toEqual(['agreed', 'withdrawn']);
  });

  it('only a fulfilled commitment can be verified', () => {
    const from = (Object.keys(COMMITMENT_MOVES) as Array<keyof typeof COMMITMENT_MOVES>).filter((s) =>
      COMMITMENT_MOVES[s].includes('verified'),
    );
    expect(from).toEqual(['fulfilled']);
  });

  const draft = (over: Partial<TransitionDraft>): TransitionDraft => ({
    target: 'agreed',
    rationale: '',
    toldOn: '',
    loopNotRequired: '',
    createRisk: false,
    ...over,
  });

  it('agreeing needs an owner and a due date', () => {
    expect(transitionProblems(draft({}), commitment())).toEqual([]);
    expect(transitionProblems(draft({}), commitment({ owner_user_id: null }))).toEqual(['owner_and_due_required']);
    expect(transitionProblems(draft({}), commitment({ due_date: null }))).toEqual(['owner_and_due_required']);
  });

  it('withdrawing and confirming a breach need a reason, and spaces are not one', () => {
    for (const target of ['withdrawn', 'breached'] as const) {
      expect(transitionProblems(draft({ target, rationale: '   ' }), commitment())).toEqual(['rationale_required']);
      expect(transitionProblems(draft({ target, rationale: 'Design changed' }), commitment())).toEqual([]);
    }
  });

  it('starting work needs nothing', () => {
    expect(transitionProblems(draft({ target: 'in_progress' }), commitment({ owner_user_id: null }))).toEqual([]);
  });

  it('verifying needs the day the stakeholder was told, a reason why not, or an earlier record of it', () => {
    const fulfilled = commitment({ status: 'fulfilled' });
    expect(transitionProblems(draft({ target: 'verified' }), fulfilled)).toEqual(['loop_required']);
    expect(transitionProblems(draft({ target: 'verified', toldOn: '2026-10-02' }), fulfilled)).toEqual([]);
    expect(transitionProblems(draft({ target: 'verified', loopNotRequired: 'Stakeholder dissolved' }), fulfilled)).toEqual([]);
    expect(
      transitionProblems(draft({ target: 'verified' }), commitment({ communicated_back_at: '2026-10-01T12:00:00+00:00' })),
    ).toEqual([]);
  });

  it('sends only what the target uses', () => {
    expect(toTransitionInput(draft({ target: 'verified', toldOn: '2026-10-02', createRisk: true, rationale: ' x ' }))).toEqual({
      target: 'verified',
      rationale: 'x',
      communicated_back_at: '2026-10-02T12:00:00Z',
      loop_not_required_rationale: '',
      create_risk: false,
    });
    expect(toTransitionInput(draft({ target: 'breached', toldOn: '2026-10-02', createRisk: true, rationale: 'Late' }))).toEqual({
      target: 'breached',
      rationale: 'Late',
      communicated_back_at: null,
      loop_not_required_rationale: '',
      create_risk: true,
    });
  });
});

describe('plan item states', () => {
  it('a new item starts planned or active', () => {
    expect(planStatusOptions(null)).toEqual(['planned', 'active']);
  });

  it('an existing item offers its own state first and then its moves', () => {
    expect(planStatusOptions('active')).toEqual(['active', 'paused', 'completed', 'cancelled']);
    expect(planStatusOptions('completed')).toEqual(['completed']);
    expect(PLAN_MOVES.planned).not.toContain('completed');
  });
});

describe('frequency presets', () => {
  it('recognises every preset from its own rule', () => {
    for (const [preset, rule] of Object.entries(FREQUENCY_RULE)) expect(presetOfFrequency(rule)).toBe(preset);
  });

  it('reads an empty rule as once', () => {
    expect(presetOfFrequency('')).toBe('once');
    expect(presetOfFrequency(null)).toBe('once');
  });

  it('ignores case, part order, the RRULE prefix and an interval of one', () => {
    expect(presetOfFrequency('rrule:interval=2;freq=weekly')).toBe('every_two_weeks');
    expect(presetOfFrequency('FREQ=MONTHLY;INTERVAL=1')).toBe('monthly');
  });

  it('does not force an own rule onto a preset', () => {
    expect(presetOfFrequency('FREQ=WEEKLY;BYDAY=TU')).toBeNull();
    expect(presetOfFrequency('FREQ=MONTHLY;INTERVAL=6')).toBeNull();
  });
});

describe('what sets a plan line off', () => {
  it('reads a stored line', () => {
    expect(planStartOf(null)).toBe('schedule');
    expect(planStartOf({ trigger_kind: null, trigger_ref: null })).toBe('schedule');
    expect(planStartOf({ trigger_kind: 'gate', trigger_ref: 'gate_3' })).toBe('gate');
    expect(planStartOf({ trigger_kind: 'event', trigger_ref: 'project_governance.phase.changed' })).toBe(
      'project_governance.phase.changed',
    );
  });

  it('does not force a trigger it does not know onto one it offers', () => {
    expect(planStartOf({ trigger_kind: 'event', trigger_ref: 'something.else' })).toBeNull();
  });

  it('turns a choice into the fields the server takes, keeping the gate a line already names', () => {
    expect(triggerOf('schedule')).toEqual({ trigger_kind: null, trigger_ref: '' });
    expect(triggerOf('gate')).toEqual({ trigger_kind: 'gate', trigger_ref: '' });
    expect(triggerOf('gate', 'gate_3')).toEqual({ trigger_kind: 'gate', trigger_ref: 'gate_3' });
    expect(triggerOf('stakeholders.commitment.fulfilled')).toEqual({
      trigger_kind: 'event',
      trigger_ref: 'stakeholders.commitment.fulfilled',
    });
  });

  it('has a name for everything the server accepts as an event trigger', () => {
    for (const name of EVENT_TRIGGERS) expect(PLAN_START[name][1]).not.toBe('');
  });
});

describe('mandate matrix', () => {
  const rows: MandateRow[] = [
    { decision_type: 'order_award', scope: '', holder_kind: 'role', holder_code: 'project_manager', letter: 'P', scope_note: '' },
    { decision_type: 'order_award', scope: '', holder_kind: 'body', holder_code: 'steering', letter: 'D', scope_note: 'above budget' },
    { decision_type: 'order_award', scope: 'lot_2', holder_kind: 'role', holder_code: 'client', letter: 'D', scope_note: '' },
  ];

  it('keeps scoped rows apart from the project-wide grid', () => {
    const { cells, scoped } = splitMatrix(rows);
    expect(cells).toEqual({ 'order_award|role|project_manager': 'P', 'order_award|body|steering': 'D' });
    expect(scoped).toEqual([rows[2]]);
  });

  it('a save without a change sends back what was stored, notes and scoped rows included', () => {
    const { cells, scoped } = splitMatrix(rows);
    expect(joinMatrix(cells, scoped, rows)).toEqual(rows);
  });

  it('a cleared cell is not sent, a new one is', () => {
    const { cells, scoped } = splitMatrix(rows);
    const next = { ...cells, 'order_award|role|project_manager': '' as const, 'order_award|role|client': 'C' as const };
    const sent = joinMatrix(next, scoped, rows);
    expect(sent.find((r) => r.holder_code === 'project_manager')).toBeUndefined();
    expect(sent).toContainEqual({
      decision_type: 'order_award',
      scope: '',
      holder_kind: 'role',
      holder_code: 'client',
      letter: 'C',
      scope_note: '',
    });
  });

  it('a role and a body with the same code are different columns', () => {
    expect(cellKey('x', { kind: 'role', code: 'board' })).not.toBe(cellKey('x', { kind: 'body', code: 'board' }));
  });

  it('sends a scoped row with only the fields the server takes, and drops one without a part', () => {
    const scoped: MandateRow[] = [
      { id: 'm9', decision_type: 'order_award', scope: ' Lot 2 ', holder_kind: 'role', holder_code: 'client', letter: 'D', scope_note: ' facade ' },
      { decision_type: 'order_award', scope: '  ', holder_kind: 'role', holder_code: 'client', letter: 'D', scope_note: '' },
    ];
    expect(joinMatrix({}, scoped)).toEqual([
      { decision_type: 'order_award', scope: 'Lot 2', holder_kind: 'role', holder_code: 'client', letter: 'D', scope_note: 'facade' },
    ]);
  });

  it('finds two deciders for the same part, and treats different parts as separate', () => {
    const row = (scope: string, letter: MandateRow['letter'], holder: string): MandateRow => ({
      decision_type: 'order_award',
      scope,
      holder_kind: 'role',
      holder_code: holder,
      letter,
      scope_note: '',
    });
    expect(doubleScopedDeciders([row('Lot 2', 'D', 'client'), row(' Lot 2', 'D', 'project_manager')])).toEqual([['order_award', 'Lot 2']]);
    expect(doubleScopedDeciders([row('Lot 2', 'D', 'client'), row('Lot 3', 'D', 'project_manager')])).toEqual([]);
    expect(doubleScopedDeciders([row('Lot 2', 'D', 'client'), row('Lot 2', 'C', 'project_manager')])).toEqual([]);
    expect(doubleScopedDeciders([row('a|b', 'D', 'client'), row('a|b', 'D', 'project_manager')])).toEqual([['order_award', 'a|b']]);
  });

  it('names the decision types with two deciders, and only those', () => {
    expect(doubleDeciders({ 'a|role|x': 'D', 'a|body|y': 'D', 'b|role|x': 'D', 'b|role|z': 'A' })).toEqual(['a']);
    expect(doubleDeciders({ 'a|role|x': 'D', 'a|body|y': '' })).toEqual([]);
  });
});

describe('names', () => {
  it('shows a tenant label before the shipped key, in the reader language', () => {
    const de: LabelContext = { ...labels, language: 'de-CH' };
    expect(itemName(de, { code: 'c', name_key: 'stakeholders.catalogue.category.client', labels: { en: 'Owner', de: 'Eigner' } })).toBe('Eigner');
    expect(itemName(labels, { code: 'client', name_key: 'stakeholders.catalogue.category.client', labels: null })).toBe('Client');
  });

  it('never shows a raw key or a raw code', () => {
    expect(itemName(labels, { code: 'works_council', name_key: 'stakeholders.catalogue.category.works_council', labels: null })).toBe(
      'Works council',
    );
    expect(nameOf(labels, [], 'keep_informed')).toBe('Keep informed');
    expect(vocab(enT, COMMITMENT_STATUS, 'on_ice')).toBe('On ice');
    expect(humanizeCode('')).toBe('');
  });

  it('says so when a name is hidden or erased, and never leaks the stored name of a masked person', () => {
    expect(stakeholderName(enT, { name: null, masked: true, anonymised: false, display_name: 'Resident of number 12' })).toBe(
      'Private person (name hidden)',
    );
    expect(stakeholderName(enT, { name: null, masked: false, anonymised: true })).toBe('Anonymised');
    expect(stakeholderName(enT, { name: null, masked: false, anonymised: false })).toBe('Unnamed stakeholder');
  });

  it('skips ids the register no longer has', () => {
    expect(namesOf(enT, [stakeholder()], ['gone', 's1'])).toEqual(['Building authority']);
  });
});

describe('server refusals', () => {
  const refusal = new ApiError(403, 'Forbidden', {
    detail: {
      code: 'not_decider',
      message_key: 'stakeholders.errors.not_decider',
      message: 'You do not hold the deciding role for commitments to stakeholders',
    },
  });

  it('reads the code and the sentence the server sent', () => {
    expect(stakeholderErrorCode(refusal)).toBe('not_decider');
    expect(stakeholderErrorMessage(refusal)).toBe('You do not hold the deciding role for commitments to stakeholders');
  });

  it('reads every blocker of a refused matrix', () => {
    const err = new ApiError(422, 'Unprocessable', {
      detail: { code: 'two_deciders', violations: [{ decision_type: 'order_award', scope: '' }] },
    });
    expect(stakeholderViolations(err)).toEqual([{ decision_type: 'order_award', scope: '' }]);
  });

  it('is silent about a failure that is not a refusal', () => {
    expect(stakeholderErrorCode(new Error('offline'))).toBeNull();
    expect(stakeholderErrorCode(new ApiError(500, 'Server Error', { detail: 'database unavailable' }))).toBeNull();
    expect(stakeholderViolations(new ApiError(404, 'Not Found', { detail: { code: 'settings_missing' } }))).toEqual([]);
  });

  it('a code the locale does not know reads as the server wrote it, then as words', () => {
    const plain = (key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue ?? key);
    expect(errorText(plain, 'brand_new_code', 'The server explains')).toBe('The server explains');
    expect(errorText(plain, 'brand_new_code')).toBe('Brand new code');
    expect(errorText(enT, 'two_deciders')).toBe('A decision type may have only one deciding role or body per scope');
  });
});
