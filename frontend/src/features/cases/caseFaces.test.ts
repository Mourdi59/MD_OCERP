// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Gate for the case-photography plumbing. The one that matters most is the
// closed-set check at the bottom: every path the module can EVER return must
// name a file that exists under frontend/public/assets/people, so a renamed
// or deleted webp fails here instead of 404ing in production.

import { describe, expect, it } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  BESPOKE_CASE_PHOTOS,
  PEOPLE_ASSETS_BASE,
  ROLE_CAST,
  type CaseRole,
  caseFaceFor,
  companySceneFor,
  companyThumbFor,
  dealCaseFaces,
} from './caseFaces';
import { COMPANY_TYPE_META } from './companyTypes';
import { PLAYBOOKS } from './playbooks';

const HERE = dirname(fileURLToPath(import.meta.url));
const PEOPLE_DIR = resolve(HERE, '../../../public/assets/people');
const PRESETS_PY = resolve(HERE, '../../../../backend/app/core/onboarding_presets.py');

/** The closed set of files actually on disk. */
const filesOnDisk = new Set(readdirSync(PEOPLE_DIR));

/** Assert a public path returned by the module names a real file. */
function expectOnDisk(publicPath: string | null): void {
  expect(publicPath).not.toBeNull();
  expect(publicPath!.startsWith(`${PEOPLE_ASSETS_BASE}/`)).toBe(true);
  const file = publicPath!.slice(`${PEOPLE_ASSETS_BASE}/`.length);
  expect(filesOnDisk, `${file} is not in public/assets/people`).toContain(file);
}

/** The backend's company preset keys, read from the source of truth
 *  (COMPANY_PRESETS only - the SIZE_PRESETS dict below it is a different
 *  dimension and has no photos). */
function backendPresetKeys(): string[] {
  const text = readFileSync(PRESETS_PY, 'utf-8');
  const start = text.indexOf('COMPANY_PRESETS');
  const end = text.indexOf('SIZE_PRESETS');
  const section = text.slice(start, end === -1 ? undefined : end);
  const keys = [...section.matchAll(/key="([a-z0-9_]+)"/g)].map((m) => m[1]!);
  // The wizard shows at least the nine headline profiles; the catalogue has
  // grown past that. If this drops below nine the slice above went stale.
  expect(keys.length).toBeGreaterThanOrEqual(9);
  return keys;
}

describe('companyThumbFor', () => {
  it('resolves every COMPANY_TYPE_META id (hyphenated scheme) to a file on disk', () => {
    for (const meta of COMPANY_TYPE_META) {
      expectOnDisk(companyThumbFor(meta.id));
    }
  });

  it('resolves every backend onboarding preset key (underscored scheme) to a file on disk', () => {
    for (const key of backendPresetKeys()) {
      expectOnDisk(companyThumbFor(key));
    }
  });

  it('returns null for an unknown id instead of minting a 404 path', () => {
    expect(companyThumbFor('interior-decorator')).toBeNull();
    expect(companyThumbFor('')).toBeNull();
  });
});

describe('companySceneFor', () => {
  it('resolves every COMPANY_TYPE_META id (hyphenated scheme) to a file on disk', () => {
    for (const meta of COMPANY_TYPE_META) {
      expectOnDisk(companySceneFor(meta.id));
    }
  });

  it('resolves every backend onboarding preset key (underscored scheme) to a file on disk', () => {
    for (const key of backendPresetKeys()) {
      expectOnDisk(companySceneFor(key));
    }
  });

  it('returns null for an unknown id instead of minting a 404 path', () => {
    expect(companySceneFor('interior-decorator')).toBeNull();
    expect(companySceneFor('')).toBeNull();
  });

  it('names the same stem as the thumb it is cropped from', () => {
    for (const meta of COMPANY_TYPE_META) {
      const thumb = companyThumbFor(meta.id)!;
      expect(companySceneFor(meta.id)).toBe(thumb.replace('/cmt-', '/cmp-'));
    }
  });
});

/** A value that is NOT in the company vocabulary.
 *
 *  `caseFaceFor` and `CaseFaceInput` take `CompanyType` rather than `string`,
 *  so a caller can no longer wander into the unknown-id branch by accident -
 *  which is the point of the types. The branch still has to hold at runtime,
 *  because both id schemes arrive as plain strings from the server and from
 *  localStorage, so the only way left to test it is to force one through. The
 *  double assertion is deliberate and is the marker for "this is a negative
 *  control", not a shortcut around a type that was inconvenient. */
const NOT_A_COMPANY_TYPE = 'interior-decorator' as unknown as CaseRole;

