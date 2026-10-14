# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Engineering brief permission definitions.

Approval is not a permission of this module: the brief is approved by the governance gate decision on
the hosting area, whose deciders the gate's approval route entitles. ``engineering_brief.edit`` opens
the brief, requirements, concept, programme and schedule; ``engineering_brief.manage`` publishes the
framework schedule into the programme and approves by hand on a project without gates.
"""

from app.core.permissions import Role, permission_registry

MANAGE = "engineering_brief.manage"


def register_engineering_brief_permissions() -> None:
    """Register permissions for the engineering brief module."""
    permission_registry.register_module_permissions(
        "engineering_brief",
        {
            "engineering_brief.read": Role.VIEWER,
            "engineering_brief.edit": Role.EDITOR,
            MANAGE: Role.MANAGER,
        },
    )


def has_permission(payload: dict, permission: str) -> bool:
    """Same decision as ``RequirePermission``: the token's list, or the live mapping of the token's role."""
    if permission in (payload.get("permissions") or []):
        return True
    return permission_registry.role_has_permission(str(payload.get("role", "")), permission)
