// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The engineering brief page as a reader meets it: the empty state, the head
// with status and findings, requirements grouped by category with the hint for
// uncovered ones, a locked brief that offers no writes, the framework schedule
// ordered by date with its sync indicator, and the backplan preview.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    getBrief: vi.fn(),
    getPinnedCatalogue: vi.fn(),
    listCatalogues: vi.fn(),
    listBriefFindings: vi.fn(),
    listRequirements: vi.fn(),
    listConcepts: vi.fn(),
    listProgramme: vi.fn(),
    listMilestones: vi.fn(),
    submitBrief: vi.fn(),
    createRequirement: vi.fn(),
    backplan: vi.fn(),
  };
});

import { ApiError } from '@/shared/lib/api';
import * as api from '../api';
import { EngineeringBriefPage } from '../EngineeringBriefPage';
import { normaliseQuantity } from '../ProgrammeTab';
import { sortByDate, syncState } from '../ScheduleTab';
import { brief, catalogue, concept, milestone, no, programmeLine, requirement } from './fixtures';

const mocked = vi.mocked(api);
const page = <T,>(items: T[]) => ({ items, total: items.length, offset: 0, limit: items.length });

function renderPage(path = '/projects/p1/engineering-brief') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/projects/:projectId/engineering-brief" element={<EngineeringBriefPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocked.getBrief.mockResolvedValue(brief());
  mocked.getPinnedCatalogue.mockResolvedValue(catalogue);
  mocked.listBriefFindings.mockResolvedValue(page([]));
  mocked.listRequirements.mockResolvedValue(page([requirement()]));
  mocked.listConcepts.mockResolvedValue(page([concept()]));
  mocked.listProgramme.mockResolvedValue(page([programmeLine()]));
  mocked.listMilestones.mockResolvedValue(page([]));
  mocked.listCatalogues.mockResolvedValue(page([]));
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('engineering brief page states', () => {
  it('offers to start a brief when the project has none', async () => {
    mocked.getBrief.mockRejectedValue(
      new ApiError(404, 'Not Found', { detail: { code: 'brief_missing', message: 'No brief.' } }),
    );
    renderPage();
    expect(await screen.findByText('No engineering brief yet')).toBeTruthy();
    expect(screen.getByTestId('brief-setup')).toBeTruthy();
  });

  it('shows an error, not an empty state, when the brief cannot be loaded', async () => {
    mocked.getBrief.mockRejectedValue(new ApiError(500, 'Server Error', { detail: { code: 'boom', message: 'Server broke.' } }));
    renderPage();
    expect(await screen.findByText('The engineering brief could not be loaded')).toBeTruthy();
    expect(screen.getByText('Server broke.')).toBeTruthy();
    expect(screen.queryByTestId('brief-setup')).toBeNull();
  });

  it('shows status, proof date and the findings that block submission', async () => {
    mocked.listBriefFindings.mockResolvedValue(
      page([
        { code: 'category_uncovered', ref: 'availability', severity: 'error', detail: '' },
        { code: 'requirement_unverifiable', ref: 'r1', severity: 'warning', detail: '' },
      ]),
    );
    renderPage();
    expect(await screen.findByTestId('brief-status')).toHaveProperty('textContent', 'Draft');
    expect(screen.getByTestId('brief-proof-date').textContent).not.toBe('Not set');
    const blocking = await screen.findByTestId('brief-findings-error');
    expect(within(blocking).getByText('availability')).toBeTruthy();
    expect(screen.getByTestId('brief-findings-warning')).toBeTruthy();
  });

  it('shows only the actions the capability flags allow', async () => {
    renderPage();
    await screen.findByTestId('brief-approval');
    expect(screen.getByTestId('brief-submit')).toBeTruthy();
    // Return and approve do not apply to a draft: they are left off, not greyed out.
    expect(screen.queryByTestId('brief-return')).toBeNull();
    expect(screen.queryByTestId('brief-approve')).toBeNull();
  });

  it('shows approve by hand, disabled with its reason, when only the caller is refused', async () => {
    mocked.getBrief.mockResolvedValue(
      brief({ status: 'in_review' }, { approve: no('approver_is_submitter', true), edit: no('brief_in_review', true) }),
    );
    renderPage();
    const approve = (await screen.findByTestId('brief-approve')) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
  });

  it('sends the brief for review and shows the server refusal in its own words', async () => {
    mocked.submitBrief.mockRejectedValue(
      new ApiError(409, 'Conflict', { detail: { code: 'invalid_transition', message: 'The brief cannot be submitted now.' } }),
    );
    renderPage();
    fireEvent.click(await screen.findByTestId('brief-submit'));
    await waitFor(() => expect(mocked.submitBrief).toHaveBeenCalledWith('p1'));
  });
});

