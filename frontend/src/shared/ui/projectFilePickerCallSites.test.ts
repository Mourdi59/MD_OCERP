// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
//
// "Project files" is not one store, and a dialog that says it is tells the
// user something false.
//
// The documents module has its filing cabinet, and several viewer modules have
// their own: PDF takeoff keeps sheets in ``oe_takeoff_document``, DWG takeoff
// keeps drawings in ``oe_dwg_takeoff``, the BIM hub keeps models. A picker
// that lists only the documents module in one of those modules cannot find the
// file that module is holding open at that very moment, and the user is told
// their own plan is not in the project.
//
// Passing ``moduleKinds`` federates the stores. Whether a call site passes it
// is invisible on screen until somebody goes looking for a file that is not
// listed, so it is pinned here instead: every caller either federates, or is
// named below with the reason it has nothing to federate. A new viewer module
// cannot quietly ship the narrow shape.

import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const SRC = resolve(__dirname, '..', '..');
const ROOTS = ['features', 'shared'];

/**
 * Callers with no store of their own, and why.
 *
 * A path lands here only when the module genuinely has nowhere else to look,
 * not when federating it is merely unfinished. Unfinished work belongs in the
 * counted list below, where it stays visible.
 */
const NO_STORE_OF_ITS_OWN: Record<string, string> = {
  'features/pointcloud/PointCloudPage.tsx':
    'Point clouds are filed as ordinary project documents; the file manager has no kind for them.',
};

/**
 * Callers that own a store and do not yet read it.
 *
 * Known and outstanding, and the count is a ratchet: it may fall, never rise.
 * The CAD explorer converts whatever it is handed, so listing the drawings and
 * models the other modules hold would offer a second conversion of a file the
 * project has already converted once. Whether that is the right thing to do
 * here is a question about the explorer rather than about this dialog, and it
 * is not answered yet.
 */
const OUTSTANDING = ['features/cad-explorer/CadDataExplorerPage.tsx'];

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'dist') continue;
    const full = resolve(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else if (entry.endsWith('.tsx')) out.push(full);
  }
  return out;
}

interface CallSite {
  path: string;
  federated: boolean;
}

function callSites(): CallSite[] {
  const found: CallSite[] = [];
  for (const root of ROOTS) {
    for (const file of walk(resolve(SRC, root))) {
      const text = readFileSync(file, 'utf-8');
      let from = 0;
      for (;;) {
        const start = text.indexOf('<ProjectFilePicker', from);
        if (start === -1) break;
        const end = text.indexOf('/>', start);
        // Every call site in the tree is a self-closing element whose props
        // hold no nested JSX. If that stops being true this reads the wrong
        // span, so say so rather than quietly measuring the wrong text.
        expect(end, `${file}: <ProjectFilePicker is not self-closing`).toBeGreaterThan(start);
        const element = text.slice(start, end);
        found.push({
          path: file.slice(SRC.length + 1).replace(/\\/g, '/'),
          federated: element.includes('moduleKinds'),
        });
        from = end;
      }
    }
  }
  return found;
}

describe('every project-file dialog reads the stores its module owns', () => {
  const sites = callSites();

  it('found the call sites at all', () => {
    // A walker that reads nothing passes every assertion below it, so state
    // the floor. Five modules offer this dialog today; the number may grow.
    expect(
      sites.length,
      `the walk over src/${ROOTS.join(', src/')} found ${sites.length} <ProjectFilePicker call sites`,
    ).toBeGreaterThanOrEqual(5);
    // The test file itself renders one, and it is not a product call site.
    expect(sites.some((s) => s.path.endsWith('.test.tsx'))).toBe(true);
  });

  it('federates everywhere except the callers named here', () => {
    const narrow = sites
      .filter((s) => !s.federated && !s.path.endsWith('.test.tsx'))
      .map((s) => s.path)
      .sort();
    const allowed = [...Object.keys(NO_STORE_OF_ITS_OWN), ...OUTSTANDING].sort();
    const unexplained = narrow.filter((p) => !allowed.includes(p));
    expect(
      unexplained,
      'A module offering "Open from project files" without moduleKinds lists only the documents ' +
        'module, so a file its own store is holding cannot be found by name. Federate it, or name ' +
        'it in NO_STORE_OF_ITS_OWN with the reason it has nothing to federate.',
    ).toEqual([]);
  });

  it('does not let the outstanding list grow', () => {
    const narrow = sites.filter((s) => !s.federated && !s.path.endsWith('.test.tsx'));
    const stillOutstanding = narrow.filter((s) => OUTSTANDING.includes(s.path)).map((s) => s.path);
    expect(
      stillOutstanding.length,
      `${stillOutstanding.length} of ${sites.length} call sites own a store they do not read: ` +
        `${stillOutstanding.join(', ') || 'none'}`,
    ).toBeLessThanOrEqual(OUTSTANDING.length);
  });

  it('keeps the modules that already federate', () => {
    // Named rather than counted, because a regression in one of these is the
    // reported bug coming back rather than a new one appearing.
    for (const path of [
      'features/takeoff/TakeoffPage.tsx',
      'features/dwg-takeoff/DwgTakeoffPage.tsx',
      'features/bim/BIMPage.tsx',
    ]) {
      const site = sites.find((s) => s.path === path);
      expect(site, `${path} no longer renders a ProjectFilePicker`).toBeDefined();
      expect(site?.federated, `${path} stopped reading its own store`).toBe(true);
    }
  });
});
