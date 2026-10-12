// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for the delivery model tests. Each takes a partial override, so a
// test states only what it is about.

import type {
  Allocation,
  AllocationItem,
  AllocationMatrix,
  Comparison,
  Decision,
  DeliveryCatalogue,
  DeliveryForm,
  DeliveryModel,
  DeliveryOption,
  DeliveryPackage,
  ModelAction,
  ModelStatus,
  OwnerFurnishedItem,
} from '../api';

const NEUTRAL = 'delivery_model.catalogue.neutral';

export function form(code = 'design_build', over: Partial<DeliveryForm> = {}): DeliveryForm {
  return {
    code,
    name_key: `${NEUTRAL}.form.${code}.name`,
    description_key: `${NEUTRAL}.form.${code}.description`,
    aliases: [],
    design_responsibility: 'contractor',
    owner_construction_contracts: 'one',
    contractor_role: 'builder',
    price_basis_at_award: 'lump_sum',
    allowed_price_bases: ['lump_sum'],
    review_status: 'verified',
    source_url: '',
    ...over,
  };
}

export type Role = 'manager' | 'editor' | 'viewer';

/** `can` the way the server answers it for a role in a status, so a fixture reads like a response. */
export function capabilities(status: ModelStatus, role: Role = 'manager'): DeliveryModel['can'] {
  const editable = status === 'draft' || status === 'under_evaluation' || status === 'reopened';
  const blocks: Record<ModelAction, string | null> = {
    edit: editable ? null : 'model_not_editable',
    propose: status === 'proposed' ? 'decision_pending' : status === 'under_evaluation' || status === 'reopened' ? null : 'model_not_editable',
    withdraw: status === 'proposed' ? null : 'decision_not_pending',
    reopen: status === 'binding' ? null : 'model_not_binding',
    close_reopening: status === 'reopened' ? null : 'reopening_not_open',
  };
  const flag = (action: ModelAction, permitted: boolean) => {
    const reason = permitted ? blocks[action] : 'permission_missing';
    return { allowed: reason === null, reason };
  };
  return {
    edit: flag('edit', role !== 'viewer'),
    propose: flag('propose', role === 'manager'),
    withdraw: flag('withdraw', role === 'manager'),
    reopen: flag('reopen', role === 'manager'),
    close_reopening: flag('close_reopening', role === 'manager'),
  };
}

export function model(over: Partial<DeliveryModel> = {}, role: Role = 'manager'): DeliveryModel {
  return {
    id: 'm1',
    project_id: 'p1',
    catalogue_source: 'shipped',
    catalogue_id: 'neutral',
    catalogue_version: 1,
    selected_form_code: null,
    selected_form: null,
    status: 'under_evaluation',
    underground_risk_sharing: false,
    owner_capability: {},
    carrier: { document_id: 'doc1', document_type: 'procurement_strategy', document_status: 'draft', missing_reason: null },
    change_request_id: null,
    current_decision_id: null,
    approval_blocked_reason: null,
    can: capabilities(over.status ?? 'under_evaluation', role),
    version: 1,
    ...over,
  };
}

export function option(id: string, code: string, total: string | null, over: Partial<DeliveryOption> = {}): DeliveryOption {
  return { id, form_code: code, form: form(code), overrides: {}, notes: '', weighted_total: total, ...over };
}

/** Two forms on two criteria weighted 60 and 40, fully scored unless `scores` says otherwise. */
export function comparison(over: Partial<Comparison> = {}): Comparison {
  return {
    options: [option('o1', 'design_bid_build_single', '3.40'), option('o2', 'design_build', '4.20')],
    criteria: [
      {
        id: 'c1',
        code: 'cost_certainty_at_award',
        weight: '60',
        name_key: `${NEUTRAL}.criterion.cost_certainty_at_award.name`,
        rationale_key: `${NEUTRAL}.criterion.cost_certainty_at_award.scale`,
      },
      {
        id: 'c2',
        code: 'schedule',
        weight: '40',
        name_key: null,
        rationale_key: null,
      },
    ],
    scores: [
      { option_id: 'o1', criterion_code: 'cost_certainty_at_award', score: 3, rationale: '' },
      { option_id: 'o1', criterion_code: 'schedule', score: 4, rationale: '' },
      { option_id: 'o2', criterion_code: 'cost_certainty_at_award', score: 5, rationale: 'fixed price' },
      { option_id: 'o2', criterion_code: 'schedule', score: 3, rationale: '' },
    ],
    weights_total: '100',
    ...over,
  };
}

