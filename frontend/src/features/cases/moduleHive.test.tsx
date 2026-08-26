// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The module honeycomb, and the shape it is cut from.
//
// Three things this pins, each of which was untrue before the honeycomb was
// carried into the product:
//
//  1. ONE DEFINITION PER SHAPE. The portrait hexagon was written out by hand in
//     three files - CasesPage, DashboardCasesCard and, with no name at all, the
//     sign-in art. Three copies of a polygon do not stay equal. The walk below
//     asserts each shape appears in exactly one source file, and asserts FIRST
//     that it actually opened a plausible number of files: a tree walk that
//     visits nothing reports every literal as absent and passes forever.
//
//  2. THE HIVE DRAWS THE CASE'S OWN MODULES. Not a fixed list, not the
//     marketing catalogue. Two different cases must produce two different
//     combs, and each comb must match what its playbook declares.
//
//  3. IDENTITY IS THE ROUTE. `types.ts` warns at length that a step's
//     `moduleLabel` and `moduleLabelKey` can disagree and that a half-corrected
//     pair reads in review as the fix working. Counting cells by label inherits
//     that; counting by route cannot.
//
// Run: npx vitest run src/features/cases/moduleHive.test.tsx --pool=forks

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve, join, basename } from 'node:path';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import {
  hiveBand,
  HEX_ASPECT,
  HEX_CELL_CLIP,
  HEX_PORTRAIT_ASPECT,
  HEX_PORTRAIT_CLIP,
} from '@/shared/lib/honeycomb';
import { modulesForPlaybook } from './playbookModules';
import { CaseModuleHive, ModuleHive } from './ModuleHive';
import { PLAYBOOKS } from './playbooks';
import type { Playbook, PlaybookStep } from './types';

vi.mock('react-i18next', () => {
  const t = (key: string, opts?: Record<string, unknown>) => {
    if (typeof opts === 'object' && opts !== null && 'defaultValue' in opts) {
      // Mirror i18next's plural pick, so a test reads the form a user reads.
      const template =
        'count' in opts && opts.count !== 1 && typeof opts.defaultValue_other === 'string'
          ? opts.defaultValue_other
          : String(opts.defaultValue);
      return template.replace(/\{\{(\w+)\}\}/g, (_m, name: string) =>
        name in opts ? String(opts[name]) : `{{${name}}}`,
      );
    }
    return key;
  };
  return {
    useTranslation: () => ({ t, i18n: { language: 'en' } }),
    initReactI18next: { type: '3rdParty', init: () => {} },
  };
});

const SRC = resolve(__dirname, '..', '..');

/** Every source file under `frontend/src`, tests excluded (a test may quote a
 *  literal in order to look for it, which is not a second definition of it). */
function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) {
      sourceFiles(path, out);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(entry)) continue;
    if (/\.test\.tsx?$/.test(entry)) continue;
    out.push(path);
  }
  return out;
}

function step(over: Partial<PlaybookStep> & Pick<PlaybookStep, 'id' | 'to' | 'moduleLabel'>): PlaybookStep {
  return {
    titleKey: `t.${over.id}`,
    titleDefault: 'Step',
    whatKey: `w.${over.id}`,
    whatDefault: 'What',
    whyKey: `y.${over.id}`,
    whyDefault: 'Why',
    ...over,
  };
}

function playbook(steps: PlaybookStep[]): Playbook {
  return {
    id: 'fixture',
    order: 1,
    category: 'estimating',
    companyTypes: ['general-contractor'],
    titleKey: 'fixture.title',
    titleDefault: 'Fixture',
    descKey: 'fixture.desc',
    descDefault: 'Fixture case',
    estMinutes: 5,
    steps,
  };
}

