// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty, error and loaded states, and the proof that every key
// the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/subcontractors/api', () => ({ listSubcontractors: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getConcept: vi.fn(),
    setConcept: vi.fn(),
    listCatalogues: vi.fn(),
    getPinnedCatalogue: vi.fn(),
    listFindings: vi.fn(),
    listPackages: vi.fn(),
    listProfiles: vi.fn(),
    listFrameworks: vi.fn(),
    listProjectFrameworks: vi.fn(),
    listGates: vi.fn(),
    listTenderPackages: vi.fn(),
    listAdvanceReleases: vi.fn(),
    listSoundings: vi.fn(),
    getSchedule: vi.fn(),
    listCandidates: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ProcurementConceptPage } from '../ProcurementConceptPage';
import { ALL_KEY_MAPS } from '../labels';
import { CANDIDATE_PROBLEM, FRAMEWORK_PROBLEM, PACKAGE_PROBLEM, PROFILE_PROBLEM } from '../rules';
import { RECORD_KEY_MAPS } from '../ConceptRecord';
import { PACKAGE_ACTION, PACKAGE_CONFIRM } from '../PackageBoard';
import { FRAMEWORK_MOVE } from '../Frameworks';
import {
  agreementPackage,
  blockingFinding,
  can,
  catalogue,
  catalogueRow,
  concept,
  framework,
  matrix,
  packageView,
  profile,
  schedule,
  soundingTight,
  unplannedPackage,
  warningFinding,
} from './fixtures';

const mocked = vi.mocked(api);
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: items.length });

function renderPage(url = '/projects/p1/procurement-concept') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/projects/:projectId/procurement-concept" element={<ProcurementConceptPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function loaded() {
  mocked.getConcept.mockResolvedValue(concept());
  mocked.listPackages.mockResolvedValue(page([packageView(), unplannedPackage, agreementPackage]));
  mocked.listFindings.mockResolvedValue(page([blockingFinding, warningFinding]));
  mocked.getPinnedCatalogue.mockResolvedValue(catalogue);
  mocked.listProfiles.mockResolvedValue(page([profile]));
  mocked.listFrameworks.mockResolvedValue(page([framework]));
  mocked.listProjectFrameworks.mockResolvedValue(page([framework]));
  mocked.listSoundings.mockResolvedValue(page([soundingTight]));
  mocked.getSchedule.mockResolvedValue(schedule);
  mocked.listCandidates.mockResolvedValue(matrix());
}

