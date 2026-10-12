// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// REST client for the logistics plan: expansion stages, site areas and their
// balance, utility connections, the logistics concept, transports, permits,
// customs cases and the neighbourhood.
//
// Backend: backend/app/modules/site_logistics/router.py, mounted at
// /api/v1/site-logistics/. Every plan route lives under /projects/{id}/.
//
// Quantities and money are decimal strings and stay strings here. Errors
// arrive as `detail = {code, message_key, message, violations?}`; `message`
// is already in the reader's language.

import { ApiError, apiDelete, apiGet, apiPatch, apiPost, apiPut, downloadWithAuth, API_BASE } from '@/shared/lib/api';

export interface PlanPage<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

/** A write body: only the keys it carries are changed. */
export type Body = Record<string, unknown>;

/* ── Catalogue ────────────────────────────────────────────────────────── */

export interface CatalogueEntry {
  code: string;
  labels?: Record<string, string> | null;
  [extra: string]: unknown;
}

export type CatalogueGroup =
  | 'area_kinds'
  | 'access_kinds'
  | 'load_classes'
  | 'media_kinds'
  | 'transport_kinds'
  | 'permit_kinds'
  | 'customs_document_kinds'
  | 'noise_limits'
  | 'neighbour_issue_kinds';

export interface AreaKindEntry extends CatalogueEntry {
  counts_in_balance: boolean;
  balance_group: string;
}

export interface MediaKindEntry extends CatalogueEntry {
  capacity_unit: string;
  phase: string;
}

export interface NoiseLimitEntry extends CatalogueEntry {
  zone_type: string;
  day_dba: string | null;
  night_dba: string | null;
  quiet_hours: [string, string] | null;
  project_value_required: boolean;
}

export interface Incoterm {
  code: string;
  risk_transfer_point: string;
  export_clearance_by: string;
  import_clearance_by: string;
  sea_only: boolean;
}

export interface PlanCatalogue {
  id: string;
  version: number;
  labels?: Record<string, string> | null;
  jurisdiction: string;
  review_status: string;
  area_kinds: AreaKindEntry[];
  access_kinds: CatalogueEntry[];
  load_classes: CatalogueEntry[];
  media_kinds: MediaKindEntry[];
  transport_kinds: CatalogueEntry[];
  permit_kinds: CatalogueEntry[];
  incoterms: Incoterm[];
  customs_document_kinds: CatalogueEntry[];
  noise_limits: NoiseLimitEntry[];
  neighbour_issue_kinds: CatalogueEntry[];
  pin: { source: 'shipped' | 'tenant'; id: string; version: number | null };
  resolved_thresholds: Record<string, string | number>;
}

/** One catalogue a project may pin, as the governance catalogue list returns it. */
export interface CatalogueChoice {
  source: 'shipped' | 'tenant';
  id: string;
  code: string;
  name: { key: string | null; text: Record<string, string> | null };
  latest_version: number | null;
  review_status: string;
}

export function getCatalogue(projectId: string): Promise<PlanCatalogue> {
  return apiGet<PlanCatalogue>(`/v1/site-logistics/projects/${projectId}/catalogue`);
}

export function listCatalogueChoices(): Promise<PlanPage<CatalogueChoice>> {
  return apiGet<PlanPage<CatalogueChoice>>('/v1/project-governance/catalogues?kind=site_logistics');
}

export function pinCatalogue(projectId: string, body: Body): Promise<Concept> {
  return apiPut<Concept>(`/v1/site-logistics/projects/${projectId}/catalogue`, body);
}

/* ── Stages, areas, balance ───────────────────────────────────────────── */

export interface Stage {
  id: string;
  code: string;
  title: string;
  ordinal: number;
  state: string;
  from_date: string | null;
  to_date: string | null;
  /** The dates the stage runs, from its own dates or from the linked activities. */
  start: string | null;
  end: string | null;
}

export interface Allocation {
  id: string;
  site_area_id: string;
  stage_id: string;
  area_kind: string;
  allocated_m2: string | null;
  use_note: string;
}

