// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty, error and loaded states, and the proof that every
// delivery model key the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('../linkTargets', () => ({ fetchLinkTargets: vi.fn() }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getModel: vi.fn(),
    setModel: vi.fn(),
    listCatalogues: vi.fn(),
    getPinnedCatalogue: vi.fn(),
    getComparison: vi.fn(),
    getAllocations: vi.fn(),
    listPackages: vi.fn(),
    getConsistency: vi.fn(),
    listOfi: vi.fn(),
    listDecisions: vi.fn(),
    getReadiness: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import { useAuthStore } from '@/stores/useAuthStore';

import { DISABLED_REASON } from '../access';
import * as api from '../api';
import { DIALOG_KEY_MAPS } from '../ComparisonDialogs';
import { DECISION_KEY_MAPS } from '../DecisionRecordPanel';
import { DeliveryModelPage } from '../DeliveryModelPage';
import { ERROR_TEXT } from '../errorText';
import { ALL_KEY_MAPS } from '../labels';
import { OFI_KEY_MAPS } from '../OfiPanel';
import { PACKAGE_KEY_MAPS } from '../PackagePlanPanel';
import { MATRIX_KEY_MAPS } from '../RiskMatrixPanel';
import { PROBLEM } from '../rules';
import { catalogue, comparison, model, pkg } from './fixtures';

const mocked = vi.mocked(api);
const emptyPage = { items: [], total: 0, offset: 0, limit: 0 };

