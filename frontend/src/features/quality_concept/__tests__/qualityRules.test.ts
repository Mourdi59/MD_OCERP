// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The state tables, the form rules and the label helpers of the quality
// concept, without a screen around them.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { isConceptMissing, refusalDetail } from '../api';
import {
  EXPERT_FREQUENCY,
  FINDING,
  catalogueName,
  findingText,
  gate,
  humanizeCode,
  nameIn,
  refusalText,
  vocab,
  vocabOrRaw,
  type LabelContext,
} from '../labels';
import {
  ACCEPTANCE_ACTIONS,
  CERTIFICATION_ACTIONS,
  CONCEPT_ACTIONS,
  CREDIT_ACTIONS,
  STAGE_ACTIONS,
  SURVEY_ACTIONS,
  canKey,
  closedReasons,
  conceptEditable,
  filledPackages,
  isAccepted,
  lines,
  may,
  needsAchievedLevel,
  needsRationale,
  packageScopeProblem,
  percent,
  pointsString,
  preconditionNotApplicable,
  refChange,
  proofActions,
  waiverPending,
  whyNot,
} from '../rules';
import { enT } from './i18nMock';

const pkg = (ref: string, title = '') => ({ ref, code: '', title, no_proofs_rationale: '' });

describe('state tables', () => {
  it('offers no step that another module owns', () => {
    const all = (table: Record<string, string[]>) => Object.values(table).flat();
    expect(all(CONCEPT_ACTIONS)).not.toContain('approve');
    expect(all(CONCEPT_ACTIONS)).not.toContain('bind');
    expect(all(CONCEPT_ACTIONS)).not.toContain('revise');
    expect(all(CONCEPT_ACTIONS)).not.toContain('reopen');
    expect(all(STAGE_ACTIONS)).not.toContain('release');
    expect(all(ACCEPTANCE_ACTIONS)).not.toContain('accept');
    expect(all(ACCEPTANCE_ACTIONS)).not.toContain('revoke');
  });

  it('lets a concept be edited only as a draft or under revision', () => {
    expect(conceptEditable('draft')).toBe(true);
    expect(conceptEditable('revising')).toBe(true);
    expect(conceptEditable('in_review')).toBe(false);
    expect(conceptEditable('approved')).toBe(false);
    expect(conceptEditable('binding')).toBe(false);
    expect(CONCEPT_ACTIONS.binding).toEqual([]);
    expect(CONCEPT_ACTIONS.approved).toEqual([]);
  });

  it('ends every machine in a state without actions', () => {
    expect(CERTIFICATION_ACTIONS.certified).toEqual([]);
    expect(CREDIT_ACTIONS.achieved).toEqual([]);
    expect(STAGE_ACTIONS.not_applicable).toEqual(['reinstate']);
    expect(STAGE_ACTIONS.released).not.toContain('reinstate');
    expect(SURVEY_ACTIONS.closed).toEqual([]);
  });

  it('asks for a release only once a stage passed or its release went stale', () => {
    const offering = Object.entries(STAGE_ACTIONS)
      .filter(([, actions]) => actions.includes('request_release'))
      .map(([state]) => state);
    expect(offering.sort()).toEqual(['passed', 'stale']);
  });

  it('confirms effects only on an accepted unit', () => {
    for (const [state, actions] of Object.entries(ACCEPTANCE_ACTIONS)) {
      expect(actions.includes('confirm_effects')).toBe(isAccepted(state as keyof typeof ACCEPTANCE_ACTIONS));
    }
  });
});

describe('proof actions', () => {
  const base = { decision: 'none' as const, state: 'open' as const, requested_by: null, decision_rationale: '' };

  it('offers a waiver request on an open proof and acceptance only once delivered', () => {
    expect(proofActions(base)).toEqual(['request_waiver']);
    expect(proofActions({ ...base, state: 'delivered' })).toEqual(['accept', 'request_waiver']);
  });

  it('turns a pending waiver into a decision for somebody else', () => {
    const pending = { ...base, requested_by: 'u1', decision_rationale: 'Not part of this contract' };
    expect(waiverPending(pending)).toBe(true);
    expect(proofActions(pending)).toEqual(['approve_waiver', 'reject_waiver']);
    expect(waiverPending({ ...pending, decision_rationale: '  ' })).toBe(false);
  });

  it('only reopens a decided proof', () => {
    expect(proofActions({ ...base, decision: 'accepted', state: 'accepted' })).toEqual(['reopen']);
    expect(proofActions({ ...base, decision: 'waived', state: 'waived' })).toEqual(['reopen']);
  });
});