export interface SiteArea {
  id: string;
  code: string;
  name: string;
  area_kind: string;
  frame: string;
  /** Measured from the outline, when the area has one. */
  area_m2: string | null;
  area_m2_declared: string | null;
  effective_m2: string | null;
  owner_party: string;
  allocations: Allocation[];
}

export interface MediaBalance {
  media_kind: string;
  stage_id: string;
  capacity_unit: string;
  demand_count: number;
  required: string;
  contracted: string;
  reserve_pct: string;
  short: boolean;
  unsourced: string[];
  late: string[];
}

export interface StageBalance {
  stage: Stage;
  area: {
    site_total_m2: string;
    counted_m2: string;
    difference_m2: string;
    difference_pct: string | null;
    closed: boolean;
    by_group: Record<string, string>;
    by_kind: Record<string, string>;
    reason?: string | null;
  };
  tolerance_pct: string;
  overlaps: string[][];
  gaps: string[];
  exceeding: string[];
  media: MediaBalance[];
}

export const listStages = (projectId: string) => apiGet<PlanPage<Stage>>(`/v1/site-logistics/projects/${projectId}/stages`);
export const listAreas = (projectId: string) => apiGet<PlanPage<SiteArea>>(`/v1/site-logistics/projects/${projectId}/areas`);
export const getBalance = (projectId: string) => apiGet<PlanPage<StageBalance>>(`/v1/site-logistics/projects/${projectId}/balance`);

export function putAllocations(projectId: string, areaId: string, items: Body[]): Promise<unknown> {
  return apiPut<unknown>(`/v1/site-logistics/projects/${projectId}/areas/${areaId}/allocations`, { items });
}

/* ── Utilities ────────────────────────────────────────────────────────── */

export interface MediaConnection {
  id: string;
  media_kind: string;
  phase: string;
  provider_name: string;
  connection_point: string;
  capacity_unit: string;
  available_capacity: string | null;
  contracted_capacity: string | null;
  application_ref: string;
  applied_on: string | null;
  promised_on: string | null;
  connected_on: string | null;
  document_ref: string;
  state: string;
}

export interface MediaDemand {
  id: string;
  media_connection_id: string | null;
  media_kind: string;
  stage_id: string;
  consumer: string;
  site_plant_position_id: string | null;
  plant_item_id: string | null;
  peak_demand: string | null;
  simultaneity_factor: string | null;
  /** Owned by a plant position on the site plan; the server refuses a direct edit. */
  from_plant_position: boolean;
}

export const listMedia = (projectId: string) => apiGet<PlanPage<MediaConnection>>(`/v1/site-logistics/projects/${projectId}/media`);
export const listDemands = (projectId: string, mediaId: string) =>
  apiGet<PlanPage<MediaDemand>>(`/v1/site-logistics/projects/${projectId}/media/${mediaId}/demands`);

/** The power demand a plant position owns; `null` removes it. Called by the site plan when a position is saved. */
export function putPlantPowerDemand(
  projectId: string,
  body: { site_plant_position_id: string; stage_id?: string | null; power_demand_kva: string | null; consumer?: string },
): Promise<{ demand: MediaDemand | null }> {
  return apiPut<{ demand: MediaDemand | null }>(`/v1/site-logistics/projects/${projectId}/plant-positions/power-demand`, body);
}

/* ── Concept ──────────────────────────────────────────────────────────── */

export interface Flow {
  flow_code: string;
  description: string;
  mode: string;
  storage_area_id: string | null;
  takt_schedule_id?: string | null;
  buffer_days: number;
}

export interface Concept {
  /** Null until the concept was saved once; reading never creates it. */
  id: string | null;
  catalogue_source: 'shipped' | 'tenant';
  catalogue_id: string;
  catalogue_version: number | null;
  strategy: Flow[];
  delivery_open: string | null;
  delivery_close: string | null;
  max_deliveries_per_hour: number | null;
  rules_text: string;
  document_ref: string | null;
  /** IANA zone of the site. Every time-of-day rule runs on this clock and is not checked without it. */
  site_timezone: string | null;
  updated_at: string | null;
}

export const getConcept = (projectId: string) => apiGet<Concept>(`/v1/site-logistics/projects/${projectId}/concept`);
export const putConcept = (projectId: string, body: Body) => apiPut<Concept>(`/v1/site-logistics/projects/${projectId}/concept`, body);

