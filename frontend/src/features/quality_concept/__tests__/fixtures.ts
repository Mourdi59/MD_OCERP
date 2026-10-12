// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Typed records for the quality concept tests. Shapes follow the router's
// `_*_out` helpers; nothing here is rendered outside a test.

import type {
  AcceptanceUnit,
  Catalogue,
  CatalogueRegime,
  Concept,
  Page,
  Proof,
  Readiness,
  StageDef,
  StageMatrix,
  StageProgress,
} from '../api';

export function page<T>(items: T[]): Page<T> {
  return { items, total: items.length, offset: 0, limit: 100 };
}

export function concept(over: Partial<Concept> = {}): Concept {
  return {
    id: 'c1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    state: 'draft',
    governance_doc_id: null,
    requirement_set_id: null,
    documentation_set_code: null,
    packages: [],
    holidays: [],
    revision_no: 0,
    submitted_by: null,
    submitted_at: null,
    catalogue_label: { key: 'quality_concept.catalogue.name.neutral', text: null },
    catalogue_review_status: 'verified',
    applicable_packages: [],
    findings: [],
    can: { manage: true, edit_plan: true, submit: false, submit_reason: 'concept_incomplete' },
    ...over,
  };
}

export const MAY_SUBMIT = { manage: true, edit_plan: true, submit: true, submit_reason: null };
export const PLAN_CLOSED = { manage: true, edit_plan: false, submit: false, submit_reason: 'invalid_transition' };
export const NOT_MANAGER = { manage: false, edit_plan: false, submit: false, submit_reason: 'manage_required' };

export const SHELL = { ref: 'pkg-shell', code: 'A', title: 'Structural shell', no_proofs_rationale: '' };

export const regime: CatalogueRegime = {
  code: 'fidic_taking_over',
  name_key: 'quality_concept.catalogue.regime.fidic_taking_over',
  country_code: null,
  contract_basis: 'standard_form',
  act_name: 'taking_over_certificate',
  partial_allowed: true,
  partial_term: 'section',
  reservable: ['defects'],
  refusal_needs_defect: false,
  effects: [{ effect: 'risk_transfer', review_status: 'unconfirmed' }],
};

export const catalogue: Catalogue = {
  id: 'neutral',
  version: 1,
  name_key: 'quality_concept.catalogue.name.neutral',
  standard_families: [{ code: 'concrete', name_key: 'quality_concept.catalogue.standard_family.concrete' }],
  requirement_categories: [
    { code: 'acoustics', name_key: 'quality_concept.catalogue.requirement_category.acoustics', verification_method: 'test' },
  ],
  certification_schemes: [],
  evidence_types: [
    {
      code: 'pressure_test',
      name_key: 'quality_concept.catalogue.evidence_type.pressure_test',
      kind: 'test',
      fulfilled_by: ['cc_test_result'],
      default_deliverer: 'contractor',
    },
  ],
  commissioning_stages: [
    {
      code: 'factory_test',
      name_key: 'quality_concept.catalogue.stage.factory_test',
      order: 1,
      default_release_party: 'qa',
      evidence_types: [],
    },
  ],
  acceptance_regimes: [regime],
  documentation_sets: [{ code: 'residential', name_key: 'quality_concept.catalogue.documentation_set.residential' }],
  preservation_subjects: [],
};

export function proof(over: Partial<Proof> = {}): Proof {
  return {
    id: 'pr1',
    package_ref: 'pkg-shell',
    plant_item_id: null,
    cx_system_id: null,
    evidence_type: 'pressure_test',
    title: '',
    deliverer_role: 'contractor',
    deliverer_contact_id: null,
    required_by_kind: 'stage',
    required_by_ref: 'factory_test',
    quantity_rule: {},
    review_by_role: '',
    source: 'manual',
    decision: 'none',
    decision_rationale: '',
    requested_by: null,
    decided_by: null,
    decided_at: null,
    derived_state: 'open',
    state: 'open',
    counted: 0,
    required: 1,
    findings: [],
    ...over,
  };
}

export const stageDef: StageDef = {
  id: 's1',
  code: 'factory_test',
  order: 1,
  name_override: '',
  owner_user_id: null,
  release_party_role: 'qa',
  release_user_ids: [],
  preconditions: [],
  evidence_types: [],
  applies_to: {},
  catalogue_code: 'factory_test',
};

export function progress(over: Partial<StageProgress> = {}): StageProgress {
  return {
    id: 'sp1',
    system_id: 'sys1',
    stage_code: 'factory_test',
    state: 'blocked',
    rationale: '',
    depends_on_system_ids: [],
    hold_gate_id: null,
    released_at: null,
    released_by: null,
    computed_state: 'blocked',
    preconditions: [{ code: 'proofs_delivered', met: false, reason: 'proofs_missing', params: {} }],
    ...over,
  };
}

export function matrix(rows: StageProgress[] = [], stages: StageDef[] = [stageDef]): StageMatrix {
  return {
    ...page(rows),
    stages,
    systems: rows.length ? [{ id: 'sys1', name: 'Ventilation plant', system_type: 'hvac', status: 'installed' }] : [],
  };
}

export function unit(over: Partial<AcceptanceUnit> = {}): AcceptanceUnit {
  return {
    id: 'u1',
    code: 'AU-1',
    title: 'Whole works',
    kind: 'total',
    package_refs: [],
    section_ref: '',
    regime_code: 'fidic_taking_over',
    planned_date: '2027-03-01',
    handover_package_id: null,
    state: 'planned',
    completion_notice_at: null,
    use_started_at: null,
    deadline_at: null,
    accepted_on: null,
    reservations: [],
    refusal_reason: '',
    refusal_defects: [],
    regime,
    deemed: [],
    effects_applied: [],
    effects_proposed: [],
    unmet: [],
    ...over,
  };
}

export const readiness: Readiness = { concept: true, approved: false, errors: [], preservation_unplanned: [] };
