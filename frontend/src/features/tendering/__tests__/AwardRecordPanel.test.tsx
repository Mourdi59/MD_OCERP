// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <AwardRecordPanel /> - the award record (Vergabevermerk) of a
// tender package. The screen has to be honest about two things: what the
// procedure has already recorded, and what it still owes at the stage it
// stands at.
//
// Coverage:
//   1. An early record names the decisions it already owes instead of looking
//      complete, and says nothing has been stored on the package yet.
//   2. The facts on screen are the procedure's own (the winner and the awarded
//      sum come off the record, not out of a form somebody filled in).
//   3. Writing a statement posts it against the section it belongs to.
//   4. An earlier statement stays readable after a newer one supersedes it.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import type { AwardRecord, AwardRecordSection } from '../api';

/* -- Toast mock ------------------------------------------------------- */

const toastMocks = vi.hoisted(() => ({ addToast: vi.fn() }));
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: Object.assign(
    (selector: (s: { addToast: typeof toastMocks.addToast }) => unknown) =>
      selector({ addToast: toastMocks.addToast }),
    { getState: () => ({ addToast: toastMocks.addToast }) },
  ),
}));

/* -- i18n shim - return defaultValue with interpolation. -------------- */

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string } & Record<string, unknown>) => {
      if (typeof opts === 'object' && opts && 'defaultValue' in opts) {
        let dv = String(opts.defaultValue ?? '');
        for (const [k, v] of Object.entries(opts)) {
          if (k === 'defaultValue') continue;
          dv = dv.replaceAll(`{{${k}}}`, String(v));
        }
        return dv;
      }
      return _key;
    },
    i18n: { language: 'en' },
  }),
  initReactI18next: { type: '3rdParty', init: () => undefined },
  I18nextProvider: ({ children }: { children: unknown }) => children,
  Trans: ({ children }: { children?: unknown }) => children ?? null,
}));

/* -- API mock --------------------------------------------------------- */

const apiMocks = vi.hoisted(() => ({
  getAwardRecord: vi.fn(),
  recordAwardRecordNote: vi.fn(),
}));
vi.mock('../api', () => ({
  getAwardRecord: apiMocks.getAwardRecord,
  recordAwardRecordNote: apiMocks.recordAwardRecordNote,
}));

import { AwardRecordPanel } from '../AwardRecordPanel';

function section(overrides: Partial<AwardRecordSection> & { key: string }): AwardRecordSection {
  return {
    source: 'reasoning',
    state: 'missing',
    facts: [],
    statement: '',
    value: '',
    recorded_at: null,
    recorded_by: null,
    superseded: [],
    ...overrides,
  };
}

function makeRecord(overrides?: Partial<AwardRecord>): AwardRecord {
  return {
    package_id: 'p-1',
    package_name: 'Dachabdichtung BA 2',
    project_name: 'Neubau Halle 3',
    stage: 'draft',
    currency: 'EUR',
    started: false,
    started_at: null,
    is_complete: false,
    sections: [
      section({
        key: 'subject',
        source: 'procedure',
        state: 'recorded',
        facts: [
          { key: 'package_name', text: 'Dachabdichtung BA 2', amount: null, currency: '', count: null, at: null, state: '' },
        ],
      }),
      section({ key: 'procedure_type' }),
      section({ key: 'procedure_reason' }),
      section({ key: 'award_reason', state: 'not_due_yet' }),
    ],
    gaps: [
      { section: 'procedure_type', source: 'reasoning' },
      { section: 'procedure_reason', source: 'reasoning' },
    ],
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AwardRecordPanel packageId="p-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  apiMocks.getAwardRecord.mockReset();
  apiMocks.recordAwardRecordNote.mockReset();
  toastMocks.addToast.mockReset();
});

afterEach(cleanup);

