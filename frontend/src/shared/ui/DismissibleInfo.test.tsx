/**
 * Tests for the shared DismissibleInfo help card.
 *
 * Behaviour under test (the two-state contract):
 *   - clicking the card collapses it to a bare "Module information" line
 *   - clicking that line re-expands the card
 *   - the X now ALSO just collapses (it no longer hides the card forever)
 *   - a legacy localStorage value of "2" (old "dismissed") maps to collapsed,
 *     so previously-hidden cards reappear as the bare line
 *   - a stored "1" maps to collapsed
 *   - clicking an inner link pill runs its handler WITHOUT toggling the card
 *   - keyboard: Enter / Space on the collapsed line expands it
 *
 * ``react-i18next`` and ``window.localStorage`` are mocked globally in
 * ``src/test/setup.ts`` (t returns ``defaultValue``; localStorage is an
 * in-memory store with a working ``clear()``).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { DismissibleInfo } from './DismissibleInfo';

const KEY = 'demo-card';
const LS_KEY = `oce.intro.${KEY}`;

function renderCard(props?: { links?: { label: string; onClick: () => void }[] }) {
  return render(
    <DismissibleInfo storageKey={KEY} title="Demo title" links={props?.links}>
      <span>Body copy explaining the page.</span>
    </DismissibleInfo>,
  );
}

/**
 * Locate the element that carries the toggle semantics for a given state.
 *
 * Collapsed: a bare native ``<button>`` line with ``aria-expanded=false``.
 * Expanded:  a native ``<button>`` header carries ``aria-expanded`` (the X and
 *            link pills are interactive, so they cannot be nested inside a
 *            role=button - that would be invalid ARIA).
 *
 * Either way the toggle element is uniquely identified by its
 * ``aria-expanded`` attribute.
 */
function ariaToggle(expanded: boolean): HTMLElement {
  const el = document.querySelector(`[aria-expanded="${expanded}"]`) as HTMLElement | null;
  if (!el) throw new Error(`no toggle with aria-expanded=${expanded}`);
  return el;
}

/** The clickable surface for "whole-card click" in the expanded state. */
function cardClickSurface(): HTMLElement {
  const wrapper = document.querySelector('div.border-l-oe-blue\\/70') as HTMLElement | null;
  if (!wrapper) throw new Error('no expanded card wrapper rendered');
  // First element child is the flex row that carries the collapse click handler.
  return wrapper.firstElementChild as HTMLElement;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe('DismissibleInfo', () => {
  it('renders expanded by default with title, body and an expanded toggle', () => {
    renderCard();
    expect(screen.getByText('Demo title')).toBeInTheDocument();
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    // A toggle marked aria-expanded carries the collapse semantics for AT.
    expect(ariaToggle(true)).toBeInTheDocument();
  });

  it('clicking anywhere on the card collapses it to the bare line and persists "1"', () => {
    renderCard();
    // Click the whole-card surface (not just the title) to prove the entire
    // card is the toggle.
    fireEvent.click(cardClickSurface());

    // Body and title are gone; only the bare "Module information" line remains.
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
    expect(screen.queryByText('Demo title')).not.toBeInTheDocument();
    expect(screen.getByText('Module information')).toBeInTheDocument();
    expect(ariaToggle(false)).toBeInTheDocument();
    // Collapsed state persisted under "1".
    expect(window.localStorage.getItem(LS_KEY)).toBe('1');
  });

  it('clicking the collapsed line re-expands it and persists "0"', () => {
    renderCard();
    fireEvent.click(cardClickSurface());
    // The bare collapsed line is itself the clickable surface.
    fireEvent.click(ariaToggle(false));

    expect(screen.getByText('Demo title')).toBeInTheDocument();
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('0');
  });

  it('the X collapses the card (it no longer hides it) and persists "1"', () => {
    const { unmount } = renderCard();
    const collapseBtn = screen.getByRole('button', { name: /collapse/i });
    fireEvent.click(collapseBtn);

    // Collapsed to the bare line - NOT removed.
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
    expect(screen.getByText('Module information')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('1');

    // Remount with the SAME storageKey -> still renders the collapsed line.
    unmount();
    renderCard();
    expect(screen.getByText('Module information')).toBeInTheDocument();
    expect(ariaToggle(false)).toBeInTheDocument();
  });

  it('pressing Enter on the collapsed line expands it (keyboard accessible)', () => {
    window.localStorage.setItem(LS_KEY, '1');
    renderCard();
    fireEvent.keyDown(ariaToggle(false), { key: 'Enter' });

    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('0');
  });

  it('pressing Space on the collapsed line expands it', () => {
    window.localStorage.setItem(LS_KEY, '1');
    renderCard();
    fireEvent.keyDown(ariaToggle(false), { key: ' ' });

    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('0');
  });

  it('legacy stored "1" maps to collapsed', () => {
    window.localStorage.setItem(LS_KEY, '1');
    renderCard();

    expect(screen.queryByText('Demo title')).not.toBeInTheDocument();
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
    expect(screen.getByText('Module information')).toBeInTheDocument();
    expect(ariaToggle(false)).toBeInTheDocument();
  });

  it('legacy stored "2" (old "dismissed") now renders the collapsed line, NOT nothing', () => {
    window.localStorage.setItem(LS_KEY, '2');
    renderCard();

    // The card is no longer hidden - it shows the bare collapsed line.
    expect(screen.getByText('Module information')).toBeInTheDocument();
    expect(ariaToggle(false)).toBeInTheDocument();
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
  });

  it('clicking an inner link pill runs its handler WITHOUT toggling the card', () => {
    const onClick = vi.fn();
    renderCard({ links: [{ label: 'Open BOQ', onClick }] });

    const pill = screen.getByRole('button', { name: 'Open BOQ' });
    fireEvent.click(pill);

    // Handler fired, but the card stayed expanded (body still visible) and
    // nothing was persisted (still no toggle write).
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBeNull();
  });

  it('two cards with different keys keep independent state', () => {
    render(
      <>
        <DismissibleInfo storageKey="a" title="Card A" />
        <DismissibleInfo storageKey="b" title="Card B" />
      </>,
    );
    // Collapse only card A via its X (collapse) button.
    const collapseButtons = screen.getAllByRole('button', { name: /collapse/i });
    expect(collapseButtons).toHaveLength(2);
    fireEvent.click(collapseButtons[0]!);

    // Card A collapsed to the bare line (title gone); Card B still expanded.
    expect(screen.queryByText('Card A')).not.toBeInTheDocument();
    expect(screen.getByText('Card B')).toBeInTheDocument();
    expect(window.localStorage.getItem('oce.intro.a')).toBe('1');
    expect(window.localStorage.getItem('oce.intro.b')).toBeNull();
  });
});
