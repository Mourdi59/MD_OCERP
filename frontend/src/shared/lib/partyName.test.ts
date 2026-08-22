// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * The three states a person column can be in, and why none of them collapse.
 *
 * The punch list already holds these cases against its own screen. They live
 * here as well because the rule now serves change orders, the plan-room
 * overlay and the markup hub too, and a rule written once per caller is only
 * ever tested at the caller that was already right.
 */
import { describe, it, expect } from 'vitest';
import { resolvePartyName } from './partyName';

const ID = '3f2b8c1e-9a44-4c7e-9a1f-2f2d6a8b0c31';

describe('resolvePartyName', () => {
  it('prefers the name the API resolved', () => {
    expect(resolvePartyName(ID, 'Bauunternehmung Keller')).toEqual({
      kind: 'named',
      name: 'Bauunternehmung Keller',
    });
  });

  it('keeps a typed-in name as it stands', () => {
    // Nobody looked this up and nobody needs to: what was typed is the answer.
    expect(resolvePartyName('Anna Schmidt')).toEqual({ kind: 'named', name: 'Anna Schmidt' });
    expect(resolvePartyName('a.schmidt@example.com')).toEqual({
      kind: 'named',
      name: 'a.schmidt@example.com',
    });
  });

  it('calls an unresolved id unresolved, never nobody', () => {
    // This is the whole point. The record has an owner we cannot name, and
    // reporting it as unassigned invites a second assignment.
    expect(resolvePartyName(ID)).toEqual({ kind: 'unresolved' });
    expect(resolvePartyName(ID, '')).toEqual({ kind: 'unresolved' });
    expect(resolvePartyName(ID, '   ')).toEqual({ kind: 'unresolved' });
  });

  it('reports an empty column as nobody', () => {
    expect(resolvePartyName(null)).toEqual({ kind: 'none' });
    expect(resolvePartyName(undefined)).toEqual({ kind: 'none' });
    expect(resolvePartyName('')).toEqual({ kind: 'none' });
    expect(resolvePartyName('   ')).toEqual({ kind: 'none' });
  });

  it('reads an id in either case', () => {
    // Postgres hands ids back lower-case, but a value that arrived through an
    // integration or a hand edit can be upper-case and is the same id.
    expect(resolvePartyName(ID.toUpperCase())).toEqual({ kind: 'unresolved' });
  });

  it('never returns an id as though it were a name', () => {
    for (const value of [ID, ID.toUpperCase(), ` ${ID} `]) {
      const party = resolvePartyName(value);
      expect(party.kind).not.toBe('none');
      expect(party).not.toHaveProperty('name');
    }
  });

  it('trims a resolved name rather than printing its padding', () => {
    expect(resolvePartyName(ID, '  Tom Fischer  ')).toEqual({ kind: 'named', name: 'Tom Fischer' });
  });
});
