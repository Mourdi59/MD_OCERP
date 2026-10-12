// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for the plant register tests. Each one returns a complete, valid
// object and takes overrides, so a test states only what it is about.

import { ApiError } from '@/shared/lib/api';

import type {
  FrameSummary,
  LimitMatrix,
  Page,
  Paper,
  PlantCatalogue,
  PlantItem,
  PlantViolation,
  Quote,
  Readiness,
  Slot,
  Spare,
} from '../api';

export const TODAY = '2026-10-12';

export function catalogue(over: Partial<PlantCatalogue> = {}): PlantCatalogue {
  return {
    id: 'neutral',
    version: 1,
    name_key: 'plant.catalogue.name',
    long_lead_threshold_weeks: 12,
    warn_days: 30,
    component_classes: [
      {
        code: 'power_transformer',
        name_key: 'plant.catalogue.class.power_transformer',
        item_class: 'main_component',
        discipline: 'electrical',
        typical_lead_weeks: { min: 80, max: 128, as_of: '2025-06-30', review_status: 'unconfirmed' },
        quote_max_age_days: 90,
        critical_by_default: true,
      },
      {
        code: 'kitchen_equipment',
        name_key: 'plant.catalogue.class.kitchen_equipment',
        item_class: 'user_equipment',
        discipline: 'mechanical',
        typical_lead_weeks: { min: 8, max: 16, as_of: '2025-06-30', review_status: 'unconfirmed' },
        quote_max_age_days: 180,
        critical_by_default: false,
      },
    ],
    redundancy_schemes: [
      { code: 'N', name_key: 'plant.catalogue.redundancy.n', min_quantity: 1 },
      { code: 'N+1', name_key: 'plant.catalogue.redundancy.n_plus_1', min_quantity: 2 },
    ],
    procurement_routes: [
      {
        code: 'contractor_furnished_installed',
        name_key: 'plant.catalogue.route.contractor_furnished_installed',
        acronym: 'CFCI',
        owner_furnished: false,
        needs_package: true,
      },
      {
        code: 'owner_furnished_contractor_installed',
        name_key: 'plant.catalogue.route.owner_furnished_contractor_installed',
        acronym: 'OFCI',
        owner_furnished: true,
        needs_package: true,
      },
    ],
    lead_time_sources: [
      { code: 'supplier_quote', name_key: 'plant.catalogue.source.supplier_quote', market_evidence: true },
      { code: 'expert_estimate', name_key: 'plant.catalogue.source.expert_estimate', market_evidence: false },
    ],
    spare_categories: [{ code: 'strategic_spares', name_key: 'plant.catalogue.spare.strategic_spares' }],
    maintenance_strategies: [{ code: 'preventive_interval', name_key: 'plant.catalogue.maintenance.preventive_interval' }],
    delivery_limit_steps: [
      { code: 'supply', name_key: 'plant.catalogue.step.supply', order: 1 },
      { code: 'offload', name_key: 'plant.catalogue.step.offload', order: 2 },
      { code: 'commission', name_key: 'plant.catalogue.step.commission', order: 3 },
    ],
    site_plant_kinds: [{ code: 'tower_crane', name_key: 'plant.catalogue.site_plant.tower_crane' }],
    it_service_kinds: [{ code: 'site_network', name_key: 'plant.catalogue.it_service.site_network', responsible_party: 'contractor' }],
    parties: [
      { code: 'supplier', name_key: 'plant.catalogue.party.supplier' },
      { code: 'contractor', name_key: 'plant.catalogue.party.contractor' },
    ],
    ...over,
  };
}

export function item(over: Partial<PlantItem> = {}): PlantItem {
  return {
    id: 'i1',
    project_id: 'p1',
    code: 'PL-001',
    title: 'Main power transformer 20/0.4 kV',
    description: '',
    component_class_code: 'power_transformer',
    item_class: 'main_component',
    quantity: '2.0000',
    unit: 'pcs',
    tag: '',
    space_ref: '',
    performance: [{ key: 'rated_power', value: '2500', unit: 'kVA' }],
    redundancy_scheme: 'N+1',
    vendor_policy: 'neutral',
    vendor_bound_reason: '',
    vendor_id: null,
    critical_override: null,
    critical_reason: '',
    need_activity_id: null,
    need_date_fixed: '2028-11-10',
    procurement_route: null,
    contract_package_id: null,
    purchase_order_id: null,
    maintenance_strategy: 'preventive_interval',
    no_strategic_spare_reason: '',
    long_lead_override: null,
    long_lead_override_reason: '',
    owner_user_id: null,
    status: 'enquired',
    service_asset_id: null,
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T08:00:00Z',
    critical: true,
    long_lead: true,
    long_lead_threshold_weeks: 12,
    effective_lead_weeks: 110,
    lead_source: 'supplier_quote',
    lead_basis: 'from_order',
    market_evidence: true,
    basis_quote_id: 'q2',
    basis_enquiry_date: '2026-09-02',
    quote_age_days: 40,
    quote_max_age_days: 90,
    quote_stale: false,
    need_date: '2028-11-10',
    date_basis: 'fixed',
    latest_order_date: '2026-08-14',
    float_days: -59,
    order_status: 'overdue',
    needs_slot: true,
    paper_id: null,
    paper_status: null,
    slot_id: null,
    slot_status: null,
    slot_after_order_date: false,
    delivery_limit_gaps: ['commission'],
    spare_categories: ['strategic_spares'],
    strategic_spares_ok: true,
    redundancy_ok: true,
    vendor_findings: [],
    ...over,
  };
}