export function catalogue(over: Partial<DeliveryCatalogue> = {}): DeliveryCatalogue {
  return {
    id: 'neutral',
    version: 1,
    name_key: `${NEUTRAL}.name`,
    forms: [form('design_bid_build_single'), form('design_build'), form('cm_at_risk', { review_status: 'unconfirmed' })],
    parties: parties(),
    risk_categories: [],
    criteria: [],
    ...over,
  };
}

export function parties() {
  return [
    { code: 'owner', name_key: `${NEUTRAL}.party.owner` },
    { code: 'contractor', name_key: `${NEUTRAL}.party.contractor` },
    { code: 'shared', name_key: `${NEUTRAL}.party.shared` },
  ];
}

export function allocation(category: string, over: Partial<Allocation> = {}): Allocation {
  return {
    id: `a-${category}`,
    category_code: category,
    party: 'contractor',
    basis: 'contract',
    shares: {},
    rationale: '',
    not_applicable: false,
    source: 'catalogue_default',
    status: 'confirmed',
    confirmed_by: 'u1',
    confirmed_at: '2026-10-01T09:00:00+00:00',
    risk_item_ids: [],
    ...over,
  };
}

export function allocationItem(category: string, over: Partial<AllocationItem> = {}): AllocationItem {
  return {
    category_code: category,
    name_key: `${NEUTRAL}.risk.${category}.name`,
    description_key: `${NEUTRAL}.risk.${category}.description`,
    register_category: 'technical',
    allocation: null,
    default: { party: 'contractor', basis: 'contract', shares: null, rationale_key: null, source_url: '', review_status: 'verified' },
    findings: [],
    ...over,
  };
}

export function matrix(items: AllocationItem[], over: Partial<AllocationMatrix> = {}): AllocationMatrix {
  return { form_code: 'design_build', parties: parties(), items, orphans: [], total: items.length, offset: 0, limit: items.length, ...over };
}

export function pkg(id: string, over: Partial<DeliveryPackage> = {}): DeliveryPackage {
  return {
    id,
    code: id.toUpperCase(),
    title: `Package ${id}`,
    kind: 'construction',
    designs: false,
    builds: true,
    supplies: false,
    manages: false,
    party: 'contractor',
    contracting_party: 'owner',
    price_basis: 'lump_sum',
    standard_form: '',
    parent_id: null,
    scope: '',
    wbs_ref: '',
    boq_ref: '',
    need_date: null,
    status: 'planned',
    effective_status: 'planned',
    link: null,
    linked_contract_type: null,
    ...over,
  };
}

export function ofi(id: string, over: Partial<OwnerFurnishedItem> = {}): OwnerFurnishedItem {
  return {
    id,
    code: id.toUpperCase(),
    description: `Item ${id}`,
    item_kind: 'equipment',
    install_by: 'package',
    package_id: null,
    procurement_route: null,
    link: null,
    schedule_activity_id: null,
    need_by_date: null,
    expected_delivery_date: null,
    enquiry_date: null,
    lead_time_days: null,
    status: 'identified',
    findings: [],
    ...over,
  };
}

export function decision(over: Partial<Decision> = {}): Decision {
  return {
    id: 'd1',
    form_code: 'design_build',
    option_id: 'o2',
    status: 'proposed',
    rationale: 'One point of responsibility and a fixed price at award.',
    snapshot: { form: form('design_build'), options: comparison().options },
    owner_capability: {},
    dispositions: {},
    proposed_by: 'u1',
    proposed_at: '2026-10-02T10:00:00+00:00',
    approved_by: null,
    approved_at: null,
    approval_source: '',
    governance_document_id: null,
    supersedes_id: null,
    four_eyes_violated: false,
    is_current: true,
    ...over,
  };
}
