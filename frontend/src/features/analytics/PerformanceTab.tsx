// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Analytics -> Performance: pick projects, pick one KPI, compare what was
// actually achieved. Standalone on purpose - it needs no open estimate - and
// read from the same benchmark endpoint an estimating screen can use later.
//
// Three rules from the backend are visible here and must stay visible: a
// missing value reads "Unavailable" with its reason and is never drawn as 0,
// each unit or currency is its own block, and the weighted benchmark (a sum
// over a sum) is shown beside the median rather than instead of it.

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Download, RefreshCw, Search, Gauge } from 'lucide-react';
import { Badge, Button, Card, EmptyState, Skeleton } from '@/shared/ui';
import { fmtNumber, fmtPercent } from '@/shared/lib/formatters';
import { compareNames } from '@/shared/lib/collator';
import {
  NULL_GROUP_KEY,
  buildPerformanceCsv,
  downloadCsv,
  fetchPerformanceBenchmark,
  fetchPerformancePresets,
  rangeBand,
  tableRows,
  toNumber,
  type Decimalish,
  type PerformanceGroup,
} from './performance';

export interface PerformanceTabProject {
  id: string;
  name: string;
}

const DEFAULT_KPI = 'labour_hours_per_installed_unit';

/** Up to four significant decimals: productivity ratios are small numbers. */
function fmtValue(value: Decimalish | undefined): string | null {
  const n = toNumber(value);
  if (n === null) return null;
  return fmtNumber(n, Math.abs(n) >= 100 ? 0 : Math.abs(n) >= 1 ? 2 : 4);
}

