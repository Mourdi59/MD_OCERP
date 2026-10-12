// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Pure rules behind the governance screens: who may press which button and
// why not, what a decision draft is missing, and how the matrix is built.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import type { GateDetail } from '../api';
import {
  canAddCondition,
  canAddDocument,
  canClearCondition,
  canConfirmCheck,
  canDecide,
  canManage,
  canRaiseChange,
  canReopen,
  canResume,
  canSubmitGate,
  canWaiveCondition,
  documentVerdict,
  outcomeVerdict,
  reasonOfCode,
  type Viewer,
} from '../access';
import {
  AT_RISK_LIFTABLE,
  areaDocumentTypes,
  atRiskCandidates,
  conditionForDocument,
  coversDocument,
  decisionProblems,
  documentBlockers,
  emptyCondition,
  dayAfter,
  reopenProblem,
  reopenRewind,
  toConditionInput,
  toDecisionInput,
  waiverProblem,
  type DecisionDraft,
} from '../decisionRules';
import { frameContainerCode } from '../documentFiles';
import { buildMatrix } from '../matrix';
import { catalogueIdOf, catalogueName, humanizeCode, type LabelContext } from '../labels';
import { area, blocker, condition, detail, frameDocument, gate, gateDocument, matrixArea, matrixResponse, model } from './fixtures';

const editor: Viewer = { userId: 'u-editor' };
const viewer: Viewer = { userId: 'u-viewer' };

