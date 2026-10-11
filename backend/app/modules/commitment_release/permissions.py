# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commitment release permission definitions.

Release authority is never a permission. Whoever may release an amount is
named by the approval route of the required tier (``entitled_deciders``);
these permissions only open the screens and the writes around it.
``commitment.edit`` lets an editor work on items; the service narrows changes
of an item further to its owner or a manager.
"""

from app.core.permissions import Role, permission_registry


def register_commitment_permissions() -> None:
    """Register permissions for the commitment release module."""
    permission_registry.register_module_permissions(
        "commitment_release",
        {
            "commitment.read": Role.VIEWER,
            "commitment.edit": Role.EDITOR,
            # Pinning a schedule, switching enforcement, naming who fills a tier.
            "commitment.manage": Role.MANAGER,
            # Tenant authority schedules and abort bases.
            "commitment.catalogue": Role.ADMIN,
        },
    )
