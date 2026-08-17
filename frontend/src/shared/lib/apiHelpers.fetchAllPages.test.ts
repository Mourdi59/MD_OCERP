// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// `fetchAllPages` exists so that a sum, a count or an export is computed over a
// data set rather than over its first page. The ceiling is what stops it from
// reading an unbounded register into memory, and reaching it is the case these
// tests care about: the result has to carry enough for the caller to say how
// much of the set it holds, because a caller that cannot say so has to choose
// between publishing a short figure and publishing nothing.
//
// The total comes off the page envelope, which is the one number that stays
// correct when the read is cut short. A route still answering with a bare array
// has no total to give, and that has to stay distinguishable from a total of
// zero rather than collapsing into it.

import { describe, it, expect } from 'vitest';

import { fetchAllPages } from './apiHelpers';

/** A page envelope over a register of `total` rows, sliced the way a route would. */
function envelopeRegister(total: number) {
  const rows = Array.from({ length: total }, (_, i) => ({ id: `r${i}` }));
  return (offset: number, limit: number) =>
    Promise.resolve({ items: rows.slice(offset, offset + limit), total, offset, limit });
}

describe('fetchAllPages', () => {
  it('reports the register size a complete read already knew', async () => {
    const result = await fetchAllPages(envelopeRegister(250));

    expect(result.truncated).toBe(false);
    expect(result.items).toHaveLength(250);
    expect(result.total).toBe(250);
  });

  it('still knows the register size when the ceiling cut the read short', async () => {
    const result = await fetchAllPages(envelopeRegister(4321), { ceiling: 200 });

    // The rows are partial and say so, but the size is not a guess: it is what
    // the server stated, so the caller can report 200 of 4321 rather than
    // reporting 200 as if it were the whole register.
    expect(result.truncated).toBe(true);
    expect(result.items).toHaveLength(200);
    expect(result.total).toBe(4321);
  });

  it('keeps the first page total when later pages disagree', async () => {
    // A register being written while the loop runs hands back a denominator
    // that moves between requests. Taking the last one would let the number
    // drift under the reader; the first page is the one the read began from.
    let call = 0;
    const drifting = (offset: number, limit: number) => {
      call += 1;
      const total = 500 + call * 10;
      return Promise.resolve({
        items: Array.from({ length: limit }, (_, i) => ({ id: `r${offset + i}` })),
        total,
        offset,
        limit,
      });
    };

    const result = await fetchAllPages(drifting, { ceiling: 300 });

    expect(call).toBeGreaterThan(1);
    expect(result.total).toBe(510);
  });

  it('leaves the total undefined for a route that answers with a bare array', async () => {
    const rows = Array.from({ length: 40 }, (_, i) => ({ id: `r${i}` }));
    const result = await fetchAllPages((offset, limit) => Promise.resolve(rows.slice(offset, offset + limit)));

    expect(result.items).toHaveLength(40);
    // Not zero. A caller that printed a denominator here would state the
    // register is empty while handing the reader forty rows out of it.
    expect(result.total).toBeUndefined();
  });

  it('reports an empty register as a stated zero rather than as no answer', async () => {
    const result = await fetchAllPages(envelopeRegister(0));

    expect(result.items).toEqual([]);
    expect(result.truncated).toBe(false);
    expect(result.total).toBe(0);
  });
});