export function quote(over: Partial<Quote> = {}): Quote {
  return {
    id: 'q2',
    plant_item_id: 'i1',
    source: 'supplier_quote',
    source_name: 'Transformer manufacturer A (budget quote)',
    enquiry_date: '2026-09-02',
    response_date: '2026-09-16',
    lead_weeks_min: 96,
    lead_weeks_max: 110,
    lead_basis: 'from_order',
    valid_until: null,
    document_ref: '',
    is_basis: true,
    superseded_by: null,
    note: '',
    created_at: '2026-09-16T08:00:00Z',
    ...over,
  };
}

export function slot(over: Partial<Slot> = {}): Slot {
  return {
    id: 's1',
    plant_item_id: 'i1',
    vendor_name: 'Transformer manufacturer A',
    slot_from: '2027-03-01',
    slot_to: '2027-09-30',
    reservation_fee: '12500.50',
    currency: 'EUR',
    fee_refundable: 'partial',
    fee_credited_to_order: true,
    convert_by_date: '2026-12-01',
    terms: '',
    commitment_item_id: null,
    document_ref: '',
    status: 'requested',
    created_at: '2026-09-20T08:00:00Z',
    ...over,
  };
}

export function paper(over: Partial<Paper> = {}): Paper {
  return {
    id: 'pp1',
    plant_item_id: 'i1',
    question: 'Which manufacturer supplies the switchgear?',
    options: [
      { code: 'a', title: 'Manufacturer A, from order', lead_weeks: 40, cost: '410000.00', currency: 'EUR', scores: { lead_time: '4' } },
      { code: 'b', title: 'Manufacturer B, from approved drawings', lead_weeks: 52, cost: '385000.00', currency: 'EUR', scores: { lead_time: '2' } },
    ],
    criteria: [{ code: 'lead_time', title: 'Lead time', weight: '4' }],
    scores: { a: '4.0000', b: '2.0000' },
    recommendation: 'a',
    rationale: 'Shorter lead time protects the energisation date.',
    approval_instance_id: null,
    status: 'draft',
    decided_at: null,
    created_at: '2026-09-25T08:00:00Z',
    ...over,
  };
}

export function spare(over: Partial<Spare> = {}): Spare {
  return {
    id: 'sp1',
    plant_item_id: 'i1',
    category: 'strategic_spares',
    description: 'Spare bushing set',
    quantity: '1.0000',
    unit: 'set',
    supply_by: 'supplier',
    handover_target: '',
    waiver_reason: '',
    status: 'required',
    ...over,
  };
}

export function page<T>(items: T[], total = items.length): Page<T> {
  return { items, total, offset: 0, limit: 500 };
}

export function matrix(over: Partial<LimitMatrix> = {}): LimitMatrix {
  return {
    steps: ['supply', 'offload', 'commission'],
    rows: [
      {
        item_id: 'i1',
        code: 'PL-001',
        title: 'Main power transformer 20/0.4 kV',
        item_class: 'main_component',
        cells: {
          supply: { party: 'supplier', contract_package_id: null },
          offload: { party: 'contractor', contract_package_id: null },
        },
      },
    ],
    ...over,
  };
}

export function frame(over: Partial<FrameSummary> = {}): FrameSummary {
  return {
    catalogue: 'shipped:neutral',
    item_count: 8,
    critical_count: 3,
    long_lead_count: 5,
    overdue_count: 1,
    by_item_class: { main_component: 6, user_equipment: 2 },
    by_route: { unset: 8 },
    site_plant: [],
    ...over,
  };
}

export function readiness(over: Partial<Readiness> = {}): Readiness {
  return {
    ready: false,
    error_findings: [],
    critical_open: ['PL-001', 'PL-002'],
    long_lead_open: ['PL-001'],
    frame_document_attached: false,
    ...over,
  };
}

/** A refusal exactly as the plant router sends it. */
export function refusal(status: number, code: string, message: string, violations?: PlantViolation[]): ApiError {
  return new ApiError(status, 'Refused', {
    detail: { code, message_key: `plant.errors.${code}`, message, ...(violations ? { violations } : {}) },
  });
}
