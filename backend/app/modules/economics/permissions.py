# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Economics permission definitions.

Approval is not a permission of this module: the plan is approved by the governance gate decision on the
commercial area, whose deciders the gate's approval route entitles (or by a manager, by hand, on a project
without gates). ``economics.edit`` opens the lines of the three parts; starting the plan, proposing,
withdrawing and reopening need ``economics.manage``.
"""

from app.core.permissions import Role, permission_registry


def register_economics_permissions() -> None:
    """Register permissions for the economics module."""
    permission_registry.register_module_permissions(
        "economics",
        {
            "economics.read": Role.VIEWER,
            "economics.edit": Role.EDITOR,
            "economics.manage": Role.MANAGER,
        },
    )
