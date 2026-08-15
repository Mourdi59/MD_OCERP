// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// "Past due date" is a chase list, so it must not count snags that are already
// closed, and "days on the list" must stop at the day a snag was resolved
// rather than growing forever after the fact.
import { describe, it, expect } from 'vitest';
import { buildPunchlistInsights } from './punchlistInsights';
import type { PunchItem } from './api';

/** Mirrors i18next's defaultValue behaviour without pulling in the runtime. */
const t = ((key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key) as never;

const DAY = 24 * 60 * 60 * 1000;
const daysAgo = (n: number) => new Date(Date.now() - n * DAY).toISOString();

function punch(over: Partial<PunchItem>): PunchItem {
  return {
    id: 'p1',
    project_id: 'pr1',
    title: 'Riser duct penetration unsealed',
    description: '',
    priority: 'high',
    status: 'open',
    category: 'fire_safety',
    assigned_to: 'Site manager',
    due_date: daysAgo(5),
    trade: 'Fire stopping',
    photos: [],
    metadata: {},
    created_at: daysAgo(20),
    updated_at: daysAgo(1),
    resolved_at: null,
    verified_at: null,
    ...over,
  } as PunchItem;
}

function row(p: PunchItem) {
  return buildPunchlistInsights([p], t).datasets[0]?.rows[0];
}

describe('buildPunchlistInsights', () => {
  it('counts an open snag past its due date as overdue', () => {
    const r = row(punch({ status: 'open', due_date: daysAgo(5) }));
    expect(r?.overdue).toBe(1);
    expect(r?.open).toBe(1);
  });

  it('does not chase a closed snag whose due date has passed', () => {
    const r = row(punch({ status: 'closed', due_date: daysAgo(30), resolved_at: daysAgo(25) }));
    expect(r?.overdue).toBe(0);
    expect(r?.open).toBe(0);
  });

  it('does not call an open snag overdue before its date', () => {
    const r = row(punch({ due_date: new Date(Date.now() + 5 * DAY).toISOString() }));
    expect(r?.overdue).toBe(0);
  });

  it('treats a snag with no due date as not overdue rather than infinitely late', () => {
    expect(row(punch({ due_date: null }))?.overdue).toBe(0);
  });

  it('stops the age clock at resolution so turnaround is preserved', () => {
    const r = row(punch({ status: 'resolved', created_at: daysAgo(30), resolved_at: daysAgo(24) }));
    expect(r?.age).toBe(6);
  });

  it('keeps an open snag ageing', () => {
    expect(row(punch({ created_at: daysAgo(20) }))?.age).toBe(20);
  });

  it('draws nothing at all on an empty list', () => {
    expect(buildPunchlistInsights([], t).datasets[0]?.rows).toHaveLength(0);
    expect(buildPunchlistInsights([punch({})], t).datasets[0]?.rows).toHaveLength(1);
  });

  // The assignee column holds a contact id as often as a name, and an id makes
  // a bar nobody can read. Grouping is the one place where the three states
  // have to stay apart: work owned by a named party, work owned by somebody
  // the register can no longer name, and work owned by nobody.
  it('groups by the resolved name rather than the id behind it', () => {
    const r = row(
      punch({ assigned_to: '3f2b8c1e-9a44-4d2e-8b7a-0c1d2e3f4a5b', assigned_to_name: 'Keller' }),
    );
    expect(r?.assignee).toBe('Keller');
  });

  it('keeps an unresolvable owner out of the unassigned bucket', () => {
    const r = row(punch({ assigned_to: '3f2b8c1e-9a44-4d2e-8b7a-0c1d2e3f4a5b' }));
    expect(r?.assignee).toBe('Unknown');
    expect(row(punch({ assigned_to: null }))?.assignee).toBe('Unassigned');
  });

  it('exposes no currency-formatted measure, because a snag carries no money', () => {
    const ds = buildPunchlistInsights([], t).datasets[0];
    expect(ds?.currency).toBe('');
    expect(ds?.fields.some((f) => f.format === 'currency')).toBe(false);
  });
});
