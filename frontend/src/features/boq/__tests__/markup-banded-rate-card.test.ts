// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The markup panel's copy of the banded bond arithmetic.
 *
 * The panel mirrors the server cascade so a toggle reacts before the round
 * trip lands, which means this rate card is computed in two places and the two
 * have to agree. The backend authority is `_banded_amount` in
 * `backend/app/modules/boq/service.py`, and the same cases are asserted there
 * in `backend/tests/unit/test_boq_markup_types.py` against the same numbers.
 * If one moves, both of these fail rather than one bill quietly disagreeing
 * with the screen it was priced on.
 *
 * The effort goes on the band edges. A tranche table is right everywhere
 * except at its boundaries, and that is where the money is.
 */

import { describe, it, expect } from 'vitest';
import { bandedAmount } from '../MarkupPanel';

/** 2.5 % on the first million, 1.5 % on the next four, 1 % above five. */
const RATE_CARD = [
  { up_to: '1000000', percentage: '2.5' },
  { up_to: '5000000', percentage: '1.5' },
  { up_to: null, percentage: '1.0' },
];

describe('bandedAmount', () => {
  it('charges each tranche at its own rate', () => {
    // 25,000 on the first million and 7,500 on the next half million. Not
    // 22,500 (whole sum at the band it lands in) and not 37,500 (top rate
    // throughout).
    expect(bandedAmount(1_500_000, { bands: RATE_CARD })).toBe(32_500);
  });

  it('puts a base sitting exactly on a band edge in the lower band', () => {
    expect(bandedAmount(1_000_000, { bands: RATE_CARD })).toBe(25_000);
  });

  it('charges only the excess above an edge at the next rate', () => {
    expect(bandedAmount(1_000_100, { bands: RATE_CARD })).toBeCloseTo(25_001.5, 6);
  });

  it('never reaches the upper bands for a base inside the first', () => {
    expect(bandedAmount(400_000, { bands: RATE_CARD })).toBe(10_000);
  });

  it('gives everything above the last ceiling to the open-ended band', () => {
    expect(bandedAmount(10_000_000, { bands: RATE_CARD })).toBe(135_000);
  });

  it('reads the card in order however it was written', () => {
    const shuffled = [RATE_CARD[2], RATE_CARD[0], RATE_CARD[1]];
    expect(bandedAmount(1_500_000, { bands: shuffled })).toBe(32_500);
  });

  it('drops an unreadable entry rather than rendering nothing at all', () => {
    const bands = [
      { up_to: '1000000', percentage: '2.5' },
      { up_to: 'not a number', percentage: '9' },
      'nonsense',
      { up_to: null, percentage: '1.0' },
    ];
    expect(bandedAmount(1_500_000, { bands })).toBe(30_000);
  });

  it.each([undefined, null, {}, { bands: [] }, { bands: 'not a list' }, 'not an object'])(
    'charges nothing when there is no card (%p)',
    (metadata) => {
      expect(bandedAmount(1_000_000, metadata)).toBe(0);
    },
  );
});
