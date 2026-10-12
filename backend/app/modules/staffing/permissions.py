# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Staffing permission definitions (SPEC section 5, lead decision 7).

Two tiers. ``staffing.read`` / ``staffing.edit`` cover the plan, positions,
fills and handovers and show names, roles, FTE, dates and the cleared-to-work
flag only. The personnel tier (``staffing.personnel.*``) opens files,
documents, travel and leave, and is narrowed per record by a relationship
check in the service: the m05 area owner, the owner of a position the person
fills, or the person themself (rule 13). ``Role`` is global, so the
relationship check is what keeps a manager of one project out of another
project's files. Approval of the plan is not a permission here: the
governance gate approves it.
"""

from app.core.permissions import Role, permission_registry

PERSONNEL_READ = "staffing.personnel.read"
PERSONNEL_EDIT = "staffing.personnel.edit"
PERSONNEL_ERASE = "staffing.personnel.erase"


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
        },
    )


def has_permission(payload: dict, permission: str) -> bool:
    """Same decision as ``RequirePermission``: admin, the token's list, or the live role mapping."""
    role = str(payload.get("role") or "")
    if role == "admin":
        return True
    if permission in (payload.get("permissions") or []):
        return True
    try:
        return permission_registry.role_has_permission(role, permission)
    except Exception:
        return False
