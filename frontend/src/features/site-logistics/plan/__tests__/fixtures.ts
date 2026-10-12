// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Records in the shape the plan routes return them, for the screen tests.

import type {
  Complaint,
  Concept,
  Neighbourhood,
  CustomsCase,
  MediaConnection,
  MediaDemand,
  Permit,
  PlanCatalogue,
  PlanPage,
  Readiness,
  SiteArea,
  Stage,
  StageBalance,
  Transport,
} from '../api';

export function page<T>(items: T[]): PlanPage<T> {
  return { items, total: items.length, offset: 0, limit: items.length };
}

export const catalogue: PlanCatalogue = {
  id: 'neutral',
  version: 1,
  labels: null,
  jurisdiction: '',
  review_status: 'unconfirmed',
  area_kinds: [
    { code: 'site_total', counts_in_balance: false, balance_group: 'built' },
    { code: 'storage', counts_in_balance: true, balance_group: 'logistics' },
  ],
  access_kinds: [{ code: 'road_gate' }],
  load_classes: [],
  media_kinds: [{ code: 'power', capacity_unit: 'kVA', phase: 'both' }],
  transport_kinds: [{ code: 'heavy_oversize' }, { code: 'inbound_delivery' }],
  permit_kinds: [{ code: 'oversize_permit' }, { code: 'night_work' }],
  incoterms: [
    { code: 'DAP', risk_transfer_point: 'named place', export_clearance_by: 'seller', import_clearance_by: 'buyer', sea_only: false },
  ],
  customs_document_kinds: [{ code: 'commercial_invoice' }],
  noise_limits: [],
  neighbour_issue_kinds: [{ code: 'noise' }, { code: 'dust' }],
  pin: { source: 'shipped', id: 'neutral', version: 1 },
  resolved_thresholds: {},
};

export const stage: Stage = {
  id: 's1',
  code: 'shell',
  title: 'Shell works',
  ordinal: 1,
  state: 'planned',
  from_date: '2026-11-01',
  to_date: '2027-03-31',
  start: '2026-11-01',
  end: '2027-03-31',
};

export const area: SiteArea = {
  id: 'a1',
  code: 'store_north',
  name: 'North store',
  area_kind: 'storage',
  frame: 'local',
  area_m2: null,
  area_m2_declared: '1200.00',
  effective_m2: '1200.00',
  owner_party: '',
  allocations: [{ id: 'al1', site_area_id: 'a1', stage_id: 's1', area_kind: 'storage', allocated_m2: '800.00', use_note: 'Rebar' }],
};

export const openBalance: StageBalance = {
  stage,
  area: {
    site_total_m2: '5000.00',
    counted_m2: '4200.00',
    difference_m2: '800.00',
    difference_pct: '16.0',
    closed: false,
    by_group: { logistics: '4200.00' },
    by_kind: { storage: '4200.00' },
  },
  tolerance_pct: '2',
  overlaps: [],
  gaps: ['stage_without_site_setup'],
  exceeding: [],
  media: [
    {
      media_kind: 'power',
      stage_id: 's1',
      capacity_unit: 'kVA',
      demand_count: 2,
      required: '330.0',
      contracted: '250',
      reserve_pct: '10',
      short: true,
      unsourced: [],
      late: [],
    },
  ],
};

export const media: MediaConnection = {
  id: 'm1',
  media_kind: 'power',
  phase: 'construction',
  provider_name: 'Grid operator',
  connection_point: 'Substation at the east fence',
  capacity_unit: 'kVA',
  available_capacity: '400',
  contracted_capacity: '250',
  application_ref: 'APP-17',
  applied_on: '2026-09-01',
  promised_on: '2026-10-20',
  connected_on: null,
  document_ref: '',
  state: 'offered',
};

export const craneDemand: MediaDemand = {
  id: 'd1',
  media_connection_id: 'm1',
  media_kind: 'power',
  stage_id: 's1',
  consumer: 'Tower crane 1',
  site_plant_position_id: 'pp1',
  plant_item_id: null,
  peak_demand: '180',
  simultaneity_factor: '1',
  from_plant_position: true,
};

