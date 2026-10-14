# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project handbook permission definitions.

``project_handbook.edit`` writes chapter text and submits a chapter for approval.
``project_handbook.manage`` approves a chapter, rebuilds the chapter list from the catalogue and
materialises the data room. With four eyes on, the approver is never the submitter, whatever their rights.
"""

from app.core.permissions import Role, permission_registry

MANAGE = "project_handbook.manage"
EDIT = "project_handbook.edit"


def register_project_handbook_permissions() -> None:
    """Register permissions for the project handbook module."""
    permission_registry.register_module_permissions(
        "project_handbook",
        {
            "project_handbook.read": Role.VIEWER,
            EDIT: Role.EDITOR,
            MANAGE: Role.MANAGER,
        },
    )


def has_permission(payload: dict, permission: str) -> bool:
    """Same decision as ``RequirePermission``: the token's list, or the live mapping of the token's role."""
    if permission in (payload.get("permissions") or []):
        return True
    return permission_registry.role_has_permission(str(payload.get("role", "")), permission)
