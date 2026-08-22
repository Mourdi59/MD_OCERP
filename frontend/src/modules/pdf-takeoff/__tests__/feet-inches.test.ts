// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * `formatFeetInches`: the write side of the imperial notation.
 *
 * The read side (`parseFeetInches` in the BOQ grid) has accepted 12'-6 3/4"
 * for a long time. Nothing wrote it back, so an American estimator could type
 * a dimension the product would only ever answer in decimal feet. These tests
 * pin the write side, and most of them are about the two ways this function
 * can be wrong in a way that still looks plausible on screen:
 *
 *  1. The carry. Rounding a float inch value and only then splitting off the
 *     fraction prints `3'-11 16/16"` - a fraction equal to one, which is not a
 *     dimension anyone writes. Rounding to integer sixteenths FIRST makes that
 *     unrepresentable rather than merely unlikely, so the case is asserted at
 *     the exact boundary rather than near it.
 *  2. The reduction. `12/16` is arithmetically right and typographically
 *     wrong; a tape is read in halves, quarters, eighths and sixteenths.
 *
 * An explicit locale is passed everywhere so the assertions do not depend on
 * whichever language i18n happens to be initialised with.
 */

import { describe, expect, it } from 'vitest';
import { formatFeetInches, METERS_PER_INCH } from '../data/scale-helpers';

const EN = 'en-US';

/** Build an exact metre value from feet + sixteenths, so the test says what it
 *  means instead of carrying a decimal constant nobody can check by eye. */
function metres(feet: number, sixteenths = 0): number {
  return (feet * 12 + sixteenths / 16) * METERS_PER_INCH;
}

describe('formatFeetInches - the notation', () => {
  it('writes whole feet with an explicit zero inches', () => {
    // A drawing says 12'-0", never 12'. The zero is part of the notation: it
    // tells the reader the inches were considered, not omitted.
    expect(formatFeetInches(metres(12), EN)).toBe(`12'-0"`);
  });

  it('writes the case the product documents', () => {
    // The dimension the US takeoff case tells the reader they can type.
    expect(formatFeetInches(metres(12, 6 * 16 + 12), EN)).toBe(`12'-6 3/4"`);
  });

  it('folds a full twelve inches into the foot', () => {
    // Exactly 12 ft plus 12 in is 13 ft. Written as an exact input rather than
    // a rounded one, so this asserts the carry and not the rounding.
    expect(formatFeetInches(metres(12, 12 * 16), EN)).toBe(`13'-0"`);
  });

  it('writes inches with no fraction when the value lands on the inch', () => {
    expect(formatFeetInches(metres(3, 7 * 16), EN)).toBe(`3'-7"`);
  });

  it('writes a length under a foot as zero feet, not as bare inches', () => {
    expect(formatFeetInches(metres(0, 6 * 16 + 12), EN)).toBe(`0'-6 3/4"`);
  });
});

describe('formatFeetInches - the fraction is reduced', () => {
  it.each([
    [8, '1/2'],
    [4, '1/4'],
    [12, '3/4'],
    [2, '1/8'],
    [6, '3/8'],
    [10, '5/8'],
    [14, '7/8'],
    [1, '1/16'],
    [15, '15/16'],
  ])('%i sixteenths reads as %s', (sixteenths, expected) => {
    expect(formatFeetInches(metres(1, sixteenths), EN)).toBe(`1'-0 ${expected}"`);
  });
});

describe('formatFeetInches - the carry', () => {
  it('never prints a fraction equal to one', () => {
    // 15.9/16 of an inch rounds UP to a full inch. The float path would print
    // 11 16/16; the integer path has to carry into the inch.
    const justUnderAnInch = metres(3, 11 * 16 + 15.9);
    expect(formatFeetInches(justUnderAnInch, EN)).toBe(`4'-0"`);
  });

  it('never prints twelve inches', () => {
    // 11 and 63/64 inches rounds to 12 inches, which is a foot.
    const justUnderAFoot = metres(2, 11 * 16 + 15.99);
    expect(formatFeetInches(justUnderAFoot, EN)).toBe(`3'-0"`);
  });

  it('rounds to the nearest sixteenth rather than truncating', () => {
    // A hair over 6 1/2 stays 6 1/2; a hair under 6 9/16 rounds up to it.
    expect(formatFeetInches(metres(1, 6 * 16 + 8.4), EN)).toBe(`1'-6 1/2"`);
    expect(formatFeetInches(metres(1, 6 * 16 + 8.6), EN)).toBe(`1'-6 9/16"`);
  });
});

describe('formatFeetInches - degenerate values', () => {
  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])(
    'returns the empty string for %p, like formatMeasurement does',
    (value) => {
      expect(formatFeetInches(value, EN)).toBe('');
    },
  );

  it('returns empty rather than a false zero below the smallest division', () => {
    // Under half a sixteenth there is no division left to round to. Printing
    // 0'-0" would assert a dimension that was measured as nothing.
    expect(formatFeetInches(metres(0, 0.4), EN)).toBe('');
  });
});

describe('formatFeetInches - the reader decides the numerals', () => {
  it('renders digits in the reader language, and marks are notation', () => {
    // K-12: numbers read in the app language. The feet mark, the dash and the
    // inch mark are notation and do not translate. German groups thousands
    // with a dot, which is the visible difference on a long dimension.
    const long = metres(1234, 8);
    expect(formatFeetInches(long, 'de')).toBe(`1.234'-0 1/2"`);
    expect(formatFeetInches(long, EN)).toBe(`1,234'-0 1/2"`);
  });
});