describe('ProcurementConceptPage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocked.listCatalogues.mockResolvedValue(page([catalogueRow]));
    mocked.listGates.mockResolvedValue(
      page([
        { code: 'g2', from_phase: 'p2', to_phase: 'p3', status: 'open', target_date: null, sort_order: 2, tagged_release_gate: false, selected: false },
        { code: 'g3', from_phase: 'p3', to_phase: 'p4', status: 'open', target_date: null, sort_order: 3, tagged_release_gate: true, selected: true },
      ]),
    );
  });
  afterEach(cleanup);

  it('a project without a concept says what the screen is for and offers the first step', async () => {
    mocked.getConcept.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'concept_missing', message: 'This project has no procurement concept yet.' } }),
    );
    renderPage();
    expect(await screen.findByText('No procurement concept yet.')).toBeInTheDocument();
    expect(screen.getByTestId('concept-start')).toHaveTextContent('Start concept');
    // Nothing else is asked of the server while there is no concept: every other route would answer 404.
    expect(mocked.listPackages).not.toHaveBeenCalled();
    expect(mocked.listFindings).not.toHaveBeenCalled();
  });

  it('starts the concept with the laws and client types the chosen catalogue brings', async () => {
    mocked.getConcept.mockRejectedValue(new ApiError(404, 'Not Found', { detail: { code: 'concept_missing', message: 'none' } }));
    mocked.setConcept.mockResolvedValue(concept());
    renderPage();
    fireEvent.click(await screen.findByTestId('concept-start'));
    const law = (await screen.findByLabelText('Procurement law')) as HTMLSelectElement;
    await waitFor(() => expect([...law.options].map((o) => o.value)).toEqual(['none', 'eu']));
    // Under no public procurement law there is no public client to choose.
    expect(screen.getByTestId('concept-public-client')).toBeDisabled();
    fireEvent.change(law, { target: { value: 'eu' } });
    fireEvent.click(screen.getByTestId('concept-public-client'));
    const kind = screen.getByLabelText('Kind of public client') as HTMLSelectElement;
    expect([...kind.options].map((o) => o.value)).toEqual(['central', 'sub_central', 'utility']);
    fireEvent.change(kind, { target: { value: 'utility' } });
    fireEvent.change(screen.getByLabelText('VAT rate in percent'), { target: { value: '19' } });
    // A new concept does not name the gate: who may is known only once the concept exists.
    expect(screen.queryByLabelText('Gate that releases procurement')).toBeNull();
    fireEvent.click(screen.getByTestId('concept-save'));
    await waitFor(() => expect(mocked.setConcept).toHaveBeenCalledTimes(1));
    expect(mocked.setConcept.mock.calls[0]).toEqual([
      'p1',
      { catalogue_source: 'shipped', catalogue_id: 'eu', jurisdiction: 'eu', public_client: true, client_type: 'utility', vat_rate_pct: '19' },
    ]);
    expect(mocked.listGates).not.toHaveBeenCalled();
  });

  it('names the release gate from the gates of the project', async () => {
    loaded();
    mocked.setConcept.mockResolvedValue(concept());
    renderPage('/projects/p1/procurement-concept?tab=record');
    fireEvent.click(await screen.findByTestId('concept-edit'));
    const gate = (await screen.findByLabelText('Gate that releases procurement')) as HTMLSelectElement;
    await waitFor(() => expect([...gate.options].map((o) => o.value)).toEqual(['', 'g2', 'g3']));
    expect(gate.options[0]!.textContent).toContain('g3');
    fireEvent.change(gate, { target: { value: 'g2' } });
    fireEvent.click(screen.getByTestId('concept-save'));
    await waitFor(() => expect(mocked.setConcept).toHaveBeenCalledTimes(1));
    expect(mocked.setConcept.mock.calls[0]![1]).toEqual({
      jurisdiction: 'eu',
      public_client: true,
      client_type: 'sub_central',
      vat_rate_pct: '0',
      release_gate_code: 'g2',
    });
  });

  it('keeps the release gate closed, with the reason, for who may not name it', async () => {
    loaded();
    mocked.getConcept.mockResolvedValue(concept({ can: can({ set_gate_fields: 'manage_required' }) }));
    renderPage('/projects/p1/procurement-concept?tab=record');
    fireEvent.click(await screen.findByTestId('concept-edit'));
    const gate = await screen.findByLabelText('Gate that releases procurement');
    expect(gate).toBeDisabled();
    expect(screen.getByTestId('concept-dialog')).toHaveTextContent(en.translation['procurement_concept.errors.manage_required']!);
  });

  it('a refusal to start the concept shows the reason the server gave', async () => {
    mocked.getConcept.mockRejectedValue(new ApiError(404, 'Not Found', { detail: { code: 'concept_missing', message: 'none' } }));
    mocked.setConcept.mockRejectedValue(
      new ApiError(403, 'Forbidden', { detail: { code: 'not_procurement_owner', message: 'server sentence' } }),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId('concept-start'));
    await waitFor(() => expect(screen.getByTestId('concept-save')).toBeEnabled());
    fireEvent.click(screen.getByTestId('concept-save'));
    const box = await screen.findByTestId('refusal-box');
    expect(box).toHaveAttribute('data-code', 'not_procurement_owner');
    expect(box).toHaveTextContent('Only a project manager or the owner of the procurement area can do this.');
  });

  it('a failing request shows the error, not the empty state', async () => {
    mocked.getConcept.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderPage();
    expect(await screen.findByText('The procurement concept could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No procurement concept yet.')).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "start a concept"', async () => {
    mocked.getConcept.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found' } }),
    );
    renderPage();
    expect(await screen.findByText('The procurement concept could not be loaded')).toBeInTheDocument();
    expect(screen.queryByTestId('concept-start')).toBeNull();
  });

  it('opens on the package board with the state and what blocks approval', async () => {
    loaded();
    renderPage();
    expect(await screen.findByTestId('package-board')).toBeInTheDocument();
    expect(screen.getAllByTestId('package-row')).toHaveLength(3);
    expect(screen.getByTestId('concept-state-badge')).toHaveTextContent('Draft');
    await waitFor(() => expect(screen.getByTestId('concept-blocking')).toHaveTextContent('Blocking approval: 1'));
  });

  it('a link reopens the tab and the package it names', async () => {
    loaded();
    renderPage('/projects/p1/procurement-concept?tab=prequalification&package=k1');
    expect(await screen.findByTestId('candidate-matrix')).toBeInTheDocument();
    expect(mocked.listCandidates).toHaveBeenCalledWith('p1', 'k1');
  });

  it.each([
    ['market', 'market-soundings'],
    ['schedule', 'award-schedule'],
    ['frameworks', 'frameworks'],
    ['record', 'concept-record'],
  ])('the %s tab renders its screen', async (tab, testId) => {
    loaded();
    renderPage(`/projects/p1/procurement-concept?tab=${tab}`);
    expect(await screen.findByTestId(testId)).toBeInTheDocument();
  });

  it('a list that fails shows its own error and a retry', async () => {
    loaded();
    mocked.listPackages.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'boom' }));
    renderPage();
    expect(await screen.findByText('The packages could not be loaded')).toBeInTheDocument();
  });
});

