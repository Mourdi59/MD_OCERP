// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Shapes the engineering brief tests hand to the screens, written as the
// server sends them.

import type { Brief, BriefCatalogue, Can, ConceptItem, Milestone, ProgrammeLine, Requirement, SpecificationState, Study } from '../api';

export const yes: Can = { allowed: true, reason: null, applies: true };
export const no = (reason: string, applies = true): Can => ({ allowed: false, reason, applies });

export function brief(over: Partial<Brief> = {}, can: Partial<Brief['can']> = {}): Brief {
  return {
    id: 'b1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    status: 'draft',
    title: 'Hospital extension',
    summary: '',
    operation_proof_date: '2028-06-30',
    submitted_at: null,
    approved_at: null,
    approval_source: null,
    requirements_changed: false,
    requirement_count: 1,
    gates_in_use: false,
    can: {
      manage: yes,
      submit: yes,
      return: no('brief_not_in_review', false),
      approve: no('brief_not_in_review', false),
      edit: yes,
      publish: yes,
      ...can,
    },
    ...over,
  };
}

export const catalogue: BriefCatalogue = {
  id: 'neutral',
  version: 1,
  name_key: 'engineering_brief.catalogue.neutral.name',
  labels: null,
  requirement_categories: [
    { code: 'performance', name_key: 'engineering_brief.category.performance', labels: null, required: true, reference: '' },
    { code: 'availability', name_key: 'engineering_brief.category.availability', labels: null, required: true, reference: 'ISO 22301' },
  ],
  concept_topics: [{ code: 'supply', name_key: 'engineering_brief.topic.supply', labels: null, required: true }],
  programme_kinds: [{ code: 'net_room_area', name_key: 'engineering_brief.programme_kind.net_room_area', labels: null, default_unit: 'm2' }],
  milestone_kinds: [
    { code: 'operation_proof', name_key: 'engineering_brief.milestone_kind.operation_proof', labels: null, anchor: true, gate: false },
    { code: 'delivery', name_key: 'engineering_brief.milestone_kind.delivery', labels: null, anchor: false, gate: false },
  ],
  milestone_templates: [],
  verification_methods: ['inspection', 'test'],
  originator_roles: ['client', 'designer'],
  phases: ['brief', 'design'],
  priorities: ['must', 'should', 'could', 'wont'],
};

export function requirement(over: Partial<Requirement> = {}): Requirement {
  return {
    id: 'r1',
    entity: 'Cooling plant',
    attribute: 'Capacity',
    constraint_type: 'min',
    constraint_value: '500',
    unit: 'kW',
    category: 'performance',
    priority: 'must',
    verification_method: 'test',
    originator: '',
    originator_role: '',
    source_ref: '',
    rationale: '',
    phase: '',
    status: 'draft',
    answered_by: [],
    ...over,
  };
}

export function concept(over: Partial<ConceptItem> = {}): ConceptItem {
  return {
    id: 'c1',
    code: 'CON-001',
    topic_code: 'supply',
    title: 'Chilled water supply',
    description: '',
    decision: '',
    status: 'open',
    requirement_ids: [],
    ...over,
  };
}

export function programmeLine(over: Partial<ProgrammeLine> = {}): ProgrammeLine {
  return { id: 'g1', code: 'PRG-001', kind_code: 'net_room_area', label: 'Wards', unit: 'm2', quantity: '1250.50', basis: '', ...over };
}

export function milestone(over: Partial<Milestone> = {}): Milestone {
  return {
    id: 'm1',
    code: 'MS-001',
    kind_code: 'delivery',
    name: 'Chiller delivery',
    planned_date: '2027-03-01',
    lead_days: 30,
    successor_id: null,
    gate_code: null,
    permit_requirement_id: null,
    activity_id: null,
    gate: null,
    permit_state: null,
    published: false,
    findings: [],
    ...over,
  };
}

export function study(over: Partial<Study> = {}): Study {
  return {
    id: 's1',
    code: 'S-1',
    kind: 'site_analysis',
    title: 'Soil survey',
    scope: '',
    author: 'Geo Office',
    study_date: '2026-03-01',
    result: 'Bearing capacity sufficient.',
    conclusion: 'suitable',
    document_id: 'd1',
    document_name: 'Soil report.pdf',
    ...over,
  };
}

export function specification(over: Partial<SpecificationState> = {}): SpecificationState {
  const issue = (version_no: number, issued_at: string) => ({
    id: `i${version_no}`,
    version_no,
    title: 'Requirements specification',
    issued_at,
    issued_by: null,
    document_id: `doc${version_no}`,
    requirements_hash: `h${version_no}`,
    requirement_count: 1,
    note: '',
  });
  return {
    items: [issue(2, '2026-05-02T10:00:00Z'), issue(1, '2026-04-01T10:00:00Z')],
    current: true,
    stale: false,
    requirement_count: 1,
    detail: '',
    ...over,
  };
}
