// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// The plain logic behind the procurement screens: which button a state
// offers, why a button is off, what a form still misses, and how a form
// becomes a request body. No React here, so every rule is a unit test.
//
// Permissions are never worked out here. Whether the reader may act comes
// from the `can` flags the server sends with the concept; this file only
// turns a `false` into the sentence that explains it.

import type {
  CandidateInput,
  CandidateList,
  CandidateSource,
  Concept,
  ConceptAction,
  Finding,
  FrameworkInput,
  FrameworkLedger,
  FrameworkPatch,
  FrameworkState,
  FrameworkTarget,
  PackageInput,
  PackageKind,
  PackageView,
  ProfileCriterion,
  ProfileInput,
  ScheduleRow,
  ScoreInput,
  SoundingInput,
  SplitBasis,
  TenderBasis,
} from './api';
import type { KeyText } from './labels';

/** Null when the action is allowed, else the server error code whose sentence explains the refusal. */
export type Verdict = string | null;

/** Changing the plan (packages, concept settings): the server's `can.edit`. */
export function editVerdict(concept: Concept): Verdict {
  if (concept.can.edit) return null;
  if (!concept.can.steer) return 'not_procurement_owner';
  return concept.state === 'binding' ? 'binding_requires_change_request' : 'concept_locked';
}

/** Steering moves that stay open while the plan is locked (hold, short list, milestones): `can.steer`. */
export function steerVerdict(concept: Concept): Verdict {
  return concept.can.steer ? null : 'not_procurement_owner';
}

export interface ConceptStep {
  action: ConceptAction;
  verdict: Verdict;
  primary: boolean;
}

/** The lifecycle steps the current state offers, in the order they are shown. */
export function conceptSteps(concept: Concept): ConceptStep[] {
  const steer = steerVerdict(concept);
  switch (concept.state) {
    case 'draft':
    case 'reopened':
      return [{ action: 'submit', verdict: steer, primary: true }];
    case 'in_review':
      return [
        { action: 'approve', verdict: concept.can.approve ? null : 'not_procurement_owner', primary: true },
        { action: 'return', verdict: steer, primary: false },
      ];
    case 'approved':
      return [{ action: 'reopen', verdict: steer, primary: false }];
    default:
      // Binding: the frame document rules, and it changes through a change request.
      return [];
  }
}

export function splitFindings(findings: Finding[]): { blocking: Finding[]; warnings: Finding[] } {
  return {
    blocking: findings.filter((f) => f.blocks_approval),
    warnings: findings.filter((f) => !f.blocks_approval),
  };
}

/* ── Amounts ──────────────────────────────────────────────────────────── */

/**
 * What a person typed as an amount, as the decimal string the API takes, or
 * null when it is not an amount. Accepts grouping by space or apostrophe and
 * either decimal separator ("1 250 000,50", "1,250,000.50"). Never goes
 * through a float, so no cent is lost on the way.
 */
