// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Pure rules behind the governance screens: who may press which button and
// why not, what a decision draft is missing, and how the matrix is built.

import { describe, expect, it } from 'vitest';

import {
  canClearCondition,
  canConfirmCheck,
  canDecide,
  canManage,
  canSubmitGate,
  canWaiveCondition,
  roleAllows,
  type Viewer,
} from '../access';
import { decisionProblems, toDecisionInput, waiverProblem, type DecisionDraft } from '../decisionRules';
import { buildMatrix, nextGate } from '../matrix';
import { catalogueIdOf, catalogueName, humanizeCode, type LabelContext } from '../labels';
import { area, condition, detail, gate, model } from './fixtures';

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

describe('canDecide', () => {
  const inReview = detail({ gate: gate({ status: 'in_review' }) });

  it('lets an entitled manager decide a gate in review', () => {
    expect(canDecide(manager, model(), inReview)).toBeNull();
  });
  it('refuses an editor with the role reason', () => {
    expect(canDecide(editor, model(), inReview)).toBe('role_decide');
  });
  it('refuses a gate not yet in review', () => {
    expect(canDecide(manager, model(), detail({ gate: gate({ status: 'in_preparation' }) }))).toBe('gate_not_in_review');
  });
  it('applies four-eyes to an area owner and to a deputy', () => {
    const owned = detail({ gate: gate({ status: 'in_review' }), areas: [{ owner_user_id: 'u-manager' }] });
    expect(canDecide(manager, model({ four_eyes: true }), owned)).toBe('four_eyes');
    const deputised = detail({ gate: gate({ status: 'in_review' }), areas: [{ deputy_user_id: 'u-manager' }] });
    expect(canDecide(manager, model({ four_eyes: true }), deputised)).toBe('four_eyes');
  });
  it('lets the owner decide when the project switched four-eyes off', () => {
    const owned = detail({ gate: gate({ status: 'in_review' }), areas: [{ owner_user_id: 'u-manager' }] });
    expect(canDecide(manager, model({ four_eyes: false }), owned)).toBeNull();
  });
  it('refuses on a stopped project', () => {
    expect(canDecide(manager, model({ stopped: true }), inReview)).toBe('project_stopped');
  });
});

describe('canConfirmCheck', () => {
  it('needs an owner on the area first', () => {
    const a = detail().areas[0]!;
    expect(canConfirmCheck(editor, model(), { ...a, owner_user_id: null })).toBe('area_without_owner');
  });
  it('refuses someone who is not owner or deputy', () => {
    const a = detail().areas[0]!;
    expect(canConfirmCheck(editor, model(), { ...a, owner_user_id: 'someone-else' })).toBe('not_area_owner');
  });
  it('lets the owner confirm', () => {
    const a = detail().areas[0]!;
    expect(canConfirmCheck(editor, model(), { ...a, owner_user_id: 'u-editor' })).toBeNull();
  });
  it('tells a viewer it is the role', () => {
    const a = detail().areas[0]!;
    expect(canConfirmCheck(viewer, model(), { ...a, owner_user_id: 'u-viewer' })).toBe('role_edit');
  });
});

describe('other verdicts', () => {
  it('submit needs a gate in preparation and edit rights', () => {
    expect(canSubmitGate(editor, model(), detail({ gate: gate({ status: 'in_preparation' }) }))).toBeNull();
    expect(canSubmitGate(editor, model(), detail({ gate: gate({ status: 'not_started' }) }))).toBe('gate_not_ready_to_submit');
    expect(canSubmitGate(viewer, model(), detail({ gate: gate({ status: 'in_preparation' }) }))).toBe('role_edit');
  });
  it('manage is manager only', () => {
    expect(canManage(manager)).toBeNull();
    expect(canManage(editor)).toBe('role_manage');
  });
  it('a condition owner who is an editor may clear but not waive', () => {
    const c = condition({ owner_user_id: 'u-editor' });
    expect(canClearCondition(editor, c)).toBeNull();
    expect(canWaiveCondition(editor, c)).toBe('role_decide');
    expect(canClearCondition(editor, condition({ owner_user_id: 'other' }))).toBe('not_condition_owner');
    expect(canWaiveCondition(manager, condition({ status: 'cleared' }))).toBe('condition_closed');
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
  it('next gate is the first live undecided gate in order', () => {
    const gates = [
      gate({ id: 'g1', sort_order: 1, status: 'decided' }),
      gate({ id: 'g3', sort_order: 3, status: 'not_started' }),
      gate({ id: 'g2', sort_order: 2, status: 'in_review' }),
      gate({ id: 'gh', sort_order: 0, status: 'in_review', historic: true }),
    ];
    expect(nextGate(gates)?.id).toBe('g2');
    expect(nextGate([gate({ status: 'decided' })])).toBeNull();
  });

  it('cells carry the decided outcome, the next gate check and the owed documents', () => {
    const m = model();
    const a = area({ id: 'a1', code: 'cost_finance' });
    const decided = gate({ id: 'g1', code: 'strategy_to_brief', from_phase: 'strategy', status: 'decided', last_outcome: 'go_with_conditions' });
    const open = gate({ id: 'g2', code: 'brief_to_concept', from_phase: 'brief', sort_order: 2, status: 'in_review' });
    const data = buildMatrix({
      phases: m.phases,
      currentPhase: 'brief',
      areas: [a],
      gates: [decided, open],
      documents: [
        {
          id: 'd1',
          area_id: 'a1',
          doc_type: 'business_case',
          required_at_gates: ['brief_to_concept'],
          status: 'in_review',
          container_id: null,
          bound_revision_id: null,
          bound_content_hash: null,
          approved_gate_id: null,
          read_only: false,
        },
      ],
      nextDetail: detail({ gate: open, areas: [{ area_id: 'a1', code: 'cost_finance', check: 'not_ready' }] }),
    });
    expect(data.columns.map((c) => c.isCurrent)).toEqual([false, true, false]);
    const [c0, c1, c2] = data.rows[0]!.cells;
    expect(c0!.readiness).toEqual({ kind: 'decided', outcome: 'go_with_conditions' });
    expect(c1!.readiness).toEqual({ kind: 'check', status: 'not_ready', stale: false });
    expect(c1!.documents).toEqual([{ id: 'd1', docType: 'business_case', status: 'in_review' }]);
    expect(c2!.readiness).toEqual({ kind: 'none' });
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
