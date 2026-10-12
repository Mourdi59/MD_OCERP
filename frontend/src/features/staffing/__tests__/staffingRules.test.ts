// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plain rules of the staffing forms and the words the screens show for a
// code: what a form refuses before sending, which state changes are offered,
// how a catalogue item, a finding and a refusal are named.

import { describe, expect, it, vi } from 'vitest';

vi.mock('react-i18next', async () => (await import('./i18nMock')).i18nMockModule);

import { ApiError } from '@/shared/lib/api';

import { staffingErrorCode, staffingViolations } from '../api';
import {
  catalogueName,
  errorText,
  findingText,
  humanizeCode,
  labelText,
  positionName,
  refusalText,
  type LabelContext,
} from '../labels';
import { positionProblem } from '../PositionDialogs';
import {
  allowedStatusMoves,
  costProblem,
  datesProblem,
  decimalString,
  fteDecimals,
  fteProblem,
  groupByPhase,
  headcountProblem,
  last4Problem,
  liveFills,
  nextLeaveStatuses,
  nextTravelStatuses,
  phasesOf,
  planIsLocked,
  planIsSubmittable,
  requirementTags,
  rolesNotPlanned,
} from '../rules';
import { enT } from './i18nMock';
import en from '@/app/locales/en';
import { catalogue, fill, no, position, yes } from './fixtures';

const labels: LabelContext = { t: enT, language: 'en', exists: (k) => k in en.translation };

/** Like i18next itself: a key the locale lacks renders its defaultValue, which the strict mock does not. */
const liveT = (key: string, opts?: Record<string, unknown>) =>
  key in en.translation ? enT(key, opts) : String(opts?.defaultValue ?? key);

describe('plan state', () => {
  it('locks only a plan in review', () => {
    expect(planIsLocked('in_review')).toBe(true);
    for (const s of ['draft', 'approved', 'binding', 'revising'] as const) expect(planIsLocked(s)).toBe(false);
  });

  it('offers submission for a draft and a revision only', () => {
    expect(planIsSubmittable('draft')).toBe(true);
    expect(planIsSubmittable('revising')).toBe(true);
    for (const s of ['in_review', 'approved', 'binding'] as const) expect(planIsSubmittable(s)).toBe(false);
  });
});

describe('state changes offered', () => {
  it('offers the position moves the server allows and no other', () => {
    expect(allowedStatusMoves(position())).toEqual(['recruiting', 'on_hold', 'cancelled']);
    const locked = { open: no('plan_in_review'), recruiting: no('plan_in_review'), on_hold: no('plan_in_review'), cancelled: no('plan_in_review') };
    expect(allowedStatusMoves(position({ can: { ...position().can, status: locked } }))).toEqual([]);
    // The client has no table of its own: a state the server adds is offered, one it drops is not.
    expect(allowedStatusMoves(position({ can: { ...position().can, status: { paused: yes } } }))).toEqual(['paused']);
  });

  it('follows the travel and leave lifecycles', () => {
    expect(nextTravelStatuses('planned')).toEqual(['booked', 'cancelled']);
    expect(nextTravelStatuses('done')).toEqual([]);
    expect(nextLeaveStatuses('requested')).toEqual(['approved', 'cancelled']);
    expect(nextLeaveStatuses('taken')).toEqual([]);
  });
});

describe('numbers the reader types', () => {
  it('keeps a decimal as a string and accepts a comma', () => {
    expect(decimalString('0,5')).toBe('0.5');
    expect(decimalString(' 380.00 ')).toBe('380.00');
    expect(decimalString('abc')).toBeNull();
    expect(decimalString('-1')).toBeNull();
  });

  it('accepts an FTE above 0 and at most 1', () => {
    for (const ok of ['1', '1.0', '0.5', '0,25', '0.01']) expect(fteProblem(ok)).toBeNull();
    for (const bad of ['0', '0.0', '1.1', '2', '', 'half']) expect(fteProblem(bad)).toBe('fte_out_of_range');
  });

  it('wants a headcount of at least one', () => {
    expect(headcountProblem('3')).toBeNull();
    expect(headcountProblem('0')).toBe('headcount_invalid');
    expect(headcountProblem('1.5')).toBe('headcount_invalid');
  });

  it('refuses an end before the start and allows an open end', () => {
    expect(datesProblem('2026-09-01', '2026-08-31')).toBe('exit_before_entry');
    expect(datesProblem('2026-09-01', '2026-09-01')).toBeNull();
    expect(datesProblem('2026-09-01', '')).toBeNull();
  });

  it('refuses more than four characters of a document number', () => {
    expect(last4Problem('4821')).toBeNull();
    expect(last4Problem('')).toBeNull();
    expect(last4Problem('C01X4821')).toBe('full_number_rejected');
  });

  it('wants a currency for a cost and a plain amount', () => {
    expect(costProblem('', '')).toBeNull();
    expect(costProblem('380.00', 'EUR')).toBeNull();
    expect(costProblem('380.00', '')).toBe('currency_required');
    expect(costProblem('about 400', 'EUR')).toBe('cost_invalid');
  });

  it('shows one decimal unless the figure needs two', () => {
    expect(fteDecimals('1.00')).toBe(1);
    expect(fteDecimals('0.50')).toBe(1);
    expect(fteDecimals('0.25')).toBe(2);
    expect(fteDecimals(null)).toBe(1);
  });
});

