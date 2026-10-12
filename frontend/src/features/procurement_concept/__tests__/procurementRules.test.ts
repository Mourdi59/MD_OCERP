// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plain rules of the procurement screens: amounts, verdicts, what a state
// offers, what a form still misses and what it sends.

import { describe, expect, it } from 'vitest';

import { catalogueName, errorText, findingText, humanizeCode, vocab, PACKAGE_STATE, type LabelContext } from '../labels';
import {
  calledOffShare,
  candidateProblems,
  conceptSteps,
  editVerdict,
  frameworkProblems,
  frameworkTargets,
  hasProposal,
  isConfirmed,
  packageDraft,
  packageMoves,
  packageProblems,
  parseAmount,
  profileProblems,
  scoresValid,
  soundingReady,
  soundingUnmitigated,
  splitFindings,
  steerVerdict,
  toFrameworkPatch,
  toPackageInput,
  toProfileInput,
  toScoreInputs,
  toSoundingInput,
  weightsTotal,
  type FrameworkDraft,
  type ProfileDraft,
  type SoundingDraft,
} from '../rules';
import { enT } from './i18nMock';
import {
  agreementPackage,
  blockingFinding,
  concept,
  packageView,
  schedule,
  supplyPackage,
  unplannedPackage,
  warningFinding,
} from './fixtures';

describe('parseAmount', () => {
  it.each([
    ['2400000', '2400000'],
    ['2400000.50', '2400000.50'],
    ['1 250 000,50', '1250000.50'],
    ['1,250,000.50', '1250000.50'],
    ['1.250.000,50', '1250000.50'],
    ['1,250,000', '1250000'],
    ['1.250.000', '1250000'],
    ["1'250'000.5", '1250000.5'],
    ['12,5', '12.5'],
    ['0.1', '0.1'],
  ])('reads %s as %s', (input, expected) => {
    expect(parseAmount(input)).toBe(expected);
  });

  it.each(['', '  ', 'abc', '-5', '1e6', '12.3.4x', '1,2,3'])('refuses %j', (input) => {
    expect(parseAmount(input)).toBeNull();
  });

  it('keeps every digit of a large amount, which a float would not', () => {
    expect(parseAmount('9007199254740993.01')).toBe('9007199254740993.01');
  });
});

describe('verdicts follow the server flags', () => {
  it('allows what the server allows', () => {
    const c = concept();
    expect(editVerdict(c)).toBeNull();
    expect(steerVerdict(c)).toBeNull();
  });

  it('names the procurement owner when the reader may not steer', () => {
    const c = concept({ can: { edit: false, approve: false, steer: false } });
    expect(editVerdict(c)).toBe('not_procurement_owner');
    expect(steerVerdict(c)).toBe('not_procurement_owner');
  });

  it('says the plan is locked while it is reviewed or approved', () => {
    const c = concept({ state: 'in_review', can: { edit: false, approve: true, steer: true } });
    expect(editVerdict(c)).toBe('concept_locked');
    expect(steerVerdict(c)).toBeNull();
  });

  it('points a binding concept to the change request', () => {
    const c = concept({ state: 'binding', can: { edit: false, approve: false, steer: true } });
    expect(editVerdict(c)).toBe('binding_requires_change_request');
  });
});

describe('conceptSteps', () => {
  it('a draft and a reopened concept can be submitted', () => {
    expect(conceptSteps(concept()).map((s) => s.action)).toEqual(['submit']);
    expect(conceptSteps(concept({ state: 'reopened' })).map((s) => s.action)).toEqual(['submit']);
  });

  it('a concept in review is approved by who the server entitles, or returned', () => {
    const steps = conceptSteps(concept({ state: 'in_review', can: { edit: false, approve: false, steer: true } }));
    expect(steps.map((s) => s.action)).toEqual(['approve', 'return']);
    expect(steps[0]!.verdict).toBe('not_procurement_owner');
    expect(steps[1]!.verdict).toBeNull();
  });

  it('an approved concept can only be reopened, and a binding one offers nothing', () => {
    expect(conceptSteps(concept({ state: 'approved' })).map((s) => s.action)).toEqual(['reopen']);
    expect(conceptSteps(concept({ state: 'binding' }))).toEqual([]);
  });
});

describe('splitFindings', () => {
  it('separates what blocks approval from warnings', () => {
    const out = splitFindings([warningFinding, blockingFinding]);
    expect(out.blocking).toEqual([blockingFinding]);
    expect(out.warnings).toEqual([warningFinding]);
  });
});

