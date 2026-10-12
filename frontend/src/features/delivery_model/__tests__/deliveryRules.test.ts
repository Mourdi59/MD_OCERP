// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The arithmetic, the draft checks, the button verdicts and the label
// fallbacks of the delivery model, each as a plain function.

import { describe, expect, it } from 'vitest';

import { ApiError } from '@/shared/lib/api';

import {
  canChangeCatalogue,
  canCloseReopening,
  canEditAllocations,
  canEditComparison,
  canEditPlan,
  canManage,
  canPropose,
  canReopen,
  canWithdraw,
  personOnly,
  roleAllows,
} from '../access';
import { deliveryErrorCode, deliveryServerMessage, deliveryViolations } from '../api';
import { catalogueSentence, catalogueText, errorText, findingText, formName, humanizeCode, partyNamer, vocab, MODEL_STATUS, type LabelContext } from '../labels';
import {
  allocationProblems,
  allocationsFrozen,
  cellState,
  changedFields,
  comparisonEditable,
  filterPackages,
  fromHundredths,
  leadingOptionId,
  matrixSummary,
  missingScores,
  nextOfiStatus,
  nextPackageStatuses,
  ofiProblems,
  packageProblems,
  packageTree,
  proposeProblems,
  shownAllocation,
  sumHundredths,
  toAllocationInput,
  toHundredths,
  weightsProblem,
} from '../rules';
import { allocation, allocationItem, comparison, form, model, option, parties, pkg } from './fixtures';

const echo = (key: string, opts?: Record<string, unknown>) => (opts?.defaultValue as string | undefined) ?? key;
const ctx = (known: Record<string, string> = {}, language = 'en'): LabelContext => ({
  t: (key, opts) => known[key] ?? echo(key, opts),
  language,
  exists: (key) => key in known,
});

describe('decimal strings', () => {
  it('reads weights as hundredths without floats', () => {
    expect(toHundredths('15')).toBe(1500);
    expect(toHundredths('33.3')).toBe(3330);
    expect(toHundredths('33.30')).toBe(3330);
    expect(toHundredths('100.00')).toBe(10000);
    expect(toHundredths('  7.05 ')).toBe(705);
  });

  it('refuses what is not a plain non-negative decimal', () => {
    for (const bad of ['', 'abc', '-5', '1e2', '1,5', '3.855', null, undefined]) expect(toHundredths(bad)).toBeNull();
  });

  it('adds thirds to exactly 100, which floats do not', () => {
    expect(sumHundredths(['33.3', '33.3', '33.4'])).toBe(10000);
    expect(0.1 + 0.2).not.toBe(0.3);
    expect(sumHundredths(['0.1', '0.2'])).toBe(30);
    expect(sumHundredths(['10', 'x'])).toBeNull();
  });

  it('writes hundredths back without trailing zeros', () => {
    expect(fromHundredths(10000)).toBe('100');
    expect(fromHundredths(3350)).toBe('33.5');
    expect(fromHundredths(705)).toBe('7.05');
    expect(fromHundredths(0)).toBe('0');
  });
});

describe('weights', () => {
  it('accepts weights that add up to 100', () => {
    expect(weightsProblem({ a: '60', b: '40' })).toBeNull();
    expect(weightsProblem({ a: '33.3', b: '33.3', c: '33.4' })).toBeNull();
  });

  it('names a total that is not 100, in either direction', () => {
    expect(weightsProblem({ a: '60', b: '30' })).toBe('weights_not_100');
    expect(weightsProblem({ a: '60', b: '50' })).toBe('weights_not_100');
  });

  it('names an invalid weight before the total', () => {
    expect(weightsProblem({ a: 'many', b: '40' })).toBe('weight_invalid');
    expect(weightsProblem({ a: '120', b: '-20' })).toBe('weight_invalid');
    expect(weightsProblem({ a: '101' })).toBe('weight_invalid');
  });
});

