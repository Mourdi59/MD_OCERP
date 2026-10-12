// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The page's empty and error states, the personnel file as it opens from a
// link, the promise that a file is read once, and the proof that every
// staffing key the feature uses resolves in both English and German.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('@/shared/ui/ProjectPeopleSelect', () => ({
  ProjectPeopleSelect: ({ placeholder }: { placeholder?: string }) => <input aria-label={placeholder} readOnly />,
}));
vi.mock('@/features/teams/api', () => ({ listRoster: vi.fn(async () => ({ items: [], total: 0 })) }));
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getPlan: vi.fn(),
    listCatalogues: vi.fn(),
    getPinnedCatalogue: vi.fn(),
    listPositions: vi.fn(),
    listHandovers: vi.fn(),
    listPlanFindings: vi.fn(),
    listFiles: vi.fn(),
    getFile: vi.fn(),
    getAccessLog: vi.fn(),
    createPlan: vi.fn(),
    verifyDocument: vi.fn(),
  };
});

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { ProjectStaffingPage } from '../ProjectStaffingPage';
import { ALL_KEY_MAPS } from '../labels';
import { catalogue, fileCan, fileCanNothing, fileDocument, fileRow, no, personnelFile, plan, position, yes } from './fixtures';

const mocked = vi.mocked(api);
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: items.length });

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/projects/:projectId/staffing" element={<ProjectStaffingPage />} />
          <Route path="/projects/:projectId/staffing/files/:fileId" element={<ProjectStaffingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mocked.listCatalogues.mockResolvedValue(
    page([
      {
        kind: 'staffing_model',
        source: 'shipped' as const,
        id: 'neutral',
        code: 'neutral',
        name: { key: 'staffing.catalogue.neutral.name', text: null },
        state: 'published',
        versions: [1],
        latest_version: 1,
        review_status: 'unconfirmed',
      },
    ]),
  );
  mocked.getPinnedCatalogue.mockResolvedValue(catalogue());
  mocked.listPositions.mockResolvedValue(page([position()]));
  mocked.listHandovers.mockResolvedValue(page([]));
  mocked.listPlanFindings.mockResolvedValue(page([]));
});
afterEach(cleanup);

describe('ProjectStaffingPage states', () => {
  it('a project without a plan says what the plan is for and offers the catalogue', async () => {
    mocked.getPlan.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'plan_missing', message: 'This project has no staffing plan yet.' } }),
    );
    mocked.createPlan.mockResolvedValue(plan());
    renderAt('/projects/p1/staffing');
    expect(await screen.findByText('No staffing plan yet')).toBeInTheDocument();
    expect(await screen.findByRole('option', { name: 'Staffing model, country neutral' })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('plan-create'));
    await waitFor(() =>
      expect(mocked.createPlan).toHaveBeenCalledWith('p1', {
        catalogue_source: 'shipped',
        catalogue_id: 'neutral',
        requires_accommodation: false,
        commissioning_date: null,
      }),
    );
  });

  it('a failing plan request shows the error, not the empty state', async () => {
    mocked.getPlan.mockRejectedValue(new ApiError(500, 'Server Error', { detail: 'database unavailable' }));
    renderAt('/projects/p1/staffing');
    expect(await screen.findByText('Staffing could not be loaded')).toBeInTheDocument();
    expect(screen.queryByText('No staffing plan yet')).toBeNull();
  });

  it('a 404 for a project the user cannot see is an error, not "create a plan"', async () => {
    mocked.getPlan.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'project_not_found', message: 'Project not found.' } }),
    );
    renderAt('/projects/p1/staffing');
    expect(await screen.findByText('Staffing could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('Project not found.')).toBeInTheDocument();
    expect(screen.queryByText('No staffing plan yet')).toBeNull();
  });

  it('opens on the plan and loads the people list only when its tab is opened', async () => {
    mocked.getPlan.mockResolvedValue(plan());
    mocked.listFiles.mockResolvedValue(page([fileRow()]));
    renderAt('/projects/p1/staffing');
    expect(await screen.findByTestId('plan-panel')).toBeInTheDocument();
    expect(mocked.listFiles).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('tab', { name: /People/ }));
    expect(await screen.findByTestId('people-panel')).toBeInTheDocument();
    expect(mocked.getFile).not.toHaveBeenCalled();
  });
});

