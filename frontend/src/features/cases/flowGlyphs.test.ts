// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// The glyph beside a "Goes in" / "Comes out" row has one job: say what the
// artefact is, the same way in every language. These tests hold the two ways
// that quietly stops being true.
//
// One, the drawing goes blank. A kind with no paths, or a resolver that starts
// answering `document` for everything, renders a column of empty space that
// still passes every render test, because the text beside it is unchanged.
// So the coverage is measured against the real case library rather than
// against a handful of examples.
//
// Two, the order of the rules rots. The matcher is a list, and the whole
// correctness of it is that a compound is tested before the bare word it
// contains: `schedule of values` is a bill, a bare `schedule` is a programme.
// Appending a new rule in the wrong place is a one-line change with no visible
// symptom outside these assertions.

import { describe, it, expect } from 'vitest';
import { PLAYBOOKS } from './playbooks';
import { flowGlyphFor, type FlowGlyphKind } from './flowGlyphs';

/** Every English flow label the case library declares, both sides. */
function everyLabel(): string[] {
  const out: string[] = [];
  for (const pb of PLAYBOOKS) {
    for (const step of pb.steps) {
      for (const item of step.inputs ?? []) out.push(item.label);
      for (const item of step.outputs ?? []) out.push(item.label);
    }
  }
  return out;
}

describe('flowGlyphFor', () => {
  it('reads a compound before the bare word inside it', () => {
    // Each pair is a label that contains a word belonging to another kind. If
    // the matcher is ever reordered so the bare word wins, these flip.
    expect(flowGlyphFor('Schedule of values')).toBe('bill');
    expect(flowGlyphFor('Baseline programme')).toBe('programme');
    expect(flowGlyphFor('Point cloud')).toBe('model');
    expect(flowGlyphFor('Drawing register')).toBe('register');
    expect(flowGlyphFor('Site photo')).toBe('photo');
  });

  it('names the artefact for the shapes an estimator hands over', () => {
    const cases: ReadonlyArray<readonly [string, FlowGlyphKind]> = [
      ['Priced BOQ', 'bill'],
      ['Revised drawing', 'drawing'],
      ['Federated model', 'model'],
      ['Unit rates', 'rates'],
      ['Payment certificate', 'money'],
      ['Validation report', 'check'],
      ['Clash results', 'model'],
      ['Purchase order', 'contract'],
      ['Asset register', 'register'],
      ['GAEB X83 file', 'file'],
      ['Project team', 'person'],
      ['Diary entry', 'site'],
      ['RFI response', 'message'],
      ['Outstanding items', 'register'],
      ['Product warranties', 'contract'],
      // German cases name some artefacts in German. The split that finds words
      // is unicode-aware for exactly this, so the stem still matches.
      ['Nebenangebot rule', 'contract'],
      // And an LV is a bill of quantities, so the alternative bid's LV is a
      // bill and not the bid document: the bill group is read first on purpose.
      ['Nebenangebot LV', 'bill'],
      ['Aufmaß je Position', 'bill'],
    ];
    for (const [label, kind] of cases) {
      expect(flowGlyphFor(label), label).toBe(kind);
    }
  });

  it('does not care how the label is cased', () => {
    expect(flowGlyphFor('PRICED BOQ')).toBe(flowGlyphFor('priced boq'));
  });

  it('falls back to a document rather than to nothing', () => {
    // A blank where the neighbouring rows carry a drawing reads as a broken
    // render; a plain document reads as "some artefact", which is true.
    expect(flowGlyphFor('Zzzz qqqq')).toBe('document');
    expect(flowGlyphFor('')).toBe('document');
  });

  it('draws something specific for most of the real library', () => {
    // Measured, not guessed: the labels are a long tail of over a thousand
    // distinct strings, so the bar is a floor under the real number rather
    // than a target. It exists to catch a resolver that has quietly collapsed,
    // which is the failure that leaves the column looking fine.
    const labels = everyLabel();
    expect(labels.length).toBeGreaterThan(500);
    const specific = labels.filter((l) => flowGlyphFor(l) !== 'document').length;
    // Measured at 0.858 over 2479 labels when this was written.
    expect(specific / labels.length).toBeGreaterThan(0.8);
  });
});
