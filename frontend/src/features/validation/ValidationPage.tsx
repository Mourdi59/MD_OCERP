import { useState, useMemo, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ShieldCheck,
  Play,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Info,
  ChevronDown,
  ChevronRight,
  Download,
  Wand2,
  Filter,
  ExternalLink,
} from 'lucide-react';
import { Button, Card, Badge, EmptyState, Skeleton, Breadcrumb } from '@/shared/ui';
import { SectionIntro } from './SectionIntro';
import { apiGet, apiPost, triggerDownload } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { useToastStore } from '@/stores/useToastStore';
import { useAuthStore } from '@/stores/useAuthStore';

/* ── Types ─────────────────────────────────────────────────────────────── */

interface Project {
  id: string;
  name: string;
  description: string;
  classification_standard: string;
}

interface BOQ {
  id: string;
  project_id: string;
  name: string;
  description: string;
  status: string;
}

interface ValidationResultItem {
  rule_id: string;
  rule_name: string;
  severity: 'error' | 'warning' | 'info';
  passed: boolean;
  message: string;
  element_ref: string | null;
  suggestion: string | null;
}

interface ValidationReportData {
  id: string;
  status: 'passed' | 'warnings' | 'errors' | 'skipped';
  score: number;
  counts: {
    total: number;
    passed: number;
    errors: number;
    warnings: number;
    infos: number;
  };
  rule_sets: string[];
  duration_ms: number;
  results: ValidationResultItem[];
}

/* ── Backend wire shapes (validation module) ──────────────────────────── */

/** Single result item as returned by POST /v1/validation/run/. */
interface RunValidationResultItem {
  rule_id: string;
  status: string; // "pass" | "warning" | "error" | "info"
  message: string;
  element_ref: string | null;
  details: Record<string, unknown> | null;
  suggestion: string | null;
}

/** Response body of POST /v1/validation/run/. */
interface RunValidationResponse {
  report_id: string;
  status: string;
  score: number | null;
  total_rules: number;
  passed_count: number;
  warning_count: number;
  error_count: number;
  info_count: number;
  rule_sets: string[];
  duration_ms: number;
  results: RunValidationResultItem[];
}

/**
 * Stored result item embedded in a persisted ValidationReport. Richer than
 * the run-response item — it carries `rule_name`, `severity` and `passed`
 * because the server keeps the full engine output in `results`.
 */
interface StoredResultItem {
  rule_id: string;
  rule_name?: string;
  severity?: string;
  status?: string;
  passed?: boolean;
  message: string;
  element_ref?: string | null;
  details?: Record<string, unknown> | null;
  suggestion?: string | null;
}

/** Response body of GET /v1/validation/reports/{id} and the list endpoint. */
interface ValidationReportResponse {
  id: string;
  project_id: string;
  target_type: string;
  target_id: string;
  rule_set: string;
  status: string;
  score: string | null;
  total_rules: number;
  passed_count: number;
  error_count: number;
  warning_count: number;
  results: StoredResultItem[];
  created_at: string | null;
  metadata: { duration_ms?: number; rule_sets?: string[] } | null;
}

type FilterMode = 'all' | 'errors' | 'warnings' | 'info' | 'passed';

/* ── Rule-set resolution ──────────────────────────────────────────────── */

/**
 * Resolve which rule sets a project validates against, from its
 * classification standard. `boq_quality` is universal and always applied;
 * the classification-specific sets are layered on top. This mirrors the
 * engine's registered rule sets and is the exact list sent to /run/.
 */
function resolveRuleSets(classificationStandard: string | undefined): string[] {
  const sets = ['boq_quality'];
  const std = (classificationStandard ?? '').trim().toLowerCase();
  switch (std) {
    case 'din276':
      sets.push('din276', 'gaeb');
      break;
    case 'nrm':
      sets.push('nrm');
      break;
    case 'masterformat':
      sets.push('masterformat');
      break;
    default:
      break;
  }
  return sets;
}

/** Normalise an engine severity/status string to the UI severity union. */
function toSeverity(value: string | undefined): 'error' | 'warning' | 'info' {
  if (value === 'error') return 'error';
  if (value === 'info') return 'info';
  return 'warning';
}

/** Map a POST /v1/validation/run/ response into the page's report shape. */
function mapRunResponse(data: RunValidationResponse): ValidationReportData {
  return {
    id: data.report_id,
    status: data.status as ValidationReportData['status'],
    score: data.score ?? 0,
    counts: {
      total: data.total_rules,
      passed: data.passed_count,
      errors: data.error_count,
      warnings: data.warning_count,
      infos: data.info_count,
    },
    rule_sets: data.rule_sets,
    duration_ms: data.duration_ms,
    results: data.results.map((r) => {
      const passed = r.status === 'pass';
      return {
        rule_id: r.rule_id,
        rule_name: r.rule_id,
        severity: toSeverity(r.status),
        passed,
        message: r.message,
        element_ref: r.element_ref,
        suggestion: r.suggestion,
      };
    }),
  };
}