describe('AwardRecordPanel', () => {
  it('names the decisions the record already owes at an early stage', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(makeRecord());
    renderPanel();

    expect(await screen.findByText('2 point(s) still open at this stage')).toBeInTheDocument();
    // The open points are named, not counted and left mysterious.
    expect(screen.getAllByText('Type of procedure').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Reason for the type of procedure').length).toBeGreaterThan(0);
    // A stage the procedure has not reached is not a gap.
    expect(screen.getByText('Not due yet')).toBeInTheDocument();
  });

  it('says nothing is stored on the package until somebody writes', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(makeRecord());
    renderPanel();

    expect(
      await screen.findByText(
        'Nothing is stored on this package until you write the first statement, so a package this does not apply to is left exactly as it is.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the winner and the sum as facts the procedure recorded', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(
      makeRecord({
        stage: 'awarded',
        started: true,
        started_at: '2026-05-02T09:00:00Z',
        sections: [
          section({
            key: 'award_decision',
            source: 'procedure',
            state: 'recorded',
            facts: [
              { key: 'awarded_to', text: 'Bedachungen Kreuzer', amount: null, currency: '', count: null, at: null, state: '' },
              { key: 'awarded_sum', text: '', amount: '798000.00', currency: 'EUR', count: null, at: null, state: '' },
            ],
          }),
          section({ key: 'award_reason' }),
        ],
        gaps: [{ section: 'award_reason', source: 'reasoning' }],
      }),
    );
    renderPanel();

    expect(await screen.findByText('Bedachungen Kreuzer')).toBeInTheDocument();
    expect(screen.getByText('Awarded to')).toBeInTheDocument();
    // The one thing the procedure cannot supply is still open.
    expect(screen.getByText('1 point(s) still open at this stage')).toBeInTheDocument();
  });

  it('words the status codes a fact carries instead of printing them raw', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(
      makeRecord({
        sections: [
          section({
            key: 'subject',
            source: 'procedure',
            state: 'recorded',
            facts: [
              { key: 'covers_whole_bill', text: '', amount: null, currency: '', count: null, at: null, state: 'part_of_bill' },
            ],
          }),
          section({
            key: 'exclusions',
            source: 'reasoning',
            facts: [
              { key: 'bid_status', text: 'Flachdach Nord', amount: null, currency: '', count: null, at: null, state: 'rejected' },
            ],
          }),
        ],
        gaps: [],
        is_complete: true,
      }),
    );
    renderPanel();

    expect(await screen.findByText('Part of the bill')).toBeInTheDocument();
    expect(screen.getByText('Flachdach Nord, Rejected')).toBeInTheDocument();
    // The code itself never reaches the reader.
    expect(screen.queryByText(/part_of_bill/)).not.toBeInTheDocument();
    expect(screen.queryByText(/rejected/)).not.toBeInTheDocument();
  });

  it('writes a statement against the section it belongs to', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(
      makeRecord({
        sections: [section({ key: 'award_reason', state: 'missing' })],
        gaps: [{ section: 'award_reason', source: 'reasoning' }],
      }),
    );
    apiMocks.recordAwardRecordNote.mockResolvedValue(makeRecord({ started: true }));
    renderPanel();

    fireEvent.click(await screen.findByText('Record'));
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Levelled sum lowest and capacity confirmed for the programme.' },
    });
    fireEvent.click(screen.getByText('Save statement'));

    await waitFor(() => {
      expect(apiMocks.recordAwardRecordNote).toHaveBeenCalledWith('p-1', {
        section: 'award_reason',
        text: 'Levelled sum lowest and capacity confirmed for the programme.',
        value: undefined,
      });
    });
  });

  it('keeps an earlier statement readable after a newer one supersedes it', async () => {
    apiMocks.getAwardRecord.mockResolvedValue(
      makeRecord({
        started: true,
        is_complete: true,
        sections: [
          section({
            key: 'procedure_reason',
            state: 'recorded',
            statement: 'Below the threshold, three suitable firms in the region.',
            recorded_at: '2026-05-04T09:00:00Z',
            superseded: [
              {
                text: 'Three suitable firms in the region.',
                value: '',
                recorded_at: '2026-05-02T09:00:00Z',
                recorded_by: 'buyer-7',
              },
            ],
          }),
        ],
        gaps: [],
      }),
    );
    renderPanel();

    expect(
      await screen.findByText('Below the threshold, three suitable firms in the region.'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByText('1 earlier statement(s)'));
    expect(screen.getByText('Three suitable firms in the region.')).toBeInTheDocument();
    expect(screen.getByText('Complete for this stage')).toBeInTheDocument();
  });
});
