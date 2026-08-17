// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// One route, one module chip.
//
// Every playbook step carries a chip: a visible label, the i18n key that label
// is translated through, and the route the chip walks to. The chip is a
// breadcrumb into the sidebar, so two cases sending a reader to the same screen
// have to name that screen the same way. They frequently do not, and the two
// ways that fails are not the same defect:
//
//   * Two different KEYS on one route. Invisible in English whenever both keys
//     happen to render the same word, and visible in every locale where they
//     do not. This is the one that reaches a user, and no English-language
//     review can see it, which is why it needs a machine.
//   * One key under two spellings of the LABEL ('Field Time' / 'Field time').
//     No locale effect at all, because the label is only a fallback for the
//     key. Untidy source, nothing more.
//
// They are reported separately on purpose. Printing an untidy capital letter
// next to a word that comes out wrong in forty-two languages teaches the reader
// to skim both.
//
// Where the right key is disputed, the tie-break is the LIVE NAVIGATION, not
// the playbook majority: the key the sidebar itself puts on that route wins,
// because that is the word the reader sees on arrival. A majority of playbooks
// is a count of authors, not a fact about the destination.
//
// What this file checks is narrower than that tie-break, and the difference
// matters. It enforces that the chips agree with EACH OTHER. It does not
// compare them against `navCatalog.ts`, so a route where every case unanimously
// uses a key the navigation never puts there passes cleanly. Measured
// 2026-08-17 against both live surfaces: 75 routes unanimous and matching, 16
// unanimous and contradicting, 23 split, 7 on routes neither surface carries.
// Those 16 are a separate piece of work with an owner; do not read a green run
// here as "the chips agree with the sidebar".
//
// The baselines below are a shrink list, not an allowlist. They record the
// splits that predate this gate so the suite is not red on arrival, and they
// are compared by exact key set: a baselined route that grows a new variant
// goes red, and so does one that gets fixed, because a fixed route has to leave
// the list. Nothing may be added to either baseline.

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { PLAYBOOKS } from './playbooks';

/**
 * Routes already carrying more than one key when this gate landed, with the
 * exact keys each one carries. 23 routes across 140 of the 163 case files.
 * Owner: the case-catalogue maintainer. Shrinks only.
 */
const KEY_SPLIT_BASELINE: Record<string, string[]> = {
  '/assets': ['assets.title', 'nav.assets'],
  '/bim/federations': ['nav.bim_federations', 'nav.federations'],
  '/changeorders': ['nav.change_orders', 'nav.changeorders'],
  '/clash': ['clash.title', 'nav.clash'],
  '/closeout': ['closeout.title', 'nav.closeout'],
  '/projects/:projectId/bim': ['bim.title', 'nav.bim', 'nav.bim_viewer'],
  '/projects/:projectId/boq': ['boq.title', 'nav.boq'],
  '/projects/:projectId/contracts': [
    'contracts.title',
    'nav.contracts',
    'onboarding.mod_contracts',
  ],
  '/projects/:projectId/correspondence': ['correspondence.title', 'nav.correspondence'],
  '/projects/:projectId/daily-diary': ['nav.daily_diary', 'onboarding.mod_daily_diary'],
  '/projects/:projectId/finance': ['finance.title', 'nav.finance'],
  '/projects/:projectId/inspections': ['inspections.title', 'nav.inspections', 'nav.ncr'],
  '/projects/:projectId/ncr': ['nav.ncr', 'ncr.title'],
  '/projects/:projectId/procurement': ['nav.procurement', 'procurement.title'],
  '/projects/:projectId/safety': ['nav.safety', 'safety.title'],
  '/projects/:projectId/subcontractors': [
    'nav.subcontractors',
    'onboarding.mod_subcontractors',
    'subcontractors.title',
  ],
  '/projects/new': ['nav.projects', 'nav.projects_new'],
  '/quantities': ['nav.quantities', 'quantities.title'],
  '/reports': ['nav.reporting', 'nav.reports'],
  '/schedule': ['nav.schedule', 'schedule.title'],
  '/schedule-advanced': ['nav.schedule_advanced', 'onboarding.mod_schedule_advanced'],
  '/tendering': ['nav.tendering', 'tendering.title'],
  '/validation': ['nav.validation', 'validation.title'],
};

