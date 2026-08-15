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
const BUILT = /new Intl\.(?:Number|DateTime)Format\(\s*getIntlLocale\(\)/;
const DECLARES = /^(?:export\s+)?(?:const|let|var)\b/;
const MEMOISED = /\b(?:useMemo|useRef|useState)\(/;
// The language is only re-read where the expression is evaluated again, so
// what disqualifies a site is not its indentation - it is anything that makes
// the expression run once. Two shapes do that. The statement can sit at module
// scope, directly or nested in an object or array literal, in which case it
// runs when the chunk loads. Or it can be memoised across renders, in which
// case it runs on mount, and a language change does not remount anything.
function frozenSites(text: string): number[] {
  const lines = text.split('\n');
  const frozen: number[] = [];
  lines.forEach((line, index) => {
    if (!BUILT.test(line)) return;
    const anchor = lines.slice(0, index + 1).reverse().find((candidate) => candidate.trim() && !/^\s/.test(candidate));
    const atModuleScope =
      anchor !== undefined && DECLARES.test(anchor) && !anchor.includes('=>') && !anchor.includes('function');
    const hook = lines.slice(Math.max(0, index - 4), index + 1).some((candidate) => MEMOISED.test(candidate));
    // A memo that lists the language is re-run by the switch, so it is fine.
    const deps = lines.slice(index, index + 12).join('\n').match(/,\s*(\[[^\]]*\])\s*,?\s*\)/);
    const watchesLanguage = deps !== null && /language|locale|i18n/i.test(deps[1]);
    if (atModuleScope || (hook && !watchesLanguage)) frozen.push(index + 1);
  });
  return frozen;
}

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

describe('no formatter outlives a language change', () => {
  it('finds none anywhere under src', () => {
    const offenders = sourceFiles(SRC)
      .filter((file) => frozenSites(readFileSync(file, 'utf8')).length > 0)
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

  it('still recognises a freeze in each of the shapes it can take', () => {
    const plain = 'const money = new Intl.NumberFormat(getIntlLocale(), { style: "currency" });';
    const nested = ['const FORMATS = {', '  money: new Intl.NumberFormat(getIntlLocale()),', '};'].join('\n');
    const memoised = ['  const money = useMemo(', '    () => new Intl.NumberFormat(getIntlLocale()),', '    [],', '  );'].join('\n');
    const perRender = ['  function Row() {', '    const money = new Intl.NumberFormat(getIntlLocale());', '  }'].join('\n');
    const watching = ['  const money = useMemo(', '    () => new Intl.NumberFormat(getIntlLocale()),', '    [i18n.language],', '  );'].join('\n');

    // The three that freeze, including the two the column-0 reading missed.
    expect(frozenSites(plain)).toHaveLength(1);
    expect(frozenSites(nested)).toHaveLength(1);
    expect(frozenSites(memoised)).toHaveLength(1);
    // And the two that do not, so the gate cannot pass by calling everything a freeze.
    expect(frozenSites(perRender)).toEqual([]);
    expect(frozenSites(watching)).toEqual([]);
  });
});
