// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Tests for the file-comments CommentThread component. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CommentThread } from '../CommentThread';
import type {
  FileCommentListResponse,
  FileCommentThread as ThreadNode,
} from '../types';

vi.mock('../api', async () => {
  const actual =
    await vi.importActual<typeof import('../api')>('../api');
  return {
    ...actual,
    listThreads: vi.fn(),
    updateComment: vi.fn(),
    deleteComment: vi.fn(),
    createComment: vi.fn(),
  };
});

// The thread nodes carry an Epic C version pin, and CommentThread mounts
// StaleVersionPill for each one. The pill resolves the chain through the
// file-versions query, so that transport is stubbed here too — otherwise
// every test in this file would fire a real request for it.
vi.mock('@/features/file-versions/api', async () => {
  const actual = await vi.importActual<typeof import('@/features/file-versions/api')>(
    '@/features/file-versions/api',
  );
  return {
    ...actual,
    listVersions: vi.fn(),
    restoreVersion: vi.fn(),
  };
});

import { listThreads } from '../api';
import { listVersions } from '@/features/file-versions/api';
import type { FileVersionResponse } from '@/features/file-versions/types';

function makeVersion(
  overrides: Partial<FileVersionResponse> & Pick<FileVersionResponse, 'id'>,
): FileVersionResponse {
  return {
    project_id: 'p-1',
    file_kind: 'document',
    file_id: 'f-1',
    version_number: 1,
    canonical_name: 'plan.pdf',
    previous_version_id: null,
    is_current: false,
    superseded_at: null,
    superseded_by_id: null,
    notes: null,
    uploaded_by_id: null,
    uploaded_at: '2026-05-19T08:00:00Z',
    file_size: 1024,
    checksum: null,
    created_at: '2026-05-19T08:00:00Z',
    updated_at: '2026-05-19T08:00:00Z',
    ...overrides,
  };
}

function makeNode(overrides: Partial<ThreadNode> = {}): ThreadNode {
  return {
    id: overrides.id ?? 'c-1',
    project_id: 'p-1',
    file_kind: 'document',
    file_id: 'f-1',
    file_version_id: overrides.file_version_id ?? null,
    file_version_snapshot: null,
    parent_id: null,
    author_id: overrides.author_id ?? '00000000-0000-0000-0000-000000000001',
    author_name:
      overrides.author_name !== undefined ? overrides.author_name : 'Alice Smith',
    body: overrides.body ?? 'Top-level note.',
    page_number: null,
    anchor_x: null,
    anchor_y: null,
    resolved: overrides.resolved ?? false,
    resolved_at: null,
    resolved_by_id: null,
    created_at: '2026-05-19T08:00:00Z',
    updated_at: '2026-05-19T08:00:00Z',
    mentions: [],
    replies: overrides.replies ?? [],
  };
}

function renderWithClient(ui: React.ReactNode): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  // Default: an empty chain, so the pill stays invisible for every test
  // that is not about it. Cases below override this per test.
  vi.mocked(listVersions).mockResolvedValue([]);
});

afterEach(() => {
  vi.resetAllMocks();
});

describe('CommentThread', () => {
  it('renders the heading with the thread count and the empty state when there are no threads', async () => {
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [],
      total: 0,
    } satisfies FileCommentListResponse);

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      // The i18n test mock returns defaultValue verbatim, so the
      // ``{{count}}`` placeholder is not interpolated; we just verify
      // the heading text root is present.
      expect(screen.getByText(/Comments/)).toBeInTheDocument();
    });
    // EmptyState appears for the zero-row response.
    expect(screen.getByText(/No comments yet/)).toBeInTheDocument();
  });

  it('renders nested replies and shows the Reply affordance for non-tombstoned nodes', async () => {
    const reply = makeNode({ id: 'c-2', parent_id: 'c-1', body: 'Reply body.' });
    const top = makeNode({ id: 'c-1', replies: [reply] });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('Top-level note.')).toBeInTheDocument();
    });
    expect(screen.getByText('Reply body.')).toBeInTheDocument();
    expect(screen.getByTestId('comment-reply-c-1')).toBeInTheDocument();
    expect(screen.getByTestId('comment-reply-c-2')).toBeInTheDocument();
    // Resolve only on top-level.
    expect(screen.getByTestId('comment-resolve-c-1')).toBeInTheDocument();
    expect(screen.queryByTestId('comment-resolve-c-2')).not.toBeInTheDocument();
  });

  it('highlights @mentions inside the rendered body', async () => {
    const top = makeNode({ id: 'c-1', body: 'Hey @alice please look.' });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    // The mention is wrapped in its own element with the highlight bg.
    const mention = within(node).getByText('@alice');
    expect(mention).toBeInTheDocument();
    expect(mention.tagName).toBe('SPAN');
  });

  it('renders the resolved author name instead of the raw id', async () => {
    const top = makeNode({
      id: 'c-1',
      author_id: '11112222-3333-4444-5555-666677778888',
      author_name: 'Alice Smith',
    });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    expect(within(node).getByText('Alice Smith')).toBeInTheDocument();
    // The 8-char id prefix must no longer appear in the byline.
    expect(within(node).queryByText(/^11112222$/)).not.toBeInTheDocument();
  });

  it('falls back to the short id when author_name is null (legacy payload)', async () => {
    const top = makeNode({
      id: 'c-1',
      author_id: '11112222-3333-4444-5555-666677778888',
      author_name: null,
    });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('comment-node-c-1')).toBeInTheDocument();
    });
    const node = screen.getByTestId('comment-node-c-1');
    expect(within(node).getByText('11112222')).toBeInTheDocument();
  });

  it('renders a tombstone for [deleted] bodies and hides the Reply affordance', async () => {
    const top = makeNode({ id: 'c-1', body: '[deleted]' });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [top],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId="00000000-0000-0000-0000-000000000001"
        canResolve
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Comment deleted/)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('comment-reply-c-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('comment-resolve-c-1')).not.toBeInTheDocument();
  });
});

