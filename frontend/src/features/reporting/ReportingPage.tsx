import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BarChart3,
  Briefcase,
  Calculator,
  HardHat,
  Wallet,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Clock,
  TrendingUp,
  TrendingDown,
  Loader2,
  FileText,
  ClipboardList,
  Activity,
  Eye,
  X,
} from 'lucide-react';
import { Breadcrumb, Button, Card, CardContent, EmptyState, Skeleton } from '@/shared/ui';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { useAuthStore } from '@/stores/useAuthStore';
import { apiGet, apiPost, API_BASE, getAuthToken, ApiError } from '@/shared/lib/api';
import { projectsApi, type Project } from '@/features/projects/api';

// Roles allowed to trigger the portfolio-wide KPI recompute. The backend
// gates /kpi/recalculate-all/ behind reporting.distribute (MANAGER), so
// editors/viewers would only ever get a 403 — hiding the trigger keeps it
// from being a dead control (W2 audit, /reporting).
const RECALC_ROLES = new Set(['manager', 'admin', 'superuser', 'owner']);

/* ── Types ─────────────────────────────────────────────────────────────────── */

type DashboardTab = 'executive' | 'pm' | 'estimator' | 'site' | 'finance' | 'reports';

interface ReportTemplate {
  id: string;
  name: string;
  report_type: string;
  description: string | null;
  is_system: boolean;
  is_scheduled: boolean;
  schedule_cron: string | null;
  created_at: string;
}

interface GeneratedReport {
  id: string;
  project_id: string;
  template_id: string | null;
  report_type: string;
  title: string;
  format: string;
  generated_at: string;
  created_at: string;
}

interface KPISnapshot {
  id: string;
  project_id: string;
  snapshot_date: string;
  cpi: string | null;
  spi: string | null;
  budget_consumed_pct: string | null;
  open_defects: number;
  open_observations: number;
  schedule_progress_pct: string | null;
  open_rfis: number;
  open_submittals: number;
  risk_score_avg: string | null;
}

// Wire contract for GET /api/v1/finance/dashboard/. The previous shape
// (total_budget / budget_warning / overdue_payable / overdue_receivable /
// invoices_due_this_week / invoices_due_this_month) did NOT exist on the
// finance endpoint, so every card bound to those keys rendered N/A /
// undefined% and the budget traffic-light was permanently green. The real
// response is FinanceDashboardResponse in backend/app/modules/finance/
// schemas.py: total_budget_revised / total_budget_original / total_committed /
// total_overdue / budget_warning_level. Money fields are Decimal-serialized
// and arrive as STRINGS on the wire (the @field_serializer emits plain
// decimal strings), so they are typed `number | string` and MUST be wrapped
// in Number() before any arithmetic / .toFixed() (platform money rule).
// `currency` carries the ISO code these amounts are denominated in — never
// hardcode EUR.
interface FinanceDashboard {
  total_payable: number | string;
  total_receivable: number | string;
  total_budget_original: number | string;
  total_budget_revised: number | string;
  total_committed: number | string;
  total_actual: number | string;
  total_overdue: number | string;
  // Percentage ratio — backend keeps this a float (not in the deferred
  // money list), but it is null-safe to treat the wire value defensively.
  budget_consumed_pct: number | string | null;
  budget_warning_level: string; // "normal" | "caution" | "critical"
  cash_flow_net: number | string;
  currency: string;
}

interface SafetyStats {
  total_incidents: number;
  total_observations: number;
  open_corrective_actions: number;
  days_since_last_incident: number;
}

interface TaskStats {
  total: number;
  by_status: Record<string, number>;
  overdue: number;
}

interface RFIStats {
  total: number;
  open: number;
  overdue: number;
  avg_response_days: number;
}

interface ScheduleStats {
  total_activities: number;
  completed: number;
  in_progress: number;
  delayed: number;
  on_track: number;
  progress_pct: number;
}

interface ProcurementStats {
  total_pos: number;
  by_status: Record<string, number>;
  total_committed: number;
  pending_delivery: number;
}

/* ── KPI helpers ───��───────────────────────────────────────────────────────── */

type TrafficLight = 'green' | 'yellow' | 'red' | 'gray';

function kpiColor(value: number | null | undefined, thresholds: [number, number]): TrafficLight {
  if (value === null || value === undefined) return 'gray';
  if (value >= thresholds[1]) return 'green';
  if (value >= thresholds[0]) return 'yellow';
  return 'red';
}

const trafficClasses: Record<TrafficLight, string> = {
  green: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  yellow: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  red: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  gray: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
};

// Empty metrics render as a muted em-dash, never "N/A". A grid full of
// "N/A" reads as a broken page; a quiet dash reads as "not measured yet".
const EMPTY = '—';

function fmt(v: string | number | null | undefined, suffix = ''): string {
  if (v === null || v === undefined || v === '') return EMPTY;
  return `${v}${suffix}`;
}