describe('package plan', () => {
  it('sends nothing for an untouched form', () => {
    const d = packageDraft(packageView());
    expect(toPackageInput(d, d)).toEqual({});
  });

  it('sends only the changed fields, the amount as a string', () => {
    const original = packageDraft(packageView());
    const body = toPackageInput({ ...original, estimated_value: '2 600 000,00', procedure_code: 'restricted' }, original);
    expect(body).toEqual({ estimated_value: '2600000.00', procedure_code: 'restricted' });
    expect(typeof body.estimated_value).toBe('string');
  });

  it('does not resend an amount that only differs in trailing zeros', () => {
    const original = packageDraft(packageView());
    expect(toPackageInput({ ...original, estimated_value: '2400000' }, original)).toEqual({});
  });

  it('clears a field with null and a text with an empty string', () => {
    const original = packageDraft(supplyPackage);
    const body = toPackageInput({ ...original, need_date: '', is_advance: false, advance_reason: '', estimated_value: '' }, original);
    expect(body).toEqual({ need_date: null, is_advance: false, advance_reason: '', estimated_value: null });
  });

  it('a first plan sends the value with its currency', () => {
    const original = packageDraft(unplannedPackage);
    const body = toPackageInput({ ...original, estimated_value: '500000', currency: 'eur', lead_time_days: '90' }, original);
    expect(body).toEqual({ estimated_value: '500000', currency: 'EUR', lead_time_days: 90 });
  });

  it('lists what the form still misses', () => {
    const d = packageDraft(unplannedPackage);
    expect(packageProblems(d)).toEqual([]);
    expect(packageProblems({ ...d, estimated_value: 'about a million' })).toEqual(['value_invalid', 'currency_invalid']);
    expect(packageProblems({ ...d, estimated_value: '100', currency: 'EURO' })).toEqual(['currency_invalid']);
    expect(packageProblems({ ...d, is_advance: true })).toEqual(['advance_without_reason']);
    expect(packageProblems({ ...d, lead_time_days: '2000' })).toEqual(['lead_time_invalid']);
  });
});

describe('packageMoves', () => {
  it('a package with a procedure can be changed, held, cancelled and sent to tender', () => {
    expect(packageMoves(packageView())).toEqual({
      edit: true,
      hold: true,
      resume: false,
      cancel: true,
      execution: 'bid_package',
      candidates: true,
    });
  });

  it('a supply package goes out as a request for quotation', () => {
    expect(packageMoves(supplyPackage).execution).toBe('rfq');
  });

  it('a package without a plan can only be planned', () => {
    expect(packageMoves(unplannedPackage)).toEqual({
      edit: true,
      hold: false,
      resume: false,
      cancel: false,
      execution: null,
      candidates: false,
    });
  });

  it('a kind that is not procured offers nothing', () => {
    expect(Object.values(packageMoves(agreementPackage)).every((v) => !v)).toBe(true);
  });

  it('a package on hold can be resumed or cancelled, not changed into tender', () => {
    const m = packageMoves(packageView({}, { state: 'on_hold' }));
    expect(m).toMatchObject({ hold: false, resume: true, cancel: true, execution: null });
  });

  it('a package in tender is closed for the plan and an awarded one for everything', () => {
    expect(packageMoves(packageView({}, { state: 'in_tender' }))).toMatchObject({ edit: false, hold: false, cancel: true });
    expect(packageMoves(packageView({}, { state: 'awarded' }))).toMatchObject({ edit: false, cancel: false, execution: null });
  });

  it('a package that already has its tender vehicle does not get a second one', () => {
    const view = packageView();
    view.contract_package.execution_link = { kind: 'bid_package', id: 'b1' };
    expect(packageMoves(view).execution).toBeNull();
  });
});