export const officeDemand: MediaDemand = {
  ...craneDemand,
  id: 'd2',
  consumer: 'Site offices',
  site_plant_position_id: null,
  peak_demand: '60',
  simultaneity_factor: '0.7',
  from_plant_position: false,
};

export const heavyTransport: Transport = {
  id: 't1',
  direction: 'inbound',
  transport_kind: 'heavy_oversize',
  title: 'Roof girder',
  carrier_name: 'Heavy haulage partner',
  origin: 'Fabrication yard',
  destination: 'Site',
  gate_id: null,
  planned_window_start: '2026-11-03T05:00:00+00:00',
  planned_window_end: '2026-11-03T07:00:00+00:00',
  customs_case_id: null,
  waste_record_ref: '',
  route_notes: '',
  escort_required: true,
  state: 'planned',
  arrived_on: null,
  axle_load_t: '12',
  gross_weight_t: '62.5',
  height_m: '4.2',
  width_m: '3.5',
  length_m: '24',
  turning_radius_m: null,
  load_class: null,
  is_heavy: true,
  gate_exceeded: [],
  gate_blocked: false,
  gate_needs_timezone: false,
  gate_passed_by_permit: null,
  permit_finding: 'heavy_without_permit',
  permits: [],
};

export const permit: Permit = {
  id: 'p1',
  transport_id: null,
  covers_transport_ids: ['t1'],
  permit_kind: 'oversize_permit',
  authority: 'Road traffic authority',
  reference: 'OS-2026-044',
  applied_on: '2026-10-01',
  valid_from: '2026-11-01',
  valid_to: '2026-11-30',
  allowed_windows: [{ weekdays: [0, 1, 2], from: '22:00', to: '05:00' }],
  conditions: 'Escort vehicle front and rear',
  document_ref: '',
  state: 'applied',
};

export const hiddenCase: CustomsCase = {
  id: 'c1',
  direction: 'import',
  title: 'Facade panels',
  incoterm: 'DAP',
  named_place: 'Site gate',
  transport_mode: 'road',
  country_of_origin: 'TR',
  country_of_destination: 'DE',
  declarant_party: 'buyer',
  broker_name: '',
  customs_value: null,
  currency: null,
  values_hidden: true,
  declaration_ref: '',
  cleared_on: null,
  state: 'open',
};

export const overdueComplaint: Complaint = {
  id: 'n1',
  kind: 'noise',
  reported_on: '2026-10-01',
  reporter: 'Resident of the street to the north',
  description: 'Deliveries before six in the morning',
  transport_id: null,
  delivery_id: null,
  owner_user_id: null,
  response: '',
  response_due: '2026-10-06',
  state: 'received',
  overdue: true,
};

export const notReady: Readiness = {
  ready: false,
  governance: null,
  passed_by_permit: [],
  items: [
    { code: 'no_errors', state: 'not_met', detail: 'heavy_without_permit' },
    { code: 'balance_closed', state: 'met', detail: '' },
  ],
  findings: [
    { rule: 'heavy_transport_permitted', code: 'heavy_without_permit', severity: 'error', ref: 't1', params: { title: 'Roof girder' } },
    { rule: 'zone_mapped', code: 'zone_not_mapped', severity: 'warning', ref: 'z1', params: { zone: 'Zone B' } },
  ],
};

/** What the server answers before anything was saved: defaults, and no id. */
export const unsavedConcept: Concept = {
  id: null,
  catalogue_source: 'shipped',
  catalogue_id: 'neutral',
  catalogue_version: 1,
  strategy: [],
  delivery_open: null,
  delivery_close: null,
  max_deliveries_per_hour: null,
  rules_text: '',
  document_ref: null,
  site_timezone: null,
  updated_at: null,
};

export const unsavedNeighbourhood: Neighbourhood = {
  id: null,
  zone_type: 'mixed',
  noise_limit_source: '',
  day_dba: null,
  night_dba: null,
  quiet_hours: [],
  parking_note: '',
  municipality_contact: '',
};
