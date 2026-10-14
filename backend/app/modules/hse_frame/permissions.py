# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""HSE frame permission definitions.

``hse_frame.manage`` changes what a governance gate reads (the pinned
catalogue, the facts that trigger duties, the frame's state); ``approve`` is
the second signature on the frame and the service adds four-eyes on top.
"""

from app.core.permissions import Role, permission_registry


def register_hse_frame_permissions() -> None:
    """Register permissions for the HSE frame module."""
    permission_registry.register_module_permissions(
        "hse_frame",
        {
            "hse_frame.read": Role.VIEWER,
            "hse_frame.edit": Role.EDITOR,
            "hse_frame.manage": Role.MANAGER,
            "hse_frame.approve": Role.MANAGER,
        },
    )
