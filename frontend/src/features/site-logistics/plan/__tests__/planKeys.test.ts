// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The proof that every word of the logistics plan is in the text table, and
// that the table is carried by the English and the German locale.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import en from '@/app/locales/en';
import de from '@/app/locales/de';

import { EN, PREFIX } from '../texts';

const featureDir = join(__dirname, '..');
const files = readdirSync(featureDir).filter((f) => /\.(ts|tsx)$/.test(f) && f !== 'texts.ts');
const sources = files.map((f) => readFileSync(join(featureDir, f), 'utf-8')).join('\n');
const keys = Object.keys(EN);

describe('logistics plan text keys', () => {
  it('finds the screens it is meant to check', () => {
    // A broken scan would let the tests below pass on nothing.
    expect(files.length).toBeGreaterThan(9);
    expect(keys.length).toBeGreaterThan(400);
  });

  it('every key a screen names literally exists in the table', () => {
    const named = new Set<string>();
    for (const m of sources.matchAll(/tx\(\s*\w+,\s*'([^']+)'/g)) named.add(m[1]!);
    for (const m of sources.matchAll(/\b(?:label|hint|title|body|action)[:=]\s*["']([a-z_]+(?:\.[a-z_0-9]+)+|[a-z_]+)["']/g)) {
      named.add(m[1]!);
    }
    expect(named.size).toBeGreaterThan(150);
    expect([...named].filter((k) => !(k in EN))).toEqual([]);
  });

  it('no screen writes its own text past the table', () => {
    // A defaultValue or a bare t() call would be a string the table does not know.
    expect(sources).not.toMatch(/defaultValue/);
    expect([...sources.matchAll(/\bt\(\s*['"`]/g)]).toHaveLength(0);
  });

  it('the English locale carries the table word for word', () => {
    const differing = keys.filter((k) => en.translation[PREFIX + k] !== EN[k as keyof typeof EN]);
    expect(differing).toEqual([]);
  });

  it('the German locale carries every key with the same placeholders', () => {
    const marks = (text: string) => [...text.matchAll(/\{\{\w+\}\}/g)].map((m) => m[0]).sort();
    const missing = keys.filter((k) => !(PREFIX + k in de.translation));
    expect(missing).toEqual([]);
    const broken = keys.filter(
      (k) => marks(de.translation[PREFIX + k]!).join() !== marks(EN[k as keyof typeof EN]).join(),
    );
    expect(broken).toEqual([]);
  });

  it('German is translated, not copied from English', () => {
    const copied = keys.filter((k) => {
      const e = EN[k as keyof typeof EN];
      return de.translation[PREFIX + k] === e && e.split(' ').length > 2;
    });
    expect(copied).toEqual([]);
  });

  it('no text uses a long dash', () => {
    const dashed = keys.filter((k) => /[–—]/.test(EN[k as keyof typeof EN] + de.translation[PREFIX + k]));
    expect(dashed).toEqual([]);
  });

  it('the tab of the site logistics page is in both locales', () => {
    expect(en.translation['site_logistics.plan.title']).toBe('Logistics plan');
    expect(de.translation['site_logistics.plan.title']).toBe('Logistikplan');
  });
});
