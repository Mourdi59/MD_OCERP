/**
 * Unit tests for the money primitives (`toNum`, `formatCurrency`).
 *
 * The contract under test is the Decimal-as-string backend money format:
 * `toNum` must accept the string the wire actually delivers without ever
 * yielding NaN/Infinity, and `formatCurrency` must coerce safely, never
 * fall back to a wrong currency symbol, and honour fraction overrides.
 *
 * `locale` is passed explicitly so the assertions are independent of the
 * test runner's i18next/browser locale.
 */
import { describe, it, expect } from 'vitest';
import { toNum, formatCurrency } from './money';

describe('toNum', () => {
  it('passes through finite numbers', () => {
    expect(toNum(1234.56)).toBe(1234.56);
    expect(toNum(0)).toBe(0);
    expect(toNum(-42)).toBe(-42);
  });

  it('parses the Decimal-as-string backend format', () => {
    expect(toNum('1234.56')).toBe(1234.56);
    expect(toNum('0')).toBe(0);
    expect(toNum('-42.5')).toBe(-42.5);
  });

  it('collapses null / undefined / empty to 0', () => {
    expect(toNum(null)).toBe(0);
    expect(toNum(undefined)).toBe(0);
    expect(toNum('')).toBe(0);
  });

  it('collapses unparseable / non-finite input to 0 (never NaN)', () => {
    expect(toNum('not a number')).toBe(0);
    expect(toNum(NaN)).toBe(0);
    expect(toNum(Infinity)).toBe(0);
    expect(toNum(-Infinity)).toBe(0);
    expect(Number.isNaN(toNum('abc'))).toBe(false);
  });

  it('does not throw on a string (the historical .toFixed crash class)', () => {
    // The whole reason this helper exists: code used to call .toFixed on a
    // string and crash. toNum makes the value safe to .toFixed afterwards.
    expect(() => toNum('99.99').toFixed(2)).not.toThrow();
    expect(toNum('99.99').toFixed(2)).toBe('99.99');
  });
});

describe('formatCurrency', () => {
  it('formats a Decimal-string with the currency symbol', () => {
    // Use a non-breaking-space-tolerant check: assert the digits + symbol
    // are present rather than pinning exact whitespace (Intl uses NBSP).
    const out = formatCurrency('1234.56', 'USD', 'en-US');
    expect(out).toContain('$');
    expect(out).toContain('1,234.56');
  });

  it('uses the currency natural minor units by default', () => {
    // JPY has 0 minor units; KWD has 3.
    expect(formatCurrency('1000', 'JPY', 'en-US')).toContain('1,000');
    expect(formatCurrency('1000', 'JPY', 'en-US')).not.toContain('.00');
    expect(formatCurrency('1.5', 'KWD', 'en-US')).toContain('1.500');
  });

  it('renders a plain grouped number (no symbol) for unknown currency', () => {
    const out = formatCurrency('1234.56', '', 'en-US');
    expect(out).toBe('1,234.56'); // 2 fraction digits, no symbol
    expect(out).not.toContain('€');
    expect(out).not.toContain('$');
  });

  it('never falls back to EUR for a blank / invalid code', () => {
    expect(formatCurrency('1000', undefined, 'en-US')).not.toContain('€');
    expect(formatCurrency('1000', 'xx', 'en-US')).not.toContain('€');
    expect(formatCurrency('1000', '123', 'en-US')).not.toContain('€');
  });

  it('honours fraction-digit overrides (whole-number summaries)', () => {
    const whole = formatCurrency('1234.56', 'USD', 'en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    expect(whole).toContain('$');
    expect(whole).toContain('1,235'); // rounded, no cents
    expect(whole).not.toContain('.56');
  });

  it('accepts a maximum without a minimum and no currency', () => {
    // A whole-money caller passes maximumFractionDigits alone. The blank
    // currency branch used to keep its default minimum of 2, and Intl throws a
    // RangeError when the minimum exceeds the maximum. The existing test above
    // passed both ends, which is why the crash survived: dashboard cards that
    // pass max only took the page down whenever the currency was blank.
    expect(() => formatCurrency('1234.56', '', 'en-US', { maximumFractionDigits: 0 })).not.toThrow();
    expect(formatCurrency('1234.56', '', 'en-US', { maximumFractionDigits: 0 })).toBe('1,235');
    expect(formatCurrency('1234.56', undefined, 'en-US', { maximumFractionDigits: 1 })).toBe(
      '1,234.6',
    );
  });

  it('survives an inverted min / max pair on a real currency', () => {
    expect(() =>
      formatCurrency('1234.56', 'USD', 'en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 0,
      }),
    ).not.toThrow();
  });

  it('coerces null / undefined / NaN to a formatted zero, never crashes', () => {
    expect(() => formatCurrency(null, 'USD', 'en-US')).not.toThrow();
    expect(formatCurrency(null, 'USD', 'en-US')).toContain('0');
    expect(formatCurrency(undefined, '', 'en-US')).toBe('0.00');
    expect(formatCurrency('garbage', 'USD', 'en-US')).toContain('0');
  });

  it('accepts a genuine number as well as a string', () => {
    expect(formatCurrency(1234.56, 'USD', 'en-US')).toContain('1,234.56');
  });
});

