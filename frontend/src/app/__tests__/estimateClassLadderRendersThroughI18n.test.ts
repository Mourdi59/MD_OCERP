// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The estimate class ladder is one table on the server, and both surfaces that
 * show it have to render its rung names in the reader's language.
 *
 * The BOQ classification panel used to print `classification.class_label`
 * straight from the API, which is English on screen in every language we ship,
 * while the fifteen keys around it for "Accuracy", "Methodology" and
 * "Definition Level" were fully translated. We translated the labels and not the
 * thing they label.
 *
 * Nothing else can catch a return to that. The computed-key guard checks whether
 * `estimateBasis.class.label.` is answered by every locale, and it would stay
 * green if this component stopped asking the question at all. So the assertion
 * has to be about the call site, and it is made against the source text for the
 * same reason `enUSFallsBackToEnglish.test.ts` reads its bundles from disk:
 * rendering this component means standing up react-query and a fetch mock to
 * prove a property that is really about one line.
 */

function readSource(relative: string): string {
  const candidates = [resolve(process.cwd(), relative), resolve(process.cwd(), 'frontend', relative)];
  const path = candidates.find(existsSync);
  if (!path) throw new Error(`cannot find ${relative}, looked in ${candidates.join(' and ')}`);
  return readFileSync(path, 'utf8');
}

function enKeys(): Record<string, string> {
  const src = readSource('src/app/locales/en.ts');
  const start = src.indexOf('{', src.indexOf('const resource'));
  const end = src.lastIndexOf('} as ');
  return new Function(`return ${src.slice(start, end + 1)}`)().translation;
}

const LADDER_PREFIX = 'estimateBasis.class.label.';
const CLASSES = [1, 2, 3, 4, 5];

describe('the estimate class ladder renders through i18n on every surface', () => {
  it('the BOQ panel does not print the server label raw', () => {
    const src = readSource('src/features/boq/EstimateClassification.tsx');
    expect(src).not.toMatch(/\{\s*classification\.class_label\s*\}/);
  });

  it('both surfaces resolve the rung name through the same key namespace', () => {
    for (const file of [
      'src/features/boq/EstimateClassification.tsx',
      'src/features/estimate-basis/BasisHeadline.tsx',
    ]) {
      expect(readSource(file), `${file} does not resolve the ladder through ${LADDER_PREFIX}`).toContain(
        LADDER_PREFIX,
      );
    }
  });

  it('en.ts answers every rung the ladder can return', () => {
    const keys = enKeys();
    const missing = CLASSES.filter((n) => !keys[`${LADDER_PREFIX}${n}`]);
    expect(missing, `rungs with no English key: ${missing.join(', ')}`).toEqual([]);
  });
});
