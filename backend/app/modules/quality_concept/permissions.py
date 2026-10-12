# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Quality concept permission definitions.

Stage release is not a permission here: it stays construction_control's hold
gate release, with its party-role check. ``quality_concept.waive`` is the floor
for waiving a proof; the service adds four-eyes (approver != requester).
"""

from app.core.permissions import Role, permission_registry


def register_quality_concept_permissions() -> None:
    """Register permissions for the quality concept module."""
    permission_registry.register_module_permissions(
        "quality_concept",
        {
            "quality_concept.read": Role.VIEWER,
            "quality_concept.edit": Role.EDITOR,
            "quality_concept.waive": Role.MANAGER,
        },
    )
