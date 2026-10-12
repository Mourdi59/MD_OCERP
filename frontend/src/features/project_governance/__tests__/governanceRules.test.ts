// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Pure rules behind the governance screens: who may press which button and
// why not, what a decision draft is missing, and how the matrix is built.

import { describe, expect, it } from 'vitest';

import type { GateDetail } from '../api';
import {
  canClearCondition,
  canConfirmCheck,
  canDecide,
  canManage,
  canSubmitGate,
  canWaiveCondition,
  roleAllows,
  roleManage,
  type Viewer,
} from '../access';
import { decisionProblems, toDecisionInput, waiverProblem, type DecisionDraft } from '../decisionRules';
import { buildMatrix } from '../matrix';
import { catalogueIdOf, catalogueName, humanizeCode, type LabelContext } from '../labels';
import { condition, detail, gate, matrixArea, matrixResponse, model } from './fixtures';

const manager: Viewer = { userId: 'u-manager', role: 'manager' };
const editor: Viewer = { userId: 'u-editor', role: 'editor' };
const viewer: Viewer = { userId: 'u-viewer', role: 'viewer' };

describe('roleAllows', () => {
  it.each([
    ['viewer', 'read', true],
    ['viewer', 'edit', false],
    ['editor', 'edit', true],
    ['editor', 'manage', false],
    ['manager', 'manage', true],
    ['admin', 'manage', true],
    ['estimator', 'edit', true],
    ['site_foreman', 'read', false],
    ['unknown_role', 'read', false],
    [null, 'read', false],
  ] as const)('%s at %s -> %s', (role, level, expected) => {
    expect(roleAllows(role, level)).toBe(expected);
  });
});

describe('canDecide reads the server answer', () => {
  const inReview = (can: Partial<GateDetail['can']>) => ({
    ...detail({ gate: gate({ status: 'in_review' }) }),
    can: { edit: true, decide: false, ...can },
  });

  it('allows when the server says the caller may decide', () => {
    expect(canDecide(model(), inReview({ decide: true }))).toBeNull();
  });
  it.each([
    ['decider_not_entitled', 'role_decide'],
    ['missing_permission', 'role_decide'],
    ['decider_is_area_owner', 'four_eyes'],
  ] as const)('maps the known code %s to %s', (code, reason) => {
    expect(canDecide(model(), inReview({ decide_reason: code }))).toBe(reason);
  });
  it('an unknown or missing code is passed through, never mapped onto a guessed reason', () => {
    expect(canDecide(model(), inReview({ decide_reason: 'budget_frozen_by_board' }))).toEqual({
      server: 'budget_frozen_by_board',
    });
    expect(canDecide(model(), inReview({}))).toEqual({ server: '' });
  });
  it('gate state and a stopped project explain first', () => {
    const preparing = { ...detail({ gate: gate({ status: 'in_preparation' }) }), can: { edit: true, decide: true } };
    expect(canDecide(model(), preparing)).toBe('gate_not_in_review');
    expect(canDecide(model({ stopped: true }), inReview({ decide: true }))).toBe('project_stopped');
  });
});

describe('canConfirmCheck', () => {
  const editable = { can: { edit: true, decide: false } };
  const a = () => detail().areas[0]!;

  it('needs an owner on the area first', () => {
    expect(canConfirmCheck(editor, model(), { ...a(), owner_user_id: null }, editable)).toBe('area_without_owner');
  });
  it('refuses someone who is not owner or deputy', () => {
    expect(canConfirmCheck(editor, model(), { ...a(), owner_user_id: 'someone-else' }, editable)).toBe('not_area_owner');
  });
  it('lets the owner and the deputy confirm', () => {
    expect(canConfirmCheck(editor, model(), { ...a(), owner_user_id: 'u-editor' }, editable)).toBeNull();
    expect(canConfirmCheck(editor, model(), { ...a(), deputy_user_id: 'u-editor' }, editable)).toBeNull();
  });
  it('follows the server edit flag, not the role', () => {
    const own = { ...a(), owner_user_id: 'u-editor' };
    expect(canConfirmCheck(editor, model(), own, { can: { edit: false, decide: false } })).toBe('role_edit');
    expect(canConfirmCheck(viewer, model(), { ...a(), owner_user_id: 'u-viewer' }, editable)).toBeNull();
  });
});

