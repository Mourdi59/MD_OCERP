// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The clock a foreman types into, and the moment it has to become.
 *
 * A time typed on site is a wall-clock reading somewhere; the record stores
 * moments. These assertions are all relative (a round trip, a difference in
 * hours) so they hold in whatever timezone the test machine happens to be in,
 * which is the same reason the conversion exists in the first place.
 */

import { describe, it, expect } from 'vitest';
import { instantFromTime, timeOfDay } from './api';

const DAY = '2026-03-10';

function hoursBetween(startISO: string, endISO: string): number {
  return (new Date(endISO).getTime() - new Date(startISO).getTime()) / 3_600_000;
}

describe('instantFromTime', () => {
  it('round trips through the reader own clock', () => {
    const at = instantFromTime(DAY, '07:00');

    expect(at).not.toBeNull();
    expect(timeOfDay(at)).toBe('07:00');
  });

  it('keeps a day shift on its own day', () => {
    const start = instantFromTime(DAY, '07:00') as string;
    const end = instantFromTime(DAY, '16:00', start) as string;

    expect(hoursBetween(start, end)).toBe(9);
    expect(timeOfDay(end)).toBe('16:00');
  });

  it('rolls a night shift end into the next morning', () => {
    const start = instantFromTime(DAY, '22:00') as string;
    const end = instantFromTime(DAY, '06:00', start) as string;

    expect(hoursBetween(start, end)).toBe(8);
    expect(timeOfDay(end)).toBe('06:00');
  });

  it('leaves an end equal to its start alone, so the server can refuse it', () => {
    const start = instantFromTime(DAY, '07:00') as string;
    const end = instantFromTime(DAY, '07:00', start) as string;

    expect(hoursBetween(start, end)).toBe(0);
  });

  it('has nothing to say without a day or a time', () => {
    expect(instantFromTime('', '07:00')).toBeNull();
    expect(instantFromTime(DAY, '')).toBeNull();
    expect(timeOfDay(null)).toBe('');
    expect(timeOfDay('not a date')).toBe('');
  });
});