/** Map a persisted ValidationReport into the page's report shape. */
function mapStoredReport(report: ValidationReportResponse): ValidationReportData {
  const results: ValidationResultItem[] = report.results.map((r) => {
    const passed = r.passed ?? r.status === 'pass';
    return {
      rule_id: r.rule_id,
      rule_name: r.rule_name ?? r.rule_id,
      severity: toSeverity(r.severity ?? r.status),
      passed,
      message: r.message,
      element_ref: r.element_ref ?? null,
      suggestion: r.suggestion ?? null,
    };
  });
  const infos = results.filter((r) => !r.passed && r.severity === 'info').length;
  return {
    id: report.id,
    status: report.status as ValidationReportData['status'],
    score: report.score !== null && report.score !== '' ? Number(report.score) : 0,
    counts: {
      total: report.total_rules,
      passed: report.passed_count,
      errors: report.error_count,
      warnings: report.warning_count,
      infos,
    },
    rule_sets: report.metadata?.rule_sets ?? (report.rule_set ? report.rule_set.split('+') : []),
    duration_ms: report.metadata?.duration_ms ?? 0,
    results,
  };
}

/* ── Rule descriptions for tooltips ───────────────────────────────────── */

function getRuleDescriptions(t: (key: string, opts?: Record<string, unknown>) => string): Record<string, string> {
  return {
    'boq_quality.position_has_quantity': t('validation.rule_position_has_quantity', { defaultValue: 'Checks that every BOQ position has a quantity greater than zero.' }),
    'boq_quality.position_has_unit_rate': t('validation.rule_position_has_unit_rate', { defaultValue: 'Checks that every position has a unit rate assigned.' }),
    'boq_quality.position_has_description': t('validation.rule_position_has_description', { defaultValue: 'Checks that every position has a meaningful description.' }),
    'boq_quality.no_duplicate_ordinals': t('validation.rule_no_duplicate_ordinals', { defaultValue: 'Ensures all ordinal numbers within the BOQ are unique.' }),
    'boq_quality.unit_rate_in_range': t('validation.rule_unit_rate_in_range', { defaultValue: 'Flags unit rates that deviate more than 5x from median.' }),
    'din276.cost_group_required': t('validation.rule_cost_group_required', { defaultValue: 'Ensures every position has a DIN 276 Kostengruppe assigned.' }),
    'din276.valid_cost_group': t('validation.rule_valid_cost_group', { defaultValue: 'Validates that DIN 276 codes are proper 3-digit codes.' }),
    'gaeb.ordinal_format': t('validation.rule_ordinal_format', { defaultValue: 'Checks ordinal numbers follow GAEB LV format XX.XX.XXXX.' }),
  };
}

/* ── Rule-set descriptions (badge tooltips) ───────────────────────────── */

