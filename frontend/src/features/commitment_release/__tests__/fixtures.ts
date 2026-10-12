// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for API shapes in the commitment tests. Each returns a complete
// object so a test names only the fields its case is about.

import type {
  CanFlag,
  CommitmentItem,
  CommitmentMatrix,
  Exposure,
  ItemAction,
  ItemLink,
  ItemTotals,
  Precondition,
  ProjectAction,
  Release,
  ReleasePreview,
} from '../api';

export function matrix(over: Partial<CommitmentMatrix> = {}): CommitmentMatrix {
  return {
    id: 'm1',
    project_id: 'p1',
    schedule_source: 'shipped',
    schedule_id: 'neutral',
    schedule_version: 1,
    enforcement: 'warn',
    fx_policy: 'fx_service_rate_set',
    require_link: false,
    tier_routes: { project_manager: 'r1' },
    legal_entity_id: null,
    base_currency: 'EUR',
    schedule_currency: 'EUR',
    tiers: [
      {
        code: 'project_manager',
        name: { key: 'commitment.tier.project_manager', text: null },
        approver: { kind: 'project_role', ref: 'project_manager' },
        steps_mode: 'any',
        four_eyes: true,
        route_id: 'r1',
        route_state: 'generated',
      },
      {
        code: 'sponsor',
        name: { key: 'commitment.tier.sponsor', text: null },
        approver: { kind: 'project_role', ref: 'sponsor' },
        steps_mode: 'any',
        four_eyes: true,
        route_id: null,
        route_state: 'none',
      },
    ],
    commitment_types: [
      { code: 'works', name: { key: 'commitment.type.works', text: null } },
      { code: 'supplies', name: { key: 'commitment.type.supplies', text: null } },
      { code: 'design', name: { key: 'commitment.type.design', text: null } },
    ],
    novelty_flags: [{ code: 'novel_contentious', name: { key: 'commitment.flag.novel_contentious', text: null }, min_tier: 'sponsor' }],
    ...over,
  };
}

export function precondition(over: Partial<Precondition> = {}): Precondition {
  return {
    id: 'pre1',
    kind: 'manual',
    ref_id: null,
    text: 'Client brief signed off',
    state: 'open',
    evidence_ref: null,
    confirmed_by: null,
    confirmed_at: null,
    ...over,
  };
}

export function link(over: Partial<ItemLink> = {}): ItemLink {
  return {
    link_id: 'l1',
    kind: 'contract',
    document_id: 'doc1',
    contract_id: null,
    currency: 'EUR',
    document_amount: '1700000.00',
    counted_amount: '1700000.00',
    counts: true,
    closed: false,
    status: 'active',
    found: true,
    notes: [],
    ...over,
  };
}

export function exposure(over: Partial<Exposure> = {}): Exposure {
  return {
    sunk: '200000.00',
    committed: '1700000.00',
    committed_not_spent: '1500000.00',
    cancellation_charge: '40000.00',
    recoverable: '0',
    residual_loss: '240000.00',
    reason: null,
    method: 'custom',
    basis_review_status: 'verified',
    lines: [],
    currency: 'EUR',
    as_of: '2026-10-12',
    basis_code: 'custom',
    transferable: 'no',
    ...over,
  };
}

const ACTIONS: ItemAction[] = [
  'edit',
  'link',
  'request_release',
  'request_abort',
  'withdraw',
  'decide',
  'hold',
  'resume',
  'transfer',
  'defer',
  'edit_gate_fields',
];

/**
 * The `can` block as the server sends it: every action allowed unless a
 * refusal code is named for it.
 */
export function can(refused: Partial<Record<ItemAction, string>> = {}): Record<ItemAction, CanFlag> {
  const out = {} as Record<ItemAction, CanFlag>;
  for (const action of ACTIONS) {
    const reason = refused[action] ?? null;
    out[action] = { allowed: reason === null, reason };
  }
  return out;
}

/** What an owner sees on a planned item with nothing pending. */
export const OWNER_CAN = can({ withdraw: 'no_pending_release', decide: 'no_pending_release', resume: 'invalid_transition' });

/** What somebody with read access only sees on the same item. */
export const READER_CAN = can({
  edit: 'not_item_owner',
  link: 'not_item_owner',
  request_release: 'not_item_owner',
  request_abort: 'not_item_owner',
  withdraw: 'no_pending_release',
  decide: 'no_pending_release',
  hold: 'manage_required',
  resume: 'manage_required',
  transfer: 'manage_required',
  defer: 'manage_required',
});

