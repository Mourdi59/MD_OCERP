// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The viewpoint thumbnail in the project issue register.
 *
 * This screen and the model review dock draw the same thumbnail from the same
 * data, and the answer to "which nothing is this" now lives in one module that
 * both of them read. Nothing asserted that this one still reads it. A rewrite
 * that gave the register a private answer again would reintroduce exactly the
 * split we removed - one screen fixed, one screen quietly wrong - and every
 * other test would stay green while it happened.
 *
 * So these drive the component through the DOM and pin the three states apart
 * on what a reader actually gets: the accessible name, and the state the
 * element declares. The sibling test does the same for the dock.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { BcfSnapshot } from './BcfIssuesPanel';
import { fetchViewpointSnapshotBlob, type Viewpoint } from './api';

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>();
  return { ...actual, fetchViewpointSnapshotBlob: vi.fn() };
});

const fetchSnapshot = vi.mocked(fetchViewpointSnapshotBlob);

/** A viewpoint carrying only what the thumbnail reads off it. */
function viewpoint(hasSnapshot: boolean): Viewpoint {
  return {
    guid: '9c1f7e20-0000-4000-8000-0000000000b1',
    has_snapshot: hasSnapshot,
  } as Viewpoint;
}

function renderSnapshot(vp: Viewpoint | null) {
  return render(
    <BcfSnapshot
      projectId="11111111-2222-4333-8444-555555555555"
      topicGuid="7f2b8c44-0000-4000-8000-0000000000aa"
      viewpoint={vp}
      alt="Issue viewpoint snapshot"
      withCaption
    />,
  );
}

describe('BcfSnapshot', () => {
  beforeEach(() => {
    fetchSnapshot.mockReset();
    // jsdom has no object-URL plumbing; the component revokes on unmount.
    URL.createObjectURL = vi.fn(() => 'blob:register-snapshot');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('does not call a viewpoint without an image a failure', async () => {
    renderSnapshot(viewpoint(false));

    const box = await screen.findByRole('img', {
      name: 'No snapshot captured from this view.',
    });
    expect(box).toHaveAttribute('data-snapshot-state', 'no_snapshot');
    // A viewpoint that declares no PNG is never fetched, so it can never have
    // failed - the fetch is what separates this state from the next one.
    expect(fetchSnapshot).not.toHaveBeenCalled();
  });

  it('says a snapshot was lost rather than never taken when the fetch fails', async () => {
    fetchSnapshot.mockRejectedValue(new Error('Snapshot fetch failed (HTTP 404)'));

    renderSnapshot(viewpoint(true));

    const box = await screen.findByRole('img', { name: 'Snapshot could not be loaded.' });
    expect(box).toHaveAttribute('data-snapshot-state', 'failed');
    // Claiming the view never carried an image would be untrue: it did.
    expect(
      screen.queryByRole('img', { name: 'No snapshot captured from this view.' }),
    ).toBeNull();
  });

  it('calls an issue with no viewpoint neither missing nor broken', async () => {
    // The register can be handed a null viewpoint, so unlike the dock this
    // screen reaches the third state for real rather than in theory.
    renderSnapshot(null);

    const box = await screen.findByRole('img', { name: 'No viewpoint on this issue.' });
    expect(box).toHaveAttribute('data-snapshot-state', 'no_viewpoint');
    expect(fetchSnapshot).not.toHaveBeenCalled();
  });

  it('gives the three states three different names on screen', async () => {
    const seen: string[] = [];
    for (const vp of [viewpoint(false), null]) {
      const view = renderSnapshot(vp);
      const box = await screen.findByRole('img');
      seen.push(box.getAttribute('data-snapshot-state') ?? '');
      view.unmount();
    }
    fetchSnapshot.mockRejectedValue(new Error('gone'));
    renderSnapshot(viewpoint(true));
    seen.push(
      (await screen.findByRole('img', { name: 'Snapshot could not be loaded.' })).getAttribute(
        'data-snapshot-state',
      ) ?? '',
    );

    // Collapsing any two of them back together is the defect this whole module
    // exists to prevent, so assert they stay distinct rather than assert three
    // particular strings.
    expect(new Set(seen).size).toBe(seen.length);
  });

  it('draws the picture when there is one, so the empty states are not the only path', async () => {
    fetchSnapshot.mockResolvedValue(new Blob([new Uint8Array([137, 80, 78, 71])]));

    renderSnapshot(viewpoint(true));

    await waitFor(() => {
      const img = screen.getByAltText('Issue viewpoint snapshot');
      expect(img.tagName).toBe('IMG');
      expect(img).toHaveAttribute('src', 'blob:register-snapshot');
    });
    expect(document.querySelector('[data-snapshot-state]')).toBeNull();
  });
});
