// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Every message key the project handbook screens use resolves in English and
// German, and the route and the link from the project page are registered.

import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import en from '@/app/locales/en';
import de from '@/app/locales/de';
import { CHAPTER_STATUS, SOURCE_TITLE } from '../labels';

const featureDir = join(__dirname, '..');
const sources = readdirSync(featureDir)
  .filter((f) => /\.(ts|tsx)$/.test(f))
  .map((f) => readFileSync(join(featureDir, f), 'utf-8'))
  .join('\n');
const srcRoot = join(__dirname, '..', '..', '..');

const used = new Set<string>();
for (const m of sources.matchAll(/'(projectHandbook\.[A-Za-z0-9_.]+)'/g)) used.add(m[1]!);
for (const map of [CHAPTER_STATUS, SOURCE_TITLE]) {
  for (const [key] of Object.values(map)) used.add(key);
}
// Keys built from a code the server sends.
for (const k of Object.keys(en.translation)) {
  if (/^projectHandbook\.(finding|data_room\.phase)\./.test(k)) used.add(k);
}

describe('project handbook i18n keys', () => {
  it('finds the keys it is meant to check', () => {
    expect(used.size).toBeGreaterThan(60);
    expect(used.has('projectHandbook.title')).toBe(true);
  });

  it('resolves every key in English and German', () => {
    const en_ = en.translation as Record<string, string>;
    const de_ = de.translation as Record<string, string>;
    const missing = [...used].filter((k) => !(k in en_) || !(k in de_));
    expect(missing).toEqual([]);
  });

  it('registers the route and the link from the project page', () => {
    const app = readFileSync(join(srcRoot, 'app', 'App.tsx'), 'utf-8');
    expect(app).toContain('/projects/:projectId/handbook');
    const detail = readFileSync(join(srcRoot, 'features', 'projects', 'ProjectDetailPage.tsx'), 'utf-8');
    expect(detail).toContain('project-handbook-link');
  });
});