/* ── Transports and permits ───────────────────────────────────────────── */

export interface TransportPermitRef {
  id: string;
  permit_kind: string;
  state: string;
  valid_to: string | null;
}

export interface Transport {
  id: string;
  direction: string;
  transport_kind: string;
  title: string;
  carrier_name: string;
  origin: string;
  destination: string;
  gate_id: string | null;
  planned_window_start: string | null;
  planned_window_end: string | null;
  customs_case_id: string | null;
  waste_record_ref: string;
  route_notes: string;
  escort_required: boolean;
  state: string;
  arrived_on: string | null;
  axle_load_t: string | null;
  gross_weight_t: string | null;
  height_m: string | null;
  width_m: string | null;
  length_m: string | null;
  turning_radius_m: string | null;
  /** The load class the vehicle is measured against; without one the most permissive class of the catalogue. */
  load_class: string | null;
  /** Derived by the server from the load and the limits; never stored. */
  is_heavy: boolean;
  gate_exceeded: string[];
  /** The entrance limit is exceeded and nothing covers it. */
  gate_blocked: boolean;
  gate_needs_timezone: boolean;
  /** The permit that lets the load through an entrance whose limit it exceeds. */
  gate_passed_by_permit: { id: string; permit_kind: string; reference: string } | null;
  permit_finding: string | null;
  permits: TransportPermitRef[];
}

export interface PermitWindow {
  weekdays: number[];
  from: string;
  to: string;
}

export interface Permit {
  id: string;
  transport_id: string | null;
  covers_transport_ids: string[];
  permit_kind: string;
  authority: string;
  reference: string;
  applied_on: string | null;
  valid_from: string | null;
  valid_to: string | null;
  allowed_windows: PermitWindow[];
  conditions: string;
  document_ref: string;
  state: string;
}

export const listTransports = (projectId: string) => apiGet<PlanPage<Transport>>(`/v1/site-logistics/projects/${projectId}/transports`);
export const listPermits = (projectId: string) => apiGet<PlanPage<Permit>>(`/v1/site-logistics/projects/${projectId}/permits`);

/* ── Customs ──────────────────────────────────────────────────────────── */

export interface CustomsCase {
  id: string;
  direction: string;
  title: string;
  incoterm: string;
  named_place: string;
  transport_mode: string;
  country_of_origin: string;
  country_of_destination: string;
  declarant_party: string | null;
  broker_name: string;
  /** `null` together with `values_hidden` for a reader without the customs permission. */
  customs_value: string | null;
  currency: string | null;
  values_hidden: boolean;
  declaration_ref: string;
  cleared_on: string | null;
  state: string;
}

export interface CustomsLine {
  id: string;
  customs_case_id: string;
  description: string;
  hs_code: string;
  quantity: string | null;
  unit: string;
  net_mass_kg: string | null;
  value: string | null;
  /** Hidden together with the value. */
  currency: string | null;
  origin_country: string;
  preferential_origin: boolean;
  sort_order: number;
}

export interface CustomsDocument {
  id: string;
  customs_case_id: string;
  kind: string;
  required: boolean;
  document_ref: string;
  state: string;
}

export const listCustoms = (projectId: string) => apiGet<PlanPage<CustomsCase>>(`/v1/site-logistics/projects/${projectId}/customs`);
export const listLines = (projectId: string, caseId: string) =>
  apiGet<PlanPage<CustomsLine>>(`/v1/site-logistics/projects/${projectId}/customs/${caseId}/lines`);
export const listDocuments = (projectId: string, caseId: string) =>
  apiGet<PlanPage<CustomsDocument>>(`/v1/site-logistics/projects/${projectId}/customs/${caseId}/documents`);

/* ── Neighbourhood ────────────────────────────────────────────────────── */

export interface Neighbourhood {
  /** Null until the plan was saved once; the other fields are then the defaults. */
  id: string | null;
  zone_type: string | null;
  noise_limit_source: string | null;
  day_dba: string | null;
  night_dba: string | null;
  quiet_hours: string[];
  parking_note: string;
  municipality_contact: string;
}