/* ── Epic C staleness warning, reached through the thread ─────────────
   These cases deliberately never import StaleVersionPill. They mount
   CommentThread, the component the file preview pane actually renders,
   and look for the pill inside a comment node. A test that imported the
   pill directly would prove the pill renders and prove nothing about a
   user being able to see it, which is how it came to sit outside the
   reachability closure in the first place. */

describe('CommentThread version staleness', () => {
  const V1 = '00000000-0000-0000-0000-0000000000a1';
  const V2 = '00000000-0000-0000-0000-0000000000a2';

  /** A two-row chain: V01 superseded by V02, which is current. This is
   *  what ``register_new_version`` leaves behind after a re-upload. */
  function twoVersionChain(): FileVersionResponse[] {
    return [
      makeVersion({
        id: V2,
        version_number: 2,
        is_current: true,
        previous_version_id: V1,
      }),
      makeVersion({
        id: V1,
        version_number: 1,
        is_current: false,
        superseded_at: '2026-05-20T08:00:00Z',
        superseded_by_id: V2,
      }),
    ];
  }

  it('surfaces the stale pill inside a comment pinned to a superseded revision', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [makeNode({ id: 'c-1', file_version_id: V1 })],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    const node = await screen.findByTestId('comment-node-c-1');
    // Scoped to the node: the pill has to hang off the comment the user
    // is reading, not merely exist somewhere on the surface.
    await waitFor(() => {
      expect(within(node).getByTestId('stale-version-pill')).toBeInTheDocument();
    });
  });

  it('stays silent when the comment is pinned to the current revision', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [makeNode({ id: 'c-1', file_version_id: V2 })],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await screen.findByTestId('comment-node-c-1');
    await waitFor(() => {
      expect(vi.mocked(listVersions)).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('stale-version-pill')).not.toBeInTheDocument();
  });

  it('stays silent for a legacy comment with no version pin', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [makeNode({ id: 'c-1', file_version_id: null })],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    await screen.findByTestId('comment-node-c-1');
    expect(screen.queryByTestId('stale-version-pill')).not.toBeInTheDocument();
  });

  it('warns on a stale reply nested under a current top-level comment', async () => {
    vi.mocked(listVersions).mockResolvedValue(twoVersionChain());
    const reply = makeNode({
      id: 'c-2',
      parent_id: 'c-1',
      body: 'Reply body.',
      file_version_id: V1,
    });
    vi.mocked(listThreads).mockResolvedValue({
      file_kind: 'document',
      file_id: 'f-1',
      threads: [makeNode({ id: 'c-1', file_version_id: V2, replies: [reply] })],
      total: 1,
    });

    renderWithClient(
      <CommentThread
        projectId="p-1"
        fileKind="document"
        fileId="f-1"
        currentUserId={null}
      />,
    );

    const replyNode = await screen.findByTestId('comment-node-c-2');
    await waitFor(() => {
      expect(within(replyNode).getByTestId('stale-version-pill')).toBeInTheDocument();
    });
    // The parent is on the chain head, so exactly one pill on screen.
    expect(screen.getAllByTestId('stale-version-pill')).toHaveLength(1);
  });
});