function renderPage(search = '') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/projects/p1/delivery${search}`]}>
        <Routes>
          <Route path="/projects/:projectId/delivery" element={<DeliveryModelPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DeliveryModelPage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useAuthStore.setState({ userId: 'u1', userRole: 'manager' });
    mocked.listCatalogues.mockResolvedValue({
      ...emptyPage,
      total: 1,
      items: [
        {
          kind: 'delivery_forms',
          source: 'shipped',
          id: 'neutral',
          code: 'neutral',
          name: { key: 'delivery_model.catalogue.neutral.name', text: null },
          state: 'published',
          versions: [1],
          latest_version: 1,
          review_status: 'unconfirmed',
        },
      ],
    });
    mocked.getPinnedCatalogue.mockResolvedValue(catalogue());
    mocked.listPackages.mockResolvedValue({ ...emptyPage, items: [pkg('main')], total: 1 });
    mocked.getComparison.mockResolvedValue(comparison());
  });
  afterEach(cleanup);

  it('a project without a model says what the screen is for and offers the catalogue to start from', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'This project has no delivery model yet.' } }),
    );
    mocked.setModel.mockResolvedValue(model({ status: 'draft' }));
    renderPage();
    expect(await screen.findByText('No delivery model yet')).toBeInTheDocument();
    expect(await screen.findByText('Neutral delivery forms')).toBeInTheDocument();
    // the catalogue is not verified against its sources, and the screen says so next to its name
    expect(screen.getByTestId('review-unconfirmed')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('start-model-button'));
    await waitFor(() => expect(mocked.setModel).toHaveBeenCalledWith('p1', { catalogue_source: 'shipped', catalogue_id: 'neutral' }));
  });

  it('only a manager may start the model, and the button says so', async () => {
    useAuthStore.setState({ userRole: 'editor' });
    mocked.getModel.mockRejectedValue(new ApiError(404, 'Not Found', { detail: { code: 'model_missing', message: 'none' } }));
    renderPage();
    expect(await screen.findByTestId('start-model-button')).toBeDisabled();
    expect(screen.getByTestId('disabled-reason')).toHaveAttribute('data-reason', 'role_manage');
  });

  it('a failing model request shows the error, not the empty state', async () => {
    mocked.getModel.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('The delivery model could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No delivery model yet')).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "start a model"', async () => {
    mocked.getModel.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found.' } }),
    );
    renderPage();
    expect(await screen.findByText('The delivery model could not be loaded')).toBeInTheDocument();
    expect(screen.queryByTestId('start-model')).toBeNull();
  });

  it('with a model it opens on the comparison and shows where the model stands', async () => {
    mocked.getModel.mockResolvedValue(model());
    renderPage();
    expect(await screen.findByTestId('comparison-table')).toBeInTheDocument();
    expect(screen.getByTestId('model-status')).toHaveTextContent('Comparing forms');
    expect(screen.getByTestId('model-form')).toHaveTextContent('Not chosen yet');
    expect(await screen.findByText('Neutral delivery forms')).toBeInTheDocument();
    expect(mocked.getAllocations).not.toHaveBeenCalled();
  });

  it('the tab in the URL opens that section, and a failing section says so without hiding the page', async () => {
    mocked.getModel.mockResolvedValue(model());
    mocked.getAllocations.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'boom' }));
    renderPage('?tab=risks');
    expect(await screen.findByText('This part of the delivery model could not be loaded')).toBeInTheDocument();
    expect(screen.getByTestId('model-strip')).toBeInTheDocument();
    expect(mocked.getComparison).not.toHaveBeenCalled();
  });

  it('an unknown tab falls back to the comparison', async () => {
    mocked.getModel.mockResolvedValue(model());
    renderPage('?tab=nonsense');
    expect(await screen.findByTestId('comparison-table')).toBeInTheDocument();
  });
});

describe('delivery model i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/\bt\(\s*'(delivery_model\.[A-Za-z0-9_.]+)'/g)) used.add(m[1]!);
  const maps = [
    ...Object.values(ALL_KEY_MAPS),
    ...Object.values(DIALOG_KEY_MAPS),
    ...Object.values(DECISION_KEY_MAPS),
    ...Object.values(OFI_KEY_MAPS),
    ...Object.values(PACKAGE_KEY_MAPS),
    ...Object.values(MATRIX_KEY_MAPS),
    DISABLED_REASON,
    PROBLEM,
  ];
  for (const map of maps) for (const [key] of Object.values(map)) used.add(key);
  for (const code of Object.keys(ERROR_TEXT)) used.add(`delivery_model.errors.${code}`);

  const placeholders = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(300);
    expect(used.has('delivery_model.ui.comparison.propose')).toBe(true);
    expect(used.has('delivery_model.ui.disabled.role_manage')).toBe(true);
    expect(used.has('delivery_model.blocked.approval_not_ready')).toBe(true);
    expect(used.has('delivery_model.errors.weights_not_100')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    expect([...used].filter((k) => !(k in table))).toEqual([]);
  });

  it('the English in the code is the English in the locale', () => {
    const drift: string[] = [];
    for (const map of maps) for (const [key, english] of Object.values(map)) if (en.translation[key] !== english) drift.push(key);
    for (const [code, english] of Object.entries(ERROR_TEXT)) {
      if (en.translation[`delivery_model.errors.${code}`] !== english) drift.push(code);
    }
    expect(drift).toEqual([]);
  });

  it('the catalogue keys the backend sends resolve in both locales', () => {
    const shipped = Object.keys(en.translation).filter((k) => k.startsWith('delivery_model.catalogue.'));
    expect(shipped.length).toBeGreaterThan(100);
    expect(shipped.filter((k) => !(k in de.translation))).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = Object.keys(en.translation).filter((k) => {
      if (!k.startsWith('delivery_model.')) return false;
      const e = en.translation[k]!;
      const d = de.translation[k];
      const words = e.replace(/\{\{[^}]*\}\}/g, '').match(/[A-Za-z]{2,}/g) ?? [];
      return d === e && words.length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('German keeps every placeholder of the English', () => {
    const broken = Object.keys(en.translation).filter(
      (k) =>
        k.startsWith('delivery_model.') &&
        JSON.stringify(placeholders(en.translation[k]!)) !== JSON.stringify(placeholders(de.translation[k] ?? '')),
    );
    expect(broken).toEqual([]);
  });

  it('stays inside its own namespace', () => {
    expect([...used].every((k) => k.startsWith('delivery_model.'))).toBe(true);
  });
});
