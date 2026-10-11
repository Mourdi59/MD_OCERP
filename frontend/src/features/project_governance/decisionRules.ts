// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The decision dialog's own reading of the rules the server enforces on
// POST .../gates/{id}/decide, so the decider sees what is missing before the
// request instead of after it. The server stays the authority: it repeats
// every check and adds the blockers the client cannot see.

import type { ConditionInput, DecisionInput, GateDetail, Outcome } from './api';
import type { KeyText } from './labels';

export interface ConditionDraft extends ConditionInput {
  /** Stable row id for React keys; never sent. */
  rowId: string;
}

export interface DecisionDraft {
  outcome: Outcome | null;
  rationale: string;
  conditions: ConditionDraft[];
  proceedAtRisk: string[];
  acceptedNotApplicable: string[];
  holdResumeDate: string;
}

export type DecisionProblem =
  | 'outcome_required'
  | 'rationale_required'
  | 'conditions_required'
  | 'condition_text_required'
  | 'hold_needs_resume_date'
  | 'not_applicable_not_accepted';

export const DECISION_PROBLEM: Record<DecisionProblem, KeyText> = {
  outcome_required: ['governance.project.decision.problem.outcome_required', 'Choose an outcome.'],
  rationale_required: [
    'governance.project.decision.problem.rationale_required',
    'Write down the reason. Every outcome other than go needs one on record.',
  ],
  conditions_required: [
    'governance.project.decision.problem.conditions_required',
    'A go with conditions needs at least one condition.',
  ],
  condition_text_required: [
    'governance.project.decision.problem.condition_text_required',
    'Every condition needs a text.',
  ],
  hold_needs_resume_date: [
    'governance.project.decision.problem.hold_needs_resume_date',
    'A hold needs a resume date after today.',
  ],
  not_applicable_not_accepted: [
    'governance.project.decision.problem.not_applicable_not_accepted',
    'Accept every area marked not applicable, or send the gate back.',
  ],
};

/** Outcomes whose rationale the record must carry. Everything except a plain go. */
export function needsRationale(outcome: Outcome | null): boolean {
  return outcome !== null && outcome !== 'go';
}

/** Area codes that are not applicable on this gate, by area flag or by check. */
export function notApplicableAreas(detail: GateDetail): string[] {
  return detail.areas
    .filter((a) => !a.applicable || a.check?.status === 'not_applicable')
    .map((a) => a.code);
}

/** Area codes whose readiness blocks the gate, which are the only ones a decider may name as proceeding at risk. */
export function atRiskCandidates(detail: GateDetail): string[] {
  const codes = new Set<string>();
  for (const b of detail.blockers) {
    if (b.area_code && (b.code === 'area_not_ready' || b.code === 'check_stale' || b.code === 'evidence_not_met')) {
      codes.add(b.area_code);
    }
  }
  return [...codes];
}

export function decisionProblems(draft: DecisionDraft, detail: GateDetail, today: string): DecisionProblem[] {
  const problems: DecisionProblem[] = [];
  if (!draft.outcome) return ['outcome_required'];
  if (needsRationale(draft.outcome) && !draft.rationale.trim()) problems.push('rationale_required');
  if (draft.outcome === 'go_with_conditions') {
    if (draft.conditions.length === 0) problems.push('conditions_required');
    else if (draft.conditions.some((c) => !c.text.trim())) problems.push('condition_text_required');
  }
  if (draft.outcome === 'hold' && (!draft.holdResumeDate || draft.holdResumeDate <= today)) {
    problems.push('hold_needs_resume_date');
  }
  if (draft.outcome === 'go' || draft.outcome === 'go_with_conditions') {
    const accepted = new Set(draft.acceptedNotApplicable);
    if (notApplicableAreas(detail).some((code) => !accepted.has(code))) problems.push('not_applicable_not_accepted');
  }
  return problems;
}

/** The request body for a draft that passed `decisionProblems`. */
export function toDecisionInput(draft: DecisionDraft): DecisionInput {
  const outcome = draft.outcome ?? 'go';
  const withConditions = outcome === 'go_with_conditions';
  return {
    outcome,
    rationale: draft.rationale.trim(),
    conditions: withConditions
      ? draft.conditions.map(({ rowId: _rowId, ...c }) => ({
          ...c,
          text: c.text.trim(),
          area_code: c.area_code || null,
          document_type: c.document_type || null,
          owner_user_id: c.owner_user_id || null,
          due_date: c.due_date || null,
        }))
      : [],
    proceed_at_risk_areas: withConditions ? draft.proceedAtRisk : [],
    accepted_not_applicable: draft.acceptedNotApplicable,
    hold_resume_date: outcome === 'hold' ? draft.holdResumeDate : null,
  };
}

/** Whether a waiver may be sent: the rationale is the whole of the rule the client can check. */
export function waiverProblem(rationale: string): 'waiver_needs_rationale' | null {
  return rationale.trim() ? null : 'waiver_needs_rationale';
}
