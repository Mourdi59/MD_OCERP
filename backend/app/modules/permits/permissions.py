# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits permission definitions.

``permits.edit`` lets an editor work on requirements, applications and
conditions; the service narrows a change of a condition to its owner or a
manager. Recording authority decisions, pinning the catalogue and changing the
roadmap need ``permits.manage``. Verifying a self-certified discharge needs
``permits.verify`` and is always four-eyes: the verifier is never the owner.
"""

from app.core.permissions import Role, permission_registry


def register_permit_permissions() -> None:
    """Register permissions for the permits module."""
    permission_registry.register_module_permissions(
        "permits",
        {
            "permits.read": Role.VIEWER,
            "permits.edit": Role.EDITOR,
            "permits.manage": Role.MANAGER,
            "permits.verify": Role.MANAGER,
            # Tenant permit-type catalogues.
            "permits.catalogue": Role.ADMIN,
        },
    )
