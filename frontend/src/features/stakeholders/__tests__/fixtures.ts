// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Builders for the API shapes the stakeholder tests feed the screens. Each
// returns a complete, valid object; a test overrides only what it is about.

import type {
  AnalysisMethod,
  Commitment,
  CommitmentCan,
  DueOccurrence,
  EngagementEvent,
  Framework,
  FrameworkItem,
  GovernanceBody,
  GridItem,
  GridResponse,
  MandateMatrix,
  PlanItem,
  Readiness,
  RolesView,
  Stakeholder,
  StakeholderSettings,
  WhoDecides,
} from '../api';
import type { Screen } from '../screen';
import { enExists, enT } from './i18nMock';

const item = (group: string, code: string): FrameworkItem => ({
  code,
  name_key: `stakeholders.catalogue.${group}.${code}`,
  labels: null,
});

export const powerInterest: AnalysisMethod = {
  ...item('method', 'power_interest'),
  version: 1,
  dimensions: [
    { ...item('dimension', 'power'), type: 'int', min: 1, max: 5 },
    { ...item('dimension', 'interest'), type: 'int', min: 1, max: 5 },
  ],
  classes: ['manage_closely', 'keep_satisfied', 'keep_informed', 'monitor'].map((c) => item('class', c)),
  rules: [
    {
      when: { power: { gte: 3, lte: null, eq: null }, interest: { gte: 3, lte: null, eq: null } },
      classification: 'manage_closely',
    },
    { when: { power: { gte: 3, lte: null, eq: null } }, classification: 'keep_satisfied' },
    { when: { interest: { gte: 3, lte: null, eq: null } }, classification: 'keep_informed' },
  ],
  default: 'monitor',
};

export const salience: AnalysisMethod = {
  ...item('method', 'salience'),
  version: 1,
  dimensions: ['power', 'legitimacy', 'urgency'].map((d) => ({ ...item('dimension', d), type: 'bool' as const, min: 0, max: 0 })),
  classes: ['definitive', 'dormant'].map((c) => item('class', c)),
  rules: [
    {
      when: {
        power: { gte: null, lte: null, eq: true },
        legitimacy: { gte: null, lte: null, eq: true },
        urgency: { gte: null, lte: null, eq: true },
      },
      classification: 'definitive',
    },
    { when: { power: { gte: null, lte: null, eq: true } }, classification: 'dormant' },
  ],
  default: null,
};

export function framework(over: Partial<Framework> = {}): Framework {
  return {
    id: 'neutral',
    version: 1,
    name_key: 'stakeholders.catalogue.framework.neutral',
    labels: null,
    review_status: 'unconfirmed',
    default_method: 'power_interest',
    feedback_due_days: 30,
    stakeholder_categories: [
      { ...item('category', 'client'), kind: 'internal', private_person: false },
      { ...item('category', 'neighbour'), kind: 'external', private_person: true },
      { ...item('category', 'permitting_authority'), kind: 'external', private_person: false },
    ],
    analysis_methods: [powerInterest, salience],
    engagement_levels: ['unaware', 'resistant', 'neutral', 'supportive', 'leading'].map((c, order) => ({
      ...item('engagement_level', c),
      order,
    })),
    participation_levels: ['inform', 'consult', 'involve'].map((c, order) => ({
      ...item('participation_level', c),
      order,
      promise_key: `stakeholders.catalogue.participation_promise.${c}`,
    })),
    channels: ['letter', 'meeting'].map((c) => item('channel', c)),
    participation_formats: [],
    roles: [
      { ...item('role', 'client'), holder_kind: 'organisation', multi: false, required: true },
      { ...item('role', 'project_manager'), holder_kind: 'person', multi: false, required: true },
    ],
    body_types: [{ ...item('body_type', 'steering_committee'), default_decision_level: 3 }],
    decision_types: [
      {
        ...item('decision_type', 'order_award'),
        commitment_type: 'works',
        approval_target_kind: null,
        required: true,
        forbid_self_approval: true,
      },
      {
        ...item('decision_type', 'stakeholder_commitment'),
        commitment_type: null,
        approval_target_kind: null,
        required: true,
        forbid_self_approval: false,
      },
    ],
    ...over,
  };
}

