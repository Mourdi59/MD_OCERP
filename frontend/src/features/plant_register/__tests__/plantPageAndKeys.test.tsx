// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty, loading and error states, the item that opens from the
// URL, and the proof that every plant register key the feature uses resolves
// in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getCatalogue: vi.fn(),
    listItems: vi.fn(),
    listQuotes: vi.fn(),
    listSlots: vi.fn(),
    listPapers: vi.fn(),
    listLimits: vi.fn(),
    listSpares: vi.fn(),
    getLimitMatrix: vi.fn(),
    listItServices: vi.fn(),
    getFrameSummary: vi.fn(),
    getReadiness: vi.fn(),
    listFindings: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ERROR_TEXT } from '../errors';
import { EXPORT_NAME } from '../FrameSummary';
import { ALL_KEY_MAPS } from '../labels';
import { PlantRegisterPage } from '../PlantRegisterPage';
import { REGISTER_FILTER } from '../RegisterTable';
import { PROBLEM } from '../rules';
import { catalogue, frame, item, matrix, page, refusal } from './fixtures';

const mocked = vi.mocked(api);

function renderPage(search = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/projects/p1/plant-register${search}`]}>
        <Routes>
          <Route path="/projects/:projectId/plant-register" element={<PlantRegisterPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PlantRegisterPage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.getCatalogue.mockResolvedValue(catalogue());
    mocked.listItems.mockResolvedValue(page([item(), item({ id: 'i2', code: 'PL-002', title: 'Medium voltage switchgear', order_status: 'ok', float_days: 30 })]));
    for (const list of [mocked.listQuotes, mocked.listSlots, mocked.listPapers, mocked.listLimits, mocked.listSpares, mocked.listFindings]) {
      list.mockResolvedValue(page([]) as never);
    }
    mocked.listItServices.mockResolvedValue(page([]));
    mocked.getLimitMatrix.mockResolvedValue(matrix());
    mocked.getFrameSummary.mockResolvedValue(frame());
    mocked.getReadiness.mockResolvedValue({ ready: true, error_findings: [], critical_open: [], long_lead_open: [], frame_document_attached: true });
  });
  afterEach(cleanup);

  it('an empty register says what it is for and what to add first', async () => {
    mocked.listItems.mockResolvedValue(page([]));
    renderPage();
    expect(await screen.findByText('No plant items yet')).toBeInTheDocument();
    expect(screen.getByText(/Start with the equipment that takes longest to get/)).toBeInTheDocument();
    // One primary action: the empty state carries it, the header does not repeat it.
    expect(screen.getAllByRole('button', { name: 'Add item' })).toHaveLength(1);
    fireEvent.click(screen.getByRole('button', { name: 'Add item' }));
    expect(await screen.findByTestId('plant-item-dialog')).toBeInTheDocument();
  });

  it('a failing request shows the error with the reason, not the empty state', async () => {
    mocked.listItems.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('The plant register could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('database unavailable')).toBeInTheDocument();
    expect(screen.queryByText('No plant items yet')).toBeNull();
  });

  it('a project the reader cannot see is an error, not an invitation to add items', async () => {
    mocked.getCatalogue.mockRejectedValue(new ApiError(404, 'Not Found', { detail: 'Project not found' }));
    mocked.listItems.mockRejectedValue(new ApiError(404, 'Not Found', { detail: 'Project not found' }));
    renderPage();
    expect(await screen.findByText('The plant register could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No plant items yet')).toBeNull();
    expect(screen.queryByTestId('plant-add-item')).toBeNull();
  });

  it('a coded refusal on load reads as its sentence', async () => {
    mocked.getCatalogue.mockRejectedValue(refusal(404, 'unknown_catalogue', 'Unknown plant catalogue.'));
    renderPage();
    expect(await screen.findByText('Unknown plant catalogue.')).toBeInTheDocument();
  });

  it('lists the items, explains the module above the tabs and counts the overdue orders on the timeline tab', async () => {
    renderPage();
    expect(await screen.findAllByTestId('register-row')).toHaveLength(2);
    expect(screen.getByText('How the plant register works')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Long-lead timeline/ })).toHaveTextContent('1');
    expect(screen.getByTestId('plant-add-item')).toBeInTheDocument();
  });

  it('opens the item the URL names and hides the tabs while it is open', async () => {
    renderPage('?item=i2');
    expect(await screen.findByTestId('plant-item-panel')).toHaveTextContent('Medium voltage switchgear');
    expect(screen.queryByRole('tablist')).toBeNull();
    fireEvent.click(screen.getByText('Back to the register'));
    expect(await screen.findAllByTestId('register-row')).toHaveLength(2);
  });

  it('an item id from another project is explained, with the way back', async () => {
    renderPage('?item=elsewhere');
    expect(await screen.findByText('This item is not in the register')).toBeInTheDocument();
  });

  it('opens a row from the register', async () => {
    renderPage();
    const rows = await screen.findAllByTestId('register-row');
    fireEvent.click(rows[0]!);
    expect(await screen.findByTestId('plant-item-panel')).toHaveTextContent('Main power transformer');
  });

  it('the delivery limits tab loads the matrix', async () => {
    renderPage('?tab=limits');
    expect(await screen.findByTestId('plant-limit-matrix')).toBeInTheDocument();
  });

  it('site and IT is reachable before any item exists and says what to plan first', async () => {
    mocked.listItems.mockResolvedValue(page([]));
    renderPage('?tab=site_it');
    expect(await screen.findByTestId('it-empty')).toHaveTextContent('No IT service planned yet.');
    expect(screen.getByTestId('site-plant-empty')).toBeInTheDocument();
  });

  it('a failing tab shows its own error and keeps the page', async () => {
    mocked.getFrameSummary.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'summary failed' }));
    renderPage('?tab=frame');
    expect(await screen.findByText('The frame summary could not be loaded')).toBeInTheDocument();
    expect(screen.getByRole('tablist')).toBeInTheDocument();
  });
});

describe('plant register i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/\bt\(\s*'(plant\.[a-z0-9_.]+)'/g)) used.add(m[1]!);
  for (const map of [...Object.values(ALL_KEY_MAPS), PROBLEM, REGISTER_FILTER, EXPORT_NAME]) {
    for (const [key] of Object.values(map)) used.add(key);
  }
  for (const code of Object.keys(ERROR_TEXT)) used.add(`plant.errors.${code}`);
  // Catalogue entries are named by the key the pinned catalogue carries.
  const shipped = Object.keys(en.translation).filter((k) => k.startsWith('plant.catalogue.'));
  for (const key of shipped) used.add(key);

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(400);
    expect(shipped.length).toBeGreaterThan(60);
    expect(used.has('plant.page.empty_title')).toBe(true);
    expect(used.has('plant.problem.enquiry_date_required')).toBe(true);
    expect(used.has('plant.errors.waiver_needs_reason')).toBe(true);
    expect(used.has('plant.state.route_set')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    const missing = [...used].filter((k) => !(k in table));
    expect(missing).toEqual([]);
  });

  it('no default text in the source disagrees with the English locale', () => {
    const drift: string[] = [];
    const pattern = /\bt\(\s*'(plant\.[a-z0-9_.]+)',\s*\{\s*defaultValue:\s*'((?:[^'\\]|\\.)*)'/g;
    for (const m of sources.matchAll(pattern)) {
      const text = m[2]!.replace(/\\'/g, "'");
      if (en.translation[m[1]!] !== text) drift.push(m[1]!);
    }
    for (const map of [...Object.values(ALL_KEY_MAPS), PROBLEM, REGISTER_FILTER, EXPORT_NAME]) {
      for (const [key, text] of Object.values(map)) if (en.translation[key] !== text) drift.push(key);
    }
    for (const [code, text] of Object.entries(ERROR_TEXT)) {
      if (en.translation[`plant.errors.${code}`] !== text) drift.push(`plant.errors.${code}`);
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

  it('German keeps every placeholder the English has', () => {
    const holes = (text: string) => [...text.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort();
    const broken = [...used, ...Object.keys(en.translation).filter((k) => k.startsWith('notifications.plant.'))].filter(
      (k) => JSON.stringify(holes(en.translation[k] ?? '')) !== JSON.stringify(holes(de.translation[k] ?? '')),
    );
    expect(broken).toEqual([]);
  });

  it('no locale text is left with a single-brace placeholder i18next would print as is', () => {
    const single = Object.entries(en.translation)
      .filter(([k]) => k.startsWith('plant.') || k.startsWith('notifications.plant.'))
      .filter(([, v]) => /(^|[^{])\{[a-z_]+\}([^}]|$)/.test(v));
    expect(single).toEqual([]);
  });

  it('stays inside its own namespace', () => {
    expect([...used].every((k) => k.startsWith('plant.'))).toBe(true);
  });
});
