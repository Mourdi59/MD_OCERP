// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's loading, error and first-visit states, and the proof that every
// key the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, screen } from '@testing-library/react';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({ ProjectPeopleSelect: () => null }));
vi.mock('../api', async (importOriginal) => (await import('./apiMock')).apiMock(importOriginal));

import de from '@/app/locales/de';
import en from '@/app/locales/en';
import { ApiError } from '@/shared/lib/api';

import * as api from '../api';
import { ALL_KEY_MAPS } from '../labels';
import { concept, page } from './fixtures';
import { emptyProject, renderPage } from './harness';

const mocked = vi.mocked(api);

describe('QualityConceptPage states', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    emptyProject(mocked);
  });
  afterEach(cleanup);

  it('says what the page is for before anything has loaded', () => {
    mocked.getConcept.mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByRole('heading', { name: 'Quality concept' })).toBeInTheDocument();
    expect(
      screen.getByText('What quality the project owes, how it is proven and how the works are accepted.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('quality-concept-page')).toBeNull();
  });

  it('shows the failure and a way to retry when the concept cannot be read', async () => {
    mocked.getConcept.mockRejectedValue(new ApiError(403, 'Forbidden', { detail: 'No access to this project' }));
    renderPage();
    expect(await screen.findByText('The quality concept could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('No access to this project')).toBeInTheDocument();
    expect(screen.queryByTestId('quality-concept-page')).toBeNull();
  });

  it('offers to create the concept when the project has none', async () => {
    mocked.getConcept.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'concept_missing', message: 'No quality concept.' } }),
    );
    mocked.createConcept.mockResolvedValue(concept());
    renderPage();
    expect(await screen.findByText('This project has no quality concept yet')).toBeInTheDocument();
    expect(screen.queryByText('The quality concept could not be loaded')).toBeNull();
    mocked.getConcept.mockResolvedValue(concept());
    fireEvent.click(screen.getByRole('button', { name: 'Create quality concept' }));
    expect(await screen.findByTestId('quality-concept-page')).toBeInTheDocument();
    expect(mocked.createConcept).toHaveBeenCalledWith('p1');
  });

  it('shows why the concept could not be created', async () => {
    mocked.getConcept.mockRejectedValue(new ApiError(404, 'Not Found', { detail: { code: 'concept_missing' } }));
    mocked.createConcept.mockRejectedValue(
      new ApiError(403, 'Forbidden', {
        detail: { code: 'manage_required', message_key: 'quality_concept.errors.manage_required', message: 'x' },
      }),
    );
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'Create quality concept' }));
    expect(await screen.findByTestId('refusal-note')).toHaveTextContent(
      'Only a manager or the owner of the quality area can change the plan.',
    );
  });

  it('tells a first visitor what to do on the concept tab', async () => {
    renderPage();
    expect(await screen.findByTestId('quality-concept-page')).toBeInTheDocument();
    expect(await screen.findByTestId('standards-empty')).toHaveTextContent('Name at least one');
    expect(screen.getByTestId('scope-empty')).toHaveTextContent('Name the work packages first');
    expect(screen.getByTestId('concept-next-step')).toHaveTextContent('Clear the open points below');
  });

  it('opens the tab the address names and falls back to the concept for an unknown one', async () => {
    renderPage('preservation');
    expect(await screen.findByTestId('preservation-panel')).toBeInTheDocument();
    cleanup();
    renderPage('nonsense');
    expect(await screen.findByTestId('concept-panel')).toBeInTheDocument();
  });

  it('switches tabs and counts the blocking points on the concept tab', async () => {
    mocked.getConcept.mockResolvedValue(
      concept({ findings: [{ code: 'standards_basis_missing', severity: 'error', ref: '', params: {} }] }),
    );
    renderPage();
    const tab = await screen.findByRole('tab', { name: /Concept/ });
    expect(tab).toHaveTextContent('1');
    fireEvent.click(screen.getByRole('tab', { name: /Certification/ }));
    expect(await screen.findByText('No certification target')).toBeInTheDocument();
  });

  it('reports readiness and opens the failing checks on request', async () => {
    mocked.getReadiness.mockResolvedValue({
      concept: false,
      approved: false,
      errors: [{ code: 'standards_basis_missing', severity: 'error', ref: '', params: {} }],
      preservation_unplanned: ['north-neighbour'],
    });
    mocked.getValidation.mockResolvedValue(
      page([
        { rule_id: 'r1', passed: false, severity: 'error', message: 'A stage has no owner.', element_ref: null, suggestion: null },
        { rule_id: 'r2', passed: true, severity: 'error', message: 'Fine.', element_ref: null, suggestion: null },
      ]),
    );
    renderPage();
    expect(await screen.findByTestId('ready-complete')).toHaveAttribute('data-met', 'false');
    expect(screen.getByTestId('ready-complete')).toHaveTextContent('Concept has open points: 1');
    expect(screen.getByTestId('ready-preservation')).toHaveAttribute('data-met', 'false');
    fireEvent.click(await screen.findByTestId('checks-toggle'));
    expect(screen.getByTestId('unplanned-subjects')).toHaveTextContent('north-neighbour');
    expect(screen.getByTestId('check-list')).toHaveTextContent('A stage has no owner.');
    expect(screen.getByTestId('check-list')).not.toHaveTextContent('Fine.');
  });
});

describe('quality concept keys', () => {
  const dir = join(__dirname, '..');
  const sources = readdirSync(dir)
    .filter((f) => /\.tsx?$/.test(f))
    .map((f) => readFileSync(join(dir, f), 'utf8'))
    .join('\n');
  const used = new Set<string>();
  for (const m of sources.matchAll(/'(qualityConcept\.[\w.]+)'/g)) used.add(m[1]!);
  for (const map of Object.values(ALL_KEY_MAPS)) for (const [key] of Object.values(map)) used.add(key);
  const shipped = Object.keys(en.translation).filter((k) => k.startsWith('quality_concept.'));
  const all = [...used, ...shipped];

  it('finds the keys of the feature', () => {
    expect(used.size).toBeGreaterThan(400);
    expect(shipped.length).toBeGreaterThan(200);
  });

  it('has English and German for every key', () => {
    expect(all.filter((k) => !(k in en.translation))).toEqual([]);
    expect(all.filter((k) => !(k in de.translation))).toEqual([]);
  });

  it('keeps the same placeholders in both languages', () => {
    const holes = (text: string) => [...text.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();
    const off = all.filter((k) => holes(en.translation[k]!).join() !== holes(de.translation[k]!).join());
    expect(off).toEqual([]);
  });

  it('does not ship English sentences as German', () => {
    const copied = all.filter((k) => {
      const text = en.translation[k]!;
      return text.trim().split(/\s+/).length > 2 && de.translation[k] === text;
    });
    expect(copied).toEqual([]);
  });

  it('writes no long dash', () => {
    const dashed = all.filter((k) => /[\u2013\u2014]/.test(en.translation[k]! + de.translation[k]!));
    expect(dashed).toEqual([]);
  });
});
