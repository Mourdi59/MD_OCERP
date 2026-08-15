// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// A formatter built at module scope reads the language once, when its chunk
// first loads. The language switcher deliberately does not reload the app
// (Header.tsx: "no English flash and no reload"), so from that moment the
// constant keeps writing in whatever language the page happened to open in.
// A German reader who arrived in English saw `12,550,880` in a tile above
// rows reading `12.550.880` - and only after a switch, so it survives every
// screenshot taken in one language.
//
// Two things are pinned. The helpers really do follow a language change,
// which is the behaviour the fix depends on; and no module-scope formatter
// comes back, which no rendering test can see because the freeze needs a
// switch to show itself.
import { describe, it, expect, afterAll } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import i18next from 'i18next';
import { fmtNumber, fmtCompact, fmtPercent } from '../formatters';

const SRC = join(__dirname, '..', '..', '..');
// A statement that starts at column 0 is at module scope; anything indented
// is inside a component, a hook or a helper, and runs per call.
const FROZEN = /^(?:export )?const [\w$]+ = new Intl\.(?:Number|DateTime)Format\(\s*getIntlLocale\(\)/m;

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules') continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      sourceFiles(full, found);
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      found.push(full);
    }
  }
  return found;
}

describe('number helpers follow a language change', () => {
  const original = i18next.language;
  afterAll(() => {
    void i18next.changeLanguage(original || 'en');
  });

  it('writes the separators of the language in force at the call', async () => {
    await i18next.init({ lng: 'en', resources: {}, initImmediate: false });
    const inEnglish = fmtNumber(12550880.81, 2);
    await i18next.changeLanguage('de');
    const inGerman = fmtNumber(12550880.81, 2);

    expect(inEnglish).toBe('12,550,880.81');
    expect(inGerman).toBe('12.550.880,81');
    // The point of the test, stated as itself: the same call answers
    // differently once the language moves, with no reload in between.
    expect(inGerman).not.toBe(inEnglish);
  });

  it('applies to the compact and percent helpers too', async () => {
    await i18next.changeLanguage('en');
    const enCompact = fmtCompact(22_100_000);
    const enPercent = fmtPercent(68.3);
    await i18next.changeLanguage('de');

    expect(fmtCompact(22_100_000)).not.toBe(enCompact);
    expect(fmtPercent(68.3)).not.toBe(enPercent);
    expect(fmtPercent(68.3)).toContain(',');
  });
});

describe('no formatter is frozen at module scope', () => {
  it('finds none anywhere under src', () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => FROZEN.test(readFileSync(file, 'utf8')))
      .map((file) => relative(SRC, file).replace(/\\/g, '/'));

    // Five of these existed, and one carried a comment describing the freeze
    // and leaving it in place. Build the formatter where it is used, or call
    // fmtNumber / fmtCurrency / fmtCompact, which read the locale per call.
    expect(offenders).toEqual([]);
  });

  it('is looking at real files, so an empty result means something', () => {
    // A tree walk that visits nothing also finds no offenders.
    expect(sourceFiles(SRC).length).toBeGreaterThan(500);
  });
});