describe('no permission is derived from a role name', () => {
  const featureDir = join(__dirname, '..');
  // Screens, rules and their tests; this file is left out because it has to name what it looks for.
  const files = [
    ...readdirSync(featureDir).map((f) => join(featureDir, f)),
    ...readdirSync(__dirname)
      .filter((f) => f !== 'governanceRules.test.ts')
      .map((f) => join(__dirname, f)),
  ].filter((f) => /\.(ts|tsx)$/.test(f));
  const sources = files.map((f) => [f.slice(featureDir.length + 1), readFileSync(f, 'utf-8')] as const);

  it('reads the feature sources it is meant to check', () => {
    expect(sources.length).toBeGreaterThan(16);
    expect(sources.some(([f]) => f === 'access.ts')).toBe(true);
    expect(sources.some(([f]) => f.endsWith('governanceScreens.test.tsx'))).toBe(true);
  });

  it.each([
    'roleAllows',
    'roleManage',
    'userRole',
    'viewer.role',
    'ROLE_RANK',
    'ROLE_ALIASES',
    'shared/lib/roles',
  ])('no screen or rule mentions %s', (needle) => {
    expect(sources.filter(([, text]) => text.includes(needle)).map(([f]) => f)).toEqual([]);
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
  it('manage follows the model flag', () => {
    expect(canManage(model({ can: { manage: true, edit: true } }))).toBeNull();
    expect(canManage(model({ can: { manage: false, edit: true } }))).toBe('role_manage');
  });
  it('adding a document follows the flag of the area', () => {
    expect(canAddDocument(area({ can: { add_document: true } }))).toBeNull();
    expect(canAddDocument(area({ can: { add_document: false, add_document_reason: 'missing_permission' } }))).toBe('role_edit');
    expect(canAddDocument(area({ can: { add_document: false, add_document_reason: 'not_area_owner' } }))).toBe('not_area_owner');
    expect(canAddDocument(area({ can: { add_document: false, add_document_reason: 'area_retired' } }))).toEqual({
      server: 'area_retired',
    });
    // A server that sends no flag is not second-guessed.
    expect(canAddDocument(area())).toBeNull();
  });
  it('raising a change request follows the flag of the document', () => {
    const can = { attach: true, submit: true, return: true };
    expect(canRaiseChange(frameDocument({ can: { ...can, change_request: true } }))).toBeNull();
    expect(
      canRaiseChange(frameDocument({ can: { ...can, change_request: false, change_request_reason: 'not_area_owner' } })),
    ).toBe('not_area_owner');
    expect(
      canRaiseChange(frameDocument({ can: { ...can, change_request: false, change_request_reason: 'no_change_route' } })),
    ).toEqual({ server: 'no_change_route' });
    expect(canRaiseChange(frameDocument({ can }))).toBeNull();
  });
});

describe('conditions follow their own server flags', () => {
  it('clears when the server allows it, whoever the viewer is', () => {
    expect(canClearCondition(condition({ owner_user_id: 'somebody-else' }))).toBeNull();
  });
  it.each([
    ['not_condition_owner', 'not_condition_owner'],
    ['missing_permission', 'role_edit'],
    ['condition_not_open', 'condition_closed'],
  ] as const)('a refused clear with %s reads as %s', (code, reason) => {
    expect(canClearCondition(condition({ can: { clear: false, clear_reason: code, waive: true } }))).toBe(reason);
  });
  it('a refused clear never borrows the area sentence', () => {
    // The old server code for this was not_area_owner, which named the wrong thing.
    const verdict = canClearCondition(condition({ can: { clear: false, clear_reason: 'not_condition_owner', waive: true } }));
    expect(verdict).not.toBe('not_area_owner');
  });
  it.each([
    ['missing_permission', 'role_decide'],
    ['decider_not_entitled', 'role_decide'],
    ['decider_is_area_owner', 'four_eyes'],
  ] as const)('a refused waiver with %s reads as %s', (code, reason) => {
    expect(canWaiveCondition(condition({ can: { clear: true, waive: false, waive_reason: code } }))).toBe(reason);
  });
  it('waiving does not follow the manage flag of the model', () => {
    // A manager the route never named may not waive; the model flag would have let them.
    expect(canWaiveCondition(condition({ can: { clear: true, waive: false, waive_reason: 'decider_not_entitled' } }))).toBe(
      'role_decide',
    );
    expect(canWaiveCondition(condition({ can: { clear: false, waive: true } }))).toBeNull();
  });
  it('a closed condition is closed for both, whatever the flags say', () => {
    const closed = condition({ status: 'cleared', can: { clear: true, waive: true } });
    expect(canClearCondition(closed)).toBe('condition_closed');
    expect(canWaiveCondition(closed)).toBe('condition_closed');
  });
  it('an unknown refusal code travels as is', () => {
    expect(canWaiveCondition(condition({ can: { clear: true, waive: false, waive_reason: 'frozen_by_audit' } }))).toEqual({
      server: 'frozen_by_audit',
    });
  });
});

describe('gate actions follow the gate flags', () => {
  const withCan = (can: Partial<GateDetail['can']>) => ({ can: { edit: true, decide: true, ...can } });

  it('resume, reopen and add condition are allowed only by their flag', () => {
    expect(canResume(withCan({ resume: true }))).toBeNull();
    expect(canReopen(withCan({ reopen: true }))).toBeNull();
    expect(canAddCondition(withCan({ add_condition: true }))).toBeNull();
    // No flag is not a yes: the button stays closed and says the server did not allow it.
    expect(canResume(withCan({}))).toEqual({ server: '' });
    expect(canReopen(withCan({}))).toEqual({ server: '' });
    expect(canAddCondition(withCan({}))).toEqual({ server: '' });
  });
  it.each([
    ['missing_permission', 'role_decide'],
    ['decider_not_entitled', 'role_decide'],
    ['project_stopped', 'project_stopped'],
  ] as const)('a refused resume with %s reads as %s', (code, reason) => {
    expect(canResume(withCan({ resume: false, resume_reason: code }))).toBe(reason);
  });
  it('a refused reopen names the later gate through the server code', () => {
    expect(canReopen(withCan({ reopen: false, reopen_reason: 'later_gate_active' }))).toEqual({ server: 'later_gate_active' });
  });

  it('each outcome follows its own flag', () => {
    const approved = withCan({
      outcomes: {
        go: { allowed: true },
        go_with_conditions: { allowed: true },
        hold: { allowed: false, reason: 'route_not_pending' },
        recycle: { allowed: false, reason: 'route_not_pending' },
        stop: { allowed: false, reason: 'route_not_pending' },
      },
    });
    expect(outcomeVerdict(approved, 'go')).toBeNull();
    expect(outcomeVerdict(approved, 'go_with_conditions')).toBeNull();
    expect(outcomeVerdict(approved, 'stop')).toEqual({ server: 'route_not_pending' });
    expect(outcomeVerdict(approved, 'hold')).toEqual({ server: 'route_not_pending' });
  });
  it('an outcome the server did not answer for is left to the request', () => {
    expect(outcomeVerdict(withCan({}), 'stop')).toBeNull();
    expect(outcomeVerdict(withCan({ outcomes: { go: { allowed: false, reason: 'decider_is_area_owner' } } }), 'stop')).toBeNull();
  });
  it('missing_permission names the permission the action needs', () => {
    expect(reasonOfCode('missing_permission')).toBe('role_decide');
    expect(reasonOfCode('missing_permission', 'edit')).toBe('role_edit');
    expect(reasonOfCode('missing_permission', 'manage')).toBe('role_manage');
  });
});

describe('frame document actions', () => {
  it('without a flag from the server nothing is guessed', () => {
    const bare = frameDocument({ container_id: 'k1', can: undefined });
    expect(documentVerdict(bare, 'attach')).toBeNull();
    expect(documentVerdict(bare, 'return')).toBeNull();
    expect(canRaiseChange(bare)).toBeNull();
  });
  it('a document without a file cannot be submitted by anybody', () => {
    expect(documentVerdict(frameDocument({ container_id: null }), 'submit')).toBe('document_without_file');
    expect(documentVerdict(frameDocument({ container_id: 'k1' }), 'submit')).toBeNull();
  });
  it.each([
    ['not_area_owner', 'not_area_owner'],
    ['missing_permission', 'role_edit'],
  ] as const)('a refused attach with %s reads as %s', (code, reason) => {
    const doc = frameDocument({ can: { attach: false, attach_reason: code, submit: true, return: true } });
    expect(documentVerdict(doc, 'attach')).toBe(reason);
  });
  it('each action reads its own flag', () => {
    const doc = frameDocument({
      container_id: 'k1',
      can: { attach: true, submit: false, submit_reason: 'not_area_owner', return: false, return_reason: 'document_read_only' },
    });
    expect(documentVerdict(doc, 'attach')).toBeNull();
    expect(documentVerdict(doc, 'submit')).toBe('not_area_owner');
    expect(documentVerdict(doc, 'return')).toEqual({ server: 'document_read_only' });
  });
  it('the container made for a document is named by area and type, so a second try finds it', () => {
    expect(frameContainerCode('cost_finance', 'business_case')).toBe('FRAME-COST-FINANCE-BUSINESS-CASE');
    expect(frameContainerCode('cost_finance', 'business_case')).toBe(frameContainerCode('cost_finance', 'business_case'));
    expect(frameContainerCode('organisation', 'business_case')).not.toBe(frameContainerCode('cost_finance', 'business_case'));
  });
});

describe('proceed at risk', () => {
  const inReview = gate({ status: 'in_review' });

  it('offers exactly the areas whose blocker a proceed-at-risk lifts', () => {
    const d = detail({
      gate: inReview,
      blockers: [
        blocker('area_not_ready', 'organisation'),
        blocker('evidence_not_met', 'cost_finance'),
        blocker('check_stale', 'schedule'),
        blocker('required_document_not_approved', 'quality', 'quality_plan'),
        blocker('area_without_owner', 'risk'),
        blocker('condition_overdue'),
      ],
    });
    expect(atRiskCandidates(d).sort()).toEqual(['cost_finance', 'organisation']);
  });
  it('an area whose only blocker is a stale check is not offered', () => {
    // The server answers proceed_at_risk_area_not_blocking for it, so offering it is a trap.
    expect(atRiskCandidates(detail({ gate: inReview, blockers: [blocker('check_stale', 'schedule')] }))).toEqual([]);
  });
  it('an area that is stale and also not ready is offered once', () => {
    const d = detail({ gate: inReview, blockers: [blocker('check_stale', 'schedule'), blocker('area_not_ready', 'schedule')] });
    expect(atRiskCandidates(d)).toEqual(['schedule']);
  });
  it('the liftable set is the one the server enforces', () => {
    const evaluator = readFileSync(
      join(__dirname, '../../../../../backend/app/modules/project_governance/evaluator.py'),
      'utf-8',
    );
    const declared = /PROCEED_AT_RISK_LIFTABLE[^=]*=\s*frozenset\(\{([^}]*)\}\)/.exec(evaluator);
    expect(declared, 'evaluator.py no longer declares PROCEED_AT_RISK_LIFTABLE as a literal set').not.toBeNull();
    const server = [...declared![1]!.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]!).sort();
    expect(server.length).toBeGreaterThan(0);
    expect([...AT_RISK_LIFTABLE].sort()).toEqual(server);
  });
});

