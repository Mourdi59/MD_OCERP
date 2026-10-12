# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Stakeholders permission definitions.

Deciding a commitment to a stakeholder is not a permission: the mandate matrix
names the deciding role, and the service checks that the caller holds it.
``stakeholders.read_personal`` opens names of private persons (neighbours, the
public); without it lists and exports mask them (decision m). Roles never
grant platform permissions or project access (decision l).
"""

from app.core.permissions import Role, permission_registry


def register_stakeholder_permissions() -> None:
    """Register permissions for the stakeholders module."""
    permission_registry.register_module_permissions(
        "stakeholders",
        {
            "stakeholders.read": Role.VIEWER,
            "stakeholders.edit": Role.EDITOR,
            "stakeholders.read_personal": Role.MANAGER,
            # Roles, bodies and the mandate matrix: who decides what on this project.
            "organisation.manage": Role.MANAGER,
            # Tenant stakeholder frameworks.
            "stakeholders.catalogue": Role.ADMIN,
        },
    )
