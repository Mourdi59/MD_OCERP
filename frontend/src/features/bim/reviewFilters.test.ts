// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';

import type { Topic } from '@/features/bcf/api';

import {
  EMPTY_REVIEW_FILTER,
  UNASSIGNED,
  buildReviewAgenda,
  collectReviewLabels,
  countReviewTopics,
  filterReviewTopics,
  isFilterActive,
  priorityRank,
  sortReviewTopics,
  type ReviewFilter,
} from './reviewFilters';

const NOW = Date.parse('2026-08-20T12:00:00Z');

function topic(over: Partial<Topic> & { guid: string }): Topic {
  return {
    project_id: 'p1',
    bim_model_id: null,
    title: 'Issue',
    description: null,
    topic_type: null,
    topic_status: 'Open',
    priority: null,
    stage: null,
    index: null,
    assigned_to: null,
    due_date: null,
    labels: [],
    reference_links: [],
    creation_author: null,
    creation_date: '2026-08-01T00:00:00Z',
    modified_author: null,
    modified_date: null,
    comments: [],
    viewpoints: [],
    ...over,
  };
}

const filter = (over: Partial<ReviewFilter> = {}): ReviewFilter => ({
  ...EMPTY_REVIEW_FILTER,
  ...over,
});

/** A small register spanning both models, both states and two assignees. */
const REGISTER: Topic[] = [
  topic({
    guid: 'a',
    title: 'Duct clashes with beam',
    bim_model_id: 'm1',
    priority: 'Critical',
    assigned_to: 'u1',
    due_date: '2026-08-10T00:00:00Z',
    labels: ['MEP'],
    creation_date: '2026-08-05T00:00:00Z',
  }),
  topic({
    guid: 'b',
    title: 'Door swing blocked',
    bim_model_id: 'm2',
    priority: 'Normal',
    due_date: '2026-09-01T00:00:00Z',
    creation_date: '2026-08-12T00:00:00Z',
  }),
  topic({
    guid: 'c',
    title: 'Handrail height',
    bim_model_id: 'm1',
    topic_status: 'Closed',
    priority: 'Low',
    assigned_to: 'u2',
    creation_date: '2026-08-02T00:00:00Z',
  }),
  topic({
    guid: 'd',
    title: 'Imported from the consultant',
    priority: 'Major',
    assigned_to: 'u1',
    due_date: '2026-08-18T00:00:00Z',
    labels: ['Structure', 'imported'],
    creation_date: '2026-08-15T00:00:00Z',
  }),
];

const guids = (list: Topic[]): string[] => list.map((t) => t.guid);

describe('filterReviewTopics', () => {
  it('returns everything under the neutral filter', () => {
    expect(guids(filterReviewTopics(REGISTER, EMPTY_REVIEW_FILTER, 'm1', NOW))).toEqual([
      'a',
      'b',
      'c',
      'd',
    ]);
  });

  it('scopes to the active model only when asked, and never silently', () => {
    const scoped = filterReviewTopics(REGISTER, filter({ scope: 'model' }), 'm1', NOW);
    expect(guids(scoped)).toEqual(['a', 'c']);
    // An issue raised outside any model is NOT part of a model scope.
    expect(guids(scoped)).not.toContain('d');
  });

  it('yields nothing for model scope with no model selected', () => {
    expect(filterReviewTopics(REGISTER, filter({ scope: 'model' }), null, NOW)).toEqual([]);
  });

  it('keeps only open issues', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ onlyOpen: true }), 'm1', NOW))).toEqual([
      'a',
      'b',
      'd',
    ]);
  });

  it('keeps only overdue open issues, measured against the injected clock', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ onlyOverdue: true }), 'm1', NOW))).toEqual([
      'a',
      'd',
    ]);
    // Two days earlier, "d" is not late yet.
    const earlier = Date.parse('2026-08-17T12:00:00Z');
    expect(guids(filterReviewTopics(REGISTER, filter({ onlyOverdue: true }), 'm1', earlier))).toEqual(
      ['a'],
    );
  });

  it('filters by assignee, and by nobody', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ assignee: 'u1' }), 'm1', NOW))).toEqual([
      'a',
      'd',
    ]);
    expect(guids(filterReviewTopics(REGISTER, filter({ assignee: UNASSIGNED }), 'm1', NOW))).toEqual([
      'b',
    ]);
  });

  it('filters by status and priority exactly', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ status: 'Closed' }), 'm1', NOW))).toEqual([
      'c',
    ]);
    expect(guids(filterReviewTopics(REGISTER, filter({ priority: 'Normal' }), 'm1', NOW))).toEqual([
      'b',
    ]);
  });

  it('searches title, labels and assignee, case-insensitively', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ search: 'DUCT' }), 'm1', NOW))).toEqual(['a']);
    expect(guids(filterReviewTopics(REGISTER, filter({ search: 'structure' }), 'm1', NOW))).toEqual([
      'd',
    ]);
    expect(guids(filterReviewTopics(REGISTER, filter({ search: 'u2' }), 'm1', NOW))).toEqual(['c']);
  });

  it('narrows to one discipline by exact label, not by substring', () => {
    expect(guids(filterReviewTopics(REGISTER, filter({ label: 'MEP' }), 'm1', NOW))).toEqual(['a']);
    expect(guids(filterReviewTopics(REGISTER, filter({ label: 'Structure' }), 'm1', NOW))).toEqual([
      'd',
    ]);
    // 'Struct' is a prefix of a real label and must still match nothing:
    // an exact-match control cannot quietly behave like the search box.
    expect(guids(filterReviewTopics(REGISTER, filter({ label: 'Struct' }), 'm1', NOW))).toEqual([]);
  });

  it('keeps a topic that carries the label among several', () => {
    // 'd' is labelled ['Structure', 'imported'] - the second label counts too.
    expect(guids(filterReviewTopics(REGISTER, filter({ label: 'imported' }), 'm1', NOW))).toEqual([
      'd',
    ]);
  });

  it('combines predicates instead of letting the last one win', () => {
    const combined = filterReviewTopics(
      REGISTER,
      filter({ scope: 'model', onlyOpen: true, assignee: 'u1' }),
      'm1',
      NOW,
    );
    expect(guids(combined)).toEqual(['a']);
  });
});