// Humanise a report_type enum token ("progress_report" → "Progress
// Report") for display. Report types are seeded server-side, so the list
// is open-ended; rather than maintaining a closed label map we Title-Case
// the snake_case token. Keeps the new progress_report type readable
// without a frontend code change per new type.
function humanizeReportType(reportType: string): string {
  if (!reportType) return '';
  return reportType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtNum(v: number | null | undefined, decimals = 0): string {
  if (v === null || v === undefined) return EMPTY;
  return v.toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

// Money-bug guard: finance amounts arrive as Decimal-serialized STRINGS
// (e.g. "517103508.65"). Passing a string to fmtNum (which calls
// .toLocaleString) or doing `value > 0` would format/compare a string —
// yielding "NaN" or a lexicographic comparison. Coerce through Number()
// first; non-numeric/empty values become null so the card shows N/A rather
// than a misleading 0. Returns number | null, which fmtNum already accepts.
function toMoneyNum(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/* ── KPI Card component ────────────────────────────────────────────────────── */

function KPICard({
  label,
  value,
  color = 'gray',
  icon: Icon,
}: {
  label: string;
  value: string;
  color?: TrafficLight;
  icon?: React.ElementType;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border-light bg-surface-primary p-4 shadow-xs">
      {Icon && (
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${trafficClasses[color]}`}>
          <Icon size={18} />
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-content-secondary">{label}</p>
        <p className="text-lg font-semibold text-content-primary">{value}</p>
      </div>
    </div>
  );
}

/* ── Project status badge ──────────────────────────────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  const { t } = useTranslation();
  // Colors carry dark-mode variants so the badge is legible in both
  // themes (the rest of the page is dark-aware). Labels route through
  // t() so non-English locales don't see raw English enum tokens; the
  // unknown-status fallback humanises snake_case rather than printing it
  // verbatim.
  const map: Record<string, { color: string; label: string }> = {
    active: {
      color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
      label: t('reporting.status_active', { defaultValue: 'Active' }),
    },
    on_hold: {
      color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
      label: t('reporting.status_on_hold', { defaultValue: 'On Hold' }),
    },
    completed: {
      color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      label: t('reporting.status_completed', { defaultValue: 'Completed' }),
    },
    archived: {
      color: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
      label: t('reporting.status_archived', { defaultValue: 'Archived' }),
    },
  };
  const fallbackLabel = status
    ? status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
    : t('reporting.status_unknown', { defaultValue: 'Unknown' });
  const s = map[status] ?? {
    color: 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
    label: fallbackLabel,
  };
  return <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${s.color}`}>{s.label}</span>;
}

/* ── Tab buttons ─────��─────────────────────────────────────────────────────── */

const TABS: { key: DashboardTab; labelKey: string; defaultLabel: string; icon: React.ElementType }[] = [
  { key: 'executive', labelKey: 'reporting.tab_executive', defaultLabel: 'Executive', icon: Briefcase },
  { key: 'pm', labelKey: 'reporting.tab_pm', defaultLabel: 'Project Manager', icon: ClipboardList },
  { key: 'estimator', labelKey: 'reporting.tab_estimator', defaultLabel: 'Estimator', icon: Calculator },
  { key: 'site', labelKey: 'reporting.tab_site', defaultLabel: 'Site Engineer', icon: HardHat },
  { key: 'finance', labelKey: 'reporting.tab_finance', defaultLabel: 'Finance', icon: Wallet },
  { key: 'reports', labelKey: 'reporting.tab_reports', defaultLabel: 'Reports', icon: FileText },
];

/* ── Main component ────────────────────────────────────────────────────────── */

export function ReportingPage() {
  const { t } = useTranslation();
  const { activeProjectId, activeProjectName } = useProjectContextStore();
  const userRole = useAuthStore((s) => s.userRole);
  const canRecalculate = RECALC_ROLES.has((userRole ?? '').toLowerCase());

  const [tab, setTab] = useState<DashboardTab>('executive');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [recalcError, setRecalcError] = useState(false);

  // Data
  const [projects, setProjects] = useState<Project[]>([]);
  const [kpiMap, setKpiMap] = useState<Record<string, KPISnapshot>>({});
  const [financeDash, setFinanceDash] = useState<FinanceDashboard | null>(null);
  const [safetyStats, setSafetyStats] = useState<SafetyStats | null>(null);
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null);
  const [rfiStats, setRfiStats] = useState<RFIStats | null>(null);
  const [scheduleStats, setScheduleStats] = useState<ScheduleStats | null>(null);
  const [procurementStats, setProcurementStats] = useState<ProcurementStats | null>(null);

  const selectedProjectId = activeProjectId ?? '';

  // Generation counter — bumped at the start of every loadProjectStats
  // call so in-flight responses for an older pid get discarded if the
  // user switches projects mid-fetch (otherwise stale data overwrites
  // current data when the slow request finally resolves).
  const statsGenRef = useRef(0);

  const loadProjectStats = useCallback(async (pid: string) => {
    const gen = ++statsGenRef.current;
    const guard = <T,>(setter: (v: T | null) => void) => (v: T) => {
      if (statsGenRef.current === gen) setter(v);
    };
    const results = await Promise.allSettled([
      apiGet<FinanceDashboard>(`/v1/finance/dashboard/?project_id=${pid}`).then(guard(setFinanceDash)),
      apiGet<SafetyStats>(`/v1/safety/stats/?project_id=${pid}`).then(guard(setSafetyStats)),
      apiGet<TaskStats>(`/v1/tasks/stats/?project_id=${pid}`).then(guard(setTaskStats)),
      apiGet<RFIStats>(`/v1/rfi/stats/?project_id=${pid}`).then(guard(setRfiStats)),
      apiGet<ScheduleStats>(`/v1/schedule/stats/?project_id=${pid}`).then(guard(setScheduleStats)),
      apiGet<ProcurementStats>(`/v1/procurement/stats/?project_id=${pid}`).then(guard(setProcurementStats)),
    ]);

    // Clear data for rejected promises to avoid stale state — but only
    // if this fetch is still the current generation.
    if (statsGenRef.current !== gen) return;
    if (results[0].status === 'rejected') setFinanceDash(null);
    if (results[1].status === 'rejected') setSafetyStats(null);
    if (results[2].status === 'rejected') setTaskStats(null);
    if (results[3].status === 'rejected') setRfiStats(null);
    if (results[4].status === 'rejected') setScheduleStats(null);
    if (results[5].status === 'rejected') setProcurementStats(null);
  }, []);

  // Load everything
  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      const projs = await projectsApi.list();
      setProjects(projs);

      // Load KPI for each project
      const kpis: Record<string, KPISnapshot> = {};
      await Promise.allSettled(
        projs.map(async (p) => {
          try {
            const kpi = await apiGet<KPISnapshot | null>(
              `/v1/reporting/kpi/?project_id=${p.id}`,
            );
            if (kpi) kpis[p.id] = kpi;
          } catch {
            // no KPI for this project yet
          }
        }),
      );
      setKpiMap(kpis);

      // Project-scoped stats (use selected project or first)
      const pid = selectedProjectId || projs[0]?.id;
      if (pid) {
        await loadProjectStats(pid);
      }
    } catch {
      // The per-project KPI and per-section fetches above already
      // degrade gracefully (Promise.allSettled). Reaching this catch
      // means the *fatal* projects.list() call failed — without a
      // surfaced error the user would see an empty dashboard that is
      // indistinguishable from "no projects yet". Flag it so the
      // retry banner renders instead.
      setProjects([]);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [selectedProjectId, loadProjectStats]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reload project-specific stats when selected project changes
  useEffect(() => {
    if (selectedProjectId) {
      loadProjectStats(selectedProjectId);
    }
  }, [selectedProjectId, loadProjectStats]);

  const handleRecalculate = async () => {
    setRecalculating(true);
    setRecalcError(false);
    try {
      await apiPost('/v1/reporting/kpi/recalculate-all/', {});
      await loadData();
    } catch {
      // No error boundary wraps this page — a swallowed failure left
      // the button looking like it succeeded. Surface it inline.
      setRecalcError(true);
    } finally {
      setRecalculating(false);
    }
  };

  // Active / total counts
  const activeProjects = projects.filter((p) => p.status === 'active');
  // Portfolio value MUST NOT blend currencies: a EUR project and a USD
  // project cannot be added as if 1 EUR = 1 USD. We group each project's
  // budget by its own ISO currency and let the UI render per-currency
  // subtotals (each carrying its code), per the platform money rule.
  const portfolioValueByCurrency = projects.reduce<Record<string, number>>((acc, p) => {
    const meta = p.metadata as Record<string, unknown> | undefined;
    const budget = meta?.budget_estimate ?? (p as unknown as Record<string, unknown>).budget_estimate;
    const amount = budget ? Number(budget) || 0 : 0;
    if (amount <= 0) return acc;
    const code = (p.currency || '').trim().toUpperCase() || 'N/A';
    acc[code] = (acc[code] ?? 0) + amount;
    return acc;
  }, {});

  const selectedProject = projects.find((p) => p.id === selectedProjectId);
  const selectedKpi = selectedProjectId ? kpiMap[selectedProjectId] : undefined;

  /* ── Render ─────────────────────────────────────────────────────────────── */

  return (
    <div className="w-full space-y-6 animate-fade-in">
      <Breadcrumb
        items={[
          ...(activeProjectName
            ? [{ label: activeProjectName, to: `/projects/${activeProjectId}` }]
            : []),
          { label: t('nav.reporting_dashboards', { defaultValue: 'Reporting Dashboards' }) },
        ]}
        className="mb-4"
      />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-content-primary">
            {t('reporting.title', { defaultValue: 'Reporting Dashboards' })}
          </h1>
          <p className="mt-1 text-sm text-content-secondary">
            {t('reporting.subtitle', {
              defaultValue: 'Role-based KPI dashboards with real-time project data',
            })}
          </p>
        </div>
        {canRecalculate && (
          <button
            onClick={handleRecalculate}
            disabled={recalculating}
            className="inline-flex items-center gap-2 rounded-lg bg-oe-blue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-oe-blue-hover disabled:opacity-50"
          >
            {recalculating ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            {t('reporting.recalculate', { defaultValue: 'Recalculate KPIs' })}
          </button>
        )}
      </div>

      {recalcError && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400"
        >
          <AlertTriangle size={16} className="shrink-0" />
          <span>
            {t('reporting.recalculate_failed', {
              defaultValue: 'KPI recalculation failed. Please try again.',
            })}
          </span>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex flex-wrap gap-1 rounded-xl border border-border-light bg-surface-secondary p-1">
        {TABS.map(({ key, labelKey, defaultLabel, icon: TabIcon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              tab === key
                ? 'bg-surface-primary text-content-primary shadow-sm'
                : 'text-content-secondary hover:text-content-primary hover:bg-surface-primary/50'
            }`}
          >
            <TabIcon size={16} />
            {t(labelKey, { defaultValue: defaultLabel })}
          </button>
        ))}
      </div>

      {/* Project selector for PM / Estimator / Site / Finance tabs */}
      {tab !== 'executive' && (
        <div className="flex items-center gap-3">
          <label className="text-xs font-medium text-content-secondary">
            {t('reporting.select_project', { defaultValue: 'Project' })}
          </label>
          <select
            value={selectedProjectId}
            onChange={(e) => {
              const id = e.target.value;
              const name = projects.find((p) => p.id === id)?.name ?? '';
              if (id) {
                useProjectContextStore.getState().setActiveProject(id, name);
              }
            }}
            className="h-9 min-w-[240px] rounded-lg border border-border-light bg-surface-primary px-3 text-sm text-content-primary outline-none focus:border-oe-blue focus:ring-1 focus:ring-oe-blue"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {/* Fatal load failure — distinct from "no projects yet" */}
      {!loading && loadError && (
        <Card>
          <CardContent>
            <div
              role="alert"
              className="flex flex-col items-center justify-center gap-3 py-12 text-center"
            >
              <AlertTriangle size={40} className="text-red-500" />
              <p className="text-sm text-content-secondary">
                {t('reporting.load_error', {
                  defaultValue: 'Could not load reporting data. Check your connection and try again.',
                })}
              </p>
              <button
                onClick={loadData}
                className="inline-flex items-center gap-2 rounded-lg border border-border-light bg-surface-primary px-4 py-2 text-sm font-medium text-content-primary transition-colors hover:bg-surface-secondary"
              >
                <RefreshCw size={16} />
                {t('common.retry', { defaultValue: 'Retry' })}
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tab content */}
      {!loading && !loadError && tab === 'executive' && (
        <ExecutiveDashboard
          projects={projects}
          activeProjects={activeProjects}
          valueByCurrency={portfolioValueByCurrency}
          kpiMap={kpiMap}
        />
      )}
      {!loading && !loadError && tab === 'pm' && (
        <PMDashboard
          project={selectedProject}
          kpi={selectedKpi}
          taskStats={taskStats}
          rfiStats={rfiStats}
          scheduleStats={scheduleStats}
        />
      )}
      {!loading && !loadError && tab === 'estimator' && (
        <EstimatorDashboard
          project={selectedProject}
          kpi={selectedKpi}
        />
      )}
      {!loading && !loadError && tab === 'site' && (
        <SiteDashboard
          project={selectedProject}
          safetyStats={safetyStats}
          scheduleStats={scheduleStats}
        />
      )}
      {!loading && !loadError && tab === 'finance' && (
        <FinanceDashboardView
          project={selectedProject}
          financeDash={financeDash}
          procurementStats={procurementStats}
        />
      )}
      {!loading && !loadError && tab === 'reports' && (
        <ReportsTab project={selectedProject} />
      )}
    </div>
  );
}

/* ── Executive Dashboard ──────────────────────────────────────────────────── */

function ExecutiveDashboard({
  projects,
  activeProjects,
  valueByCurrency,
  kpiMap,
}: {
  projects: Project[];
  activeProjects: Project[];
  valueByCurrency: Record<string, number>;
  kpiMap: Record<string, KPISnapshot>;
}) {
  const { t } = useTranslation();

  // Sort currencies by descending subtotal so the largest leads. Each
  // entry keeps its own ISO code — we never collapse them into one
  // figure because there is no FX context here to convert with.
  const currencyEntries = Object.entries(valueByCurrency).sort((a, b) => b[1] - a[1]);
  const [topEntry] = currencyEntries;
  const portfolioValueLabel =
    currencyEntries.length === 0 || topEntry === undefined
      ? EMPTY
      : currencyEntries.length === 1
        ? `${fmtNum(topEntry[1])} ${topEntry[0]}`
        : currencyEntries.map(([code, amount]) => `${fmtNum(amount)} ${code}`).join(' · ');

  return (
    <div className="space-y-6">
      {/* Portfolio KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('reporting.total_projects', { defaultValue: 'Total Projects' })}
          value={String(projects.length)}
          color="gray"
          icon={FileText}
        />
        <KPICard
          label={t('reporting.active_projects', { defaultValue: 'Active Projects' })}
          value={String(activeProjects.length)}
          color="green"
          icon={Activity}
        />
        <KPICard
          label={t('reporting.portfolio_value', { defaultValue: 'Portfolio Value' })}
          value={portfolioValueLabel}
          color="gray"
          icon={BarChart3}
        />
        <KPICard
          label={t('reporting.projects_with_kpi', { defaultValue: 'Projects with KPI' })}
          value={`${Object.keys(kpiMap).length} / ${projects.length}`}
          color={Object.keys(kpiMap).length >= projects.length ? 'green' : 'yellow'}
          icon={TrendingUp}
        />
      </div>

      {/* Explain the dashes: KPI snapshots are opt-in per project, so a fresh
          project legitimately has no CPI/SPI/progress until its first snapshot. */}
      {projects.length > 0 && Object.keys(kpiMap).length < projects.length && (
        <div className="flex items-start gap-2 rounded-lg border border-border-light bg-surface-secondary/60 px-4 py-2.5 text-xs text-content-secondary">
          <Activity size={14} className="mt-0.5 shrink-0 text-content-tertiary" />
          <span>
            {t('reporting.kpi_empty_hint', {
              defaultValue:
                'CPI, SPI, budget and schedule progress appear once a project has its first cost snapshot. Projects without one show a dash, not a problem.',
            })}
          </span>
        </div>
      )}

      {/* Project table with KPI traffic lights */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-light bg-surface-secondary text-left text-xs font-medium text-content-secondary">
                  <th className="px-4 py-3">{t('reporting.col_project', { defaultValue: 'Project' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_status', { defaultValue: 'Status' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_cpi', { defaultValue: 'CPI' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_spi', { defaultValue: 'SPI' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_budget', { defaultValue: 'Budget %' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_schedule', { defaultValue: 'Schedule %' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_risk', { defaultValue: 'Risk Score' })}</th>
                  <th className="px-4 py-3">{t('reporting.col_open_items', { defaultValue: 'Open Items' })}</th>
                </tr>
              </thead>
              <tbody>
                {projects.map((p) => {
                  const kpi = kpiMap[p.id];
                  const cpiVal = kpi?.cpi ? parseFloat(kpi.cpi) : null;
                  const spiVal = kpi?.spi ? parseFloat(kpi.spi) : null;
                  const budgetVal = kpi?.budget_consumed_pct ? parseFloat(kpi.budget_consumed_pct) : null;
                  const schedVal = kpi?.schedule_progress_pct ? parseFloat(kpi.schedule_progress_pct) : null;
                  const riskVal = kpi?.risk_score_avg ? parseFloat(kpi.risk_score_avg) : null;
                  const openItems = (kpi?.open_rfis ?? 0) + (kpi?.open_submittals ?? 0) + (kpi?.open_defects ?? 0) + (kpi?.open_observations ?? 0);

                  return (
                    <tr key={p.id} className="border-b border-border-light last:border-0 hover:bg-surface-secondary/50">
                      <td className="px-4 py-3 font-medium text-content-primary">{p.name}</td>
                      <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                      <td className="px-4 py-3">
                        <TrafficDot color={kpiColor(cpiVal, [0.9, 1.0])} label={fmt(kpi?.cpi)} />
                      </td>
                      <td className="px-4 py-3">
                        <TrafficDot color={kpiColor(spiVal, [0.9, 1.0])} label={fmt(kpi?.spi)} />
                      </td>
                      <td className="px-4 py-3">
                        <TrafficDot color={budgetVal !== null ? kpiColor(100 - budgetVal, [5, 20]) : 'gray'} label={fmt(kpi?.budget_consumed_pct, '%')} />
                      </td>
                      <td className="px-4 py-3">
                        <TrafficDot color={kpiColor(schedVal, [50, 80])} label={fmt(kpi?.schedule_progress_pct, '%')} />
                      </td>
                      <td className="px-4 py-3">
                        <TrafficDot color={riskVal !== null ? kpiColor(10 - riskVal, [3, 7]) : 'gray'} label={fmt(kpi?.risk_score_avg)} />
                      </td>
                      <td className="px-4 py-3 text-content-secondary">
                        {kpi ? openItems : <span className="text-content-tertiary">{EMPTY}</span>}
                      </td>
                    </tr>
                  );
                })}
                {projects.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-8 text-center text-content-secondary">
                      {t('reporting.no_projects', { defaultValue: 'No projects found' })}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/* ── Traffic dot component ─────────────────────────────────────────────────── */

function TrafficDot({ color, label }: { color: TrafficLight; label: string }) {
  // No value yet: render a quiet muted dash with no status dot, so an
  // un-snapshotted project does not light up a row of grey "lights".
  if (label === EMPTY) {
    return <span className="text-sm text-content-tertiary">{EMPTY}</span>;
  }
  const dotColors: Record<TrafficLight, string> = {
    green: 'bg-emerald-500',
    yellow: 'bg-amber-500',
    red: 'bg-red-500',
    gray: 'bg-gray-300 dark:bg-gray-600',
  };
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotColors[color]}`} />
      <span className="text-sm text-content-primary">{label}</span>
    </span>
  );
}

/* ── PM Dashboard ──────────────────────────────────────────────────────────── */

function PMDashboard({
  project,
  kpi,
  taskStats,
  rfiStats,
  scheduleStats,
}: {
  project?: Project;
  kpi?: KPISnapshot;
  taskStats: TaskStats | null;
  rfiStats: RFIStats | null;
  scheduleStats: ScheduleStats | null;
}) {
  const { t } = useTranslation();
  if (!project) {
    return <PromptCard message={t('reporting.select_project_prompt', { defaultValue: 'Select a project to view PM dashboard' })} />;
  }

  const budgetPct = kpi?.budget_consumed_pct ? parseFloat(kpi.budget_consumed_pct) : null;
  const spiVal = kpi?.spi ? parseFloat(kpi.spi) : null;
  const cpiVal = kpi?.cpi ? parseFloat(kpi.cpi) : null;

  return (
    <div className="space-y-6">
      {/* Project KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('reporting.budget_consumed', { defaultValue: 'Budget Consumed' })}
          value={fmt(kpi?.budget_consumed_pct, '%')}
          color={budgetPct !== null ? kpiColor(100 - budgetPct, [5, 20]) : 'gray'}
          icon={Wallet}
        />
        <KPICard
          label={t('reporting.spi', { defaultValue: 'Schedule SPI' })}
          value={fmt(kpi?.spi)}
          color={kpiColor(spiVal, [0.9, 1.0])}
          icon={spiVal !== null && spiVal >= 1 ? TrendingUp : TrendingDown}
        />
        <KPICard
          label={t('reporting.cpi', { defaultValue: 'Cost CPI' })}
          value={fmt(kpi?.cpi)}
          color={kpiColor(cpiVal, [0.9, 1.0])}
          icon={cpiVal !== null && cpiVal >= 1 ? TrendingUp : TrendingDown}
        />
        <KPICard
          label={t('reporting.schedule_progress', { defaultValue: 'Schedule Progress' })}
          value={fmt(kpi?.schedule_progress_pct, '%')}
          color={kpiColor(
            kpi?.schedule_progress_pct ? parseFloat(kpi.schedule_progress_pct) : null,
            [50, 80],
          )}
          icon={BarChart3}
        />
      </div>

      {/* Open items row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('reporting.open_rfis', { defaultValue: 'Open RFIs' })}
          value={rfiStats ? String(rfiStats.open) : fmt(kpi?.open_rfis)}
          color={kpiColor(rfiStats?.open !== undefined ? (rfiStats.open === 0 ? 10 : 10 - rfiStats.open) : null, [0, 5])}
          icon={FileText}
        />
        <KPICard
          label={t('reporting.open_submittals', { defaultValue: 'Open Submittals' })}
          value={String(kpi?.open_submittals ?? 'N/A')}
          color="gray"
          icon={ClipboardList}
        />
        <KPICard
          label={t('reporting.overdue_tasks', { defaultValue: 'Overdue Tasks' })}
          value={taskStats ? String(taskStats.overdue) : 'N/A'}
          color={taskStats?.overdue ? (taskStats.overdue > 5 ? 'red' : 'yellow') : 'gray'}
          icon={AlertTriangle}
        />
        <KPICard
          label={t('reporting.total_tasks', { defaultValue: 'Total Tasks' })}
          value={taskStats ? String(taskStats.total) : 'N/A'}
          color="gray"
          icon={CheckCircle2}
        />
      </div>

      {/* Schedule summary */}
      {scheduleStats && (
        <Card>
          <CardContent>
            <h3 className="mb-3 text-sm font-semibold text-content-primary">
              {t('reporting.schedule_summary', { defaultValue: 'Schedule Summary' })}
            </h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              <StatBlock label={t('reporting.total_activities', { defaultValue: 'Total' })} value={scheduleStats.total_activities} />
              <StatBlock label={t('reporting.completed', { defaultValue: 'Completed' })} value={scheduleStats.completed} color="emerald" />
              <StatBlock label={t('reporting.in_progress', { defaultValue: 'In Progress' })} value={scheduleStats.in_progress} color="blue" />
              <StatBlock label={t('reporting.delayed', { defaultValue: 'Delayed' })} value={scheduleStats.delayed} color="red" />
              <StatBlock label={t('reporting.on_track', { defaultValue: 'On Track' })} value={scheduleStats.on_track} color="emerald" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* RFI details */}
      {rfiStats && (
        <Card>
          <CardContent>
            <h3 className="mb-3 text-sm font-semibold text-content-primary">
              {t('reporting.rfi_summary', { defaultValue: 'RFI Summary' })}
            </h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatBlock label={t('reporting.total', { defaultValue: 'Total' })} value={rfiStats.total} />
              <StatBlock label={t('reporting.open', { defaultValue: 'Open' })} value={rfiStats.open} color="amber" />
              <StatBlock label={t('reporting.overdue', { defaultValue: 'Overdue' })} value={rfiStats.overdue} color="red" />
              <StatBlock
                label={t('reporting.avg_response', { defaultValue: 'Avg Response (days)' })}
                value={rfiStats.avg_response_days?.toFixed(1) ?? 'N/A'}
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ── Estimator Dashboard ─────────��─────────────────────────────────────────── */

function EstimatorDashboard({
  project,
  kpi,
}: {
  project?: Project;
  kpi?: KPISnapshot;
}) {
  const { t } = useTranslation();
  const [boqs, setBoqs] = useState<Array<{ id: string; name: string; status: string; grand_total: number; currency: string; position_count: number }>>([]);
  const [loadingBoqs, setLoadingBoqs] = useState(false);
  const projectId = project?.id;

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    setLoadingBoqs(true);
    (async () => {
      try {
        const data = await apiGet<Array<{ id: string; name: string; status: string; grand_total: number; currency: string; position_count: number }>>(
          `/v1/boq/boqs/?project_id=${projectId}`,
        );
        if (!cancelled) setBoqs(data);
      } catch {
        if (!cancelled) setBoqs([]);
      } finally {
        if (!cancelled) setLoadingBoqs(false);
      }
    })();
    return () => { cancelled = true; };
  }, [projectId]);

  if (!project) {
    return <PromptCard message={t('reporting.select_project_prompt_estimator', { defaultValue: 'Select a project to view Estimator dashboard' })} />;
  }

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KPICard
          label={t('reporting.cpi', { defaultValue: 'CPI' })}
          value={fmt(kpi?.cpi)}
          color={kpiColor(kpi?.cpi ? parseFloat(kpi.cpi) : null, [0.9, 1.0])}
          icon={TrendingUp}
        />
        <KPICard
          label={t('reporting.budget_consumed', { defaultValue: 'Budget Consumed' })}
          value={fmt(kpi?.budget_consumed_pct, '%')}
          color="gray"
          icon={Wallet}
        />
        <KPICard
          label={t('reporting.boq_count', { defaultValue: 'BOQs' })}
          value={String(boqs.length)}
          color="gray"
          icon={Calculator}
        />
      </div>

      {/* BOQ table */}
      <Card>
        <CardContent className="p-0">
          {loadingBoqs ? (
            <div className="p-4">
              <Skeleton className="h-20 w-full rounded-lg" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-light bg-surface-secondary text-left text-xs font-medium text-content-secondary">
                    <th className="px-4 py-3">{t('reporting.boq_name', { defaultValue: 'BOQ Name' })}</th>
                    <th className="px-4 py-3">{t('reporting.col_status', { defaultValue: 'Status' })}</th>
                    <th className="px-4 py-3 text-right">{t('reporting.positions', { defaultValue: 'Positions' })}</th>
                    <th className="px-4 py-3 text-right">{t('reporting.grand_total', { defaultValue: 'Grand Total' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {boqs.map((b) => (
                    <tr key={b.id} className="border-b border-border-light last:border-0 hover:bg-surface-secondary/50">
                      <td className="px-4 py-3 font-medium text-content-primary">{b.name}</td>
                      <td className="px-4 py-3"><StatusBadge status={b.status} /></td>
                      <td className="px-4 py-3 text-right text-content-secondary">{b.position_count ?? 0}</td>
                      <td className="px-4 py-3 text-right font-medium text-content-primary">
                        {fmtNum(b.grand_total, 2)} {b.currency}
                      </td>
                    </tr>
                  ))}
                  {boqs.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-8 text-center text-content-secondary">
                        {t('reporting.no_boqs', { defaultValue: 'No BOQs in this project' })}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/* ── Site Engineer Dashboard ───────────────────────────────────────────────── */

function SiteDashboard({
  project,
  safetyStats,
  scheduleStats,
}: {
  project?: Project;
  safetyStats: SafetyStats | null;
  scheduleStats: ScheduleStats | null;
}) {
  const { t } = useTranslation();

  if (!project) {
    return <PromptCard message={t('reporting.select_project_prompt_site', { defaultValue: 'Select a project to view Site Engineer dashboard' })} />;
  }

  return (
    <div className="space-y-6">
      {/* Schedule KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('reporting.today_activities', { defaultValue: 'Total Activities' })}
          value={scheduleStats ? String(scheduleStats.total_activities) : 'N/A'}
          color="gray"
          icon={ClipboardList}
        />
        <KPICard
          label={t('reporting.in_progress', { defaultValue: 'In Progress' })}
          value={scheduleStats ? String(scheduleStats.in_progress) : 'N/A'}
          color="green"
          icon={Activity}
        />
        <KPICard
          label={t('reporting.delayed_activities', { defaultValue: 'Delayed' })}
          value={scheduleStats ? String(scheduleStats.delayed) : 'N/A'}
          color={scheduleStats?.delayed ? (scheduleStats.delayed > 3 ? 'red' : 'yellow') : 'gray'}
          icon={AlertTriangle}
        />
        <KPICard
          label={t('reporting.progress', { defaultValue: 'Progress' })}
          value={scheduleStats ? `${scheduleStats.progress_pct?.toFixed(0) ?? 0}%` : 'N/A'}
          color={kpiColor(scheduleStats?.progress_pct ?? null, [50, 80])}
          icon={BarChart3}
        />
      </div>

      {/* Safety stats */}
      {safetyStats ? (
        <Card>
          <CardContent>
            <h3 className="mb-3 text-sm font-semibold text-content-primary">
              {t('reporting.safety_overview', { defaultValue: 'Safety Overview' })}
            </h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatBlock
                label={t('reporting.incidents', { defaultValue: 'Incidents' })}
                value={safetyStats.total_incidents}
                color={safetyStats.total_incidents > 0 ? 'red' : 'emerald'}
              />
              <StatBlock
                label={t('reporting.observations', { defaultValue: 'Observations' })}
                value={safetyStats.total_observations}
              />
              <StatBlock
                label={t('reporting.open_actions', { defaultValue: 'Open Actions' })}
                value={safetyStats.open_corrective_actions}
                color={safetyStats.open_corrective_actions > 0 ? 'amber' : 'emerald'}
              />
              <StatBlock
                label={t('reporting.days_safe', { defaultValue: 'Days Since Incident' })}
                value={safetyStats.days_since_last_incident}
                color="emerald"
              />
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent>
            <p className="text-sm text-content-secondary">
              {t('reporting.no_safety_data', { defaultValue: 'No safety data available for this project.' })}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ���─ Finance Dashboard ───────���─────────────────────────────────────────────── */

function FinanceDashboardView({
  project,
  financeDash,
  procurementStats,
}: {
  project?: Project;
  financeDash: FinanceDashboard | null;
  procurementStats: ProcurementStats | null;
}) {
  const { t } = useTranslation();

  if (!project) {
    return <PromptCard message={t('reporting.select_project_prompt_finance', { defaultValue: 'Select a project to view Finance dashboard' })} />;
  }

  // The procurement stats endpoint does not expose its own currency, so
  // committed money is shown against the project's finance currency
  // (purchase orders inherit the project currency). Money must always
  // carry its ISO code — a bare number is ambiguous. Derived from the
  // finance payload's own currency first, then the project, never EUR.
  const procurementCurrency = financeDash?.currency || project.currency || '';

  // Coerce the Decimal-string money fields once so arithmetic and
  // formatting below operate on real numbers (money-bug fix). null means
  // the figure was absent — render N/A instead of a misleading 0.
  const currency = financeDash?.currency ?? '';
  const totalPayable = toMoneyNum(financeDash?.total_payable);
  const totalReceivable = toMoneyNum(financeDash?.total_receivable);
  // Was overdue_payable (a key the endpoint never returns) — real wire field
  // is total_overdue.
  const totalOverdue = toMoneyNum(financeDash?.total_overdue);
  const cashFlowNet = toMoneyNum(financeDash?.cash_flow_net);
  // Real wire field is total_budget_revised; the old `total_budget` key never
  // existed so this card always read N/A.
  const totalBudgetRevised = toMoneyNum(financeDash?.total_budget_revised);
  const totalCommitted = toMoneyNum(financeDash?.total_committed);
  const totalActual = toMoneyNum(financeDash?.total_actual);
  // budget_consumed_pct is a percentage (may be string/float/null on the wire).
  const budgetConsumedPct = toMoneyNum(financeDash?.budget_consumed_pct);
  // Primary budget signal is the numeric consumed-% (unambiguous); the
  // backend's budget_warning_level string ("normal"|"caution"|"critical") is
  // a secondary escalator. The old code compared the nonexistent
  // `budget_warning` key, so the light was permanently green even at 100%.
  const warningLevel = (financeDash?.budget_warning_level ?? '').toLowerCase();
  const budgetColor: TrafficLight =
    warningLevel === 'critical' || (budgetConsumedPct !== null && budgetConsumedPct >= 100)
      ? 'red'
      : warningLevel === 'caution' || (budgetConsumedPct !== null && budgetConsumedPct >= 90)
        ? 'yellow'
        : budgetConsumedPct === null
          ? 'gray'
          : 'green';

  return (
    <div className="space-y-6">
      {/* Finance KPIs */}
      {financeDash ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label={t('reporting.payable', { defaultValue: 'Total Payable' })}
              value={`${fmtNum(totalPayable, 2)} ${currency}`.trim()}
              color="gray"
              icon={Wallet}
            />
            <KPICard
              label={t('reporting.receivable', { defaultValue: 'Total Receivable' })}
              value={`${fmtNum(totalReceivable, 2)} ${currency}`.trim()}
              color="gray"
              icon={TrendingUp}
            />
            <KPICard
              label={t('reporting.overdue_total', { defaultValue: 'Total Overdue' })}
              value={`${fmtNum(totalOverdue, 2)} ${currency}`.trim()}
              color={totalOverdue !== null && totalOverdue > 0 ? 'red' : 'green'}
              icon={AlertTriangle}
            />
            <KPICard
              label={t('reporting.cash_flow_net', { defaultValue: 'Net Cash Flow' })}
              value={`${fmtNum(cashFlowNet, 2)} ${currency}`.trim()}
              color={cashFlowNet === null ? 'gray' : cashFlowNet >= 0 ? 'green' : 'red'}
              icon={cashFlowNet !== null && cashFlowNet < 0 ? TrendingDown : TrendingUp}
            />
          </div>

          {/* Budget and committed — replaces the invoices_due_* cards, which
              had no source on the finance dashboard endpoint. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <KPICard
              label={t('reporting.budget_total', { defaultValue: 'Total Budget' })}
              value={`${fmtNum(totalBudgetRevised, 2)} ${currency}`.trim()}
              color="gray"
              icon={Wallet}
            />
            <KPICard
              label={t('reporting.committed', { defaultValue: 'Committed' })}
              value={`${fmtNum(totalCommitted, 2)} ${currency}`.trim()}
              color="gray"
              icon={ClipboardList}
            />
            <KPICard
              label={t('reporting.actual_spend', { defaultValue: 'Actual Spend' })}
              value={`${fmtNum(totalActual, 2)} ${currency}`.trim()}
              color="gray"
              icon={Wallet}
            />
            <KPICard
              label={t('reporting.budget_consumed', { defaultValue: 'Budget Consumed' })}
              value={budgetConsumedPct !== null ? `${budgetConsumedPct.toFixed(1)}%` : 'N/A'}
              color={budgetColor}
              icon={BarChart3}
            />
          </div>
        </>
      ) : (
        <Card>
          <CardContent>
            <p className="text-sm text-content-secondary">
              {t('reporting.no_finance_data', { defaultValue: 'No finance data available for this project. Create invoices and budgets first.' })}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Procurement summary */}
      {procurementStats && (
        <Card>
          <CardContent>
            <h3 className="mb-3 text-sm font-semibold text-content-primary">
              {t('reporting.procurement_summary', { defaultValue: 'Procurement Summary' })}
            </h3>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatBlock label={t('reporting.total_pos', { defaultValue: 'Total POs' })} value={procurementStats.total_pos} />
              <StatBlock
                label={t('reporting.committed', { defaultValue: 'Committed' })}
                value={`${fmtNum(procurementStats.total_committed, 2)}${procurementCurrency ? ` ${procurementCurrency}` : ''}`}
              />
              <StatBlock
                label={t('reporting.pending_delivery', { defaultValue: 'Pending Delivery' })}
                value={procurementStats.pending_delivery}
                color={procurementStats.pending_delivery > 0 ? 'amber' : 'emerald'}
              />
              <StatBlock
                label={t('reporting.approved_pos', { defaultValue: 'Approved' })}
                value={procurementStats.by_status?.approved ?? 0}
                color="emerald"
              />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ── Shared sub-components ─────────────────────────────────────────────────── */

type StatColor = 'emerald' | 'amber' | 'red' | 'blue';

// Static lookup — Tailwind only ships classes it finds as literal
// strings in source. Interpolating `text-${color}-600` would let the
// production purge drop every colored stat (they appear nowhere literal),
// so the red/amber/green signalling silently disappeared in builds.
const STAT_COLOR_CLASSES: Record<StatColor, string> = {
  emerald: 'text-emerald-600 dark:text-emerald-400',
  amber: 'text-amber-600 dark:text-amber-400',
  red: 'text-red-600 dark:text-red-400',
  blue: 'text-blue-600 dark:text-blue-400',
};

function StatBlock({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: StatColor;
}) {
  const textColor = color ? STAT_COLOR_CLASSES[color] : 'text-content-primary';
  return (
    <div>
      <p className="text-xs font-medium text-content-secondary">{label}</p>
      <p className={`text-xl font-semibold ${textColor}`}>{value}</p>
    </div>
  );
}

function PromptCard({ message }: { message: string }) {
  return (
    <Card>
      <CardContent>
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <BarChart3 size={40} className="mb-3 text-content-tertiary" />
          <p className="text-sm text-content-secondary">{message}</p>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Reports tab — templates + generated reports list ─────────────────────── */

function ReportsTab({ project }: { project?: Project }) {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<ReportTemplate[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(true);
  const [loadingReports, setLoadingReports] = useState(true);
  const [templatesError, setTemplatesError] = useState(false);
  const [reportsError, setReportsError] = useState(false);
  const [creating, setCreating] = useState<string | null>(null);
  // W23 P0 (#252): viewer state — opens the rendered HTML from the
  // /reports/{id}/content endpoint in a modal so users can finally
  // read the generated body instead of staring at a row that does nothing.
  const [viewing, setViewing] = useState<GeneratedReport | null>(null);

  const projectId = project?.id;

  const fetchTemplates = useCallback(async () => {
    setLoadingTemplates(true);
    setTemplatesError(false);
    try {
      const data = await apiGet<ReportTemplate[]>('/v1/reporting/templates/');
      setTemplates(data);
    } catch {
      setTemplates([]);
      setTemplatesError(true);
    } finally {
      setLoadingTemplates(false);
    }
  }, []);

  const fetchReports = useCallback(async () => {
    if (!projectId) {
      setReports([]);
      setLoadingReports(false);
      return;
    }
    setLoadingReports(true);
    setReportsError(false);
    try {
      const data = await apiGet<GeneratedReport[]>(`/v1/reporting/reports/?project_id=${projectId}`);
      setReports(data);
    } catch {
      setReports([]);
      setReportsError(true);
    } finally {
      setLoadingReports(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  const handleGenerate = async (template: ReportTemplate) => {
    if (!projectId) return;
    setCreating(template.id);
    try {
      await apiPost('/v1/reporting/generate/', {
        project_id: projectId,
        template_id: template.id,
        report_type: template.report_type,
        title: `${template.name} — ${new Date().toLocaleDateString()}`,
        format: 'pdf',
      });
      await fetchReports();
    } catch {
      setReportsError(true);
    } finally {
      setCreating(null);
    }
  };

  if (!project) {
    return <PromptCard message={t('reporting.select_project_prompt_reports', { defaultValue: 'Select a project to view reports' })} />;
  }

  return (
    <div className="space-y-6">
      {/* Templates */}
      <Card>
        <CardContent>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-content-primary">
              {t('reporting.templates_title', { defaultValue: 'Report templates' })}
            </h3>
          </div>

          {loadingTemplates ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full rounded-lg" />
              <Skeleton className="h-12 w-full rounded-lg" />
              <Skeleton className="h-12 w-full rounded-lg" />
            </div>
          ) : templatesError ? (
            <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
              <AlertTriangle size={16} className="shrink-0" />
              <span>{t('reporting.templates_load_failed', { defaultValue: 'Could not load report templates.' })}</span>
              <button onClick={fetchTemplates} className="ml-2 underline">
                {t('common.retry', { defaultValue: 'Retry' })}
              </button>
            </div>
          ) : templates.length === 0 ? (
            <EmptyState
              icon={<FileText size={24} />}
              title={t('reporting.no_templates_title', { defaultValue: 'No report templates yet' })}
              description={t('reporting.no_templates_desc', { defaultValue: 'System templates will appear here as the platform seeds them, or your admin can add custom templates.' })}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-light bg-surface-secondary text-left text-xs font-medium text-content-secondary">
                    <th className="px-4 py-3">{t('reporting.template_name', { defaultValue: 'Name' })}</th>
                    <th className="px-4 py-3">{t('reporting.template_type', { defaultValue: 'Type' })}</th>
                    <th className="px-4 py-3">{t('reporting.template_scope', { defaultValue: 'Scope' })}</th>
                    <th className="px-4 py-3">{t('reporting.template_schedule', { defaultValue: 'Schedule' })}</th>
                    <th className="px-4 py-3 text-right">{t('reporting.actions', { defaultValue: 'Actions' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {templates.map((tpl) => (
                    <tr key={tpl.id} className="border-b border-border-light last:border-0 hover:bg-surface-secondary/50">
                      <td className="px-4 py-3 font-medium text-content-primary">{tpl.name}</td>
                      <td className="px-4 py-3 text-content-secondary">{humanizeReportType(tpl.report_type)}</td>
                      <td className="px-4 py-3 text-content-secondary">
                        {tpl.is_system
                          ? t('reporting.scope_system', { defaultValue: 'System' })
                          : t('reporting.scope_custom', { defaultValue: 'Custom' })}
                      </td>
                      <td className="px-4 py-3 text-content-secondary">
                        {tpl.is_scheduled && tpl.schedule_cron
                          ? tpl.schedule_cron
                          : t('reporting.schedule_none', { defaultValue: '—' })}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleGenerate(tpl)}
                          disabled={creating === tpl.id}
                        >
                          {creating === tpl.id ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            t('reporting.generate_now', { defaultValue: 'Generate' })
                          )}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Generated reports */}
      <Card>
        <CardContent>
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-content-primary">
              {t('reporting.generated_reports_title', { defaultValue: 'Generated reports' })}
            </h3>
          </div>

          {loadingReports ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full rounded-lg" />
              <Skeleton className="h-12 w-full rounded-lg" />
            </div>
          ) : reportsError ? (
            <div role="alert" className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
              <AlertTriangle size={16} className="shrink-0" />
              <span>{t('reporting.reports_load_failed', { defaultValue: 'Could not load generated reports.' })}</span>
              <button onClick={fetchReports} className="ml-2 underline">
                {t('common.retry', { defaultValue: 'Retry' })}
              </button>
            </div>
          ) : reports.length === 0 ? (
            <EmptyState
              icon={<FileText size={24} />}
              title={t('reporting.no_reports_title', { defaultValue: 'No reports yet' })}
              description={t('reporting.no_reports_desc', { defaultValue: 'Generate your first report from a template above to get started.' })}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-light bg-surface-secondary text-left text-xs font-medium text-content-secondary">
                    <th className="px-4 py-3">{t('reporting.report_title', { defaultValue: 'Title' })}</th>
                    <th className="px-4 py-3">{t('reporting.report_type', { defaultValue: 'Type' })}</th>
                    <th className="px-4 py-3">{t('reporting.report_format', { defaultValue: 'Format' })}</th>
                    <th className="px-4 py-3">{t('reporting.report_generated_at', { defaultValue: 'Generated' })}</th>
                    <th className="px-4 py-3 text-right">{t('reporting.actions', { defaultValue: 'Actions' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => {
                    const generated = r.generated_at || r.created_at;
                    const ts = generated ? new Date(generated).toLocaleString() : '—';
                    return (
                      <tr key={r.id} className="border-b border-border-light last:border-0 hover:bg-surface-secondary/50">
                        <td className="px-4 py-3 font-medium text-content-primary">{r.title}</td>
                        <td className="px-4 py-3 text-content-secondary">{humanizeReportType(r.report_type)}</td>
                        <td className="px-4 py-3 text-content-secondary uppercase">{r.format}</td>
                        <td className="px-4 py-3 text-content-secondary">{ts}</td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => setViewing(r)}
                            aria-label={t('reporting.view_report_aria', {
                              defaultValue: 'View report: {{title}}',
                              title: r.title,
                            })}
                          >
                            <Eye size={14} className="mr-1" />
                            {t('reporting.view', { defaultValue: 'View' })}
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {viewing && (
        <ReportViewerModal report={viewing} onClose={() => setViewing(null)} />
      )}
    </div>
  );
}

/* ── Report viewer modal — renders the HTML body inside a sandboxed iframe ─ */

/**
 * Modal viewer for a generated report.
 *
 * Fetches the rendered HTML from ``/v1/reporting/reports/{id}/content`` (the
 * endpoint added in the W23 P0 backend fix for #252) and pipes the body into
 * a sandboxed ``<iframe srcDoc>``. Sandboxing is mandatory — the renderer
 * already HTML-escapes user-supplied values but defence-in-depth keeps a
 * future renderer regression from turning into a stored-XSS hole.
 *
 * Loading / 410-not-yet-rendered / 404 / generic-error states all surface
 * distinct messages so the user knows whether to wait, regenerate, or
 * complain to support.
 */
function ReportViewerModal({
  report,
  onClose,
}: {
  report: GeneratedReport;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [html, setHtml] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorKind, setErrorKind] = useState<'not_rendered' | 'not_found' | 'network' | null>(null);

  // Fetch the rendered HTML body. We bypass apiGet because it always parses
  // JSON — this endpoint returns text/html.
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    (async () => {
      setLoading(true);
      setErrorKind(null);
      try {
        const token = getAuthToken();
        const res = await fetch(
          `${API_BASE}/v1/reporting/reports/${report.id}/content`,
          {
            method: 'GET',
            headers: {
              ...(token ? { Authorization: `Bearer ${token}` } : {}),
              Accept: 'text/html',
              'X-DDC-Client': 'OE/1.0',
            },
            signal: controller.signal,
          },
        );
        if (cancelled) return;
        if (res.status === 410) {
          setErrorKind('not_rendered');
          setLoading(false);
          return;
        }
        if (res.status === 404) {
          setErrorKind('not_found');
          setLoading(false);
          return;
        }
        if (!res.ok) {
          setErrorKind('network');
          setLoading(false);
          return;
        }
        const body = await res.text();
        if (!cancelled) {
          setHtml(body);
          setLoading(false);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError) {
          setErrorKind('network');
        } else if (err instanceof DOMException && err.name === 'AbortError') {
          // Component unmounted — silently ignore.
          return;
        } else {
          setErrorKind('network');
        }
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [report.id]);

  // Escape key closes the modal — matches the rest of the app's modals.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-viewer-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8"
    >
      <button
        type="button"
        aria-label={t('common.close', { defaultValue: 'Close' })}
        onClick={onClose}
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-in"
      />
      <div className="relative flex h-full max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-xl border border-border-light bg-surface-primary shadow-2xl animate-scale-in">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 border-b border-border-light px-5 py-3">
          <div className="min-w-0">
            <h2
              id="report-viewer-title"
              className="truncate text-base font-semibold text-content-primary"
            >
              {report.title}
            </h2>
            <p className="truncate text-xs text-content-secondary">
              {humanizeReportType(report.report_type)} · {report.format?.toUpperCase()}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                // Open the same URL in a fresh tab so users can use the
                // browser's native Print / Save-As-PDF flow.
                const token = getAuthToken();
                // We can't easily send Authorization on a window.open(),
                // but the auth cookie (when present) covers the case.
                // For Bearer-only auth we copy the URL to clipboard as
                // a graceful fallback.
                const url = `${API_BASE}/v1/reporting/reports/${report.id}/content`;
                if (token) {
                  // Trigger a fetch + blob URL so we can carry the Authorization.
                  fetch(url, {
                    headers: { Authorization: `Bearer ${token}` },
                  })
                    .then((r) => (r.ok ? r.blob() : Promise.reject(r)))
                    .then((blob) => {
                      const objUrl = URL.createObjectURL(blob);
                      window.open(objUrl, '_blank', 'noopener,noreferrer');
                      // Revoke after a delay so the new tab has time to load.
                      setTimeout(() => URL.revokeObjectURL(objUrl), 30_000);
                    })
                    .catch(() => {
                      window.open(url, '_blank', 'noopener,noreferrer');
                    });
                } else {
                  window.open(url, '_blank', 'noopener,noreferrer');
                }
              }}
              disabled={loading || !!errorKind}
              aria-label={t('reporting.open_in_new_tab', { defaultValue: 'Open in new tab' })}
            >
              {t('reporting.open_in_new_tab', { defaultValue: 'Open in new tab' })}
            </Button>
            <button
              type="button"
              onClick={onClose}
              aria-label={t('common.close', { defaultValue: 'Close' })}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary transition-colors hover:bg-surface-secondary hover:text-content-primary"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-hidden bg-surface-secondary">
          {loading && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-content-secondary">
              <Loader2 size={28} className="animate-spin" />
              <p className="text-sm">
                {t('reporting.loading_report', { defaultValue: 'Loading report…' })}
              </p>
            </div>
          )}

          {!loading && errorKind === 'not_rendered' && (
            <div
              role="alert"
              className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
            >
              <Clock size={36} className="text-amber-500" />
              <p className="max-w-md text-sm text-content-secondary">
                {t('reporting.report_not_rendered', {
                  defaultValue:
                    'This report has been queued but no body has been rendered yet. Re-generate it from the templates list above.',
                })}
              </p>
            </div>
          )}

          {!loading && errorKind === 'not_found' && (
            <div
              role="alert"
              className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
            >
              <AlertTriangle size={36} className="text-red-500" />
              <p className="max-w-md text-sm text-content-secondary">
                {t('reporting.report_not_found', {
                  defaultValue:
                    'This report was not found. It may have been deleted by another user.',
                })}
              </p>
            </div>
          )}

          {!loading && errorKind === 'network' && (
            <div
              role="alert"
              className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
            >
              <AlertTriangle size={36} className="text-red-500" />
              <p className="max-w-md text-sm text-content-secondary">
                {t('reporting.report_load_failed', {
                  defaultValue:
                    'Could not load the report body. Check your connection and try again.',
                })}
              </p>
            </div>
          )}

          {!loading && !errorKind && html != null && (
            <iframe
              // Sandbox: forbid scripts, top-navigation, popups, form submission.
              // The renderer already escapes user input but defence-in-depth
              // matters — a future regression should NOT turn into XSS.
              sandbox=""
              srcDoc={html}
              title={report.title}
              className="h-full w-full border-0 bg-white"
            />
          )}
        </div>
      </div>
    </div>
  );
}
