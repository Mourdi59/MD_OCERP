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
  conceptInput,
  conceptSteps,
  editVerdict,
  gateVerdict,
  frameworkProblems,
  hasProposal,
  isConfirmed,
  packageDraft,
  executionVehicle,
  packageMove,
  packageProblems,
  parseAmount,
  profileProblems,
  publicClientTypes,
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
  LOCKED,
  NO_RIGHTS,
  agreementPackage,
  blockingFinding,
  can,
  concept,
  packageCan,
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
    const c = concept({ can: NO_RIGHTS });
    expect(editVerdict(c)).toBe('not_procurement_owner');
    expect(steerVerdict(c)).toBe('not_procurement_owner');
  });

  it('says the plan is locked while it is reviewed or approved', () => {
    const c = concept({ state: 'in_review', can: LOCKED });
    expect(editVerdict(c)).toBe('concept_locked');
    expect(steerVerdict(c)).toBeNull();
  });

  it('points a binding concept to the change request', () => {
    const c = concept({ state: 'binding', can: can({ edit_plan: 'binding_requires_change_request' }) });
    expect(editVerdict(c)).toBe('binding_requires_change_request');
  });

  it('takes the reason from the server and never from the state', () => {
    // A draft the server refuses stays refused; an approved one it allows stays allowed.
    expect(editVerdict(concept({ state: 'draft', can: can({ edit_plan: 'concept_locked' }) }))).toBe('concept_locked');
    expect(editVerdict(concept({ state: 'approved', can: can() }))).toBeNull();
  });

  it('falls back to a sentence when the server refuses without a code', () => {
    const c = concept({ can: { ...can(), steer: { allowed: false, reason: null } } });
    expect(steerVerdict(c)).toBe('not_procurement_owner');
  });

  it('keeps the release gate closed for who may not name it', () => {
    expect(gateVerdict(concept())).toBeNull();
    expect(gateVerdict(concept({ can: can({ set_gate_fields: 'manage_required' }) }))).toBe('manage_required');
    expect(gateVerdict(concept({ can: LOCKED }))).toBe('gate_fields_frozen');
  });
});

describe('conceptSteps', () => {
  it('a draft and a reopened concept can be submitted', () => {
    expect(conceptSteps(concept()).map((s) => s.action)).toEqual(['submit']);
    expect(conceptSteps(concept({ state: 'reopened' })).map((s) => s.action)).toEqual(['submit']);
  });

  it('a submitted concept can only be returned: approval belongs to the governance gate', () => {
    const steps = conceptSteps(concept({ state: 'in_review', can: LOCKED }));
    expect(steps.map((s) => s.action)).toEqual(['return']);
    expect(steps[0]!.verdict).toBeNull();
  });

  it('the step carries the refusal the server gave for it', () => {
    expect(conceptSteps(concept({ can: NO_RIGHTS }))[0]!.verdict).toBe('not_procurement_owner');
    expect(conceptSteps(concept({ state: 'in_review', can: NO_RIGHTS }))[0]!.verdict).toBe('not_procurement_owner');
  });

  it('an approved and a binding concept offer no hand move', () => {
    expect(conceptSteps(concept({ state: 'approved' }))).toEqual([]);
    expect(conceptSteps(concept({ state: 'binding' }))).toEqual([]);
  });
});