describe('form rules', () => {
  it('names the actions that need a written reason', () => {
    expect(needsRationale('certification', 'abandon')).toBe(true);
    expect(needsRationale('certification', 'register')).toBe(false);
    expect(needsRationale('stage', 'not_applicable')).toBe(true);
    expect(needsRationale('acceptance', 'refuse')).toBe(true);
    expect(needsRationale('preservation', 'refuse_access')).toBe(true);
    expect(needsRationale('preservation', 'invite')).toBe(false);
  });

  it('asks for the granted level when a certificate or a lower level is recorded', () => {
    expect(needsAchievedLevel('certify')).toBe(true);
    expect(needsAchievedLevel('miss_level')).toBe(true);
    expect(needsAchievedLevel('register')).toBe(false);
  });

  it('sends points as a plain decimal string and refuses anything it would have to guess', () => {
    expect(pointsString(' 12 ')).toBe('12');
    expect(pointsString('2,5')).toBe('2.5');
    expect(pointsString('0.25')).toBe('0.25');
    for (const bad of ['', '-1', '1e3', '1.000,5', '1.', 'abc', '.5']) expect(pointsString(bad)).toBeNull();
  });

  it('splits a text field into its non-empty lines', () => {
    expect(lines(' crack in slab \n\n  missing seal\n')).toEqual(['crack in slab', 'missing seal']);
    expect(lines('')).toEqual([]);
  });

  it('finds the first problem of a package scope and ignores empty rows', () => {
    expect(packageScopeProblem([pkg('a'), pkg(''), pkg('b')])).toBeNull();
    expect(packageScopeProblem([pkg('', 'Shell')])).toBe('ref_required');
    expect(packageScopeProblem([pkg('a'), pkg(' a ')])).toBe('ref_duplicate');
    expect(filledPackages([pkg(' a ', ' Shell '), pkg('')])).toEqual([pkg('a', 'Shell')]);
  });

  it('does not count an unreadable precondition as passed', () => {
    expect(preconditionNotApplicable({ met: true, params: { not_applicable: true } })).toBe(true);
    expect(preconditionNotApplicable({ met: true, params: {} })).toBe(false);
    expect(preconditionNotApplicable({ met: false, params: { not_applicable: true } })).toBe(false);
  });

  it('keeps a share between 0 and 100 and survives an empty whole', () => {
    expect(percent(1, 4)).toBe(25);
    expect(percent(0, 0)).toBe(0);
    expect(percent(9, 4)).toBe(100);
  });
});

describe('labels', () => {
  const ctx: LabelContext = { t: enT, language: 'de-CH', exists: (k) => enT(k) !== k };

  it('never shows a raw code', () => {
    expect(humanizeCode('pressure_test')).toBe('Pressure test');
    expect(vocab(enT, FINDING, 'some_new_finding')).toBe('Some new finding');
    expect(vocab(enT, FINDING, null)).toBe('');
  });

  it('puts the reference into the sentence of a finding', () => {
    expect(findingText(enT, 'stage_without_owner', 'Factory acceptance test')).toBe(
      'Stage Factory acceptance test has no owner',
    );
  });

  it('names a catalogue item by key, then by its own text, then by its code', () => {
    const shipped = { code: 'factory_test', name_key: 'quality_concept.catalogue.stage.factory_test' };
    expect(catalogueName(ctx, shipped)).toBe('Factory acceptance test');
    expect(catalogueName(ctx, { code: 'own', labels: { de: 'Eigene Stufe', en: 'Own stage' } })).toBe('Eigene Stufe');
    expect(catalogueName(ctx, { code: 'own_stage', name_key: 'not.a.key' })).toBe('Own stage');
    expect(nameIn(ctx, [shipped], 'factory_test')).toBe('Factory acceptance test');
    expect(nameIn(ctx, [shipped], 'site_test')).toBe('Site test');
    expect(nameIn(ctx, undefined, null)).toBe('');
  });
});

