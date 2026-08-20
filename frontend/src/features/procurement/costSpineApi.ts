// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The project's cost spine, read so a buyer can order against a bill position.
 *
 * The buyer picks a position, not a cost line. What the picker actually lists
 * is the cost spine, because a spine line generated from the bill carries the
 * position's code, description, unit and estimate, and it is the set of
 * positions an order can be attributed to. A position with no spine line is
 * not offered, since ordering against it would record no money link at all.
 *
 * What goes back to the server is the `boq_position_id`, not the cost line, so
 * the link is resolved server-side at the moment the order line is written.
 * Sending the cost line we happen to be holding would freeze whatever this
 * page loaded, which may already be stale.
 * `backend/app/modules/procurement/cost_spine.py` sets out why.
 *
 * The endpoint caps `limit` at 200 and takes no search parameter, so a bill of
 * two thousand positions would otherwise show its first two hundred and leave
 * the buyer to conclude their position does not exist. This pages until the
 * server stops filling a page, and filtering happens over the loaded set.
 */

import { apiGet } from '@/shared/lib/api';

/** One cost line as `GET /v1/costmodel/projects/{id}/spine/lines/` returns it. */
export interface CostSpineLine {
  id: string;
  project_id: string;
  code: string;
  description: string;
  unit: string | null;
  source: string;
  boq_position_id: string | null;
  boq_id: string | null;
  estimate_quantity: string;
  estimate_unit_rate: string;
  estimate_amount: string;
  currency: string;
  status: string;
}

/** The page size the endpoint allows. Larger values are rejected with a 422. */
const PAGE_SIZE = 200;

/**
 * How many pages to walk before giving up.
 *
 * A bill of 20 000 positions is already far past what a dropdown can serve,
 * and an unbounded loop against a paginated endpoint is one off-by-one on the
 * server away from never terminating. The cap is a stop, not a limit we expect
 * to reach.
 */
const MAX_PAGES = 100;

/**
 * Every active cost line of a project, following the endpoint's paging.
 *
 * Stops as soon as a page comes back short, so the ordinary project costs one
 * request. Only lines carrying a `boq_position_id` are useful to the picker,
 * but the filtering happens at the call site rather than here so the shape
 * stays the endpoint's own.
 */
export async function listCostSpineLines(projectId: string): Promise<CostSpineLine[]> {
  const out: CostSpineLine[] = [];
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const params = new URLSearchParams({
      status: 'active',
      offset: String(page * PAGE_SIZE),
      limit: String(PAGE_SIZE),
    });
    const batch = await apiGet<CostSpineLine[]>(
      `/v1/costmodel/projects/${projectId}/spine/lines/?${params.toString()}`,
    );
    out.push(...batch);
    if (batch.length < PAGE_SIZE) break;
  }
  return out;
}

/**
 * The bill positions an order line can be attributed to, in bill order.
 *
 * A spine line with no `boq_position_id` was created by hand and answers to no
 * position, so it is dropped: this picker offers positions, and offering a
 * bare cost line would put the buyer back in front of the vocabulary the
 * server exists to keep away from them.
 */
export function billPositionOptions(lines: CostSpineLine[]): CostSpineLine[] {
  return lines
    .filter((line) => Boolean(line.boq_position_id))
    .sort((a, b) => a.code.localeCompare(b.code, undefined, { numeric: true }));
}

/** Case-insensitive match over the code and the description. */
export function matchesQuery(line: CostSpineLine, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return (
    line.code.toLowerCase().includes(needle) ||
    line.description.toLowerCase().includes(needle)
  );
}
