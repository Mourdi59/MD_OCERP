// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Rows shaped like the design API sends them, for the tests only.

import type {
  Deliverable,
  DesignRole,
  DesignSetup,
  Drawing,
  NumberingField,
  NumberingScheme,
  Permit,
  PermitItem,
  PhaseReadiness,
  Release,
  WbsNode,
} from '../api';
import type { DesignContext } from '../DesignBits';
import type { LabelContext } from '../labels';
import { enT } from './i18nMock';

export const labels: LabelContext = { t: enT, language: 'en', exists: (key) => enT(key) !== key };

export function field(over: Partial<NumberingField> = {}): NumberingField {
  return {
    code: 'discipline',
    label_key: 'design.catalogue.simple_sequential.field.discipline',
    labels: null,
    required: true,
    pattern: null,
    length_min: 1,
    length_max: 2,
    code_list: 'free',
    pad: null,
    source_field: 'input',
    joiner: null,
    ...over,
  };
}

export function scheme(over: Partial<NumberingScheme> = {}): NumberingScheme {
  return {
    id: 'simple_sequential',
    version: 1,
    name_key: 'design.catalogue.simple_sequential.name',
    labels: null,
    description_key: 'design.catalogue.simple_sequential.description',
    source_url: null,
    source_title: null,
    review_status: 'verified',
    fields: [
      field(),
      field({ code: 'number', label_key: 'design.catalogue.simple_sequential.field.number', source_field: 'counter', pad: 3 }),
    ],
    separator: '-',
    max_length: 20,
    ...over,
  };
}

export function setup(over: Partial<DesignSetup> = {}): DesignSetup {
  return {
    id: 's1',
    project_id: 'p1',
    scheme_source: 'shipped',
    scheme_id: 'simple_sequential',
    scheme_version: 1,
    reports_source: 'shipped',
    reports_id: 'default',
    reports_version: 1,
    previous_schemes: [],
    four_eyes_release: true,
    default_distribution_purpose: 'for_information',
    lead_designer_role_id: null,
    hierarchical_codes: true,
    wbs_separator: '.',
    target_suitability: {},
    approval_route_id: null,
    release_route_id: null,
    scheme: scheme(),
    reports_catalogue: {
      id: 'default',
      version: 1,
      name_key: 'design.catalogue.reports.default.name',
      labels: null,
      report_kinds: [],
      permit_steps: [],
    },
    phases: [
      { code: 'concept', order: 1, name: { key: null, text: { en: 'Concept design' } } },
      { code: 'permit', order: 2, name: { key: null, text: { en: 'Permit design' } } },
    ],
    ...over,
  };
}

export function role(over: Partial<DesignRole> = {}): DesignRole {
  return {
    id: 'r1',
    code: 'R-01',
    title: 'Architect',
    party_kind: 'lead_designer',
    discipline_code: 'A',
    contact_id: null,
    user_id: null,
    originator_code: 'ARC',
    contract_package_id: null,
    responsible_wbs_ids: [],
    state: 'active',
    ...over,
  };
}

export function wbsNode(over: Partial<WbsNode> = {}): WbsNode {
  return {
    id: 'w1',
    parent_id: null,
    code: '1',
    name: 'Building',
    level: 1,
    sort_order: 0,
    kind: 'location',
    discipline: null,
    closed: false,
    duplicate_code: false,
    references: {},
    ...over,
  };
}

export function deliverable(over: Partial<Deliverable> = {}): Deliverable {
  return {
    id: 'd1',
    code: 'DL-001',
    title: 'Permit drawings',
    phase_code: 'permit',
    role_id: 'r1',
    discipline_code: 'A',
    form_code: null,
    wbs_node_id: null,
    planned_count: 3,
    planned_count_rationale: '',
    required: true,
    required_for: [],
    target_suitability: null,
    waived: false,
    waived_rationale: '',
    state: 'in_progress',
    ...over,
  };
}

export function drawing(over: Partial<Drawing> = {}): Drawing {
  return {
    id: 'dr1',
    container_id: 'c1',
    number: 'A-001',
    title: 'Ground floor plan',
    scale: '1:100',
    sheet_size: 'A1',
    phase_code: 'permit',
    deliverable_id: 'd1',
    wbs_node_id: null,
    role_id: 'r1',
    planned_first_issue: null,
    forecast_issue: null,
    superseded_by_container_id: null,
    legacy_scheme: false,
    aliases: [],
    title_block_number: null,
    cde_state: 'shared',
    suitability_code: 'S2',
    discipline_code: 'A',
    form_code: null,
    revision_code: 'P01',
    current_revision_id: 'rev1',
    title_block_mismatch: false,
    last_issue: null,
    ...over,
  };
}

export function permitItem(over: Partial<PermitItem> = {}): PermitItem {
  return {
    id: 'i1',
    permit_id: 'pm1',
    kind: 'drawing',
    title: 'Site plan',
    container_id: 'c1',
    report_id: null,
    required: true,
    included_revision_id: null,
    present: true,
    state_ok: true,
    current_revision_id: 'rev1',
    ...over,
  };
}

export function permit(over: Partial<Permit> = {}): Permit {
  return {
    id: 'pm1',
    code: 'PP-001',
    title: 'Building permit',
    profile_code: 'neutral',
    authority_submission_id: null,
    review_cycle_id: null,
    target_submission_date: null,
    state: 'assembling',
    submitted_by: null,
    submitted_at: null,
    superseded_content: false,
    conditions: [],
    items: [],
    missing: [],
    ...over,
  };
}

export function release(over: Partial<Release> = {}): Release {
  return {
    id: 'rl1',
    code: 'REL-001',
    title: 'Permit set',
    purpose: 'for_approval',
    revision_ids: ['rev1'],
    state: 'draft',
    transmittal_ids: [],
    duplicate_reason: '',
    prepared_by: 'u1',
    issued_by: null,
    issued_at: null,
    ...over,
  };
}

export function readiness(over: Partial<PhaseReadiness> = {}): PhaseReadiness {
  return {
    code: 'permit',
    order: 2,
    name: { key: null, text: { en: 'Permit design' } },
    met: false,
    open_deliverables: [],
    open_reports: [],
    open_major_comments: 0,
    ...over,
  };
}

export function context(over: Partial<DesignContext> = {}): DesignContext {
  return {
    projectId: 'p1',
    setup: setup(),
    labels,
    roles: [],
    wbs: [],
    deliverables: [],
    drawings: [],
    personName: () => null,
    onChanged: () => undefined,
    ...over,
  };
}
