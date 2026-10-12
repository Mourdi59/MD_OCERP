// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plain functions of the logistics plan: status moves, form to request
// body, the words for codes and findings, and what a refusal carries.

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import { planProblem, type PlanCatalogue } from '../api';
import {
  codeLabel,
  decimalsOf,
  enumLabel,
  findingText,
  formProblems,
  humanise,
  moveLabel,
  offered,
  openParts,
  reasonText,
  shown,
  stateLabel,
  toBody,
  toFormValues,
  weekdayOptions,
  type Field,
  type Lifecycle,
  WAITING,
} from '../rules';
import { instantOf, wallClock } from '../siteTime';
import { EN, isTextKey } from '../texts';
import { enT } from './i18nMock';

const words = { t: enT, language: 'en' };

describe('status moves', () => {
  it('every state and every move of the server has its own words', () => {
    // The moves themselves are the server's to offer (`can.transitions`); the screen only has to have a word for each.
    const planning = readFileSync(
      join(__dirname, '../../../../../../backend/app/modules/site_logistics/planning.py'),
      'utf-8',
    );
    const names: Record<Lifecycle, string> = {
      stage: 'STAGE_FSM',
      media: 'MEDIA_FSM',
      transport: 'TRANSPORT_FSM',
      permit: 'PERMIT_FSM',
      customs: 'CUSTOMS_FSM',
      document: 'CUSTOMS_DOCUMENT_FSM',
      complaint: 'COMPLAINT_FSM',
    };
    for (const [lifecycle, name] of Object.entries(names) as [Lifecycle, string][]) {
      const block = planning.slice(planning.indexOf(`${name}: dict`)).split('\n}')[0]!;
      const states = [...block.matchAll(/"(\w+)": \(([^)]*)\)/g)];
      expect(states.length, name).toBeGreaterThan(2);
      for (const m of states) {
        expect(isTextKey(`state.${m[1]}`), `state.${m[1]}`).toBe(true);
        for (const target of m[2]!.matchAll(/"(\w+)"/g)) {
          expect(isTextKey(`move.${lifecycle}.${target[1]}`), `move.${lifecycle}.${target[1]}`).toBe(true);
        }
      }
    }
    expect(stateLabel(enT, 'permit_pending')).toBe('Permit pending');
    expect(moveLabel(enT, 'transport', 'scheduled')).toBe('Schedule');
    expect(stateLabel(enT, 'brand_new_state')).toBe('Brand new state');
  });
});

describe('the site clock', () => {
  it('an hour typed for the site is the same instant wherever the planner sits', () => {
    expect(instantOf('2026-07-01T08:00', 'Europe/Berlin')).toBe('2026-07-01T06:00:00.000Z');
    expect(instantOf('2026-01-15T08:00', 'Europe/Berlin')).toBe('2026-01-15T07:00:00.000Z');
    expect(instantOf('2026-01-15T08:00', 'Asia/Kolkata')).toBe('2026-01-15T02:30:00.000Z');
  });

  it('a stored instant reads back as the hour on the site clock', () => {
    expect(wallClock('2026-07-01T06:00:00+00:00', 'Europe/Berlin')).toBe('2026-07-01T08:00');
    expect(wallClock('2026-01-15T02:30:00Z', 'Asia/Kolkata')).toBe('2026-01-15T08:00');
  });

  it('the hour after the clocks go forward lands after the change', () => {
    // 29 March 2026, 03:30 in Berlin is summer time already.
    expect(instantOf('2026-03-29T03:30', 'Europe/Berlin')).toBe('2026-03-29T01:30:00.000Z');
  });

  it('says nothing without a zone or with one the browser does not know', () => {
    expect(instantOf('2026-07-01T08:00', null)).toBeNull();
    expect(instantOf('2026-07-01T08:00', 'Mars/Olympus')).toBeNull();
    expect(wallClock('2026-07-01T06:00:00Z', undefined)).toBeNull();
    expect(wallClock('not a time', 'Europe/Berlin')).toBeNull();
  });

  it('a form with the site zone sends and shows site hours', () => {
    const f: Field[] = [{ name: 'planned_window_start', label: 'f.planned_window_start', kind: 'datetime' }];
    const body = toBody(f, { planned_window_start: '2026-07-01T08:00' }, null, 'Europe/Berlin');
    expect(body.planned_window_start).toBe('2026-07-01T06:00:00.000Z');
    expect(toFormValues(f, body, 'Europe/Berlin').planned_window_start).toBe('2026-07-01T08:00');
  });
});