function getRuleSetDescription(
  ruleSet: string,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  const map: Record<string, string> = {
    boq_quality: t('validation.rs_boq_quality', {
      defaultValue: 'Universal BOQ hygiene: missing quantities/rates, duplicate ordinals, outlier rates.',
    }),
    din276: t('validation.rs_din276', {
      defaultValue: 'DIN 276 (DACH) cost-group structure & Kostengruppe completeness.',
    }),
    gaeb: t('validation.rs_gaeb', {
      defaultValue: 'GAEB tender format: LV structure & ordinal format checks.',
    }),
    nrm: t('validation.rs_nrm', {
      defaultValue: 'NRM 1/2 (UK) element compliance & measurement rules.',
    }),
    masterformat: t('validation.rs_masterformat', {
      defaultValue: 'MasterFormat (US) division structure & code format.',
    }),
    bim_compliance: t('validation.rs_bim', {
      defaultValue: 'CAD/BIM data: required properties, geometry validity, classification mapped.',
    }),
    project_completeness: t('validation.rs_completeness', {
      defaultValue: 'All trades covered, cost benchmarks, missing-scope detection.',
    }),
  };
  return map[ruleSet] ?? t('validation.rs_generic', {
    defaultValue: '{{name}} validation rules',
    name: ruleSet,
  });
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function getScoreLabel(pct: number, t: (key: string, fallback: string) => string): string {
  if (pct >= 95) return t('validation.score_excellent', 'Excellent');
  if (pct >= 80) return t('validation.score_good', 'Good');
  if (pct >= 60) return t('validation.score_needs_review', 'Needs Review');
  return t('validation.score_poor', 'Poor');
}

function getScoreColor(pct: number): string {
  if (pct >= 95) return 'text-semantic-success';
  if (pct >= 80) return 'text-oe-blue';
  if (pct >= 60) return 'text-semantic-warning';
  return 'text-semantic-error';
}

function getScoreRingColor(pct: number): string {
  if (pct >= 95) return 'stroke-semantic-success';
  if (pct >= 80) return 'stroke-oe-blue';
  if (pct >= 60) return 'stroke-semantic-warning';
  return 'stroke-semantic-error';
}

/* ── Sub-components ────────────────────────────────────────────────────── */

function ScoreCircle({ score }: { score: number }) {
  const { t } = useTranslation();
  const pct = Math.round(score * 100);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (pct / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-36 w-36">
        <svg className="h-36 w-36 -rotate-90" viewBox="0 0 120 120" role="img" aria-label={`${t('validation.quality_score', { defaultValue: 'Quality score' })}: ${pct}%`}>
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-surface-secondary"
          />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            className={`${getScoreRingColor(pct)} transition-all duration-700 ease-out`}
            style={{
              strokeDasharray: circumference,
              strokeDashoffset: dashOffset,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold tabular-nums ${getScoreColor(pct)}`}>
            {pct}
          </span>
          <span className={`text-sm font-medium ${getScoreColor(pct)}`}>%</span>
        </div>
      </div>
      <span className={`text-sm font-semibold ${getScoreColor(pct)}`}>
        {getScoreLabel(pct, t)}
      </span>
    </div>
  );
}

function SummaryCard({ report }: { report: ValidationReportData }) {
  const { t } = useTranslation();

  return (
    <Card>
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-content-primary">
          {t('validation.summary', 'Summary')}
        </h3>
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-content-secondary">
              {t('validation.rules_checked', 'Rules checked')}
            </span>
            <span className="font-medium text-content-primary tabular-nums">
              {report.counts.total}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-content-secondary">
              <CheckCircle2 size={14} className="text-semantic-success" />
              {t('validation.passed', 'Passed')}
            </span>
            <span className="font-medium text-semantic-success tabular-nums">
              {report.counts.passed}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-content-secondary">
              <AlertTriangle size={14} className="text-semantic-warning" />
              {t('validation.warnings', 'Warnings')}
            </span>
            <span className="font-medium text-semantic-warning tabular-nums">
              {report.counts.warnings}
            </span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-2 text-content-secondary">
              <XCircle size={14} className="text-semantic-error" />
              {t('validation.errors', 'Errors')}
            </span>
            <span className="font-medium text-semantic-error tabular-nums">
              {report.counts.errors}
            </span>
          </div>
        </div>
        <div className="border-t border-border-light pt-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-content-tertiary">
              {t('validation.rule_sets', 'Rule sets')}:
            </span>
            {report.rule_sets.length > 0 ? (
              report.rule_sets.map((rs) => (
                <span key={rs} title={getRuleSetDescription(rs, t)} className="inline-flex">
                  <Badge variant="neutral" size="sm">
                    {rs}
                  </Badge>
                </span>
              ))
            ) : (
              <span className="text-xs text-content-tertiary italic">
                {t('validation.no_rule_sets', {
                  defaultValue: 'none configured for this project',
                })}
              </span>
            )}
          </div>
          <p className="mt-1.5 text-xs text-content-tertiary">
            {t('validation.rule_sets_auto_hint', {
              defaultValue:
                'Rule sets are chosen automatically from the project’s region & classification standard.',
            })}
          </p>
          <p className="mt-1 text-xs text-content-tertiary tabular-nums">
            {t('validation.duration', 'Duration')}: {report.duration_ms.toFixed(1)}ms
          </p>
        </div>
      </div>
    </Card>
  );
}

function ResultRow({
  result,
  expanded,
  onToggle,
  boqId,
  onNavigateToPosition,
}: {
  result: ValidationResultItem;
  expanded: boolean;
  onToggle: () => void;
  boqId?: string;
  onNavigateToPosition?: (boqId: string, positionId: string) => void;
}) {
  const { t } = useTranslation();

  const statusIcon = result.passed ? (
    <CheckCircle2 size={16} className="shrink-0 text-semantic-success" />
  ) : result.severity === 'error' ? (
    <XCircle size={16} className="shrink-0 text-semantic-error" />
  ) : (
    <AlertTriangle size={16} className="shrink-0 text-semantic-warning" />
  );

  const statusBadgeVariant = result.passed
    ? 'success'
    : result.severity === 'error'
      ? 'error'
      : 'warning';

  const statusLabel = result.passed
    ? t('validation.status_passed', 'Passed')
    : result.severity === 'error'
      ? t('validation.status_error', 'Error')
      : t('validation.status_warning', 'Warning');

  const tooltip = getRuleDescriptions(t)[result.rule_id] || '';

  return (
    <div
      className={`rounded-xl border transition-all duration-fast ${
        expanded
          ? 'border-border bg-surface-primary shadow-xs'
          : 'border-border-light bg-surface-primary hover:bg-surface-secondary/50'
      }`}
    >
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        title={tooltip}
        aria-expanded={expanded}
        aria-label={`${result.rule_name}: ${statusLabel}`}
      >
        {statusIcon}
        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-content-primary">
            {result.rule_name}
          </span>
        </div>
        {result.element_ref && (
          <span className="hidden text-xs font-mono text-content-tertiary sm:inline-block">
            {result.element_ref.substring(0, 8)}
          </span>
        )}
        <Badge variant={statusBadgeVariant as 'success' | 'error' | 'warning'} size="sm">
          {statusLabel}
        </Badge>
        <span className="shrink-0 text-content-tertiary">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-border-light px-4 py-3 animate-fade-in">
          <p className="text-sm text-content-secondary">{result.message}</p>
          {result.suggestion && (
            <div className="mt-2 flex items-start gap-2 rounded-lg bg-oe-blue-subtle px-3 py-2">
              <Wand2 size={14} className="mt-0.5 shrink-0 text-oe-blue" />
              <p className="text-xs text-oe-blue">
                {t('validation.suggestion', 'Suggestion')}: {result.suggestion}
              </p>
            </div>
          )}
          {result.element_ref && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-content-tertiary">
              <Info size={12} />
              {t('validation.element_ref', 'Element')}:{' '}
              {boqId && onNavigateToPosition ? (
                <button
                  onClick={(e) => { e.stopPropagation(); onNavigateToPosition(boqId, result.element_ref!); }}
                  aria-label={t('validation.go_to_element', { defaultValue: 'Go to element' })}
                  className="inline-flex items-center gap-1 text-oe-blue hover:underline font-mono"
                >
                  {result.element_ref.substring(0, 8)}...
                  <ExternalLink size={10} />
                </button>
              ) : (
                <span className="font-mono">{result.element_ref}</span>
              )}
            </p>
          )}
          {tooltip && (
            <p className="mt-1 text-xs text-content-tertiary italic">{tooltip}</p>
          )}
        </div>
      )}
    </div>
  );
}

function FilterBar({
  filter,
  onFilterChange,
  counts,
}: {
  filter: FilterMode;
  onFilterChange: (f: FilterMode) => void;
  counts: { all: number; errors: number; warnings: number; infos: number; passed: number };
}) {
  const { t } = useTranslation();

  const options: { value: FilterMode; label: string; count: number }[] = [
    { value: 'all', label: t('validation.filter_all', 'All'), count: counts.all },
    { value: 'errors', label: t('validation.filter_errors', 'Errors'), count: counts.errors },
    { value: 'warnings', label: t('validation.filter_warnings', 'Warnings'), count: counts.warnings },
    { value: 'info', label: t('validation.filter_info', 'Info'), count: counts.infos },
    { value: 'passed', label: t('validation.filter_passed', 'Passed'), count: counts.passed },
  ];

  return (
    <div className="flex items-center gap-1.5">
      <Filter size={14} className="text-content-tertiary" />
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onFilterChange(opt.value)}
          aria-pressed={filter === opt.value}
          className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-fast ${
            filter === opt.value
              ? 'bg-oe-blue text-content-inverse shadow-xs'
              : 'bg-surface-secondary text-content-secondary hover:bg-surface-tertiary'
          }`}
        >
          {opt.label}
          <span
            className={`tabular-nums ${
              filter === opt.value ? 'text-content-inverse/70' : 'text-content-tertiary'
            }`}
          >
            {opt.count}
          </span>
        </button>
      ))}
    </div>
  );
}

