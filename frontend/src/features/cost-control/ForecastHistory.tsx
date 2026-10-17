// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// How the forecast moved: one point per saved forecast against the plan, and
// the list underneath with the change from the previous one. This is the part
// a client asks for in every cost meeting ("it was 1.97 million at the
// calculation, why is it 2.38 now?"), so it reads without opening anything.
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Trash2 } from 'lucide-react';

import { ConfirmDialog } from '@/shared/ui/ConfirmDialog';
import { fmtCurrency, fmtDate } from '@/shared/lib/formatters';
import { num, type SnapshotSummary } from './api';
import { stageLabel } from './labels';

const W = 640;
const H = 160;
const PAD = 28;

function Chart({ points, currency }: { points: SnapshotSummary[]; currency: string }) {
  const { t } = useTranslation();
  const forecasts = points.map((p) => num(p.totals.forecast));
  const plans = points.map((p) => num(p.totals.planned));
  const all = [...forecasts, ...plans].filter((v) => v > 0);
  if (points.length < 2 || all.length === 0) return null;
  const min = Math.min(...all) * 0.97;
  const max = Math.max(...all) * 1.03;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (points.length - 1);
  const y = (v: number) => H - PAD - ((v - min) / (max - min || 1)) * (H - 2 * PAD);
  const line = (values: number[]) => values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ');
  return (
    <figure className="mb-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-40 w-full" role="img" aria-label={t('cost_control.chart_label', { defaultValue: 'Forecast over time against the plan' })}>
        <path d={line(plans)} fill="none" strokeWidth={1.5} strokeDasharray="4 4" className="stroke-content-quaternary" />
        <path d={line(forecasts)} fill="none" strokeWidth={2.5} className="stroke-oe-blue" />
        {forecasts.map((v, i) => (
          <circle key={points[i]!.id} cx={x(i)} cy={y(v)} r={3.5} className="fill-oe-blue">
            <title>{`${fmtDate(points[i]!.taken_on)}: ${fmtCurrency(v, currency)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="flex gap-4 text-2xs text-content-tertiary">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 bg-oe-blue" />
          {t('cost_control.col_forecast', { defaultValue: 'Forecast' })}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 border-t border-dashed border-content-quaternary" />
          {t('cost_control.col_planned', { defaultValue: 'Planned' })}
        </span>
      </figcaption>
    </figure>
  );
}

export interface ForecastHistoryProps {
  snapshots: SnapshotSummary[];
  currency: string;
  canDelete: boolean;
  onDelete: (id: string) => void;
}

export function ForecastHistory({ snapshots, currency, canDelete, onDelete }: ForecastHistoryProps) {
  const { t } = useTranslation();
  const [pendingDelete, setPendingDelete] = useState<SnapshotSummary | null>(null);
  const newestFirst = useMemo(() => [...snapshots].reverse(), [snapshots]);

  if (snapshots.length === 0) {
    return (
      <p className="text-sm text-content-tertiary">
        {t('cost_control.history_none', {
          defaultValue:
            'No forecast saved yet. Save one now and again every month: the saved forecasts show how the cost moved and why.',
        })}
      </p>
    );
  }

  return (
    <div>
      <Chart points={snapshots} currency={currency} />
      <ul className="divide-y divide-border-light">
        {newestFirst.map((s, i) => {
          const prev = newestFirst[i + 1];
          const delta = prev ? num(s.totals.forecast) - num(prev.totals.forecast) : null;
          return (
            <li key={s.id} className="flex items-center gap-3 py-2.5 text-sm">
              <span className="w-24 shrink-0 text-content-tertiary">{fmtDate(s.taken_on)}</span>
              <span className="min-w-0 flex-1 truncate text-content-primary">
                {s.label || stageLabel(t, s.stage)}
                {s.label && <span className="ml-2 text-xs text-content-tertiary">{stageLabel(t, s.stage)}</span>}
              </span>
              <span className="shrink-0 font-medium tabular-nums text-content-primary">
                {fmtCurrency(s.totals.forecast, currency)}
              </span>
              <span
                className={`w-28 shrink-0 text-right text-xs tabular-nums ${
                  delta === null || Math.abs(delta) < 0.005
                    ? 'text-content-tertiary'
                    : delta > 0
                      ? 'text-semantic-error'
                      : 'text-semantic-success'
                }`}
              >
                {delta === null ? '' : `${delta > 0 ? '+' : ''}${fmtCurrency(delta, currency)}`}
              </span>
              {canDelete && (
                <button
                  type="button"
                  className="shrink-0 rounded p-1 text-content-quaternary hover:text-semantic-error"
                  onClick={() => setPendingDelete(s)}
                  aria-label={t('cost_control.snapshot_delete', { defaultValue: 'Delete saved forecast' })}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <ConfirmDialog
        open={!!pendingDelete}
        title={t('cost_control.snapshot_delete', { defaultValue: 'Delete saved forecast' })}
        message={t('cost_control.snapshot_delete_confirm', {
          defaultValue: 'The saved forecast of {{date}} is removed from the history for everyone.',
          date: pendingDelete ? fmtDate(pendingDelete.taken_on) : '',
        })}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => {
          if (pendingDelete) onDelete(pendingDelete.id);
          setPendingDelete(null);
        }}
      />
    </div>
  );
}