describe('form to request body', () => {
  const fields: Field[] = [
    { name: 'title', label: 'f.title', kind: 'text', required: true },
    { name: 'gross_weight_t', label: 'f.gross_weight_t', kind: 'decimal' },
    { name: 'valid_to', label: 'f.valid_to', kind: 'date' },
    { name: 'buffer_days', label: 'f.buffer_days', kind: 'int' },
    { name: 'escort_required', label: 'f.escort_required', kind: 'checkbox' },
    { name: 'gate_id', label: 'f.gate', kind: 'select', options: [{ value: 'g1', label: 'North' }] },
  ];

  it('a new record leaves out what was not filled in, so the server default applies', () => {
    const values = { ...toFormValues(fields), title: '  Crane girder  ', gross_weight_t: '62,5' };
    expect(toBody(fields, values)).toEqual({ title: 'Crane girder', gross_weight_t: '62.5' });
  });

  it('a decimal stays the text the user typed and never becomes a float', () => {
    const values = { ...toFormValues(fields), title: 'x', gross_weight_t: '0.10' };
    expect(toBody(fields, values).gross_weight_t).toBe('0.10');
  });

  it('a change sends only what changed, and a cleared number or choice as null', () => {
    const record = { title: 'Girder', gross_weight_t: '62.5', valid_to: '2026-11-01', buffer_days: 2, escort_required: true, gate_id: 'g1' };
    const initial = toFormValues(fields, record);
    expect(toBody(fields, initial, initial)).toEqual({});
    const changed = { ...initial, gross_weight_t: '', gate_id: '', buffer_days: '3', escort_required: false };
    expect(toBody(fields, changed, initial)).toEqual({
      gross_weight_t: null,
      gate_id: null,
      buffer_days: 3,
      escort_required: false,
    });
  });

  it('a cleared text is sent as empty text, not null', () => {
    const initial = toFormValues(fields, { title: 'Girder' });
    expect(toBody([{ name: 'title', label: 'f.title', kind: 'text' }], { ...initial, title: '' }, initial)).toEqual({ title: '' });
  });

  it('a date and time is sent as an instant', () => {
    const f: Field[] = [{ name: 'planned_window_start', label: 'f.planned_window_start', kind: 'datetime' }];
    const body = toBody(f, { planned_window_start: '2026-11-03T06:30' });
    expect(body.planned_window_start).toBe(new Date('2026-11-03T06:30').toISOString());
    // And reads back into the input as the same local time.
    expect(toFormValues(f, body).planned_window_start).toBe('2026-11-03T06:30');
  });

  it('rows travel as a list of their own bodies, weekdays as numbers', () => {
    const f: Field[] = [
      {
        name: 'allowed_windows',
        label: 'f.allowed_windows',
        kind: 'rows',
        columns: [
          { name: 'from', label: 'f.window_from', kind: 'time', required: true },
          { name: 'to', label: 'f.window_to', kind: 'time', required: true },
          { name: 'weekdays', label: 'f.weekdays', kind: 'multi', options: weekdayOptions('en') },
        ],
      },
    ];
    const initial = toFormValues(f, { allowed_windows: [{ weekdays: [0, 1], from: '22:00', to: '05:00' }] });
    expect(initial.allowed_windows).toEqual([{ from: '22:00', to: '05:00', weekdays: ['0', '1'] }]);
    const changed = { allowed_windows: [{ from: '21:00', to: '05:00', weekdays: ['0', '1', '2'] }, { from: '09:00', to: '15:00', weekdays: [] }] };
    expect(toBody(f, changed, initial)).toEqual({
      allowed_windows: [
        { from: '21:00', to: '05:00', weekdays: [0, 1, 2] },
        { from: '09:00', to: '15:00' },
      ],
    });
  });

  it('names every field that blocks sending, also inside rows', () => {
    const f: Field[] = [
      ...fields,
      { name: 'rows', label: 'f.strategy', kind: 'rows', columns: [{ name: 'flow_code', label: 'f.flow_code', kind: 'text', required: true }] },
    ];
    const values = { ...toFormValues(f), gross_weight_t: 'heavy', rows: [{ flow_code: '' }] };
    expect(formProblems(f, values)).toEqual({
      title: 'required',
      gross_weight_t: 'number_invalid',
      'rows.0.flow_code': 'required',
    });
    expect(formProblems(fields, { ...toFormValues(fields), title: 'ok', gross_weight_t: '12,5' })).toEqual({});
  });
});

