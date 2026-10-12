// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty and error states, and the proof that every governance key
// the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getModel: vi.fn(),
    listCatalogues: vi.fn(),
    listAreas: vi.fn(),
    getMatrix: vi.fn(),
    listDocuments: vi.fn(),
    listChangeRequests: vi.fn(),
    listConditions: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ProjectGovernancePage } from '../ProjectGovernancePage';
import { ALL_KEY_MAPS, ERROR_TEXT } from '../labels';
import { DISABLED_REASON } from '../access';
import { DECISION_PROBLEM } from '../decisionRules';
import { AREA_KEY_MAPS } from '../AreaPanel';

const mocked = vi.mocked(api);

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/projects/p1/governance']}>
        <Routes>
          <Route path="/projects/:projectId/governance" element={<ProjectGovernancePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const emptyPage = { items: [], total: 0, offset: 0, limit: 100 };

describe('ProjectGovernancePage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.listCatalogues.mockResolvedValue({
      ...emptyPage,
      total: 1,
      items: [
        {
          kind: 'phase_model',
          source: 'shipped',
          id: 'neutral',
          code: 'neutral',
          name: { key: null, text: { en: 'Neutral phase model' } },
          state: 'published',
          versions: [1],
          latest_version: 1,
          review_status: 'verified',
          jurisdiction_countries: [],
        },
      ],
    });
  });
  afterEach(cleanup);

  it('a project without a model tells the reader to choose one and offers the catalogues', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'No governance model' } }),
    );
    renderPage();
    expect(await screen.findByText('No phase model yet')).toBeInTheDocument();
    expect(await screen.findByText('Neutral phase model')).toBeInTheDocument();
    expect(screen.getByTestId('model-save')).toBeInTheDocument();
  });

  it('a failing model request shows the error, not the empty state', async () => {
    mocked.getModel.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('Project governance could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No phase model yet')).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "choose a model"', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found' } }),
    );
    renderPage();
    expect(await screen.findByText('Project governance could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No phase model yet')).toBeNull();
  });

  it('a model without areas points to the phase model tab', async () => {
    mocked.getModel.mockResolvedValue({
      id: 'm1',
      project_id: 'p1',
      catalogue_source: 'shipped',
      catalogue_id: 'neutral',
      catalogue_version: 1,
      current_phase: null,
      four_eyes: true,
      decision_route_id: null,
      change_route_id: null,
      stopped: false,
      stopped_at: null,
      phases: [],
      can: { manage: true },
    });
    mocked.listAreas.mockResolvedValue(emptyPage);
    mocked.getMatrix.mockResolvedValue({ gates: [], next_gate: null, areas: [] });
    mocked.listDocuments.mockResolvedValue(emptyPage);
    mocked.listChangeRequests.mockResolvedValue(emptyPage);
    mocked.listConditions.mockResolvedValue(emptyPage);
    renderPage();
    expect(await screen.findByText('No management areas yet')).toBeInTheDocument();
  });
});

describe('governance i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/t\(\s*'(governance\.[a-z_.]+)'/g)) used.add(m[1]!);
  for (const map of [...Object.values(ALL_KEY_MAPS), DISABLED_REASON, DECISION_PROBLEM, ...Object.values(AREA_KEY_MAPS)]) {
    for (const [key] of Object.values(map)) used.add(key);
  }
  for (const code of Object.keys(ERROR_TEXT)) used.add(`governance.errors.${code}`);
  used.add('governance.project.disabled.unavailable');

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the two tests below pass on nothing.
    expect(used.size).toBeGreaterThan(200);
    expect(used.has('governance.project.decision.problem.rationale_required')).toBe(true);
    expect(used.has('governance.errors.waiver_needs_rationale')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    const missing = [...used].filter((k) => !(k in table) && !(`${k}_other` in table && `${k}_one` in table));
    expect(missing).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = [...used].filter((k) => {
      const e = en.translation[k];
      const d = de.translation[k];
      return e && d && e === d && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('does not overwrite the admin governance page keys', () => {
    expect(en.translation['governance.title']).toBe('Governance');
    expect([...used].every((k) => k.startsWith('governance.project.') || k.startsWith('governance.errors.') || k.startsWith('governance.evidence.'))).toBe(true);
  });
});
