// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// REST client for Staffing: the project staffing plan, its positions and the
// people on them, personnel files with their documents, travel and leave.
//
// Backend module: backend/app/modules/staffing/router.py, mounted at
// /api/v1/staffing/. Every project route lives under /projects/{project_id}/.
// The shapes below follow what the service returns, which is the contract.
//
// Errors arrive as `detail = {code, message_key, message, violations?, info?}`.
// The screens show the server's sentence for a refusal and list every
// violation of a refused submission.

import { ApiError, apiDelete, apiGet, apiPatch, apiPost, apiPut, downloadWithAuth } from '@/shared/lib/api';

const BASE = '/v1/staffing';

export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

/** A label as the catalogue list sends it: a message key for shipped items, texts per locale for tenant ones. */
export interface StaffingLabel {
  key: string | null;
  text: Record<string, string> | null;
}

export type Phase = 'development' | 'execution' | 'operation';
export type PlanStatus = 'draft' | 'in_review' | 'approved' | 'binding' | 'revising';
export type PositionStatus = 'open' | 'recruiting' | 'filled' | 'on_hold' | 'cancelled';
export type SettablePositionStatus = Exclude<PositionStatus, 'filled'>;
export type FillStatus = 'proposed' | 'confirmed' | 'ended';
export type HandoverStatus = 'planned' | 'done';
export type RecruitingChannel = 'internal' | 'agency' | 'direct' | 'framework' | 'consultant_contract';
export type FileStatus = 'active' | 'ended' | 'retention_hold' | 'anonymised';
export type EmploymentBasis = 'employee' | 'posted_worker' | 'contractor_staff' | 'consultant' | 'agency';
export type LawfulBasis = 'contract' | 'legal_obligation' | 'legitimate_interest';
export type TravelKind = 'mobilisation' | 'rotation' | 'business' | 'demobilisation';
export type TravelStatus = 'planned' | 'booked' | 'done' | 'cancelled';
export type LeaveStatus = 'requested' | 'approved' | 'taken' | 'cancelled';
export type FitForRole = 'yes' | 'with_restrictions' | 'no';
export type CellState = 'valid' | 'expiring' | 'expired' | 'missing' | 'waived' | 'not_required';
export type ExportFormat = 'pdf' | 'xlsx';
export type ExportWhat = 'plan' | 'org_chart' | 'compliance';

export const PHASES: Phase[] = ['development', 'execution', 'operation'];

export interface CatalogueSummary {
  kind: string;
  source: 'shipped' | 'tenant';
  id: string;
  code: string;
  name: StaffingLabel;
  state: string;
  versions: number[];
  latest_version: number | null;
  review_status: string;
  jurisdiction_countries?: string[];
}

/** A catalogue item names itself by a locale key (shipped) or by texts per locale (tenant). */
export interface Labelled {
  code: string;
  name_key: string;
  labels: Record<string, string> | null;
}

export interface CatalogueRole extends Labelled {
  organisation: string;
  phases: Phase[];
  default_fte: string;
  key_role: boolean;
  required_by_gate: string | null;
  required_document_kinds: string[];
  handover_role: boolean;
}

export interface CatalogueDocumentKind extends Labelled {
  credential_type: string;
  special_category: boolean;
  store_number: boolean;
  retention_rule: string;
}

export interface StaffingCatalogue {
  id: string;
  version: number;
  name_key: string;
  labels: Record<string, string> | null;
  review_status: string;
  organisations: Labelled[];
  roles: CatalogueRole[];
  document_kinds: CatalogueDocumentKind[];
  leave_types: Labelled[];
}

export interface StaffingPlan {
  id: string;
  project_id: string;
  catalogue_source: 'shipped' | 'tenant';
  catalogue_id: string;
  catalogue_version: number;
  status: PlanStatus;
  requires_accommodation: boolean;
  commissioning_date: string | null;
  governance_document_id: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  approval_source: string | null;
  has_bound_snapshot: boolean;
}

export interface Fill {
  id: string;
  position_id: string;
  roster_member_id: string | null;
  /** Null when the roster line behind the assignment is gone. */
  name: string | null;
  fte_share: string;
  from_date: string | null;
  to_date: string | null;
  status: FillStatus;
  /** Null when the person has no personnel file yet, so nothing is known. */
  cleared_to_work: boolean | null;
}

