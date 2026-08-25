// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The saved-view thumbnail in the Model Review dock.
 *
 * The dock renders the same viewpoint thumbnail as the project issue register
 * but was written separately, and it drew every empty thumbnail with the
 * crossed-out image glyph under one label. That is wrong twice over: a
 * viewpoint with no PNG is the ordinary case and is not a failure, and a
 * snapshot that exists and would not load is a failure being reported as
 * "no snapshot captured", which is a false statement about the data.
 *
 * These tests pin the three states apart on the surface a reader sees: the
 * accessible name, and the state the element declares.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { SavedViewThumb } from '../ReviewIssuesDock';
import { fetchViewpointSnapshotBlob, type Viewpoint } from '@/features/bcf/api';

vi.mock('@/features/bcf/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/bcf/api')>();
  return { ...actual, fetchViewpointSnapshotBlob: vi.fn() };
});

const fetchSnapshot = vi.mocked(fetchViewpointSnapshotBlob);

/** A viewpoint carrying only what the thumbnail reads off it. */
function viewpoint(hasSnapshot: boolean): Viewpoint {
  return {
    guid: '3d3a2c1e-0000-4000-8000-000000000001',
    has_snapshot: hasSnapshot,
  } as Viewpoint;
}

function renderThumb(vp: Viewpoint) {
  return render(
    <SavedViewThumb
      projectId="11111111-2222-4333-8444-555555555555"
      topicGuid="7f2b8c44-0000-4000-8000-0000000000aa"
      viewpoint={vp}
      alt="Captured view snapshot"
    />,
  );
}

describe('SavedViewThumb', () => {
  beforeEach(() => {
    fetchSnapshot.mockReset();
    // jsdom has no object-URL plumbing; the component revokes on unmount.
    URL.createObjectURL = vi.fn(() => 'blob:snapshot');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not call a viewpoint without an image a failure', async () => {
    renderThumb(viewpoint(false));

    const box = await screen.findByRole('img', {
      name: 'No snapshot captured from this view.',
    });
    // The state is named on the element so the two screens that draw this
    // thumbnail can be checked against the same vocabulary.
    expect(box).toHaveAttribute('data-snapshot-state', 'no_snapshot');
    // A viewpoint that declares no PNG is never fetched, so it can never have
    // failed - the fetch is what separates this state from the next one.
    expect(fetchSnapshot).not.toHaveBeenCalled();
  });

  it('says a snapshot was lost rather than never taken when the fetch fails', async () => {
    fetchSnapshot.mockRejectedValue(new Error('Snapshot fetch failed (HTTP 404)'));

    renderThumb(viewpoint(true));

    const box = await screen.findByRole('img', { name: 'Snapshot could not be loaded.' });
    expect(box).toHaveAttribute('data-snapshot-state', 'failed');
    // The old wording claimed the view never carried an image. It did.
    expect(
      screen.queryByRole('img', { name: 'No snapshot captured from this view.' }),
    ).toBeNull();
  });

  it('draws the picture when there is one, so the empty states are not the only path', async () => {
    fetchSnapshot.mockResolvedValue(new Blob([new Uint8Array([137, 80, 78, 71])]));

    renderThumb(viewpoint(true));

    await waitFor(() => {
      const img = screen.getByAltText('Captured view snapshot');
      expect(img.tagName).toBe('IMG');
      expect(img).toHaveAttribute('src', 'blob:snapshot');
    });
    expect(document.querySelector('[data-snapshot-state]')).toBeNull();
  });
});