describe('comparison', () => {
  it('the leading option is the highest server total', () => {
    expect(leadingOptionId(comparison().options)).toBe('o2');
  });

  it('an option that is not fully scored never leads', () => {
    expect(leadingOptionId([option('a', 'x', null), option('b', 'y', '1.20')])).toBe('b');
    expect(leadingOptionId([option('a', 'x', null)])).toBeNull();
    expect(leadingOptionId([])).toBeNull();
  });

  it('a tie goes to the option listed first and totals compare as numbers, not text', () => {
    expect(leadingOptionId([option('a', 'x', '4.2'), option('b', 'y', '4.20')])).toBe('a');
    expect(leadingOptionId([option('a', 'x', '9.5'), option('b', 'y', '10.25')])).toBe('b');
    expect(leadingOptionId([option('a', 'x', '3.8525'), option('b', 'y', '3.85')])).toBe('a');
  });

  it('counts the cells that still have no score', () => {
    expect(missingScores(comparison())).toBe(0);
    const c = comparison();
    expect(missingScores({ ...c, scores: c.scores.slice(0, 1) })).toBe(3);
  });

  it('a complete comparison with a choice and a reason has nothing left to fix', () => {
    expect(proposeProblems(comparison(), { optionId: 'o2', rationale: 'Fixed price.' })).toEqual([]);
  });

  it('lists every missing piece in the order the reader fixes it', () => {
    const c = comparison({ options: [option('o1', 'design_build', null)], weights_total: '90', scores: [] });
    expect(proposeProblems(c, { optionId: null, rationale: '  ' })).toEqual([
      'single_option_decision',
      'weights_not_100',
      'scores_incomplete',
      'option_required',
      'rationale_missing',
    ]);
  });

  it('refuses an option that is no longer in the comparison', () => {
    expect(proposeProblems(comparison(), { optionId: 'gone', rationale: 'x' })).toEqual(['chosen_option_unknown']);
  });
});

