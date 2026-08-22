// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <FormworkPage /> - the formwork pricing register.
//
// What they pin down:
//
//   1. The rate build-up as the table routes it. The panel half of the rate
//      amortises over the reuse count; the erect-and-strike half is paid on
//      every single use and does not move. Both halves and their sum arrive
//      from the server as Decimal-as-string, so what a frontend test can prove
//      is the routing and the formatting: the amortising number has to land in
//      the "Panels /m2" column and move with the reuse count, the per-use
//      number has to land in "Erect+strike /m2" and stay put, and the rate
//      column has to be their sum. The assertions are therefore cross-row -
//      one row on its own proves nothing, because a swapped pair of columns or
//      an inverted divisor still renders a perfectly plausible number.
//   2. The pour-cycle conflict row. Two pours closer together than the
//      striking time cannot be served by one panel set, and the panel has to
//      say so with both numbers on screen rather than quietly rounding the
//      reuse claim up.
//
// Column positions are resolved from the header row rather than hardcoded, so
// a reordered column fails loudly instead of shifting the assertions with it.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

/* ── Feature api ───────────────────────────────────────────────────────────
   Spread the real module first: the page imports seventeen functions plus the
   types from here, and a hand-written export list is one refactor away from
   leaving a newly imported symbol undefined at runtime. */

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    listSystems: vi.fn(),
    createSystem: vi.fn(),
    updateSystem: vi.fn(),
    deleteSystem: vi.fn(),
    seedDefaultSystems: vi.fn(),
    repriceSystem: vi.fn(),
    listAssignments: vi.fn(),
    createAssignment: vi.fn(),
    deleteAssignment: vi.fn(),
    getCycle: vi.fn(),
    deriveFromSchedule: vi.fn(),
    listScheduleLines: vi.fn(),
    addScheduleLine: vi.fn(),
    deleteScheduleLine: vi.fn(),
    getProjectSummary: vi.fn(),
    validateProject: vi.fn(),
    repriceProject: vi.fn(),
  };
});

/* ── Project context - a fixed active project.
   The page reads the store with a bare call and destructures; RequiresProject
   reads it with a selector. The stub answers both shapes. */

vi.mock('@/stores/useProjectContextStore', () => {
  const state = { activeProjectId: 'proj-1' };
  return {
    useProjectContextStore: (selector?: (s: typeof state) => unknown) =>
      selector ? selector(state) : state,
  };
});

import { getNumberLocale } from '@/stores/usePreferencesStore';
import {
  getCycle,
  getProjectSummary,
  listAssignments,
  listScheduleLines,
  listSystems,
  validateProject,
  type FormworkAssignmentDetail,
  type FormworkCycleAnalysis,
  type FormworkProjectSummary,
  type FormworkValidationReport,
} from '../api';
import { FormworkPage } from '../FormworkPage';

/* ── The rate the fixtures are built from ───────────────────────────────── */

/** Panel acquisition cost per m2 of panel. Amortises over the reuses. */
const PANEL_RATE = 60;
/** Erect-and-strike labour per m2 formed. Paid on every use, never divided. */
const LABOUR_RATE = 18;
const REUSES_MAX = 50;
const AREA = 100;

/** Two halves of the rate, the way the backend computes them. */
function panelHalf(reuses: number): number {
  return PANEL_RATE / reuses;
}

/**
 * Locale-formatted the same way the page formats a number, for display only.
 * The page reads the format preference (FormworkPage.tsx:310), so the
 * expectation reads it too. Built on the interface language instead, these
 * nine assertions would agree with the page only while the preference is
 * `auto`, and would fail on a reader who picked their own number format.
 */
