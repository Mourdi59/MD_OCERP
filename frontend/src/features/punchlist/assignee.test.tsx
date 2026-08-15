// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The punch list printed `assigned_to` as it stood, and that column holds a
// contact id as often as a name, so a row read "Assigned To 3f2b8c1e-9a44-..."
// with an avatar lettered from a hex digit. The API now sends the resolved
// name beside the raw value; what is pinned here is which of the two gets
// painted, including the case nobody thinks about - an id that resolved to
// nothing, which is an owned snag whose owner we cannot name and must not be
// reported as unassigned.
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AssigneeLabel, resolveAssignee } from './assignee';

const ID = '3f2b8c1e-9a44-4d2e-8b7a-0c1d2e3f4a5b';

describe('resolveAssignee', () => {
  it('prefers the name the API resolved', () => {
    expect(resolveAssignee(ID, 'Bauunternehmung Keller')).toEqual({
      kind: 'named',
      name: 'Bauunternehmung Keller',
    });
  });

  it('keeps free text that somebody typed', () => {
    expect(resolveAssignee('Anna Schmidt', null)).toEqual({ kind: 'named', name: 'Anna Schmidt' });
  });

  it('reports an unresolved id as unresolved, not as unassigned', () => {
    expect(resolveAssignee(ID, null)).toEqual({ kind: 'unresolved' });
    expect(resolveAssignee(ID.toUpperCase(), '   ')).toEqual({ kind: 'unresolved' });
  });

  it('reports an empty column as nobody', () => {
    expect(resolveAssignee(null, null)).toEqual({ kind: 'none' });
    expect(resolveAssignee('   ', undefined)).toEqual({ kind: 'none' });
  });

  it('does not mistake other identifiers for ids', () => {
    // An email address, a payroll number and a short code are all things
    // people type into this field, and all of them are readable as they are.
    expect(resolveAssignee('a.schmidt@keller.example', null)).toEqual({
      kind: 'named',
      name: 'a.schmidt@keller.example',
    });
    expect(resolveAssignee('SM-014', null)).toEqual({ kind: 'named', name: 'SM-014' });
  });
});

describe('AssigneeLabel', () => {
  it('paints the resolved name and never the id behind it', () => {
    render(<AssigneeLabel raw={ID} name="Bauunternehmung Keller" variant="row" />);
    expect(screen.getByText('Bauunternehmung Keller')).toBeTruthy();
    expect(screen.queryByText(new RegExp(ID.slice(0, 8), 'i'))).toBeNull();
    // The avatar takes its letter from the name, not from a hex digit.
    expect(screen.getByText('B')).toBeTruthy();
  });

  it('says unassigned only when nobody is named', () => {
    render(<AssigneeLabel raw={null} name={null} variant="card" />);
    expect(screen.getByText('Unassigned')).toBeTruthy();
  });

  it('says unknown when an id names a contact that is gone', () => {
    render(<AssigneeLabel raw={ID} name={null} variant="card" />);
    expect(screen.getByText('Unknown')).toBeTruthy();
    expect(screen.queryByText('Unassigned')).toBeNull();
  });

  it('drops the avatar in the drawer, which already labels the field', () => {
    const { container } = render(<AssigneeLabel raw="Anna Schmidt" variant="plain" />);
    expect(container.textContent).toBe('Anna Schmidt');
  });
});
