// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One amount, one reading, on every surface that shows it.
//
// The defect this was written from: the same record rendered `$180,174.28` on
// the bill of quantities and `180.174,28 $` on the finance register, inside one
// English UI. Nothing was random about it. The bill formats through
// `shared/lib/money`, which resolves the locale from the UI language, and the
// finance register formats through `<MoneyDisplay>`, which read a separate
// `numberLocale` preference whose default was the literal `'de-DE'`. Both
// surfaces were doing exactly what they were told; they were told different
// things.
//
// So this file asks the question the sibling gates cannot. They ask whether a
// call names a locale at all - `numbersAreWrittenInTheAppLanguage` catches the
// missing argument, `formattersReadTheLocalePerCall` catches the argument read
// once at chunk load. A call that confidently passes the WRONG locale satisfies
// both. That is the shape of this bug, and it is why finding it needed a
// screenshot rather than a gate.
//
// Two halves, in one file because they are one question:
//
//   * the rendering half checks that the money surfaces agree with the common
//     path, in a form derived from the locale rather than compared to a string.
//     A test that knows `$180,174.28` passes again the moment the seed amount
//     changes; a test that knows en-US groups with commas, points its decimals
//     and leads with the symbol keeps working on any amount.
//   * the census half checks that there is only one place the answer can come
//     from. Fixing the two rows in the screenshot would have left every other
//     surface free to invent its own locale, and we would be back here.
import { describe, it, expect, beforeEach, afterEach, afterAll } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { render, cleanup } from '@testing-library/react';
import i18next from 'i18next';

import { MoneyDisplay } from '@/shared/ui/MoneyDisplay';
import { QuantityDisplay } from '@/shared/ui/QuantityDisplay';
import { formatCurrency } from '@/shared/lib/money';
import { fmtWithCurrency } from '@/features/boq/boqHelpers';
import { usePreferencesStore } from '@/stores/usePreferencesStore';

const SRC = join(__dirname, '..', '..', '..');

/**
 * The fixed point of the whole file: the language the reader picked, and the
 * locale tag their numbers therefore have to be written in. Taken straight
 * from `LOCALE_MAP` in `intlLocale.ts`, deliberately restated here rather than
 * imported - a test that derives its expectation from the same function it is
 * checking passes whatever that function returns.
 */
const LANGUAGES: [string, string][] = [
  ['en', 'en-US'],
  ['de', 'de-DE'],
  ['fr', 'fr-FR'],
  ['ja', 'ja-JP'],
];

/** Amounts, not an amount. The assertion must not depend on which one. */
const AMOUNTS = [180174.28, 225297.6, 3088.4, 0, -1234.5];

const originalLanguage = i18next.language;

function speak(language: string) {
  // The store is read through a selector, and `useIntlLocale` reads i18next at
  // render, so both are in place before the component mounts.
  i18next.language = language;
}

beforeEach(() => {
  localStorage.clear();
  usePreferencesStore.getState().resetPreferences();
});

afterEach(() => {
  cleanup();
});

afterAll(() => {
  i18next.language = originalLanguage;
});

/* ── The reading a locale actually prescribes ─────────────────────────────── */

interface Shape {
  group: string | undefined;
  decimal: string | undefined;
  symbolLeads: boolean;
}

/**
 * What this locale does to a number, asked of Intl rather than asserted from
 * memory. Returning the separators and the symbol position - the three things
 * that differed on the screenshot - lets the tests below state the rule
 * ("English groups on commas") without hardcoding any rendered amount.
 */
function shapeOf(locale: string, currency: string, amount: number): Shape {
  const parts = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).formatToParts(amount);
  const symbolAt = parts.findIndex((p) => p.type === 'currency');
  const digitsAt = parts.findIndex((p) => p.type === 'integer');
  return {
    group: parts.find((p) => p.type === 'group')?.value,
    decimal: parts.find((p) => p.type === 'decimal')?.value,
    symbolLeads: symbolAt >= 0 && symbolAt < digitsAt,
  };
}

/** The money string a reader of `locale` is owed, computed, never quoted. */
function expectedMoney(locale: string, currency: string, amount: number): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