function fmt(value: number): string {
  return new Intl.NumberFormat(getNumberLocale(), {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/* ── Fixtures ──────────────────────────────────────────────────────────── */

function makeAssignment(
  reuseCount: number,
  over: Partial<FormworkAssignmentDetail> = {},
): FormworkAssignmentDetail {
  const material = panelHalf(reuseCount);
  const unit = material + LABOUR_RATE;
  return {
    id: `assign-${reuseCount}`,
    project_id: 'proj-1',
    boq_position_id: 'boq-1',
    formwork_system_id: 'sys-1',
    area_m2: AREA.toFixed(2),
    reuse_count: reuseCount,
    waste_pct: '5.00',
    computed_unit_cost: unit.toFixed(2),
    material_unit_cost: material.toFixed(2),
    labour_unit_cost: LABOUR_RATE.toFixed(2),
    computed_total: (unit * AREA).toFixed(2),
    notes: null,
    tenant_id: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    system_name: 'Framed wall panel',
    system_type: 'wall',
    material: 'steel',
    supplier: 'Hire yard',
    reuses_max: REUSES_MAX,
    system_unit_rate: PANEL_RATE.toFixed(2),
    erect_strike_rate: LABOUR_RATE.toFixed(2),
    strip_time_days: 9,
    // A purchase basis is what the arithmetic above already assumes: it divides
    // the panel rate by the reuse count. A per-use basis would not amortise,
    // so stating it here keeps the fixture and `panelHalf` telling one story.
    rate_basis: 'purchase',
    typical_reuses: null,
    cycle_days: '9.00',
    currency: 'EUR',
    schedule_line_count: 0,
    ...over,
  };
}

function makeSummary(over: Partial<FormworkProjectSummary> = {}): FormworkProjectSummary {
  return {
    project_id: 'proj-1',
    assignment_count: 2,
    system_count: 1,
    total_area_m2: '200.00',
    total_cost: '11100.00',
    material_cost: '7500.00',
    labour_cost: '3600.00',
    average_unit_cost: '55.50',
    single_use_total: '15600.00',
    amortisation_saving: '4500.00',
    amortisation_saving_pct: '28.8',
    unlinked_to_boq: 0,
    currency: 'EUR',
    currency_mixed: false,
    // Left empty on purpose: a non-empty breakdown renders a second table and
    // the row queries below would no longer be unambiguous.
    by_system_type: [],
    ...over,
  };
}

function makeValidation(over: Partial<FormworkValidationReport> = {}): FormworkValidationReport {
  return {
    target_type: 'project',
    target_id: 'proj-1',
    status: 'passed',
    error_count: 0,
    warning_count: 0,
    info_count: 0,
    passed_count: 6,
    findings: [],
    unsupported_rule_sets: [],
    ...over,
  };
}

function makeCycle(over: Partial<FormworkCycleAnalysis> = {}): FormworkCycleAnalysis {
  return {
    assignment_id: 'assign-4',
    pour_count: 4,
    total_pour_area_m2: '400.00',
    peak_pour_area_m2: '100.00',
    reuse_ratio: '4.00',
    derived_reuse_count: 4,
    current_reuse_count: 4,
    current_area_m2: '100.00',
    reuses_max: REUSES_MAX,
    strip_time_days: 9,
    min_gap_days: 9,
    conflicts: [],
    dated_pour_count: 4,
    in_sync: true,
    ...over,
  };
}

/* ── Harness ───────────────────────────────────────────────────────────── */

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/formwork']}>
        <FormworkPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Header labels of the assignments table, in document order. */
function headerIndex(table: HTMLElement, label: string): number {
  const headers = within(table)
    .getAllByRole('columnheader')
    .map((h) => h.textContent?.trim() ?? '');
  const index = headers.indexOf(label);
  expect(index, `column "${label}" is missing from ${JSON.stringify(headers)}`).toBeGreaterThan(-1);
  return index;
}

function cellText(row: HTMLElement, table: HTMLElement, label: string): string {
  const cell = within(row).getAllByRole('cell')[headerIndex(table, label)];
  expect(cell, `row has no cell under column "${label}"`).toBeDefined();
  return cell?.textContent?.trim() ?? '';
}

/** The body row priced at `reuseCount` reuses, found by its own reuse cell. */
function rowForReuse(table: HTMLElement, reuseCount: number): HTMLElement {
  const bodyRows = within(table).getAllByRole('row').slice(1);
  const wanted = `${reuseCount} / ${REUSES_MAX}`;
  const row = bodyRows.find((r) => cellText(r, table, 'Reuses') === wanted);
  expect(row, `no row priced at ${wanted}`).toBeDefined();
  return row as HTMLElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listSystems).mockResolvedValue([]);
  vi.mocked(listAssignments).mockResolvedValue([]);
  vi.mocked(getProjectSummary).mockResolvedValue(makeSummary());
  vi.mocked(validateProject).mockResolvedValue(makeValidation());
  vi.mocked(listScheduleLines).mockResolvedValue([]);
  vi.mocked(getCycle).mockResolvedValue(makeCycle());
});

afterEach(() => cleanup());

/* ── Tests ─────────────────────────────────────────────────────────────── */

describe('FormworkPage rate build-up', () => {
  it('amortises the panel half over the reuses and leaves the labour half alone', async () => {
    // Same system, same area, same labour rate. The only difference between
    // the two rows is how many times the panel set is turned around.
    vi.mocked(listAssignments).mockResolvedValue([makeAssignment(1), makeAssignment(4)]);
    renderPage();

    const table = await screen.findByRole('table');
    const once = rowForReuse(table, 1);
    const fourTimes = rowForReuse(table, 4);

    // The amortising half follows the divisor: four turnarounds, a quarter of
    // the panel cost carried per m2 formed.
    expect(cellText(once, table, 'Panels /m2')).toBe(fmt(PANEL_RATE));
    expect(cellText(fourTimes, table, 'Panels /m2')).toBe(fmt(PANEL_RATE / 4));
    expect(cellText(once, table, 'Panels /m2')).not.toBe(cellText(fourTimes, table, 'Panels /m2'));

    // The per-use half does not amortise at all. If this column ever tracked
    // the reuse count, the job would be priced as though the crew erected and
    // struck the panels once and got the other three lifts free.
    expect(cellText(once, table, 'Erect+strike /m2')).toBe(fmt(LABOUR_RATE));
    expect(cellText(fourTimes, table, 'Erect+strike /m2')).toBe(
      cellText(once, table, 'Erect+strike /m2'),
    );

    // The rate is the sum of the two halves, not one of them.
    expect(cellText(once, table, 'Rate /m2')).toBe(fmt(PANEL_RATE + LABOUR_RATE));
    expect(cellText(fourTimes, table, 'Rate /m2')).toBe(fmt(PANEL_RATE / 4 + LABOUR_RATE));

    // Area times rate, with the currency of the assignment appended.
    expect(cellText(fourTimes, table, 'Total')).toBe(
      `${fmt((PANEL_RATE / 4 + LABOUR_RATE) * AREA)} EUR`,
    );
    expect(cellText(fourTimes, table, 'Area m2')).toBe(fmt(AREA));
  });

  it('keeps a single-use assignment at the full panel cost', async () => {
    vi.mocked(listAssignments).mockResolvedValue([makeAssignment(1)]);
    renderPage();

    const table = await screen.findByRole('table');
    const row = rowForReuse(table, 1);
    // One use means nothing is amortised: panels are carried whole and the
    // rate is the plain sum of the two catalogue rates.
    expect(cellText(row, table, 'Panels /m2')).toBe(fmt(PANEL_RATE));
    expect(cellText(row, table, 'Rate /m2')).toBe(fmt(PANEL_RATE + LABOUR_RATE));
  });
});

describe('FormworkPage pour cycle', () => {
  it('reports two pours closer together than the striking time', async () => {
    vi.mocked(listAssignments).mockResolvedValue([makeAssignment(4)]);
    vi.mocked(getCycle).mockResolvedValue(
      makeCycle({
        min_gap_days: 2,
        strip_time_days: 9,
        conflicts: [{ from_pour_no: 3, to_pour_no: 4, gap_days: 2, required_days: 9 }],
      }),
    );
    renderPage();

    await screen.findByRole('table');
    fireEvent.click(screen.getByRole('button', { name: /^Cycle$/ }));

    // Both numbers have to be on screen: the gap that was planned and the
    // striking time it fails to clear. Reporting one without the other leaves
    // the reader unable to tell how far out the programme is.
    const conflict = await screen.findByText(/9 d needed/);
    expect(conflict.textContent).toMatch(/2 d apart/);
    expect(conflict.textContent).toMatch(/\b3\b/);
    expect(conflict.textContent).toMatch(/\b4\b/);
    expect(getCycle).toHaveBeenCalledWith('assign-4');
  });

  it('says nothing about conflicts when the cycle clears the striking time', async () => {
    vi.mocked(listAssignments).mockResolvedValue([makeAssignment(4)]);
    vi.mocked(getCycle).mockResolvedValue(
      makeCycle({ min_gap_days: 12, strip_time_days: 9, conflicts: [] }),
    );
    renderPage();

    await screen.findByRole('table');
    fireEvent.click(screen.getByRole('button', { name: /^Cycle$/ }));

    // The panel itself has to be up - otherwise the absent banner below would
    // pass for the wrong reason.
    expect(await screen.findByText(/Turnarounds delivered/)).toBeInTheDocument();
    expect(screen.queryByText(/d needed/)).toBeNull();
  });
});