describe('the concept form', () => {
  const eu = concept().jurisdictions[1];

  it('offers a public client every client type but the one the law keeps for private clients', () => {
    expect(publicClientTypes(eu)).toEqual(['central', 'sub_central', 'utility']);
    expect(publicClientTypes(concept().jurisdictions[0])).toEqual([]);
    expect(publicClientTypes(undefined)).toEqual([]);
    expect(publicClientTypes({ code: 'x', client_types: ['a', 'own'], private_client_type: 'own' })).toEqual(['a']);
  });

  const draft = { catalogue: 'shipped:eu', jurisdiction: 'eu', public_client: true, client_type: 'central', vat_rate_pct: '19', release_gate_code: null as string | null };

  it('starts a concept with the catalogue and the rules in one request', () => {
    expect(conceptInput(null, draft)).toEqual({
      catalogue_source: 'shipped',
      catalogue_id: 'eu',
      jurisdiction: 'eu',
      public_client: true,
      client_type: 'central',
      vat_rate_pct: '19',
    });
  });

  it('sends the catalogue again only when it changed', () => {
    expect('catalogue_id' in conceptInput(concept(), draft)).toBe(false);
    expect(conceptInput(concept(), { ...draft, catalogue: 'shipped:uk' })).toMatchObject({ catalogue_source: 'shipped', catalogue_id: 'uk' });
    expect(conceptInput(concept(), { ...draft, catalogue: 'tenant:9f2c:1' })).toMatchObject({ catalogue_source: 'tenant', catalogue_id: '9f2c:1' });
  });

  it('sends the client type only for a public client, the rate as a string', () => {
    expect(conceptInput(concept(), draft)).toEqual({ jurisdiction: 'eu', public_client: true, client_type: 'central', vat_rate_pct: '19' });
    expect(conceptInput(concept(), { ...draft, public_client: false })).toEqual({ jurisdiction: 'eu', public_client: false, vat_rate_pct: '19' });
  });

  it('sends the release gate only when it changed and the reader may set it', () => {
    expect(conceptInput(concept(), { ...draft, release_gate_code: 'g2' }).release_gate_code).toBe('g2');
    expect('release_gate_code' in conceptInput(concept({ release_gate_code: 'g2' }), { ...draft, release_gate_code: 'g2' })).toBe(false);
    expect('release_gate_code' in conceptInput(concept(), draft)).toBe(false);
    // Clearing it goes back to the gate the governance plan names.
    expect(conceptInput(concept({ release_gate_code: 'g2' }), { ...draft, release_gate_code: '' }).release_gate_code).toBe('');
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

describe('package moves follow the flags of the row', () => {
  it('an allowed move is offered and open', () => {
    expect(packageMove(packageView(), 'hold')).toEqual({ show: true, verdict: null });
    expect(packageMove(packageView(), 'create_execution')).toEqual({ show: true, verdict: null });
  });

  it('a move that does not apply to the package as it stands is left out', () => {
    expect(packageMove(packageView(), 'resume')).toEqual({ show: false, verdict: 'package_not_on_hold' });
    expect(packageMove(unplannedPackage, 'hold').show).toBe(false);
    expect(packageMove(unplannedPackage, 'edit')).toEqual({ show: true, verdict: null });
    for (const move of ['edit', 'hold', 'cancel', 'create_execution'] as const) {
      expect(packageMove(agreementPackage, move).show).toBe(false);
    }
  });

  it('a move refused because of the reader or the concept stays visible with the reason', () => {
    const view = packageView({
      can: packageCan({ edit: 'concept_locked', hold: 'not_procurement_owner', create_execution: 'concept_not_approved', resume: 'package_not_on_hold' }),
    });
    expect(packageMove(view, 'edit')).toEqual({ show: true, verdict: 'concept_locked' });
    expect(packageMove(view, 'hold')).toEqual({ show: true, verdict: 'not_procurement_owner' });
    expect(packageMove(view, 'create_execution')).toEqual({ show: true, verdict: 'concept_not_approved' });
  });

  it('never works a move out from the state: the flag alone decides', () => {
    // A state that would allow a hold, and a server that refuses it.
    const refused = packageView({ can: packageCan({ all: 'not_procurement_owner' }) }, { state: 'procedure_set' });
    expect(packageMove(refused, 'hold').verdict).toBe('not_procurement_owner');
    // A state that reads closed, and a server that allows the change.
    expect(packageMove(packageView({ can: packageCan() }, { state: 'awarded' }), 'edit')).toEqual({ show: true, verdict: null });
  });

  it('a package that already has its tender vehicle does not get a second one', () => {
    const view = packageView({ can: packageCan({ create_execution: 'execution_exists' }) });
    expect(packageMove(view, 'create_execution').show).toBe(false);
  });

  it('a row without flags offers nothing', () => {
    const view = { ...packageView(), can: undefined } as unknown as ReturnType<typeof packageView>;
    expect(packageMove(view, 'edit').show).toBe(false);
  });

  it('a supply package goes out as a request for quotation, the rest as a bid package', () => {
    expect(executionVehicle(supplyPackage)).toBe('rfq');
    expect(executionVehicle(packageView())).toBe('bid_package');
  });

  it('names the release of an advance package as one pair, and clears it as one', () => {
    const original = packageDraft(packageView({}, { is_advance: true, advance_reason: 'Long lead item' }));
    expect(original.advance_release).toBe('');
    expect(toPackageInput({ ...original, advance_release: 'gate_decision:d1' }, original)).toEqual({
      advance_release_kind: 'gate_decision',
      advance_release_id: 'd1',
    });
    const released = packageDraft(packageView({}, { is_advance: true, advance_release_kind: 'condition', advance_release_id: 'c9' }));
    expect(released.advance_release).toBe('condition:c9');
    expect(toPackageInput(released, released)).toEqual({});
    expect(toPackageInput({ ...released, is_advance: false }, released)).toMatchObject({
      is_advance: false,
      advance_release_kind: null,
      advance_release_id: null,
    });
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