describe('words for codes', () => {
  const catalogue = {
    area_kinds: [
      { code: 'storage', counts_in_balance: true, balance_group: 'logistics' },
      { code: 'cold_store', labels: { en: 'Cold store', de: 'Kühllager' }, counts_in_balance: true, balance_group: 'logistics' },
      { code: 'tenant_only', counts_in_balance: true, balance_group: 'reserve' },
    ],
  } as unknown as PlanCatalogue;

  it('a shipped code reads from the locale', () => {
    expect(codeLabel(words, 'area_kinds', 'storage', catalogue)).toBe('Storage');
  });

  it("a catalogue's own label wins, in the reader's language", () => {
    expect(codeLabel({ t: enT, language: 'de-AT' }, 'area_kinds', 'cold_store', catalogue)).toBe('Kühllager');
    expect(codeLabel({ t: enT, language: 'fr' }, 'area_kinds', 'cold_store', catalogue)).toBe('Cold store');
  });

  it('a code nobody named is made readable rather than shown raw', () => {
    expect(codeLabel(words, 'area_kinds', 'tenant_only', catalogue)).toBe('Tenant only');
    expect(codeLabel(words, 'area_kinds', null, catalogue)).toBe('Not set');
    expect(humanise('eu_96_53_articulated')).toBe('Eu 96 53 articulated');
    expect(enumLabel(enT, 'body', 'police')).toBe('Police');
  });

  it('every code of the shipped neutral catalogue has a name', () => {
    const neutral = JSON.parse(
      readFileSync(
        join(__dirname, '../../../../../../backend/app/modules/site_logistics/catalogues/site_logistics/neutral.json'),
        'utf-8',
      ),
    ) as Record<string, unknown>;
    const unnamed: string[] = [];
    for (const group of ['area_kinds', 'media_kinds', 'transport_kinds', 'permit_kinds', 'customs_document_kinds', 'noise_limits', 'neighbour_issue_kinds']) {
      for (const entry of neutral[group] as { code: string; labels?: unknown }[]) {
        if (!entry.labels && !isTextKey(`code.${group}.${entry.code}`)) unnamed.push(`${group}.${entry.code}`);
      }
    }
    expect(unnamed).toEqual([]);
  });
});