export function settings(over: Partial<StakeholderSettings> = {}): StakeholderSettings {
  return {
    id: 'set1',
    project_id: 'p1',
    framework_source: 'shipped',
    framework_id: 'neutral',
    framework_version: 1,
    analysis_method: 'power_interest',
    review_interval_days: 90,
    owner_area_code: 'm01_project_management',
    commitment_route_id: null,
    framework: framework(),
    can: { edit: true, read_personal: true, manage_organisation: true },
    can_file: {
      register: { applies: true, allowed: true, reason: null },
      organisation: { applies: true, allowed: true, reason: null },
    },
    ...over,
  };
}

export function screen(over: Partial<Screen> = {}): Screen {
  return {
    projectId: 'p1',
    settings: settings(),
    labels: { t: enT, language: 'en', exists: enExists },
    personName: (id) => (id === 'u-owner' ? 'Dana Weber' : null),
    onChanged: () => undefined,
    ...over,
  };
}

export function stakeholder(over: Partial<Stakeholder> = {}): Stakeholder {
  return {
    id: 's1',
    project_id: 'p1',
    code: 'STK-001',
    display_name: 'Building authority',
    name: 'Building authority',
    masked: false,
    anonymised: false,
    category: 'permitting_authority',
    contact_id: null,
    is_group: false,
    group_size_estimate: null,
    parent_stakeholder_id: null,
    geo: null,
    risk_id: null,
    interests: '',
    expectations: '',
    concerns: '',
    relationship_owner_user_id: 'u-owner',
    is_confidential: false,
    status: 'active',
    classification: 'manage_closely',
    method_code: 'power_interest',
    engagement_current: 'neutral',
    engagement_desired: 'supportive',
    engagement_gap: 1,
    attitude: 0,
    last_assessed_at: '2026-09-01T09:00:00+00:00',
    review_due: false,
    external: true,
    open_commitments: 0,
    ...over,
  };
}

const yes = { applies: true, allowed: true, reason: null };
/** Refused: an action the state does not have is ruled out as a transition, anything else applies and is switched off. */
const no = (reason: string) => ({ applies: reason !== 'invalid_transition', allowed: false, reason });

/** What the server allows on a commitment in `status` for someone who may edit and decides commitments. */
export function canOf(status: Commitment['status'], over: Partial<CommitmentCan> = {}): CommitmentCan {
  const moves: Record<Commitment['status'], string[]> = {
    proposed: ['agreed', 'withdrawn'],
    agreed: ['in_progress', 'fulfilled', 'withdrawn', 'breached'],
    in_progress: ['fulfilled', 'withdrawn', 'breached'],
    fulfilled: ['verified', 'breached'],
    breached: ['fulfilled', 'withdrawn'],
    verified: [],
    withdrawn: [],
  };
  const flag = (target: string) => (moves[status].includes(target) ? yes : no('invalid_transition'));
  return {
    agreed: flag('agreed'),
    in_progress: flag('in_progress'),
    fulfilled: flag('fulfilled'),
    verified: flag('verified'),
    withdrawn: flag('withdrawn'),
    breached: flag('breached'),
    // A closed commitment is not editable, so the server says editing does not apply there.
    edit: moves[status].length > 0 ? yes : no('invalid_transition'),
    ...over,
  };
}

export function commitment(over: Partial<Commitment> = {}): Commitment {
  return {
    id: 'c1',
    code: 'COM-001',
    stakeholder_ids: ['s1'],
    source_kind: 'manual',
    source_ref: '',
    source_snapshot: {},
    text: 'No deliveries before seven in the morning',
    category: 'working_hours',
    owner_user_id: 'u-owner',
    due_date: '2026-11-30',
    verification: '',
    cost_estimate: null,
    currency: '',
    risk_id: null,
    task_id: null,
    requirement_id: null,
    release_item_id: null,
    status: 'proposed',
    overdue: false,
    approval_instance_id: null,
    pending_target: null,
    withdraw_rationale: '',
    breach_rationale: '',
    communicated_back_at: null,
    loop_not_required_rationale: '',
    can: canOf(over.status ?? 'proposed'),
    ...over,
  };
}

export function planItem(over: Partial<PlanItem> = {}): PlanItem {
  return {
    id: 'pl1',
    title: 'Neighbour newsletter',
    purpose: '',
    key_message: 'What happens on site next month',
    audience_stakeholder_ids: [],
    audience_categories: ['neighbour'],
    audience_body_id: null,
    participation_level: 'inform',
    channel: 'letter',
    format_code: null,
    frequency: 'FREQ=MONTHLY',
    trigger_kind: null,
    trigger_ref: null,
    owner_user_id: 'u-owner',
    starts_on: '2026-09-01',
    ends_on: null,
    status: 'active',
    next_due: '2026-10-01',
    overdue: true,
    ...over,
  };
}

