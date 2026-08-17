import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * German construction does not call a bill of quantities a BOQ. It calls it a
 * Leistungsverzeichnis, LV for short, and every German tender document, every
 * GAEB exchange and every Vergabe file says LV. The German locale had been
 * translated in two passes and ended up holding both: 532 values said LV and
 * 339 still said BOQ, which is not a style question but a comprehension one.
 *
 * The loan word also carried the wrong gender, and carried it inconsistently.
 * "die BOQ" was borrowed as feminine in some strings and "das BOQ" as neuter in
 * others, so the file contained "Bepreiste BOQ" on one line and "Bepreistes
 * BOQ" on another for the same thing. LV is neuter, after Leistungsverzeichnis,
 * so a bare LV behind a feminine article is the same defect wearing the German
 * word, and the second assertion here is what stops the sweep from installing
 * it.
 *
 * Two uses of the abbreviation are correct and stay. The country exchange
 * modules name a format that really is called a BOQ in that market, and one
 * takeoff string glosses the German term with the English one in brackets for
 * a reader who arrived from an English tender.
 */

const LOCALES_DIR = ['src/app/locales', 'frontend/src/app/locales']
  .map((p) => resolve(process.cwd(), p))
  .find(existsSync);

/** `  "key": "value",` - the shape every line in a locale file has. */
const PAIR = /^\s*"((?:[^"\\]|\\.)*)"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,?\s*$/;

const BARE = /\bBOQs?\b/;

/**
 * The adjectives the German locale actually puts in front of the bill, in the feminine
 * form a sweep would leave behind. German declines the adjective after whatever stands in
 * front of it, so "das bepreiste LV" is right and only a bare one, with no determiner, has
 * to move to the strong ending.
 */
const ADJECTIVE =
  'bepreiste|verknüpfte|vollständige|andere|erste|vorhandene|neue|leere|eigene|gesperrte|' +
  'importierte|aktuelle|gepreiste|ausgepreiste|strukturierte|echte|betroffene|gesamte|unbenannte';
/** A feminine determiner, or a bare feminine adjective, in front of the neuter LV. */
const FEMININE = new RegExp(
  `\\b(?:die|eine|einer|der|dieser|diese|ihrer|zur|keine)(?:\\s+[a-zäöüß]+(?:e|es|en|er))?\\s+LV(?![\\w-])` +
    `|(?:^|[;:,(\\-·]\\s*)(?:${ADJECTIVE})\\s+LV(?![\\w-])`,
  'i',
);

/** The abbreviation is the artifact's own name in these markets. */
const EXCHANGE_MODULE = /^nav\.[a-z]+_boq_exchange$/;
/** Naming the German term and glossing it in brackets is not a leftover. */
const GLOSSED = /Leistungsverzeichnis[^"]*\(BOQ\)/;

type Entry = { key: string; value: string };

function readLocale(code: string): Entry[] {
  const text = readFileSync(resolve(LOCALES_DIR as string, `${code}.ts`), 'utf8');
  const entries: Entry[] = [];
  for (const line of text.split('\n')) {
    const match = PAIR.exec(line);
    // Both groups are read explicitly rather than relying on the match being
    // truthy: under noUncheckedIndexedAccess an indexed read off a match array
    // is string | undefined however the regex is written, because the compiler
    // has no way to know the pattern has two groups.
    const [, key, value] = match ?? [];
    if (key !== undefined && value !== undefined) entries.push({ key, value });
  }
  return entries;
}

function untranslated(entries: Entry[]): Entry[] {
  return entries.filter(
    (entry) => BARE.test(entry.value) && !EXCHANGE_MODULE.test(entry.key) && !GLOSSED.test(entry.value),
  );
}

describe('the German bill is named the way German names it', () => {
  const german = readLocale('de');

  it('reads the whole locale, so an empty finding means something', () => {
    expect(LOCALES_DIR).toBeDefined();
    expect(german.length).toBeGreaterThan(30000);
  });

  it('leaves no bare BOQ in a German string', () => {
    const left = untranslated(german).map((entry) => `${entry.key}: ${entry.value}`);
    expect(left).toEqual([]);
  });

  it('keeps the two uses of the abbreviation that are correct', () => {
    const kept = german.filter((entry) => BARE.test(entry.value));
    expect(kept.length).toBeGreaterThan(0);
    expect(kept.every((entry) => EXCHANGE_MODULE.test(entry.key) || GLOSSED.test(entry.value))).toBe(true);
  });

  it('does not leave a feminine article in front of the neuter LV', () => {
    const disagreeing = german
      .filter((entry) => FEMININE.test(entry.value))
      .map((entry) => `${entry.key}: ${entry.value}`);
    expect(disagreeing).toEqual([]);
  });

  it('recognises both defects when they are present', () => {
    const fixture: Entry[] = [
      { key: 'boq.title', value: 'Bepreiste BOQ' },
      { key: 'boq.list', value: 'Noch keine BOQs in diesem Projekt' },
      { key: 'nav.uae_boq_exchange', value: 'UAE BOQ Exchange' },
      { key: 'takeoff.export', value: 'Senden Sie Messungen in Ihr Leistungsverzeichnis (BOQ).' },
      { key: 'boq.ok', value: 'Bepreistes LV mit seinen LV-Positionen' },
    ];
    expect(untranslated(fixture).map((entry) => entry.key)).toEqual(['boq.title', 'boq.list']);
    expect(fixture.filter((entry) => FEMININE.test(entry.value))).toEqual([]);
    expect(FEMININE.test('Material aus der LV beschaffen')).toBe(true);
    expect(FEMININE.test('Eine vollständige LV erzeugen')).toBe(true);
    // The article survived a sweep that moved only the adjective, which is the
    // half-finished shape and has to be caught as well.
    expect(FEMININE.test('Eine vollständiges LV erzeugen')).toBe(true);
    expect(FEMININE.test('Zur LV hinzufügen')).toBe(true);
    expect(FEMININE.test('Vollständige LV im Export')).toBe(true);
    expect(FEMININE.test('Ein vollständiges LV erzeugen')).toBe(false);
    // Weak after a definite article, so this one is already right.
    expect(FEMININE.test('Sehen das bepreiste LV, nicht die Margen')).toBe(false);
    expect(FEMININE.test('eine Menge, die vom LV abweicht')).toBe(false);
    expect(FEMININE.test('Keine LVs in diesem Projekt')).toBe(false);
    expect(FEMININE.test('Nicht mit einer LV-Position verknüpft')).toBe(false);
  });
});
