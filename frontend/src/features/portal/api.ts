/**
 * API helpers for the Customer & Partner Portal module.
 *
 * Backed by /api/v1/portal/ — see backend/app/modules/portal/router.py
 *
 * Exposes the internal-admin surface (RequirePermission-gated):
 *   - users (invite / list / get / patch / resend)
 *   - access-rules (grant / revoke)
 *   - document-access-log (audit log, read-only)
 *
 * The portal-user-facing /auth/* + /me/* endpoints are NOT wrapped here;
 * those live on a different session token system and have their own UI.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type PortalRole =
  | 'client'
  | 'investor'
  | 'consultant'
  | 'subcontractor'
  | 'supplier'
  | 'building_user';

export type PortalUserStatus = 'invited' | 'active' | 'suspended' | 'expired';

export type AccessPermission = 'view' | 'comment' | 'submit' | 'sign';

export type AccessAction = 'view' | 'download' | 'sign';

export interface PortalUser {
  id: string;
  email: string;
  full_name: string;
  portal_role: PortalRole | string;
  language: string;
  timezone: string;
  status: PortalUserStatus | string;
  invited_at: string | null;
  last_login_at: string | null;
  failed_login_count: number;
  locked_until: string | null;
  created_at: string;
  updated_at: string;
}

export interface PortalUserList {
  items: PortalUser[];
  total: number;
}

export interface InvitePayload {
  email: string;
  full_name?: string;
  portal_role: PortalRole;
  language?: string;
  timezone?: string;
  redirect_path?: string | null;
}

export interface InviteResponse {
  user: PortalUser;
  magic_link_token: string;
  magic_link_expires_at: string;
}

export interface UserPatch {
  status?: PortalUserStatus;
  full_name?: string;
  language?: string;
  timezone?: string;
}

export interface AccessRule {
  id: string;
  portal_user_id: string;
  resource_type: string;
  resource_id: string;
  permission: AccessPermission | string;
  granted_at: string | null;
  granted_by: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccessRuleCreate {
  portal_user_id: string;
  resource_type: string;
  resource_id: string;
  permission?: AccessPermission;
  expires_at?: string | null;
}

export interface AccessRuleList {
  items: AccessRule[];
  total: number;
}

export interface DocumentAccessLogEntry {
  id: string;
  portal_user_id: string;
  document_type: string;
  document_id: string;
  action: AccessAction | string;
  occurred_at: string | null;
  ip_address: string | null;
  created_at: string;
}

/* ── Users ─────────────────────────────────────────────────────────────── */

export function listPortalUsers(params?: {
  offset?: number;
  limit?: number;
  portal_role?: string;
  status?: string;
}): Promise<PortalUserList> {
  const qs = new URLSearchParams();
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  if (params?.portal_role) qs.set('portal_role', params.portal_role);
  if (params?.status) qs.set('status', params.status);
  const q = qs.toString();
  return apiGet<PortalUserList>(`/v1/portal/admin/users${q ? `?${q}` : ''}`);
}

export function getPortalUser(id: string): Promise<PortalUser> {
  return apiGet<PortalUser>(`/v1/portal/admin/users/${id}`);
}

export function invitePortalUser(data: InvitePayload): Promise<InviteResponse> {
  return apiPost<InviteResponse>('/v1/portal/admin/users/invite', data);
}

export function patchPortalUser(id: string, data: UserPatch): Promise<PortalUser> {
  return apiPatch<PortalUser>(`/v1/portal/admin/users/${id}`, data);
}

export function suspendPortalUser(id: string): Promise<PortalUser> {
  return patchPortalUser(id, { status: 'suspended' });
}

export function reactivatePortalUser(id: string): Promise<PortalUser> {
  return patchPortalUser(id, { status: 'active' });
}

export function resendInvite(id: string): Promise<InviteResponse> {
  return apiPost<InviteResponse>(`/v1/portal/admin/users/${id}/resend-invite`, {});
}

/* ── Access rules ──────────────────────────────────────────────────────── */

export function listAccessRules(params?: {
  portal_user_id?: string;
  resource_type?: string;
  offset?: number;
  limit?: number;
}): Promise<AccessRuleList> {
  const qs = new URLSearchParams();
  if (params?.portal_user_id) qs.set('portal_user_id', params.portal_user_id);
  if (params?.resource_type) qs.set('resource_type', params.resource_type);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<AccessRuleList>(
    `/v1/portal/admin/access-rules${q ? `?${q}` : ''}`,
  );
}

export function grantAccess(data: AccessRuleCreate): Promise<AccessRule> {
  return apiPost<AccessRule>('/v1/portal/admin/access-rules', data);
}

export function revokeAccess(ruleId: string): Promise<void> {
  return apiDelete(`/v1/portal/admin/access-rules/${ruleId}`);
}

