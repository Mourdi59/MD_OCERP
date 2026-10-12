// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Records shaped as the permits API sends them, for the tests only.

import type {
  Application,
  ConditionRow,
  Permit,
  Readiness,
  RequirementRow,
  Roadmap,
  TimelineRow,
} from '../api';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';

export const labels: LabelContext = { t: enT, language: 'en', exists: () => false };

export const emptyPage = { items: [], total: 0, offset: 0, limit: 100 };

export function page<T>(items: T[]) {
  return { items, total: items.length, offset: 0, limit: 100 };
}

export function roadmap(over: Partial<Roadmap> = {}): Roadmap {
  return {
    id: 'rm1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    jurisdiction: null,
    route_assessment_id: null,
    delivery_model_id: null,
    governance_document_id: null,
    state: 'draft',
    roadmap_area_code: null,
    conditions_area_code: null,
    internal_review: false,
    approval_route_id: null,
    escalation_days: 7,
    buffer_days: 14,
    ...over,
  };
}

export function requirement(over: Partial<RequirementRow> = {}): RequirementRow {
  return {
    id: 'r1',
    project_id: 'p1',
    permit_type_code: 'main_permit',
    title: 'Main building permit',
    applicable: true,
    applicability_rationale: '',
    applicant_role: 'owner',
    applicant_source: 'manual',
    applicant_rationale: '',
    applicant_party: '',
    applicant_contact_id: null,
    responsible_user_id: null,
    planned_submit_date: null,
    needed_by_activity_id: null,
    needed_by_date: '2026-09-01',
    clock_variant: '',
    expected_decision_date: null,
    schedule_activity_id: null,
    governance_area_code: null,
    conflict_accepted: false,
    follow_up_of_id: null,
    proposed_from_route: false,
    sort_order: 1,
    state: 'in_progress',
    category: 'building',
    name_key: null,
    depends_on: [],
    ...over,
  };
}

export function timelineRow(over: Partial<TimelineRow> = {}): TimelineRow {
  return {
    requirement_id: 'r1',
    needed_by: '2026-09-01',
    date_basis: 'manual',
    latest_decision: '2026-08-18',
    latest_submit: '2026-05-18',
    forecast_decision: '2026-08-01',
    forecast_reason: null,
    schedule_conflict: false,
    conflict_days: null,
    conflict_accepted: false,
    derived_from: null,
    state: 'in_progress',
    estimate: false,
    clock: null,
    ...over,
  };
}

export function application(over: Partial<Application> = {}): Application {
  return {
    id: 'a1',
    requirement_id: 'r1',
    attempt: 1,
    kind: 'new',
    parent_permit_id: null,
    discharges_condition_ids: [],
    authority_name: 'Building authority',
    authority_reference: 'BA-2026-0412',
    submitted_at: '2026-05-04',
    received_at: null,
    validated_at: null,
    review_cycle_ids: [],
    submission_id: null,
    cde_container_id: null,
    approval_instance_id: null,
    state: 'under_review',
    appeal_note: '',
    ...over,
  };
}

export function permit(over: Partial<Permit> = {}): Permit {
  return {
    id: 'pm1',
    requirement_id: 'r1',
    application_id: 'a1',
    decision_id: 'd1',
    permit_type_code: 'main_permit',
    scope: 'full',
    state: 'in_force',
    reference: 'BA-2026-0412/G',
    revocable: false,
    security_amount: null,
    security_currency: '',
    start_notified_at: null,
    valid_until: '2029-06-30',
    superseded_by_id: null,
    lapse_warning: null,
    ...over,
  };
}

export function condition(over: Partial<ConditionRow> = {}): ConditionRow {
  return {
    id: 'c1',
    permit_id: 'pm1',
    number: '1',
    text: 'Submit the site traffic plan before work starts.',
    kind: 'obligation',
    national_kind: '',
    trigger: 'before_start',
    stage_ref: '',
    event_text: '',
    due_date: null,
    topic: 'traffic',
    purpose: '',
    owner_user_id: 'u1',
    responsible_party: '',
    requires_authority_approval: false,
    evidence_required: '',
    requirement_id: null,
    hse_relevant: false,
    state: 'open',
    source: 'manual',
    confidence: null,
    text_span: '',
    confirmed: true,
    gate_condition_id: null,
    original_id: null,
    breach_ref_kind: '',
    breach_ref_id: null,
    breach_note: '',
    permit_reference: 'BA-2026-0412/G',
    permit_type_code: 'main_permit',
    overdue: false,
    breach_risk: false,
    evidence_count: 0,
    ...over,
  };
}

export function readiness(over: Partial<Readiness> = {}): Readiness {
  return { gate: 'start', status: 'ready', items: [], ...over };
}

/** A settled query, as the panels read it. */
export function loaded<T>(data: T) {
  return { data, isLoading: false, isError: false, error: null, refetch: () => undefined };
}