export interface Complaint {
  id: string;
  kind: string;
  reported_on: string | null;
  reporter: string;
  description: string;
  transport_id: string | null;
  delivery_id: string | null;
  owner_user_id: string | null;
  response: string;
  response_due: string | null;
  state: string;
  /** Past its answer date and not yet acknowledged, decided by the server. */
  overdue: boolean;
}

export interface CoordinationEntry {
  id: string;
  entry_date: string | null;
  body: string;
  topic: string;
  outcome: string;
  next_action_due: string | null;
}

export const getNeighbourhood = (projectId: string) =>
  apiGet<{ plan: Neighbourhood }>(`/v1/site-logistics/projects/${projectId}/neighbourhood`).then((r) => r.plan);
export const putNeighbourhood = (projectId: string, body: Body) =>
  apiPut<Neighbourhood>(`/v1/site-logistics/projects/${projectId}/neighbourhood`, body);
export const listComplaints = (projectId: string) =>
  apiGet<PlanPage<Complaint>>(`/v1/site-logistics/projects/${projectId}/neighbour-issues`);
export const listCoordination = (projectId: string) =>
  apiGet<PlanPage<CoordinationEntry>>(`/v1/site-logistics/projects/${projectId}/coordination`);

/* ── Readiness, sweep, export ─────────────────────────────────────────── */

export interface Finding {
  rule: string;
  code: string;
  severity: 'error' | 'warning' | string;
  ref: string | null;
  params: Record<string, unknown>;
}

export interface Readiness {
  ready: boolean;
  /** Why the plan could not be placed in the governance model; null when it could. */
  governance: string | null;
  /** `unknown` is a check the server could not evaluate, which is not the same as failed. */
  items: { code: string; state: 'met' | 'not_met' | 'unknown'; detail: string }[];
  /** Loads above an entrance limit that a granted permit lets through. */
  passed_by_permit: { transport_id: string; title: string; id: string; permit_kind: string; reference: string }[];
  findings: Finding[];
}

export interface SweepResult {
  permits: Record<string, number>;
  complaints_overdue: number;
  transports_arrived: number;
}

export const getReadiness = (projectId: string) => apiGet<Readiness>(`/v1/site-logistics/projects/${projectId}/readiness`);
export const runSweep = (projectId: string) => apiPost<SweepResult>(`/v1/site-logistics/projects/${projectId}/sweep`, {});

export interface PlanCheck {
  rule_id: string;
  rule_name: string;
  severity: 'error' | 'warning' | string;
  passed: boolean;
  message: string;
  element_ref: string | null;
  suggestion: string | null;
}

export interface PlanValidation {
  status: string;
  score: number | null;
  rules_run: string[];
  counts: { passed: number; errors: number; warnings: number };
  results: PlanCheck[];
}

/** Runs the rule set of the plan. Reads only; nothing is stored. */
export const validatePlan = (projectId: string) =>
  apiPost<PlanValidation>(`/v1/site-logistics/projects/${projectId}/validate`, {});

export const REGISTERS = ['balance', 'media', 'transports', 'customs', 'neighbourhood', 'frame'] as const;
export type Register = (typeof REGISTERS)[number];

export function exportRegister(projectId: string, register: Register, format: 'pdf' | 'xlsx'): Promise<void> {
  return downloadWithAuth(
    `${API_BASE}/v1/site-logistics/projects/${projectId}/export/${register}?format=${format}`,
    `logistics-${register}.${format}`,
  );
}

/* ── Generic writes ───────────────────────────────────────────────────── */

/**
 * The collections that share one shape of write: POST to the collection,
 * PATCH / DELETE / transition on the item. Each path is written out in full
 * so that it can be compared with the served routes one by one.
 */
export type ResourceKind =
  | 'stage'
  | 'area'
  | 'media'
  | 'demand'
  | 'transport'
  | 'permit'
  | 'customs'
  | 'line'
  | 'document'
  | 'complaint'
  | 'coordination';

/** The router serves no such write for this kind of record; no screen offers it. */
function notServed(kind: ResourceKind, action: string): Promise<never> {
  return Promise.reject(new Error(`site logistics plan: no ${action} route for ${kind}`));
}

