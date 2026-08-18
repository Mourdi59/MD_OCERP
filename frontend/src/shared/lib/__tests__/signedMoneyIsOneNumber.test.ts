// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A signed amount is one number, not a sign and a number.
//
// The defect this was written from: on the change-order register the `+` of a
// signed cost impact sat on its own line, above the figure it belonged to, on
// every row of the frame. Both `+` and `$` are prefix-numeric under the
// Unicode line-breaking algorithm and only one prefix may open an unbreakable
// numeric run, so the break between them is legal - a narrow column is all it
// takes to make the browser use it, and then the reader sees a `+` and a
// number rather than a positive amount. That holds of the rendered characters
// however the cell was assembled, so what forbids the break is the cell saying
// `whitespace-nowrap`, checked next door in
// `features/changeorders/signStaysWithTheFigure.test.ts`.
//
// This file covers the other half of the same cell. The register wrote the
// sign itself, as `{x >= 0 ? '+' : ''}`, which puts it in front for every
// reader whatever their language does. `formatCurrency` now forwards a
// `signDisplay` to `Intl`, which returns the sign inside the same string and
// in the position the reader's language puts it.
//
// The assertions below are computed rather than quoted. A test that knows
// `+$175,000.00` starts failing the day the seeded amount changes; a test that
// knows "the signed rendering is the unsigned rendering with exactly one sign
// character added, and nothing else moved" keeps working on any amount, in any
// currency, in any language.
import { describe, it, expect } from 'vitest';

import { formatCurrency } from '../money';

/** Locale, currency: three different answers about where a symbol goes. */
const READERS: [string, string][] = [
  ['en-US', 'USD'],
  ['de-DE', 'EUR'],
  ['tr-TR', 'USD'],
];

const AMOUNTS = [175_000, 3088.4, 0.5, 12];

/** The plus this locale writes, asked of Intl rather than assumed to be `+`. */
function plusSignOf(locale: string): string {
  const parts = new Intl.NumberFormat(locale, { signDisplay: 'always' }).formatToParts(1);
  return parts.find((p) => p.type === 'plusSign')?.value ?? '+';
}

describe('a positive amount carries its own sign', () => {
  // Guards the guard. Every assertion below compares a signed rendering with
  // an unsigned one, and all of them would pass on a host whose Intl ignored
  // `signDisplay` entirely if that comparison were the only thing asked. So
  // ask first whether the two are different at all.
  it('the plain rendering of a positive amount has no sign to begin with', () => {
    for (const [locale, currency] of READERS) {
      expect(formatCurrency(175_000, currency, locale)).not.toContain(plusSignOf(locale));
    }
  });

  it.each(READERS)('%s writes the sign inside the number, not beside it', (locale, currency) => {
    const plus = plusSignOf(locale);
    for (const amount of AMOUNTS) {
      const plain = formatCurrency(amount, currency, locale);
      const signed = formatCurrency(amount, currency, locale, { signDisplay: 'always' });

      // Exactly one character was added, it is this locale's plus, and
      // removing it gives back the unsigned rendering untouched. That is the
      // whole contract: the sign is part of the same string, and nothing about
      // the figure - separators, decimals, symbol position - changed with it.
      expect(signed).toContain(plus);
      expect(signed.replace(plus, '')).toBe(plain);
    }
  });

  it('zero counts as positive, exactly as the hand-written test did', () => {
    // The register wrote `amount >= 0 ? '+' : ''`, so a zero impact showed a
    // plus. `always` keeps that; `exceptZero` would have changed the screen
    // while claiming to be a formatting fix.
    const signed = formatCurrency(0, 'USD', 'en-US', { signDisplay: 'always' });
    expect(signed).toContain(plusSignOf('en-US'));
  });

  it('leaves a negative amount exactly as it was', () => {
    for (const [locale, currency] of READERS) {
      expect(formatCurrency(-4200, currency, locale, { signDisplay: 'always' })).toBe(
        formatCurrency(-4200, currency, locale),
      );
    }
  });

  it('survives a wire value that arrives as a Decimal string', () => {
    const signed = formatCurrency('175000.00', 'USD', 'en-US', { signDisplay: 'always' });
    expect(signed).toBe(formatCurrency(175_000, 'USD', 'en-US', { signDisplay: 'always' }));
  });

  it('keeps the sign when Intl is unusable and the hand-rolled path answers', () => {
    // A malformed locale tag is the one RangeError `formatCurrency` can still
    // take, and it lands in a fallback that builds the string itself. A
    // fallback that quietly drops the sign hands the caller back the problem
    // it asked the formatter to solve - and only on the hosts nobody tests.
    expect(() => formatCurrency(1234, 'USD', 'not a locale', { signDisplay: 'always' })).not.toThrow();
    expect(formatCurrency(1234, 'USD', 'not a locale', { signDisplay: 'always' })).toContain('+');
    expect(formatCurrency(-1234, 'USD', 'not a locale', { signDisplay: 'always' })).not.toContain('+');
  });

  it('still respects a fraction-digit override while signing', () => {
    const signed = formatCurrency(1234.5, 'USD', 'en-US', {
      signDisplay: 'always',
      maximumFractionDigits: 0,
    });
    expect(signed).toBe(`+${formatCurrency(1234.5, 'USD', 'en-US', { maximumFractionDigits: 0 })}`);
  });
});
