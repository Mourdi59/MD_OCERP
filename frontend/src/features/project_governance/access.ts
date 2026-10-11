// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Who may press which governance button, and in words why not.
//
// The server decides; this only predicts, so a button is disabled with a
// reason instead of answering with a 403 after the click. The prediction
// reads what the client has: the role (backend `governance.*` permissions are
// viewer / editor / manager, see project_governance/permissions.py), the
// project's four-eyes switch and the area owners. Route entitlement is not
// visible to the client, so `decider_not_entitled` can only be shown after
// the server refuses.

import type { GateArea, GateDetail, GovernanceArea, GovernanceCondition, GovernanceModel } from './api';
import type { KeyText } from './labels';

export type GovernanceLevel = 'read' | 'edit' | 'manage';

/** Rank of a role the way `core/permissions.py` ROLE_HIERARCHY and ROLE_ALIASES rank it. */
const ROLE_RANK: Record<string, number> = {
  field_worker: -2,
  site_foreman: -1,
  site_inspector: 0,
  viewer: 0,
  readonly: 0,
  editor: 1,
  estimator: 1,
  quantity_surveyor: 1,
  qs: 1,
  user: 1,
  manager: 2,
  admin: 3,
  superuser: 3,
  owner: 3,
};

const LEVEL_RANK: Record<GovernanceLevel, number> = { read: 0, edit: 1, manage: 2 };

export function roleAllows(role: string | null | undefined, level: GovernanceLevel): boolean {
  const rank = ROLE_RANK[(role ?? '').toLowerCase()];
  if (rank === undefined) return false;
  return rank >= LEVEL_RANK[level];
}

export type DisabledReason =
  | 'role_edit'
  | 'role_manage'
  | 'role_decide'
  | 'four_eyes'
  | 'gate_not_in_review'
  | 'gate_not_ready_to_submit'
  | 'project_stopped'
  | 'area_without_owner'
  | 'not_area_owner'
  | 'area_not_applicable'
  | 'condition_closed'
  | 'not_condition_owner';

export const DISABLED_REASON: Record<DisabledReason, KeyText> = {
  role_edit: ['governance.project.disabled.role_edit', 'Your role can view governance but not edit it. An editor or manager can.'],
  role_manage: ['governance.project.disabled.role_manage', 'Only a project manager can change this.'],
  role_decide: [
    'governance.project.disabled.role_decide',
    'Only a manager named on the gate approval route can decide a gate.',
  ],
  four_eyes: [
    'governance.project.disabled.four_eyes',
    'Four-eyes rule: you own or deputise an area of this gate, so someone else has to decide it.',
  ],
  gate_not_in_review: [
    'governance.project.disabled.gate_not_in_review',
    'Submit the gate for review first. A decision is recorded on a gate in review.',
  ],
  gate_not_ready_to_submit: [
    'governance.project.disabled.gate_not_ready_to_submit',
    'Only a gate in preparation can be submitted for review.',
  ],
  project_stopped: ['governance.project.disabled.project_stopped', 'The project was stopped at a gate.'],
  area_without_owner: [
    'governance.project.disabled.area_without_owner',
    'This area has no owner yet. Assign one on the area page, then the owner confirms readiness.',
  ],
  not_area_owner: [
    'governance.project.disabled.not_area_owner',
    'Only the owner or deputy of this area confirms its readiness.',
  ],
  area_not_applicable: [
    'governance.project.disabled.area_not_applicable',
    'This area is marked not applicable for the project.',
  ],
  condition_closed: ['governance.project.disabled.condition_closed', 'This condition is already closed.'],
  not_condition_owner: [
    'governance.project.disabled.not_condition_owner',
    'Only the condition owner or a manager can clear it.',
  ],
};

/** null means allowed; otherwise the first reason that stops the action. */
export type Verdict = DisabledReason | null;

export interface Viewer {
  userId: string | null;
  role: string | null;
}

function ownsArea(viewer: Viewer, area: Pick<GateArea, 'owner_user_id' | 'deputy_user_id'>): boolean {
  return !!viewer.userId && (area.owner_user_id === viewer.userId || area.deputy_user_id === viewer.userId);
}

export function canManage(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'manage') ? null : 'role_manage';
}

export function canSubmitGate(viewer: Viewer, model: GovernanceModel, detail: GateDetail): Verdict {
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  if (model.stopped) return 'project_stopped';
  if (detail.gate.status !== 'in_preparation') return 'gate_not_ready_to_submit';
  return null;
}

/**
 * Whether the viewer may open the decision dialog on this gate.
 *
 * Four-eyes comes after the role on purpose: an editor who also owns an area
 * should read that their role is the reason, because a change of owner would
 * not let them decide either.
 */
export function canDecide(viewer: Viewer, model: GovernanceModel, detail: GateDetail): Verdict {
  if (!roleAllows(viewer.role, 'manage')) return 'role_decide';
  if (model.stopped) return 'project_stopped';
  if (detail.gate.status !== 'in_review') return 'gate_not_in_review';
  if (model.four_eyes && detail.areas.some((a) => ownsArea(viewer, a))) return 'four_eyes';
  return null;
}

export function canConfirmCheck(viewer: Viewer, model: GovernanceModel, area: GateArea): Verdict {
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  if (model.stopped) return 'project_stopped';
  if (!area.applicable) return 'area_not_applicable';
  if (!area.owner_user_id) return 'area_without_owner';
  if (!ownsArea(viewer, area)) return 'not_area_owner';
  return null;
}

export function canEditArea(viewer: Viewer, _area: GovernanceArea): Verdict {
  return canManage(viewer);
}

export function canClearCondition(viewer: Viewer, condition: GovernanceCondition): Verdict {
  if (condition.status === 'cleared' || condition.status === 'waived') return 'condition_closed';
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  if (roleAllows(viewer.role, 'manage')) return null;
  if (!viewer.userId || condition.owner_user_id !== viewer.userId) return 'not_condition_owner';
  return null;
}

export function canWaiveCondition(viewer: Viewer, condition: GovernanceCondition): Verdict {
  if (condition.status === 'cleared' || condition.status === 'waived') return 'condition_closed';
  return roleAllows(viewer.role, 'manage') ? null : 'role_decide';
}
