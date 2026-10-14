// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Every message key the engineering brief screens use resolves in English and
// German, every API path is written in full in the call that sends it, and the
// route and the page title are registered.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { BRIEF_STATUS, CONCEPT_STATUS, CONSTRAINT_LABEL, PRIORITY_LABEL } from '../labels';

const featureDir = join(__dirname, '..');
const sources = readdirSync(featureDir)
  .filter((f) => /\.(ts|tsx)$/.test(f))
  .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
  .join('\n');
const srcRoot = join(__dirname, '..', '..', '..');

const used = new Set<string>();
for (const m of sources.matchAll(/'(engineeringBrief\.[A-Za-z0-9_.]+)'/g)) used.add(m[1]!);
for (const map of [BRIEF_STATUS, PRIORITY_LABEL, CONSTRAINT_LABEL, CONCEPT_STATUS]) {
  for (const [key] of Object.values(map)) used.add(key);
}
// Keys built from a code the server or the catalogue sends.
for (const k of Object.keys(en.translation)) {
  if (/^engineeringBrief\.(role|phase)\./.test(k)) used.add(k);
  if (/^engineering_brief\.(errors|verification|category|topic|programme_kind|milestone_kind|catalogue)\./.test(k)) used.add(k);
}

describe('engineering brief i18n keys', () => {
  it('finds the keys it is meant to check', () => {
    expect(used.size).toBeGreaterThan(200);
    expect(used.has('engineeringBrief.title')).toBe(true);
    expect(used.has('engineering_brief.errors.category_uncovered')).toBe(true);
  });

  it('resolves every key in English', () => {
    const missing = [...used].filter((k) => !(k in en.translation));
    expect(missing).toEqual([]);
  });

  it('resolves every key in German with its own text', () => {
    const missing = [...used].filter((k) => !(k in de.translation));
    expect(missing).toEqual([]);
    const copied = [...used].filter(
      (k) => k.startsWith('engineeringBrief.') && de.translation[k] === en.translation[k] && !/^(engineeringBrief\.(export\.|title$))/.test(k) && en.translation[k]!.length > 12,
    );
    expect(copied).toEqual([]);
  });

  it('keeps German umlauts and never a transliteration', () => {
    const german = [...used].filter((k) => k.startsWith('engineeringBrief.')).map((k) => de.translation[k] ?? '');
    expect(german.some((v) => /[äöüß]/.test(v))).toBe(true);
    expect(german.filter((v) => /\b\w*(ae|oe|ue)\w*\b/.test(v) && /Pruefung|Aenderung|Uebergabe|Faehig|Loesch/.test(v))).toEqual([]);
  });

  it('keeps the placeholders of the English text in the German text', () => {
    for (const k of used) {
      const placeholders = (en.translation[k] ?? '').match(/\{\{\w+\}\}/g) ?? [];
      for (const p of placeholders) expect(de.translation[k], k).toContain(p);
    }
  });
});

describe('engineering brief wiring', () => {
  it('writes every API path in full, in the call that sends it', () => {
    const client = readFileSync(join(featureDir, 'api.ts'), 'utf-8');
    const calls = [...client.matchAll(/\bapi(Get|Post|Patch|Put|Delete)(<[^(]*>)?\(\s*(\S+)/g)];
    expect(calls.length).toBeGreaterThan(20);
    expect(calls.filter((m) => !m[3]!.startsWith("'/v1/engineering_brief/") && !m[3]!.startsWith('`/v1/engineering_brief/'))).toEqual([]);
  });

  it('is routed, titled and linked from the project', () => {
    const app = readFileSync(join(srcRoot, 'app', 'App.tsx'), 'utf-8');
    expect(app).toContain('path="/projects/:projectId/engineering-brief"');
    const header = readFileSync(join(srcRoot, 'app', 'layout', 'Header.tsx'), 'utf-8');
    expect(header).toContain("'Engineering brief': 'engineeringBrief.title'");
    const detail = readFileSync(join(srcRoot, 'features', 'projects', 'ProjectDetailPage.tsx'), 'utf-8');
    expect(detail).toContain('/engineering-brief');
  });
});