describe('risk allocation', () => {
  it('reads the state of a row', () => {
    expect(cellState(allocationItem('a', { default: null }))).toBe('empty');
    expect(cellState(allocationItem('a'))).toBe('default');
    expect(cellState(allocationItem('a', { allocation: allocation('a', { status: 'unconfirmed' }) }))).toBe('unconfirmed');
    expect(cellState(allocationItem('a', { allocation: allocation('a') }))).toBe('confirmed');
    expect(cellState(allocationItem('a', { allocation: allocation('a', { status: 'link_missing' }) }))).toBe('link_missing');
    expect(cellState(allocationItem('a', { allocation: allocation('a', { not_applicable: true, party: null }) }))).toBe('not_applicable');
  });

  it('shows the project allocation before the catalogue default', () => {
    const edited = allocationItem('a', { allocation: allocation('a', { party: 'owner', basis: 'insurance' }) });
    expect(shownAllocation(edited)).toEqual({ party: 'owner', basis: 'insurance', shares: {} });
    expect(shownAllocation(allocationItem('a'))).toEqual({ party: 'contractor', basis: 'contract', shares: {} });
    expect(shownAllocation(allocationItem('a', { default: null }))).toBeNull();
  });

  it('summarises what is confirmed, what is open and what can go to the register', () => {
    const summary = matrixSummary([
      allocationItem('a', { allocation: allocation('a', { risk_item_ids: ['r1'] }) }),
      allocationItem('b', { allocation: allocation('b') }),
      allocationItem('c', { allocation: allocation('c', { status: 'unconfirmed' }) }),
      allocationItem('d', { findings: [{ code: 'risk_unallocated', severity: 'error', ref: 'd' }] }),
      allocationItem('e', {
        allocation: allocation('e', { not_applicable: true, party: null }),
        findings: [{ code: 'allocation_deviates_from_default', severity: 'warning', ref: 'e' }],
      }),
    ]);
    expect(summary).toEqual({ total: 5, confirmed: 3, toConfirm: 2, errors: 1, warnings: 1, seedable: 1 });
  });

  const draft = (over: Partial<Parameters<typeof allocationProblems>[0]> = {}) => ({
    party: 'contractor' as string | null,
    basis: 'contract' as const,
    shares: {} as Record<string, string>,
    rationale: '',
    not_applicable: false,
    ...over,
  });

  it('a single party needs nothing more', () => {
    expect(allocationProblems(draft())).toEqual([]);
  });

  it('needs a party unless the risk does not apply', () => {
    expect(allocationProblems(draft({ party: null }))).toEqual(['party_required']);
  });

  it('not applicable needs a reason and nothing else', () => {
    expect(allocationProblems(draft({ not_applicable: true, party: null }))).toEqual(['not_applicable_needs_rationale']);
    expect(allocationProblems(draft({ not_applicable: true, party: null, rationale: 'No tunnel on this project.' }))).toEqual([]);
  });

  it('a shared risk needs two parties whose shares add up to 100', () => {
    const shared = (shares: Record<string, string>) => draft({ party: 'shared', basis: 'shared_pain_gain', shares });
    expect(allocationProblems(shared({ owner: '60', contractor: '40' }))).toEqual([]);
    expect(allocationProblems(shared({ owner: '100' }))).toEqual(['shared_needs_two_parties']);
    expect(allocationProblems(shared({ owner: '60', contractor: '30' }))).toEqual(['shared_risk_not_100']);
    expect(allocationProblems(shared({ owner: '60', contractor: '0' }))).toEqual(['share_invalid']);
    expect(allocationProblems(shared({ owner: 'half', contractor: '50' }))).toEqual(['share_invalid']);
    expect(allocationProblems(shared({ owner: '', contractor: '' }))).toEqual(['shared_needs_two_parties']);
  });

  it('a shared risk is never shared simply by contract', () => {
    const byContract = draft({ party: 'shared', basis: 'contract', shares: { owner: '50', contractor: '50' } });
    expect(allocationProblems(byContract)).toEqual(['shared_needs_basis']);
    expect(allocationProblems({ ...byContract, basis: 'ground_baseline' })).toEqual([]);
    // the basis is free for a risk one party carries alone
    expect(allocationProblems(draft({ basis: 'insurance' }))).toEqual([]);
  });

  it('sends shares only with a shared risk and drops empty share fields', () => {
    expect(toAllocationInput(draft({ party: 'owner', shares: { owner: '60' }, rationale: ' why ' }))).toMatchObject({
      party: 'owner',
      shares: {},
      rationale: 'why',
    });
    expect(toAllocationInput(draft({ party: 'shared', shares: { owner: '60', contractor: ' 40 ', insurer: '' } })).shares).toEqual({
      owner: '60',
      contractor: '40',
    });
    expect(toAllocationInput(draft({ not_applicable: true, party: 'owner', shares: { owner: '1' }, rationale: 'n/a' }))).toMatchObject({
      party: null,
      shares: {},
      not_applicable: true,
    });
  });
});