/* ── Half one: the surfaces agree, in the reader's language ───────────────── */

describe('a money surface is written in the language the reader is reading', () => {
  // Guards the guard. Every assertion below compares a rendered string against
  // an Intl-derived one, which would be satisfied by anything at all if the
  // test host shipped no locale data and Intl collapsed every locale onto one
  // output. Stating the differences explicitly means a hollow environment
  // fails here, loudly, instead of turning the rest of the file green.
  it('the locales under test genuinely disagree about how to write a number', () => {
    const en = shapeOf('en-US', 'USD', 180174.28);
    const de = shapeOf('de-DE', 'USD', 180174.28);

    expect(en.group).toBe(',');
    expect(en.decimal).toBe('.');
    expect(en.symbolLeads).toBe(true);

    expect(de.group).toBe('.');
    expect(de.decimal).toBe(',');
    expect(de.symbolLeads).toBe(false);
  });

  it.each(LANGUAGES)('MoneyDisplay writes %s money as %s prescribes', (language, tag) => {
    speak(language);
    for (const amount of AMOUNTS) {
      const { container } = render(<MoneyDisplay amount={amount} currency="USD" />);
      expect(container.textContent).toBe(expectedMoney(tag, 'USD', amount));
      cleanup();
    }
  });

  // The defect itself: `/boq` renders through `formatCurrency` and `/finance`
  // through `<MoneyDisplay>`. Whatever else changes, those two have to produce
  // one string for one amount.
  it.each(LANGUAGES)('the bill and the register agree in %s', (language, _tag) => {
    speak(language);
    for (const amount of AMOUNTS) {
      const { container } = render(<MoneyDisplay amount={amount} currency="USD" />);
      expect(container.textContent).toBe(formatCurrency(amount, 'USD'));
      cleanup();
    }
  });

  it('a quantity is written with the same separators as the money beside it', () => {
    speak('de');
    const { container } = render(<QuantityDisplay value={1234.5} unit="m³" precision={2} />);
    const expected = new Intl.NumberFormat('de-DE', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    }).format(1234.5);
    expect(container.textContent).toContain(expected);
  });

  it('switching the language moves the numbers with it', () => {
    speak('en');
    const first = render(<MoneyDisplay amount={180174.28} currency="USD" />).container.textContent;
    cleanup();
    speak('de');
    const second = render(<MoneyDisplay amount={180174.28} currency="USD" />).container.textContent;

    expect(first).toBe(expectedMoney('en-US', 'USD', 180174.28));
    expect(second).toBe(expectedMoney('de-DE', 'USD', 180174.28));
    expect(first).not.toBe(second);
  });
});

/* ── Half one, continued: an explicit choice still wins ───────────────────── */

describe('the number-format preference', () => {
  it('overrides the UI language when the reader has actually chosen one', () => {
    speak('en');
    usePreferencesStore.getState().setPreference('numberLocale', 'de-DE');
    const { container } = render(<MoneyDisplay amount={180174.28} currency="USD" />);
    expect(container.textContent).toBe(expectedMoney('de-DE', 'USD', 180174.28));
  });

  // The half of the fix that is invisible from a fresh profile. `persist`
  // writes the whole preferences object on any change, so every browser that
  // ever set a currency has the old hardcoded `'de-DE'` written down. Changing
  // the default without reading that value back would have fixed the bug for
  // nobody who had ever used the app.
  // `setPreference` rebuilds the stored blob from `readPreferences()`, so what
  // lands back in localStorage is the migration's own output. Asserting there
  // exercises the real boot path rather than a helper exported for the test.
  const persisted = () => JSON.parse(localStorage.getItem('oe_preferences') as string);

  it('reads the pre-auto default out of an existing browser', () => {
    localStorage.setItem('oe_preferences', JSON.stringify({ currency: 'USD', numberLocale: 'de-DE' }));
    usePreferencesStore.getState().setPreference('vatRate', 19);
    expect(persisted().numberLocale).toBe('auto');
  });

  it('migrates once, so a de-DE chosen afterwards survives', () => {
    localStorage.setItem(
      'oe_preferences',
      JSON.stringify({ currency: 'USD', numberLocale: 'de-DE', _v: 2 }),
    );
    usePreferencesStore.getState().setPreference('vatRate', 19);
    expect(persisted().numberLocale).toBe('de-DE');
  });

  it('leaves a locale nobody could have got by default alone', () => {
    localStorage.setItem('oe_preferences', JSON.stringify({ numberLocale: 'ja-JP' }));
    usePreferencesStore.getState().setPreference('vatRate', 19);
    expect(persisted().numberLocale).toBe('ja-JP');
  });
});

