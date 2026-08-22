// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * How one position's unit rate is built up, and the German EFB view of it.
 *
 * The backend has computed this since the price_breakdown module landed and
 * nothing in the product ever asked for it, so an estimator could not see the
 * make-up of a rate and a German bidder could not produce the Preisblatt a
 * public client demands with the tender. This drawer is that entrance.
 *
 * Two things about the wire are worth knowing before reading the JSX.
 *
 * Money and quantities arrive as Decimal-rendered STRINGS ("108.00"), the
 * platform-wide contract, so every value goes through `toNum` before it is
 * formatted or compared. The backend has already rounded each amount to the
 * currency's own precision; `formatCurrency` renders at that same precision,
 * so a peso rate does not grow cents on the way to the screen.
 *
 * `kind_totals` carries all six resource kinds, zeros included, so the
 * category list filters to the ones that actually carry cost. `efb.rows` also
 * carries all six and is deliberately NOT filtered: a Formblatt has fixed
 * rows, and a reader checking the sheet against the paper form should find
 * "Nachunternehmerleistungen (222)" where the form puts it, reading zero.
 */
import { useState, useMemo, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Calculator, Download, Loader2, X } from 'lucide-react';
import { boqApi, type PriceAnalysisPreset, type PriceAnalysisResponse } from './api';
import { getErrorMessage } from '@/shared/lib/api';
import { formatCurrency, toNum } from '@/shared/lib/money';
import { formatValue } from '@/shared/lib/numberFormat';
import { fmtPercent } from '@/shared/lib/formatters';

/* ── Constants ──────────────────────────────────────────────────────── */

/**
 * English defaults for the `price_breakdown.kind.*` keys the backend mints.
 * The keys themselves are the backend's (`model.kind_i18n_key`); only the
 * fallback wording lives here, and it matches the international preset.
 */
const KIND_DEFAULT_LABELS: Record<string, string> = {
  labor: 'Labour',
  material: 'Material',
  machinery: 'Machinery',
  equipment: 'Equipment',
  subcontractor: 'Subcontract',
  other: 'Other',
};

/** The two presets offered here, with the English default of each label. */
const PRESETS: { name: PriceAnalysisPreset; defaultLabel: string }[] = [
  { name: 'international', defaultLabel: 'Unit price analysis' },
  { name: 'efb', defaultLabel: 'EFB price sheets (221/222/223)' },
];

/** Colour per resource kind, same assignment as the BOQ cost breakdown. */
const KIND_DOT_CLASSES: Record<string, string> = {
  material: 'bg-blue-500',
  labor: 'bg-amber-500',
  machinery: 'bg-teal-500',
  equipment: 'bg-violet-500',
  subcontractor: 'bg-pink-500',
  other: 'bg-gray-500',
};

/* ── Props ──────────────────────────────────────────────────────────── */

export interface PriceAnalysisPanelProps {
  positionId: string;
  positionOrdinal: string;
  positionDescription: string;
  /**
   * Whether the position stores a resource split (`metadata.resources`).
   *
   * This cannot be read off the response: a position with no split still
   * answers with a full sheet, because the backend synthesises one "other"
   * line carrying the whole rate so the analysis always renders. Telling that
   * synthesised line apart from a real single-resource one means guessing at
   * its description, and the guess is wrong for a position with an empty
   * description. The caller holds the position and knows the answer, so it
   * says so instead.
   */
  hasResourceSplit: boolean;
  onClose: () => void;
}

/* ── Component ──────────────────────────────────────────────────────── */

