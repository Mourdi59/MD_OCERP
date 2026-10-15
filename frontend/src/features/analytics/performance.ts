// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Cross-project performance benchmark: API, types and the pure helpers the
// Performance tab renders with. Backed by
// POST /api/v1/bi-dashboards/performance/benchmark, see
// backend/app/modules/bi_dashboards/performance.py for the semantics. The two
// that matter on screen: a value can be null (unavailable, with a reason) and
// must never be drawn as 0, and each unit or currency is its own group.

import { apiGet, apiPost } from '@/shared/lib/api';

/* ── Types ─────────────────────────────────────────────────────────────── */

export type Decimalish = string | number | null;

export interface PerformancePreset {
  key: string;
  spec: Record<string, unknown>;
}

export interface PerformanceProjectRow {
  project_id: string;
  value: Decimalish;
  numerator: Decimalish;
  denominator: Decimalish;
  records: number;
  unavailable_reason: string | null;
}

export interface PerformanceBenchmarkFigures {
  weighted: Decimalish;
  weighted_unavailable_reason: string | null;
  median: Decimalish;
  p25: Decimalish;
  p75: Decimalish;
  min: Decimalish;
  max: Decimalish;
}

export interface PerformanceGroup {
  key: string;
  dimensions: Record<string, string | null>;
  rows: PerformanceProjectRow[];
  benchmark: PerformanceBenchmarkFigures;
  evidence: { projects_with_data: number; projects_with_value: number; records: number };
  coverage: Decimalish;
}

export interface PerformanceProjectLabel {
  project_id: string;
  name: string;
  currency: string;
}

export interface PerformanceBenchmarkResponse {
  kpi: string | null;
  spec: Record<string, unknown>;
  aggregation: string;
  projects_selected: number;
  projects: PerformanceProjectLabel[];
  groups: PerformanceGroup[];
}

export interface PerformanceBenchmarkRequest {
  kpi: string;
  project_ids: string[];
}

export function fetchPerformancePresets(): Promise<PerformancePreset[]> {
  return apiGet<PerformancePreset[]>('/v1/bi-dashboards/performance/presets');
}

export function fetchPerformanceBenchmark(
  body: PerformanceBenchmarkRequest,
): Promise<PerformanceBenchmarkResponse> {
  return apiPost<PerformanceBenchmarkResponse, PerformanceBenchmarkRequest>('/v1/bi-dashboards/performance/benchmark', body);
}

/* ── Pure helpers ─────────────────────────────────────────────────────── */

/** The server's key for "this group had no value", see kpi_spec.NULL_GROUP_KEY. */
export const NULL_GROUP_KEY = '__null__';

/** A Decimal string as a number, or null when there is no value. Never 0 for absent. */
export function toNumber(value: Decimalish | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export type RangeBand = 'below' | 'within' | 'above';

/** Where one project's value sits against the cohort's P25-P75 range. */
export function rangeBand(
  value: Decimalish | undefined,
  p25: Decimalish | undefined,
  p75: Decimalish | undefined,
): RangeBand | null {
  const v = toNumber(value);
  const lo = toNumber(p25);
  const hi = toNumber(p75);
  if (v === null || lo === null || hi === null) return null;
  if (v < lo) return 'below';
  if (v > hi) return 'above';
  return 'within';
}

/** One table row per selected project; a project with no reading is a row too. */
export interface PerformanceTableRow {
  projectId: string;
  name: string;
  row: PerformanceProjectRow | null;
}

export function tableRows(
  group: PerformanceGroup,
  projects: PerformanceProjectLabel[],
): PerformanceTableRow[] {
  const byId = new Map(group.rows.map((r) => [r.project_id, r]));
  return projects.map((p) => ({ projectId: p.project_id, name: p.name, row: byId.get(p.project_id) ?? null }));
}

type CsvCell = string | number | null | undefined;

/** RFC 4180 quoting, plus a leading quote on a cell a spreadsheet would run as a formula. */
export function csvCell(value: CsvCell): string {
  let s = value == null ? '' : String(value);
  if (/^[=+\-@\t\r]/.test(s) && !/^-?\d/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export interface PerformanceCsvLabels {
  group: string;
  project: string;
  value: string;
  numerator: string;
  denominator: string;
  records: string;
  status: string;
  weighted: string;
  median: string;
  p25: string;
  p75: string;
  /** Text for a reading with no value, given its reason code. */
  unavailable: (reason: string | null) => string;
  /** Text for a group key. */
  groupLabel: (group: PerformanceGroup) => string;
}

/**
 * The benchmark as CSV: one line per group and selected project, with the
 * cohort figures repeated on every line so a filtered spreadsheet keeps them.
 * Values are written as the server sent them, with a dot decimal, so a
 * spreadsheet reads them as numbers in any locale it is opened in.
 */
export function buildPerformanceCsv(
  data: PerformanceBenchmarkResponse,
  labels: PerformanceCsvLabels,
): string {
  const header = [
    labels.group,
    labels.project,
    labels.value,
    labels.numerator,
    labels.denominator,
    labels.records,
    labels.status,
    labels.weighted,
    labels.median,
    labels.p25,
    labels.p75,
  ];
  const lines = [header.map(csvCell).join(',')];
  for (const group of data.groups) {
    for (const { name, row } of tableRows(group, data.projects)) {
      const value = toNumber(row?.value);
      lines.push(
        [
          labels.groupLabel(group),
          name,
          value === null ? '' : String(row?.value),
          row?.numerator ?? '',
          row?.denominator ?? '',
          row?.records ?? 0,
          value === null ? labels.unavailable(row?.unavailable_reason ?? 'no_data') : '',
          group.benchmark.weighted ?? '',
          group.benchmark.median ?? '',
          group.benchmark.p25 ?? '',
          group.benchmark.p75 ?? '',
        ]
          .map(csvCell)
          .join(','),
      );
    }
  }
  return lines.join('\r\n');
}

/** Save CSV text as a file: the Blob + object-URL download the analytics page uses. */
export function downloadCsv(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