describe('personnel file', () => {
  beforeEach(() => mocked.getPlan.mockResolvedValue(plan()));

  it('opens from the notification link and shows documents, their state and what to check', async () => {
    mocked.getFile.mockResolvedValue(
      personnelFile({
        cleared_to_work: false,
        documents: [
          fileDocument(),
          fileDocument({ id: 'doc-2', document_kind: 'work_permit', status: 'expiring_soon', valid_until: '2026-11-01', number_last4: '4821' }),
          fileDocument({ id: null, document_kind: 'safety_training', status: null }),
        ],
        warnings: [{ code: 'no_accommodation', ref: 'rm-1', severity: 'warning', detail: '' }],
      }),
    );
    renderAt('/projects/p1/staffing/files/file-1');
    const file = await screen.findByTestId('personnel-file');
    expect(within(file).getByRole('heading', { name: 'Dana Weber' })).toBeInTheDocument();
    expect(within(file).getByTestId('cleared-no')).toBeInTheDocument();
    expect(within(file).getByText('No accommodation is booked for the start date.')).toBeInTheDocument();
    const docs = within(file).getAllByTestId('document-row');
    expect(docs.map((d) => within(d).getByTestId('document-state').textContent)).toEqual(['Valid', 'Expiring soon', 'Missing']);
    expect(within(docs[1]!).getByTestId('document-last4-shown')).toHaveTextContent('Number ending 4821');
    expect(within(docs[2]!).getByTestId('document-waive')).toBeInTheDocument();
    expect(within(file).getByTestId('travel-empty')).toBeInTheDocument();
    expect(within(file).getByTestId('accommodation-empty')).toBeInTheDocument();
    expect(mocked.getFile).toHaveBeenCalledWith('p1', 'file-1');
  });

  it('reads the file once: neither a window focus nor the access log button reads it again', async () => {
    mocked.getFile.mockResolvedValue(personnelFile());
    mocked.getAccessLog.mockResolvedValue(page([{ actor_id: null, action: 'personnel_file.read', at: '2026-10-12T08:00:00+00:00' }]));
    renderAt('/projects/p1/staffing/files/file-1');
    await screen.findByTestId('personnel-file');
    expect(mocked.getAccessLog).not.toHaveBeenCalled();
    window.dispatchEvent(new Event('focus'));
    document.dispatchEvent(new Event('visibilitychange'));
    fireEvent.click(screen.getByTestId('file-log-toggle'));
    const log = await screen.findByTestId('access-log');
    expect(within(log).getByText('Opened the file')).toBeInTheDocument();
    expect(within(log).getByText('Somebody outside the project team')).toBeInTheDocument();
    expect(mocked.getFile).toHaveBeenCalledTimes(1);
  });

  it('offers no write on a file the server marks read-only', async () => {
    mocked.getFile.mockResolvedValue(
      personnelFile({
        can: fileCanNothing('own_file_read_only'),
        documents: [fileDocument({ can: { verify: no('personnel_permission_missing') } })],
      }),
    );
    renderAt('/projects/p1/staffing/files/file-1');
    const file = await screen.findByTestId('personnel-file');
    expect(within(file).getByTestId('file-read-only')).toHaveTextContent(en.translation['staffing.errors.own_file_read_only']!);
    const writes = ['file-edit', 'file-end', 'file-hold', 'file-release', 'file-erase', 'add-travel', 'add-leave'];
    for (const id of [...writes, 'document-link', 'document-verify', 'document-waive', 'file-export-own']) {
      expect(within(file).queryByTestId(id)).toBeNull();
    }
  });

  it('offers each action of the file by its own server flag, not by a rule of the client', async () => {
    // An ended file on hold: only the release is allowed. The person concerned may download it.
    mocked.getFile.mockResolvedValue(
      personnelFile({
        status: 'retention_hold',
        hold_rationale: 'Open dispute',
        can: fileCan({ end: no('file_not_active'), hold: no('already_in_state'), release: yes, erase: no('retention_hold_active'), export: yes }),
      }),
    );
    renderAt('/projects/p1/staffing/files/file-1');
    const file = await screen.findByTestId('personnel-file');
    expect(within(file).getByTestId('file-release')).toBeInTheDocument();
    expect(within(file).getByTestId('file-export-own')).toBeInTheDocument();
    for (const id of ['file-end', 'file-hold', 'file-erase']) expect(within(file).queryByTestId(id)).toBeNull();
    expect(within(file).getByTestId('file-erase-refused')).toHaveTextContent('A retention hold is active. Release it first.');
  });

  it('does not offer the check to the person who recorded the document, and says why', async () => {
    mocked.getFile.mockResolvedValue(
      personnelFile({
        documents: [
          fileDocument({ recorded_by: 'u-me', can: { verify: no('verifier_is_recorder') } }),
          fileDocument({ id: 'doc-2', document_kind: 'work_permit', recorded_by: 'u-other' }),
        ],
      }),
    );
    renderAt('/projects/p1/staffing/files/file-1');
    const file = await screen.findByTestId('personnel-file');
    const docs = within(file).getAllByTestId('document-row');
    expect(within(docs[0]!).queryByTestId('document-verify')).toBeNull();
    expect(within(docs[0]!).getByTestId('document-verify-refused')).toHaveTextContent(en.translation['staffing.errors.verifier_is_recorder']!);
    expect(within(docs[1]!).getByTestId('document-verify')).toBeInTheDocument();
    expect(within(docs[1]!).queryByTestId('document-verify-refused')).toBeNull();
  });

  it('a refused file says who may open it instead of offering a retry', async () => {
    mocked.getFile.mockRejectedValue(
      new ApiError(403, 'Forbidden', { detail: { code: 'no_relationship_to_person', message: 'x' } }),
    );
    renderAt('/projects/p1/staffing/files/file-1');
    const denied = await screen.findByTestId('file-denied');
    expect(within(denied).getByText('You cannot open this file.')).toBeInTheDocument();
    expect(within(denied).getByText(en.translation['staffing.errors.no_relationship_to_person']!)).toBeInTheDocument();
    expect(within(denied).queryByRole('button', { name: /retry|try again/i })).toBeNull();
  });

  it('an erased file shows that it was erased and no personal sections', async () => {
    mocked.getFile.mockResolvedValue(personnelFile({ status: 'anonymised', name: null, documents: [], can: fileCanNothing('file_anonymised') }));
    renderAt('/projects/p1/staffing/files/file-1');
    const file = await screen.findByTestId('personnel-file');
    expect(within(file).getByTestId('file-anonymised')).toBeInTheDocument();
    expect(within(file).getByRole('heading', { name: 'Former team member' })).toBeInTheDocument();
    expect(within(file).queryByTestId('file-documents')).toBeNull();
    expect(within(file).queryByTestId('file-erase')).toBeNull();
  });
});

