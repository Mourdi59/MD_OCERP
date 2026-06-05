/**
 * ClashCostImpactColumn — read-only money cell for the clash review table.
 *
 * Fetches the per-clash cost-impact payload from
 *   GET /v1/clash-cost-impact/clash/{clashId}/impact
 * and renders a right-aligned formatted-money cell with a hover tooltip
 * that surfaces the rework + labour breakdown and the confidence chip.
 *
 * The endpoint is owned by the ``clash_cost_impact`` backend module —
 * this column is the unique-to-AGPL-ERP differentiator (competitors that
 * ship coordination without a BOQ side cannot wire clashes to construction
 * cost). The component fails soft: any 4xx / 5xx renders an em-dash so a
 * partial outage of the cost-impact service never breaks the clash row.
 */

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/shared/lib/api';
import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';

/** Backend response shape — kept in lock-step with
 *  ``backend/app/modules/clash_cost_impact/schemas.py``.
 *
 *  NOTE: ``rework_subtotal`` and ``labour_subtotal`` are emitted as decimal
 *  *strings* on the wire (Pydantic ``field_serializer`` narrows Decimal to a
 *  string to avoid float-rounding drift). The other money fields are plain
 *  numbers. We type them as ``number | string`` and normalise with
 *  {@link toNum} before any arithmetic so a string never reaches
 *  ``Number.prototype.toFixed`` (which would throw and break the row). */
export interface ClashCostImpactComponents {
  rework_positions_total: number | string;
  rework_factor_pct: number | string;
  rework_subtotal: number | string;
  labour_hours: number | string;
  blended_rate: number | string;
  labour_subtotal: number | string;
}

/** Coerce a wire value (number or decimal string) to a finite number;
 *  falls back to 0 for null / undefined / unparseable input. */
function toNum(v: number | string | null | undefined): number {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export interface ClashCostImpactPayload {
  clash_id: string;
  currency: string;
  components: ClashCostImpactComponents;
  total_estimate: number;
  confidence: 'low' | 'medium' | 'high' | string;
  affected_positions: Array<{
    position_id: string;
    ordinal: string;
    description: string;
    total: number;
  }>;
}

export interface ClashCostImpactColumnProps {
  /** Clash id whose cost impact should render in this cell. */
  clashId: string;
  /** Project currency (falls back to the payload's own ``currency`` field
   *  if the prop is empty). Plumbed in by the parent so the formatter
   *  picks up project-level overrides without an extra round-trip. */
  currency?: string;
  /** Optional test-only overrides for the React Query options. */
  queryEnabled?: boolean;
}

/** Confidence pill — three-step ladder mirrored from the backend service. */
function ConfidenceChip({ confidence }: { confidence: string }) {
  const cls =
    confidence === 'high'
      ? 'bg-semantic-success-bg text-semantic-success'
      : confidence === 'medium'
        ? 'bg-semantic-warning-bg text-semantic-warning'
        : 'bg-surface-secondary text-content-tertiary';
  return (
    <span
      className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${cls}`}
      data-testid="clash-cost-confidence"
    >
      {confidence}
    </span>
  );
}

export function ClashCostImpactColumn({
  clashId,
  currency,
  queryEnabled = true,
}: ClashCostImpactColumnProps) {
  const query = useQuery<ClashCostImpactPayload>({
    queryKey: ['clash-cost-impact', clashId],
    queryFn: () =>
      apiGet<ClashCostImpactPayload>(
        `/v1/clash-cost-impact/clash/${clashId}/impact`,
      ),
    enabled: queryEnabled && !!clashId,
    // Money rarely shifts mid-session — keep it cached for a minute so
    // scrolling the review table does not re-issue a network call per row.
    staleTime: 60_000,
    retry: false,
  });

  if (query.isLoading) {
    return (
      <td
        className="px-3 py-2 text-right"
        data-testid="clash-cost-cell"
        data-state="loading"
      >
        <span
          className="ml-auto inline-block h-3 w-16 animate-pulse rounded bg-surface-tertiary"
          data-testid="clash-cost-skeleton"
        />
      </td>
    );
  }

  // Fail soft on any error / missing payload — an em-dash is preferable
  // to breaking the surrounding clash row.
  if (query.isError || !query.data) {
    return (
      <td
        className="px-3 py-2 text-right text-content-tertiary"
        data-testid="clash-cost-cell"
        data-state={query.isError ? 'error' : 'empty'}
      >
        &mdash;
      </td>
    );
  }

  const impact = query.data;
  const displayCurrency = currency || impact.currency || 'EUR';
  const c = impact.components;

  const tooltip =
    `Rework: ${toNum(c.rework_positions_total).toFixed(2)} ${displayCurrency} × ` +
    `${toNum(c.rework_factor_pct)}% = ${toNum(c.rework_subtotal).toFixed(2)} ${displayCurrency}\n` +
    `Labour: ${toNum(c.labour_hours)}h × ${toNum(c.blended_rate).toFixed(2)} ${displayCurrency} = ` +
    `${toNum(c.labour_subtotal).toFixed(2)} ${displayCurrency}\n` +
    `Confidence: ${impact.confidence}`;

  return (
    <td
      className="px-3 py-2 text-right"
      title={tooltip}
      data-testid="clash-cost-cell"
      data-state="ready"
    >
      <div className="flex items-center justify-end gap-1.5">
        <ConfidenceChip confidence={impact.confidence} />
        <MoneyDisplay
          amount={impact.total_estimate}
          currency={displayCurrency}
          className="tabular-nums text-content-primary"
        />
      </div>
    </td>
  );
}

export default ClashCostImpactColumn;
