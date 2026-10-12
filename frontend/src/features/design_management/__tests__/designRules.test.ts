// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plain logic of the design screens: the step tables, the work breakdown
// as a tree, what a draft lacks, request bodies, and how codes get a name.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { designErrorCode, designErrorMessage, designViolations } from '../api';
import { refusalText } from '../hooks';
import {
  PARTY_KIND,
  PERMIT_STATE,
  catalogueLabel,
  errorText,
  humanizeCode,
  phaseName,
  ui,
  uiCount,
  vocab,
  vocabOptions,
} from '../labels';
import {
  COMMENT_NEXT,
  PERMIT_NEXT,
  RELEASE_NEXT,
  REPORT_NEXT,
  REVIEW_NEXT,
  changedFields,
  commentMoveNeedsAnswer,
  compareCodes,
  deliverableProblems,
  deliverableProgress,
  filledFields,
  recipientName,
  releasable,
  reportMoveNeedsReason,
  roleStateChoices,
  typedFields,
  wbsRows,
  wholeNumber,
} from '../rules';
import { UI } from '../text';
import { enT } from './i18nMock';
import { deliverable, drawing, labels, role, scheme, setup, wbsNode } from './fixtures';

describe('step tables', () => {
  it('offers no step out of a final state', () => {
    expect(RELEASE_NEXT.issued).toEqual([]);
    expect(RELEASE_NEXT.cancelled).toEqual([]);
    expect(REVIEW_NEXT.concluded).toEqual([]);
    expect(COMMENT_NEXT.closed).toEqual([]);
    expect(REPORT_NEXT.accepted).toEqual([]);
    expect(PERMIT_NEXT.approved).toEqual([]);
  });

  it('keeps issuing and concluding out of the one-click steps, because each has its own dialog', () => {
    expect(Object.values(RELEASE_NEXT).flat()).not.toContain('issued');
    expect(Object.values(REVIEW_NEXT).flat()).not.toContain('concluded');
  });

  it('leaves a submitted permit only the step a person takes', () => {
    expect(PERMIT_NEXT.submitted).toEqual(['withdrawn']);
    expect(PERMIT_NEXT.under_review).toEqual(['withdrawn']);
  });

  it('a role form offers the current state first and then where it can go', () => {
    expect(roleStateChoices('planned')).toEqual(['planned', 'appointed', 'active']);
    expect(roleStateChoices('released')).toEqual(['released']);
  });

  it('knows which steps need words', () => {
    expect(reportMoveNeedsReason('not_required')).toBe(true);
    expect(reportMoveNeedsReason('accepted')).toBe(false);
    expect(commentMoveNeedsAnswer('answered')).toBe(true);
    expect(commentMoveNeedsAnswer('closed')).toBe(false);
  });
});

describe('work breakdown', () => {
  it('compares codes part by part', () => {
    expect(compareCodes('1.9', '1.10')).toBeLessThan(0);
    expect(compareCodes('1.10', '1.2')).toBeGreaterThan(0);
    expect(compareCodes('1', '1.1')).toBeLessThan(0);
    expect(compareCodes('A.2', 'A.2')).toBe(0);
  });

  it('lists parents before children and adds up the references', () => {
    const rows = wbsRows([
      wbsNode({ id: 'c', parent_id: 'a', code: '1.10', level: 2 }),
      wbsNode({ id: 'b', parent_id: 'a', code: '1.2', level: 2, references: { costs: 2, schedule: 3 } }),
      wbsNode({ id: 'a', code: '1' }),
    ]);
    expect(rows.map((r) => [r.node.code, r.depth])).toEqual([
      ['1', 0],
      ['1.2', 1],
      ['1.10', 1],
    ]);
    expect(rows[1]!.referenceCount).toBe(5);
  });

  it('keeps a node whose parent the API did not send', () => {
    const rows = wbsRows([wbsNode({ id: 'x', parent_id: 'gone', code: '7.1' })]);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.depth).toBe(0);
  });
});

describe('schedule lines and drawings', () => {
  it('counts the drawings of a line against its plan', () => {
    const line = deliverable({ id: 'd1', planned_count: 3 });
    expect(deliverableProgress(line, [drawing(), drawing({ id: 'dr2', deliverable_id: 'other' })])).toEqual({ linked: 1, planned: 3 });
  });

  it('names what a draft line still lacks', () => {
    const draft = { title: ' ', phase_code: '', planned_count: 1, planned_count_rationale: '', waived: true, waived_rationale: '' };
    expect(deliverableProblems(draft, { planned_count: 3 })).toEqual(['title_required', 'phase_required', 'waiver_reason', 'count_reason']);
    expect(
      deliverableProblems({ ...draft, title: 'Plans', phase_code: 'permit', waived: false, planned_count_rationale: 'Two sheets merged' }, { planned_count: 3 }),
    ).toEqual([]);
  });

  it('asks for no reason when the planned number grows or the line is new', () => {
    const draft = { title: 'Plans', phase_code: 'permit', planned_count: 5, planned_count_rationale: '', waived: false, waived_rationale: '' };
    expect(deliverableProblems(draft, { planned_count: 3 })).toEqual([]);
    expect(deliverableProblems({ ...draft, planned_count: 0 })).toEqual([]);
  });

  it('releases only a drawing that has a revision and is not superseded', () => {
    const list = [
      drawing({ id: 'a' }),
      drawing({ id: 'b', current_revision_id: null }),
      drawing({ id: 'c', superseded_by_container_id: 'c9' }),
    ];
    expect(releasable(list).map((d) => d.id)).toEqual(['a']);
  });

  it('asks a person only for the typed parts of a number', () => {
    expect(typedFields(scheme()).map((f) => f.code)).toEqual(['discipline']);
  });

  it('names a recipient key by its role and admits when it cannot', () => {
    expect(recipientName('role:r1', [role()])).toBe('Architect');
    expect(recipientName('role:r1', [role({ title: '' })])).toBe('R-01');
    expect(recipientName('list:l1', [role()])).toBeNull();
    expect(recipientName('role:unknown', [role()])).toBeNull();
  });
});