export interface Position {
  id: string;
  role_code: string;
  custom_label: string | null;
  organisation: string;
  phase: Phase;
  title: string | null;
  fte: string;
  headcount: number;
  entry_date: string | null;
  exit_date: string | null;
  required_by_gate: string | null;
  key_role: boolean;
  handover_role: boolean;
  /** Derived by the server: `filled` follows the people assigned. */
  status: PositionStatus;
  stored_status: SettablePositionStatus;
  recruiting_channel: RecruitingChannel | null;
  owner_user_id: string | null;
  notes: string | null;
  covered_fte: string;
  fills: Fill[];
}

export interface PositionInput {
  role_code?: string;
  phase?: Phase;
  custom_label?: string | null;
  organisation?: string | null;
  title?: string | null;
  fte?: string | null;
  headcount?: number | null;
  entry_date?: string | null;
  exit_date?: string | null;
  required_by_gate?: string | null;
  key_role?: boolean | null;
  handover_role?: boolean | null;
  recruiting_channel?: RecruitingChannel | null;
  owner_user_id?: string | null;
  notes?: string | null;
}

export interface Handover {
  id: string;
  from_fill_id: string;
  to_position_id: string;
  overlap_days: number;
  scope: string;
  status: HandoverStatus;
}

/** One rule finding: a stable code, the element it is about, a severity. */
export interface Finding {
  code: string;
  ref: string;
  severity: string;
  detail: string;
}

export interface OrgChart {
  phases: Array<{
    phase: Phase;
    organisations: Array<{
      organisation: string;
      positions: Array<{
        position_id: string;
        role_code: string;
        custom_label: string | null;
        title: string | null;
        key_role: boolean;
        vacant: boolean;
        people: Array<{ name: string | null; fte_share: string; status: FillStatus }>;
      }>;
    }>;
  }>;
}

export interface ComplianceRow {
  roster_member_id: string;
  name: string | null;
  roles: string[];
  file_id: string | null;
  cleared_to_work: boolean | null;
  cells: Record<string, { state: CellState; days?: number | null }>;
}

export interface Compliance {
  document_kinds: string[];
  items: ComplianceRow[];
  total: number;
}

export interface PlannedVsActualRow {
  position_id: string;
  role_code: string;
  planned_fte_days: string;
  actual_hours: string;
  actual_fte_days: string;
  variance_fte_days: string;
  linked_resources: number;
}

export interface PersonnelFileRow {
  id: string;
  roster_member_id: string | null;
  name: string | null;
  roles: string[];
  start: string | null;
  end: string | null;
  cleared_to_work: boolean | null;
  status: FileStatus;
  /** Decided by the server: whether this caller may open the file. */
  can_open: boolean;
}

export interface FileDocument {
  id: string | null;
  document_kind: string;
  required: boolean;
  credential_id: string | null;
  status: string | null;
  issued_at: string | null;
  valid_until: string | null;
  number_last4: string | null;
  verified_by: string | null;
  verified_at: string | null;
  waived: boolean;
  waiver_rationale: string;
  fit_for_role: FitForRole | null;
  special_category: boolean;
}

export interface TravelRecord {
  id: string;
  kind: TravelKind;
  from_place: string;
  to_place: string;
  depart_date: string | null;
  return_date: string | null;
  booking_ref: string;
  cost: string | null;
  currency: string;
  status: TravelStatus;
}

export interface TravelInput {
  kind: TravelKind;
  from_place?: string;
  to_place?: string;
  depart_date: string;
  return_date?: string | null;
  booking_ref?: string;
  cost?: string | null;
  currency?: string;
}

export interface LeaveRecord {
  id: string;
  leave_type: string;
  from_date: string | null;
  to_date: string | null;
  status: LeaveStatus;
  approved_by: string | null;
  approved_at: string | null;
}

/** An accommodation booking as the accommodation module reports it; only the fields the file shows are named. */
export interface AccommodationBooking {
  id?: string;
  accommodation?: string | null;
  room?: string | null;
  check_in?: string | null;
  check_out?: string | null;
  status?: string;
}

export interface PersonnelFile {
  id: string;
  roster_member_id: string | null;
  name: string | null;
  employer_organisation: string;
  employment_basis: EmploymentBasis;
  nationality_required: boolean;
  lawful_basis: LawfulBasis;
  status: FileStatus;
  ended_on: string | null;
  retention_due_at: string | null;
  hold_rationale: string | null;
  anonymised_at: string | null;
  roles: string[];
  start: string | null;
  end: string | null;
  cleared_to_work: boolean | null;
  missing: string[];
  expired: string[];
  documents: FileDocument[];
  accommodation: AccommodationBooking[];
  travel: TravelRecord[];
  leave: LeaveRecord[];
  warnings: Finding[];
  /** Decided by the server: whether this caller may change the file. */
  can_edit: boolean;
}

