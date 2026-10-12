// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, expect, it } from 'vitest';

import type { NeighbourIssue } from '../site-logistics/api';
import { isOverdue, mapEach, mapNeighbourIssue } from './issueSources';

function issue(overrides: Partial<NeighbourIssue> = {}): NeighbourIssue {
  return {
    id: 'n1',
    kind: 'noise',
    reported_on: '2026-10-05',
    reporter: '',
    location: null,
    description: 'Concrete pump running before 07:00\nsecond line',
    transport_id: null,
    delivery_id: null,
    owner_user_id: 'u-site-manager',
    response: '',
    response_due: '2026-10-10',
    state: 'received',
    overdue: true,
    created_at: '2026-10-05T08:00:00Z',
    ...overrides,
  };
}

describe('mapNeighbourIssue', () => {
  it('maps an open complaint with its owner and response date', () => {
    const mapped = mapNeighbourIssue(issue());
    expect(mapped).toMatchObject({
      id: 'neighbour:n1',
      rawId: 'n1',
      source: 'neighbour',
      title: 'Concrete pump running before 07:00',
      status: 'open',
      rawStatus: 'received',
      assignee: 'u-site-manager',
      dueDate: '2026-10-10',
      createdAt: '2026-10-05T08:00:00Z',
    });
    expect(mapped?.deepLink).toBe('/site-logistics?neighbourIssue=n1');
  });

  it('buckets the lifecycle and drops closed complaints', () => {
    expect(mapNeighbourIssue(issue({ state: 'acknowledged' }))?.status).toBe('in_progress');
    expect(mapNeighbourIssue(issue({ state: 'action_taken' }))?.status).toBe('resolved');
    expect(mapNeighbourIssue(issue({ state: 'closed' }))).toBeNull();
    expect(mapNeighbourIssue(issue({ state: 'unknown_state' }))).toBeNull();
  });

  it('falls back to the complaint kind when there is no description', () => {
    expect(mapNeighbourIssue(issue({ description: '  ' }))?.title).toBe('Neighbour complaint: noise');
  });

  it('marks priority high only while the response is overdue', () => {
    expect(mapNeighbourIssue(issue())?.priority).toBe('high');
    expect(mapNeighbourIssue(issue({ overdue: false }))?.priority).toBe('medium');
  });

  it('is overdue in the hub by its response date, not acknowledged once answered', () => {
    const now = new Date('2026-10-12T12:00:00');
    expect(isOverdue(mapNeighbourIssue(issue())!, now)).toBe(true);
    // An acknowledged complaint has been answered; the response date no longer binds.
    expect(mapNeighbourIssue(issue({ state: 'acknowledged' }))?.dueDate).toBeNull();
  });

  it('survives a malformed row without taking the rest down', () => {
    const rows = [issue(), null as unknown as NeighbourIssue, issue({ id: 'n2' })];
    expect(mapEach(rows, mapNeighbourIssue).map((i) => i.rawId)).toEqual(['n1', 'n2']);
  });
});