describe('packages and owner-furnished items', () => {
  it('puts children right under their parent and keeps plan order', () => {
    const rows = packageTree([pkg('a'), pkg('b'), pkg('a1', { parent_id: 'a' }), pkg('a2', { parent_id: 'a' }), pkg('a1x', { parent_id: 'a1' })]);
    expect(rows.map((r) => [r.pkg.id, r.depth])).toEqual([
      ['a', 0],
      ['a1', 1],
      ['a1x', 2],
      ['a2', 1],
      ['b', 0],
    ]);
  });

  it('never hides a package whose parent is missing or part of a cycle', () => {
    expect(packageTree([pkg('a', { parent_id: 'gone' })]).map((r) => r.pkg.id)).toEqual(['a']);
    const cycle = packageTree([pkg('a', { parent_id: 'b' }), pkg('b', { parent_id: 'a' })]);
    expect(cycle.map((r) => r.pkg.id).sort()).toEqual(['a', 'b']);
  });

  it('answers who designs, builds or supplies, without cancelled packages', () => {
    const plan = [
      pkg('d', { designs: true, builds: false }),
      pkg('b'),
      pkg('x', { designs: true, effective_status: 'cancelled' }),
    ];
    expect(filterPackages(plan, 'designs').map((p) => p.id)).toEqual(['d']);
    expect(filterPackages(plan, 'builds').map((p) => p.id)).toEqual(['b']);
    expect(filterPackages(plan, 'supplies')).toEqual([]);
    expect(filterPackages(plan, 'all')).toHaveLength(3);
  });

  it('offers the stored state changes the server allows', () => {
    expect(nextPackageStatuses('planned')).toEqual(['closed', 'cancelled']);
    expect(nextPackageStatuses('closed')).toEqual(['planned']);
    expect(nextPackageStatuses('cancelled')).toEqual(['planned']);
  });

  it('walks an item forward one step, and only after it has a route', () => {
    expect(nextOfiStatus('identified')).toBeNull();
    expect(nextOfiStatus('route_set')).toBe('ordered');
    expect(nextOfiStatus('ordered')).toBe('delivered');
    expect(nextOfiStatus('delivered')).toBe('handed_to_installer');
    expect(nextOfiStatus('handed_to_installer')).toBeNull();
  });

  it('checks a new package code and title, and leaves the code of an existing one alone', () => {
    expect(packageProblems({ code: '', title: '' }, true)).toEqual(['code_required', 'title_required']);
    expect(packageProblems({ code: 'P 01', title: 'Shell' }, true)).toEqual(['code_invalid']);
    expect(packageProblems({ code: '-P', title: 'Shell' }, true)).toEqual(['code_invalid']);
    expect(packageProblems({ code: 'P-01.a_b', title: 'Shell' }, true)).toEqual([]);
    expect(packageProblems({ code: '', title: 'Shell' }, false)).toEqual([]);
  });

  it('an item installed by a package must name the package', () => {
    const base = { code: 'OFI-1', description: 'Lift', install_by: 'package' as const, package_id: null };
    expect(ofiProblems(base, true)).toEqual(['installer_required']);
    expect(ofiProblems({ ...base, package_id: 'p1' }, true)).toEqual([]);
    expect(ofiProblems({ ...base, install_by: 'owner' }, true)).toEqual([]);
    expect(ofiProblems({ ...base, description: ' ', install_by: 'owner' }, true)).toEqual(['description_required']);
  });
});

describe('states', () => {
  it('the comparison is editable only before a proposal and after a reopening', () => {
    expect((['draft', 'under_evaluation', 'reopened'] as const).every(comparisonEditable)).toBe(true);
    expect((['proposed', 'approved', 'binding'] as const).some(comparisonEditable)).toBe(false);
  });

  it('allocations stay editable while proposed and freeze once approved', () => {
    expect(allocationsFrozen('proposed')).toBe(false);
    expect(allocationsFrozen('approved')).toBe(true);
    expect(allocationsFrozen('binding')).toBe(true);
  });
});