describe('refusals', () => {
  const refused = (detail: unknown) => new ApiError(409, 'Conflict', { detail });

  it('reads the structured detail of a refusal', () => {
    const d = refusalDetail(
      refused({
        code: 'concept_incomplete',
        message_key: 'quality_concept.errors.concept_incomplete',
        message: 'Server text',
        violations: [{ code: 'standards_basis_missing', severity: 'error', ref: '', params: {} }],
      }),
    );
    expect(d?.code).toBe('concept_incomplete');
    expect(d?.violations).toHaveLength(1);
    expect(refusalDetail(new Error('offline'))).toBeNull();
    expect(refusalDetail(refused('plain text'))).toBeNull();
  });

  it('tells a project without a concept from any other failure', () => {
    expect(isConceptMissing(new ApiError(404, 'Not Found', { detail: { code: 'concept_missing' } }))).toBe(true);
    expect(isConceptMissing(new ApiError(404, 'Not Found', { detail: 'Project not found' }))).toBe(false);
    expect(isConceptMissing(new ApiError(403, 'Forbidden', { detail: { code: 'concept_missing' } }))).toBe(false);
  });

  it('shows the sentence of the key when the locale has it, the server sentence otherwise', () => {
    const key = 'quality_concept.errors.acceptance_regime_missing';
    expect(refusalText(enT, refused({ code: 'x', message_key: key, message: 'Server text' }))).toBe(
      'The acceptance unit has no acceptance regime.',
    );
    expect(refusalText(enT, refused({ code: 'x', message: 'Server text' }))).toBe('Server text');
    expect(refusalText(enT, 'nothing useful')).toBe('The action could not be completed.');
  });
});

describe('capability flags', () => {
  it('follows the flag when the record carries one and the fallback when it does not', () => {
    expect(may({ can: { edit: false } }, 'edit', true)).toBe(false);
    expect(may({ can: { edit: true } }, 'edit', false)).toBe(true);
    expect(may({ can: {} }, 'edit', false)).toBe(false);
    expect(may({}, 'edit')).toBe(true);
    expect(may(null, 'edit', false)).toBe(false);
  });

  it('gives a reason only for a closed action', () => {
    const row = { can: { accept: false, reopen: true }, can_reason: { accept: 'approver_added_evidence' } };
    expect(whyNot(row, 'accept')).toBe('approver_added_evidence');
    expect(whyNot(row, 'reopen')).toBeNull();
    expect(whyNot({}, 'accept')).toBeNull();
  });

  it('reads both waiver buttons and both test results from the flag the server names', () => {
    expect(canKey('approve_waiver')).toBe('decide_waiver');
    expect(canKey('reject_waiver')).toBe('decide_waiver');
    expect(canKey('pass')).toBe('record_pass');
    expect(canKey('fail')).toBe('record_fail');
    expect(canKey('request')).toBe('request');
  });

  it('turns the reason into the sentence of its error key', () => {
    const closed = gate(enT, { can: { edit: false }, can_reason: { edit: 'manage_required' } }, 'edit');
    expect(closed).toEqual({
      disabled: true,
      title: 'Only a manager or the owner of the quality area can change the plan.',
    });
    expect(gate(enT, { can: { edit: true } }, 'edit')).toEqual({ disabled: false, title: undefined });
    expect(gate(enT, {}, 'pass', false).disabled).toBe(true);
  });

  it('shows a code of the vocabulary as words and older free text as it was typed', () => {
    expect(vocabOrRaw(enT, EXPERT_FREQUENCY, 'once')).toBe('Once');
    expect(vocabOrRaw(enT, EXPERT_FREQUENCY, 'every second pour')).toBe('every second pour');
    expect(vocabOrRaw(enT, EXPERT_FREQUENCY, '')).toBe('');
  });
});

describe('references to records of another module', () => {
  it('sends a reference only when it changed, and null when it was emptied', () => {
    expect(refChange('expert_contact_id', 'c1', 'c1')).toEqual({});
    expect(refChange('expert_contact_id', null, '')).toEqual({});
    expect(refChange('expert_contact_id', undefined, 'c2')).toEqual({ expert_contact_id: 'c2' });
    expect(refChange('expert_contact_id', 'c1', '')).toEqual({ expert_contact_id: null });
  });
});

describe('reasons of closed actions', () => {
  it('lists each reason once, only for the actions asked about', () => {
    const row = {
      can: { edit: false, delete: false, accept: false, reopen: true },
      can_reason: { edit: 'manage_required', delete: 'manage_required', accept: 'invalid_transition' },
    };
    expect(closedReasons(row, ['edit', 'delete', 'reopen'])).toEqual(['manage_required']);
    expect(closedReasons(row, ['accept', 'edit'])).toEqual(['invalid_transition', 'manage_required']);
    expect(closedReasons({}, ['edit'])).toEqual([]);
    expect(closedReasons({ can: { decide_waiver: false }, can_reason: { decide_waiver: 'approver_is_requester' } }, ['approve_waiver', 'reject_waiver'])).toEqual([
      'approver_is_requester',
    ]);
  });
});
