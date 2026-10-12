// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty, loading-through and error states, and the proof that
// every commitment key the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('@/features/approval-routes/api', () => ({ listRoutes: vi.fn(async () => []) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getMatrix: vi.fn(),
    getCapabilities: vi.fn(),
    listAssignments: vi.fn(),
    listItems: vi.fn(),
    listFindings: vi.fn(),
    listSchedules: vi.fn(),
    listReleases: vi.fn(),
    listAbortTerms: vi.fn(),
    listAbortBases: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { CAN_REASONS, DISABLED_REASON } from '../access';
import { CommitmentReleasePage, FindingsList } from '../CommitmentReleasePage';
import { ALL_KEY_MAPS, ERROR_TEXT } from '../labels';
import { ABORT_TERMS_PROBLEM, ITEM_PROBLEM, RELEASE_PROBLEM } from '../rules';
import { item, matrix, projectCan, totals } from './fixtures';

const mocked = vi.mocked(api);

function renderPage(search = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/projects/p1/commitments${search}`]}>
        <Routes>
          <Route path="/projects/:projectId/commitments" element={<CommitmentReleasePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: 100 });

const LOAD_FAILED = 'The commitments could not be loaded';
const NO_MATRIX = 'No commitment matrix yet';

describe('CommitmentReleasePage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.getCapabilities.mockResolvedValue({ matrix_exists: true, can: projectCan() });
    mocked.listAssignments.mockResolvedValue(page([]));
    mocked.listSchedules.mockResolvedValue(page([]));
    mocked.listFindings.mockResolvedValue(page([]));
    mocked.listReleases.mockResolvedValue(page([]));
    mocked.listAbortTerms.mockResolvedValue(page([]));
    mocked.listAbortBases.mockResolvedValue(page([]));
  });
  afterEach(cleanup);

  it('a project without a matrix says what the page is for and what to do first', async () => {
    mocked.getMatrix.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'matrix_missing', message: 'No commitment matrix' } }),
    );
    renderPage();
    expect(await screen.findByText(NO_MATRIX)).toBeInTheDocument();
    expect(screen.getByText(/First choose who may approve up to which amount/)).toBeInTheDocument();
    expect(screen.getByTestId('matrix-save')).toBeInTheDocument();
    expect(mocked.listItems).not.toHaveBeenCalled();
  });

  it('starting the matrix follows the manage flag the server sends before a matrix exists', async () => {
    mocked.getMatrix.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'matrix_missing', message: 'No commitment matrix' } }),
    );
    mocked.getCapabilities.mockResolvedValue({
      matrix_exists: false,
      can: projectCan({ manage: 'manage_required', add_item: 'matrix_missing', save_scenario: 'matrix_missing' }),
    });
    renderPage();
    await screen.findByText(NO_MATRIX);
    await waitFor(() =>
      expect(screen.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('manage_required'),
    );
    expect(screen.getByTestId('matrix-save')).toBeDisabled();
  });

  it('adding an item follows the server flag, and stays off while the server has not answered', async () => {
    let answer: (v: Awaited<ReturnType<typeof api.getCapabilities>>) => void = () => undefined;
    mocked.getCapabilities.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    mocked.getMatrix.mockResolvedValue(matrix());
    mocked.listItems.mockResolvedValue({ ...page([item()]), totals: totals() });
    renderPage();
    await screen.findByTestId('commitment-grid');
    expect(screen.getByTestId('item-add')).toBeDisabled();
    answer({ matrix_exists: true, can: projectCan({ add_item: 'edit_required' }) });
    await waitFor(() =>
      expect(screen.getByTestId('disabled-reason').getAttribute('data-reason')).toBe('edit_required'),
    );
    expect(screen.getByTestId('item-add')).toBeDisabled();
  });

  it('the setup tab marks a tier whose route was changed and offers to confirm it', async () => {
    const m = matrix();
    m.tiers[0] = { ...m.tiers[0]!, route_state: 'changed' };
    mocked.getMatrix.mockResolvedValue(m);
    mocked.listItems.mockResolvedValue({ ...page([item()]), totals: totals() });
    const { listRoutes } = await import('@/features/approval-routes/api');
    vi.mocked(listRoutes).mockResolvedValue([{ id: 'r1', name: 'Project manager route' }] as never);
    renderPage('?tab=setup');
    expect(await screen.findByTestId('tier-route-changed')).toBeInTheDocument();
    expect(await screen.findByTestId('tier-route-confirm')).toBeInTheDocument();
    // The untouched tier offers neither a confirmation nor a reset.
    expect(screen.getAllByTestId('tier-route-confirm')).toHaveLength(1);
    expect(screen.getAllByTestId('tier-route-reset')).toHaveLength(1);
  });

  it('a failing matrix request shows the error, not the empty state', async () => {
    mocked.getMatrix.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText(LOAD_FAILED)).toBeInTheDocument();
    expect(screen.queryByText(NO_MATRIX)).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "start a matrix"', async () => {
    mocked.getMatrix.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found' } }),
    );
    renderPage();
    expect(await screen.findByText(LOAD_FAILED)).toBeInTheDocument();
    expect(screen.queryByText(NO_MATRIX)).toBeNull();
    expect(screen.queryByTestId('matrix-save')).toBeNull();
  });

  it('a matrix without items points at the one thing to do next', async () => {
    mocked.getMatrix.mockResolvedValue(matrix());
    mocked.listItems.mockResolvedValue({ ...page([]), totals: totals({ planned: '0', released: '0', committed: '0' }) });
    renderPage();
    expect(await screen.findByText('No commitment items yet')).toBeInTheDocument();
    expect(screen.getAllByTestId('item-add')).toHaveLength(1);
    expect(screen.queryByTestId('commitment-grid')).toBeNull();
  });

  it('a failing item list shows the error under the header, not an empty matrix', async () => {
    mocked.getMatrix.mockResolvedValue(matrix());
    mocked.listItems.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText(LOAD_FAILED)).toBeInTheDocument();
    expect(screen.queryByText('No commitment items yet')).toBeNull();
  });

  it('with items it shows the grid and how strict the guard is', async () => {
    mocked.getMatrix.mockResolvedValue(matrix({ enforcement: 'block' }));
    mocked.listItems.mockResolvedValue({ ...page([item()]), totals: totals() });
    renderPage();
    expect(await screen.findByTestId('commitment-grid')).toBeInTheDocument();
    expect(screen.getAllByTestId('grid-row')).toHaveLength(1);
    expect(screen.getByTestId('enforcement-mode').textContent).toContain(enText('commitment.enforcement.block'));
  });

  it('an item link opens that item, and a stale link says the item is gone', async () => {
    mocked.getMatrix.mockResolvedValue(matrix());
    mocked.listItems.mockResolvedValue({ ...page([item()]), totals: totals() });
    const first = renderPage('?item=i1');
    expect(await screen.findByTestId('item-panel')).toBeInTheDocument();
    first.unmount();
    renderPage('?item=nope');
    expect(await screen.findByText('This item is not in the matrix')).toBeInTheDocument();
  });

  it('findings are listed in words and the block is absent when there are none', () => {
    const none = render(<FindingsList findings={[]} />);
    expect(screen.queryByTestId('findings')).toBeNull();
    none.unmount();
    render(
      <FindingsList
        findings={[
          {
            rule_id: 'commitment.over_release',
            passed: false,
            severity: 'error',
            message: 'Committed amount exceeds the release',
            element_ref: 'CR-002',
            suggestion: null,
          },
        ]}
      />,
    );
    expect(screen.getAllByTestId('finding-row')).toHaveLength(1);
    expect(screen.getByTestId('findings').textContent).not.toMatch(/commitment\.[a-z_]+\.[a-z_]+/);
  });
});

function enText(key: string): string {
  return en.translation[key] ?? key;
}

describe('commitment i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/\bt\(\s*'(commitment\.[a-z0-9_.]+)'/g)) used.add(m[1]!);
  for (const m of sources.matchAll(/\[\s*'(commitment\.[a-z0-9_.]+)'\s*,/g)) used.add(m[1]!);
  for (const map of [...Object.values(ALL_KEY_MAPS), DISABLED_REASON, RELEASE_PROBLEM, ITEM_PROBLEM, ABORT_TERMS_PROBLEM]) {
    for (const [key] of Object.values(map)) used.add(key);
  }
  for (const code of Object.keys(ERROR_TEXT)) used.add(`commitment.errors.${code}`);

  const has = (table: Record<string, string>, k: string) => k in table || (`${k}_other` in table && `${k}_one` in table);

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(300);
    expect(used.has('commitment.page.empty_matrix_title')).toBe(true);
    expect(used.has('commitment.errors.preconditions_open')).toBe(true);
    expect(used.has('commitment.disabled.manage_required')).toBe(true);
    expect(used.has('commitment.decide.approve')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every refusal code a capability flag can carry has its two sentences in %s', (_lang, table) => {
    const missing = CAN_REASONS.flatMap((code) =>
      [`commitment.disabled.${code}`, `commitment.errors.${code}`].filter((k) => !(k in table)),
    );
    expect(missing).toEqual([]);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    expect([...used].filter((k) => !has(table, k))).toEqual([]);
  });

  it('the English in the locale is the English written at the call site', () => {
    const drift: string[] = [];
    for (const m of sources.matchAll(/\bt\(\s*'(commitment\.[a-z0-9_.]+)'\s*,\s*\{\s*defaultValue:\s*'((?:[^'\\]|\\.)*)'/g)) {
      const want = m[2]!.replace(/\\'/g, "'");
      const got = en.translation[m[1]!] ?? en.translation[`${m[1]!}_other`];
      if (got !== want) drift.push(m[1]!);
    }
    expect(drift).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = [...used].filter((k) => {
      const e = en.translation[k];
      const d = de.translation[k];
      return e && d && e === d && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('German keeps every placeholder of the English sentence', () => {
    const holes = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]!).sort().join(',');
    const broken = Object.keys(en.translation).filter(
      (k) => k.startsWith('commitment.') && de.translation[k] !== undefined && holes(en.translation[k]!) !== holes(de.translation[k]!),
    );
    expect(broken).toEqual([]);
  });

  it('the locale texts carry no long dash', () => {
    const dashed = Object.keys(en.translation).filter(
      (k) => k.startsWith('commitment.') && /[–—]/.test(`${en.translation[k]}${de.translation[k] ?? ''}`),
    );
    expect(dashed).toEqual([]);
  });
});
