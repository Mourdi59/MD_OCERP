// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Reachability proof for the Epic C versioning surfaces in the file
 *  preview pane.
 *
 *  The point of this file is the mount point, not the components. Both
 *  ``StaleVersionPill`` and the pane's own ``VersionHistorySection``
 *  have tests that render them directly, and such a test cannot fail
 *  because nothing in the application mounts the thing it renders. The
 *  pill sat outside the import closure from ``src/main.tsx`` for three
 *  months with green tests of exactly that kind.
 *
 *  So this renders ``FilePreviewPane``, the component a user is looking
 *  at after picking a file on ``/files``, and requires the versioning
 *  surfaces to arrive inside it. The remaining links above this point
 *  are static unconditional imports the compiler checks:
 *  ``App.tsx`` routes ``/files`` and ``/projects/:projectId/files`` to
 *  ``FileManagerPage``, which renders this pane for the focused row.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, within, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Transport stubs. Everything the pane fans out to (projects list,
// activity feed, references, approvals) goes through the shared api
// helper; answering it with empties keeps those sections quiet so the
// assertions below are about versioning and nothing else.
//
// The empty value is an array carrying ``items``/``total`` properties
// because the pane's fan-out reads both shapes off the same helper:
// the projects and approval-workflow queries call ``.find`` on the
// result, the activity and reference queries read ``.items``. One
// value that answers both saves matching on URL strings, which would
// silently stop covering a call site the day someone renames a route.
vi.mock('@/shared/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/shared/lib/api')>(
    '@/shared/lib/api',
  );
  const empty = () => Object.assign([], { items: [], total: 0 });
  return {
    ...actual,
    apiGet: vi.fn(async () => empty()),
    apiPost: vi.fn(async () => empty()),
    apiPatch: vi.fn(async () => empty()),
    apiDelete: vi.fn(async () => empty()),
  };
});

vi.mock('@/features/file-versions/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/file-versions/api')>(
    '@/features/file-versions/api',
  );
  return { ...actual, listVersions: vi.fn(), restoreVersion: vi.fn() };
});

vi.mock('@/features/file-comments/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/file-comments/api')>(
    '@/features/file-comments/api',
  );
  return { ...actual, listThreads: vi.fn() };
});

import { FilePreviewPane } from '../FilePreviewPane';
import { listVersions } from '@/features/file-versions/api';
import { listThreads } from '@/features/file-comments/api';
import type { FileVersionResponse } from '@/features/file-versions/types';
import type { FileCommentThread } from '@/features/file-comments/types';
import type { FileRow } from '../../types';

const V1 = '00000000-0000-0000-0000-0000000000a1';
const V2 = '00000000-0000-0000-0000-0000000000a2';

function makeVersion(
  overrides: Partial<FileVersionResponse> & Pick<FileVersionResponse, 'id'>,
): FileVersionResponse {
  return {
    project_id: 'proj-1',
    file_kind: 'document',
    file_id: 'file-1',
    version_number: 1,
    canonical_name: 'plans.pdf',
    previous_version_id: null,
    is_current: false,
    superseded_at: null,
    superseded_by_id: null,
    notes: null,
    uploaded_by_id: null,
    uploaded_at: '2026-05-19T08:00:00Z',
    file_size: 2048,
    checksum: null,
    created_at: '2026-05-19T08:00:00Z',
    updated_at: '2026-05-19T08:00:00Z',
    ...overrides,
  };
}

/** A re-uploaded document: V01 superseded by V02. This is the state
 *  ``register_new_version`` leaves behind, and it is reachable in the
 *  shipped product by linking a document into a CDE container. */
function twoVersionChain(): FileVersionResponse[] {
  return [
    makeVersion({ id: V2, version_number: 2, is_current: true, previous_version_id: V1 }),
    makeVersion({
      id: V1,
      version_number: 1,
      superseded_at: '2026-05-20T08:00:00Z',
      superseded_by_id: V2,
    }),
  ];
}

