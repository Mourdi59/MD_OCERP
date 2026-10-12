# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where quality lives in a project's phase model, read through the governance port.

A phase model says which frame document hosts a subject and which phase
enables a capability. This module asks for the subject ``quality`` and the
capability ``construction_start`` and never names an area, a document type, a
phase or a gate by code. Everything is resolved at read time; nothing resolved
is stored. ``None`` or an empty answer means the model does not say, and the
callers report that as unknown, never as met.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance import public

SUBJECT = "quality"
CONSTRUCTION_START = "construction_start"


def host(catalogue: Any) -> public.Host | None:
    """The area and frame document type hosting quality in ``catalogue``, or ``None``."""
    return public.host_in(catalogue, SUBJECT)


def phases_enabling(catalogue: Any, capability: str) -> frozenset[str]:
    """Codes of the phases whose entry enables ``capability``; empty when the catalogue tags none."""
    return frozenset(public.phases_enabling_in(catalogue, capability))


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned phase model, or ``None`` without one."""
    return await public.project_catalogue(session, project_id)


async def project_host(session: Any, project_id: uuid.UUID) -> public.Host | None:
    """The host of quality in the project's pinned phase model, or ``None``."""
    catalogue = await project_catalogue(session, project_id)
    return host(catalogue) if catalogue is not None else None
