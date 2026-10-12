# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where design lives in a project's phase model: asked from module 1's read port, never matched by code.

A phase model tags one frame document type with the subject ``design``; the
hosting area is that document's own area. Resolved at read time, nothing is
stored: a project may move to another model.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.public import Host, host_for, host_in

#: The subject design management asks the phase model for.
DESIGN_SUBJECT = "design"


def design_host_in(catalogue: Any) -> Host | None:
    """The host of design in a parsed catalogue, or ``None`` when it tags none."""
    return host_in(catalogue, DESIGN_SUBJECT)


async def design_host(session: Any, project_id: uuid.UUID) -> Host | None:
    """The host of design in the project's pinned phase model; ``None`` without a model or a tag."""
    return await host_for(session, project_id, DESIGN_SUBJECT)


__all__ = ["DESIGN_SUBJECT", "Host", "design_host", "design_host_in"]
