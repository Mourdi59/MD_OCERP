import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertOctagon, AlertTriangle, Gauge, Loader2, RefreshCw } from 'lucide-react';

import { Breadcrumb, Button, Card, EmptyState } from '@/shared/ui';
import { useProjectContextStore } from '@/stores/useProjectContextStore';

import type { ControlsKPI } from './api';
import { useControlsSnapshot } from './api';
import { ControlsTile } from './ControlsTile';
import { DrillDrawer } from './DrillDrawer';

/**
 * Executive cross-module controls dashboard (connective-tissue feature 09).
 *
 * One screen, six domains (Cost, Schedule, Quality, Safety, Risk, Changes),
 * every number status-banded and traceable back to the owning module via
 * the drill drawer. Reads the single consolidated /snapshot endpoint.
 *
 * Scope follows the global project context (top app bar): a project is
 * selected → scope to it; nothing selected → portfolio (all projects).
 */
export function ProjectControlsPage() {
  const { t } = useTranslation();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const [drillKpi, setDrillKpi] = useState<ControlsKPI | null>(null);

  const projectId = activeProjectId ?? null;

  const snapshotQ = useControlsSnapshot(projectId);
  const snapshot = snapshotQ.data;

  const alerts = snapshot?.alerts ?? [];
  const criticalCount = useMemo(
    () => alerts.filter((a) => a.severity === 'critical').length,
    [alerts],
  );

  // Honest hero stat chips — every number is derived from the snapshot the
  // page already loads (no fabricated figures). Flattening the KPI groups lets
  // us surface coverage + health at a glance inside the hero band.
  const allKpis = useMemo(
    () => (snapshot?.groups ?? []).flatMap((g) => g.kpis),
    [snapshot],
  );
  const domainCount = snapshot?.groups?.length ?? 0;
  const kpiCount = allKpis.length;
  const greenCount = useMemo(
    () => allKpis.filter((k) => k.status === 'green').length,
    [allKpis],
  );
  const redCount = useMemo(
    () => allKpis.filter((k) => k.status === 'red').length,
    [allKpis],
  );

  return (
    <div className="space-y-5">
      {/* Tinted hero header — module-accent gradient band */}
      <div className="rounded-2xl border border-border-light bg-gradient-to-r from-oe-blue/[0.06] via-transparent to-transparent px-5 py-4 dark:from-oe-blue/[0.12]">
        <Breadcrumb
          items={[
            { label: t('nav.group_analytics', { defaultValue: 'Analytics' }) },
            {
              label: t('nav.project_controls', {
                defaultValue: 'Project Controls',
              }),
            },
          ]}
        />

        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2.5">
            <Gauge className="mt-0.5 h-6 w-6 shrink-0 text-accent" />
            <p className="text-sm text-content-secondary">
              {t('controls.subtitle', {
                defaultValue:
                  'Cost, schedule, quality, safety, risk and change KPIs in one view. Click a tile to trace it back to the source records.',
              })}
              <span className="ml-1.5 rounded-full bg-surface-tertiary px-2 py-0.5 text-xs font-medium text-content-tertiary">
                {projectId
                  ? t('controls.scope_project', { defaultValue: 'This project' })
                  : t('controls.portfolio', { defaultValue: 'Portfolio' })}
              </span>
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => snapshotQ.refetch()}
              disabled={snapshotQ.isFetching}
              aria-label={t('common.refresh', { defaultValue: 'Refresh' })}
            >
              <RefreshCw
                className={snapshotQ.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
              />
            </Button>
          </div>
        </div>

        {/* Inline stat chips — key numbers the page already computes */}
        {kpiCount > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-light bg-surface-primary/70 px-3 py-1 text-xs backdrop-blur">
              <span className="text-content-tertiary">
                {t('controls.chip_domains', { defaultValue: 'Domains' })}
              </span>
              <span className="font-bold text-content-primary">{domainCount}</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-light bg-surface-primary/70 px-3 py-1 text-xs backdrop-blur">
              <span className="text-content-tertiary">
                {t('controls.chip_kpis', { defaultValue: 'KPIs tracked' })}
              </span>
              <span className="font-bold text-content-primary">{kpiCount}</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-light bg-surface-primary/70 px-3 py-1 text-xs backdrop-blur">
              <span className="text-content-tertiary">
                {t('controls.chip_on_track', { defaultValue: 'On track' })}
              </span>
              <span className="font-bold text-semantic-success">{greenCount}</span>
            </span>
            {redCount > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border-light bg-surface-primary/70 px-3 py-1 text-xs backdrop-blur">
                <span className="text-content-tertiary">
                  {t('controls.chip_critical', { defaultValue: 'Critical' })}
                </span>
                <span className="font-bold text-semantic-error">{redCount}</span>
              </span>
            )}
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border-light bg-surface-primary/70 px-3 py-1 text-xs backdrop-blur">
              <span className="text-content-tertiary">
                {t('controls.chip_currency', { defaultValue: 'Currency' })}
              </span>
              <span className="font-bold text-content-primary">
                {snapshot?.multi_currency
                  ? t('controls.currency_mixed', { defaultValue: 'Mixed' })
                  : (snapshot?.currency ?? '—')}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Alerts banner */}
      {alerts.length > 0 && (
        <div
          className={`flex items-start gap-2 rounded-lg border p-3 text-sm ${
            criticalCount > 0
              ? 'border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200'
              : 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
          }`}
        >
          {criticalCount > 0 ? (
            <AlertOctagon className="mt-0.5 h-4 w-4 shrink-0" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          <div className="flex flex-col gap-0.5">
            <span className="font-medium">
              {t('controls.alerts_heading', {
                defaultValue: '{{n}} KPIs need attention',
                n: alerts.length,
              })}
            </span>
            {alerts.slice(0, 5).map((a) => (
              <span key={a.kpi_code}>{a.message}</span>
            ))}
          </div>
        </div>
      )}

      {/* Spine */}
      {snapshotQ.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-content-tertiary">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t('common.loading', { defaultValue: 'Loading…' })}
        </div>
      ) : snapshotQ.isError ? (
        <EmptyState
          title={t('controls.load_error', {
            defaultValue: 'Could not load the controls snapshot',
          })}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {(snapshot?.groups ?? []).map((group) => (
            <Card key={group.domain} className="p-4">
              <h2 className="mb-3 text-sm font-semibold text-content-secondary">
                {t(`controls.domain.${group.domain}`, {
                  defaultValue: group.label,
                })}
              </h2>
              <div className="grid grid-cols-2 gap-2.5">
                {group.kpis.map((kpi) => (
                  <ControlsTile key={kpi.code} kpi={kpi} onDrill={setDrillKpi} />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      <DrillDrawer
        kpi={drillKpi}
        projectId={projectId}
        open={drillKpi !== null}
        onClose={() => setDrillKpi(null)}
      />
    </div>
  );
}
