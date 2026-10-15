// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty and error states, and the proof that every governance key
// the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/approval-routes/ApprovalInstanceDetailDrawer', () => ({ ApprovalInstanceDetailDrawer: () => null }));
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getModel: vi.fn(),
    listCatalogues: vi.fn(),
    getProjectCountry: vi.fn(),
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
import { ALL_KEY_MAPS, ERROR_TEXT, EVIDENCE_DETAIL, EVIDENCE_STATE } from '../labels';
import { DISABLED_REASON } from '../access';
import { DECISION_PROBLEM } from '../decisionRules';
import { AREA_KEY_MAPS } from '../AreaPanel';
import { ROUTE_KEY_MAPS } from '../RoutePin';

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
    mocked.getProjectCountry.mockResolvedValue(null);
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

  it('the first model follows the flag the missing-model answer carries', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'No governance model', can: { manage: false } } }),
    );
    const view = renderPage();
    await screen.findByText('Neutral phase model');
    const refused = () => screen.queryAllByTestId('disabled-reason').some((r) => r.getAttribute('data-reason') === 'role_manage');
    await waitFor(() => expect(refused()).toBe(true));
    view.unmount();

    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'No governance model', can: { manage: true } } }),
    );
    renderPage();
    await screen.findByText('Neutral phase model');
    expect(refused()).toBe(false);
  });

  it('asks for the models of the project country and preselects the one the server marks', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'No governance model', can: { manage: true } } }),
    );
    mocked.getProjectCountry.mockResolvedValue('DE');
    const item = (over: object) => ({
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
      ...over,
    });
    mocked.listCatalogues.mockResolvedValue({
      ...emptyPage,
      total: 2,
      items: [
        item({ source: 'pack', pack: 'de', id: 'pack_model', code: 'pack_model', default: true, name: { key: null, text: { en: 'Pack phase model' } } }),
        item({}),
      ],
    } as never);
    renderPage();
    const preset = await screen.findByRole('radio', { name: /^Pack phase model/ });
    await waitFor(() => expect(preset).toBeChecked());
    expect(mocked.listCatalogues).toHaveBeenCalledWith('DE');
    expect(screen.getByText(/From the active pack/)).toHaveTextContent('Suggested for this project');
    expect(screen.getByRole('radio', { name: /^Neutral phase model/ })).not.toBeChecked();
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
  for (const m of sources.matchAll(/t\(\s*'(governance\.[a-z0-9_.]+)'/g)) used.add(m[1]!);
  for (const map of [...Object.values(ALL_KEY_MAPS), DISABLED_REASON, DECISION_PROBLEM, ...Object.values(AREA_KEY_MAPS), ...Object.values(ROUTE_KEY_MAPS)]) {
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

describe('evidence keys of the modules', () => {
  // The label keys the backend evidence providers send. Governance reads them through the API, so no
  // call site names them; a key missing here renders the humanised code in English in every language.
  const backend = join(__dirname, '..', '..', '..', '..', '..', 'backend', 'app', 'modules');
  const labelKeys = new Set<string>();
  for (const module of ['economics', 'project_handbook', 'engineering_brief']) {
    const source = readFileSync(join(backend, module, 'evidence.py'), 'utf-8');
    for (const m of source.matchAll(/"([a-z_]+\.evidence\.[a-z_.]+)"/g)) labelKeys.add(m[1]!);
  }
  for (const key of ['site_analysis', 'suitability', 'specification']) labelKeys.add(`engineering_brief.evidence.${key}`);
  for (const key of ['roadmap', 'register', 'start', 'handover', 'permit_due_later']) labelKeys.add(`permits.evidence.${key}`);
  for (const reason of ['no_area_hosts_permits', 'no_frame_document', 'no_phase_enables_tag']) {
    labelKeys.add(`permits.evidence.unresolved.${reason}`);
  }
  const detailKeys = [
    ...Object.values(EVIDENCE_DETAIL),
    ...Object.values(EVIDENCE_STATE).flatMap((m) => Object.values(m)),
  ].map(([key]) => key);

  it('finds the keys it is meant to check', () => {
    expect(labelKeys.size).toBeGreaterThan(25);
    expect(labelKeys.has('economics.evidence.proposed')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every evidence label and detail key resolves in %s', (_lang, table) => {
    expect([...labelKeys, ...detailKeys].filter((k) => !(k in table))).toEqual([]);
  });
});