function SelectDropdown({
  id,
  label,
  value,
  onChange,
  options,
  placeholder,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  placeholder: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-content-primary">{label}</label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`h-10 w-full rounded-lg border border-border bg-surface-primary px-3 text-sm transition-all duration-normal ease-oe focus:outline-none focus:ring-2 focus:ring-oe-blue/30 focus:border-oe-blue hover:border-content-tertiary ${
          !value ? 'text-content-tertiary' : 'text-content-primary'
        }`}
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ── Main Page ─────────────────────────────────────────────────────────── */

export function ValidationPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { activeProjectId, setActiveProject } = useProjectContextStore();
  const addToast = useToastStore((s) => s.addToast);

  const selectedProjectId = activeProjectId ?? '';
  const [selectedBoqId, setSelectedBoqId] = useState('');
  const [filter, setFilter] = useState<FilterMode>('all');
  const [expandedResults, setExpandedResults] = useState<Set<number>>(new Set());

  // Fetch projects
  const { data: projects, isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: () => apiGet<Project[]>('/v1/projects/'),
    staleTime: 5 * 60_000,
  });

  // Fetch BOQs for selected project
  const { data: boqs, isLoading: boqsLoading } = useQuery({
    queryKey: ['boqs', selectedProjectId],
    queryFn: () => apiGet<BOQ[]>(`/v1/boq/boqs/?project_id=${selectedProjectId}`),
    enabled: !!selectedProjectId,
  });

  const selectedProject = useMemo(
    () => projects?.find((p) => p.id === selectedProjectId),
    [projects, selectedProjectId],
  );

  // Rule sets the engine will apply to this project — derived from its
  // classification standard. Shown as chips and sent verbatim to /run/.
  const resolvedRuleSets = useMemo(
    () => resolveRuleSets(selectedProject?.classification_standard),
    [selectedProject],
  );

  // Validation report state (from a run, or restored from the latest
  // persisted report for the selected BOQ).
  const [report, setReport] = useState<ValidationReportData | null>(null);

  const reportIdParam = searchParams.get('report');

  // Restore the latest persisted report for the selected BOQ so re-entering
  // the page (or following a ?report= link) shows the result instead of an
  // empty state. Prefers an explicit ?report= id; otherwise picks the newest
  // report whose target is the selected BOQ.
  const { data: restoredReport } = useQuery({
    queryKey: ['validation', 'latest', selectedProjectId, selectedBoqId, reportIdParam],
    queryFn: async (): Promise<ValidationReportResponse | null> => {
      if (reportIdParam) {
        return apiGet<ValidationReportResponse>(`/v1/validation/reports/${reportIdParam}`);
      }
      const reports = await apiGet<ValidationReportResponse[]>(
        `/v1/validation/reports/?project_id=${selectedProjectId}&target_type=boq`,
      );
      const match = reports.find((r) => r.target_id === selectedBoqId);
      return match ?? null;
    },
    // Fire on an explicit ?report= deep link even before a BOQ is picked, so a
    // link from a validation notification opens the report on its own.
    enabled: (!!selectedProjectId && !!selectedBoqId) || !!reportIdParam,
    staleTime: 30_000,
  });

  // Deep-link alignment: when arriving via ?report= (e.g. from a validation
  // notification), the project/BOQ selectors are usually empty. Point them at
  // the linked report's project and BOQ so the dropdowns, rule chips and the
  // hydrate effect below all resolve to the report being viewed.
  useEffect(() => {
    if (!reportIdParam || !restoredReport) return;
    if (restoredReport.project_id && restoredReport.project_id !== selectedProjectId) {
      const name = projects?.find((p) => p.id === restoredReport.project_id)?.name ?? '';
      setActiveProject(restoredReport.project_id, name);
    }
    if (restoredReport.target_id && restoredReport.target_id !== selectedBoqId) {
      setSelectedBoqId(restoredReport.target_id);
    }
  }, [reportIdParam, restoredReport, selectedProjectId, selectedBoqId, projects, setActiveProject]);

  // Hydrate the page report from a restored persisted report (only when the
  // user has not just produced a fresher one via a run). A deep-linked report
  // (explicit ?report= id) hydrates regardless of the BOQ selection, which the
  // alignment effect above brings into sync a render later.
  useEffect(() => {
    if (!restoredReport) return;
    if (!reportIdParam && restoredReport.target_id !== selectedBoqId) return;
    setReport((prev) => {
      if (prev && prev.id === restoredReport.id) return prev;
      return mapStoredReport(restoredReport);
    });
  }, [restoredReport, selectedBoqId, reportIdParam]);

  // Run validation mutation — persists a server-side ValidationReport via
  // the validation module (RBAC: validation.create) instead of the
  // throwaway BOQ-side validate endpoint.
  const runValidation = useMutation({
    mutationFn: () =>
      apiPost<RunValidationResponse, { project_id: string; boq_id: string; rule_sets: string[] }>(
        '/v1/validation/run/',
        {
          project_id: selectedProjectId,
          boq_id: selectedBoqId,
          rule_sets: resolvedRuleSets,
        },
      ),
    onSuccess: (data) => {
      setReport(mapRunResponse(data));
      setFilter('all');
      setExpandedResults(new Set());
      // Persist the report id in the URL so re-entry restores this result.
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('report', data.report_id);
          return next;
        },
        { replace: true },
      );
      queryClient.invalidateQueries({ queryKey: ['validation'] });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', title: t('validation.run_failed', { defaultValue: 'Validation failed' }), message: err.message });
    },
  });

  // Reset BOQ selection when project changes
  const handleProjectChange = useCallback(
    (projectId: string) => {
      const name = projects?.find((p) => p.id === projectId)?.name ?? '';
      if (projectId) {
        setActiveProject(projectId, name);
      } else {
        useProjectContextStore.getState().clearProject();
      }
      setSelectedBoqId('');
      setReport(null);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete('report');
          return next;
        },
        { replace: true },
      );
    },
    [projects, setActiveProject, setSearchParams],
  );

  const handleBoqChange = useCallback(
    (boqId: string) => {
      setSelectedBoqId(boqId);
      setReport(null);
      // Drop any stale ?report= so the latest-report restore can re-resolve
      // for the newly selected BOQ.
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete('report');
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Filter results
  const filteredResults = useMemo(() => {
    if (!report) return [];
    let results: ValidationResultItem[];
    switch (filter) {
      case 'errors':
        results = report.results.filter((r) => !r.passed && r.severity === 'error');
        break;
      case 'warnings':
        results = report.results.filter((r) => !r.passed && r.severity === 'warning');
        break;
      case 'info':
        results = report.results.filter((r) => !r.passed && r.severity === 'info');
        break;
      case 'passed':
        results = report.results.filter((r) => r.passed);
        break;
      default:
        results = [...report.results];
    }
    // Sort: errors first, then warnings, then info, then passed
    const severityOrder: Record<string, number> = { error: 0, warning: 1, info: 2 };
    return results.sort((a, b) => {
      if (a.passed !== b.passed) return a.passed ? 1 : -1;
      return (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3);
    });
  }, [report, filter]);

  const filterCounts = useMemo(() => {
    if (!report) return { all: 0, errors: 0, warnings: 0, infos: 0, passed: 0 };
    return {
      all: report.results.length,
      errors: report.results.filter((r) => !r.passed && r.severity === 'error').length,
      warnings: report.results.filter((r) => !r.passed && r.severity === 'warning').length,
      infos: report.results.filter((r) => !r.passed && r.severity === 'info').length,
      passed: report.results.filter((r) => r.passed).length,
    };
  }, [report]);

  const toggleResult = useCallback((idx: number) => {
    setExpandedResults((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  }, []);

  const [pdfPending, setPdfPending] = useState(false);

  const handleExportPdf = useCallback(async () => {
    if (!selectedBoqId || pdfPending) return;
    setPdfPending(true);
    try {
      const token = useAuthStore.getState().accessToken;
      const response = await fetch(`/api/v1/boq/boqs/${selectedBoqId}/export/pdf/`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Export failed: ${response.status}`);
      const blob = await response.blob();
      triggerDownload(blob, `boq_${selectedBoqId.slice(0, 8)}.pdf`);
    } catch (err) {
      addToast({
        type: 'error',
        title: t('validation.export_failed', { defaultValue: 'Export failed' }),
        message: err instanceof Error ? err.message : undefined,
      });
    } finally {
      setPdfPending(false);
    }
  }, [selectedBoqId, pdfPending, addToast, t]);

  // The validation findings are persisted server-side as a ValidationReport
  // (see /v1/validation/run/). This CSV is generated client-side from exactly
  // what the user sees so the export always mirrors the on-screen results and
  // applied filters' source data.
  const handleExportCsv = useCallback(() => {
    if (!report) return;
    const esc = (v: string) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = ['rule_id', 'rule_name', 'severity', 'status', 'message', 'element_ref', 'suggestion'];
    const lines = report.results.map((r) =>
      [
        r.rule_id,
        r.rule_name,
        r.severity,
        r.passed ? 'passed' : r.severity === 'error' ? 'error' : 'warning',
        r.message,
        r.element_ref ?? '',
        r.suggestion ?? '',
      ]
        .map((c) => esc(String(c)))
        .join(','),
    );
    const csv = [header.join(','), ...lines].join('\r\n');
    const blob = new Blob(['' + csv], { type: 'text/csv;charset=utf-8;' });
    triggerDownload(blob, `validation_findings_${selectedBoqId.slice(0, 8)}.csv`);
    addToast({
      type: 'success',
      title: t('validation.csv_exported', { defaultValue: 'Findings exported' }),
    });
  }, [report, selectedBoqId, addToast, t]);

  const projectOptions = (projects || []).map((p) => ({
    value: p.id,
    label: p.name,
  }));

  const boqOptions = (boqs || []).map((b) => ({
    value: b.id,
    label: b.name,
  }));

  return (
    <div className="w-full animate-fade-in">
      <Breadcrumb items={[
        ...(selectedProject ? [{ label: selectedProject.name, to: `/projects/${selectedProject.id}` }] : []),
        { label: t('validation.title', 'Validation') },
      ]} className="mb-4" />

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-content-primary">
          {t('validation.title', 'Validation Dashboard')}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t(
            'validation.subtitle',
            'Select a project and BOQ to validate against configured rule sets',
          )}
        </p>
      </div>

      <SectionIntro
        storageKey="validation"
        title={t('validation.intro_title', {
          defaultValue: 'How validation fits the workflow',
        })}
        links={[
          {
            label: t('validation.intro_link_boq', { defaultValue: 'Open BOQ editor' }),
            onClick: () => navigate('/boq'),
          },
          {
            label: t('validation.intro_link_bim', { defaultValue: 'BIM / canonical model' }),
            onClick: () => navigate('/bim'),
          },
        ]}
      >
        {t('validation.intro_body', {
          defaultValue:
            'Validation is a first-class step in the Import → Validate → Enrich → Estimate pipeline. It checks a Bill of Quantities (and its linked canonical/BIM elements) against the rule sets configured for the project — these are derived automatically from the project’s region and classification standard (DIN 276, GAEB, NRM, MasterFormat, boq_quality, …). Each finding links back to the exact BOQ position so you can fix it at the source.',
        })}
      </SectionIntro>

      {/* Selector bar */}
      <Card className="mb-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="flex-1">
            {projectsLoading ? (
              <Skeleton height={40} className="w-full" rounded="md" />
            ) : (
              <SelectDropdown
                id="validation-project-select"
                label={t('validation.select_project', 'Project')}
                value={selectedProjectId}
                onChange={handleProjectChange}
                options={projectOptions}
                placeholder={t('validation.select_project_placeholder', 'Choose a project...')}
              />
            )}
          </div>
          <div className="flex-1">
            {boqsLoading ? (
              <Skeleton height={40} className="w-full" rounded="md" />
            ) : (
              <SelectDropdown
                id="validation-boq-select"
                label={t('validation.select_boq', 'Bill of Quantities')}
                value={selectedBoqId}
                onChange={handleBoqChange}
                options={boqOptions}
                placeholder={
                  selectedProjectId
                    ? t('validation.select_boq_placeholder', 'Choose a BOQ...')
                    : t('validation.select_project_first', 'Select a project first')
                }
              />
            )}
          </div>
          <div className="shrink-0">
            <span title={!selectedBoqId ? t('validation.select_boq_first', { defaultValue: 'Select a project and BOQ first' }) : undefined}>
              <Button
                variant="primary"
                size="md"
                icon={<Play size={16} />}
                loading={runValidation.isPending}
                disabled={!selectedBoqId}
                onClick={() => runValidation.mutate()}
              >
                {t('validation.run', 'Run Validation')}
              </Button>
            </span>
          </div>
        </div>

        {/* Resolved rule sets — shown before running so the user knows
            exactly which checks will be applied to this project. */}
        {selectedProjectId && (
          <div className="mt-4 flex flex-wrap items-center gap-1.5 border-t border-border-light pt-3">
            <span className="text-xs text-content-tertiary">
              {t('validation.will_check_with', { defaultValue: 'Will check with' })}:
            </span>
            {resolvedRuleSets.map((rs) => (
              <span key={rs} title={getRuleSetDescription(rs, t)} className="inline-flex">
                <Badge variant="blue" size="sm">
                  {rs}
                </Badge>
              </span>
            ))}
            <span className="text-xs text-content-tertiary">
              {t('validation.rule_sets_from_standard', {
                defaultValue: 'derived from the project’s classification standard',
              })}
            </span>
          </div>
        )}
      </Card>

      {/* No selection state */}
      {!report && !runValidation.isPending && (
        <EmptyState
          icon={<ShieldCheck size={28} strokeWidth={1.5} />}
          title={t('validation.empty_title', 'No validation report yet')}
          description={t(
            'validation.empty_description',
            'Select a project and BOQ, then click "Run Validation" to check data quality.',
          )}
        />
      )}

      {/* Loading state */}
      {runValidation.isPending && (
        <div className="space-y-4">
          <div className="flex gap-6">
            <Skeleton width={160} height={200} rounded="lg" />
            <Skeleton height={200} className="flex-1" rounded="lg" />
          </div>
          <Skeleton height={48} className="w-full" rounded="lg" />
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} height={56} className="w-full" rounded="lg" />
          ))}
        </div>
      )}

      {/* Error state */}
      {runValidation.isError && (
        <Card className="border-semantic-error/30 bg-semantic-error-bg">
          <div className="flex items-center gap-3">
            <XCircle size={20} className="text-semantic-error" />
            <div>
              <p className="text-sm font-medium text-semantic-error">
                {t('validation.error_title', 'Validation failed')}
              </p>
              <p className="mt-0.5 text-xs text-content-secondary">
                {runValidation.error instanceof Error
                  ? runValidation.error.message
                  : t(
                      'validation.error_description',
                      'Could not run validation. Check that the BOQ has positions and try again.',
                    )}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Report */}
      {report && !runValidation.isPending && (
        <div className="space-y-6 animate-fade-in">
          {/* Score + Summary row */}
          <div className="grid gap-6 md:grid-cols-[200px_1fr]">
            {/* Score circle card */}
            <Card className="flex items-center justify-center">
              <ScoreCircle score={report.score} />
            </Card>

            {/* Summary card */}
            <SummaryCard report={report} />
          </div>

          {/* Filter + Results */}
          <div>
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="text-lg font-semibold text-content-primary">
                {t('validation.results_title', 'Results')}
              </h2>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => setExpandedResults(new Set(filteredResults.map((_, i) => i)))}
                    aria-label={t('validation.expand_all', { defaultValue: 'Expand All' })}
                    className="text-xs font-medium text-content-secondary hover:text-content-primary transition-colors"
                  >
                    {t('validation.expand_all', { defaultValue: 'Expand All' })}
                  </button>
                  <span className="text-content-quaternary">|</span>
                  <button
                    onClick={() => setExpandedResults(new Set())}
                    aria-label={t('validation.collapse_all', { defaultValue: 'Collapse All' })}
                    className="text-xs font-medium text-content-secondary hover:text-content-primary transition-colors"
                  >
                    {t('validation.collapse_all', { defaultValue: 'Collapse All' })}
                  </button>
                </div>
                <FilterBar
                  filter={filter}
                  onFilterChange={setFilter}
                  counts={filterCounts}
                />
              </div>
            </div>

            {/* All passed banner */}
            {report.counts.total > 0 && report.counts.errors === 0 && report.counts.warnings === 0 && (
              <div className="mb-4 flex items-center gap-3 rounded-xl bg-semantic-success-bg px-5 py-4">
                <CheckCircle2 size={20} className="shrink-0 text-semantic-success" />
                <p className="text-sm font-medium text-semantic-success">
                  {t(
                    'validation.all_passed',
                    'All validation rules passed successfully!',
                  )}
                </p>
              </div>
            )}

            {/* Results list */}
            <div className="space-y-2">
              {filteredResults.length === 0 && (
                <p className="py-8 text-center text-sm text-content-tertiary">
                  {t('validation.no_results_for_filter', 'No results match this filter.')}
                </p>
              )}
              {filteredResults.map((result, idx) => (
                <ResultRow
                  key={`${result.rule_id}-${idx}`}
                  result={result}
                  expanded={expandedResults.has(idx)}
                  onToggle={() => toggleResult(idx)}
                  boqId={selectedBoqId || undefined}
                  onNavigateToPosition={(bId, posId) => navigate(`/boq/${bId}?highlight=${posId}`)}
                />
              ))}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3 border-t border-border-light pt-6">
            <Button
              variant="secondary"
              size="md"
              icon={<Download size={16} />}
              onClick={handleExportCsv}
            >
              {t('validation.export_csv', { defaultValue: 'Export Findings (CSV)' })}
            </Button>
            <Button
              variant="ghost"
              size="md"
              icon={<Download size={16} />}
              onClick={handleExportPdf}
              loading={pdfPending}
              disabled={pdfPending}
            >
              {pdfPending
                ? t('validation.export_boq_pdf_pending', { defaultValue: 'Preparing BOQ PDF…' })
                : t('validation.export_priced_boq_pdf', { defaultValue: 'Export priced BOQ (PDF)' })}
            </Button>
            {(report.counts.warnings > 0 || report.counts.errors > 0) && (
              <Button
                variant="ghost"
                size="md"
                icon={<Wand2 size={16} />}
                onClick={() => setFilter('errors')}
              >
                {t('validation.show_issues', 'Show All Issues')}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