export interface FileHeaderInput {
  employer_organisation?: string;
  employment_basis?: EmploymentBasis;
  nationality_required?: boolean;
  lawful_basis?: LawfulBasis;
}

export interface AccessLogEntry {
  actor_id: string | null;
  action: string;
  at: string | null;
}

export interface Upcoming {
  expiring: Array<{
    file_id: string;
    name: string | null;
    document_kind: string;
    valid_until: string | null;
    days: number;
    status: string | null;
    bucket: number;
  }>;
  mobilisations: Array<TravelRecord & { file_id: string; name: string | null }>;
  leave: Array<LeaveRecord & { file_id: string; name: string | null }>;
}

/* ── Errors ───────────────────────────────────────────────────────────── */

interface ErrorDetail {
  code?: unknown;
  message?: unknown;
  violations?: unknown;
  info?: unknown;
}

function detailOf(err: unknown): ErrorDetail | null {
  if (!(err instanceof ApiError)) return null;
  const body = err.body as { detail?: unknown } | null;
  const detail = body && typeof body === 'object' ? body.detail : null;
  return detail && typeof detail === 'object' && !Array.isArray(detail) ? (detail as ErrorDetail) : null;
}

/** The stable error code of a refusal, or null when the failure was not a staffing refusal. */
export function staffingErrorCode(err: unknown): string | null {
  const code = detailOf(err)?.code;
  return typeof code === 'string' ? code : null;
}

/** The sentence the server wrote for the refusal, already in the reader's language. */
export function staffingErrorMessage(err: unknown): string | null {
  const message = detailOf(err)?.message;
  return typeof message === 'string' && message.trim() ? message : null;
}

/** Extra detail of a refusal, for example the date a retention duty runs until. */
export function staffingErrorInfo(err: unknown): string | null {
  const info = detailOf(err)?.info;
  return typeof info === 'string' && info.trim() ? info : null;
}

/** Every finding a refused submission listed, so the screen can show all of them at once. */
export function staffingViolations(err: unknown): Finding[] {
  const list = detailOf(err)?.violations;
  return Array.isArray(list) ? (list as Finding[]) : [];
}

export const staffingKeys = {
  catalogues: ['staffing', 'catalogues'] as const,
  /** Everything a plan or position write can change. Personnel file details live outside it on purpose. */
  project: (projectId: string) => ['staffing', projectId] as const,
  plan: (projectId: string) => ['staffing', projectId, 'plan'] as const,
  catalogue: (projectId: string) => ['staffing', projectId, 'catalogue'] as const,
  findings: (projectId: string) => ['staffing', projectId, 'findings'] as const,
  positions: (projectId: string) => ['staffing', projectId, 'positions'] as const,
  handovers: (projectId: string) => ['staffing', projectId, 'handovers'] as const,
  orgChart: (projectId: string) => ['staffing', projectId, 'org-chart'] as const,
  compliance: (projectId: string) => ['staffing', projectId, 'compliance'] as const,
  plannedVsActual: (projectId: string) => ['staffing', projectId, 'planned-vs-actual'] as const,
  upcoming: (projectId: string) => ['staffing', projectId, 'upcoming'] as const,
  files: (projectId: string) => ['staffing', projectId, 'files'] as const,
  /** Reading a file writes an audit row, so its key is not under `project` and is never swept by a plan write. */
  file: (projectId: string, fileId: string) => ['staffing-file', projectId, fileId] as const,
  accessLog: (projectId: string, fileId: string) => ['staffing-file', projectId, fileId, 'access-log'] as const,
};

const p = (projectId: string) => `${BASE}/projects/${projectId}`;
const f = (projectId: string, fileId: string) => `${p(projectId)}/personnel-files/${fileId}`;

/* ── Catalogues and plan ──────────────────────────────────────────────── */

export function listCatalogues(): Promise<Page<CatalogueSummary>> {
  return apiGet<Page<CatalogueSummary>>(`${BASE}/catalogues`);
}

export function getPinnedCatalogue(projectId: string): Promise<StaffingCatalogue> {
  return apiGet<StaffingCatalogue>(`${p(projectId)}/catalogue`);
}

export function getPlan(projectId: string): Promise<StaffingPlan> {
  return apiGet<StaffingPlan>(`${p(projectId)}/plan`);
}

export function createPlan(
  projectId: string,
  body: {
    catalogue_source: 'shipped' | 'tenant';
    catalogue_id: string;
    requires_accommodation: boolean;
    commissioning_date: string | null;
  },
): Promise<StaffingPlan> {
  return apiPut<StaffingPlan>(`${p(projectId)}/plan`, body);
}

