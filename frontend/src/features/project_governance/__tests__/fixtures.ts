// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for API shapes in the governance tests. Each returns a complete
// object so a test names only the fields its case is about.

import type {
  CheckStatus,
  GateArea,
  GateDetail,
  GovernanceArea,
  GovernanceCondition,
  GovernanceGate,
  GovernanceModel,
  Violation,
} from '../api';

export function model(over: Partial<GovernanceModel> = {}): GovernanceModel {
  return {
    id: 'm1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    current_phase: 'brief',
    four_eyes: true,
    decision_route_id: null,
    change_route_id: null,
    stopped: false,
    stopped_at: null,
    phases: [
      { code: 'strategy', order: 1, name: { key: 'governance.catalogue.neutral.phase.strategy', text: null } },
      { code: 'brief', order: 2, name: { key: 'governance.catalogue.neutral.phase.brief', text: null } },
      { code: 'concept', order: 3, name: { key: 'governance.catalogue.neutral.phase.concept', text: null } },
    ],
    ...over,
  };
}

export function area(over: Partial<GovernanceArea> = {}): GovernanceArea {
  return {
    id: 'a1',
    code: 'organisation',
    name_override: '',
    sort_order: 1,
    owner_user_id: 'u-owner',
    deputy_user_id: null,
    applicable: true,
    na_rationale: '',
    retired: false,
    ...over,
  };
}

export function gate(over: Partial<GovernanceGate> = {}): GovernanceGate {
  return {
    id: 'g1',
    code: 'strategy_to_brief',
    catalogue_id: 'shipped:neutral@1',
    from_phase: 'strategy',
    to_phase: 'brief',
    sort_order: 1,
    status: 'not_started',
    attempt_no: 1,
    target_date: '',
    schedule_activity_id: null,
    approval_instance_id: null,
    hold_resume_date: '',
    last_outcome: '',
    historic: false,
    version: 1,
    ...over,
  };
}

type AreaSeed = Partial<Omit<GateArea, 'check'>> & { check?: CheckStatus | null };

export function gateArea(seed: AreaSeed = {}): GateArea {
  const { check, ...rest } = seed;
  return {
    area_id: 'a1',
    code: 'organisation',
    owner_user_id: 'u-owner',
    deputy_user_id: null,
    applicable: true,
    evidence: [],
    documents: [],
    ...rest,
    check: check
      ? { status: check, rag: '', note: '', confirmed_by: null, confirmed_at: null, stale: false, na_rationale: '' }
      : null,
  };
}

export function detail(
  over: { gate?: GovernanceGate; areas?: AreaSeed[]; blockers?: Violation[]; decisions?: GateDetail['decisions'] } = {},
): GateDetail {
  return {
    gate: over.gate ?? gate(),
    blockers: over.blockers ?? [],
    areas: (over.areas ?? [{}]).map(gateArea),
    decisions: over.decisions ?? [],
  };
}

export function blocker(code: string, area_code: string | null = null): Violation {
  return { code, message_key: `governance.errors.${code}`, area_code, document_type: null, ref: null };
}

export function condition(over: Partial<GovernanceCondition> = {}): GovernanceCondition {
  return {
    id: 'c1',
    decision_id: 'dec1',
    gate_id: 'g1',
    gate_code: 'strategy_to_brief',
    area_code: 'organisation',
    document_type: null,
    text: 'Confirm the funding letter',
    owner_user_id: 'u-owner',
    due_date: '2026-11-01',
    severity: 'essential',
    status: 'open',
    evidence: '',
    cleared_by: null,
    cleared_at: null,
    waiver_rationale: '',
    waived_by: null,
    waived_at: null,
    escalated_at: null,
    ...over,
  };
}