export function PriceAnalysisPanel({
  positionId,
  positionOrdinal,
  positionDescription,
  hasResourceSplit,
  onClose,
}: PriceAnalysisPanelProps) {
  const { t } = useTranslation();
  const [preset, setPreset] = useState<PriceAnalysisPreset>('international');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // No `staleTime` on purpose. `hasResourceSplit` is read live off the bill
  // while the sheet would come from a cache that outlives the drawer, and the
  // two disagree in exactly the case the honest line exists for: add resources
  // to a position, reopen this drawer, and a held payload would still be the
  // synthesised single line while the prop says the rate is split. That draws
  // a lump sum as though it were a build-up. Refetching on open costs one
  // round-trip and cannot go stale against the bill.
  const { data, isLoading, error } = useQuery({
    queryKey: ['boq-price-analysis', positionId, preset],
    queryFn: () => boqApi.getPriceAnalysis(positionId, preset),
    enabled: !!positionId,
  });

  // Escape closes the drawer. The listener sits on the document rather than on
  // the panel because the panel is a plain div: it never takes focus, so a
  // handler bound to it would only fire when something inside it happens to be
  // focused, and would read as a working shortcut that mostly does nothing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  /** Categories that actually carry cost, in the backend's own order. */
  const activeCategories = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.kind_totals)
      .filter(([, amount]) => toNum(amount) !== 0)
      .map(([kind, amount]) => ({ kind, amount }));
  }, [data]);

  const handleDownload = async () => {
    setDownloading(true);
    setDownloadError(null);
    try {
      await boqApi.downloadPriceAnalysisMarkdown(positionId, preset, positionOrdinal);
    } catch (e: unknown) {
      setDownloadError(getErrorMessage(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20 backdrop-blur-[2px]" />

      {/* Drawer panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={t('boq.price_analysis', { defaultValue: 'Price analysis' })}
        className="relative w-full max-w-2xl bg-surface-elevated border-l border-border-light shadow-2xl
                    flex flex-col animate-slide-in-right"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-start gap-3 px-5 py-4 border-b border-border-light shrink-0">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-oe-blue/10 text-oe-blue shrink-0">
            <Calculator size={17} />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="text-sm font-semibold text-content-primary">
              {t('boq.price_analysis', { defaultValue: 'Price analysis' })}
            </h2>
            <p className="text-xs text-content-tertiary truncate mt-0.5">
              <span className="font-mono">{positionOrdinal}</span>
              {positionDescription && <> - {positionDescription}</>}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close', { defaultValue: 'Close' })}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-content-tertiary hover:bg-surface-secondary hover:text-content-primary transition-colors shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── Preset switch + download ───────────────────────────────── */}
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border-light shrink-0 flex-wrap">
          <div
            role="group"
            aria-label={t('boq.price_analysis_preset', { defaultValue: 'Presentation preset' })}
            className="flex items-center gap-1 rounded-lg bg-surface-secondary p-0.5"
          >
            {PRESETS.map((p) => (
              <button
                key={p.name}
                type="button"
                aria-pressed={preset === p.name}
                onClick={() => setPreset(p.name)}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  preset === p.name
                    ? 'bg-surface-elevated text-content-primary font-medium shadow-xs'
                    : 'text-content-tertiary hover:text-content-primary'
                }`}
              >
                {t(`price_breakdown.preset.${p.name}`, { defaultValue: p.defaultLabel })}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={handleDownload}
            disabled={downloading || !data}
            className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border border-border-light text-content-secondary hover:bg-surface-secondary hover:text-content-primary transition-colors disabled:opacity-50"
          >
            {downloading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {t('boq.price_analysis_download', { defaultValue: 'Download sheet (Markdown)' })}
          </button>
        </div>

        {/* ── Body ───────────────────────────────────────────────────── */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {downloadError && (
            <p className="text-xs text-red-600 dark:text-red-400">{downloadError}</p>
          )}

          {isLoading && !data && (
            <div className="flex items-center gap-2 text-xs text-content-tertiary animate-pulse">
              <Calculator size={14} />
              {t('boq.price_analysis_loading', { defaultValue: 'Loading price analysis...' })}
            </div>
          )}

          {error != null && !data && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {t('boq.price_analysis_failed', {
                defaultValue: 'The price analysis could not be loaded.',
              })}
            </p>
          )}

          {data && (
            <>
              {/* Position meta */}
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-content-tertiary">
                <span>
                  {t('boq.unit', { defaultValue: 'Unit' })}:{' '}
                  <span className="text-content-secondary">{data.unit || '-'}</span>
                </span>
                <span>
                  {t('boq.quantity', { defaultValue: 'Quantity' })}:{' '}
                  <span className="text-content-secondary tabular-nums">
                    {formatValue(toNum(data.position_quantity), 'number', {
                      maximumFractionDigits: 4,
                    })}
                  </span>
                </span>
                <span>
                  {t('boq.price_analysis_currency', { defaultValue: 'Currency' })}:{' '}
                  <span className="text-content-secondary">{data.currency}</span>
                </span>
              </div>

              {!hasResourceSplit ? (
                /* The rate exists but nobody has said what it is made of. Saying
                   so in one line is the honest reading; a table would suggest
                   the split is there and empty. */
                <p className="text-sm text-content-secondary bg-surface-secondary rounded-lg px-4 py-3">
                  {t('boq.price_analysis_no_split', {
                    defaultValue:
                      'This rate has not been broken down into resources yet, so the whole unit rate is carried as one amount. Add resources to the position to see how it is built up.',
                  })}
                </p>
              ) : preset === 'efb' && data.efb ? (
                <EfbSheet data={data} />
              ) : (
                <>
                  <ComponentTable data={data} />
                  {activeCategories.length > 1 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-semibold text-content-tertiary uppercase tracking-wide">
                        {t('boq.price_analysis_by_category', { defaultValue: 'By category' })}
                      </h3>
                      <div className="space-y-1">
                        {activeCategories.map((c) => (
                          <div key={c.kind} className="flex items-center justify-between text-xs">
                            <span className="flex items-center gap-2 text-content-secondary">
                              <span
                                className={`w-2.5 h-2.5 rounded-sm flex-shrink-0 ${KIND_DOT_CLASSES[c.kind] ?? 'bg-gray-500'}`}
                              />
                              {t(`price_breakdown.kind.${c.kind}`, {
                                defaultValue: KIND_DEFAULT_LABELS[c.kind] ?? c.kind,
                              })}
                            </span>
                            <span className="text-content-primary font-medium tabular-nums">
                              {formatCurrency(c.amount, data.currency)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              <MarkupSummary data={data} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────────────── */

/** The stored resource lines, each costed per one unit of the position. */
function ComponentTable({ data }: { data: PriceAnalysisResponse }) {
  const { t } = useTranslation();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-content-tertiary uppercase tracking-wide">
            <th className="text-left font-semibold py-1.5 pr-3">
              {t('boq.price_analysis_col_resource', { defaultValue: 'Resource' })}
            </th>
            <th className="text-left font-semibold py-1.5 pr-3">
              {t('boq.description', { defaultValue: 'Description' })}
            </th>
            <th className="text-right font-semibold py-1.5 pr-3">
              {t('boq.quantity', { defaultValue: 'Quantity' })}
            </th>
            <th className="text-right font-semibold py-1.5 pr-3">
              {t('boq.price_analysis_col_unit_cost', { defaultValue: 'Unit cost' })}
            </th>
            <th className="text-right font-semibold py-1.5">
              {t('boq.price_analysis_col_amount', { defaultValue: 'Amount' })}
            </th>
          </tr>
        </thead>
        <tbody>
          {data.components.map((c, idx) => (
            <tr key={`${c.kind}-${c.description}-${idx}`} className="border-t border-border-light">
              <td className="py-1.5 pr-3 whitespace-nowrap">
                <span className="flex items-center gap-2 text-content-secondary">
                  <span
                    className={`w-2 h-2 rounded-sm flex-shrink-0 ${KIND_DOT_CLASSES[c.kind] ?? 'bg-gray-500'}`}
                  />
                  {t(`price_breakdown.kind.${c.kind}`, {
                    defaultValue: KIND_DEFAULT_LABELS[c.kind] ?? c.kind,
                  })}
                </span>
              </td>
              <td className="py-1.5 pr-3 text-content-primary">{c.description}</td>
              <td className="py-1.5 pr-3 text-right text-content-secondary tabular-nums whitespace-nowrap">
                {formatValue(toNum(c.quantity), 'number', { maximumFractionDigits: 4 })}
                {c.unit && <span className="text-content-tertiary ml-1">{c.unit}</span>}
              </td>
              <td className="py-1.5 pr-3 text-right text-content-secondary tabular-nums whitespace-nowrap">
                {formatCurrency(c.unit_cost, data.currency)}
              </td>
              <td className="py-1.5 text-right text-content-primary font-medium tabular-nums whitespace-nowrap">
                {formatCurrency(c.amount, data.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The EFB grouping, one row per form field.
 *
 * The row labels come straight off the wire and are not run through i18n: they
 * name fields on the German Formblaetter 221/222/223, the same class of
 * wording as a GAEB or DIN 276 heading. Translating "Lohnkosten (221)" would
 * make the sheet harder, not easier, to check against the paper form.
 */
function EfbSheet({ data }: { data: PriceAnalysisResponse }) {
  const { t } = useTranslation();
  const efb = data.efb;
  if (!efb) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-content-tertiary uppercase tracking-wide">
        {t('price_breakdown.preset.efb', { defaultValue: 'EFB price sheets (221/222/223)' })}
      </h3>
      <table className="w-full text-xs">
        <tbody>
          {efb.rows.map((row) => (
            <tr key={row.kind} className="border-t border-border-light">
              <td className="py-1.5 pr-3 text-content-secondary">
                <span className="flex items-center gap-2">
                  <span
                    className={`w-2 h-2 rounded-sm flex-shrink-0 ${KIND_DOT_CLASSES[row.kind] ?? 'bg-gray-500'}`}
                  />
                  {row.label}
                </span>
              </td>
              <td className="py-1.5 text-right text-content-primary font-medium tabular-nums whitespace-nowrap">
                {formatCurrency(row.amount, efb.currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Direct cost, the markup stack and the two totals.
 *
 * Shown under both presets and in the un-split case alike: these numbers are
 * the position's own and are true whether or not anybody has written down what
 * the rate is made of. Overhead, risk and profit appear only when they carry a
 * percentage, which is how the downloaded document reads too.
 */
function MarkupSummary({ data }: { data: PriceAnalysisResponse }) {
  const { t } = useTranslation();
  const rows: { key: string; label: string; value: string }[] = [
    {
      key: 'direct',
      label: t('price_breakdown.line.direct', { defaultValue: 'Direct cost per unit' }),
      value: data.direct_unit_cost,
    },
  ];
  if (toNum(data.overhead_pct) !== 0) {
    rows.push({
      key: 'overhead',
      label: `${t('price_breakdown.line.overhead', { defaultValue: 'Overhead' })} (${fmtPercent(toNum(data.overhead_pct))})`,
      value: data.overhead_amount,
    });
  }
  if (toNum(data.risk_pct) !== 0) {
    rows.push({
      key: 'risk',
      label: `${t('price_breakdown.line.risk', { defaultValue: 'Risk' })} (${fmtPercent(toNum(data.risk_pct))})`,
      value: data.risk_amount,
    });
  }
  if (toNum(data.profit_pct) !== 0) {
    rows.push({
      key: 'profit',
      label: `${t('price_breakdown.line.profit', { defaultValue: 'Profit' })} (${fmtPercent(toNum(data.profit_pct))})`,
      value: data.profit_amount,
    });
  }

  return (
    <div className="border-t border-border pt-3 space-y-1.5">
      {rows.map((row) => (
        <div key={row.key} className="flex items-center justify-between text-xs">
          <span className="text-content-secondary">{row.label}</span>
          <span className="text-content-primary tabular-nums">
            {formatCurrency(row.value, data.currency)}
          </span>
        </div>
      ))}
      <div className="flex items-center justify-between text-xs border-t border-border pt-1.5">
        <span className="font-semibold text-content-primary">
          {t('price_breakdown.line.unit_rate', { defaultValue: 'Unit rate' })}
        </span>
        <span className="font-semibold text-content-primary tabular-nums">
          {formatCurrency(data.unit_rate, data.currency)}
        </span>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-bold text-content-primary text-sm">
          {t('price_breakdown.line.position_total', { defaultValue: 'Position total' })}
        </span>
        <span className="font-bold text-content-primary text-sm tabular-nums">
          {formatCurrency(data.position_total, data.currency)}
        </span>
      </div>
    </div>
  );
}
