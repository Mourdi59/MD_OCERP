# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics module permission definitions."""

from app.core.permissions import Role, permission_registry


def register_site_logistics_permissions() -> None:
    """Register permissions for the Site Logistics module."""
    permission_registry.register_module_permissions(
        "site_logistics",
        {
            "site_logistics.read": Role.VIEWER,
            "site_logistics.write": Role.EDITOR,
            # Approving / rejecting a delivery holds or releases a gate slot -
            # a scheduling decision, so it sits at manager level.
            "site_logistics.approve": Role.MANAGER,
            # Customs values are commercial (invoice values): an editor without
            # this permission sees the goods lines of a customs case without any
            # value (SPEC Decision 12).
            "site_logistics.customs": Role.MANAGER,
        },
    )