describe('other verdicts', () => {
  it('submit needs a gate in preparation and the edit flag', () => {
    const d = (status: 'in_preparation' | 'not_started', edit: boolean) => ({
      ...detail({ gate: gate({ status }) }),
      can: { edit, decide: false },
    });
    expect(canSubmitGate(model(), d('in_preparation', true))).toBeNull();
    expect(canSubmitGate(model(), d('not_started', true))).toBe('gate_not_ready_to_submit');
    expect(canSubmitGate(model(), d('in_preparation', false))).toBe('role_edit');
  });
  it('manage and waive follow the model flag', () => {
    expect(canManage(model({ can: { manage: true } }))).toBeNull();
    expect(canManage(model({ can: { manage: false } }))).toBe('role_manage');
    expect(canWaiveCondition(condition(), model({ can: { manage: true } }))).toBeNull();
    expect(canWaiveCondition(condition(), model({ can: { manage: false } }))).toBe('role_decide');
    expect(canWaiveCondition(condition({ status: 'cleared' }), model())).toBe('condition_closed');
  });
  it('before a model exists only the role can answer manage', () => {
    expect(roleManage(manager)).toBeNull();
    expect(roleManage(editor)).toBe('role_manage');
  });
  it('a condition owner who is an editor may clear; others may not', () => {
    expect(canClearCondition(editor, condition({ owner_user_id: 'u-editor' }))).toBeNull();
    expect(canClearCondition(editor, condition({ owner_user_id: 'other' }))).toBe('not_condition_owner');
    expect(canClearCondition(manager, condition({ owner_user_id: 'other' }))).toBeNull();
  });
});

describe('decisionProblems', () => {
  const base: DecisionDraft = {
    outcome: null,
    rationale: '',
    conditions: [],
    proceedAtRisk: [],
    acceptedNotApplicable: [],
    holdResumeDate: '',
  };
  const d = detail({ gate: gate({ status: 'in_review' }) });

  it('asks for an outcome first', () => {
    expect(decisionProblems(base, d, '2026-10-11')).toEqual(['outcome_required']);
  });
  it('a plain go needs no rationale', () => {
    expect(decisionProblems({ ...base, outcome: 'go' }, d, '2026-10-11')).toEqual([]);
  });
  it.each(['stop', 'hold', 'recycle', 'go_with_conditions'] as const)('%s without rationale is refused', (outcome) => {
    expect(decisionProblems({ ...base, outcome }, d, '2026-10-11')).toContain('rationale_required');
  });
  it('whitespace is not a rationale', () => {
    expect(decisionProblems({ ...base, outcome: 'stop', rationale: '   ' }, d, '2026-10-11')).toContain('rationale_required');
    expect(decisionProblems({ ...base, outcome: 'stop', rationale: 'Budget withdrawn' }, d, '2026-10-11')).toEqual([]);
  });
  it('go with conditions needs a condition with text', () => {
    const draft = { ...base, outcome: 'go_with_conditions' as const, rationale: 'r' };
    expect(decisionProblems(draft, d, '2026-10-11')).toContain('conditions_required');
    const empty = { ...draft, conditions: [{ rowId: 'a', text: ' ', severity: 'essential' as const }] };
    expect(decisionProblems(empty, d, '2026-10-11')).toContain('condition_text_required');
  });
  it('hold needs a resume date after today', () => {
    const draft = { ...base, outcome: 'hold' as const, rationale: 'r', holdResumeDate: '2026-10-11' };
    expect(decisionProblems(draft, d, '2026-10-11')).toContain('hold_needs_resume_date');
    expect(decisionProblems({ ...draft, holdResumeDate: '2026-11-01' }, d, '2026-10-11')).toEqual([]);
  });
  it('a go must accept every not-applicable area', () => {
    const na = detail({ gate: gate({ status: 'in_review' }), areas: [{ code: 'cost_finance', applicable: false }] });
    expect(decisionProblems({ ...base, outcome: 'go' }, na, '2026-10-11')).toContain('not_applicable_not_accepted');
    expect(
      decisionProblems({ ...base, outcome: 'go', acceptedNotApplicable: ['cost_finance'] }, na, '2026-10-11'),
    ).toEqual([]);
  });
  it('drops conditions and at-risk areas from any outcome but go with conditions', () => {
    const body = toDecisionInput({
      ...base,
      outcome: 'stop',
      rationale: ' Funding withdrawn ',
      conditions: [{ rowId: 'a', text: 'x', severity: 'critical' }],
      proceedAtRisk: ['cost_finance'],
    });
    expect(body).toMatchObject({ outcome: 'stop', rationale: 'Funding withdrawn', conditions: [], proceed_at_risk_areas: [] });
    expect(body.conditions[0]).toBeUndefined();
  });
  it('a waiver without rationale is refused', () => {
    expect(waiverProblem('  ')).toBe('waiver_needs_rationale');
    expect(waiverProblem('Covered by the insurer')).toBeNull();
  });
});

