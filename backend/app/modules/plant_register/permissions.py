# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plant register permission definitions.

``plant.edit`` is the floor, not the grant: holding it lets an editor ask to
change the register, and the service then admits only a holder of
``plant.manage`` or the owner (or deputy) of the equipment area of the
project's governance model. ``plant.manage`` alone pins the catalogue and
overrides an item's critical or long-lead classification, because those decide
which rules a gate applies. A decision paper is approved only through its
approval route, never by a permission here.
"""

from app.core.permissions import Role, permission_registry


def register_plant_permissions() -> None:
    """Register permissions for the plant register module."""
    permission_registry.register_module_permissions(
        "plant_register",
        {
            "plant.read": Role.VIEWER,
            "plant.edit": Role.EDITOR,
            "plant.manage": Role.MANAGER,
        },
    )