export function patchPlan(
  projectId: string,
  body: { requires_accommodation?: boolean; commissioning_date?: string | null },
): Promise<StaffingPlan> {
  return apiPatch<StaffingPlan>(`${p(projectId)}/plan`, body);
}

export function changeCatalogue(
  projectId: string,
  body: { catalogue_source: 'shipped' | 'tenant'; catalogue_id: string; role_mapping: Record<string, string> },
): Promise<StaffingPlan> {
  return apiPost<StaffingPlan>(`${p(projectId)}/plan/catalogue`, body);
}

export function submitPlan(projectId: string): Promise<StaffingPlan> {
  return apiPost<StaffingPlan>(`${p(projectId)}/plan/submit`, {});
}

export function returnPlan(projectId: string): Promise<StaffingPlan> {
  return apiPost<StaffingPlan>(`${p(projectId)}/plan/return`, {});
}

export function listPlanFindings(projectId: string): Promise<Page<Finding>> {
  return apiGet<Page<Finding>>(`${p(projectId)}/plan/findings`);
}

/* ── Positions, fills, handovers ──────────────────────────────────────── */

export function listPositions(projectId: string): Promise<Page<Position>> {
  return apiGet<Page<Position>>(`${p(projectId)}/positions`);
}

export function createPosition(projectId: string, body: PositionInput): Promise<Position> {
  return apiPost<Position>(`${p(projectId)}/positions`, body);
}

export function createPositionsFromCatalogue(
  projectId: string,
  body: { phase: Phase; role_codes?: string[]; entry_date?: string | null },
): Promise<Page<Position>> {
  return apiPost<Page<Position>>(`${p(projectId)}/positions/from-catalogue`, body);
}

export function updatePosition(projectId: string, positionId: string, body: PositionInput): Promise<Position> {
  return apiPatch<Position>(`${p(projectId)}/positions/${positionId}`, body);
}

export function setPositionStatus(
  projectId: string,
  positionId: string,
  status: SettablePositionStatus,
): Promise<Position> {
  return apiPost<Position>(`${p(projectId)}/positions/${positionId}/status`, { status });
}

export function deletePosition(projectId: string, positionId: string): Promise<void> {
  return apiDelete(`${p(projectId)}/positions/${positionId}`);
}

export function createFill(
  projectId: string,
  positionId: string,
  body: { roster_member_id: string; fte_share: string; from_date: string; to_date?: string | null },
): Promise<Fill> {
  return apiPost<Fill>(`${p(projectId)}/positions/${positionId}/fills`, body);
}

export function confirmFill(projectId: string, fillId: string): Promise<{ fill: Fill; warnings: Finding[] }> {
  return apiPost<{ fill: Fill; warnings: Finding[] }>(`${p(projectId)}/fills/${fillId}/confirm`, {});
}

export function endFill(projectId: string, fillId: string, toDate: string | null): Promise<Fill> {
  return apiPost<Fill>(`${p(projectId)}/fills/${fillId}/end`, toDate ? { to_date: toDate } : {});
}

export function deleteFill(projectId: string, fillId: string): Promise<void> {
  return apiDelete(`${p(projectId)}/fills/${fillId}`);
}

export function listHandovers(projectId: string): Promise<Page<Handover>> {
  return apiGet<Page<Handover>>(`${p(projectId)}/handovers`);
}

export function createHandover(
  projectId: string,
  body: { from_fill_id: string; to_position_id: string; overlap_days: number; scope: string },
): Promise<Handover> {
  return apiPost<Handover>(`${p(projectId)}/handovers`, body);
}

export function updateHandover(
  projectId: string,
  handoverId: string,
  body: { overlap_days?: number; scope?: string; status?: HandoverStatus },
): Promise<Handover> {
  return apiPatch<Handover>(`${p(projectId)}/handovers/${handoverId}`, body);
}

export function deleteHandover(projectId: string, handoverId: string): Promise<void> {
  return apiDelete(`${p(projectId)}/handovers/${handoverId}`);
}

/* ── Views ────────────────────────────────────────────────────────────── */

export function getOrgChart(projectId: string): Promise<OrgChart> {
  return apiGet<OrgChart>(`${p(projectId)}/org-chart`);
}

export function getCompliance(projectId: string): Promise<Compliance> {
  return apiGet<Compliance>(`${p(projectId)}/compliance`);
}

export function getPlannedVsActual(projectId: string): Promise<Page<PlannedVsActualRow>> {
  return apiGet<Page<PlannedVsActualRow>>(`${p(projectId)}/planned-vs-actual`);
}

