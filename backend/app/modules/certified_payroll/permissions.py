# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Certified payroll permission definitions.

A certified payroll carries what individual people were paid, so it is
manager-scoped throughout, exactly like the payroll module it sits on. Read
access is restricted for the same reason: this is wage data about named people,
not a project statistic.

Certifying is separated from managing because it is a different act. Editing a
draft week is bookkeeping; signing a statement of compliance is a personal legal
assertion by the person who signs, and it should be possible to grant somebody
the first without the second.
"""

from app.core.permissions import Role, permission_registry


def register_certified_payroll_permissions() -> None:
    """Register permissions for the Certified Payroll module."""
    permission_registry.register_module_permissions(
        "certified_payroll",
        {
            "certified_payroll.read": Role.MANAGER,
            "certified_payroll.manage": Role.MANAGER,
            # Signing the statement of compliance. Kept apart from ``manage``
            # so preparing a week and certifying it can be different people.
            "certified_payroll.certify": Role.MANAGER,
        },
    )