export function parseAmount(input: string): string | null {
  let s = input.replace(/[\s  ']/g, '');
  if (!s) return null;
  const comma = s.lastIndexOf(',');
  const dot = s.lastIndexOf('.');
  if (comma >= 0 && dot >= 0) {
    const decimal = comma > dot ? ',' : '.';
    const grouping = decimal === ',' ? '.' : ',';
    s = s.split(grouping).join('').replace(decimal, '.');
  } else if (comma >= 0) {
    s = /^\d{1,3}(,\d{3})+$/.test(s) ? s.split(',').join('') : s.replace(',', '.');
  } else if (/^\d{1,3}(\.\d{3}){2,}$/.test(s)) {
    s = s.split('.').join('');
  }
  return /^\d+(\.\d+)?$/.test(s) ? s : null;
}

function sameAmount(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return !a && !b;
  const norm = (v: string) => (v.includes('.') ? v.replace(/0+$/, '').replace(/\.$/, '') : v).replace(/^0+(?=\d)/, '');
  return norm(a) === norm(b);
}

/* ── Packages ─────────────────────────────────────────────────────────── */

export interface PackageDraft {
  estimated_value: string;
  currency: string;
  procedure_code: string;
  tender_basis: TenderBasis | '';
  split_basis: SplitBasis;
  lot_group: string;
  small_lot_exemption: boolean;
  is_advance: boolean;
  advance_reason: string;
  need_date: string;
  lead_time_days: string;
  framework_agreement_id: string;
  prequal_profile_id: string;
  notes: string;
}

export function packageDraft(view: PackageView): PackageDraft {
  const a = view.award;
  return {
    estimated_value: a?.estimated_value ?? '',
    currency: a?.currency ?? '',
    procedure_code: a?.procedure_code ?? '',
    tender_basis: a?.tender_basis ?? '',
    split_basis: a?.split_basis ?? 'whole',
    lot_group: a?.lot_group ?? '',
    small_lot_exemption: a?.small_lot_exemption ?? false,
    is_advance: a?.is_advance ?? false,
    advance_reason: a?.advance_reason ?? '',
    need_date: a?.need_date ?? '',
    lead_time_days: a?.lead_time_days == null ? '' : String(a.lead_time_days),
    framework_agreement_id: a?.framework_agreement_id ?? '',
    prequal_profile_id: a?.prequal_profile_id ?? '',
    notes: a?.notes ?? '',
  };
}

export type PackageProblem = 'value_invalid' | 'currency_invalid' | 'advance_without_reason' | 'lead_time_invalid';

export const PACKAGE_PROBLEM: Record<PackageProblem, KeyText> = {
  value_invalid: ['procurement_concept.ui.problem.value_invalid', 'The estimated value is not an amount.'],
  currency_invalid: [
    'procurement_concept.ui.problem.currency_invalid',
    'Give the currency as a three-letter code, for example EUR.',
  ],
  advance_without_reason: ['procurement_concept.errors.advance_without_reason', 'An advance package needs a reason.'],
  lead_time_invalid: [
    'procurement_concept.ui.problem.lead_time_invalid',
    'The lead time is a whole number of days between 0 and 1500.',
  ],
};

export function packageProblems(d: PackageDraft): PackageProblem[] {
  const out: PackageProblem[] = [];
  const hasValue = d.estimated_value.trim() !== '';
  if (hasValue && parseAmount(d.estimated_value) === null) out.push('value_invalid');
  const cur = d.currency.trim();
  if ((cur && !/^[A-Za-z]{3}$/.test(cur)) || (hasValue && !cur)) out.push('currency_invalid');
  if (d.is_advance && !d.advance_reason.trim()) out.push('advance_without_reason');
  const lead = d.lead_time_days.trim();
  if (lead && (!/^\d+$/.test(lead) || Number(lead) > 1500)) out.push('lead_time_invalid');
  return out;
}

/**
 * The request body for a package: only what the reader changed. The server
 * keeps every field that is absent, so an untouched field is never sent back.
 */
export function toPackageInput(d: PackageDraft, original: PackageDraft): PackageInput {
  const out: PackageInput = {};
  if (!sameAmount(parseAmount(d.estimated_value), parseAmount(original.estimated_value))) {
    out.estimated_value = parseAmount(d.estimated_value);
  }
  const cur = d.currency.trim().toUpperCase();
  if (cur && cur !== original.currency.trim().toUpperCase()) out.currency = cur;
  if (d.procedure_code !== original.procedure_code) out.procedure_code = d.procedure_code || null;
  if (d.tender_basis !== original.tender_basis) out.tender_basis = d.tender_basis || null;
  if (d.split_basis !== original.split_basis) out.split_basis = d.split_basis;
  if (d.lot_group.trim() !== original.lot_group.trim()) out.lot_group = d.lot_group.trim();
  if (d.small_lot_exemption !== original.small_lot_exemption) out.small_lot_exemption = d.small_lot_exemption;
  if (d.is_advance !== original.is_advance) out.is_advance = d.is_advance;
  if (d.advance_reason.trim() !== original.advance_reason.trim()) out.advance_reason = d.advance_reason.trim();
  if (d.need_date !== original.need_date) out.need_date = d.need_date || null;
  if (d.lead_time_days.trim() !== original.lead_time_days.trim()) {
    out.lead_time_days = d.lead_time_days.trim() === '' ? null : Number(d.lead_time_days.trim());
  }
  if (d.framework_agreement_id !== original.framework_agreement_id) {
    out.framework_agreement_id = d.framework_agreement_id || null;
  }
  if (d.prequal_profile_id !== original.prequal_profile_id) out.prequal_profile_id = d.prequal_profile_id || null;
  if (d.notes.trim() !== original.notes.trim()) out.notes = d.notes.trim();
  return out;
}

export interface PackageMoves {
  /** False for a kind that is not procured, and once the package is in tender, awarded or cancelled. */
  edit: boolean;
  hold: boolean;
  resume: boolean;
  cancel: boolean;
  /** The tender vehicle this package would get, or null when none can be created now. */
  execution: 'bid_package' | 'rfq' | null;
  /** The package has procurement attributes, so candidates can be kept for it. */
  candidates: boolean;
}

const SUPPLY_KINDS: PackageKind[] = ['supply', 'supply_and_install'];

/** What the state of a package offers. Who may do it is the server's call (`can`). */
export function packageMoves(view: PackageView): PackageMoves {
  const state = view.award?.state;
  const procured = view.package_kind !== null;
  const open = state === 'planned' || state === 'procedure_set' || state === 'shortlisted';
  return {
    edit: procured && state !== 'in_tender' && state !== 'awarded' && state !== 'cancelled',
    hold: open,
    resume: state === 'on_hold',
    cancel: !!state && state !== 'awarded' && state !== 'cancelled',
    execution:
      procured && (state === 'procedure_set' || state === 'shortlisted') && !view.contract_package.execution_link
        ? SUPPLY_KINDS.includes(view.package_kind as PackageKind)
          ? 'rfq'
          : 'bid_package'
        : null,
    candidates: !!view.award,
  };
}

/* ── Prequalification ─────────────────────────────────────────────────── */

/** Hundredths, so 33.33 + 33.33 + 33.34 adds up to exactly 100. */
function hundredths(value: string): number {
  const amount = parseAmount(value);
  return amount === null ? Number.NaN : Math.round(Number(amount) * 100);
}

/** The sum of the weights of the scored criteria, as a display string ("100", "87.5"). */
export function weightsTotal(criteria: Array<Pick<ProfileCriterion, 'kind' | 'weight'>>): string {
  const sum = criteria.filter((c) => c.kind === 'scored').reduce((acc, c) => acc + (hundredths(c.weight) || 0), 0);
  return String(sum / 100);
}

export interface ProfileDraft {
  name: string;
  pass_mark: string;
  validity_months: string;
  /** Selected criteria by code, with the weight typed for a scored one. */
  criteria: Array<{ code: string; kind: 'pass_fail' | 'scored'; weight: string }>;
}

export type ProfileProblem = 'name_required' | 'no_criteria' | 'weights_not_100' | 'pass_mark_invalid';

export const PROFILE_PROBLEM: Record<ProfileProblem, KeyText> = {
  name_required: ['procurement_concept.ui.problem.profile_name_required', 'Give the profile a name.'],
  no_criteria: ['procurement_concept.ui.problem.no_criteria', 'Choose at least one criterion.'],
  weights_not_100: [
    'procurement_concept.errors.prequal_weights_not_100',
    'The weights of the scored criteria must add up to 100.',
  ],
  pass_mark_invalid: ['procurement_concept.ui.problem.pass_mark_invalid', 'The pass mark is a number from 0 to 100.'],
};

export function profileProblems(d: ProfileDraft): ProfileProblem[] {
  const out: ProfileProblem[] = [];
  if (!d.name.trim()) out.push('name_required');
  if (d.criteria.length === 0) out.push('no_criteria');
  const scored = d.criteria.filter((c) => c.kind === 'scored');
  if (scored.length > 0) {
    const sum = scored.reduce((acc, c) => acc + hundredths(c.weight), 0);
    if (sum !== 10000) out.push('weights_not_100');
  }
  const mark = hundredths(d.pass_mark || '0');
  if (Number.isNaN(mark) || mark > 10000) out.push('pass_mark_invalid');
  return out;
}

export function toProfileInput(d: ProfileDraft, packageId: string | null): ProfileInput {
  return {
    package_id: packageId,
    name: d.name.trim(),
    criteria: d.criteria.map((c) => ({
      code: c.code,
      weight: c.kind === 'scored' ? (parseAmount(c.weight) ?? '0') : '0',
    })),
    pass_mark: parseAmount(d.pass_mark || '0') ?? '0',
    validity_months: Number(d.validity_months) || 12,
  };
}

export interface CandidateDraft {
  subcontractor_id: string;
  free_name: string;
  source: CandidateSource;
  list: CandidateList;
  decision_rationale: string;
  conflict_of_interest_declared: boolean;
  conflict_note: string;
}

export type CandidateProblem = 'needs_company' | 'excluded_needs_rationale' | 'short_needs_registered';

export const CANDIDATE_PROBLEM: Record<CandidateProblem, KeyText> = {
  needs_company: [
    'procurement_concept.errors.candidate_needs_company',
    'Name the company or link a subcontractor or vendor.',
  ],
  excluded_needs_rationale: [
    'procurement_concept.errors.excluded_candidate_without_rationale',
    'Give a reason for excluding the candidate.',
  ],
  short_needs_registered: [
    'procurement_concept.errors.candidate_not_registered',
    'Register the company as subcontractor or vendor before short-listing it.',
  ],
};

/** `registered` covers a vendor link the form cannot edit: it keeps a vendor candidate short-listable. */
export function candidateProblems(d: CandidateDraft, registered = false): CandidateProblem[] {
  const out: CandidateProblem[] = [];
  const linked = registered || !!d.subcontractor_id;
  if (!linked && !d.free_name.trim()) out.push('needs_company');
  if (d.list === 'excluded' && !d.decision_rationale.trim()) out.push('excluded_needs_rationale');
  if (d.list === 'short' && !linked) out.push('short_needs_registered');
  return out;
}

export function toCandidateInput(d: CandidateDraft): CandidateInput {
  return {
    subcontractor_id: d.subcontractor_id || null,
    free_name: d.free_name.trim(),
    source: d.source,
    list: d.list,
    decision_rationale: d.decision_rationale.trim(),
    conflict_of_interest_declared: d.conflict_of_interest_declared,
    conflict_note: d.conflict_note.trim(),
  };
}

/** One row of the scoring form: a verdict for pass or fail, points for a scored criterion. */
export interface ScoreDraft {
  criterion_code: string;
  kind: 'pass_fail' | 'scored';
  passed: '' | 'yes' | 'no';
  score: string;
}

/** True when every typed score is a number from 0 to 100. */
export function scoresValid(rows: ScoreDraft[]): boolean {
  return rows.every((r) => {
    if (r.kind !== 'scored' || !r.score.trim()) return true;
    const v = hundredths(r.score);
    return !Number.isNaN(v) && v <= 10000;
  });
}

/** Only the rows the reader assessed. A pass or fail criterion never carries points. */
export function toScoreInputs(rows: ScoreDraft[]): ScoreInput[] {
  const out: ScoreInput[] = [];
  for (const r of rows) {
    if (r.kind === 'pass_fail') {
      if (r.passed) out.push({ criterion_code: r.criterion_code, passed: r.passed === 'yes' });
    } else if (r.score.trim()) {
      out.push({ criterion_code: r.criterion_code, score: parseAmount(r.score) });
    }
  }
  return out;
}

/* ── Market sounding ──────────────────────────────────────────────────── */

export type SoundingDraft = Omit<SoundingInput, 'lead_time_signal_days'> & { lead_time_signal_days: string };

/** Tight or insufficient capacity that names neither a mitigation nor a new split: the rule the server warns on. */
export function soundingUnmitigated(d: Pick<SoundingDraft, 'capacity_signal' | 'mitigation' | 'resplit'>): boolean {
  return (d.capacity_signal === 'tight' || d.capacity_signal === 'insufficient') && !d.mitigation.trim() && !d.resplit;
}

export function soundingReady(d: SoundingDraft): boolean {
  const days = d.lead_time_signal_days.trim();
  return !!d.held_on && (!days || (/^\d+$/.test(days) && Number(days) <= 1500));
}

export function toSoundingInput(d: SoundingDraft): SoundingInput {
  return {
    ...d,
    trade: d.trade.trim(),
    findings: d.findings.trim(),
    mitigation: d.mitigation.trim(),
    lead_time_signal_days: d.lead_time_signal_days.trim() === '' ? null : Number(d.lead_time_signal_days.trim()),
  };
}

/* ── Award schedule ───────────────────────────────────────────────────── */

/** A proposal exists only once the package has a need date and a procedure. */
export function hasProposal(row: ScheduleRow): boolean {
  return !!row.proposed_award_date && !!row.proposed_start_date;
}

/** Both milestones are already in the project schedule. Confirming again moves their dates. */
export function isConfirmed(row: ScheduleRow): boolean {
  return !!row.start_activity_id && !!row.award_activity_id;
}

/* ── Framework agreements ─────────────────────────────────────────────── */

export type FrameworkDraft = FrameworkInput;

export type FrameworkProblem =
  | 'code_required'
  | 'value_invalid'
  | 'currency_invalid'
  | 'dates_required'
  | 'dates_inverted';

export const FRAMEWORK_PROBLEM: Record<FrameworkProblem, KeyText> = {
  code_required: ['procurement_concept.ui.problem.framework_code_required', 'Give the agreement a code.'],
  value_invalid: ['procurement_concept.ui.problem.framework_value_invalid', 'The maximum value is not an amount.'],
  currency_invalid: [
    'procurement_concept.ui.problem.currency_invalid',
    'Give the currency as a three-letter code, for example EUR.',
  ],
  dates_required: ['procurement_concept.ui.problem.framework_dates_required', 'Give the start and the end date.'],
  dates_inverted: ['procurement_concept.errors.framework_dates_inverted', 'The end date is before the start date.'],
};

export function frameworkProblems(d: FrameworkDraft): FrameworkProblem[] {
  const out: FrameworkProblem[] = [];
  if (!d.code.trim()) out.push('code_required');
  if (parseAmount(d.max_value) === null) out.push('value_invalid');
  if (!/^[A-Za-z]{3}$/.test(d.currency.trim())) out.push('currency_invalid');
  if (!d.start_date || !d.end_date) out.push('dates_required');
  else if (d.end_date < d.start_date) out.push('dates_inverted');
  return out;
}

export function toFrameworkInput(d: FrameworkDraft): FrameworkInput {
  return {
    ...d,
    code: d.code.trim(),
    title: d.title.trim(),
    supplier_name: d.supplier_name.trim(),
    scope: d.scope.trim(),
    max_value: parseAmount(d.max_value) ?? '0',
    currency: d.currency.trim().toUpperCase(),
    source_procedure_ref: d.source_procedure_ref.trim(),
  };
}

/** An existing agreement keeps its code, currency and start date; the rest can change. */
export function toFrameworkPatch(d: FrameworkDraft): FrameworkPatch {
  const full = toFrameworkInput(d);
  return {
    title: full.title,
    supplier_name: full.supplier_name,
    scope: full.scope,
    package_kinds: full.package_kinds,
    max_value: full.max_value,
    end_date: full.end_date,
    call_off_mode: full.call_off_mode,
    source_procedure_ref: full.source_procedure_ref,
  };
}

const FRAMEWORK_NEXT: Record<FrameworkState, FrameworkTarget[]> = {
  draft: ['active', 'terminated'],
  active: ['exhausted', 'expired', 'terminated'],
  exhausted: ['active', 'terminated'],
  expired: [],
  terminated: [],
};

/** The states an agreement can move to from where it is. The server checks the same table. */
export function frameworkTargets(state: FrameworkState): FrameworkTarget[] {
  return FRAMEWORK_NEXT[state] ?? [];
}

/** How much of the agreement is called off, from 0 to 1, for the bar. Display only, never for a decision. */
export function calledOffShare(ledger: Pick<FrameworkLedger, 'max_value' | 'call_off_value'>): number {
  const max = Number(ledger.max_value);
  const used = Number(ledger.call_off_value);
  if (!Number.isFinite(max) || !Number.isFinite(used) || max <= 0) return 0;
  return Math.min(1, Math.max(0, used / max));
}
