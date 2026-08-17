// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Render-level coverage for the "Open from project files" picker.
 *
 * The pure matcher is tested exhaustively in
 * ``shared/lib/projectFileFormats.test.ts``. These tests cover what that one
 * cannot: that the component actually applies the matcher to the API payload,
 * distinguishes its two empty states, and labels a conversion-gated format
 * honestly on screen. A regression in any of those is invisible to the pure
 * tests but very visible to the user.
 *
 * The documents API is stubbed so the test runs fully offline.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

const fetchDocumentsMock = vi.fn();
const fetchFileListMock = vi.fn();

vi.mock('@/features/documents/api', () => ({
  fetchDocuments: (projectId: string) => fetchDocumentsMock(projectId),
  downloadDocumentBlob: vi.fn(),
}));

vi.mock('@/features/file-manager/api', () => ({
  fetchFileList: (projectId: string, filters: unknown) => fetchFileListMock(projectId, filters),
}));

import { ProjectFilePicker } from './ProjectFilePicker';
import type { DocumentItem } from '@/features/documents/api';
import {
  BIM_VIEWER_FORMATS,
  DWG_TAKEOFF_FORMATS,
  PDF_TAKEOFF_FORMATS,
  type AcceptedFormat,
} from '@/shared/lib/projectFileFormats';

/** Minimal stored-document row in the shape the CDE API really returns:
 *  the original filename lives in ``name``, and ``mime_type`` is nullable. */
function makeDoc(id: string, name: string, mime: string | null = null) {
  return {
    id,
    project_id: 'p1',
    name,
    description: null,
    category: 'drawing',
    file_size: 2048,
    mime_type: mime,
    version: 1,
    is_current_revision: true,
    parent_document_id: null,
    uploaded_by: null,
    created_at: '2026-07-20T10:00:00Z',
    updated_at: '2026-07-20T10:00:00Z',
  };
}

/** Wrap rows in the envelope the register really answers with.
 *
 *  ``total`` defaults to the number of rows handed in, which is the complete
 *  case; a test about truncation passes a bigger one. */
function docPage(items: ReturnType<typeof makeDoc>[], total = items.length) {
  return { items, total, offset: 0, limit: 50 };
}

/** Overrides for the documents-only shape of the picker. Spelled out rather
 *  than derived from the component's props, which are a union since federation
 *  landed and would distribute into a shape TypeScript cannot spread. */
interface PickerOverrides {
  open?: boolean;
  accepted?: readonly AcceptedFormat[];
  onPick?: (doc: DocumentItem) => void;
}

