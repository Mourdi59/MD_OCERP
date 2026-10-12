// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Response bodies shaped like the procurement concept router sends them.
// Company names are trade descriptions, never real firms.

import type {
  AwardPackage,
  CatalogueSummary,
  Candidate,
  CandidateMatrix,
  Concept,
  Finding,
  Framework,
  FrameworkLedger,
  MarketSounding,
  PackageView,
  PinnedCatalogue,
  PrequalProfile,
  ScheduleView,
  ThresholdCheck,
} from '../api';

export const PID = 'p1';

type Can = Concept['can'];
const yes = { allowed: true, reason: null };
const no = (reason: string) => ({ allowed: false, reason });

/** The capability block as the server sends it: everything allowed, or each key refused with its code. */
export function can(refused: Partial<Record<keyof Can, string>> = {}): Can {
  const of = (k: keyof Can) => (refused[k] ? no(refused[k] as string) : yes);
  return { steer: of('steer'), edit_plan: of('edit_plan'), submit: of('submit'), return: of('return'), set_gate_fields: of('set_gate_fields') };
}

type PackageCan = PackageView['can'];
const PACKAGE_MOVES: Array<keyof PackageCan> = ['edit', 'hold', 'resume', 'cancel', 'confirm_shortlist', 'create_execution'];

/** The flags of one package row: everything allowed, or each key refused with its code. `all` refuses every move. */
export function packageCan(refused: Partial<Record<keyof PackageCan | 'all', string>> = {}): PackageCan {
  const of = (k: keyof PackageCan) => {
    const reason = refused[k] ?? refused.all;
    return reason ? no(reason) : yes;
  };
  return Object.fromEntries(PACKAGE_MOVES.map((k) => [k, of(k)])) as PackageCan;
}

/** A package with a procedure, as the server flags it: nothing to resume, the rest open. */
export const PLANNED_CAN = packageCan({ resume: 'package_not_on_hold' });
/** A package with no award plan yet: it can be planned, and nothing else exists to act on. */
export const UNPLANNED_CAN = packageCan({
  hold: 'package_not_found',
  resume: 'package_not_found',
  cancel: 'package_not_found',
  confirm_shortlist: 'package_not_found',
  create_execution: 'package_not_found',
});

/** A reader without steering: every write is refused with the same code. */
export const NO_RIGHTS = can({
  steer: 'not_procurement_owner',
  edit_plan: 'not_procurement_owner',
  submit: 'not_procurement_owner',
  return: 'not_procurement_owner',
  set_gate_fields: 'not_procurement_owner',
});

/** Steering is open, the plan is locked: a concept in review or approved. */
export const LOCKED = can({ edit_plan: 'concept_locked', submit: 'concept_locked', set_gate_fields: 'gate_fields_frozen' });

export function concept(patch: Partial<Concept> = {}): Concept {
  return {
    id: 'c1',
    project_id: PID,
    catalogue_source: 'shipped',
    catalogue_id: 'eu',
    catalogue_version: 1,
    jurisdiction: 'eu',
    client_type: 'sub_central',
    public_client: true,
    vat_rate_pct: '0',
    state: 'draft',
    stored_state: 'draft',
    governance_document_id: null,
    release_gate_code: '',
    resolved_release_gate_code: 'g3',
    governance_area_code: 'procurement',
    default_profile_id: 'pf1',
    submitted_by: null,
    approved_by: null,
    approved_at: null,
    four_eyes_violated: false,
    jurisdictions: [
      { code: 'none', name_key: 'procurement_concept.catalogue.jurisdiction.none', client_types: ['private'], private_client_type: 'private' },
      {
        code: 'eu',
        name_key: 'procurement_concept.catalogue.jurisdiction.eu',
        client_types: ['central', 'sub_central', 'utility', 'private'],
        private_client_type: 'private',
      },
    ],
    review_status: 'unconfirmed',
    can: can({ return: 'invalid_transition' }),
    ...patch,
  };
}