/** The project capabilities as the server sends them: all allowed unless a refusal code is named. */
export function projectCan(refused: Partial<Record<ProjectAction, string>> = {}): Record<ProjectAction, CanFlag> {
  const flag = (action: ProjectAction): CanFlag => ({ allowed: !refused[action], reason: refused[action] ?? null });
  return { manage: flag('manage'), add_item: flag('add_item'), save_scenario: flag('save_scenario') };
}

/** The exposure of an item with nothing bound and nothing spent, as the server sends it: a known zero. */
export function nothingBound(): Exposure {
  return exposure({
    sunk: '0',
    committed: '0',
    committed_not_spent: '0',
    cancellation_charge: '0',
    recoverable: '0',
    residual_loss: '0',
    method: null,
    basis_review_status: null,
    basis_code: null,
    transferable: null,
    lines: [
      { code: 'paid', amount: '0' },
      { code: 'invoiced_unpaid', amount: '0' },
      { code: 'certified_not_invoiced', amount: '0' },
      { code: 'received_not_invoiced', amount: '0' },
      { code: 'nothing_committed', amount: '0' },
    ],
  });
}

export function item(over: Partial<CommitmentItem> = {}): CommitmentItem {
  return {
    id: 'i1',
    code: 'CR-001',
    title: 'Structural works package',
    commitment_type: 'works',
    status: 'planned',
    attempt_no: 1,
    flags: [],
    governance_area_code: null,
    gate_code: null,
    deferred: false,
    deferred_reason: null,
    split_group: null,
    owner_user_id: 'u-owner',
    planned_source: 'manual',
    lead_time_days: 45,
    decision_buffer_days: 10,
    latest_decision_date_fixed: '2026-11-02',
    planned: { amount: '1850000.00', currency: 'EUR', note: null },
    schedule_currency: 'EUR',
    planned_in_schedule_currency: '1850000.00',
    released: '0',
    committed: '0',
    committed_reason: null,
    release_ceiling_with_tolerance: '0',
    over_release: false,
    required_tier_for_planned: 'sponsor',
    latest_decision_date: '2026-11-02',
    date_basis: 'fixed',
    decision_overdue: false,
    preconditions: [],
    open_preconditions: 0,
    links: [],
    pending_release_id: null,
    pending_purpose: null,
    transferred_to_item_id: null,
    abort: null,
    can: OWNER_CAN,
    exposure: nothingBound(),
    ...over,
  };
}

export function totals(over: Partial<ItemTotals> = {}): ItemTotals {
  return {
    currency: 'EUR',
    planned: '2605000.00',
    released: '40000.00',
    committed: '1700000.00',
    mixed_currency: false,
    incomplete: [],
    ...over,
  };
}

export function preview(over: Partial<ReleasePreview> = {}): ReleasePreview {
  return {
    amount: '40000',
    currency: 'EUR',
    schedule_currency: 'EUR',
    amount_in_schedule_currency: '40000',
    fx: { from: 'EUR', to: 'EUR', rate: '1', as_of: null, source: 'same_currency', rate_set_id: null },
    released_before: '0',
    group_released: '0',
    evaluated_amount: '40000',
    required_tier: 'project_manager',
    escalate_outside: false,
    band_code: 'pm_any',
    raised_by: [],
    route_tier: 'project_manager',
    route_id: 'r1',
    approvers: ['u-owner'],
    schedule: 'shipped:neutral@1',
    open_preconditions: [],
    ...over,
  };
}

export function release(over: Partial<Release> = {}): Release {
  return {
    id: 'rel1',
    item_id: 'i1',
    attempt: 1,
    purpose: 'release',
    requested_amount: '40000.00',
    currency: 'EUR',
    schedule_currency: 'EUR',
    amount_in_schedule_currency: '40000.00',
    fx_rate_used: '1',
    fx_rate_date: null,
    fx_source: 'same_currency',
    evaluated_amount: '40000.00',
    cumulative_after: '40000.00',
    required_tier: 'project_manager',
    escalate_outside: false,
    external_approval_ref: '',
    approval_instance_id: 'inst1',
    outcome: 'pending',
    requested_by: 'u-other',
    decided_by: null,
    on_behalf_of: null,
    decided_at: null,
    tranche_note: 'First tranche: concept design',
    conditions: '',
    rationale: '',
    valid_until: null,
    created_at: '2026-10-10T09:00:00Z',
    ...over,
  };
}