function renderPicker(props: PickerOverrides = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectFilePicker
          open
          onClose={vi.fn()}
          projectId="p1"
          accepted={DWG_TAKEOFF_FORMATS}
          onPick={vi.fn()}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProjectFilePicker', () => {
  beforeEach(() => {
    fetchDocumentsMock.mockReset();
    fetchFileListMock.mockReset();
  });

  it('lists only the stored files the calling module can open', async () => {
    /* The whole point of the feature: a DWG module must show the project's
     * drawings and hide its PDFs and spreadsheets, so the user is never
     * offered a file that would fail to load. */
    fetchDocumentsMock.mockResolvedValue(
      docPage([
        makeDoc('1', 'A-101.rev2.dwg'),
        makeDoc('2', 'Specification.pdf'),
        makeDoc('3', 'Costs.xlsx'),
        makeDoc('4', 'Site-plan.DXF'),
      ]),
    );
    renderPicker();

    await waitFor(() => expect(screen.getByText('A-101.rev2.dwg')).toBeTruthy());
    // Uppercase extension still matches - the row is there.
    expect(screen.getByText('Site-plan.DXF')).toBeTruthy();
    expect(screen.queryByText('Specification.pdf')).toBeNull();
    expect(screen.queryByText('Costs.xlsx')).toBeNull();
  });

  it('hands the picked document back to the caller', async () => {
    /* The picker itself never opens anything - it reports the choice and the
     * module decides. If this stopped firing, every wired module would look
     * fine and quietly do nothing on click. */
    const onPick = vi.fn();
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'A-101.dwg')]));
    renderPicker({ onPick });

    await waitFor(() => expect(screen.getByText('A-101.dwg')).toBeTruthy());
    fireEvent.click(screen.getByText('A-101.dwg'));
    expect(onPick).toHaveBeenCalledTimes(1);
    // Indexing is checked (`noUncheckedIndexedAccess`), and the assertion above
    // already pins that the call happened, so read the argument defensively
    // rather than asserting non-null.
    expect(onPick.mock.calls[0]?.[0]?.id).toBe('1');
  });

  it('shows the "nothing compatible" empty state, not the search one', async () => {
    /* Two different dead ends need two different messages. A project holding
     * only PDFs must be told to add a DWG in Files - telling it "no match for
     * your search" when the search box is empty would be nonsense. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'Specification.pdf')]));
    renderPicker();

    await waitFor(() =>
      expect(screen.getByText('No compatible file in this project yet')).toBeTruthy(),
    );
    // And it points the user at where to fix it.
    expect(screen.getByText('Go to Files')).toBeTruthy();
    expect(screen.queryByText('No file matches your search.')).toBeNull();
  });

  it('shows the search empty state when a compatible file exists but is filtered out', async () => {
    /* The mirror case. Here the project DOES hold an openable file, so the
     * fix is to clear the search - not to go and upload something. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'A-101.dwg')]));
    renderPicker();

    await waitFor(() => expect(screen.getByText('A-101.dwg')).toBeTruthy());
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'zzz' } });

    await waitFor(() => expect(screen.getByText('No file matches your search.')).toBeTruthy());
    expect(screen.queryByText('No compatible file in this project yet')).toBeNull();
  });

  it('labels a conversion-gated format instead of implying an instant open', async () => {
    /* Project rule: IFC is never parsed natively, it is viewable only after
     * the DDC cad2data conversion. The row must say so. A silent offer here
     * would be the exact "do not offer a file that will fail to open"
     * failure the feature was asked to avoid. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'Tower.ifc')]));
    renderPicker({ accepted: BIM_VIEWER_FORMATS });

    await waitFor(() => expect(screen.getByText('Tower.ifc')).toBeTruthy());
    expect(screen.getByText('Converts first')).toBeTruthy();
  });

  it('labels a format that another module handles as a handoff', async () => {
    /* The BIM viewer forwards DWG to DWG takeoff rather than opening it as a
     * 3D model. Saying so is more honest than a bare row that appears to
     * promise a 3D view. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'Level-02.dwg')]));
    renderPicker({ accepted: BIM_VIEWER_FORMATS });

    await waitFor(() => expect(screen.getByText('Level-02.dwg')).toBeTruthy());
    expect(screen.getByText('Opens in another module')).toBeTruthy();
  });

  it('says how much of the register it is showing when the page is cut', async () => {
    /* A picker cannot page, so the file the user came for may simply not be
     * on the list. Before the envelope the modal looked identical whether it
     * held the whole project or its first 50 files. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'A-101.dwg')], 340));
    renderPicker();

    await waitFor(() => expect(screen.getByText('A-101.dwg')).toBeTruthy());
    expect(screen.getByTestId('truncation-notice').textContent).toContain('340');
  });

  it('stays silent when the page holds the whole register', async () => {
    /* The other half of the claim above: the notice must not appear on a
     * complete list, or it stops meaning anything. */
    fetchDocumentsMock.mockResolvedValue(docPage([makeDoc('1', 'A-101.dwg')]));
    renderPicker();

    await waitFor(() => expect(screen.getByText('A-101.dwg')).toBeTruthy());
    expect(screen.queryByTestId('truncation-notice')).toBeNull();
  });

  it('does not query the documents API while closed', async () => {
    /* The picker is mounted permanently by its callers, so an unconditional
     * query would fire a documents request on every viewer page load. */
    fetchDocumentsMock.mockResolvedValue(docPage([]));
    renderPicker({ open: false });
    expect(fetchDocumentsMock).not.toHaveBeenCalled();
  });
});

/* ── Federated mode ─────────────────────────────────────────────────────
 *
 * The defect these cover: "project files" was never one store. PDF takeoff
 * keeps its sheets in its own table, so a plan open in the takeoff viewer
 * could not be found by name in a dialog that promised the project's files.
 */

/** One row of the file-manager listing, in the shape the endpoint returns. */
function makeFileRow(
  id: string,
  kind: 'document' | 'takeoff',
  name: string,
  extra: Record<string, unknown> = {},
) {
  return {
    id,
    kind,
    name,
    project_id: 'p1',
    size_bytes: 4096,
    mime_type: 'application/pdf',
    extension: 'pdf',
    modified_at: '2026-08-01T09:00:00Z',
    physical_path: `/data/${id}.pdf`,
    relative_path: `${id}.pdf`,
    storage_backend: 'local' as const,
    download_url: `/api/v1/${kind === 'takeoff' ? 'takeoff/documents' : 'documents'}/${id}/download/`,
    preview_url: null,
    thumbnail_url: null,
    discipline: null,
    category: null,
    extra,
  };
}