export function award(patch: Partial<AwardPackage> = {}): AwardPackage {
  return {
    id: 'k1',
    split_basis: 'trade',
    is_advance: false,
    advance_reason: '',
    estimated_value: '2400000.00',
    currency: 'EUR',
    lot_group: '',
    small_lot_exemption: false,
    procedure_code: 'open',
    tender_basis: 'detailed',
    framework_agreement_id: null,
    evaluation_method: 'lowest_price',
    need_date: '2027-06-01',
    lead_time_days: null,
    procedure_days: null,
    planned_start: null,
    prequal_profile_id: null,
    start_activity_id: null,
    award_activity_id: null,
    state: 'procedure_set',
    notes: '',
    ...patch,
  };
}

export function packageView(patch: Partial<PackageView> = {}, awardPatch: Partial<AwardPackage> | null = {}): PackageView {
  return {
    contract_package: {
      id: 'k1',
      code: 'CP-01',
      title: 'Structural works',
      kind: 'construction',
      parent_id: null,
      scope: '',
      boq_ref: '',
      need_date: null,
      status: 'planned',
      execution_link: null,
    },
    package_kind: 'works',
    award: awardPatch === null ? null : award(awardPatch),
    threshold:
      awardPatch === null
        ? null
        : { status: 'unconfirmed', allowed: ['open', 'restricted'], thresholds: [], small_lot_exempt: false, aggregated_value: '2400000.00' },
    schedule: awardPatch === null ? null : { award_date: '2027-06-01', start_date: '2027-03-10', procedure_days: 83 },
    can: awardPatch === null ? UNPLANNED_CAN : PLANNED_CAN,
    ...patch,
  };
}

export const supplyPackage: PackageView = packageView(
  {
    contract_package: {
      id: 'k2',
      code: 'CP-02',
      title: 'Precast supply',
      kind: 'supply',
      parent_id: null,
      scope: '',
      boq_ref: '',
      need_date: null,
      status: 'planned',
      execution_link: null,
    },
    package_kind: 'supply',
  },
  { id: 'k2', estimated_value: '310000.00', procedure_code: 'framework_call_off', is_advance: true, advance_reason: 'Long lead item' },
);

export const unplannedPackage: PackageView = packageView(
  {
    contract_package: {
      id: 'k3',
      code: 'CP-03',
      title: 'Facade',
      kind: 'construction',
      parent_id: null,
      scope: '',
      boq_ref: '',
      need_date: null,
      status: 'planned',
      execution_link: null,
    },
  },
  null,
);

export const agreementPackage: PackageView = packageView(
  {
    contract_package: {
      id: 'k4',
      code: 'CP-00',
      title: 'Project agreement',
      kind: 'project_agreement',
      parent_id: null,
      scope: '',
      boq_ref: '',
      need_date: null,
      status: 'planned',
      execution_link: null,
    },
    package_kind: null,
    can: packageCan({ all: 'package_kind_not_procured' }),
  },
  null,
);

export const blockingFinding: Finding = {
  code: 'package_without_procedure_plan',
  severity: 'error',
  ref: 'CP-03',
  blocks_approval: true,
  message_key: 'procurement_concept.findings.package_without_procedure_plan',
};

export const warningFinding: Finding = {
  code: 'threshold_source_unconfirmed',
  severity: 'warning',
  ref: 'CP-01',
  blocks_approval: false,
  message_key: 'procurement_concept.findings.threshold_source_unconfirmed',
};

/** One row of the catalogue list, with the laws it brings. */
export const catalogueRow: CatalogueSummary = {
  source: 'shipped',
  id: 'eu',
  code: 'eu',
  name: { key: 'procurement_concept.catalogue.eu.name', text: null },
  state: 'published',
  versions: [1],
  latest_version: 1,
  review_status: 'unconfirmed',
  jurisdictions: [
    { code: 'none', name_key: 'procurement_concept.catalogue.jurisdiction.none', client_types: ['private'], private_client_type: 'private' },
    {
      code: 'eu',
      name_key: 'procurement_concept.catalogue.jurisdiction.eu',
      client_types: ['central', 'sub_central', 'utility', 'private'],
      private_client_type: 'private',
    },
  ],
};

