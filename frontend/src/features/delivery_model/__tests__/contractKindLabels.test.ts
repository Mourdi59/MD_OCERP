// Every contract kind the shipped catalogues offer has a label in English and German.

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import en from '@/app/locales/en';
import de from '@/app/locales/de';

const ROOT = join(__dirname, '..', '..', '..', '..', '..');
const NEUTRAL = join(ROOT, 'backend', 'app', 'modules', 'delivery_model', 'catalogues', 'neutral.json');
const PACKS = join(ROOT, 'packs', 'eleven-areas-framework', 'src');

interface Kind {
  code: string;
  group: string;
  name_key?: string;
  labels?: Record<string, string>;
}

function kindsOf(path: string): Kind[] {
  return (JSON.parse(readFileSync(path, 'utf-8')) as { contract_kinds?: Kind[] }).contract_kinds ?? [];
}

describe('contract kind labels', () => {
  const neutral = kindsOf(NEUTRAL);

  it('finds the kinds it is meant to check', () => {
    expect(neutral.length).toBeGreaterThanOrEqual(21);
    expect(new Set(neutral.map((k) => k.group)).size).toBe(5);
  });

  it('labels every shipped kind in English and German', () => {
    const missing: string[] = [];
    for (const k of neutral) {
      const key = k.name_key ?? '';
      if (!en.translation[key]) missing.push(`en ${key}`);
      if (!de.translation[key]) missing.push(`de ${key}`);
      else if (de.translation[key] === en.translation[key]) missing.push(`de copied ${key}`);
    }
    expect(missing).toEqual([]);
  });

  it('gives every kind of the framework pack an English and a German label', () => {
    const dirs = readdirSync(PACKS).map((d) => join(PACKS, d, 'catalogues', 'delivery_forms'));
    const bad: string[] = [];
    for (const dir of dirs) {
      for (const f of readdirSync(dir).filter((n) => n.endsWith('.json'))) {
        for (const k of kindsOf(join(dir, f))) if (!k.labels?.en || !k.labels?.de) bad.push(k.code);
      }
    }
    expect(bad).toEqual([]);
  });
});
