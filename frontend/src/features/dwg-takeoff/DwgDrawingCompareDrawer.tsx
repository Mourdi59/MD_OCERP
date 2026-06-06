/**
 * DwgDrawingCompareDrawer — revision compare with cost delta (Item 17).
 *
 * Right-side slide-over that diffs two parsed versions of the same DWG/DXF
 * drawing. Three tabs:
 *   - Entities:    per-layer entity-count changes (added / removed / count).
 *   - Annotations: per-annotation changes with a money cost impact for any
 *                  annotation linked to a BOQ position whose value changed.
 *   - Summary:     traffic-light tallies + net cost impact.
 *
 * Controls:
 *   - Two version selectors (baseline "before" + target "after").
 *   - "Hide unchanged" toggle to focus on real changes.
 *   - "Onion-skin overlay" toggle + opacity slider — a visual blend hint
 *     surfaced back to the page via ``onOverlayChange`` so the canvas can
 *     dim the older revision under the newer one.
 *
 * All money is rendered with the shared MoneyDisplay (green/red via
 * ``colorize``) and never blends currencies — the backend returns the
 * impact already expressed in the project base currency.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import {
  GitCompare,
  Loader2,
  ArrowRight,
  Layers,
  MessageSquare,
  BarChart3,
  Eye,
  FilePlus2,
} from 'lucide-react';

import { SideDrawer, MoneyDisplay, Badge } from '@/shared/ui';
import { useToastStore } from '@/stores/useToastStore';
import {
  fetchDrawingVersions,
  compareDrawings,
  createVariationFromDiff,
  type DwgDrawingVersion,
  type DwgDrawingDiffResponse,
  type DwgEntityDiffRow,
  type DwgAnnotationDiffRow,
} from './api';

type CompareTab = 'entities' | 'annotations' | 'summary';

export interface DwgCompareOverlayState {
  /** Whether the onion-skin overlay hint is active. */
  enabled: boolean;
  /** 0..1 opacity for the underlay (older revision). */
  opacity: number;
}

export interface DwgDrawingCompareDrawerProps {
  open: boolean;
  onClose: () => void;
  drawingId: string;
  drawingName: string;
  /** Notifies the page so the canvas can render the onion-skin underlay. */
  onOverlayChange?: (state: DwgCompareOverlayState) => void;
}

const CHANGE_DOT: Record<DwgEntityDiffRow['change_type'], string> = {
  added: 'bg-emerald-500',
  removed: 'bg-red-500',
  modified: 'bg-amber-500',
  unchanged: 'bg-slate-400',
};

function ChangeBadge({ type }: { type: DwgEntityDiffRow['change_type'] }) {
  const { t } = useTranslation();
  const label = t(`dwg_compare.change_${type}`, {
    defaultValue:
      type === 'added'
        ? 'Added'
        : type === 'removed'
          ? 'Removed'
          : type === 'modified'
            ? 'Modified'
            : 'Unchanged',
  });
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium text-content-secondary">
      <span className={clsx('h-2 w-2 rounded-full', CHANGE_DOT[type])} />
      {label}
    </span>
  );
}

function versionLabel(v: DwgDrawingVersion, t: TFunction): string {
  return t('dwg_compare.version_option', {
    defaultValue: 'v{{n}} · {{count}} entities',
    n: v.version_number,
    count: v.entity_count,
  });
}