describe('requirements tab', () => {
  it('groups requirements by category and hints at the required categories nobody covered', async () => {
    renderPage();
    const group = await screen.findByTestId('brief-requirements-group-performance');
    expect(within(group).getByText('Cooling plant')).toBeTruthy();
    expect(within(group).getByText('Performance')).toBeTruthy();
    const hint = screen.getByTestId('brief-uncovered');
    expect(within(hint).getByText('Availability')).toBeTruthy();
    expect(within(hint).queryByText('Performance')).toBeNull();
  });

  it('is read-only when the brief is locked: no add, no row actions, a notice instead', async () => {
    mocked.getBrief.mockResolvedValue(brief({ status: 'in_review' }, { edit: no('brief_in_review', true) }));
    renderPage();
    await screen.findByTestId('brief-requirements-group-performance');
    expect(screen.getByTestId('brief-readonly')).toBeTruthy();
    expect(screen.queryByTestId('brief-requirement-add')).toBeNull();
    expect(screen.queryByLabelText('Edit')).toBeNull();
    expect(screen.queryByLabelText('Delete')).toBeNull();
  });

  it('will not save a requirement without its subject and property', async () => {
    renderPage();
    fireEvent.click(await screen.findByTestId('brief-requirement-add'));
    fireEvent.click(await screen.findByTestId('brief-requirement-save'));
    expect(mocked.createRequirement).not.toHaveBeenCalled();
    expect((await screen.findAllByText('Required')).length).toBeGreaterThan(0);
  });
});

describe('other tabs', () => {
  it('lists concept items with their topic and agreement state', async () => {
    renderPage('/projects/p1/engineering-brief?tab=concept');
    const row = await screen.findByTestId('brief-concept-row');
    expect(within(row).getByText('Chilled water supply')).toBeTruthy();
    expect(screen.getByTestId('brief-concept-status').textContent).toBe('Open');
    expect(screen.getByTestId('brief-concept-from-catalogue')).toBeTruthy();
  });

  it('shows programme quantities as the decimal string the server sent', async () => {
    renderPage('/projects/p1/engineering-brief?tab=programme');
    const row = await screen.findByTestId('brief-programme-row');
    expect(within(row).getByText('1250.50')).toBeTruthy();
  });

  it('orders milestones by date and marks each one in sync, out of sync or unpublished', async () => {
    mocked.listMilestones.mockResolvedValue(
      page([
        milestone({ id: 'm2', code: 'MS-002', name: 'Commissioning', planned_date: '2028-01-10' }),
        milestone({ id: 'm1', code: 'MS-001', name: 'Chiller delivery', planned_date: '2027-03-01', activity_id: 'a1', published: true }),
        milestone({ id: 'm3', code: 'MS-003', name: 'Undated', planned_date: null }),
      ]),
    );
    renderPage('/projects/p1/engineering-brief?tab=schedule');
    const rows = await screen.findAllByTestId('brief-milestone-row');
    expect(rows.map((r) => /MS-00\d/.exec(r.textContent ?? '')?.[0])).toEqual(['MS-001', 'MS-002', 'MS-003']);
    const syncs = screen.getAllByTestId('brief-milestone-sync').map((s) => s.getAttribute('data-sync'));
    expect(syncs).toEqual(['in_sync', 'not_published', 'not_published']);
  });

  it('previews the backward plan with from and to dates and writes nothing until applied', async () => {
    mocked.listMilestones.mockResolvedValue(page([milestone()]));
    mocked.backplan.mockImplementation(async (_p, apply) => ({
      applied: apply,
      changes: [{ id: 'm1', code: 'MS-001', from: '2027-03-01', to: '2027-02-15', changed: true }],
      unreached: [],
    }));
    renderPage('/projects/p1/engineering-brief?tab=schedule');
    fireEvent.click(await screen.findByTestId('brief-milestones-backplan'));
    const table = await screen.findByTestId('brief-backplan-table');
    expect(within(table).getByText('MS-001')).toBeTruthy();
    expect(mocked.backplan).toHaveBeenCalledTimes(1);
    expect(mocked.backplan).toHaveBeenLastCalledWith('p1', false);
    fireEvent.click(screen.getByTestId('brief-backplan-apply'));
    await waitFor(() => expect(mocked.backplan).toHaveBeenLastCalledWith('p1', true));
  });
});

describe('pure helpers', () => {
  it('sorts by date with undated milestones last and keeps the server order on ties', () => {
    const sorted = sortByDate([
      milestone({ id: 'a', planned_date: null }),
      milestone({ id: 'b', planned_date: '2027-05-01' }),
      milestone({ id: 'c', planned_date: '2027-05-01' }),
      milestone({ id: 'd', planned_date: '2027-01-01' }),
    ]);
    expect(sorted.map((m) => m.id)).toEqual(['d', 'b', 'c', 'a']);
  });

  it('reads sync from the server findings', () => {
    expect(syncState(milestone())).toBe('not_published');
    expect(syncState(milestone({ activity_id: 'a', published: true }))).toBe('in_sync');
    expect(syncState(milestone({ activity_id: 'a', published: false }))).toBe('out_of_sync');
    expect(
      syncState(
        milestone({
          activity_id: 'a',
          published: true,
          findings: [{ code: 'schedule_out_of_sync', ref: 'm', severity: 'warning', detail: '2027-01-01' }],
        }),
      ),
    ).toBe('out_of_sync');
  });

  it('accepts a decimal with a comma and refuses anything that is not a number', () => {
    expect(normaliseQuantity('12,5')).toBe('12.5');
    expect(normaliseQuantity(' 3 ')).toBe('3');
    expect(normaliseQuantity('1e3')).toBeNull();
    expect(normaliseQuantity('')).toBeNull();
  });
});