describe('caseFaceFor', () => {
  const roles = Object.keys(ROLE_CAST) as CaseRole[];

  it('is deterministic - same inputs, same face', () => {
    for (const role of roles) {
      for (let i = 0; i < 5; i++) {
        expect(caseFaceFor('some-case', [role], i)).toBe(caseFaceFor('some-case', [role], i));
      }
    }
  });

  it('never repeats a face on adjacent indices within a role whose cast has more than one member', () => {
    for (const role of roles) {
      const cast = ROLE_CAST[role];
      if (cast.length < 2) continue;
      for (let i = 0; i < cast.length * 2; i++) {
        const a = caseFaceFor('case-a', [role], i);
        const b = caseFaceFor('case-b', [role], i + 1);
        expect(a, `role ${role}, indices ${i}/${i + 1}`).not.toBe(b);
      }
    }
  });

  it('lets the first castable company type win, like the site keys on the first data-companies token', () => {
    expect(caseFaceFor('some-case', ['cost-consultant', 'general-contractor'], 0)).toBe(
      `${PEOPLE_ASSETS_BASE}/prf-estimator.webp`,
    );
    expect(caseFaceFor('some-case', [NOT_A_COMPANY_TYPE, 'designer'], 0)).toBe(
      `${PEOPLE_ASSETS_BASE}/prf-architecture-engineering.webp`,
    );
  });

  it('lets a bespoke pbk photo win over the pooled company cast', () => {
    for (const [slug, photo] of Object.entries(BESPOKE_CASE_PHOTOS)) {
      expect(caseFaceFor(slug, ['general-contractor'], 3)).toBe(photo);
    }
  });

  it('returns null when no company type has a cast', () => {
    expect(caseFaceFor('some-case', [NOT_A_COMPANY_TYPE], 0)).toBeNull();
    expect(caseFaceFor('some-case', [], 0)).toBeNull();
  });
});

describe('dealCaseFaces', () => {
  it('deals each role round its cast by position, like the site', () => {
    const cast = ROLE_CAST['general-contractor'];
    const faces = dealCaseFaces(
      cast.map((_, i) => ({ id: `case-${i}`, companyTypes: ['general-contractor'] })),
    );
    cast.forEach((stem, i) => {
      expect(faces.get(`case-${i}`)).toBe(`${PEOPLE_ASSETS_BASE}/${stem}.webp`);
    });
  });

  it('lets a bespoke case take its turn, so it does not re-cast the ones after it', () => {
    const cast = ROLE_CAST['general-contractor'];
    const faces = dealCaseFaces([
      { id: 'answer-an-rfi', companyTypes: ['general-contractor'] },
      { id: 'plain-case', companyTypes: ['general-contractor'] },
    ]);
    expect(faces.get('answer-an-rfi')).toBe(BESPOKE_CASE_PHOTOS['answer-an-rfi']);
    expect(faces.get('plain-case')).toBe(`${PEOPLE_ASSETS_BASE}/${cast[1]}.webp`);
  });

  it('counts each role on its own, so one role does not move another along', () => {
    const faces = dealCaseFaces([
      { id: 'a', companyTypes: ['general-contractor'] },
      { id: 'b', companyTypes: ['designer'] },
      { id: 'c', companyTypes: ['designer'] },
    ]);
    expect(faces.get('a')).toBe(`${PEOPLE_ASSETS_BASE}/${ROLE_CAST['general-contractor'][0]}.webp`);
    expect(faces.get('b')).toBe(`${PEOPLE_ASSETS_BASE}/${ROLE_CAST['designer'][0]}.webp`);
    expect(faces.get('c')).toBe(`${PEOPLE_ASSETS_BASE}/${ROLE_CAST['designer'][1]}.webp`);
  });

  it('leaves out a case whose company types have no cast rather than guessing', () => {
    const faces = dealCaseFaces([
      { id: 'no-types', companyTypes: [] },
      { id: 'unknown-type', companyTypes: [NOT_A_COMPANY_TYPE] },
    ]);
    expect(faces.size).toBe(0);
  });
});

describe('closed set - every path the module can ever return exists on disk', () => {
  it('covers every pooled portrait reachable through caseFaceFor', () => {
    for (const companyType of Object.keys(ROLE_CAST) as CaseRole[]) {
      const cast = ROLE_CAST[companyType];
      for (let i = 0; i < cast.length; i++) {
        expectOnDisk(caseFaceFor('no-bespoke-case', [companyType], i));
      }
    }
  });

  it('covers every bespoke photo', () => {
    for (const [slug, photo] of Object.entries(BESPOKE_CASE_PHOTOS)) {
      expect(photo).toBe(`${PEOPLE_ASSETS_BASE}/pbk-${slug}.webp`);
      expectOnDisk(photo);
    }
  });

  it('covers every company thumb and scene reachable from either id scheme', () => {
    const ids = [...COMPANY_TYPE_META.map((m) => m.id as string), ...backendPresetKeys()];
    for (const id of ids) {
      expectOnDisk(companyThumbFor(id));
      expectOnDisk(companySceneFor(id));
    }
  });

  // The tests above feed hand-written role arrays, which can only prove the
  // module is consistent with itself. This one runs the real catalogue through
  // the same call the Cases hub makes, so a case shipping a company type
  // nobody cast - or a webp leaving the folder - fails here.
  it('gives every shipped case a face that exists on disk', () => {
    const faces = dealCaseFaces(PLAYBOOKS);
    const missing = PLAYBOOKS.filter((pb) => !faces.has(pb.id)).map((pb) => pb.id);
    expect(missing, 'cases with no castable company type').toEqual([]);
    for (const path of faces.values()) expectOnDisk(path);
  });
});
