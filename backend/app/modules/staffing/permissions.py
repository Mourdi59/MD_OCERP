# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Staffing permission definitions (SPEC section 5, lead decision 7).

Two tiers. ``staffing.read`` / ``staffing.edit`` cover the plan, positions,
fills and handovers and show names, roles, FTE, dates and the cleared-to-work
flag only. The personnel tier (``staffing.personnel.*``) opens files,
documents, travel and leave, and is narrowed per record by a relationship
check in the service: the owner of the governance area that hosts staffing,
the line manager of a position the person fills, or the person themself
(rule 13). ``Role`` is global, so the relationship check is what keeps a
manager of one project out of another project's files, and no permission
replaces it. Whatever sets who is related sits one tier higher:
``staffing.personnel.assign`` names the line manager of a position.
``staffing.manage`` changes what a gate reads (key role, requirement, handover).
Approval of the plan is not a permission here: the governance gate approves it.

The router turns the token into booleans with :func:`has_permission`; the
service never sees a role.
"""

from app.core.permissions import Role, permission_registry

PERSONNEL_READ = "staffing.personnel.read"
PERSONNEL_EDIT = "staffing.personnel.edit"
PERSONNEL_ERASE = "staffing.personnel.erase"
PERSONNEL_ASSIGN = "staffing.personnel.assign"
MANAGE = "staffing.manage"


def register_staffing_permissions() -> None:
    """Register permissions for the staffing module."""
    permission_registry.register_module_permissions(
        "staffing",
        {
            "staffing.read": Role.VIEWER,
            "staffing.edit": Role.EDITOR,
            PERSONNEL_READ: Role.MANAGER,
            PERSONNEL_EDIT: Role.MANAGER,
            PERSONNEL_ERASE: Role.ADMIN,
            PERSONNEL_ASSIGN: Role.ADMIN,
            MANAGE: Role.MANAGER,
        },
    )


def has_permission(payload: dict, permission: str) -> bool:
    """Same decision as ``RequirePermission``: the token's list, or the live mapping of the token's role."""
    if permission in (payload.get("permissions") or []):
        return True
    return permission_registry.role_has_permission(str(payload.get("role", "")), permission)