describe('the hexagon has one definition', () => {
  const files = sourceFiles(SRC);

  it('opened the source tree it claims to have searched', () => {
    // Without this, every assertion below is satisfied by a walk that found
    // nothing, and the suite stays green through any regression.
    expect(files.length).toBeGreaterThan(500);
    expect(files.some((f) => basename(f) === 'honeycomb.ts')).toBe(true);
  });

  it.each([
    ['portrait crop', HEX_PORTRAIT_CLIP],
    ['module cell face', HEX_CELL_CLIP],
  ])('declares the %s polygon in exactly one file', (_name, polygon) => {
    const holders = files.filter((f) => readFileSync(f, 'utf-8').includes(polygon));
    expect(holders.map((f) => basename(f))).toEqual(['honeycomb.ts']);
  });

  it('keeps the two shapes distinct', () => {
    // The portrait points up and down, the cell face points left and right.
    // Collapsing them would silently re-cut every case portrait sideways.
    expect(HEX_PORTRAIT_CLIP).not.toEqual(HEX_CELL_CLIP);
  });

  it('anchors cells on the inline axis so the comb mirrors in RTL', () => {
    const source = readFileSync(resolve(__dirname, 'ModuleHive.tsx'), 'utf-8');
    expect(source).toContain('insetInlineStart');
  });

  it('pins nothing in ModuleHive.tsx to a physical edge', () => {
    // A physical edge here would pin the band to the same side in Arabic,
    // Hebrew, Persian and Urdu, where it has to start from the other one.
    const source = readFileSync(resolve(__dirname, 'ModuleHive.tsx'), 'utf-8');
    // `left: 0` and `left:0` alike. Case-sensitive, so `marginLeft` is safe.
    expect(source).not.toMatch(/\bleft\s*:/);
    // And the Tailwind half of the same mistake: `start-`/`end-`, not
    // `left-`/`right-`.
    expect(source).not.toMatch(/["'\s](left|right)-/);
  });
});

describe('the hexagons are regular', () => {
  // A reader called the shipped portrait a stretched diamond, and they were
  // right on both counts a clip path can be wrong.
  //
  // A clip path cuts percentages of whatever box it is handed, so the polygon
  // cannot make a shape regular on its own - the box decides. The cards handed
  // it `aspect-[7/8]` and the sign-in art handed it 88x100, against the 0.866
  // a pointy-top regular hexagon needs, and the slanted sides came out 3.96%
  // and 4.42% longer than the vertical ones.
  //
  // The polygon was independently wrong: at `50% 2%, 100% 26%` the inset
  // shortens the slanted pair against the vertical pair whatever the box, so
  // no amount of resizing could have made it regular.
  //
  // Both halves are asserted here as arithmetic rather than as string
  // equality. A literal comparison would pin today's polygon and say nothing
  // about whether it draws equal sides, which is the property a person sees.

  /** Vertices of a `polygon(...)` clip path as fractions of its box. */
  function vertices(clip: string): Array<[number, number]> {
    const inner = clip.slice(clip.indexOf('(') + 1, clip.lastIndexOf(')'));
    return inner.split(',').map((point) => {
      const [x, y] = point.trim().split(/\s+/);
      // Read explicitly rather than trusted. A missing half reaches parseFloat
      // as undefined and comes back NaN, and every comparison below against a
      // NaN is false, so a malformed polygon would pass the spread checks
      // instead of failing them - the one outcome this file must never have.
      if (x === undefined || y === undefined) {
        throw new Error(`not an "x y" vertex: ${JSON.stringify(point)}`);
      }
      return [parseFloat(x) / 100, parseFloat(y) / 100] as [number, number];
    });
  }

  /** Side lengths of the polygon drawn in a box `width` by `height`. */
  function sides(clip: string, width: number, height: number): number[] {
    const points = vertices(clip);
    return points.map(([x, y], i) => {
      const next = points[(i + 1) % points.length];
      if (next === undefined) throw new Error(`the polygon has no vertex after ${i}`);
      const [nx, ny] = next;
      return Math.hypot((nx - x) * width, (ny - y) * height);
    });
  }

  function spread(lengths: number[]): number {
    return Math.max(...lengths) / Math.min(...lengths) - 1;
  }

  it('cuts six equal sides for a portrait in a box of its declared aspect', () => {
    const lengths = sides(HEX_PORTRAIT_CLIP, HEX_PORTRAIT_ASPECT, 1);
    expect(lengths).toHaveLength(6);
    expect(spread(lengths)).toBeLessThan(0.001);
  });

  it('cuts six equal sides for a cell face in a box of its declared aspect', () => {
    const lengths = sides(HEX_CELL_CLIP, 1, HEX_ASPECT);
    expect(lengths).toHaveLength(6);
    expect(spread(lengths)).toBeLessThan(0.001);
  });

  it('puts the two halves of the old defect on record separately', () => {
    // A witness, not a regression guard: if the arithmetic above ever stops
    // being able to tell an irregular hexagon from a regular one, these two
    // numbers move and the tests before them start asserting nothing.
    //
    // The shipped shape was wrong twice over, and the halves are not the same
    // size. Writing one number for both is how the first draft of this test
    // came to claim 3.96% for a box that produces 0.78%.
    const inset = 'polygon(50% 2%, 100% 26%, 100% 74%, 50% 98%, 0% 74%, 0% 26%)';

    // Both halves together, which is what a reader actually saw.
    expect(spread(sides(inset, 7 / 8, 1))).toBeGreaterThan(0.039);
    // The polygon alone, in a box of the right aspect: still irregular, so it
    // could never have been fixed by resizing.
    expect(spread(sides(inset, HEX_PORTRAIT_ASPECT, 1))).toBeGreaterThan(0.03);
    // The box alone, with the polygon corrected: smaller, and still visible.
    expect(spread(sides(HEX_PORTRAIT_CLIP, 7 / 8, 1))).toBeGreaterThan(0.007);
  });

  it('constrains the box everywhere the portrait crop is applied', () => {
    // The polygon being right is half the shape. A call site that applies the
    // clip without fixing the box ships the stretched diamond again, and every
    // assertion above stays green while it does.
    //
    // Comments are stripped first, and that is not tidiness. A file that says
    // in prose "the portrait is cut to HEX_CELL_CLIP, not HEX_PORTRAIT_CLIP,
    // and here is why" names the constant more times than a file that uses it,
    // and a detector reading raw text cannot tell a denial from a use: it
    // convicted the one file in the tree that had gone out of its way to
    // explain it was doing the right thing. The rule is about code, so the
    // reader has to be given code.
    const withoutComments = (file: string) =>
      readFileSync(file, 'utf-8')
        .replace(/\/\*[\s\S]*?\*\//g, ' ')
        .replace(/^\s*\/\/.*$/gm, ' ');

    const appliers = sourceFiles(SRC).filter((file) => {
      if (basename(file) === 'honeycomb.ts' || file.endsWith('.test.tsx')) return false;
      return withoutComments(file).includes('HEX_PORTRAIT_CLIP');
    });
    expect(appliers.length).toBeGreaterThan(0);

    // The rule is naming the constant, not writing a box that happens to be
    // the right shape. The first draft of this test accepted a hand-written
    // pixel pair, and matched the first `w-[..] h-[..]` anywhere in the file -
    // an 18px icon on a line that had nothing to do with the crop. A check
    // that can be satisfied by an unrelated line is not a check.
    const unconstrained = appliers
      .filter((file) => !withoutComments(file).includes('HEX_PORTRAIT_ASPECT'))
      .map((file) => basename(file));
    expect(unconstrained).toEqual([]);
  });

  it('still convicts a file that applies the crop in code and never bounds it', () => {
    // The negative control the check above needs, because stripping comments
    // is exactly the kind of edit that can quietly turn a guard into a pass.
    // The fixture names the constant on a code line, so a working detector has
    // to see it; the denial line beside it is the shape that caused the false
    // conviction, and a detector that reads it as a use fails here too.
    const withoutComments = (source: string) =>
      source.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');

    const applies = 'const clip = HEX_PORTRAIT_CLIP;';
    const denies = '// cut to HEX_CELL_CLIP, not HEX_PORTRAIT_CLIP, and HEX_PORTRAIT_ASPECT';
    const guilty = withoutComments(`${denies}\n${applies}`);
    expect(guilty).toContain('HEX_PORTRAIT_CLIP');
    expect(guilty).not.toContain('HEX_PORTRAIT_ASPECT');
    expect(withoutComments(denies)).not.toContain('HEX_PORTRAIT_CLIP');
  });
});

describe('hiveBand', () => {
  it('interlocks columns by half a cell', () => {
    const layout = hiveBand(5, 82, 2);
    const pitch = layout.placements[2]!.inlineStart;
    expect(pitch).toBeGreaterThan(0);
    // Column-major: two cells per column, so 0/1 share a column, 2/3 the next.
    expect(layout.placements.map((p) => p.inlineStart)).toEqual([
      0, 0, pitch, pitch, pitch * 2,
    ]);
    const half = Math.round(layout.cellHeight / 2);
    expect(layout.placements.map((p) => p.top)).toEqual([
      0,
      layout.cellHeight,
      half,
      layout.cellHeight + half,
      0,
    ]);
  });

  it('measures the stage from the cells that are there', () => {
    const three = hiveBand(3, 80, 2);
    const nine = hiveBand(9, 80, 2);
    expect(three.width).toBeLessThan(nine.width);
    expect(three.width).toBe(three.placements[2]!.inlineStart + three.cellWidth);
    expect(hiveBand(0, 80).width).toBe(0);
  });
});

describe('modulesForPlaybook', () => {
  it('lists the modules in the order the case reaches them', () => {
    const pb = playbook([
      step({ id: 'a', to: '/projects/:projectId/files', moduleLabel: 'Documents' }),
      step({ id: 'b', to: '/boq', moduleLabel: 'BOQ' }),
    ]);
    expect(modulesForPlaybook(pb).map((m) => m.route)).toEqual(['/files', '/boq']);
    expect(modulesForPlaybook(pb).map((m) => m.label)).toEqual(['Documents', 'BOQ']);
  });

  it('counts one module per route however the steps label it', () => {
    // The same module, reached twice, under two spellings. One hexagon.
    const pb = playbook([
      step({ id: 'a', to: '/projects/:projectId/files', moduleLabel: 'Documents' }),
      step({ id: 'b', to: '/boq', moduleLabel: 'BOQ' }),
      step({ id: 'c', to: '/files?tab=approvals', moduleLabel: 'Project files' }),
    ]);
    const mods = modulesForPlaybook(pb);
    expect(mods).toHaveLength(2);
    // The first step at that route owns the label, so the cell says what the
    // step chip above it says.
    expect(mods[0]!.label).toBe('Documents');
  });

  it('carries the label key through, not just the English', () => {
    const pb = playbook([
      step({ id: 'a', to: '/rfi', moduleLabel: 'RFIs', moduleLabelKey: 'nav.rfi' }),
    ]);
    expect(modulesForPlaybook(pb)[0]!.labelKey).toBe('nav.rfi');
  });
});

describe('CaseModuleHive', () => {
  it('draws the modules the case declares, not a fixed list', () => {
    const pb = playbook([
      step({ id: 'a', to: '/projects/:projectId/files', moduleLabel: 'Documents' }),
      step({ id: 'b', to: '/boq', moduleLabel: 'BOQ' }),
      step({ id: 'c', to: '/validation', moduleLabel: 'Validation' }),
    ]);
    render(<CaseModuleHive playbook={pb} />);
    const cells = screen.getAllByRole('listitem');
    expect(cells).toHaveLength(3);
    expect(cells.map((c) => c.textContent)).toEqual(['Documents', 'BOQ', 'Validation']);
  });

  it('draws a different comb for a different case', () => {
    // The load-bearing one: a hard-coded hive passes every test above and
    // fails this.
    const a = PLAYBOOKS[0]!;
    const b = PLAYBOOKS.find(
      (p) =>
        modulesForPlaybook(p)
          .map((m) => m.route)
          .join('|') !==
        modulesForPlaybook(a)
          .map((m) => m.route)
          .join('|'),
    );
    expect(b).toBeDefined();

    const first = render(<CaseModuleHive playbook={a} />);
    const drawnA = screen.getAllByRole('listitem').map((c) => c.textContent);
    expect(drawnA).toHaveLength(modulesForPlaybook(a).length);
    first.unmount();

    render(<CaseModuleHive playbook={b!} />);
    const drawnB = screen.getAllByRole('listitem').map((c) => c.textContent);
    expect(drawnB).toHaveLength(modulesForPlaybook(b!).length);
    expect(drawnB).not.toEqual(drawnA);
  });

  it('names the hive for a screen reader and hides only the drawing', () => {
    const pb = playbook([
      step({ id: 'a', to: '/boq', moduleLabel: 'BOQ' }),
    ]);
    render(<CaseModuleHive playbook={pb} />);
    // The comb is content: it is reachable as a named list, and the module
    // name is real text inside it rather than an image or a background.
    const list = screen.getByRole('list', { name: /modules this case walks through/i });
    expect(list).toBeInTheDocument();
    expect(screen.getByText('BOQ')).toBeInTheDocument();
  });

  it('counts a single module in the singular', () => {
    // The count is a plural key. Written with one form it reads "1 modules"
    // in English and loses every other language's forms at the same time.
    render(<CaseModuleHive playbook={playbook([step({ id: 'a', to: '/boq', moduleLabel: 'BOQ' })])} />);
    expect(screen.getByText('1 module')).toBeInTheDocument();
  });

  it('renders nothing for a case with no steps', () => {
    const { container } = render(<CaseModuleHive playbook={playbook([])} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('the product hive cannot reproduce the catalogue defects', () => {
  // `scripts/check_case_module_chips.py` guards a real mechanism on the public
  // site: the hex titles live in a hand-authored catalogue, and a hex is
  // localised by copying the translated step chip whose label matches it
  // EXACTLY. A hex the match misses renders in English in every language, and
  // a case the catalogue has no entry for renders no honeycomb at all.
  //
  // Both failures are properties of the catalogue being a second, hand-kept
  // copy. The product's hive is derived from the playbook steps instead, so
  // the two are the same object and cannot disagree. These pin that, because
  // "derived" is a claim about the code that a later refactor can quietly undo.

  it('gives every case a honeycomb, including cases no catalogue lists', () => {
    const empty = PLAYBOOKS.filter((p) => modulesForPlaybook(p).length === 0);
    expect(empty.map((p) => p.id)).toEqual([]);
  });

  it('gives every hex an i18n key, so none can render English forever', () => {
    const keyless = PLAYBOOKS.flatMap((p) =>
      modulesForPlaybook(p)
        .filter((m) => !m.labelKey)
        .map((m) => `${p.id}: ${m.route}`),
    );
    expect(keyless).toEqual([]);
  });
});

describe('ModuleHive glyphs', () => {
  it('draws a glyph for a route the icon map has never heard of', () => {
    // Measured: 3 of the 110 module routes the playbooks reach resolve to no
    // icon. Rendering those cells as bare text beside iconed neighbours reads
    // as a broken cell rather than as a module nobody gave a glyph.
    const { container } = render(
      <ModuleHive cells={[{ route: '/no-such-module-anywhere', label: 'Unmapped' }]} label="Modules" />,
    );
    expect(container.querySelectorAll('svg')).toHaveLength(1);
  });

  it('leaves no cell bare across every module the real cases reach', () => {
    const routes = [...new Set(PLAYBOOKS.flatMap((p) => modulesForPlaybook(p)).map((m) => m.route))];
    expect(routes.length).toBeGreaterThan(50);
    const { container } = render(
      <ModuleHive cells={routes.map((route) => ({ route, label: route }))} label="Modules" />,
    );
    expect(container.querySelectorAll('svg')).toHaveLength(routes.length);
  });
});

describe('ModuleHive interactivity', () => {
  const cells = [
    { route: '/boq', label: 'BOQ' },
    { route: '/files', label: 'Documents' },
  ];

  it('offers no buttons when there is nothing to activate', () => {
    // A hexagon that looks pressable and does nothing is a dead control.
    render(<ModuleHive cells={cells} label="Modules" />);
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('reports the module that was activated', () => {
    const onSelect = vi.fn();
    render(<ModuleHive cells={cells} label="Modules" onSelect={onSelect} />);
    screen.getByRole('button', { name: /documents/i }).click();
    expect(onSelect).toHaveBeenCalledWith('/files');
  });

  it('says in words what the mark means', () => {
    render(
      <ModuleHive
        cells={[{ route: '/boq', label: 'BOQ', marked: true }]}
        label="Modules"
        markLabel="In progress"
      />,
    );
    // Colour alone cannot carry a meaning.
    expect(screen.getByText('In progress')).toBeInTheDocument();
  });
});