export const catalogue: PinnedCatalogue = {
  id: 'eu',
  version: 1,
  name_key: 'procurement_concept.catalogue.eu.name',
  review_status: 'unconfirmed',
  procedures: [
    { code: 'open', name_key: 'procurement_concept.catalogue.procedure.open', sector: 'public', stages: 1, has_prequalification: false, negotiation_allowed: false, tender_basis_allowed: ['detailed', 'functional'], min_bidders: null },
    { code: 'direct_award', name_key: 'procurement_concept.catalogue.procedure.direct_award', sector: 'both', stages: 1, has_prequalification: false, negotiation_allowed: true, tender_basis_allowed: ['detailed'], min_bidders: 1 },
  ],
  jurisdictions: [
    { code: 'eu', name_key: 'procurement_concept.catalogue.jurisdiction.eu', client_types: ['central', 'sub_central', 'private'], private_client_type: 'private' },
  ],
  prequal_criteria: [
    { code: 'exclusion_grounds', name_key: 'procurement_concept.catalogue.criterion.exclusion_grounds', group: 'legal', kind: 'pass_fail', default_weight: '0' },
    { code: 'similar_projects', name_key: 'procurement_concept.catalogue.criterion.similar_projects', group: 'experience', kind: 'scored', default_weight: '60' },
    { code: 'hse_record', name_key: 'procurement_concept.catalogue.criterion.hse_record', group: 'hse', kind: 'scored', default_weight: '40' },
  ],
};

export const thresholdCheck: ThresholdCheck = {
  package_id: 'k1',
  checked_on: '2027-03-10',
  status: 'unconfirmed',
  single_value: '2400000.00',
  aggregated_value: '2400000.00',
  small_lot_exempt: false,
  thresholds: [
    {
      contract_kind: 'works',
      client_type: 'sub_central',
      amount: '5538000',
      currency: 'EUR',
      vat_basis: 'net',
      effect: 'above_requires_publication',
      source_url: 'https://example.org/thresholds',
      review_status: 'unconfirmed',
      valid_from: '2026-01-01',
      valid_to: null,
      compared_value: '2400000.00',
      position: 'below',
    },
  ],
  procedures: [
    { code: 'open', name_key: 'procurement_concept.catalogue.procedure.open', allowed: true, reason: null },
    { code: 'two_stage_negotiated', name_key: 'procurement_concept.catalogue.procedure.two_stage_negotiated', allowed: false, reason: 'private_procedure_for_public_client' },
  ],
  findings: [warningFinding],
};

export const profile: PrequalProfile = {
  id: 'pf1',
  package_id: null,
  name: 'Standard works prequalification',
  criteria: [
    { code: 'exclusion_grounds', kind: 'pass_fail', weight: '0' },
    { code: 'similar_projects', kind: 'scored', weight: '60' },
    { code: 'hse_record', kind: 'scored', weight: '40' },
  ],
  pass_mark: '60.00',
  validity_months: 12,
  in_use: true,
  can: { edit: yes, delete: no('profile_in_use') },
};

export function candidate(patch: Partial<Candidate> = {}): Candidate {
  return {
    id: 'cand1',
    package_id: 'k1',
    subcontractor_id: 's1',
    vendor_id: null,
    name: 'Regional structural works contractor',
    registered: true,
    source: 'own_list',
    list: 'short',
    decision_rationale: '',
    conflict_of_interest_declared: false,
    conflict_note: '',
    scores: [
      { criterion_code: 'exclusion_grounds', passed: true, score: null },
      { criterion_code: 'similar_projects', passed: null, score: '88.00' },
      { criterion_code: 'hse_record', passed: null, score: '75.00' },
    ],
    total_score: '82.80',
    passed_all: true,
    missing_criteria: [],
    evidence: [{ kind: 'certificate', ref: 'certificate:1', type: 'iso_9001', expires: '2028-01-31' }],
    references: [
      { id: 'r1', project_name: 'School extension', client: 'Municipality', value: '1800000.00', currency: 'EUR', year: 2024, role: 'Main contractor', contact: '', verified: true },
    ],
    ...patch,
  };
}