describe('matrix', () => {
  it('lays the server matrix out by phase: outcome, check, pending and owed documents', () => {
    const m = model();
    const decided = gate({ id: 'g1', code: 'strategy_to_brief', from_phase: 'strategy', status: 'decided', last_outcome: 'go_with_conditions' });
    const open = gate({ id: 'g2', code: 'brief_to_concept', from_phase: 'brief', sort_order: 2, status: 'in_review' });
    const ahead = gate({ id: 'g3', code: 'concept_to_design', from_phase: 'concept', sort_order: 3, status: 'not_started' });
    const data = buildMatrix({
      phases: m.phases,
      currentPhase: 'brief',
      matrix: matrixResponse({
        gates: [decided, open, ahead],
        next: { id: 'g2', code: 'brief_to_concept', status: 'in_review', blocker_count: 1 },
        areas: [
          matrixArea({
            cells: {
              brief_to_concept: {
                check_status: 'not_ready',
                rag: 'red',
                stale: false,
                documents: [{ document_id: 'd1', doc_type: 'business_case', status: 'in_review', required: true }],
              },
            },
          }),
        ],
      }),
    });
    expect(data.columns.map((c) => c.isCurrent)).toEqual([false, true, false]);
    const [c0, c1, c2] = data.rows[0]!.cells;
    expect(c0!.readiness).toEqual({ kind: 'decided', outcome: 'go_with_conditions' });
    expect(c1!.readiness).toEqual({ kind: 'check', status: 'not_ready', stale: false });
    expect(c1!.documents).toEqual([{ id: 'd1', docType: 'business_case', status: 'in_review' }]);
    expect(c2!.readiness).toEqual({ kind: 'pending' });
  });

  it('an open gate nobody assessed reads not assessed; a not-applicable area reads not applicable', () => {
    const open = gate({ id: 'g2', code: 'brief_to_concept', from_phase: 'brief', status: 'in_preparation' });
    const data = buildMatrix({
      phases: model().phases,
      currentPhase: 'brief',
      matrix: matrixResponse({
        gates: [open],
        areas: [matrixArea({ area_id: 'a1' }), matrixArea({ area_id: 'a2', applicable: false })],
      }),
    });
    expect(data.rows[0]!.cells[1]!.readiness).toEqual({ kind: 'check', status: 'not_assessed', stale: false });
    expect(data.rows[1]!.cells[1]!.readiness).toEqual({ kind: 'check', status: 'not_applicable', stale: false });
    expect(data.rows[0]!.cells[0]!.readiness).toEqual({ kind: 'none' });
  });

  it('a historic gate is not a column gate', () => {
    const data = buildMatrix({
      phases: model().phases,
      currentPhase: null,
      matrix: matrixResponse({ gates: [gate({ from_phase: 'strategy', historic: true })], areas: [matrixArea()] }),
    });
    expect(data.columns[0]!.gate).toBeNull();
  });
});

describe('labels', () => {
  const ctx = (known: Record<string, string>): LabelContext => ({
    t: (k) => known[k] ?? k,
    language: 'de',
    exists: (k) => k in known,
  });

  it('prefers the override, then the API label, then the catalogue key, then the code', () => {
    const known = { 'governance.catalogue.neutral.area.cost_finance': 'Kosten und Finanzen' };
    expect(catalogueName(ctx(known), { kind: 'area', code: 'cost_finance', override: 'Budget' })).toBe('Budget');
    expect(
      catalogueName(ctx(known), { kind: 'area', code: 'cost_finance', label: { key: null, text: { de: 'Kosten', en: 'Cost' } } }),
    ).toBe('Kosten');
    // hoai borrows its areas from neutral, so the neutral key must still be found
    expect(catalogueName(ctx(known), { kind: 'area', code: 'cost_finance', catalogueId: 'hoai_lph' })).toBe('Kosten und Finanzen');
    expect(catalogueName(ctx({}), { kind: 'area', code: 'cost_finance', catalogueId: 'hoai_lph' })).toBe('Cost finance');
  });
  it('never returns a raw key', () => {
    expect(humanizeCode('schedule_logistics')).toBe('Schedule logistics');
  });
  it('reads the catalogue id out of a gate reference', () => {
    expect(catalogueIdOf('shipped:hoai_lph@2')).toBe('hoai_lph');
    expect(catalogueIdOf('neutral')).toBe('neutral');
    expect(catalogueIdOf('')).toBeNull();
  });
});
