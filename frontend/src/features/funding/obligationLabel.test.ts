// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The rule these tests hold is that no English written by the server reaches
// a screen the reader set to another language, and that words the reader
// typed themselves are never replaced by a translation of something else.

import { describe, it, expect } from 'vitest';

import { obligationLabel } from './obligationLabel';
import type { FundingDisbursement, FundingObligation } from './api';

/** A translator that answers in a shape no English string could be mistaken for. */
const translate = ((key: string, opts?: { defaultValue?: string }) =>
  key.startsWith('funding.obligation_kind.')
    ? `DE:${key.slice('funding.obligation_kind.'.length)}`
    : (opts?.defaultValue ?? key)) as unknown as Parameters<typeof obligationLabel>[1];

function obligation(over: Partial<FundingObligation> = {}): FundingObligation {
  const row: FundingObligation = {
    id: 'o1',
    application_id: 'a1',
    kind: 'final_report',
    title: 'Final proof of use',
    detail: '',
    title_key: '',
    detail_key: 'funding.obligation_detail.final_report',
    detail_params: { days: 180, programme: 'KFW-261' },
    due_on: '2028-03-28',
    source: 'programme_rule',
    source_reference: 'KFW-261',
    responsible_user_id: null,
    status: 'open',
    completed_on: '',
    overdue: false,
    ...over,
  };
  // `title_key` is computed by the server, not stored, and the rule it uses is
  // the one mirrored here: the kind names a derived deadline, and an empty key
  // says the title is somebody's own words. Deriving it after the overrides
  // means a test that changes `kind` gets the key that change implies, rather
  // than a stale one pinned in the literal above.
  if (over.title_key === undefined) {
    row.title_key =
      row.source === 'manual' && row.title.trim() ? '' : `funding.obligation_kind.${row.kind}`;
  }
  return row;
}

function draw(over: Partial<FundingDisbursement> = {}): FundingDisbursement {
  return {
    id: 'd1',
    application_id: 'a1',
    sequence: 1,
    code: '',
    period_from: '',
    period_to: '',
    requested_on: '',
    approved_on: '',
    received_on: '2026-09-20',
    spend_deadline_on: '2026-12-19',
    amount_requested: '60000.00',
    amount_approved: '0.00',
    amount_received: '60000.00',
    status: 'paid',
    invoice_ids: [],
    notes: '',
    ...over,
  };
}

describe('a deadline the server derived', () => {
  it('is named from its kind, not from the English the server stored', () => {
    // The defect, stated: the row said "Final proof of use" on a page that
    // was otherwise entirely German, because the title is data.
    expect(obligationLabel(obligation(), translate)).toBe('DE:final_report');
  });

  it('is named from its kind for every derived source', () => {
    expect(obligationLabel(obligation({ source: 'award_notice' }), translate)).toBe('DE:final_report');
    expect(obligationLabel(obligation({ kind: 'retention_end' }), translate)).toBe('DE:retention_end');
  });

  it('takes the key the server states rather than rebuilding one', () => {
    // Two places deciding what a kind is called is two places to disagree.
    // The server sends the key; a row whose key and kind point different ways
    // proves which of the two this reads.
    const row = obligation({ kind: 'final_report', title_key: 'funding.obligation_kind.interim_report' });
    expect(obligationLabel(row, translate)).toBe('DE:interim_report');
  });

  it('builds the key itself when the server is too old to send one', () => {
    const row = obligation({ title_key: '' });
    expect(obligationLabel(row, translate)).toBe('DE:final_report');
  });

  it('falls back to the stored title when the kind has no translation at all', () => {
    // Better an English sentence than a raw enum: the fallback is what a new
    // kind added by the server but not yet by the locales would hit.
    const untranslated = ((key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key) as unknown as Parameters<typeof obligationLabel>[1];
    expect(obligationLabel(obligation(), untranslated)).toBe('Final proof of use');
  });
});

describe('a deadline someone typed', () => {
  it('keeps their words', () => {
    const manual = obligation({ source: 'manual', title: 'Call the energy adviser', kind: 'condition' });
    expect(obligationLabel(manual, translate)).toBe('Call the energy adviser');
  });

  it('falls back to the kind when they typed nothing', () => {
    const manual = obligation({ source: 'manual', title: '   ', kind: 'condition' });
    expect(obligationLabel(manual, translate)).toBe('DE:condition');
  });
});

describe('one spend window among several', () => {
  it('names the draw it belongs to', () => {
    // Two draws on one award produce two spend windows with the same name.
    // Without the reference the reader cannot tell which money is meant.
    const row = obligation({ kind: 'spend_window', due_on: '2026-12-19' });
    expect(obligationLabel(row, translate, [draw()])).toBe('DE:spend_window · #1');
  });

  it('prefers the draw reference the authority would recognise', () => {
    const row = obligation({ kind: 'spend_window', due_on: '2026-12-19' });
    expect(obligationLabel(row, translate, [draw({ code: 'MA-2026-01' })])).toBe(
      'DE:spend_window · MA-2026-01',
    );
  });

  it('matches on the deadline rather than on position in the list', () => {
    const row = obligation({ kind: 'spend_window', due_on: '2027-03-31' });
    const draws = [draw(), draw({ id: 'd2', sequence: 2, spend_deadline_on: '2027-03-31' })];
    expect(obligationLabel(row, translate, draws)).toBe('DE:spend_window · #2');
  });

  it('says nothing when two draws share the deadline', () => {
    // The match is a date, not a key. Two draws received on the same day under
    // the same terms both land on 2026-12-19, and naming either one would be a
    // confident wrong answer; the date on the row still tells them apart.
    const row = obligation({ kind: 'spend_window', due_on: '2026-12-19' });
    const draws = [draw({ code: 'MA-2026-01' }), draw({ id: 'd2', sequence: 2, code: 'MA-2026-02' })];
    expect(obligationLabel(row, translate, draws)).toBe('DE:spend_window');
  });

  it('says nothing about a draw it cannot find', () => {
    const row = obligation({ kind: 'spend_window', due_on: '2030-01-01' });
    expect(obligationLabel(row, translate, [draw()])).toBe('DE:spend_window');
    expect(obligationLabel(row, translate)).toBe('DE:spend_window');
  });
});