describe('button verdicts', () => {
  const viewer = (role: string | null) => ({ userId: 'u1', role });

  it('ranks roles like the backend, aliases included, and denies an absent or unknown role', () => {
    expect(roleAllows('viewer', 'read')).toBe(true);
    expect(roleAllows('viewer', 'edit')).toBe(false);
    expect(roleAllows('editor', 'edit')).toBe(true);
    expect(roleAllows('estimator', 'edit')).toBe(true);
    expect(roleAllows('editor', 'manage')).toBe(false);
    expect(roleAllows('Manager', 'manage')).toBe(true);
    expect(roleAllows('admin', 'manage')).toBe(true);
    expect(roleAllows(null, 'read')).toBe(false);
    expect(roleAllows('wizard', 'read')).toBe(false);
  });

  it('before a model exists only the role is known, and only a manager starts one', () => {
    expect(canManage(viewer('editor'))).toBe('role_manage');
    expect(canManage(viewer('manager'))).toBeNull();
  });

  it('every action reads the answer the server sent with the model', () => {
    expect(canEditComparison(model())).toBeNull();
    expect(canEditComparison(model({}, 'viewer'))).toBe('permission_missing');
    expect(canEditComparison(model({ status: 'proposed' }, 'editor'))).toBe('model_not_editable');
    expect(canPropose(model({}, 'editor'))).toBe('permission_missing');
    expect(canPropose(model({ status: 'reopened' }))).toBeNull();
    expect(canPropose(model({ status: 'proposed' }))).toBe('decision_pending');
    expect(canWithdraw(model({ status: 'proposed' }))).toBeNull();
    expect(canWithdraw(model())).toBe('decision_not_pending');
    expect(canReopen(model({ status: 'binding' }))).toBeNull();
    expect(canReopen(model({ status: 'approved' }))).toBe('model_not_binding');
    expect(canCloseReopening(model({ status: 'reopened' }))).toBeNull();
    expect(canCloseReopening(model())).toBe('reopening_not_open');
  });

  it('a reason the server gives is kept as it is, not replaced by a guess from the role', () => {
    const m = model();
    m.can.edit = { allowed: false, reason: 'not_area_owner' };
    m.can.reopen = { allowed: false, reason: 'change_request_required' };
    expect(canEditComparison(m)).toBe('not_area_owner');
    expect(canEditPlan(m)).toBe('not_area_owner');
    expect(canReopen(m)).toBe('change_request_required');
  });

  it('a flag that did not arrive denies', () => {
    const m = { ...model(), can: {} as ReturnType<typeof model>['can'] };
    expect(canPropose(m)).toBe('permission_missing');
    expect(canEditPlan(m)).toBe('permission_missing');
    expect(canPropose({ can: { ...model().can, propose: { allowed: false, reason: null } } })).toBe('permission_missing');
  });

  it('allocations, packages and items stay open while a decision is proposed and close once it is approved', () => {
    expect(canEditPlan(model({ status: 'proposed' }, 'editor'))).toBeNull();
    expect(canEditAllocations(model({ status: 'proposed' }))).toBeNull();
    expect(canEditPlan(model({ status: 'approved' }))).toBe('model_not_editable');
    expect(canEditPlan(model({ status: 'binding' }))).toBe('model_not_editable');
    expect(canEditPlan(model({ status: 'proposed' }, 'viewer'))).toBe('permission_missing');
  });

  it('pinning another catalogue needs no carrier document', () => {
    const m = model();
    m.can.propose = { allowed: false, reason: 'carrier_missing' };
    expect(canPropose(m)).toBe('carrier_missing');
    expect(canChangeCatalogue(m)).toBeNull();
    expect(canChangeCatalogue(model({ status: 'proposed' }))).toBe('decision_pending');
    expect(canChangeCatalogue(model({}, 'editor'))).toBe('permission_missing');
  });

  it('tells a reason about the person from a reason about the state', () => {
    expect(personOnly('not_area_owner')).toBe('not_area_owner');
    expect(personOnly('permission_missing')).toBe('permission_missing');
    expect(personOnly('model_not_editable')).toBeNull();
    expect(personOnly(null)).toBeNull();
  });
});

describe('changedFields', () => {
  const before = { title: 'Shell', parent_id: 'p0' as string | null, need_date: null as string | null, designs: false };

  it('carries only what changed, so an untouched empty field never travels as null', () => {
    expect(changedFields(before, { ...before })).toEqual({});
    expect(changedFields(before, { ...before, title: 'Shell and core' })).toEqual({ title: 'Shell and core' });
  });

  it('a cleared field travels as an explicit null', () => {
    const changes = changedFields(before, { ...before, parent_id: null });
    expect(changes).toEqual({ parent_id: null });
    expect('parent_id' in changes).toBe(true);
  });

  it('sees a flag flip and a date that was set', () => {
    expect(changedFields(before, { ...before, designs: true, need_date: '2027-01-15' })).toEqual({ designs: true, need_date: '2027-01-15' });
  });
});

