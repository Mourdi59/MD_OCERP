// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// A number format the preference can hold and the picker has no button for is
// a setting nobody can reach. That is not hypothetical: `en-IN` was absent from
// the type entirely while Indian rupees sat in the currency list, so a reader
// working on an Indian project was offered the currency and given no way to
// write it the way India writes it. Lakh and crore grouping was unreachable by
// any choice on any screen.
//
// The fix was to build the buttons from the store's own list. These tests hold
// that arrangement, because the failure it prevents is invisible: a second
// hand-written list looks perfectly healthy right up to the moment the two
// disagree, and nothing renders differently to say so.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { NUMBER_LOCALES, type NumberLocale } from '@/stores/usePreferencesStore';

/** Every locale the preference can hold, minus the follow-the-language default. */
const CHOICES = NUMBER_LOCALES.filter((l) => l !== 'auto');

function source(): string {
  return readFileSync(resolve(__dirname, 'RegionalSettings.tsx'), 'utf-8');
}

describe('the number format picker', () => {
  it('builds its buttons from the one list, not from a second one of its own', () => {
    // The single-source assertion, and the only one that survives someone
    // adding a locale: a picker with its own literal list would still pass
    // every render test while quietly offering fewer choices than the type.
    const text = source();
    expect(text).toContain('NUMBER_LOCALES.filter');
    // And no re-declared roster beside it. The old list wrote its locales out
    // as object literals; if that shape comes back, so does the drift.
    expect(text).not.toMatch(/\{\s*locale:\s*'[a-z]{2}-[A-Z]{2}'/);
  });

  it('offers Indian grouping, which is the choice that was missing', () => {
    expect(CHOICES).toContain('en-IN' as NumberLocale);
  });

  it('shows Indian grouping as something a reader can tell apart', () => {
    // The whole point of the button. Measured through Intl rather than written
    // down, because the sample only earns its length if the runtime agrees:
    // at four digits `en-IN` and `en-US` are identical and the button is noise.
    const sample = 1234567.89;
    const india = new Intl.NumberFormat('en-IN').format(sample);
    const america = new Intl.NumberFormat('en-US').format(sample);
    expect(india).not.toEqual(america);
    // Named so a reader of this file can see what the difference is.
    expect(india).toContain('12,34,567');
    expect(america).toContain('1,234,567');
    // And the trap the old four-digit sample fell into, stated out loud.
    expect(new Intl.NumberFormat('en-IN').format(1234.56)).toEqual(
      new Intl.NumberFormat('en-US').format(1234.56),
    );
  });

  it('gives every choice an example that Intl will actually produce', () => {
    // Not a tautology: it fails the moment a locale tag in the list is one the
    // runtime cannot resolve, which is how a typo in a BCP-47 tag reaches a
    // user as a button labelled with someone else's separators.
    for (const locale of CHOICES) {
      const resolved = new Intl.NumberFormat(locale).resolvedOptions().locale;
      expect(resolved.toLowerCase(), locale).toContain(locale.slice(0, 2).toLowerCase());
    }
  });
});
