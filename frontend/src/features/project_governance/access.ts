// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Who may press which governance button, and in words why not.
//
// The server decides; this only predicts, so a button is disabled with a
// reason instead of answering with a 403 after the click. The prediction
// reads what the client has: the role (backend `governance.*` permissions are
// viewer / editor / manager, see project_governance/permissions.py), the
// project's four-eyes switch and the area owners. The server's `can` flags
// (gate detail, model) decide everything they cover, because only the server
// knows the route entitlement. The role is read only where no flag exists
// yet: clearing a condition and resuming a held gate.

import type { GateArea, GateDetail, GovernanceCondition, GovernanceModel } from './api';
import type { KeyText } from './labels';
import { ROLE_ALIASES, ROLE_RANK } from '@/shared/lib/roles';

export type GovernanceLevel = 'read' | 'edit' | 'manage';


const LEVEL_RANK: Record<GovernanceLevel, number> = { read: 0, edit: 1, manage: 2 };

/**
 * Whether a role reaches a governance level, ranked by the shared mirror of the
 * backend hierarchy. No role and an unknown role both deny: an absent role is
 * not the viewer role here, because `read` sits at the viewer's rank.
 */
export function roleAllows(role: string | null | undefined, level: GovernanceLevel): boolean {
  if (!role) return false;
  const r = role.trim().toLowerCase();
  const canonical = ROLE_ALIASES[r] ?? r;
  const rank = (ROLE_RANK as Record<string, number>)[canonical];
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
/**
 * A refusal the server named with a code this screen has no reason for. It is
 * shown through `governance.errors.<code>` or a neutral sentence, never mapped
 * onto a known reason: a plausible wrong reason is worse than none.
 */
export interface ServerRefusal {
  server: string;
}

export type Verdict = DisabledReason | ServerRefusal | null;

export interface Viewer {
  userId: string | null;
  role: string | null;
}

function ownsArea(viewer: Viewer, area: Pick<GateArea, 'owner_user_id' | 'deputy_user_id'>): boolean {
  return !!viewer.userId && (area.owner_user_id === viewer.userId || area.deputy_user_id === viewer.userId);
}

/** Server refusal codes that name a reason the screen can explain. */
const REASON_OF_CODE: Record<string, DisabledReason> = {
  decider_is_area_owner: 'four_eyes',
  decider_not_entitled: 'role_decide',
  missing_permission: 'role_decide',
  gate_not_in_review: 'gate_not_in_review',
  project_stopped: 'project_stopped',
  not_area_owner: 'not_area_owner',
  area_without_owner: 'area_without_owner',
};

/** The verdict for a server refusal code: a known reason, or the code itself for the screen to resolve. */
export function reasonOfCode(code: string | null | undefined): DisabledReason | ServerRefusal {
  return (code && REASON_OF_CODE[code]) || { server: code ?? '' };
}

/**
 * Manage rights before a model exists. There is no model to carry the server
 * flag yet, so the role answers; the PUT that sets the model still decides.
 */
export function roleManage(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'manage') ? null : 'role_manage';
}

/** Manage rights, as the server reports them on the model. */
export function canManage(model: Pick<GovernanceModel, 'can'>): Verdict {
  return model.can.manage ? null : 'role_manage';
}

export function canSubmitGate(model: GovernanceModel, detail: GateDetail): Verdict {
  if (!detail.can.edit) return 'role_edit';
  if (model.stopped) return 'project_stopped';
  if (detail.gate.status !== 'in_preparation') return 'gate_not_ready_to_submit';
  return null;
}

/**
 * Whether the viewer may open the decision dialog on this gate.
 *
 * Gate state and a stopped project explain first, because they hold for
 * everyone; then the server's answer, which knows route entitlement and
 * four-eyes. A refusal code this screen does not know travels as is.
 */
export function canDecide(model: GovernanceModel, detail: GateDetail): Verdict {
  if (model.stopped) return 'project_stopped';
  if (detail.gate.status !== 'in_review') return 'gate_not_in_review';
  return detail.can.decide ? null : reasonOfCode(detail.can.decide_reason);
}

export function canConfirmCheck(
  viewer: Viewer,
  model: GovernanceModel,
  area: GateArea,
  detail: Pick<GateDetail, 'can'>,
): Verdict {
  if (!detail.can.edit) return 'role_edit';
  if (model.stopped) return 'project_stopped';
  if (!area.applicable) return 'area_not_applicable';
  if (!area.owner_user_id) return 'area_without_owner';
  if (!ownsArea(viewer, area)) return 'not_area_owner';
  return null;
}

export function canEditArea(model: Pick<GovernanceModel, 'can'>): Verdict {
  return canManage(model);
}

export function canClearCondition(viewer: Viewer, condition: GovernanceCondition): Verdict {
  if (condition.status === 'cleared' || condition.status === 'waived') return 'condition_closed';
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  if (roleAllows(viewer.role, 'manage')) return null;
  if (!viewer.userId || condition.owner_user_id !== viewer.userId) return 'not_condition_owner';
  return null;
}

export function canWaiveCondition(condition: GovernanceCondition, model: Pick<GovernanceModel, 'can'>): Verdict {
  if (condition.status === 'cleared' || condition.status === 'waived') return 'condition_closed';
  return model.can.manage ? null : 'role_decide';
}
