// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Which delivery model button may be pressed, and in words why not.
//
// The server decides; this only predicts, so a button is disabled with a
// reason instead of answering with a refusal after the click. The delivery
// model API sends no capability flags yet, so the role half of the prediction
// reads the shared mirror of the backend hierarchy (delivery_model.read is
// viewer, .edit is editor, .manage is manager, see
// delivery_model/permissions.py). The state half reads the model status the
// server sent. Once the API carries `can` flags they replace the role checks
// here and nothing else changes.

import type { DeliveryModel, ModelStatus } from './api';
import type { KeyText } from './labels';
import { allocationsFrozen, comparisonEditable } from './rules';
import { ROLE_ALIASES, ROLE_RANK } from '@/shared/lib/roles';

export type DeliveryLevel = 'read' | 'edit' | 'manage';

const LEVEL_RANK: Record<DeliveryLevel, number> = { read: 0, edit: 1, manage: 2 };

/**
 * Whether a role reaches a level. No role and an unknown role both deny: an
 * absent role is not the viewer role here, because `read` sits at the
 * viewer's rank.
 */
export function roleAllows(role: string | null | undefined, level: DeliveryLevel): boolean {
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
  | 'decision_pending'
  | 'model_frozen'
  | 'not_proposed'
  | 'not_binding'
  | 'form_not_selected';

export const DISABLED_REASON: Record<DisabledReason, KeyText> = {
  role_edit: ['delivery_model.ui.disabled.role_edit', 'Your role can view the delivery model but not edit it. An editor or manager can.'],
  role_manage: ['delivery_model.ui.disabled.role_manage', 'Only a project manager can do this.'],
  decision_pending: [
    'delivery_model.ui.disabled.decision_pending',
    'A decision is proposed and waits for the gate. Withdraw it to change the comparison.',
  ],
  model_frozen: [
    'delivery_model.ui.disabled.model_frozen',
    'The delivery model is approved. It changes only after it is reopened through a change request.',
  ],
  not_proposed: ['delivery_model.ui.disabled.not_proposed', 'There is no proposed decision to withdraw.'],
  not_binding: ['delivery_model.ui.disabled.not_binding', 'Only a binding delivery model can be reopened.'],
  form_not_selected: ['delivery_model.ui.disabled.form_not_selected', 'Propose a delivery form first. The package template comes from it.'],
};

/** null means allowed; otherwise the first reason that stops the action. */
export type Verdict = DisabledReason | null;

export interface Viewer {
  userId: string | null;
  role: string | null;
}

function frozenReason(status: ModelStatus): DisabledReason {
  return status === 'proposed' ? 'decision_pending' : 'model_frozen';
}

/** Starting the model, pinning another catalogue. */
export function canManage(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'manage') ? null : 'role_manage';
}

/** Options, weights, scores and the owner situation. */
export function canEditComparison(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  return comparisonEditable(model.status) ? null : frozenReason(model.status);
}

export function canChangeCatalogue(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'manage')) return 'role_manage';
  return comparisonEditable(model.status) ? null : frozenReason(model.status);
}

export function canPropose(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'manage')) return 'role_manage';
  return comparisonEditable(model.status) ? null : frozenReason(model.status);
}

export function canWithdraw(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'manage')) return 'role_manage';
  return model.status === 'proposed' ? null : 'not_proposed';
}

export function canReopen(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'manage')) return 'role_manage';
  return model.status === 'binding' ? null : 'not_binding';
}

export function canEditAllocations(viewer: Viewer, model: Pick<DeliveryModel, 'status'>): Verdict {
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  return allocationsFrozen(model.status) ? 'model_frozen' : null;
}

/** Packages and owner-furnished items follow the edit permission; the server owns every state rule. */
export function canEditPlan(viewer: Viewer): Verdict {
  return roleAllows(viewer.role, 'edit') ? null : 'role_edit';
}

export function canDerivePackages(viewer: Viewer, model: Pick<DeliveryModel, 'selected_form_code'>): Verdict {
  if (!roleAllows(viewer.role, 'edit')) return 'role_edit';
  return model.selected_form_code ? null : 'form_not_selected';
}