export function createItem(projectId: string, kind: ResourceKind, body: Body, parentId = ''): Promise<unknown> {
  switch (kind) {
    case 'stage':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/stages`, body);
    case 'area':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/areas`, body);
    case 'media':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/media`, body);
    case 'demand':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/media/${parentId}/demands`, body);
    case 'transport':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/transports`, body);
    case 'permit':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/permits`, body);
    case 'customs':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/customs`, body);
    case 'line':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/customs/${parentId}/lines`, body);
    case 'document':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/customs/${parentId}/documents`, body);
    case 'complaint':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/neighbour-issues`, body);
    case 'coordination':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/coordination`, body);
  }
}

export function updateItem(projectId: string, kind: ResourceKind, id: string, body: Body): Promise<unknown> {
  switch (kind) {
    case 'stage':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/stages/${id}`, body);
    case 'area':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/areas/${id}`, body);
    case 'media':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/media/${id}`, body);
    case 'demand':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/demands/${id}`, body);
    case 'transport':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/transports/${id}`, body);
    case 'permit':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/permits/${id}`, body);
    case 'customs':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/customs/${id}`, body);
    case 'line':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/customs-lines/${id}`, body);
    case 'document':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/customs-documents/${id}`, body);
    case 'complaint':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/neighbour-issues/${id}`, body);
    case 'coordination':
      return apiPatch<unknown>(`/v1/site-logistics/projects/${projectId}/coordination/${id}`, body);
  }
}

export function deleteItem(projectId: string, kind: ResourceKind, id: string): Promise<void> {
  switch (kind) {
    case 'stage':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/stages/${id}`);
    case 'area':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/areas/${id}`);
    case 'media':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/media/${id}`);
    case 'demand':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/demands/${id}`);
    case 'transport':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/transports/${id}`);
    case 'permit':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/permits/${id}`);
    case 'customs':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/customs/${id}`);
    case 'line':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/customs-lines/${id}`);
    case 'complaint':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/neighbour-issues/${id}`);
    case 'coordination':
      return apiDelete(`/v1/site-logistics/projects/${projectId}/coordination/${id}`);
    default:
      return notServed(kind, 'delete');
  }
}

export function transitionItem(projectId: string, kind: ResourceKind, id: string, target: string): Promise<unknown> {
  switch (kind) {
    case 'stage':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/stages/${id}/transition`, { target });
    case 'media':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/media/${id}/transition`, { target });
    case 'transport':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/transports/${id}/transition`, { target });
    case 'permit':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/permits/${id}/transition`, { target });
    case 'customs':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/customs/${id}/transition`, { target });
    case 'complaint':
      return apiPost<unknown>(`/v1/site-logistics/projects/${projectId}/neighbour-issues/${id}/transition`, { target });
    default:
      return notServed(kind, 'transition');
  }
}

/* ── Errors ───────────────────────────────────────────────────────────── */

/** One blocker of a refused transition; `fields` names the exceeded limits of a site entrance. */
export interface Violation {
  code: string;
  fields?: string[];
  params?: Record<string, unknown>;
}

export interface PlanProblem {
  code: string | null;
  message: string;
  violations: Violation[];
}

/** What the server said about a refused write: its own sentence, its code and every blocker it listed. */
export function planProblem(err: unknown): PlanProblem {
  const fallback = err instanceof Error ? err.message : String(err);
  if (!(err instanceof ApiError)) return { code: null, message: fallback, violations: [] };
  const detail = (err.body as { detail?: unknown } | null)?.detail;
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) {
    return { code: null, message: err.message, violations: [] };
  }
  const d = detail as { code?: unknown; message?: unknown; violations?: unknown };
  return {
    code: typeof d.code === 'string' ? d.code : null,
    message: typeof d.message === 'string' && d.message ? d.message : err.message,
    violations: Array.isArray(d.violations) ? (d.violations as Violation[]) : [],
  };
}

export const planKeys = {
  project: (projectId: string) => ['site-logistics-plan', projectId] as const,
  of: (projectId: string, ...rest: string[]) => ['site-logistics-plan', projectId, ...rest] as const,
};
