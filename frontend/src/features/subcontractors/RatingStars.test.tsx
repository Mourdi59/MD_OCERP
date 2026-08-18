// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <RatingStars> — the five-star cell in the RATING column of the
// subcontractor register.
//
// The invariant under test is that the two halves of the cell agree. Counting
// how many stars render proves nothing at all: the cell always renders five,
// and the register spent its whole life drawing five empty ones beside a
// number that read as four out of five. So every case here pins the filled
// count and the printed number together, against a scale the printed number
// now states.

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';

import { RatingStars, RATING_SCALE_MAX, RATING_STAR_COUNT, starsForScore } from './RatingStars';

/** Stars painted with the fill class, read off the rendered svg. */
function filledCount(container: HTMLElement): number {
  return Array.from(container.querySelectorAll('svg')).filter((el) =>
    (el.getAttribute('class') ?? '').includes('fill-oe-blue'),
  ).length;
}

describe('RatingStars', () => {
  it.each([
    [0, 0, '0/100'],
    [4.2, 0, '4/100'],
    [50, 3, '50/100'],
    [84, 4, '84/100'],
    [100, 5, '100/100'],
  ])('fills the stars a score of %s earns and prints it against its scale', (score, filled, printed) => {
    const { container } = render(<RatingStars score={score} />);
    expect(container.querySelectorAll('svg')).toHaveLength(RATING_STAR_COUNT);
    expect(filledCount(container)).toBe(filled);
    expect(container.textContent).toBe(printed);
  });

  it('cannot be read as a score out of five when the value is a small one', () => {
    // Every demo subcontractor carried 4.20, meant as four point two out of
    // five and stored in a column that runs to a hundred. Printed bare, the
    // cell said four while the stars said none. It now says which scale it
    // means, so a reader can see the value is low rather than assume the
    // stars are broken.
    const { container } = render(<RatingStars score="4.20" />);
    expect(filledCount(container)).toBe(0);
    expect(container.textContent).toBe('4/100');
  });

  it('accepts the numeric string the API sends for a Decimal column', () => {
    const { container } = render(<RatingStars score="84.00" />);
    expect(filledCount(container)).toBe(4);
    expect(container.textContent).toBe('84/100');
  });

  it('treats a missing score as nothing earned rather than as a blank cell', () => {
    const { container } = render(<RatingStars score={null} />);
    expect(filledCount(container)).toBe(0);
    expect(container.textContent).toBe('0/100');
  });

  it('gives every star a colour class, filled or not', () => {
    // A star with no class at all renders invisible against the row, which is
    // how a status pipeline on the purchasing page came to read backwards.
    const { container } = render(<RatingStars score={60} />);
    for (const star of container.querySelectorAll('svg')) {
      expect(star.getAttribute('class') ?? '').toMatch(/\btext-[a-z-]+/);
    }
  });

  it('clamps a score outside the scale instead of overfilling the row', () => {
    expect(starsForScore(-10)).toBe(0);
    expect(starsForScore(RATING_SCALE_MAX)).toBe(RATING_STAR_COUNT);
    expect(starsForScore(RATING_SCALE_MAX * 1.5)).toBe(RATING_STAR_COUNT);
    expect(starsForScore(Number.NaN)).toBe(0);
  });
});