/* ── Audit log ─────────────────────────────────────────────────────────── */

export function listDocumentAccessLog(params?: {
  portal_user_id?: string;
  document_type?: string;
  offset?: number;
  limit?: number;
}): Promise<DocumentAccessLogEntry[]> {
  const qs = new URLSearchParams();
  if (params?.portal_user_id) qs.set('portal_user_id', params.portal_user_id);
  if (params?.document_type) qs.set('document_type', params.document_type);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return apiGet<DocumentAccessLogEntry[]>(
    `/v1/portal/admin/document-access-log${q ? `?${q}` : ''}`,
  );
}

/* ── Progress reports (client distribution) ──────────────────────────────
 *
 * The portal-user-facing list (RLS via PortalAccessRule) lives at
 * /v1/portal/projects/{project_id}/progress-reports on a separate session
 * token. The internal admin screen below uses the reporting module's
 * JWT-gated endpoints to preview exactly what a client receives, filtered
 * to the progress_report type.
 */

export interface ProgressReport {
  id: string;
  project_id: string;
  template_id: string | null;
  report_type: string;
  title: string;
  generated_at: string;
  format: string;
  storage_key: string | null;
}

export function listProgressReports(projectId: string): Promise<ProgressReport[]> {
  return apiGet<ProgressReport[]>(
    `/v1/reporting/reports/?project_id=${encodeURIComponent(projectId)}`,
  ).then((reports) => reports.filter((r) => r.report_type === 'progress_report'));
}

/* ── Portal-user-facing (session-token) payment applications ───────────────
 *
 * Unlike the internal-admin helpers above (which ride the internal JWT via
 * shared/lib/api), the subcontractor-portal payment endpoints authenticate
 * with the magic-link SESSION token, kept in sessionStorage under
 * PORTAL_SESSION_KEY. We use raw fetch so the internal JWT is never sent on
 * these public-surface calls. Mirrors features/buyer-portal/api.ts.
 */

export const PORTAL_SESSION_KEY = 'oe.portal.session_token';

export function getPortalSessionToken(): string | null {
  try {
    return sessionStorage.getItem(PORTAL_SESSION_KEY);
  } catch {
    return null;
  }
}

export function setPortalSessionToken(token: string): void {
  try {
    sessionStorage.setItem(PORTAL_SESSION_KEY, token);
  } catch {
    /* sessionStorage unavailable (private mode) — caller still gets the token */
  }
}

