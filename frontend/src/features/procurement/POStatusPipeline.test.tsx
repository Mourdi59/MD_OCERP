// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <POStatusPipeline>.

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { POStatusPipeline } from './POStatusPipeline';

describe('<POStatusPipeline>', () => {
  it('renders five dots for an in-flight PO', () => {
    const { container } = render(<POStatusPipeline status="issued" />);
    // 5 dot spans = the 5 life-cycle stages
    // (draft → approved → issued → partial → completed).
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(5);
  });

  it('shows the approved stage instead of collapsing to draft', () => {
    // Regression: 'approved' is a real FSM state. It used to be unknown to
    // the pipeline and fell back to 'draft', so an approved PO looked
    // un-progressed even though its budget was already committed.
    render(<POStatusPipeline status="approved" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Approved'),
    );
  });

  it('exposes an accessible label with the current stage', () => {
    render(<POStatusPipeline status="partially_received" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Partial'));
  });

  it('falls back to draft for an unknown status', () => {
    render(<POStatusPipeline status="bogus" />);
    const node = screen.getByRole('img');
    expect(node).toHaveAttribute('aria-label', expect.stringContaining('Draft'));
  });

  it('collapses to a single bar when cancelled', () => {
    const { container } = render(<POStatusPipeline status="cancelled" />);
    const dots = container.querySelectorAll('span');
    expect(dots.length).toBe(1);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Cancelled'),
    );
  });

  it('marks the completed stage as the last active dot', () => {
    render(<POStatusPipeline status="completed" />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Completed'),
    );
  });

  // Counting spans is not enough: the dots were all present in the DOM while
  // the completed ones painted nothing, so a draft PO showed five visible
  // pips and an issued one showed three. These two guard the paint, not the
  // markup.
  it.each(['draft', 'approved', 'issued', 'partially_received', 'completed', 'cancelled'])(
    'gives every dot a background to paint (%s)',
    (status) => {
      const { container } = render(<POStatusPipeline status={status} />);
      for (const dot of container.querySelectorAll('span')) {
        expect(dot.className).toMatch(/\bbg-[a-z-]+/);
      }
    },
  );

  it('distinguishes past, current and future stages from one another', () => {
    const { container } = render(<POStatusPipeline status="issued" />);
    const backgrounds = Array.from(container.querySelectorAll('span')).map(
      (d) => (d.className.match(/\bbg-[a-z-]+\b/) ?? [''])[0],
    );
    // draft + approved are past, issued is current, the last two are future.
    expect(backgrounds[0]).toBe('bg-semantic-success');
    expect(backgrounds[1]).toBe('bg-semantic-success');
    expect(backgrounds[2]).toBe('bg-oe-blue');
    expect(backgrounds[3]).toBe('bg-border');
    expect(new Set(backgrounds).size).toBe(3);
  });
});