/* ── Half two: only one place may answer the question ─────────────────────── */

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    // Locale files hold translated data, not formatting calls.
    if (name === 'node_modules' || name === 'locales' || name === '__tests__') continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      sourceFiles(full, found);
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      found.push(full);
    }
  }
  return found;
}

const PRODUCT_FILES = sourceFiles(SRC).map((f) => relative(SRC, f).replace(/\\/g, '/'));
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8');

/**
 * The locale argument of a formatter call: from `from` to the first comma or
 * closing bracket. Neither character occurs inside a BCP-47 tag or inside a
 * call to one of the resolvers, so this is the whole argument in every shape
 * the tree uses today.
 */
function localeArgument(source: string, from: number): string {
  const rest = source.slice(from);
  return rest.slice(0, Math.min(...[rest.indexOf(','), rest.indexOf(')')].filter((i) => i >= 0)));
}

/**
 * Every name a `const`, `let` or `var` in this file binds to something the
 * pattern matches.
 *
 * A gate that judges the argument text alone reads `new Intl.NumberFormat(
 * locale, ...)` as clean whatever `locale` holds, so `const locale =
 * getIntlLocale()` two lines above defeats it. That is not hypothetical: three
 * of the four sites this file caught on the day the resolution was added were
 * written that way, and the gate had already been reported green over them.
 *
 * Matching by name across the whole file is deliberate over-approximation. A
 * file that keeps a language `locale` and a number `locale` under one name gets
 * flagged, and being asked to give one of them a different name is the right
 * answer rather than a false alarm.
 */
function boundTo(source: string, pattern: RegExp): Set<string> {
  const names = new Set<string>();
  for (const match of source.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;\n]+)/g)) {
    if (pattern.test(match[2])) names.add(match[1]);
  }
  return names;
}

/** Whether an argument reaches a resolver, directly or through a local name. */
function reaches(argument: string, pattern: RegExp, aliases: Set<string>): boolean {
  if (pattern.test(argument)) return true;
  const bare = argument.trim();
  return /^[A-Za-z_$][\w$]*$/.test(bare) && aliases.has(bare);
}

/**
 * The two resolvers, in every spelling that reaches them. `i18n.language` is
 * the third way to ask for the interface language and it belongs here for the
 * same reason the other two do: a formatter cannot be excused by which door it
 * used.
 */
const LANGUAGE = /\b(?:get|use)IntlLocale\b|\bi18n\.language\b/;
const NUMBER_PREFERENCE = /\b(?:get|use)NumberLocale\b/;

/**
 * The two files allowed to read the raw preference: the store, which owns it
 * and turns it into an answer, and the settings screen, which has to show the
 * reader what they picked. Everywhere else asks `useNumberLocale`.
 */
const MAY_READ_THE_PREFERENCE = [
  'stores/usePreferencesStore.ts',
  'features/settings/RegionalSettings.tsx',
];

/**
 * A locale tag written into a formatter, argued one line at a time.
 *
 * The snippet is matched against the file, so an exemption covers the line it
 * was argued for and expires the moment that line changes - the same discipline
 * the `toFixed` allowlist uses next door.
 */
const HARDCODED_LOCALE_ALLOWED: readonly { file: string; snippet: string; why: string }[] = [
  {
    file: 'shared/lib/money.ts',
    snippet: "const resolved = new Intl.NumberFormat('en-US', {",
    why:
      'A probe, not a rendering. It asks Intl how many decimal places a currency ' +
      'has and reads `resolvedOptions()`; nothing it produces reaches a screen. ' +
      'CLDR currency digits do not vary by locale, so the tag is a constant here ' +
      'in the same way `2` is.',
  },
];