describe('staffing i18n keys', () => {
  const featureDir = join(__dirname, '..');
  const sources = readdirSync(featureDir)
    .filter((f) => /\.(ts|tsx)$/.test(f))
    .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
    .join('\n');

  const used = new Set<string>();
  for (const m of sources.matchAll(/t\(\s*'(staffing\.[a-z0-9_.]+)'/g)) used.add(m[1]!);
  for (const map of Object.values(ALL_KEY_MAPS)) for (const [key] of Object.values(map)) used.add(key);
  // Keys the screens build from a code the server or the catalogue sends.
  const dynamic = Object.keys(en.translation).filter((k) =>
    /^staffing\.(errors|role|organisation|document_kind|leave_type|catalogue)\./.test(k),
  );
  for (const k of dynamic) used.add(k);

  const resolves = (table: Record<string, string>, k: string) => k in table || (`${k}_other` in table && `${k}_one` in table);

  it('reads no credentials register and holds no gate code or phase list', () => {
    // Personal documents reach the screen only through the personnel file the server returned.
    expect(sources).not.toMatch(/features\/credentials/);
    expect(sources).not.toMatch(/\/credentials\b/);
    expect(sources).not.toMatch(/credential_id/);
    expect(sources).not.toMatch(/required_by_gate|gate_code/);
    expect(sources).not.toMatch(/PHASES\b/);
    // A write that ends something carries no day of the client's.
    expect(sources).not.toMatch(/\/end`,/);
  });

  it('writes every API path in full, in the call that sends it', () => {
    const client = readFileSync(join(featureDir, 'api.ts'), 'utf-8');
    expect(client).not.toMatch(/const (BASE|p|f) =/);
    const calls = [...client.matchAll(/\bapi(Get|Post|Patch|Put|Delete)(<[^(]*>)?\(\s*(\S+)/g)];
    expect(calls.length).toBeGreaterThan(40);
    expect(calls.filter((m) => !m[3]!.startsWith('`/v1/staffing/'))).toEqual([]);
  });

  it('finds the keys it is meant to check', () => {
    // A broken extraction would make the tests below pass on nothing.
    expect(used.size).toBeGreaterThan(350);
    expect(used.has('staffing.plan.in_review_hint')).toBe(true);
    expect(used.has('staffing.errors.full_number_rejected')).toBe(true);
    expect(used.has('staffing.role.site_manager')).toBe(true);
    expect(used.has('staffing.findings.handover_missing')).toBe(true);
  });

  it.each([
    ['en', en.translation],
    ['de', de.translation],
  ] as const)('every key resolves in %s', (_lang, table) => {
    expect([...used].filter((k) => !resolves(table, k))).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = [...used].filter((k) => {
      const e = en.translation[k];
      const d = de.translation[k];
      return e && d && e === d && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('uses i18next placeholders, never the single braces the backend formats with', () => {
    for (const table of [en.translation, de.translation]) {
      const single = Object.entries(table).filter(([k, v]) => k.startsWith('staffing.') && /(^|[^{])\{\w+\}([^}]|$)/.test(v));
      expect(single).toEqual([]);
    }
  });

  it('the notification the backend sends has its title and body', () => {
    for (const table of [en.translation, de.translation]) {
      expect(table['notifications.staffing.document_expiry.title']).toBeTruthy();
      expect(table['notifications.staffing.document_expiry.body']).toContain('{{valid_until}}');
    }
  });
});