export function matrix(patch: Partial<CandidateMatrix> = {}): CandidateMatrix {
  const items = patch.items ?? [
    candidate(),
    candidate({
      id: 'cand2',
      name: 'Facade and envelope specialist',
      subcontractor_id: null,
      registered: false,
      list: 'long',
      scores: [],
      total_score: '0.00',
      passed_all: false,
      missing_criteria: ['exclusion_grounds', 'similar_projects', 'hse_record'],
      evidence: [],
      references: [],
    }),
  ];
  return {
    package_id: 'k1',
    profile: { id: 'pf1', criteria: profile.criteria, pass_mark: '60.00' },
    min_bidders: 3,
    total: items.length,
    findings: [
      { code: 'shortlist_below_min_bidders', severity: 'error', ref: 'CP-01', blocks_approval: true },
    ],
    package_state: 'procedure_set',
    can: { add: yes, score: yes, reference: yes, set_list: yes, delete: yes, confirm_shortlist: yes },
    ...patch,
    items,
  };
}

export const soundingTight: MarketSounding = {
  id: 'ms1',
  package_ids: ['k1'],
  trade: 'Structural steel',
  held_on: '2026-09-15',
  method: 'meeting',
  participant_candidate_ids: [],
  findings: 'Fabricators are booked into next spring.',
  capacity_signal: 'tight',
  price_signal: 'above_estimate',
  lead_time_signal_days: 120,
  mitigation: '',
  resplit: false,
  unmitigated: true,
};

export const schedule: ScheduleView = {
  release_date: '2027-01-15',
  release_gate_code: 'g3',
  total: 2,
  offset: 0,
  limit: 2,
  items: [
    {
      package_id: 'k1',
      code: 'CP-01',
      title: 'Structural works',
      need_date: '2027-06-01',
      lead_time_days: null,
      procedure_code: 'open',
      procedure_days: 83,
      proposed_award_date: '2027-06-01',
      proposed_start_date: '2027-03-10',
      is_advance: false,
      start_activity_id: null,
      award_activity_id: null,
      findings: [],
    },
    {
      package_id: 'k3',
      code: 'CP-03',
      title: 'Facade',
      need_date: null,
      lead_time_days: null,
      procedure_code: null,
      procedure_days: null,
      proposed_award_date: null,
      proposed_start_date: null,
      is_advance: false,
      start_activity_id: null,
      award_activity_id: null,
      findings: [{ code: 'need_date_missing', severity: 'warning', ref: 'CP-03', blocks_approval: false }],
    },
  ],
};

export const framework: Framework = {
  id: 'fw1',
  code: 'FW-SUPPLY-01',
  title: 'Reinforcement and precast supply framework',
  subcontractor_id: null,
  vendor_id: null,
  supplier_name: 'Precast concrete supplier',
  scope: 'Reinforcement steel, precast elements and delivery to site',
  package_kinds: ['supply', 'supply_and_install'],
  lots: [],
  max_value: '2500000.00',
  currency: 'EUR',
  start_date: '2026-03-01',
  end_date: '2029-03-01',
  call_off_mode: 'direct',
  source_procedure_ref: 'Open procedure, framework award 2025',
  state: 'active',
  can: { edit: yes, transitions: ['exhausted', 'expired', 'terminated'] },
};

export const ledger: FrameworkLedger = {
  framework_id: 'fw1',
  max_value: '2500000.00',
  currency: 'EUR',
  call_off_value: '310000.00',
  remaining_value: '2190000.00',
  remaining_known: true,
  complete: true,
  unconverted_entries: 0,
  total: 1,
  items: [{ kind: 'award_package', id: 'k2', project_id: PID, amount: '310000.00', currency: 'EUR', state: 'procedure_set' }],
};