describe('there is one place the number locale comes from', () => {
  it('no surface reads the raw preference behind the resolver', () => {
    const offenders = PRODUCT_FILES.filter(
      (f) => !MAY_READ_THE_PREFERENCE.includes(f) && /\bs\.numberLocale\b/.test(read(f)),
    );
    expect(offenders).toEqual([]);
  });

  it('no formatter is handed a locale tag written into the source', () => {
    // `new Intl.NumberFormat('de-DE'` and `(1234).toLocaleString('en-US'` alike:
    // a quoted BCP-47 tag in the locale position of anything that formats.
    const pattern =
      /(?:new Intl\.(?:NumberFormat|DateTimeFormat)|\.toLocaleString|\.toLocaleDateString|\.toLocaleTimeString)\(\s*(['"`])([a-z]{2}(?:-[A-Za-z0-9]+)*)\1/g;

    const offenders: string[] = [];
    for (const file of PRODUCT_FILES) {
      const source = read(file);
      for (const match of source.matchAll(pattern)) {
        const line = source.slice(0, match.index).split('\n').length;
        const argued = HARDCODED_LOCALE_ALLOWED.some(
          (a) => a.file === file && source.includes(a.snippet),
        );
        if (!argued) offenders.push(`${file}:${line} ${match[0]}`);
      }
    }
    expect(offenders).toEqual([]);
  });

  // The lesson of the defect above, applied to this file's own instrument.
  //
  // The test before this one anchors the tag to the opening bracket, so it sees
  // `new Intl.NumberFormat('de-DE'` and is blind to
  // `new Intl.NumberFormat(ctx.locale ?? 'de-DE'`, which is the same literal
  // doing the same thing one operator later. That is exactly how the bill grid
  // came to name two languages in its fallbacks while every gate stayed green:
  // a scope defined by the shape of an argument cannot see a wrong argument of
  // another shape. So this reads the whole locale position instead.
  it('no formatter has a locale tag hidden in its fallback either', () => {
    const opener =
      /(?:new Intl\.(?:NumberFormat|DateTimeFormat)|\.toLocaleString|\.toLocaleDateString|\.toLocaleTimeString)\(/g;
    const tag = /(['"`])[a-z]{2}(?:-[A-Za-z0-9]+)*\1/;

    const offenders: string[] = [];
    for (const file of PRODUCT_FILES) {
      const source = read(file);
      for (const match of source.matchAll(opener)) {
        // The locale argument runs to the first comma or the closing bracket,
        // whichever comes first. Neither appears inside a BCP-47 tag.
        const rest = source.slice(match.index + match[0].length);
        const end = Math.min(...[rest.indexOf(','), rest.indexOf(')')].filter((i) => i >= 0));
        const arg = rest.slice(0, end);
        const found = tag.exec(arg);
        if (!found) continue;
        const argued = HARDCODED_LOCALE_ALLOWED.some(
          (a) => a.file === file && source.includes(a.snippet),
        );
        if (!argued) {
          offenders.push(`${file}:${source.slice(0, match.index).split('\n').length} ${match[0]}${arg.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  // An allowlist that outlives the line it was written for is a blank cheque.
  it('every argued exemption still matches its line', () => {
    const stale = HARDCODED_LOCALE_ALLOWED.filter((a) => !read(a.file).includes(a.snippet));
    expect(stale).toEqual([]);
  });

  // Single source of truth, counted over the tree rather than shown by example.
  //
  // Naming the formatters that were wrong on the day this was written would
  // gate the ninth one and let the tenth in, which is the mistake the sibling
  // gate above already made once: it looked for a call with no locale argument
  // at all and was therefore blind to a call with the wrong one. So this counts
  // a property of every number formatter instead - which resolver it binds -
  // and it is a property a new formatter cannot avoid having.
  //
  // `new Intl.NumberFormat(` only, and that is a gap rather than a boundary.
  // `x.toLocaleString(` is one method name on `Number` and on `Date`, so the
  // shape alone cannot say which rule a call is under, and the tree carries 347
  // of them: roughly 250 numbers, roughly 50 dates, 297 passing the interface
  // language. Folding the method in wholesale would put date formatting under a
  // number rule; leaving it out leaves those number sites unguarded. They are a
  // wave of their own. The size is written down here so the next reader
  // inherits the gap rather than the impression that it was handled, and it was
  // counted over the committed tree rather than over somebody's working copy.
  it('no number formatter is built on the interface language', () => {
    // 2119 product files and 108 number formatters among them when this was
    // written. The file count is asserted because a walker that silently stops
    // finding files would otherwise pass on an empty set, which is the one way
    // a census can be green for the wrong reason.
    expect(PRODUCT_FILES.length).toBeGreaterThan(1800);

    const offenders: string[] = [];
    for (const file of PRODUCT_FILES) {
      const source = read(file);
      const aliases = boundTo(source, LANGUAGE);
      for (const match of source.matchAll(/new Intl\.NumberFormat\(/g)) {
        const argument = localeArgument(source, match.index + match[0].length);
        if (reaches(argument, LANGUAGE, aliases)) {
          offenders.push(`${file}:${source.slice(0, match.index).split('\n').length}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('and no date formatter is built on the number preference', () => {
    // The same rule read backwards, because "every number in the reader's
    // language" is easy to over-apply. A month name is not a number, the date
    // preference is a separate setting, and pointing the number locale at
    // `Intl.DateTimeFormat` answers a question nobody asked.
    const offenders: string[] = [];
    for (const file of PRODUCT_FILES) {
      const source = read(file);
      const aliases = boundTo(source, NUMBER_PREFERENCE);
      for (const match of source.matchAll(/new Intl\.DateTimeFormat\(/g)) {
        const argument = localeArgument(source, match.index + match[0].length);
        if (reaches(argument, NUMBER_PREFERENCE, aliases)) {
          offenders.push(`${file}:${source.slice(0, match.index).split('\n').length}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it('the store never hands the raw preference straight to a formatter', () => {
    const store = read('stores/usePreferencesStore.ts');
    expect(store).not.toMatch(/new Intl\.NumberFormat\(\s*numberLocale\b/);
    expect(store).toMatch(/new Intl\.NumberFormat\(resolveNumberLocale\(/);
  });
});

/* ── Half three: the bill is a surface like any other ─────────────────────── */

/**
 * Why this half exists when the two halves above already passed.
 *
 * They compared `<MoneyDisplay>` against `formatCurrency`, and both were right.
 * The bill of quantities called neither. It called `fmtWithCurrency`, a second
 * implementation of the same idea, and handed it a locale derived from the
 * project's region rather than from the reader. So the pair under test agreed
 * while the pair on the screen did not, and the gate stayed green through a
 * defect it was written for. A test of two things that already agree cannot
 * find the third thing that does not.
 *
 * The fix is structural rather than a matching pair of edits: `fmtWithCurrency`
 * now delegates, and the bill reads the same locale as everything else. These
 * assertions hold the shape of that, so the second implementation cannot grow
 * back.
 */

/** Amount and currency of readings caught on the registers, as data. */
const REGISTER_FIXTURES: readonly (readonly [number, string])[] = [
  [1543500, 'GBP'],
  [3091300, 'USD'],
  [906890, 'BRL'],
];

/**
 * The last codes on which the two surfaces disagreed, kept as data.
 *
 * They resolved the decimal count from different sources: the register read the
 * static ISO 4217 list in `shared/ui/currencyMinorUnits`, the bill read what the
 * engine holds, and CLDR gives these five zero decimals where ISO gives two.
 * That was never a contest between two tables, it was a contest between a table
 * and a reader - a Hungarian does not write forints with fillér - and on a
 * screen the reader wins, so the register asks the engine now as well. The
 * opposite rule holds for a document, which is read by a bank rather than by
 * our user, and belongs with the code that writes documents.
 *
 * Eleven other codes used to sit beside these - BHD CLP ISK JOD JPY KRW KWD OMR
 * TND UGX VND - because the bill asked for two decimals on everything, showing
 * cents on yen and hiding a digit on dinars.
 */
const ONCE_DISAGREED = ['COP', 'HUF', 'IDR', 'LBP', 'PKR'];

/** Every currency the project form offers, read from the form itself. */
function offeredCurrencies(): string[] {
  const source = read('features/projects/CreateProjectPage.tsx');
  const codes: string[] = [];
  for (const m of source.matchAll(/value: '([A-Z]{3})'/g)) {
    // The group is always present when the pattern matched, but the index
    // signature does not know that and the build is the only gate that cares.
    if (m[1]) codes.push(m[1]);
  }
  return [...new Set(codes)];
}

/** What `<MoneyDisplay>` puts on the screen for this amount. */
function registerReading(amount: number, currency: string): string {
  const { container } = render(<MoneyDisplay amount={amount} currency={currency} />);
  const text = container.textContent ?? '';
  cleanup();
  return text;
}

describe('the bill and the finance register cannot be told different things', () => {
  it.each(LANGUAGES)('%s writes one amount one way on both surfaces', (language, tag) => {
    speak(language);
    for (const [amount, currency] of REGISTER_FIXTURES) {
      expect(fmtWithCurrency(amount, tag, currency)).toBe(registerReading(amount, currency));
    }
  });

  it('the reader who picked a format is obeyed on both, not just on one', () => {
    // The screenshot pair in one line: an English UI with German numbers. The
    // bill used to answer the project's region here and the register the
    // preference, which is how one record read two ways inside one session.
    speak('en');
    usePreferencesStore.getState().setPreference('numberLocale', 'de-DE');
    for (const [amount, currency] of REGISTER_FIXTURES) {
      const bill = fmtWithCurrency(amount, 'de-DE', currency);
      expect(bill).toBe(registerReading(amount, currency));
      expect(bill).not.toBe(expectedMoney('en-US', currency, amount));
    }
  });

  it('no currency the product offers reads differently on the two surfaces', () => {
    speak('en');
    const disagree = offeredCurrencies().filter(
      (code) => fmtWithCurrency(1234.5, 'en-US', code) !== registerReading(1234.5, code),
    );
    expect(disagree).toEqual([]);
  });

  it('gives the codes that used to disagree the digit count the engine gives', () => {
    speak('en');
    for (const code of ONCE_DISAGREED) {
      // Asked of Intl rather than written out. "The forint has no fillér" is
      // an opinion, and the whole point of the ruling is that the opinion
      // belongs to CLDR: a test that spells the digits out would go on
      // passing while the product argued with the reader.
      const digits = new Intl.NumberFormat('en-US', { style: 'currency', currency: code })
        .resolvedOptions().maximumFractionDigits;
      expect(registerReading(1234.5, code), code).toBe(
        new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: code,
          minimumFractionDigits: digits,
          maximumFractionDigits: digits,
        }).format(1234.5),
      );
    }
  });

  it('the bill does not resolve its locale from the project region', () => {
    // The screen follows its reader. The document half of the rule - a GAEB
    // file, a PDF offer, an invoice, all read by somebody who is not our user -
    // is real and unbuilt, and when it is built it will key off the country
    // code the project stores. What it may not do is come back here.
    const page = read('features/boq/BOQEditorPage.tsx');
    expect(page).toMatch(/const locale = useNumberLocale\(\)/);
    const regionResolvers = PRODUCT_FILES.filter((f) => /getLocaleForRegion/.test(read(f)));
    expect(regionResolvers).toEqual([]);
  });

  it('there is one money formatter, and the bill helper is a name for it', () => {
    // The adapter may keep the argument order eleven bill surfaces already use.
    // It may not grow a formatter of its own again.
    const helpers = read('features/boq/boqHelpers.ts');
    const body = helpers.slice(helpers.indexOf('export function fmtWithCurrency'));
    expect(body.slice(0, body.indexOf('\n}'))).not.toMatch(/new Intl\.NumberFormat/);
  });
});