export function clearPortalSessionToken(): void {
  try {
    sessionStorage.removeItem(PORTAL_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

const PORTAL_ME_BASE = '/api/v1/portal/me';

export interface PaymentApplicationListItem {
  id: string;
  agreement_id: string;
  application_number: string;
  period_start: string | null;
  period_end: string | null;
  gross_amount: string;
  net_amount: string;
  currency: string;
  status: string;
  submitted_at: string | null;
}

export interface PaymentApplicationListResponse {
  items: PaymentApplicationListItem[];
  total: number;
}

export interface PaymentApplicationLineDetail {
  work_package_id: string;
  work_package_name: string;
  planned_value: string;
  claimed_amount: string;
  certified_amount: string;
  approved_amount: string;
}

export interface PaymentApplicationDetail {
  id: string;
  agreement_id: string;
  application_number: string;
  period_start: string | null;
  period_end: string | null;
  gross_amount: string;
  retention_amount: string;
  net_amount: string;
  currency: string;
  status: string;
  submitted_at: string | null;
  lines: PaymentApplicationLineDetail[];
}

export interface PaymentApplicationSubmitLine {
  work_package_id: string;
  claimed_amount: string;
}

export interface PaymentApplicationSubmitPayload {
  agreement_id: string;
  period_start?: string | null;
  period_end?: string | null;
  lines: PaymentApplicationSubmitLine[];
}

/** Raised when no portal session token is present — the UI must re-auth. */
export class PortalUnauthorizedError extends Error {
  constructor(message = 'Portal session expired') {
    super(message);
    this.name = 'PortalUnauthorizedError';
  }
}

async function portalFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getPortalSessionToken();
  if (!token) throw new PortalUnauthorizedError('No portal session');
  const headers = new Headers(init?.headers);
  headers.set('Authorization', `Bearer ${token}`);
  headers.set('Accept', 'application/json');
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401) {
    clearPortalSessionToken();
    throw new PortalUnauthorizedError();
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`;
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function listMyPaymentApplications(params?: {
  agreement_id?: string;
  status?: string;
  offset?: number;
  limit?: number;
}): Promise<PaymentApplicationListResponse> {
  const qs = new URLSearchParams();
  if (params?.agreement_id) qs.set('agreement_id', params.agreement_id);
  if (params?.status) qs.set('status', params.status);
  if (params?.offset !== undefined) qs.set('offset', String(params.offset));
  if (params?.limit !== undefined) qs.set('limit', String(params.limit));
  const q = qs.toString();
  return portalFetch<PaymentApplicationListResponse>(
    `${PORTAL_ME_BASE}/payment-applications${q ? `?${q}` : ''}`,
  );
}

export function getMyPaymentApplication(id: string): Promise<PaymentApplicationDetail> {
  return portalFetch<PaymentApplicationDetail>(
    `${PORTAL_ME_BASE}/payment-applications/${encodeURIComponent(id)}`,
  );
}

export function submitMyPaymentApplication(
  data: PaymentApplicationSubmitPayload,
): Promise<PaymentApplicationDetail> {
  return portalFetch<PaymentApplicationDetail>(`${PORTAL_ME_BASE}/payment-applications`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export interface PortalWorkPackage {
  id: string;
  name: string;
  planned_value: string;
}

export interface PortalAgreementSummary {
  id: string;
  title: string;
  currency: string;
  retention_percent: string;
  status: string;
  work_packages: PortalWorkPackage[];
}

export interface PortalAgreementSummaryList {
  items: PortalAgreementSummary[];
  total: number;
}

/** List the agreements (with work packages) the user can submit against. */
export function listMyPaymentAgreements(): Promise<PortalAgreementSummaryList> {
  return portalFetch<PortalAgreementSummaryList>(`${PORTAL_ME_BASE}/payment-agreements`);
}

/* ── Portal-user-facing (session-token) progress reports ───────────────────
 *
 * The client / subcontractor sees the progress reports for any project they
 * hold a `project` access rule on. Project resolution and the report list are
 * both RLS-scoped server-side; a project the caller was not granted 404s.
 */

export interface PortalProjectSummary {
  id: string;
  name: string;
  project_code: string | null;
}

export interface PortalProjectSummaryList {
  items: PortalProjectSummary[];
  total: number;
}

export interface PortalProgressReport {
  id: string;
  title: string;
  generated_at: string;
  report_type: string;
  format: string;
  period: string | null;
  has_content: boolean;
}

export interface PortalProgressReportList {
  items: PortalProgressReport[];
  total: number;
}

/**
 * List the projects the portal caller can see, by name. Falls back to the
 * always-present `/me/accessible/project` (UUID-only) endpoint when the named
 * variant is not deployed yet, so the tab still renders on older backends.
 */
export async function listMyProjects(): Promise<PortalProjectSummary[]> {
  try {
    const named = await portalFetch<PortalProjectSummaryList>(`${PORTAL_ME_BASE}/projects`);
    return named.items;
  } catch (err) {
    // 404 = endpoint not deployed; anything else (e.g. 401) must bubble up so
    // the session-expiry path still fires.
    if (err instanceof PortalUnauthorizedError) throw err;
    const ids = await portalFetch<string[]>(`${PORTAL_ME_BASE}/accessible/project`);
    return ids.map((id) => ({ id, name: id, project_code: null }));
  }
}

/** List the progress reports the caller can see for one accessible project. */
export function listMyProgressReports(projectId: string): Promise<PortalProgressReportList> {
  return portalFetch<PortalProgressReportList>(
    `/api/v1/portal/projects/${encodeURIComponent(projectId)}/progress-reports`,
  );
}

/**
 * Fetch the rendered HTML body of one progress report with the session token.
 * Returns the HTML string, or null when the body is not available (410).
 */
export async function fetchMyProgressReportHtml(
  projectId: string,
  reportId: string,
): Promise<string | null> {
  const token = getPortalSessionToken();
  if (!token) throw new PortalUnauthorizedError('No portal session');
  const res = await fetch(
    `/api/v1/portal/projects/${encodeURIComponent(projectId)}/progress-reports/${encodeURIComponent(
      reportId,
    )}/content`,
    { headers: { Authorization: `Bearer ${token}`, Accept: 'text/html' } },
  );
  if (res.status === 401) {
    clearPortalSessionToken();
    throw new PortalUnauthorizedError();
  }
  if (res.status === 410) return null;
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === 'string' ? body.detail : `Could not open report (${res.status})`;
    throw new Error(detail);
  }
  return res.text();
}

/** Consume a magic-link token, persist the session, and return it. */
export async function consumePortalMagicLink(
  token: string,
): Promise<{ session_token: string; expires_at: string }> {
  const res = await fetch('/api/v1/portal/auth/consume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === 'string' ? body.detail : `Sign-in failed (${res.status})`;
    throw new Error(detail);
  }
  const data = (await res.json()) as { session_token: string; expires_at: string };
  setPortalSessionToken(data.session_token);
  return data;
}
