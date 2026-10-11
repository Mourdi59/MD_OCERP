# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project governance permission definitions.

``governance.decide`` is the floor, not the grant: holding it lets a user ask
to decide, and the approval route of the gate then says whether this user may.
``governance.edit`` lets an editor work on documents and checks; the service
narrows readiness attestation further to the owner or deputy of the area.
"""

from app.core.permissions import Role, permission_registry


def register_governance_permissions() -> None:
    """Register permissions for the project governance module."""
    permission_registry.register_module_permissions(
        "project_governance",
        {
            "governance.read": Role.VIEWER,
            "governance.edit": Role.EDITOR,
            # Setting or changing the phase model, assigning area owners and
            # switching four-eyes off are project management acts.
            "governance.manage": Role.MANAGER,
            "governance.decide": Role.MANAGER,
        },
    )
