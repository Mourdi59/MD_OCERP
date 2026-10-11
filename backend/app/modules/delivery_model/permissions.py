# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Delivery model permission definitions.

Approval is not a permission of this module: the decision is approved by the
governance gate decision on the contracts area (lead decision 2), whose
deciders the gate's approval route entitles. ``delivery_model.edit`` opens the
comparison, matrix, package plan and owner-furnished items; pinning a
catalogue and proposing a decision need ``delivery_model.manage``.
"""

from app.core.permissions import Role, permission_registry


def register_delivery_model_permissions() -> None:
    """Register permissions for the delivery model module."""
    permission_registry.register_module_permissions(
        "delivery_model",
        {
            "delivery_model.read": Role.VIEWER,
            "delivery_model.edit": Role.EDITOR,
            "delivery_model.manage": Role.MANAGER,
        },
    )