/** One top-level comment, pinned to whichever revision the caller
 *  names. ``file_version_id`` is the Epic C pin the pill reads. */
function makeThreadNode(fileVersionId: string | null, body: string): FileCommentThread {
  return {
    id: 'c-1',
    project_id: 'proj-1',
    file_kind: 'document',
    file_id: 'file-1',
    file_version_snapshot: null,
    file_version_id: fileVersionId,
    parent_id: null,
    author_id: '00000000-0000-0000-0000-000000000001',
    author_name: 'Site Engineer',
    body,
    page_number: null,
    anchor_x: null,
    anchor_y: null,
    resolved: false,
    resolved_at: null,
    resolved_by_id: null,
    created_at: '2026-05-19T09:00:00Z',
    updated_at: '2026-05-19T09:00:00Z',
    mentions: [],
    replies: [],
  };
}

const ROW: FileRow = {
  id: 'file-1',
  kind: 'document',
  name: 'plans.pdf',
  project_id: 'proj-1',
  size_bytes: 2048,
  mime_type: 'application/pdf',
  extension: '.pdf',
  modified_at: '2026-05-20T08:00:00Z',
  physical_path: '/uploads/plans.pdf',
  relative_path: 'plans.pdf',
  storage_backend: 'local',
  download_url: null,
  preview_url: null,
  thumbnail_url: null,
  discipline: null,
  category: null,
  extra: {},
};

function renderPane(): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MemoryRouter initialEntries={['/files']}>
      <QueryClientProvider client={client}>
        <FilePreviewPane row={ROW} onClose={() => {}} onEmail={() => {}} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  cleanup();
  vi.mocked(listVersions).mockResolvedValue([]);
  vi.mocked(listThreads).mockResolvedValue({
    file_kind: 'document',
    file_id: 'file-1',
    threads: [],
    total: 0,
  });
});

describe('the file preview pane reaches the Epic C versioning surfaces', () => {
  it('renders the revision chain with a Make current action on the superseded row', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    renderPane();

    // The list a user actually sees for revisions is the pane's own
    // VersionHistorySection. RevisionsPanel was a second, unmounted
    // implementation of this same list and was removed.
    const list = await screen.findByTestId('version-history-list');
    expect(within(list).getByTestId('version-history-row-1')).toBeInTheDocument();
    expect(within(list).getByTestId('version-history-row-2')).toBeInTheDocument();

    // Restore is offered on the superseded row and withheld on the head.
    expect(within(list).getByTestId('version-history-restore-1')).toBeInTheDocument();
    expect(within(list).queryByTestId('version-history-restore-2')).not.toBeInTheDocument();
  });

  it('surfaces the stale pill on a comment pinned to a superseded revision', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'file-1',
      threads: [makeThreadNode(V1, 'The north elevation needs a dimension.')],
      total: 1,
    });
    renderPane();

    const node = await screen.findByTestId('comment-node-c-1');
    await waitFor(() => {
      expect(within(node).getByTestId('stale-version-pill')).toBeInTheDocument();
    });
  });

  it('shows no versioning chrome and no stale pill on a file with a single revision', async () => {
    // Negative control for both assertions above. A single-revision
    // chain has nothing to restore and nothing to be stale against, so
    // a pane that still rendered a restore button or a pill would be
    // rendering it unconditionally rather than from the data.
    vi.mocked(listVersions).mockResolvedValue([
      makeVersion({ id: V1, version_number: 1, is_current: true }),
    ]);
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'file-1',
      threads: [makeThreadNode(V1, 'Looks right to me.')],
      total: 1,
    });
    renderPane();

    const list = await screen.findByTestId('version-history-list');
    expect(within(list).getByTestId('version-history-row-1')).toBeInTheDocument();
    expect(within(list).queryByTestId('version-history-restore-1')).not.toBeInTheDocument();

    await screen.findByTestId('comment-node-c-1');
    expect(screen.queryByTestId('stale-version-pill')).not.toBeInTheDocument();
  });
});