describe('prequalification profile', () => {
  const base: ProfileDraft = {
    name: 'Works',
    pass_mark: '60',
    validity_months: '12',
    criteria: [
      { code: 'exclusion_grounds', kind: 'pass_fail', weight: '0' },
      { code: 'similar_projects', kind: 'scored', weight: '33.33' },
      { code: 'technical_capacity', kind: 'scored', weight: '33.33' },
      { code: 'hse_record', kind: 'scored', weight: '33.34' },
    ],
  };

  it('adds the scored weights up exactly', () => {
    expect(weightsTotal(base.criteria)).toBe('100');
    expect(profileProblems(base)).toEqual([]);
  });

  it('refuses weights that do not add up to 100', () => {
    const d = { ...base, criteria: base.criteria.slice(0, 3) };
    expect(weightsTotal(d.criteria)).toBe('66.66');
    expect(profileProblems(d)).toEqual(['weights_not_100']);
  });

  it('a profile of pass or fail criteria only needs no weights', () => {
    expect(profileProblems({ ...base, criteria: base.criteria.slice(0, 1) })).toEqual([]);
  });

  it('needs a name, a criterion and a pass mark within range', () => {
    expect(profileProblems({ name: ' ', pass_mark: '120', validity_months: '12', criteria: [] })).toEqual([
      'name_required',
      'no_criteria',
      'pass_mark_invalid',
    ]);
  });

  it('sends weights and the pass mark as strings, and no weight for pass or fail', () => {
    const body = toProfileInput({ ...base, pass_mark: '62,5' }, 'k1');
    expect(body.pass_mark).toBe('62.5');
    expect(body.package_id).toBe('k1');
    expect(body.criteria[0]).toEqual({ code: 'exclusion_grounds', weight: '0' });
    expect(body.criteria.every((c) => typeof c.weight === 'string')).toBe(true);
  });
});

describe('candidates and scores', () => {
  const draft = {
    subcontractor_id: '',
    free_name: '',
    source: 'own_list' as const,
    list: 'long' as const,
    decision_rationale: '',
    conflict_of_interest_declared: false,
    conflict_note: '',
  };

  it('needs a company, a reason to exclude, and a registered company to short-list', () => {
    expect(candidateProblems(draft)).toEqual(['needs_company']);
    expect(candidateProblems({ ...draft, free_name: 'Roofing contractor' })).toEqual([]);
    expect(candidateProblems({ ...draft, free_name: 'Roofing contractor', list: 'short' })).toEqual(['short_needs_registered']);
    expect(candidateProblems({ ...draft, subcontractor_id: 's1', list: 'short' })).toEqual([]);
    expect(candidateProblems({ ...draft, subcontractor_id: 's1', list: 'excluded' })).toEqual(['excluded_needs_rationale']);
  });

  it('keeps a vendor candidate short-listable although the form links subcontractors only', () => {
    expect(candidateProblems({ ...draft, list: 'short' }, true)).toEqual([]);
  });

  it('sends only assessed rows, a verdict for pass or fail and points as a string', () => {
    const rows = [
      { criterion_code: 'exclusion_grounds', kind: 'pass_fail' as const, passed: 'yes' as const, score: '' },
      { criterion_code: 'insurance_cover', kind: 'pass_fail' as const, passed: '' as const, score: '' },
      { criterion_code: 'similar_projects', kind: 'scored' as const, passed: '' as const, score: '87,5' },
      { criterion_code: 'hse_record', kind: 'scored' as const, passed: '' as const, score: '' },
    ];
    expect(scoresValid(rows)).toBe(true);
    expect(toScoreInputs(rows)).toEqual([
      { criterion_code: 'exclusion_grounds', passed: true },
      { criterion_code: 'similar_projects', score: '87.5' },
    ]);
  });

  it('refuses points outside 0 to 100', () => {
    expect(scoresValid([{ criterion_code: 'x', kind: 'scored', passed: '', score: '101' }])).toBe(false);
    expect(scoresValid([{ criterion_code: 'x', kind: 'scored', passed: '', score: 'good' }])).toBe(false);
  });
});

describe('market sounding', () => {
  const draft: SoundingDraft = {
    package_ids: [],
    trade: ' Steel ',
    held_on: '2026-09-15',
    method: 'meeting',
    findings: '',
    capacity_signal: 'tight',
    price_signal: 'unknown',
    lead_time_signal_days: '',
    mitigation: '',
    resplit: false,
  };

  it('warns on tight capacity with no answer to it', () => {
    expect(soundingUnmitigated(draft)).toBe(true);
    expect(soundingUnmitigated({ ...draft, mitigation: 'Early contractor involvement' })).toBe(false);
    expect(soundingUnmitigated({ ...draft, resplit: true })).toBe(false);
    expect(soundingUnmitigated({ ...draft, capacity_signal: 'adequate' })).toBe(false);
  });

  it('needs a date and takes whole days', () => {
    expect(soundingReady(draft)).toBe(true);
    expect(soundingReady({ ...draft, held_on: '' })).toBe(false);
    expect(soundingReady({ ...draft, lead_time_signal_days: 'four months' })).toBe(false);
    expect(toSoundingInput({ ...draft, lead_time_signal_days: '120' })).toMatchObject({ trade: 'Steel', lead_time_signal_days: 120 });
    expect(toSoundingInput(draft).lead_time_signal_days).toBeNull();
  });
});