function renderFederatedPicker(
  props: { onPick?: (file: unknown) => void; open?: boolean } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectFilePicker
          open
          onClose={vi.fn()}
          projectId="p1"
          accepted={PDF_TAKEOFF_FORMATS}
          moduleKinds={['takeoff']}
          onPick={vi.fn()}
          {...props}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProjectFilePicker (federated)', () => {
  beforeEach(() => {
    fetchDocumentsMock.mockReset();
    fetchFileListMock.mockReset();
  });

  it('finds a takeoff-only document by the name shown on screen', async () => {
    /* THE REPORTED BUG, exactly: the sheet open in the takeoff viewer lives in
     * takeoff's own store, and searching the dialog for a word from its name
     * returned nothing. The search now goes to the federated endpoint, which
     * looks in both stores, and the row comes back. */
    fetchFileListMock.mockImplementation((_projectId: string, filters: { q?: string }) => {
      const rows = [
        makeFileRow('d1', 'document', 'Baugenehmigung.pdf'),
        makeFileRow('t1', 'takeoff', 'A-2.01 Grundriss Erdgeschoss.pdf'),
      ].filter((r) => !filters.q || r.name.toLowerCase().includes(filters.q.toLowerCase()));
      return Promise.resolve({ project_id: 'p1', items: rows, total: rows.length, limit: 500, offset: 0 });
    });

    renderFederatedPicker();
    await waitFor(() => expect(screen.getByText('A-2.01 Grundriss Erdgeschoss.pdf')).toBeTruthy());

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Grundriss' } });

    await waitFor(() => expect(screen.queryByText('Baugenehmigung.pdf')).toBeNull());
    expect(screen.getByText('A-2.01 Grundriss Erdgeschoss.pdf')).toBeTruthy();
    // The search reached the server rather than filtering one page in the
    // browser - the whole reason a takeoff row can be found at all.
    await waitFor(() =>
      expect(
        fetchFileListMock.mock.calls.some((call) => call[1]?.q === 'Grundriss'),
      ).toBe(true),
    );
  });

  it('asks the server for both stores in one request', async () => {
    /* Federation is server-side on purpose: merging two paginated listings in
     * the browser would search page one of each and call it "the project". */
    fetchFileListMock.mockResolvedValue({
      project_id: 'p1',
      items: [makeFileRow('t1', 'takeoff', 'Handaufmass.pdf')],
      total: 1,
      limit: 500,
      offset: 0,
    });

    renderFederatedPicker();
    await waitFor(() => expect(screen.getByText('Handaufmass.pdf')).toBeTruthy());

    expect(fetchDocumentsMock).not.toHaveBeenCalled();
    expect(fetchFileListMock).toHaveBeenCalledTimes(1);
    expect(fetchFileListMock.mock.calls[0]?.[1]?.kinds).toEqual(['document', 'takeoff']);
    // One accepted format, so the server filters it and `total` counts the
    // same rows the list shows.
    expect(fetchFileListMock.mock.calls[0]?.[1]?.extension).toBe('pdf');
  });

  it('names the store each row came from', async () => {
    /* Two groups with the same file name in each is the honest picture on a
     * demo project; an unlabelled merged list would not be. */
    fetchFileListMock.mockResolvedValue({
      project_id: 'p1',
      items: [
        makeFileRow('d1', 'document', 'A-2.01 Grundriss Erdgeschoss.pdf'),
        makeFileRow('t1', 'takeoff', 'A-2.01 Grundriss Erdgeschoss.pdf'),
      ],
      total: 2,
      limit: 500,
      offset: 0,
    });

    renderFederatedPicker();
    await waitFor(() => expect(screen.getAllByText('A-2.01 Grundriss Erdgeschoss.pdf')).toHaveLength(2));
    // No locale bundle is loaded here, so i18next renders each heading's
    // fallback - the kind id. On screen these are `files.category.document`
    // and `files.category.takeoff`, already translated in every locale.
    expect(screen.getByText('document')).toBeTruthy();
    expect(screen.getByText('takeoff')).toBeTruthy();
  });

  it('marks a project file the module already holds and reopens that work', async () => {
    /* The server folds a takeoff document onto the project file it was made
     * from and hands over its id. Picking the row must reopen the existing
     * takeoff document, not ask for a second one. */
    fetchFileListMock.mockResolvedValue({
      project_id: 'p1',
      items: [makeFileRow('d1', 'document', 'A-2.01 Grundriss.pdf', { takeoff_document_id: 't9' })],
      total: 1,
      limit: 500,
      offset: 0,
    });
    const onPick = vi.fn();

    renderFederatedPicker({ onPick });
    await waitFor(() => expect(screen.getByText('A-2.01 Grundriss.pdf')).toBeTruthy());
    expect(screen.getByText('Already in this module')).toBeTruthy();

    fireEvent.click(screen.getByText('A-2.01 Grundriss.pdf'));
    expect(onPick).toHaveBeenCalledTimes(1);
    expect(onPick.mock.calls[0]?.[0]).toMatchObject({
      id: 'd1',
      kind: 'document',
      takeoff_document_id: 't9',
    });
  });

  it('admits when it is showing only part of the project', async () => {
    /* A picker cannot page, so the one honest thing it can do is say how much
     * of the listing is on screen. */
    fetchFileListMock.mockResolvedValue({
      project_id: 'p1',
      items: [makeFileRow('t1', 'takeoff', 'Handaufmass.pdf')],
      total: 240,
      limit: 500,
      offset: 0,
    });

    renderFederatedPicker();
    await waitFor(() => expect(screen.getByTestId('truncation-notice')).toBeTruthy());
  });

  it('does not query the file manager while closed', async () => {
    fetchFileListMock.mockResolvedValue({ project_id: 'p1', items: [], total: 0, limit: 500, offset: 0 });
    renderFederatedPicker({ open: false });
    expect(fetchFileListMock).not.toHaveBeenCalled();
  });
});
