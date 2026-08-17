// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The professional-role vocabulary is written out by hand in three places, and
// only one of them is checked by the compiler. `ROLE_META` (roles.ts) is the
// selector; `ROLE_SET` (api.ts) is a `Record` over the `ProfessionalRole`
// union, so tsc does enforce that one; `VALID_ROLES` (useCasesStore.ts) is a
// plain array, so a subset of it type-checks happily.
//
// That last one is the dangerous shape. A role added to the selector but not
// to `VALID_ROLES` compiles, renders, and lets the user pick it - and then the
// pick is filtered out when it is read back from localStorage, so the choice
// disappears on the next reload with nothing red anywhere.

import { describe, it, expect } from 'vitest';
import { ROLE_META } from './roles';
import { VALID_ROLES } from './useCasesStore';

describe('professional role vocabulary', () => {
  const selector = new Set<string>(ROLE_META.map((r) => r.id));
  const persistable = new Set<string>(VALID_ROLES);

  it('every role in the selector can be persisted', () => {
    for (const r of ROLE_META) {
      expect(persistable.has(r.id), `"${r.id}" is in ROLE_META but not in VALID_ROLES`).toBe(true);
    }
  });

  it('every persistable role is still in the selector', () => {
    // The other direction, so removing a role does not leave a dead id behind
    // that a stale localStorage entry can keep alive.
    for (const id of VALID_ROLES) {
      expect(selector.has(id), `"${id}" is in VALID_ROLES but not in ROLE_META`).toBe(true);
    }
  });

  it('no two roles share a label or an id', () => {
    // Two roles reading the same in the picker is indistinguishable from a
    // duplicate entry to the person choosing.
    expect(selector.size).toBe(ROLE_META.length);
    const labels = ROLE_META.map((r) => r.labelDefault);
    expect(new Set(labels).size, `duplicate label among ${labels.join(', ')}`).toBe(labels.length);
  });

  it('every role carries the full tint block and its own avatar colour', () => {
    // Tailwind's JIT only keeps class names that appear whole in the source, so
    // an empty or built-up token here silently renders an unstyled control.
    for (const r of ROLE_META) {
      for (const [slot, value] of Object.entries(r.tint)) {
        expect(value.trim().length, `${r.id} has an empty tint.${slot}`).toBeGreaterThan(0);
      }
      expect(r.avatarText.trim().length, `${r.id} has no avatarText`).toBeGreaterThan(0);
      expect(r.categories.length, `${r.id} runs no case discipline`).toBeGreaterThan(0);
      expect(r.labelKey, `${r.id} has a labelKey that does not match its id`).toBe(
        `cases.role.${r.id.replace(/-/g, '_')}`,
      );
    }
  });
});