describe('procurement concept i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  const defaults = new Map<string, string>();
  for (const m of sources.matchAll(/t\(\s*'(procurement_concept\.[a-z0-9_.]+)'\s*,\s*\{\s*defaultValue:\s*'((?:[^'\\]|\\.)*)'/g)) {
    used.add(m[1]!);
    defaults.set(m[1]!, m[2]!.replace(/\\'/g, "'"));
  }
  for (const m of sources.matchAll(/\[\s*'(procurement_concept\.[a-z0-9_.]+)'\s*,\s*'((?:[^'\\]|\\.)*)'\s*,?\s*\]/g)) {
    used.add(m[1]!);
    defaults.set(m[1]!, m[2]!.replace(/\\'/g, "'"));
  }
  const maps = [
    ...Object.values(ALL_KEY_MAPS),
    ...Object.values(RECORD_KEY_MAPS),
    PACKAGE_PROBLEM,
    PROFILE_PROBLEM,
    CANDIDATE_PROBLEM,
    FRAMEWORK_PROBLEM,
    PACKAGE_ACTION,
    PACKAGE_CONFIRM,
    FRAMEWORK_MOVE,
  ];
  for (const map of maps) {
    for (const [key, english] of Object.values(map)) {
      used.add(key);
      defaults.set(key, english);
    }
  }
  const enKeys = Object.keys(en.translation).filter((k) => k.startsWith('procurement_concept.'));
  const has = (table: Record<string, string>, k: string) => k in table || (`${k}_other` in table && `${k}_one` in table);

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(300);
    expect(used.has('procurement_concept.ui.package.threshold_after_save')).toBe(true);
    expect(used.has('procurement_concept.errors.advance_without_reason')).toBe(true);
    expect(used.has('procurement_concept.approval.by_gate')).toBe(true);
    // The routes for these are gone, so their words must be gone too.
    expect(enKeys.filter((k) => /actions\.(approve|reopen)$|errors\.rationale_required$/.test(k))).toEqual([]);
    expect(enKeys.length).toBeGreaterThan(450);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key the feature uses resolves in %s', (_lang, table) => {
    expect([...used].filter((k) => !has(table, k))).toEqual([]);
  });

  it('the English in the source is the English in the locale', () => {
    const drift = [...defaults].filter(([k, text]) => k in en.translation && en.translation[k] !== text).map(([k]) => k);
    expect(drift).toEqual([]);
  });

  it('every refusal and finding the backend can send has its sentence in both languages', () => {
    const server = enKeys.filter((k) => /^procurement_concept\.(errors|findings)\./.test(k));
    expect(server.length).toBeGreaterThan(70);
    expect(server.filter((k) => !(k in de.translation))).toEqual([]);
  });

  it('German has every key English has, with the same placeholders', () => {
    expect(enKeys.filter((k) => !(k in de.translation))).toEqual([]);
    const marks = (s: string) => (s.match(/\{\{\w+\}\}/g) ?? []).sort().join(',');
    expect(enKeys.filter((k) => marks(en.translation[k]!) !== marks(de.translation[k] ?? ''))).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = enKeys.filter((k) => {
      const e = en.translation[k];
      const d = de.translation[k];
      return e && d && e === d && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('stays in its own namespace and leaves the purchasing keys alone', () => {
    expect([...used].every((k) => k.startsWith('procurement_concept.'))).toBe(true);
    expect(en.translation['procurement.po_type_standard']).toBe('Standard');
  });

  it('writes no long dash anywhere', () => {
    const dashed = enKeys.filter((k) => /[–—]/.test(`${en.translation[k]}${de.translation[k] ?? ''}`));
    expect(dashed).toEqual([]);
  });
});
