// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <NoProjectState> - the "no project selected" panel on Find Records.
//
// Two of these assertions are the point of the component rather than decoration.
//
// The directional cue must be gated on the SAME breakpoint as the control it
// points at. The header ProjectSwitcher is `hidden sm:block`, so the cue is
// `hidden sm:flex`: in the compiled stylesheet both are governed by the identical
// condition `(min-width: 640px)`. jsdom applies no media queries, so this is
// asserted on the class contract rather than on a measured rect - an arrow that
// keeps a fixed class pair with its target cannot drift out of sync with it.
//
// And the animated cue must not animate for a reader who asked for less motion.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

import { NoProjectState } from './NoProjectState';

function renderPanel() {
  return render(
    <BrowserRouter>
      <NoProjectState />
    </BrowserRouter>,
  );
}

describe('NoProjectState', () => {
  it('renders the title, the description and a way out', () => {
    const { container } = renderPanel();

    expect(screen.getByText(/No project selected/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Select a project to search across its records/i),
    ).toBeInTheDocument();

    const cta = screen.getByRole('link', { name: /Open Projects/i });
    expect(cta).toHaveAttribute('href', '/projects');

    // The drawn scene is decorative, so it stays out of the accessibility tree.
    const svg = container.querySelector('svg[aria-hidden="true"]');
    expect(svg).not.toBeNull();
  });

  it('gates the cue on the breakpoint that reveals the header picker', () => {
    const { container } = renderPanel();

    const cue = container.querySelector('.sm\\:flex');
    expect(cue).not.toBeNull();
    // Hidden by default, shown from `sm` up - the picker's own class pair.
    expect(cue).toHaveClass('hidden');
    expect(cue?.className).toContain('sm:flex');
    expect(screen.getByText(/The project switcher is up here, in the header/i)).toBeInTheDocument();
  });

  it('stops the cue animating under prefers-reduced-motion', () => {
    const { container } = renderPanel();

    const bouncing = container.querySelector('.animate-bounce');
    expect(bouncing).not.toBeNull();
    // `className` on an <svg> is an SVGAnimatedString, so read the attribute.
    expect(bouncing?.getAttribute('class')).toContain('motion-reduce:animate-none');
  });

  it('keeps the bounce and the tilt on separate elements so both survive', () => {
    const { container } = renderPanel();

    // `animate-bounce` animates `transform`; a `-rotate-45` on the SAME node is
    // replaced by its keyframes and the arrow silently points straight up
    // instead of at the start-edge picker. Nothing in jsdom computes that, so
    // the invariant is asserted structurally: the two classes never co-occur.
    const bouncing = container.querySelector('.animate-bounce');
    expect(bouncing?.getAttribute('class')).not.toContain('rotate-45');

    const tilted = container.querySelector('.-rotate-45');
    expect(tilted).not.toBeNull();
    expect(tilted?.getAttribute('class')).not.toContain('animate-bounce');
  });
});