export function getUpcoming(projectId: string): Promise<Upcoming> {
  return apiGet<Upcoming>(`${p(projectId)}/upcoming`);
}

/** Download the plan, the organisation chart or the compliance matrix. The server names the file. */
export function downloadExport(projectId: string, what: ExportWhat, format: ExportFormat): Promise<void> {
  return downloadWithAuth(`/api${p(projectId)}/export?what=${what}&format=${format}`, `staffing_${what}.${format}`);
}

/* ── Personnel files ──────────────────────────────────────────────────── */

export function listFiles(projectId: string): Promise<Page<PersonnelFileRow>> {
  return apiGet<Page<PersonnelFileRow>>(`${p(projectId)}/personnel-files`);
}

export function createFile(
  projectId: string,
  body: { roster_member_id: string } & FileHeaderInput,
): Promise<{ id: string }> {
  return apiPost<{ id: string }>(`${p(projectId)}/personnel-files`, body);
}

/** Opens the file. The server records every call in the file's access log. */
export function getFile(projectId: string, fileId: string): Promise<PersonnelFile> {
  return apiGet<PersonnelFile>(f(projectId, fileId));
}

export function updateFile(projectId: string, fileId: string, body: FileHeaderInput): Promise<unknown> {
  return apiPatch(f(projectId, fileId), body);
}

export function endFile(projectId: string, fileId: string, endedOn: string | null): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/end`, endedOn ? { ended_on: endedOn } : {});
}

export function holdFile(projectId: string, fileId: string, rationale: string): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/hold`, { rationale });
}

export function releaseFile(projectId: string, fileId: string): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/release`, {});
}

export function eraseFile(projectId: string, fileId: string, rationale: string): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/erase`, { rationale });
}

export function getAccessLog(projectId: string, fileId: string): Promise<Page<AccessLogEntry>> {
  return apiGet<Page<AccessLogEntry>>(`${f(projectId, fileId)}/access-log`);
}

/** The person's own file. The server refuses anybody else with `own_file_only`. */
export function downloadOwnFile(projectId: string, fileId: string, format: ExportFormat): Promise<void> {
  return downloadWithAuth(`/api${f(projectId, fileId)}/export?format=${format}`, `personnel_file.${format}`);
}

export function linkDocument(
  projectId: string,
  fileId: string,
  body: {
    document_kind: string;
    credential_id?: string | null;
    number_last4?: string | null;
    fit_for_role?: FitForRole | null;
  },
): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/documents`, body);
}

export function verifyDocument(projectId: string, fileId: string, documentId: string): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/documents/${documentId}/verify`, {});
}

export function waiveDocument(
  projectId: string,
  fileId: string,
  documentKind: string,
  rationale: string,
): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/documents/${documentKind}/waive`, { rationale });
}

export function createTravel(projectId: string, fileId: string, body: TravelInput): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/travel`, body);
}

export function updateTravel(
  projectId: string,
  fileId: string,
  travelId: string,
  body: Partial<TravelInput>,
): Promise<unknown> {
  return apiPatch(`${f(projectId, fileId)}/travel/${travelId}`, body);
}

export function setTravelStatus(
  projectId: string,
  fileId: string,
  travelId: string,
  status: TravelStatus,
): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/travel/${travelId}/status`, { status });
}

export function deleteTravel(projectId: string, fileId: string, travelId: string): Promise<void> {
  return apiDelete(`${f(projectId, fileId)}/travel/${travelId}`);
}

export function createLeave(
  projectId: string,
  fileId: string,
  body: { leave_type: string; from_date: string; to_date: string },
): Promise<{ warnings?: Finding[] }> {
  return apiPost<{ warnings?: Finding[] }>(`${f(projectId, fileId)}/leave`, body);
}

export function updateLeave(
  projectId: string,
  fileId: string,
  leaveId: string,
  body: { leave_type?: string; from_date?: string; to_date?: string },
): Promise<unknown> {
  return apiPatch(`${f(projectId, fileId)}/leave/${leaveId}`, body);
}

export function setLeaveStatus(
  projectId: string,
  fileId: string,
  leaveId: string,
  status: Exclude<LeaveStatus, 'requested'>,
): Promise<unknown> {
  return apiPost(`${f(projectId, fileId)}/leave/${leaveId}/status`, { status });
}

export function deleteLeave(projectId: string, fileId: string, leaveId: string): Promise<void> {
  return apiDelete(`${f(projectId, fileId)}/leave/${leaveId}`);
}