describe('position draft', () => {
  const ok = { role_code: 'site_manager', custom_label: '', fte: '1', headcount: '1', entry_date: '', exit_date: '' };

  it('passes a complete draft', () => {
    expect(positionProblem(ok, 'custom')).toBeNull();
  });

  it('wants a name for a role that is not in the catalogue', () => {
    expect(positionProblem({ ...ok, role_code: 'custom' }, 'custom')).toBe('custom_role_needs_label');
    expect(positionProblem({ ...ok, role_code: 'custom', custom_label: 'Interface manager' }, 'custom')).toBeNull();
    // Which code means a free role is the catalogue's to say.
    expect(positionProblem({ ...ok, role_code: 'other' }, 'other')).toBe('custom_role_needs_label');
    expect(positionProblem({ ...ok, role_code: 'custom' }, 'other')).toBeNull();
  });

  it('names the first problem with the code the server would use', () => {
    expect(positionProblem({ ...ok, fte: '1.5' }, 'custom')).toBe('fte_out_of_range');
    expect(positionProblem({ ...ok, entry_date: '2026-09-02', exit_date: '2026-09-01' }, 'custom')).toBe('exit_before_entry');
  });
});

describe('mappers', () => {
  const positions = [
    position({ id: 'a', phase: 'operation', role_code: 'operator_plant_manager' }),
    position({ id: 'b', phase: 'execution', role_code: 'project_manager', fills: [fill({ id: 'f1' }), fill({ id: 'f2', status: 'ended' })] }),
    position({ id: 'c', phase: 'execution', role_code: 'site_manager', status: 'cancelled', stored_status: 'cancelled' }),
  ];

  it('takes the phases from the catalogue response, in its order, and holds no list of its own', () => {
    expect(phasesOf(catalogue())).toEqual(['development', 'execution', 'operation']);
    const other = catalogue({ phases: ['tender', 'build'] });
    expect(phasesOf(other)).toEqual(['tender', 'build']);
    // A phase only an old position still carries is kept, after the catalogue's own.
    expect(phasesOf(other, [position({ phase: 'execution' })])).toEqual(['tender', 'build', 'execution']);
    expect(phasesOf(null)).toEqual([]);
  });

  it('offers what a key role can be required before from the server, with whether a gate checks it', () => {
    expect(requirementTags(catalogue())).toEqual([
      { tag: 'construction_start', resolvable: true },
      { tag: 'handover', resolvable: false },
    ]);
    // A tag already on the position stays selectable even when the vocabulary dropped it.
    expect(requirementTags(catalogue({ required_before_options: [] }), 'old_tag')).toEqual([{ tag: 'old_tag', resolvable: false }]);
    expect(requirementTags(catalogue({ required_before_options: [] }))).toEqual([]);
  });

  it('groups positions by phase in the catalogue order and drops empty phases', () => {
    expect(groupByPhase(positions, phasesOf(catalogue(), positions)).map((g) => [g.phase, g.positions.map((p) => p.id)])).toEqual([
      ['execution', ['b', 'c']],
      ['operation', ['a']],
    ]);
  });

  it('offers the catalogue roles of a phase that are not planned, counting a cancelled position as not planned', () => {
    expect(rolesNotPlanned(catalogue(), positions, 'execution').map((r) => r.code)).toEqual(['site_manager']);
    expect(rolesNotPlanned(catalogue(), positions, 'operation')).toEqual([]);
  });

  it('lists only live assignments as handover sources', () => {
    expect(liveFills(positions).map((x) => x.fill.id)).toEqual(['f1']);
  });
});