/**
 * Fraction-digit safety (issue #391).
 *
 * `Intl.NumberFormat` answers `minimumFractionDigits > maximumFractionDigits`
 * with a `RangeError` ("Computed minimumFractionDigits is larger than
 * maximumFractionDigits" on WebKit). Money is rendered from React components,
 * so that throw does not degrade one cell, it unmounts the page - which is how
 * it was reported, from /match-elements.
 *
 * Two distinct sources of an invalid pair are covered here. Out-of-range digit
 * counts reach `Intl` verbatim and it rejects them outright, and a one-sided
 * override crosses the currency's own natural minor units (a whole-money
 * `maximumFractionDigits: 0` against a two-decimal currency's default minimum
 * of 2). Engines implementing the ES2023 clamping absorb the second case
 * themselves, so these assertions pin the behaviour rather than depending on
 * the browser the operator happens to bring.
 */
describe('formatCurrency fraction-digit safety', () => {
  it('survives an out-of-range maximum and still renders a zero-decimal currency', () => {
    // A negative ceiling is a caller bug that Intl rejects before it looks at
    // the currency at all, and the old hand-rolled fallback then called
    // `toFixed(-1)`, which throws again - out of the catch that was supposed
    // to contain it. JPY doubles as the zero-decimal check: the amount must
    // come back as yen with no cents, not padded to two digits.
    const opts = { maximumFractionDigits: -1 };
    expect(() => formatCurrency('1234', 'JPY', 'en-US', opts)).not.toThrow();

    const out = formatCurrency('1234', 'JPY', 'en-US', opts);
    expect(out).toContain('¥');
    expect(out).toContain('1,234');
    expect(out).not.toContain('.');
  });

  it('survives a non-finite and an over-large maximum with no currency', () => {
    // The no-currency branch is the one with no safety net around it, and
    // `Infinity` / 101 are both outside every engine's accepted window.
    // Neither is a digit count, so both defer to the plain-number default.
    expect(() =>
      formatCurrency('1234.56', '', 'en-US', { maximumFractionDigits: Infinity }),
    ).not.toThrow();
    expect(formatCurrency('1234.56', '', 'en-US', { maximumFractionDigits: Infinity })).toBe(
      '1,234.56',
    );
    expect(formatCurrency('1234.56', '', 'en-US', { maximumFractionDigits: 101 })).toBe('1,234.56');
    expect(formatCurrency('1234.56', '', 'en-US', { minimumFractionDigits: NaN })).toBe('1,234.56');
  });

  it('clamps an explicit inverted pair down to the caller ceiling', () => {
    // The ceiling is the caller's hard constraint: showing four digits when
    // the call site declared a maximum of zero would break the layout it was
    // sized for, so the floor is what gives way.
    expect(
      formatCurrency('1234.56', 'USD', 'en-US', {
        minimumFractionDigits: 4,
        maximumFractionDigits: 0,
      }),
    ).toBe('$1,235');
    expect(
      formatCurrency('1234.56', '', 'en-US', {
        minimumFractionDigits: 4,
        maximumFractionDigits: 1,
      }),
    ).toBe('1,234.6');
  });

  it('raises the ceiling for a floor a zero-decimal currency cannot meet', () => {
    // Only a floor was declared, so it is honoured rather than discarded:
    // JPY's natural maximum of 0 would otherwise invert the pair.
    const out = formatCurrency('1234.5', 'JPY', 'en-US', { minimumFractionDigits: 2 });
    expect(out).toContain('¥');
    expect(out).toContain('1,234.50');
  });

  it('leaves ordinary formatting untouched', () => {
    // Guard for the regression the fix could plausibly cause: resolving both
    // ends locally must reproduce what Intl defaulted to before.
    expect(formatCurrency('1234.56', 'USD', 'en-US')).toContain('1,234.56');
    expect(formatCurrency('1234.56', 'EUR', 'de-DE')).toContain('1.234,56');
    expect(formatCurrency('1.5', 'KWD', 'en-US')).toContain('1.500');
    expect(formatCurrency('1234.56', '', 'en-US')).toBe('1,234.56');
    expect(
      formatCurrency('1234.56', 'USD', 'en-US', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
      }),
    ).toBe('$1,235');
  });

  it('keeps the engine currency table, which our static minor-unit list contradicts', () => {
    // formatCurrency reads the natural digit count from Intl, not from a
    // static ISO 4217 list. The two disagree on 16 codes where CLDR says
    // zero decimals and ISO says two, so sourcing the count from the list
    // would start printing forint and rupiah with cents. The register used
    // to source it from there, which is how one amount could carry cents on
    // one screen and not on the next; no surface reads such a list now and
    // the frontend copy is gone, because a screen is written for its reader
    // and only a document is written for a bank.
    //
    // Asserted on the decimal marker rather than the whole string: hu-HU
    // groups with a non-breaking space, so an assertion written with an
    // ASCII space would pass no matter which source won.
    expect(formatCurrency('1234', 'HUF', 'hu-HU')).not.toMatch(/,00/);
    expect(formatCurrency('1234', 'IDR', 'en-US')).not.toMatch(/\.00/);
  });
});