/**
 * Routes whose chips agree on the key and disagree on the spelling of the
 * label. Source-only, no locale effect. Same shrink rule.
 *
 * These seven are two different things and the list says which, because a shrink
 * list that carries deliberate choices as debt earns a "why is this still here"
 * from every reader forever. The first group is slips: same word, different
 * capital or different number. The second group is different NAMES for one
 * screen, which may well be somebody's considered wording, and settling those
 * is a call for the catalogue owner rather than a tidy-up.
 *
 * `/projects/:projectId/rfi` and `/catalog` left this list when every chip moved
 * onto the key the screen claims for itself, which settled the label with it.
 */
const LABEL_SPLIT_BASELINE: Record<string, string[]> = {
  // Slips: one name, two spellings.
  '/bid-management': ['Bid Management', 'Bid management'],
  '/projects/:projectId/field-time': ['Field Time', 'Field time'],
  '/punchlist': ['Punch List', 'Punch list'],

  // Different names for the same screen. Confirm the intent before collapsing.
  // `/labor-rates` is the interesting one: the split runs along US and UK
  // spelling, so it may be a market choice rather than an accident, and a
  // market choice does not belong on a chip that names a single screen.
  '/labor-rates': ['Labor Rates', 'Labour Rates'],
  '/projects/:projectId/hse-advanced': ['HSE Advanced', 'HSE Management'],
  '/projects/:projectId/qms': ['QMS', 'Quality', 'Quality management'],
  '/requirements/matrix': ['EIR Matrix', 'Requirements matrix'],
};

/** Resolve `frontend/src` whether vitest was started at `frontend/` or at the repo root. */
function findSrcRoot(): string {
  const root = [resolve(process.cwd(), 'src'), resolve(process.cwd(), 'frontend/src')].find((p) =>
    existsSync(join(p, 'app/App.tsx')),
  );
  expect(root, 'could not locate frontend/src from the test working directory').toBeTruthy();
  return root!;
}

/**
 * How many shipped locales render these keys as different words.
 *
 * Only ever called on the failure path. Reading forty-odd locale files costs
 * more than the rest of this suite put together, and a gate slow enough to
 * notice is a gate somebody deletes.
 *
 * A locale that is missing any of the keys is not counted either way: it cannot
 * disagree about a word it does not have, and counting it as agreement would
 * let an untranslated locale hide a real split.
 */
function localeDivergence(
  keys: string[],
  srcRoot: string,
): { diverged: string[]; checked: number } {
  const dir = join(srcRoot, 'app/locales');
  const diverged: string[] = [];
  let checked = 0;
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.ts') || file === 'index.ts') continue;
    const text = readFileSync(join(dir, file), 'utf8');
    const values = keys.map((k) => {
      const escaped = k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      return new RegExp(`"${escaped}":\\s*"((?:[^"\\\\]|\\\\.)*)"`).exec(text)?.[1];
    });
    if (values.some((v) => v === undefined)) continue;
    checked += 1;
    if (new Set(values).size > 1) diverged.push(file.replace(/\.ts$/, ''));
  }
  return { diverged, checked };
}

/** Group every shipped chip by the route it walks to. */
function chipsByRoute(): Map<string, Map<string, Set<string>>> {
  // route -> label -> keys, so both failure shapes fall out of one pass.
  const byRoute = new Map<string, Map<string, Set<string>>>();
  for (const pb of PLAYBOOKS) {
    for (const step of pb.steps) {
      if (!step.moduleLabelKey) continue;
      const labels = byRoute.get(step.to) ?? new Map<string, Set<string>>();
      const keys = labels.get(step.moduleLabel) ?? new Set<string>();
      keys.add(step.moduleLabelKey);
      labels.set(step.moduleLabel, keys);
      byRoute.set(step.to, labels);
    }
  }
  return byRoute;
}

const keysOn = (labels: Map<string, Set<string>>): string[] =>
  [...new Set([...labels.values()].flatMap((s) => [...s]))].sort();

const sameSet = (a: string[], b: string[]): boolean =>
  a.length === b.length && a.every((v, i) => v === b[i]);

