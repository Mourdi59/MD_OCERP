// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Contract tests for the NCR api helpers.
 *
 * ``fetchNCRs`` does two things at once and both are easy to break silently:
 *
 *   - it normalises each wire row (``ncr_number`` arrives as "NCR-007" and the
 *     UI sorts on a number, ``location`` falls back to
 *     ``location_description``, ``reported_by`` to ``created_by``), and
 *   - it hands back the page envelope rather than unwrapping it. The route
 *     defaults to 50 rows and refuses more than 100, and quality records
 *     accumulate for the life of a project, so ``total`` is what says how
 *     much of the register is in hand. A helper that returned only the rows
 *     would put every caller back to counting its own page and calling the
 *     answer the total, which is exactly the tile this migration fixed.
 *
 * The shared HTTP layer is mocked, so nothing here touches the network.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiGet = vi.fn(async (..._args: unknown[]) => ({}) as unknown);
const apiPost = vi.fn(async (..._args: unknown[]) => ({}) as unknown);
const apiPatch = vi.fn(async (..._args: unknown[]) => ({}) as unknown);

vi.mock('@/shared/lib/api', () => ({
  apiGet: (...args: unknown[]) => apiGet(...args),
  apiPost: (...args: unknown[]) => apiPost(...args),
  apiPatch: (...args: unknown[]) => apiPatch(...args),
}));

import { fetchNCRs } from '../api';

beforeEach(() => {
  apiGet.mockClear();
});

/** A wire row with only the fields the normaliser reads. */
function wireRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 'n1',
    project_id: 'p1',
    ncr_number: 'NCR-007',
    title: 'Rebar cover short',
    ncr_type: 'workmanship',
    severity: 'major',
    status: 'identified',
    description: '',
    root_cause: '',
    root_cause_category: null,
    corrective_action: '',
    preventive_action: '',
    location_description: 'Level 3, grid C4',
    created_by: 'user-9',
    cost_impact: '1250.50',
    linked_inspection_id: null,
    linked_inspection_number: null,
    change_order_id: null,
    created_at: '2026-08-01T10:00:00Z',
    updated_at: '2026-08-01T10:00:00Z',
    ...overrides,
  };
}

function page(items: unknown[], total: number) {
  return { items, total, offset: 0, limit: 50 };
}

describe('fetchNCRs', () => {
  it('keeps the envelope and normalises the rows inside it', async () => {
    apiGet.mockResolvedValueOnce(page([wireRow()], 214));

    const result = await fetchNCRs({ project_id: 'p1' });

    expect(result.total).toBe(214);
    expect(result.offset).toBe(0);
    expect(result.limit).toBe(50);
    expect(result.items).toHaveLength(1);
    const ncr = result.items[0]!;
    expect(ncr.ncr_number).toBe(7);
    expect(ncr.location).toBe('Level 3, grid C4');
    expect(ncr.reported_by).toBe('user-9');
    expect(ncr.cost_impact).toBe(1250.5);
  });

  it('reports a total larger than the rows it carries', async () => {
    // The case the whole migration is about: 50 of 214 on screen. A caller
    // reading only `items` cannot tell this apart from a register of 50.
    apiGet.mockResolvedValueOnce(page(Array.from({ length: 50 }, () => wireRow()), 214));

    const result = await fetchNCRs({ project_id: 'p1' });

    expect(result.items).toHaveLength(50);
    expect(result.total).toBeGreaterThan(result.items.length);
  });

  it('sends offset 0 rather than dropping it as falsy', async () => {
    apiGet.mockResolvedValueOnce(page([], 0));

    await fetchNCRs({ project_id: 'p1', offset: 0, limit: 100 });

    const url = apiGet.mock.calls[0]?.[0] as string;
    const qs = new URLSearchParams(url.split('?')[1]);
    expect(qs.get('offset')).toBe('0');
    expect(qs.get('limit')).toBe('100');
  });

  it('omits filters that were not supplied', async () => {
    apiGet.mockResolvedValueOnce(page([], 0));

    await fetchNCRs({ project_id: 'p1' });

    const url = apiGet.mock.calls[0]?.[0] as string;
    expect(url).toContain('project_id=p1');
    expect(url).not.toContain('status=');
    expect(url).not.toContain('severity=');
    expect(url).not.toContain('offset=');
  });
});
