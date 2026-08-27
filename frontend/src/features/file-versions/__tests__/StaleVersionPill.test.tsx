// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/** Unit tests for StaleVersionPill.
 *
 *  These cover what the pill itself renders: the "Drawn on V01 ·
 *  current is V02" label when the pinned version is not the chain
 *  head, and silence when the pin IS the head or is NULL.
 *
 *  They are deliberately NOT the reachability proof. Mounting a
 *  component in a test says nothing about whether a user can get to
 *  it, and this pill sat outside the import closure from the entry
 *  point for three months with these very cases passing. The path a
 *  person actually walks is exercised in
 *  ``features/file-comments/__tests__/CommentThread.test.tsx``,
 *  which mounts the thread the file preview pane renders and looks
 *  for the pill inside a comment node.
 *
 *  Split out of the former ``RevisionsPanel.test.tsx`` when
 *  RevisionsPanel was removed as a duplicate of the live
 *  ``VersionHistorySection`` in the preview pane.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => ({
  listVersions: vi.fn(),
  restoreVersion: vi.fn(),
  fileVersionKeys: { list: 'file-versions-list', detail: 'file-versions-detail' },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const fallback = (opts?.defaultValue as string) ?? key;
      return fallback.replace(/\{\{(\w+)\}\}/g, (_, name) =>
        opts && opts[name] !== undefined ? String(opts[name]) : `{{${name}}}`,
      );
    },
  }),
  // ``src/app/i18n.ts`` is pulled in transitively and calls
  // ``.use(initReactI18next)`` at module load — expose the noop plugin.
  initReactI18next: { type: '3rdParty', init: () => {} },
}));

import * as api from '../api';
import { StaleVersionPill } from '../StaleVersionPill';
import type { FileVersionResponse } from '../types';

const listMock = api.listVersions as unknown as ReturnType<typeof vi.fn>;

function makeVersion(
  overrides: Partial<FileVersionResponse> & { id: string; version_number: number },
): FileVersionResponse {
  return {
    project_id: 'proj-001',
    file_kind: 'document',
    file_id: 'file-001',
    canonical_name: 'plans.pdf',
    previous_version_id: null,
    is_current: false,
    superseded_at: null,
    superseded_by_id: null,
    notes: null,
    uploaded_by_id: null,
    uploaded_at: '2026-05-25T12:00:00Z',
    file_size: 1024,
    checksum: null,
    created_at: '2026-05-25T12:00:00Z',
    updated_at: '2026-05-25T12:00:00Z',
    ...overrides,
  };
}

function renderWithClient(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  listMock.mockReset();
  cleanup();
});

describe('StaleVersionPill', () => {
  it('renders "Drawn on V01 · current is V02" when pinned is stale', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId="v1" />,
    );
    await waitFor(() => {
      const pill = screen.getByTestId('stale-version-pill');
      expect(pill).toBeTruthy();
      expect(pill.textContent ?? '').toMatch(/V01/);
      expect(pill.textContent ?? '').toMatch(/V02/);
    });
  });

  it('renders nothing when pinned version IS the chain head', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1 }),
    ]);
    const { container } = renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId="v2" />,
    );
    await waitFor(() => {
      // No pill — the wrapper component returns null.
      expect(container.querySelector('[data-testid="stale-version-pill"]')).toBeNull();
    });
  });

  it('renders nothing when pinned version is NULL (legacy markup)', async () => {
    listMock.mockResolvedValue([
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
    ]);
    const { container } = renderWithClient(
      <StaleVersionPill fileId="file-001" kind="document" pinnedVersionId={null} />,
    );
    expect(container.querySelector('[data-testid="stale-version-pill"]')).toBeNull();
  });
});