describe('module chips name one route one way', () => {
  it('reads every case file the directory holds', () => {
    // The gate is only as wide as its input. Enumerate the directory rather
    // than trusting a list written by hand: a case file added tomorrow has to
    // be inside this check without anybody remembering to add it, and a file
    // that silently fails to register has to be visible as a shortfall rather
    // than as one fewer thing to check.
    const dir = join(findSrcRoot(), 'features/cases/data');
    const onDisk = readdirSync(dir).filter((f) => f.endsWith('.playbook.ts'));
    expect(onDisk.length, 'no case files found, the directory scan is broken').toBeGreaterThan(100);
    expect(
      PLAYBOOKS.length,
      `${onDisk.length} case files on disk but ${PLAYBOOKS.length} registered playbooks: ` +
        'a file is failing to load, and the checks below would pass by not looking at it',
    ).toBe(onDisk.length);
  });

  it('never sends two cases to the same screen under two different keys', () => {
    const srcRoot = findSrcRoot();
    const failures: string[] = [];

    for (const [route, labels] of chipsByRoute()) {
      const keys = keysOn(labels);
      const baseline = KEY_SPLIT_BASELINE[route];

      if (keys.length > 1) {
        if (baseline && sameSet(keys, baseline)) continue;
        const { diverged, checked } = localeDivergence(keys, srcRoot);
        const shown = diverged.slice(0, 8).join(', ');
        const more = diverged.length > 8 ? `, +${diverged.length - 8} more` : '';
        failures.push(
          `${route} is labelled with ${keys.length} different keys: ${keys.join(', ')}. ` +
            `They render different words in ${diverged.length} of ${checked} locales` +
            (diverged.length ? ` (${shown}${more})` : '') +
            '. Pick the key the sidebar puts on this route (navCatalog.ts) and move the ' +
            'others onto it.' +
            (baseline ? ` This route is baselined as [${baseline.join(', ')}]; a new variant appeared.` : ''),
        );
      } else if (baseline) {
        failures.push(
          `${route} now uses one key (${keys[0]}) but is still listed in KEY_SPLIT_BASELINE ` +
            `as [${baseline.join(', ')}]. The split is fixed: delete the entry. The baseline ` +
            'is a shrink list and stale entries make it read as permission.',
        );
      }
    }

    expect(failures, `\n  - ${failures.join('\n  - ')}\n`).toEqual([]);
  });

  it('spells one screen name one way', () => {
    // Label-only disagreement, split out from the check above because it has no
    // effect on any locale: the label is the fallback shown when the key has no
    // translation. Still wrong, still worth one line, not worth alarm.
    const failures: string[] = [];

    for (const [route, labels] of chipsByRoute()) {
      if (keysOn(labels).length > 1) continue; // already reported as a key split
      const spellings = [...labels.keys()].sort();
      const baseline = LABEL_SPLIT_BASELINE[route];

      if (spellings.length > 1) {
        if (baseline && sameSet(spellings, baseline)) continue;
        failures.push(
          `${route} is written as ${spellings.map((s) => `"${s}"`).join(' and ')}. ` +
            'No locale is affected, the key is shared. Settle on one spelling.' +
            (baseline ? ` Baselined as [${baseline.join(', ')}]; a new spelling appeared.` : ''),
        );
      } else if (baseline) {
        failures.push(
          `${route} now has one spelling ("${spellings[0]}") but is still listed in ` +
            'LABEL_SPLIT_BASELINE. Delete the entry.',
        );
      }
    }

    expect(failures, `\n  - ${failures.join('\n  - ')}\n`).toEqual([]);
  });

  it('keeps both baselines pointed at routes that still exist', () => {
    // A baseline entry for a route no chip walks to any more is dead weight
    // that makes the list look larger than the debt it records.
    const live = new Set(chipsByRoute().keys());
    const dead = [...Object.keys(KEY_SPLIT_BASELINE), ...Object.keys(LABEL_SPLIT_BASELINE)].filter(
      (r) => !live.has(r),
    );
    expect(dead, `baselined routes no chip uses any more: ${dead.join(', ')}`).toEqual([]);
  });
});