export function due(over: Partial<DueOccurrence> = {}): DueOccurrence {
  return {
    plan_item_id: 'pl1',
    title: 'Neighbour newsletter',
    date: '2026-10-01',
    done: false,
    overdue: true,
    participation_level: 'inform',
    channel: 'letter',
    owner_user_id: 'u-owner',
    ...over,
  };
}

export function event(over: Partial<EngagementEvent> = {}): EngagementEvent {
  return {
    id: 'e1',
    plan_item_id: null,
    occurrence_date: null,
    format_code: null,
    participation_level: 'consult',
    title: 'Information evening for residents',
    held_on: '2026-08-20',
    location: 'Community hall',
    stakeholder_ids: ['s1'],
    attendance_count: 40,
    outcome: 'Residents asked for quiet hours',
    feedback_summary: '',
    meeting_id: null,
    correspondence_ids: [],
    cde_container_ids: [],
    status: 'held',
    feedback_not_reported: true,
    feedback_due_on: '2026-09-19',
    ...over,
  };
}

export function readiness(over: Partial<Readiness> = {}): Readiness {
  return {
    register_present: { status: 'met' },
    key_stakeholders_planned: { status: 'not_met', refs: ['STK-001'] },
    mandates_complete: { status: 'met' },
    roles_filled: { status: 'not_met', refs: ['client'] },
    commitments_tracked: { status: 'met' },
    ...over,
  };
}

export function rolesView(over: Partial<RolesView> = {}): RolesView {
  return {
    roles: framework().roles,
    holders: [
      {
        id: 'h1',
        role_code: 'project_manager',
        custom_label: '',
        roster_member_id: 'r1',
        holder_contact_id: null,
        deputy_roster_member_id: null,
        holder_name: 'Dana Weber',
        user_id: 'u-owner',
        valid_from: null,
        valid_to: null,
        valid_today: true,
        conflict_rationale: '',
      },
    ],
    vacant: ['client'],
    vacant_required: ['client'],
    ...over,
  };
}

export function body(over: Partial<GovernanceBody> = {}): GovernanceBody {
  return {
    id: 'b1',
    code: 'steering',
    body_type: 'steering_committee',
    name: 'Steering committee',
    chair_role_code: 'client',
    quorum_kind: 'majority',
    quorum_min: null,
    decision_level: 3,
    members: [],
    quorum_needed: 1,
    quorum_present: 0,
    inquorate: true,
    ...over,
  };
}

export function matrix(over: Partial<MandateMatrix> = {}): MandateMatrix {
  return {
    decision_types: framework().decision_types,
    roles: ['client', 'project_manager'],
    bodies: ['steering'],
    rows: [
      { id: 'm1', decision_type: 'order_award', scope: '', holder_kind: 'role', holder_code: 'project_manager', letter: 'P', scope_note: '' },
      { id: 'm2', decision_type: 'order_award', scope: '', holder_kind: 'body', holder_code: 'steering', letter: 'D', scope_note: 'above the works budget' },
    ],
    missing: ['stakeholder_commitment'],
    conflicts: [],
    ...over,
  };
}

export function gridItem(over: Partial<GridItem> = {}): GridItem {
  return {
    stakeholder_id: 's1',
    code: 'STK-001',
    name: 'Building authority',
    masked: false,
    anonymised: false,
    category: 'permitting_authority',
    classification: 'manage_closely',
    position: { x: 5, y: 4, x_dim: 'interest', y_dim: 'power' },
    scores: { power: 4, interest: 5 },
    assessment_id: 'a1',
    ...over,
  };
}

export function grid(over: Partial<GridResponse> = {}): GridResponse {
  return {
    method_code: 'power_interest',
    method_version: 1,
    dimensions: powerInterest.dimensions,
    classes: powerInterest.classes,
    items: [gridItem()],
    ...over,
  };
}

export function decider(over: Partial<WhoDecides> = {}): WhoDecides {
  return {
    decision_type: 'order_award',
    scope: '',
    holder_kind: 'body',
    holder_code: 'steering',
    user_ids: ['u-owner'],
    parties: [{ user_id: 'u-owner', contact_id: null, roster_member_id: 'r1', role_code: 'project_manager', voting: true }],
    quorum_needed: 2,
    quorum_present: 1,
    flags: ['body_inquorate'],
    authority: null,
    ...over,
  };
}