describe('isFilterActive', () => {
  it('is false for the neutral filter and true for any narrowing', () => {
    expect(isFilterActive(EMPTY_REVIEW_FILTER)).toBe(false);
    expect(isFilterActive(filter({ search: '  ' }))).toBe(false);
    expect(isFilterActive(filter({ onlyOverdue: true }))).toBe(true);
    expect(isFilterActive(filter({ scope: 'model' }))).toBe(true);
    expect(isFilterActive(filter({ label: 'MEP' }))).toBe(true);
  });
});

describe('collectReviewLabels', () => {
  it('offers each label once, sorted, from the loaded list only', () => {
    expect(collectReviewLabels(REGISTER)).toEqual(['imported', 'MEP', 'Structure']);
  });

  it('drops blank labels rather than offering an unselectable option', () => {
    const noisy = [
      topic({ guid: 'a', labels: ['  MEP  ', '', '   '] }),
      topic({ guid: 'b', labels: ['MEP'] }),
    ];
    expect(collectReviewLabels(noisy)).toEqual(['MEP']);
  });

  it('is empty when nothing is labelled', () => {
    expect(collectReviewLabels([topic({ guid: 'a', labels: [] })])).toEqual([]);
  });
});

describe('sortReviewTopics', () => {
  it('puts the most urgent first, whichever vocabulary named it', () => {
    expect(guids(sortReviewTopics(REGISTER, 'priority'))).toEqual(['a', 'd', 'b', 'c']);
  });

  it('puts the earliest deadline first and undated issues last', () => {
    expect(guids(sortReviewTopics(REGISTER, 'due'))).toEqual(['a', 'd', 'b', 'c']);
  });

  it('defaults to newest first', () => {
    expect(guids(sortReviewTopics(REGISTER, 'newest'))).toEqual(['d', 'b', 'a', 'c']);
  });

  it('does not mutate its input', () => {
    const before = guids(REGISTER);
    sortReviewTopics(REGISTER, 'due');
    expect(guids(REGISTER)).toEqual(before);
  });
});

describe('priorityRank', () => {
  it('ranks the clash engine and the picker on the same scale', () => {
    expect(priorityRank('Critical')).toBeLessThan(priorityRank('Major'));
    expect(priorityRank('Major')).toBe(priorityRank('High'));
    expect(priorityRank('Minor')).toBe(priorityRank('Low'));
    expect(priorityRank('Normal')).toBeLessThan(priorityRank('Low'));
    expect(priorityRank(null)).toBeGreaterThan(priorityRank('Low'));
    // An unrecognised value still sorts before "no priority at all".
    expect(priorityRank('Showstopper')).toBeLessThan(priorityRank(''));
  });
});

describe('countReviewTopics', () => {
  it('counts open, overdue, unassigned and per-model without double counting closed', () => {
    expect(countReviewTopics(REGISTER, 'm1', NOW)).toEqual({
      total: 4,
      open: 3,
      overdue: 2,
      unassignedOpen: 1,
      openOnModel: 1,
    });
  });

  it('reports no model issues when no model is selected', () => {
    expect(countReviewTopics(REGISTER, null, NOW).openOnModel).toBe(0);
  });
});

describe('buildReviewAgenda', () => {
  it('walks exactly what is visible, minus what is already closed', () => {
    const visible = filterReviewTopics(REGISTER, filter({ scope: 'model' }), 'm1', NOW);
    expect(guids(buildReviewAgenda(visible))).toEqual(['a']);
  });

  it('preserves the order the reader chose', () => {
    const visible = sortReviewTopics(REGISTER, 'priority');
    expect(guids(buildReviewAgenda(visible))).toEqual(['a', 'd', 'b']);
  });
});