export function PerformanceTab({ projects }: { projects: PerformanceTabProject[] }) {
  const { t } = useTranslation();
  const [kpi, setKpi] = useState(DEFAULT_KPI);
  const [selected, setSelected] = useState<string[]>([]);
  const [filter, setFilter] = useState('');

  const presetsQuery = useQuery({
    queryKey: ['analytics', 'performance', 'presets'],
    queryFn: fetchPerformancePresets,
    staleTime: 5 * 60_000,
  });

  const projectIds = useMemo(() => [...selected].sort(), [selected]);
  const benchmarkQuery = useQuery({
    queryKey: ['analytics', 'performance', 'benchmark', kpi, projectIds],
    queryFn: () => fetchPerformanceBenchmark({ kpi, project_ids: projectIds }),
    enabled: Boolean(kpi),
  });

  const sortedProjects = useMemo(
    () => [...projects].sort((a, b) => compareNames(a.name, b.name)),
    [projects],
  );
  const visibleProjects = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? sortedProjects.filter((p) => p.name.toLowerCase().includes(q)) : sortedProjects;
  }, [sortedProjects, filter]);

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  const kpiLabel = useCallback(
    (key: string) => t(`analytics.perf.kpi.${key}`, { defaultValue: key }),
    [t],
  );
  const reasonLabel = useCallback(
    (reason: string | null) =>
      t(`analytics.perf.reason.${reason ?? 'no_data'}`, {
        defaultValue: t('analytics.perf.unavailable', { defaultValue: 'Unavailable' }),
      }),
    [t],
  );
  const groupLabel = useCallback(
    (group: PerformanceGroup) => {
      const parts = Object.entries(group.dimensions).map(([name, value]) =>
        value === null || value === NULL_GROUP_KEY || value === ''
          ? t(`analytics.perf.dim_unset.${name}`, {
              defaultValue: t('analytics.perf.dim_unset_generic', { defaultValue: 'not set' }),
            })
          : value,
      );
      return parts.length ? parts.join(' / ') : t('analytics.perf.no_dimension', { defaultValue: 'All rows' });
    },
    [t],
  );

  const data = benchmarkQuery.data;
  const handleExport = useCallback(() => {
    if (!data || !data.groups.length) return;
    const csv = buildPerformanceCsv(data, {
      group: t('analytics.perf.col_group', { defaultValue: 'Group' }),
      project: t('analytics.perf.col_project', { defaultValue: 'Project' }),
      value: t('analytics.perf.col_value', { defaultValue: 'Value' }),
      numerator: t('analytics.perf.col_numerator', { defaultValue: 'Numerator' }),
      denominator: t('analytics.perf.col_denominator', { defaultValue: 'Denominator' }),
      records: t('analytics.perf.col_records', { defaultValue: 'Records' }),
      status: t('analytics.perf.col_status', { defaultValue: 'Status' }),
      weighted: t('analytics.perf.weighted', { defaultValue: 'Weighted benchmark' }),
      median: t('analytics.perf.median', { defaultValue: 'Median' }),
      p25: t('analytics.perf.p25', { defaultValue: 'P25' }),
      p75: t('analytics.perf.p75', { defaultValue: 'P75' }),
      unavailable: reasonLabel,
      groupLabel,
    });
    downloadCsv(csv, `performance_${kpi}.csv`);
  }, [data, groupLabel, kpi, reasonLabel, t]);

  const presetKeys = presetsQuery.data?.map((p) => p.key) ?? [DEFAULT_KPI];

  return (
    <div className="space-y-4" data-testid="analytics-performance">
      <Card>
        <div className="space-y-3">
          <div>
            <h2 className="text-lg font-semibold text-content-primary">
              {t('analytics.perf.title', { defaultValue: 'Historical performance' })}
            </h2>
            <p className="mt-1 text-sm text-content-secondary">
              {t('analytics.perf.intro', {
                defaultValue:
                  'Pick projects and one KPI to compare what was actually achieved. Ratios are a sum over a sum, units are never mixed, and missing data is shown as unavailable instead of zero.',
              })}
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-xs text-content-secondary">
              {t('analytics.perf.kpi_label', { defaultValue: 'KPI' })}
              <select
                value={kpi}
                onChange={(e) => setKpi(e.target.value)}
                className="h-8 min-w-[16rem] rounded-lg border border-border-light bg-surface-primary px-2 text-xs text-content-primary focus:outline-none focus:ring-1 focus:ring-oe-blue"
                data-testid="analytics-performance-kpi"
              >
                {presetKeys.map((key) => (
                  <option key={key} value={key}>
                    {kpiLabel(key)}
                  </option>
                ))}
              </select>
            </label>
            <Button
              variant="secondary"
              size="sm"
              icon={<Download size={14} />}
              onClick={handleExport}
              disabled={!data || !data.groups.length}
            >
              {t('analytics.perf.export_csv', { defaultValue: 'Export CSV' })}
            </Button>
          </div>
          <div>
            <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-content-secondary">
              <span>{t('analytics.perf.projects_label', { defaultValue: 'Projects' })}</span>
              <Badge variant="neutral" size="sm">
                {selected.length
                  ? t('analytics.perf.selected_projects', { defaultValue: '{{count}} selected', count: selected.length })
                  : t('analytics.perf.all_projects', { defaultValue: 'All projects ({{count}})', count: projects.length })}
              </Badge>
              <button
                type="button"
                className="text-oe-blue hover:underline disabled:opacity-40"
                onClick={() => setSelected([])}
                disabled={!selected.length}
              >
                {t('analytics.perf.clear_selection', { defaultValue: 'Use all projects' })}
              </button>
              <span className="relative ms-auto">
                <Search size={12} className="pointer-events-none absolute start-2 top-1/2 -translate-y-1/2 text-content-tertiary" />
                <input
                  type="text"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder={t('analytics.search_placeholder', { defaultValue: 'Search projects...' })}
                  aria-label={t('analytics.search_placeholder', { defaultValue: 'Search projects...' })}
                  className="h-7 w-44 rounded-lg border border-border-light bg-surface-primary ps-6 pe-2 text-xs focus:outline-none focus:ring-1 focus:ring-oe-blue"
                />
              </span>
            </div>
            <div className="max-h-40 overflow-y-auto rounded-lg border border-border-light p-2">
              <div className="grid grid-cols-1 gap-1 sm:grid-cols-2 lg:grid-cols-3">
                {visibleProjects.map((p) => (
                  <label key={p.id} className="flex min-w-0 items-center gap-2 text-xs text-content-primary">
                    <input type="checkbox" checked={selected.includes(p.id)} onChange={() => toggle(p.id)} />
                    <span className="truncate">{p.name}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {benchmarkQuery.isLoading ? (
        <Card>
          <Skeleton className="mb-3 h-6 w-48" />
          <Skeleton className="h-24 w-full" />
        </Card>
      ) : benchmarkQuery.isError ? (
        <EmptyState
          icon={<Gauge size={28} />}
          title={t('analytics.perf.error', { defaultValue: 'Could not load the benchmark' })}
          action={
            <Button variant="primary" icon={<RefreshCw size={14} />} onClick={() => benchmarkQuery.refetch()}>
              {t('analytics.retry', { defaultValue: 'Retry' })}
            </Button>
          }
        />
      ) : !data || data.groups.length === 0 ? (
        <EmptyState
          icon={<Gauge size={28} />}
          title={t('analytics.perf.empty_title', { defaultValue: 'No data for this KPI yet' })}
          description={t('analytics.perf.empty', {
            defaultValue:
              'None of the selected projects has data for this KPI. Productivity KPIs need approved timesheet hours booked against bill positions and reported progress.',
          })}
        />
      ) : (
        data.groups.map((group) => (
          <PerformanceGroupCard
            key={group.key}
            group={group}
            title={`${kpiLabel(kpi)} · ${groupLabel(group)}`}
            selectedCount={data.projects_selected}
            projects={data.projects}
            reasonLabel={reasonLabel}
          />
        ))
      )}
    </div>
  );
}

function PerformanceGroupCard({
  group,
  title,
  selectedCount,
  projects,
  reasonLabel,
}: {
  group: PerformanceGroup;
  title: string;
  selectedCount: number;
  projects: { project_id: string; name: string; currency: string }[];
  reasonLabel: (reason: string | null) => string;
}) {
  const { t } = useTranslation();
  const b = group.benchmark;
  const unavailable = t('analytics.perf.unavailable', { defaultValue: 'Unavailable' });
  const weighted = fmtValue(b.weighted);
  const median = fmtValue(b.median);
  const p25 = fmtValue(b.p25);
  const p75 = fmtValue(b.p75);
  const coverage = toNumber(group.coverage);
  const rows = tableRows(group, projects);
  const min = toNumber(b.min);
  const max = toNumber(b.max);

  return (
    <Card padding="none">
      <div className="border-b border-border-light px-6 py-4">
        <h3 className="text-base font-semibold text-content-primary">{title}</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <Figure
            label={t('analytics.perf.weighted', { defaultValue: 'Weighted benchmark' })}
            value={weighted ?? `${unavailable} (${reasonLabel(b.weighted_unavailable_reason)})`}
            hint={t('analytics.perf.weighted_hint', { defaultValue: 'Sum over sum across the projects with a value' })}
          />
          <Figure label={t('analytics.perf.median', { defaultValue: 'Median' })} value={median ?? unavailable} />
          <Figure
            label={t('analytics.perf.range', { defaultValue: 'Normal range (P25 - P75)' })}
            value={p25 !== null && p75 !== null ? `${p25} - ${p75}` : unavailable}
          />
          <Figure
            label={t('analytics.perf.evidence', { defaultValue: 'Evidence' })}
            value={t('analytics.perf.evidence_value', {
              defaultValue: '{{projects}} projects, {{records}} records',
              projects: group.evidence.projects_with_value,
              records: group.evidence.records,
            })}
            hint={t('analytics.perf.coverage', {
              defaultValue: 'Coverage {{pct}}: {{count}} of {{selected}} projects have a value',
              pct: coverage === null ? '-' : fmtPercent(coverage * 100),
              count: group.evidence.projects_with_value,
              selected: selectedCount,
            })}
          />
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-light text-left text-xs text-content-tertiary">
              <th className="px-6 py-2 font-medium">{t('analytics.perf.col_project', { defaultValue: 'Project' })}</th>
              <th className="px-3 py-2 text-right font-medium">{t('analytics.perf.col_value', { defaultValue: 'Value' })}</th>
              <th className="px-3 py-2 font-medium">{t('analytics.perf.col_range', { defaultValue: 'Against the range' })}</th>
              <th className="px-3 py-2 text-right font-medium">{t('analytics.perf.col_records', { defaultValue: 'Records' })}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ projectId, name, row }) => {
              const value = fmtValue(row?.value);
              const band = rangeBand(row?.value, b.p25, b.p75);
              const n = toNumber(row?.value);
              const pos = n !== null && min !== null && max !== null && max > min ? ((n - min) / (max - min)) * 100 : 50;
              return (
                <tr key={projectId} className="border-b border-border-light last:border-0">
                  <td className="max-w-[18rem] truncate px-6 py-2 text-content-primary">{name}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {value ?? (
                      <span className="text-content-tertiary" title={reasonLabel(row?.unavailable_reason ?? null)}>
                        {unavailable}
                        <span className="ms-1 text-2xs">({reasonLabel(row?.unavailable_reason ?? null)})</span>
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {band ? (
                      <div className="flex items-center gap-2">
                        <div className="relative h-1.5 w-24 rounded-full bg-surface-tertiary" aria-hidden="true">
                          <span
                            className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-oe-blue"
                            style={{ left: `${pos}%` }}
                          />
                        </div>
                        <Badge variant={band === 'within' ? 'success' : 'warning'} size="sm">
                          {t(`analytics.perf.band_${band}`, {
                            defaultValue: band === 'below' ? 'Below P25' : band === 'above' ? 'Above P75' : 'Within range',
                          })}
                        </Badge>
                      </div>
                    ) : (
                      <span className="text-content-tertiary">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-content-secondary">{row?.records ?? 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Figure({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <div className="text-content-tertiary">{label}</div>
      <div className="truncate text-sm font-semibold tabular-nums text-content-primary" title={value}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-2xs text-content-tertiary">{hint}</div>}
    </div>
  );
}
