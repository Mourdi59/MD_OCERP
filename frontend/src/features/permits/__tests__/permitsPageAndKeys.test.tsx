// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty, error and filled states, and the proof that every permits
// key the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/features/cde/api', () => ({ fetchCDEContainers: vi.fn(async () => []) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getRoadmap: vi.fn(),
    listCatalogues: vi.fn(),
    getShippedCatalogue: vi.fn(),
    listRequirements: vi.fn(),
    getTimeline: vi.fn(),
    listApplications: vi.fn(),
    listPermits: vi.fn(),
    listConditions: vi.fn(),
    getReadiness: vi.fn(),
    getValidation: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { READINESS_GATE, READINESS_GATE_HINT } from '../ChecksPanel';
import { ALL_KEY_MAPS, ERROR_TEXT, PERIOD_TEXT } from '../labels';
import { PermitsPage } from '../PermitsPage';
import { CLOCK_EVENT_PROBLEM, CONDITION_PROBLEM, DECISION_PROBLEM } from '../rules';
import { application, condition, emptyPage, page, permit, readiness, requirement, roadmap, timelineRow } from './fixtures';

const mocked = vi.mocked(api);

function renderPage(search = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/projects/p1/permits${search}`]}>
        <Routes>
          <Route path="/projects/:projectId/permits" element={<PermitsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function withProject() {
  mocked.getRoadmap.mockResolvedValue(roadmap());
  mocked.listRequirements.mockResolvedValue(
    page([requirement(), requirement({ id: 'r2', sort_order: 2, title: 'Road occupation', state: 'not_started' })]),
  );
  mocked.getTimeline.mockResolvedValue(page([timelineRow()]));
  mocked.listApplications.mockResolvedValue(page([application()]));
  mocked.listPermits.mockResolvedValue(page([permit({ requirement_id: 'r0', id: 'pm0' })]));
  mocked.listConditions.mockResolvedValue(page([condition({ permit_id: 'pm0', overdue: true })]));
}

describe('PermitsPage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.listCatalogues.mockResolvedValue(emptyPage);
    mocked.getShippedCatalogue.mockResolvedValue({ id: 'neutral', version: 1, permit_types: [] });
    mocked.getReadiness.mockImplementation(async (_p, gate) =>
      readiness({ gate, status: gate === 'start' ? 'not_ready' : 'ready' }),
    );
    mocked.getValidation.mockResolvedValue(emptyPage);
  });
  afterEach(cleanup);

  it('a project without a roadmap says what the roadmap is for and offers to start it', async () => {
    mocked.getRoadmap.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'roadmap_missing', message: 'No permit roadmap' } }),
    );
    renderPage();
    expect(await screen.findByText('No permit roadmap yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Start roadmap' })).toBeInTheDocument();
    expect(mocked.listRequirements).not.toHaveBeenCalled();
  });

  it('a failing roadmap request shows the error, not the empty state', async () => {
    mocked.getRoadmap.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('The permits could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No permit roadmap yet')).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "start a roadmap"', async () => {
    mocked.getRoadmap.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found' } }),
    );
    renderPage();
    expect(await screen.findByText('The permits could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No permit roadmap yet')).toBeNull();
  });

  it('a roadmap without permits asks for the first one', async () => {
    mocked.getRoadmap.mockResolvedValue(roadmap());
    for (const list of [mocked.listRequirements, mocked.getTimeline, mocked.listApplications, mocked.listPermits, mocked.listConditions]) {
      (list as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue(emptyPage);
    }
    renderPage();
    expect(await screen.findByText('No permit on the roadmap yet')).toBeInTheDocument();
  });

  it('shows the roadmap, the readiness of the site and where to export', async () => {
    withProject();
    renderPage();
    expect(await screen.findByText('Road occupation')).toBeInTheDocument();
    expect(screen.getAllByTestId('roadmap-row')).toHaveLength(2);
    expect(await screen.findByTestId('readiness-chip-start')).toHaveTextContent('Not ready');
    expect(screen.getByTestId('readiness-chip-handover')).toHaveTextContent('Ready');
    expect(screen.getByTestId('export-pdf')).toBeInTheDocument();
    expect(mocked.getValidation).not.toHaveBeenCalled();
  });

  it('moves between the registers through the tabs', async () => {
    withProject();
    renderPage();
    await screen.findByText('Road occupation');
    fireEvent.click(screen.getByRole('tab', { name: /Conditions/ }));
    expect(await screen.findByTestId('conditions-list')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Permits granted/ }));
    expect(await screen.findByTestId('permit-list')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /Readiness/ }));
    expect(await screen.findByTestId('checks-panel')).toBeInTheDocument();
    expect(screen.queryByTestId('export-pdf')).toBeNull();
    expect(mocked.getValidation).toHaveBeenCalledTimes(1);
  });

  it('a link reopens the tab it was copied from', async () => {
    withProject();
    renderPage('?tab=conditions');
    expect(await screen.findByTestId('conditions-list')).toBeInTheDocument();
    expect(screen.queryByTestId('roadmap-row')).toBeNull();
  });

  it('a failing list shows the error with a way to retry', async () => {
    withProject();
    mocked.listRequirements.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('The permits could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No permit on the roadmap yet')).toBeNull();
  });
});

describe('permits i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/\bt\(\s*'(permits\.[A-Za-z0-9_.]+)'/g)) used.add(m[1]!);
  const maps: Array<Record<string, readonly string[]>> = [
    ...Object.values(ALL_KEY_MAPS),
    READINESS_GATE,
    READINESS_GATE_HINT,
    CONDITION_PROBLEM,
    DECISION_PROBLEM,
    CLOCK_EVENT_PROBLEM,
    PERIOD_TEXT,
  ];
  for (const map of maps) {
    for (const [key] of Object.values(map)) used.add(key!);
  }
  for (const code of Object.keys(ERROR_TEXT)) used.add(`permits.errors.${code}`);
  for (const key of Object.keys(en.translation)) if (key.startsWith('permits.type.')) used.add(key);

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(550);
    expect(used.has('permits.ui.problem.conditions_required')).toBe(true);
    expect(used.has('permits.ui.permit.lapse_warning')).toBe(true);
    expect(used.has('permits.errors.roadmap_missing')).toBe(true);
    expect([...used].filter((k) => k.startsWith('permits.type.')).length).toBeGreaterThan(40);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    const missing = [...used].filter((k) => !(k in table) && !(`${k}_other` in table && `${k}_one` in table));
    expect(missing).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = Object.keys(en.translation).filter((k) => {
      if (!k.startsWith('permits.')) return false;
      const e = en.translation[k];
      const d = de.translation[k];
      return e && d && e === d && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('German keeps every placeholder the English has', () => {
    const holes = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(',');
    const broken = Object.keys(en.translation).filter(
      (k) => k.startsWith('permits.') && holes(en.translation[k]!) !== holes(de.translation[k] ?? ''),
    );
    expect(broken).toEqual([]);
  });

  it('the fallback text of a refusal is the text the locale ships', () => {
    const drift = Object.entries(ERROR_TEXT).filter(([code, text]) => en.translation[`permits.errors.${code}`] !== text);
    expect(drift.map(([code]) => code)).toEqual([]);
  });

  it('keeps to its own namespace', () => {
    expect([...used].every((k) => k.startsWith('permits.'))).toBe(true);
  });
});