describe('labels', () => {
  it('names a shipped item by its key, a tenant item by its texts, and anything else by its code', () => {
    const known = { 'k.name': 'Design and build' };
    expect(catalogueText(ctx(known), { key: 'k.name', code: 'design_build' })).toBe('Design and build');
    expect(catalogueText(ctx(), { key: 'k.name', texts: { en: 'Own form', de: 'Eigene Form' }, code: 'own' })).toBe('Own form');
    expect(catalogueText(ctx({}, 'de-AT'), { texts: { en: 'Own form', de: 'Eigene Form' }, code: 'own' })).toBe('Eigene Form');
    expect(catalogueText(ctx({}, 'fr'), { texts: { de: 'Eigene Form' }, code: 'own' })).toBe('Eigene Form');
    expect(catalogueText(ctx(), { key: 'missing.key', code: 'cm_at_risk' })).toBe('Cm at risk');
  });

  it('never shows a raw key for a missing sentence', () => {
    expect(catalogueSentence(ctx(), 'missing.key')).toBe('');
    expect(catalogueSentence(ctx(), null)).toBe('');
    expect(catalogueSentence(ctx({ 'k.d': 'One contract.' }), 'k.d')).toBe('One contract.');
  });

  it('names a form from the form object and falls back to the code', () => {
    const f = form('design_build', { name_key: 'k.name' });
    expect(formName(ctx({ 'k.name': 'Design and build' }), f, 'design_build')).toBe('Design and build');
    expect(formName(ctx(), null, 'design_build')).toBe('Design build');
    expect(formName(ctx(), null, null)).toBe('');
  });

  it('names parties from the list a response carries', () => {
    const name = partyNamer(ctx({ 'delivery_model.catalogue.neutral.party.owner': 'Owner' }), parties());
    expect(name('owner')).toBe('Owner');
    expect(name('insurer')).toBe('Insurer');
    expect(name(null)).toBe('');
  });

  it('writes an unknown vocabulary code in words', () => {
    expect(vocab(echo, MODEL_STATUS, 'binding')).toBe('Binding');
    expect(vocab(echo, MODEL_STATUS, 'on_ice' as never)).toBe('On ice');
    expect(vocab(echo, MODEL_STATUS, null)).toBe('');
    expect(humanizeCode('ground_conditions')).toBe('Ground conditions');
  });

  it('a refusal reads as a sentence: known code, then the server message, then the code in words', () => {
    expect(errorText(echo, 'weights_not_100')).toBe('Criterion weights must add up to 100.');
    expect(errorText(echo, 'brand_new_code', 'The server said so.')).toBe('The server said so.');
    expect(errorText(echo, 'brand_new_code')).toBe('Brand new code');
  });

  it('a finding carries the form rule behind it', () => {
    const f = findingText(echo, { code: 'allocation_inconsistent_with_form', params: { reason: 'contractor_designs' } });
    expect(f.text).toBe('This allocation does not fit the chosen form.');
    expect(f.reason).toBe('Under this form the contractor designs, so design risk sits with the contractor.');
    expect(findingText(echo, { code: 'ofi_without_route' })).toEqual({ text: 'Set a procurement route first.', reason: '' });
    expect(findingText(echo, { code: 'packages_inconsistent_with_form', params: { reason: 'never_heard' } }).reason).toBe('');
  });
});

describe('refusals from the API', () => {
  const refused = new ApiError(422, 'Unprocessable', {
    detail: {
      code: 'form_change_impacts_packages',
      message: 'Packages need a disposition.',
      violations: [{ code: 'disposition_missing', severity: 'error', ref: 'P-01' }],
    },
  });

  it('reads the code, the message and every violation', () => {
    expect(deliveryErrorCode(refused)).toBe('form_change_impacts_packages');
    expect(deliveryServerMessage(refused)).toBe('Packages need a disposition.');
    expect(deliveryViolations(refused)).toEqual([{ code: 'disposition_missing', severity: 'error', ref: 'P-01' }]);
  });

  it('answers nothing for a failure that is not a module refusal', () => {
    for (const err of [new Error('offline'), new ApiError(500, 'Server Error', { detail: 'database unavailable' }), new ApiError(422, 'x', { detail: [{ loc: ['body'] }] })]) {
      expect(deliveryErrorCode(err)).toBeNull();
      expect(deliveryServerMessage(err)).toBeNull();
      expect(deliveryViolations(err)).toEqual([]);
    }
  });
});