describe('request bodies', () => {
  it('a PATCH carries only what changed, and an emptied optional field as null', () => {
    const before = { title: 'Architect', originator_code: 'ARC', lines: ['a', 'b'], required: true };
    const after = { title: 'Architect', originator_code: '', lines: ['a', 'b'], required: false };
    expect(changedFields(before, after, ['originator_code'])).toEqual({ originator_code: null, required: false });
  });

  it('a PATCH keeps an emptied text field as empty text when null is not allowed', () => {
    expect(changedFields({ note: 'x' }, { note: '' })).toEqual({ note: '' });
  });

  it('a POST leaves out what was not filled in', () => {
    expect(filledFields({ title: 'Architect', code: '', lines: [], required: false })).toEqual({ title: 'Architect', required: false });
  });

  it('reads a whole number or nothing', () => {
    expect(wholeNumber(' 12 ')).toBe(12);
    expect(wholeNumber('1.5')).toBeNull();
    expect(wholeNumber('')).toBeNull();
    expect(wholeNumber('-1')).toBeNull();
  });
});

describe('labels', () => {
  it('renders a vocabulary entry and humanises an unknown code instead of showing a key', () => {
    expect(vocab(enT, PARTY_KIND, 'checker')).toBe('Independent checker');
    expect(vocab(enT, PARTY_KIND, 'site_agent' as never)).toBe('Site agent');
    expect(vocab(enT, PARTY_KIND, null)).toBe('');
    expect(vocabOptions(enT, PERMIT_STATE)[0]).toEqual({ value: 'assembling', label: 'Being assembled' });
  });

  it('falls back to the English of text.ts when the locale lacks the key', () => {
    const bare = (key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue ?? key);
    expect(ui(bare, 'design.ui.title')).toBe(UI['design.ui.title']);
  });

  it('picks the plural form by the count', () => {
    expect(uiCount(enT, 'design.ui.permit.missing', 1)).toBe('1 required item is missing or not shared yet.');
    expect(uiCount(enT, 'design.ui.permit.missing', 4)).toBe('4 required items are missing or not shared yet.');
  });

  it('names a catalogue item by its key, then its texts, then its code', () => {
    expect(catalogueLabel(labels, { key: 'design.catalogue.simple_sequential.name', code: 'simple_sequential' })).toBe('Simple sequential');
    expect(catalogueLabel(labels, { key: 'tenant.unknown', labels: { de: 'Hausschema', en: 'House scheme' }, code: 'house' })).toBe('House scheme');
    expect(catalogueLabel(labels, { key: null, code: 'house_scheme' })).toBe('House scheme');
    expect(humanizeCode('structural_design')).toBe('Structural design');
  });

  it('names a phase from the setup, or readably when the setup does not know it', () => {
    expect(phaseName(labels, setup().phases, 'permit')).toBe('Permit design');
    expect(phaseName(labels, setup().phases, 'handover_stage')).toBe('Handover stage');
    expect(phaseName(labels, setup().phases, null)).toBe('');
  });
});

describe('refusals', () => {
  const refused = new ApiError(409, 'Conflict', {
    detail: {
      code: 'role_in_use',
      message_key: 'design.errors.role_in_use',
      message: 'The role is still used by drawings.',
      violations: [{ code: 'originator_required', field: 'originator_code', value: null }],
    },
  });

  it('reads the code, the sentence and the violations of a refusal', () => {
    expect(designErrorCode(refused)).toBe('role_in_use');
    expect(designErrorMessage(refused)).toBe('The role is still used by drawings.');
    expect(designViolations(refused)).toEqual([{ code: 'originator_required', field: 'originator_code', value: null }]);
    expect(designErrorCode(new Error('offline'))).toBeNull();
    expect(designViolations(new Error('offline'))).toEqual([]);
  });

  it('shows the sentence for the code', () => {
    expect(refusalText(enT, refused)).toBe('The role is still used by drawings.');
  });

  it('shows what the server wrote for a code the client does not know', () => {
    const bare = (key: string, opts?: Record<string, unknown>) => String(opts?.defaultValue ?? key);
    expect(errorText(bare, 'brand_new_code', 'A new rule refused this.')).toBe('A new rule refused this.');
    expect(errorText(bare, 'brand_new_code')).toBe('Brand new code');
  });
});