describe('award schedule rows', () => {
  it('a row has a proposal once it has both dates, and is confirmed once both milestones exist', () => {
    const [ready, bare] = schedule.items;
    expect(hasProposal(ready!)).toBe(true);
    expect(hasProposal(bare!)).toBe(false);
    expect(isConfirmed(ready!)).toBe(false);
    expect(isConfirmed({ ...ready!, start_activity_id: 'a1', award_activity_id: 'a2' })).toBe(true);
  });
});

describe('framework agreements', () => {
  const draft: FrameworkDraft = {
    code: 'FW-01',
    title: 'Supply',
    supplier_name: '',
    scope: '',
    package_kinds: ['supply'],
    max_value: '2 500 000',
    currency: 'eur',
    start_date: '2026-03-01',
    end_date: '2029-03-01',
    call_off_mode: 'direct',
    source_procedure_ref: '',
  };

  it('accepts a complete agreement and names every gap of an empty one', () => {
    expect(frameworkProblems(draft)).toEqual([]);
    expect(frameworkProblems({ ...draft, code: '', max_value: '', currency: '', start_date: '', end_date: '' })).toEqual([
      'code_required',
      'value_invalid',
      'currency_invalid',
      'dates_required',
    ]);
    expect(frameworkProblems({ ...draft, end_date: '2025-01-01' })).toEqual(['dates_inverted']);
  });

  it('a change keeps code, currency and start date out of the request', () => {
    const patch = toFrameworkPatch(draft);
    expect(patch).not.toHaveProperty('code');
    expect(patch).not.toHaveProperty('currency');
    expect(patch).not.toHaveProperty('start_date');
    expect(patch.max_value).toBe('2500000');
  });

  it('offers the moves the state allows', () => {
    expect(frameworkTargets('draft')).toEqual(['active', 'terminated']);
    expect(frameworkTargets('active')).toEqual(['exhausted', 'expired', 'terminated']);
    expect(frameworkTargets('exhausted')).toEqual(['active', 'terminated']);
    expect(frameworkTargets('expired')).toEqual([]);
    expect(frameworkTargets('terminated')).toEqual([]);
  });

  it('the called-off share stays between nothing and everything', () => {
    expect(calledOffShare({ max_value: '2500000.00', call_off_value: '625000.00' })).toBe(0.25);
    expect(calledOffShare({ max_value: '100', call_off_value: '250' })).toBe(1);
    expect(calledOffShare({ max_value: '0', call_off_value: '10' })).toBe(0);
  });
});

describe('labels', () => {
  const known = new Set(['procurement_concept.catalogue.procedure.open']);
  const ctx: LabelContext = { t: enT, language: 'de-AT', exists: (k) => known.has(k) };

  it('names a catalogue item by its key, then by its own texts, then by the code', () => {
    expect(catalogueName(ctx, 'procedure', { code: 'open', name_key: 'procurement_concept.catalogue.procedure.open' })).toBe('Open procedure');
    expect(catalogueName(ctx, 'procedure', 'open')).toBe('Open procedure');
    expect(catalogueName(ctx, 'procedure', { code: 'house_rule', labels: { de: 'Hausverfahren', en: 'House procedure' } })).toBe('Hausverfahren');
    expect(catalogueName(ctx, 'criterion', 'local_presence')).toBe('Local presence');
    expect(catalogueName(ctx, 'procedure', null)).toBe('');
  });

  it('never shows a raw code for an unknown vocabulary entry', () => {
    expect(vocab(enT, PACKAGE_STATE, 'procedure_set')).toBe('Procedure set');
    expect(vocab(enT, PACKAGE_STATE, 'handed_over' as never)).toBe('Handed over');
    expect(humanizeCode('supply_and_install')).toBe('Supply and install');
  });

  it('reads a refusal and a finding as a sentence', () => {
    expect(errorText(enT, 'concept_locked')).toBe('The concept is under review or approved. Return or reopen it to change the plan.');
    expect(findingText(enT, blockingFinding)).toBe('Package without procedure plan');
  });
});