describe('conditions on a document', () => {
  const d = detail({
    gate: gate({ status: 'in_review' }),
    areas: [
      { code: 'organisation', documents: [gateDocument({ doc_type: 'business_case' }), gateDocument({ document_id: 'd2', doc_type: 'charter' })] },
      { area_id: 'a2', code: 'cost_finance', documents: [] },
    ],
    blockers: [
      blocker('required_document_not_approved', 'organisation', 'business_case'),
      blocker('area_not_ready', 'organisation'),
      // Without the pair there is nothing a condition could match on.
      blocker('required_document_not_approved', 'organisation', null),
    ],
  });

  it('a condition may name only a document of its own area', () => {
    expect(areaDocumentTypes(d.areas, 'organisation')).toEqual(['business_case', 'charter']);
    expect(areaDocumentTypes(d.areas, 'cost_finance')).toEqual([]);
    expect(areaDocumentTypes(d.areas, '')).toEqual([]);
  });
  it('finds the blockers that name a missing document', () => {
    expect(documentBlockers(d).map((b) => [b.area_code, b.document_type])).toEqual([['organisation', 'business_case']]);
  });
  it('the condition made for a missing document covers it by the pair the server matches on', () => {
    const missing = documentBlockers(d)[0]!;
    const made = conditionForDocument(missing, 'Hand in the business case');
    expect(made).toMatchObject({ area_code: 'organisation', document_type: 'business_case', text: 'Hand in the business case' });
    expect(coversDocument([made], missing)).toBe(true);
    expect(coversDocument([{ ...made, area_code: 'cost_finance' }], missing)).toBe(false);
    expect(coversDocument([{ ...made, document_type: '' }], missing)).toBe(false);
    expect(coversDocument([emptyCondition()], missing)).toBe(false);
  });
  it('sends the pair, and never a document without its area', () => {
    const missing = documentBlockers(d)[0]!;
    const body = toDecisionInput({
      outcome: 'go_with_conditions',
      rationale: 'Open point tracked',
      conditions: [{ rowId: 'r1', ...conditionForDocument(missing, 'Hand in the business case') }],
      proceedAtRisk: [],
      acceptedNotApplicable: [],
      holdResumeDate: '',
    });
    expect(body.conditions).toEqual([
      {
        text: 'Hand in the business case',
        severity: 'essential',
        area_code: 'organisation',
        document_type: 'business_case',
        owner_user_id: null,
        due_date: null,
      },
    ]);
    expect(toConditionInput({ ...emptyCondition(), text: 'x', area_code: '', document_type: 'business_case' })).toMatchObject({
      area_code: null,
      document_type: null,
    });
  });
});

describe('the first day a hold may end', () => {
  it('is the day after today, across a month end', () => {
    expect(dayAfter('2026-10-11')).toBe('2026-10-12');
    expect(dayAfter('2026-10-31')).toBe('2026-11-01');
  });
  it('leaves a value that is no date alone', () => {
    expect(dayAfter('')).toBe('');
  });
});

describe('reopening a gate', () => {
  it.each([
    ['go', 'forced'],
    ['go_with_conditions', 'forced'],
    ['stop', 'none'],
    ['hold', 'none'],
    ['recycle', 'none'],
    ['', 'none'],
  ] as const)('after %s the phase rewind is %s', (last_outcome, expected) => {
    expect(reopenRewind({ last_outcome })).toBe(expected);
  });
  it('needs a written reason', () => {
    expect(reopenProblem('  ')).toBe('rationale_required');
    expect(reopenProblem('Scope changed after the client review')).toBeNull();
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