describe('names', () => {
  it('names a shipped catalogue item through its locale key', () => {
    expect(catalogueName(labels, catalogue(), 'role', 'site_manager')).toBe('Site manager');
    expect(catalogueName(labels, catalogue(), 'organisation', 'operator')).toBe('Operator organisation');
    expect(catalogueName(labels, catalogue(), 'document_kind', 'work_permit')).toBe('Work permit');
  });

  it('names a tenant catalogue item by its own text in the reader language', () => {
    const tenant = catalogue({
      roles: [{ ...catalogue().roles[0]!, code: 'tunnel_lead', name_key: '', labels: { en: 'Tunnel lead', de: 'Tunnelleitung' } }],
    });
    expect(catalogueName(labels, tenant, 'role', 'tunnel_lead')).toBe('Tunnel lead');
    expect(catalogueName({ ...labels, language: 'de-AT' }, tenant, 'role', 'tunnel_lead')).toBe('Tunnelleitung');
  });

  it('falls back to the platform key and then to readable words, never a raw key', () => {
    expect(catalogueName(labels, null, 'role', 'scheduler')).toBe('Scheduler');
    expect(catalogueName(labels, null, 'role', 'night_shift_lead')).toBe('Night shift lead');
    expect(humanizeCode('a1_posting-certificate')).toBe('A1 posting certificate');
  });

  it('names a catalogue in the picker by key or by text', () => {
    expect(labelText(labels, { key: 'staffing.catalogue.neutral.name', text: null }, 'neutral')).toBe('Staffing model, country neutral');
    expect(labelText(labels, { key: null, text: { en: 'Our staffing model' } }, 'own')).toBe('Our staffing model');
    expect(labelText(labels, null, 'own_model')).toBe('Own model');
  });

  it('prefers the title, then the custom name, then the role', () => {
    const cat = catalogue();
    expect(positionName(labels, cat, { role_code: 'site_manager', custom_label: null, title: 'Site manager north' })).toBe('Site manager north');
    expect(positionName(labels, cat, { role_code: 'custom', custom_label: 'Interface manager', title: null })).toBe('Interface manager');
    expect(positionName(labels, cat, { role_code: 'site_manager', custom_label: null, title: ' ' })).toBe('Site manager');
  });
});

describe('findings and refusals', () => {
  it('writes the role name into a finding, whether the server named a role or a position', () => {
    const cat = catalogue();
    expect(findingText(labels, cat, { code: 'key_role_missing', ref: 'site_manager', severity: 'error', detail: '' })).toBe(
      'Key role Site manager has no position.',
    );
    expect(
      findingText(labels, cat, { code: 'handover_missing', ref: '6f1c0c1e-0000-4000-8000-000000000001', severity: 'error', detail: 'project_manager' }),
    ).toBe('Role Project manager needs a handover.');
  });

  it('leaves no placeholder braces in any finding sentence', () => {
    for (const code of ['handover_missing', 'key_role_missing', 'key_role_not_filled_before_gate', 'operation_role_late', 'no_accommodation']) {
      const text = findingText(labels, catalogue(), { code, ref: 'site_manager', severity: 'error', detail: '' });
      expect(text).not.toMatch(/[{}]/);
    }
  });

  it('reads the code and the violations of a refusal', () => {
    const err = new ApiError(422, 'Unprocessable', {
      detail: {
        code: 'key_role_missing',
        message_key: 'staffing.errors.key_role_missing',
        message: 'Key role has no position.',
        violations: [{ code: 'key_role_missing', ref: 'site_manager', severity: 'error', detail: '' }],
      },
    });
    expect(staffingErrorCode(err)).toBe('key_role_missing');
    expect(staffingViolations(err)).toHaveLength(1);
    expect(staffingErrorCode(new Error('offline'))).toBeNull();
    expect(staffingViolations(new Error('offline'))).toEqual([]);
  });

  it('shows the sentence of a known refusal code', () => {
    const err = new ApiError(409, 'Conflict', { detail: { code: 'plan_in_review', message: 'server text' } });
    expect(refusalText(enT, err)).toBe('The plan is in review. Return it to draft before editing.');
  });

  it('falls back to the sentence the server sent for a code the locale does not know', () => {
    const err = new ApiError(409, 'Conflict', { detail: { code: 'brand_new_code', message: 'The server explains it.' } });
    expect(refusalText(liveT, err)).toBe('The server explains it.');
    expect(errorText(liveT, 'brand_new_code')).toBe('Brand new code');
  });

  it('adds the date a retention duty runs until', () => {
    const err = new ApiError(409, 'Conflict', {
      detail: { code: 'retention_obligation_active', message: 'x', info: '2029-03-31' },
    });
    const text = refusalText(enT, err);
    expect(text).toContain('A legal retention duty still runs for this file.');
    expect(text).toContain('2029');
  });

  it('reads a failure that is not a staffing refusal through the shared reader', () => {
    expect(refusalText(enT, new Error('Network down'))).toBe('Network down');
  });
});
