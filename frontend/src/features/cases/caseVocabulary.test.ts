// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The closed vocabularies a case declares about itself.
//
// A playbook names a category, a set of company types, an optional set of
// professional roles and an optional market. The first two were already gated
// next to the rest of the shipped-content checks; these two were not, and both
// fail the same quiet way: the value is a runtime STRING resolved through a
// lookup that falls back rather than throws, so a wrong one is not a build
// error and not a runtime error. The card simply renders something nobody
// meant, and it renders it in production.
//
// These live in their own file rather than inside `cases.test.ts` for a reason
// worth writing down. Both were added there first, and while they sat
// uncommitted another session held that same file open with its own version.
// A save from that buffer would have taken both gates silently: nothing would
// have failed, the suite would have stayed green, and the file is named in
// `FRONTEND_TEST_FILES` where it reads as coverage. A sibling file removes the
// overlap instead of asking two sessions to be careful in the same file.

import { describe, it, expect } from 'vitest';
import { PLAYBOOKS } from './playbooks';
import { ROLE_META } from './roles';

const VALID_ROLES = new Set(ROLE_META.map((r) => r.id));

describe('the vocabularies a case declares about itself', () => {
  it('every role a case names is a role that exists', () => {
    // `roles` is a closed vocabulary exactly like `companyTypes`, but only the
    // latter was gated, so an invented role reached a green suite and was
    // caught by tsc alone - on a branch where the typecheck is a separate lane
    // and the "CI" job is chronically red for unrelated reasons. `roles` is
    // optional, so absence is fine; a name that is not in ROLE_META is not.
    for (const pb of PLAYBOOKS) {
      if (!pb.roles) continue;
      for (const id of pb.roles) {
        expect(VALID_ROLES.has(id), `unknown role "${id}" on "${pb.id}"`).toBe(true);
      }
    }
  });

  it('every market-specific case names a market Intl can actually name', () => {
    // `regionDisplayName` falls back to the raw code when Intl cannot resolve
    // it, so a typo ("USA", "us", "United States") is not a build error and not
    // a runtime error - the card just shows a chip reading the typo, and the
    // case quietly forms a market group of its own that no other case can join.
    // Two things have to hold: the shape the type documents (ISO 3166-1
    // alpha-2), and that Intl resolves it to a name rather than echoing it.
    let intlNames: Intl.DisplayNames | null = null;
    try {
      intlNames = new Intl.DisplayNames(['en'], { type: 'region' });
    } catch {
      intlNames = null; // older engine: shape is still assertable
    }
    for (const pb of PLAYBOOKS) {
      if (!pb.region) continue;
      expect(/^[A-Z]{2}$/.test(pb.region), `case "${pb.id}" has region "${pb.region}"`).toBe(true);
      if (!intlNames) continue;
      // A well-formed code Intl does not know comes back as "Unknown Region"
      // rather than as the code, so echoing is not the only failure shape.
      const named = intlNames.of(pb.region);
      expect(
        named !== pb.region && !/unknown/i.test(named ?? ''),
        `case "${pb.id}" names region "${pb.region}", which Intl resolves to "${named}"`,
      ).toBe(true);
    }
  });

  it('looks at the whole catalogue rather than at nothing', () => {
    // Both assertions above are loops over PLAYBOOKS with a `continue` for the
    // absent case, so an empty or half-loaded catalogue passes them silently.
    // The count is the only thing standing between "checked everything" and
    // "checked nothing", and it has to be asserted rather than assumed.
    expect(PLAYBOOKS.length).toBeGreaterThan(100);
    expect(PLAYBOOKS.some((p) => p.roles?.length)).toBe(true);
    expect(PLAYBOOKS.some((p) => p.region)).toBe(true);
  });
});