describe('findings and refusals', () => {
  it('a finding is a sentence with its parameters, a media code by its name', () => {
    expect(
      findingText(words, { code: 'media_late', params: { stage: 'Shell', media: 'power' } }),
    ).toBe('Stage Shell: the Power connection is promised after the stage starts.');
  });

  it('a blocker without a title does not start with a colon', () => {
    expect(findingText(words, { code: 'heavy_without_permit' })).toBe('Heavy transport without a granted permit.');
    expect(findingText(words, { code: 'something_new' })).toBe('Something new');
  });

  it('every finding the server can raise has a sentence', () => {
    const messages = JSON.parse(
      readFileSync(join(__dirname, '../../../../../../backend/app/modules/site_logistics/messages/en.json'), 'utf-8'),
    ) as unknown;
    const codes = new Set<string>();
    const walk = (node: unknown, path: string) => {
      if (node && typeof node === 'object') {
        for (const [k, v] of Object.entries(node)) walk(v, path ? `${path}.${k}` : k);
      } else {
        const m = /^site_logistics\.findings\.(\w+)\.fail$/.exec(path);
        if (m) codes.add(m[1]!);
      }
    };
    walk(messages, '');
    expect(codes.size).toBeGreaterThan(15);
    expect([...codes].filter((c) => !(`finding.${c}` in EN))).toEqual([]);
  });

  it("a refusal carries the server's sentence, its code and every blocker", () => {
    const err = new ApiError(422, 'Unprocessable', {
      detail: {
        code: 'gate_load_exceeded',
        message_key: 'site_logistics.errors.gate_load_exceeded',
        message: 'The load exceeds the limits of the site entrance.',
        violations: [{ code: 'gate_load_exceeded', fields: ['max_gross_t'] }, { code: 'quiet_hours_conflict' }],
      },
    });
    const problem = planProblem(err);
    expect(problem.code).toBe('gate_load_exceeded');
    expect(problem.message).toBe('The load exceeds the limits of the site entrance.');
    expect(problem.violations.map((v) => v.code)).toEqual(['gate_load_exceeded', 'quiet_hours_conflict']);
  });

  it('a refusal without a structured body still has a message', () => {
    expect(planProblem(new Error('offline')).message).toBe('offline');
    const plain = planProblem(new ApiError(403, 'Forbidden', { detail: 'Missing permission site_logistics.approve' }));
    expect(plain.code).toBeNull();
    expect(plain.message).toContain('site_logistics.approve');
  });
});

describe('numbers and days', () => {
  it('shows the decimals a value carries, never more than three', () => {
    expect(decimalsOf('1250.00')).toBe(0);
    expect(decimalsOf('12.50')).toBe(1);
    expect(decimalsOf('0.12345')).toBe(3);
    expect(decimalsOf(40)).toBe(0);
  });

  it('weekdays start on Monday, as the server counts them', () => {
    const days = weekdayOptions('en');
    expect(days.map((d) => d.value)).toEqual(['0', '1', '2', '3', '4', '5', '6']);
    expect(days[0]!.label).toBe('Mon');
    expect(days[6]!.label).toBe('Sun');
  });
});

describe('what a verdict does to a button', () => {
  const yes = { allowed: true, applies: true, reason: null };
  const refused = { allowed: false, applies: true, reason: 'slot_taken' };
  const noRight = { allowed: false, applies: true, reason: 'permission_denied' };
  const noSuchMove = { allowed: false, applies: false, reason: 'invalid_transition' };

  it('can be pressed only when the move exists and is allowed', () => {
    expect([yes, refused, noRight, noSuchMove].map(offered)).toEqual([true, false, false, false]);
  });

  it('stays on the screen when the record refuses it, and leaves when the reader has no right', () => {
    expect([yes, refused, noRight, noSuchMove].map(shown)).toEqual([true, true, false, false]);
  });

  it('refuses nothing where the server gives no verdict at all', () => {
    expect(offered(undefined)).toBe(true);
    expect(shown(undefined)).toBe(true);
  });

  it('waits on the screen, not pressable and without a reason, until the answer arrives', () => {
    expect(shown(WAITING)).toBe(true);
    expect(offered(WAITING)).toBe(false);
    expect(reasonText(enT, WAITING)).toBeUndefined();
  });
});

describe('what a readiness item still waits for', () => {
  it('reads the permits in progress and the missing ones out of the detail', () => {
    expect(openParts('permit_applied: Transformer; permit_missing: Crane,Girder')).toEqual([
      { key: 'readiness.open.permit_applied', titles: 'Transformer' },
      { key: 'readiness.open.permit_missing', titles: 'Crane, Girder' },
    ]);
  });

  it('gives nothing for a detail it has no words for', () => {
    expect(openParts('')).toEqual([]);
    expect(openParts(null)).toEqual([]);
    expect(openParts('3 of 4 stages')).toEqual([]);
    expect(openParts('other_reason: something')).toEqual([]);
    expect(openParts('permit_missing: ')).toEqual([]);
  });

  it('reads one part when the other is absent', () => {
    expect(openParts('permit_missing: Crane')).toEqual([{ key: 'readiness.open.permit_missing', titles: 'Crane' }]);
  });
});