export function DwgDrawingCompareDrawer({
  open,
  onClose,
  drawingId,
  drawingName,
  onOverlayChange,
}: DwgDrawingCompareDrawerProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<CompareTab>('summary');
  const [fromId, setFromId] = useState<string>('');
  const [toId, setToId] = useState<string>('');
  const [hideUnchanged, setHideUnchanged] = useState(true);
  const [overlay, setOverlay] = useState(false);
  const [opacity, setOpacity] = useState(0.5);

  const versionsQuery = useQuery({
    queryKey: ['dwg-versions', drawingId],
    queryFn: () => fetchDrawingVersions(drawingId),
    enabled: open && !!drawingId,
  });

  const versions = useMemo(() => versionsQuery.data ?? [], [versionsQuery.data]);

  // Seed defaults once versions arrive: baseline = previous, target = latest.
  useEffect(() => {
    if (versions.length === 0) return;
    // versions come back newest-first.
    const latest = versions[0];
    if (!latest) return;
    const previous = versions[1] ?? latest;
    setToId((cur) => cur || latest.id);
    setFromId((cur) => cur || previous.id);
  }, [versions]);

  // Push overlay state up to the page whenever it changes (and clear on close).
  useEffect(() => {
    onOverlayChange?.({ enabled: overlay && open, opacity });
  }, [overlay, opacity, open, onOverlayChange]);

  useEffect(() => {
    if (!open) {
      onOverlayChange?.({ enabled: false, opacity });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const canCompare = !!fromId && !!toId && fromId !== toId;

  const diffQuery = useQuery<DwgDrawingDiffResponse>({
    queryKey: ['dwg-compare', drawingId, fromId, toId],
    queryFn: () => compareDrawings(drawingId, fromId, toId),
    enabled: open && canCompare,
  });

  const diff = diffQuery.data;

  const navigate = useNavigate();
  const addToast = useToastStore((s) => s.addToast);

  // The diff has a real change when any tally bucket other than "unchanged"
  // is non-zero across entities and annotations. With no changes there is
  // nothing to turn into a variation, so the button is disabled.
  const hasChanges = useMemo(() => {
    if (!diff) return false;
    const s = diff.summary;
    const sum = (tally: Record<'added' | 'removed' | 'modified' | 'unchanged', number>) =>
      (tally.added ?? 0) + (tally.removed ?? 0) + (tally.modified ?? 0);
    return sum(s.entities) > 0 || sum(s.annotations) > 0;
  }, [diff]);

  const createVariationMutation = useMutation({
    mutationFn: () => {
      if (!canCompare) throw new Error('no comparison selected');
      return createVariationFromDiff(drawingId, fromId, toId);
    },
    onSuccess: (result) => {
      addToast(
        {
          type: 'success',
          title: t('dwg_compare.variation_created', {
            defaultValue: 'Draft variation {{code}} created',
            code: result.code,
          }),
          message: t('dwg_compare.variation_created_hint', {
            defaultValue: 'Review and confirm it in the variations module before submitting.',
          }),
          action: {
            label: t('dwg_compare.view_variation', { defaultValue: 'View variation' }),
            onClick: () => navigate('/variations'),
          },
        },
        { duration: 8000 },
      );
    },
    onError: () => {
      addToast({
        type: 'error',
        title: t('dwg_compare.variation_error', {
          defaultValue: 'Could not create the variation. Please try again.',
        }),
      });
    },
  });

  const entityRows = useMemo(
    () =>
      (diff?.entity_rows ?? []).filter(
        (r) => !hideUnchanged || r.change_type !== 'unchanged',
      ),
    [diff, hideUnchanged],
  );
  const annotationRows = useMemo(
    () =>
      (diff?.annotation_rows ?? []).filter(
        (r) => !hideUnchanged || r.change_type !== 'unchanged',
      ),
    [diff, hideUnchanged],
  );

  const tabs: { id: CompareTab; label: string; icon: typeof Layers; count: number }[] = [
    {
      id: 'summary',
      label: t('dwg_compare.tab_summary', { defaultValue: 'Summary' }),
      icon: BarChart3,
      count: 0,
    },
    {
      id: 'entities',
      label: t('dwg_compare.tab_entities', { defaultValue: 'Entities' }),
      icon: Layers,
      count: entityRows.length,
    },
    {
      id: 'annotations',
      label: t('dwg_compare.tab_annotations', { defaultValue: 'Annotations' }),
      icon: MessageSquare,
      count: annotationRows.length,
    },
  ];

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      widthClass="max-w-2xl"
      title={
        <span className="inline-flex items-center gap-2">
          <GitCompare size={16} className="text-oe-blue" />
          {t('dwg_compare.title', { defaultValue: 'Compare revisions' })}
        </span>
      }
      subtitle={drawingName}
    >
      <div className="flex flex-col gap-4 p-5">
        {/* Version pickers */}
        <div className="flex items-end gap-2">
          <label className="flex-1 min-w-0">
            <span className="block text-[11px] font-medium text-content-tertiary mb-1">
              {t('dwg_compare.from_version', { defaultValue: 'Baseline (before)' })}
            </span>
            <select
              value={fromId}
              onChange={(e) => setFromId(e.target.value)}
              disabled={versions.length === 0}
              data-testid="dwg-compare-from"
              className="w-full rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-xs text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {versionLabel(v, t)}
                </option>
              ))}
            </select>
          </label>
          <ArrowRight size={16} className="mb-2 shrink-0 text-content-tertiary" />
          <label className="flex-1 min-w-0">
            <span className="block text-[11px] font-medium text-content-tertiary mb-1">
              {t('dwg_compare.to_version', { defaultValue: 'Target (after)' })}
            </span>
            <select
              value={toId}
              onChange={(e) => setToId(e.target.value)}
              disabled={versions.length === 0}
              data-testid="dwg-compare-to"
              className="w-full rounded-md border border-border-light bg-surface-primary px-2 py-1.5 text-xs text-content-primary focus:outline-none focus:ring-2 focus:ring-oe-blue"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {versionLabel(v, t)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {versions.length < 2 && !versionsQuery.isLoading && (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-content-secondary">
            {t('dwg_compare.need_two_versions', {
              defaultValue:
                'This drawing has only one revision. Re-upload an updated DWG/DXF to create a second version to compare.',
            })}
          </p>
        )}

        {fromId === toId && versions.length >= 2 && (
          <p className="text-xs text-content-tertiary">
            {t('dwg_compare.pick_two', {
              defaultValue: 'Pick two different revisions to compare.',
            })}
          </p>
        )}

        {/* Controls row */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-border-light py-2">
          <label className="inline-flex items-center gap-1.5 text-xs text-content-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={hideUnchanged}
              onChange={(e) => setHideUnchanged(e.target.checked)}
              data-testid="dwg-compare-hide-unchanged"
              className="h-3.5 w-3.5 accent-oe-blue"
            />
            {t('dwg_compare.hide_unchanged', { defaultValue: 'Hide unchanged' })}
          </label>
          <label className="inline-flex items-center gap-1.5 text-xs text-content-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={overlay}
              onChange={(e) => setOverlay(e.target.checked)}
              data-testid="dwg-compare-overlay"
              className="h-3.5 w-3.5 accent-oe-blue"
            />
            <Eye size={13} />
            {t('dwg_compare.overlay', { defaultValue: 'Onion-skin overlay' })}
          </label>
          {overlay && (
            <label className="inline-flex items-center gap-2 text-xs text-content-tertiary">
              {t('dwg_compare.opacity', { defaultValue: 'Opacity' })}
              <input
                type="range"
                min={0}
                max={100}
                value={Math.round(opacity * 100)}
                onChange={(e) => setOpacity(Number(e.target.value) / 100)}
                data-testid="dwg-compare-opacity"
                className="w-28 accent-oe-blue"
              />
              <span className="tabular-nums w-8 text-right">{Math.round(opacity * 100)}%</span>
            </label>
          )}
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-1 rounded-lg bg-surface-secondary p-1">
          {tabs.map(({ id, label, icon: Icon, count }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              data-testid={`dwg-compare-tab-${id}`}
              className={clsx(
                'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors',
                tab === id
                  ? 'bg-surface-elevated text-oe-blue shadow-sm'
                  : 'text-content-secondary hover:text-content-primary',
              )}
            >
              <Icon size={13} />
              <span className="truncate">{label}</span>
              {count > 0 && (
                <Badge variant="neutral" className="ml-0.5 text-[9px]">
                  {count}
                </Badge>
              )}
            </button>
          ))}
        </div>

        {/* Loading / error / empty states */}
        {(versionsQuery.isLoading || (canCompare && diffQuery.isLoading)) && (
          <div className="flex items-center justify-center gap-2 py-10 text-sm text-content-tertiary">
            <Loader2 size={16} className="animate-spin" />
            {t('dwg_compare.loading', { defaultValue: 'Computing diff…' })}
          </div>
        )}

        {canCompare && diffQuery.isError && (
          <p className="rounded-md border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-500">
            {t('dwg_compare.error', {
              defaultValue: 'Could not compute the comparison. Please try again.',
            })}
          </p>
        )}

        {/* Body */}
        {diff && !diffQuery.isLoading && (
          <>
            {tab === 'summary' && (
              <SummaryTab
                diff={diff}
                canCreateVariation={hasChanges && canCompare}
                creating={createVariationMutation.isPending}
                onCreateVariation={() => createVariationMutation.mutate()}
              />
            )}
            {tab === 'entities' && <EntitiesTab rows={entityRows} hideUnchanged={hideUnchanged} />}
            {tab === 'annotations' && (
              <AnnotationsTab rows={annotationRows} hideUnchanged={hideUnchanged} />
            )}
          </>
        )}
      </div>
    </SideDrawer>
  );
}

/* ── Summary tab ───────────────────────────────────────────────────────── */

function SummaryTab({
  diff,
  canCreateVariation,
  creating,
  onCreateVariation,
}: {
  diff: DwgDrawingDiffResponse;
  canCreateVariation: boolean;
  creating: boolean;
  onCreateVariation: () => void;
}) {
  const { t } = useTranslation();
  const { summary } = diff;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <SummaryCard
          title={t('dwg_compare.entities_heading', { defaultValue: 'Entities (by layer)' })}
          tally={summary.entities}
        />
        <SummaryCard
          title={t('dwg_compare.annotations_heading', { defaultValue: 'Annotations' })}
          tally={summary.annotations}
        />
      </div>

      <div className="rounded-lg border border-border-light p-3">
        <div className="text-[11px] font-medium text-content-tertiary mb-1">
          {t('dwg_compare.net_cost_impact', { defaultValue: 'Net cost impact' })}
        </div>
        {summary.net_cost_impact != null && summary.cost_currency ? (
          <MoneyDisplay
            amount={summary.net_cost_impact}
            currency={summary.cost_currency}
            colorize
            className="text-lg font-semibold"
          />
        ) : (
          <p className="text-xs text-content-tertiary">
            {t('dwg_compare.no_cost_impact', {
              defaultValue:
                'No cost impact - no linked BOQ annotation changed value between these revisions.',
            })}
          </p>
        )}

        {/* Create-variation-from-delta handoff (Item 17). Disabled when the
            two revisions are identical / there are no changes. Creates a
            DRAFT variation the user confirms in the variations module. */}
        <button
          type="button"
          onClick={onCreateVariation}
          disabled={!canCreateVariation || creating}
          data-testid="dwg-compare-create-variation"
          className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-oe-blue px-3 py-2 text-xs font-semibold text-white transition hover:bg-oe-blue/90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {creating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <FilePlus2 size={14} />
          )}
          {t('dwg_compare.create_variation', { defaultValue: 'Create variation from delta' })}
        </button>
        {!canCreateVariation && (
          <p className="mt-1 text-[10px] text-content-tertiary">
            {t('dwg_compare.create_variation_disabled', {
              defaultValue: 'Pick two revisions with at least one change to raise a variation.',
            })}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-content-secondary">
        <span>
          {t('dwg_compare.entity_count_from', {
            defaultValue: 'Before: {{n}} entities',
            n: summary.from_entity_count,
          })}
        </span>
        <ArrowRight size={13} className="text-content-tertiary" />
        <span>
          {t('dwg_compare.entity_count_to', {
            defaultValue: 'After: {{n}} entities',
            n: summary.to_entity_count,
          })}
        </span>
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  tally,
}: {
  title: string;
  tally: Record<'added' | 'removed' | 'modified' | 'unchanged', number>;
}) {
  const { t } = useTranslation();
  const rows: { key: 'added' | 'removed' | 'modified'; color: string; label: string }[] = [
    { key: 'added', color: 'text-emerald-500', label: t('dwg_compare.change_added', { defaultValue: 'Added' }) },
    { key: 'removed', color: 'text-red-500', label: t('dwg_compare.change_removed', { defaultValue: 'Removed' }) },
    { key: 'modified', color: 'text-amber-500', label: t('dwg_compare.change_modified', { defaultValue: 'Modified' }) },
  ];
  return (
    <div className="rounded-lg border border-border-light p-3">
      <div className="text-[11px] font-medium text-content-tertiary mb-2 truncate">{title}</div>
      <div className="flex flex-col gap-1">
        {rows.map(({ key, color, label }) => (
          <div key={key} className="flex items-center justify-between text-xs">
            <span className={color}>{label}</span>
            <span className="tabular-nums font-semibold text-content-primary">{tally[key] ?? 0}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Entities tab ──────────────────────────────────────────────────────── */

function EntitiesTab({
  rows,
  hideUnchanged,
}: {
  rows: DwgEntityDiffRow[];
  hideUnchanged: boolean;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-content-tertiary">
        {hideUnchanged
          ? t('dwg_compare.no_entity_changes', { defaultValue: 'No entity changes between these revisions.' })
          : t('dwg_compare.no_entities', { defaultValue: 'No layers found.' })}
      </p>
    );
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border-light">
      <table className="w-full text-xs">
        <thead className="bg-surface-secondary text-content-tertiary">
          <tr>
            <th className="px-3 py-2 text-left font-medium">{t('dwg_compare.col_layer', { defaultValue: 'Layer' })}</th>
            <th className="px-3 py-2 text-left font-medium">{t('dwg_compare.col_change', { defaultValue: 'Change' })}</th>
            <th className="px-3 py-2 text-right font-medium">{t('dwg_compare.col_before', { defaultValue: 'Before' })}</th>
            <th className="px-3 py-2 text-right font-medium">{t('dwg_compare.col_after', { defaultValue: 'After' })}</th>
            <th className="px-3 py-2 text-right font-medium">{t('dwg_compare.col_delta', { defaultValue: 'Δ' })}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.entity_id} className="border-t border-border-light">
              <td className="px-3 py-2 font-medium text-content-primary truncate max-w-[160px]" title={r.layer}>
                {r.layer}
              </td>
              <td className="px-3 py-2">
                <ChangeBadge type={r.change_type} />
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-content-secondary">{r.old_count}</td>
              <td className="px-3 py-2 text-right tabular-nums text-content-secondary">{r.new_count}</td>
              <td
                className={clsx(
                  'px-3 py-2 text-right tabular-nums font-semibold',
                  r.delta > 0 ? 'text-emerald-500' : r.delta < 0 ? 'text-red-500' : 'text-content-tertiary',
                )}
              >
                {r.delta > 0 ? `+${r.delta}` : r.delta}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Annotations tab ───────────────────────────────────────────────────── */

function AnnotationsTab({
  rows,
  hideUnchanged,
}: {
  rows: DwgAnnotationDiffRow[];
  hideUnchanged: boolean;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <p className="py-8 text-center text-xs text-content-tertiary">
        {hideUnchanged
          ? t('dwg_compare.no_annotation_changes', {
              defaultValue: 'No annotation changes between these revisions.',
            })
          : t('dwg_compare.no_annotations', { defaultValue: 'No annotations on either revision.' })}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {rows.map((r) => (
        <div
          key={r.annotation_id}
          className="rounded-lg border border-border-light p-3"
          data-testid="dwg-compare-annotation-row"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium capitalize text-content-primary truncate">
              {r.label || r.annotation_type.replace('_', ' ')}
            </span>
            <ChangeBadge type={r.change_type} />
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-xs text-content-secondary">
            <span className="tabular-nums">
              {r.old_measurement != null ? r.old_measurement.toFixed(2) : '—'}
            </span>
            <ArrowRight size={12} className="text-content-tertiary" />
            <span className="tabular-nums font-medium text-content-primary">
              {r.new_measurement != null ? r.new_measurement.toFixed(2) : '—'}
            </span>
            {r.measurement_unit && <span className="text-content-tertiary">{r.measurement_unit}</span>}
          </div>
          {r.linked_boq_position_id && (
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <span className="text-[10px] text-content-tertiary">
                {t('dwg_compare.linked_boq', { defaultValue: 'Linked to BOQ position' })}
              </span>
              {r.cost_impact != null && r.cost_currency ? (
                <MoneyDisplay
                  amount={r.cost_impact}
                  currency={r.cost_currency}
                  colorize
                  className="text-xs font-semibold"
                />
              ) : (
                <span className="text-[10px] text-content-tertiary">
                  {t('dwg_compare.no_value_change', { defaultValue: 'No value change' })}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
