# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where staffing lives in a project's governance model, read through the governance port.

Governance models name their phases, gates, areas and documents differently,
so this module never matches one by its code. The catalogue says it as data: a
document type lists what it hosts (``hosts: ["staffing"]``) and a phase lists
what entering it enables (``enables: ["construction_start"]``). Everything is
resolved when it is read; no resolved code is stored.

A project without a governance model, or a model that hosts staffing nowhere,
answers ``None`` / empty, and the callers say so (an ``unknown`` evidence
item, a refused submission) instead of guessing.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance import public as governance

SUBJECT = "staffing"


def host(catalogue: Any) -> governance.Host | None:
    """The area and frame document type that host staffing in this catalogue, or ``None``."""
    return governance.host_in(catalogue, SUBJECT) if catalogue is not None else None


def enabled_by(catalogue: Any, phase_code: str | None) -> frozenset[str]:
    """What entering the phase ``phase_code`` enables: the capabilities a gate into it stands for."""
    if catalogue is None or not phase_code:
        return frozenset()
    return frozenset(
        capability
        for capability in governance.phase_capabilities()
        if phase_code in governance.phases_enabling_in(catalogue, capability)
    )


def enabled_tags(catalogue: Any) -> frozenset[str]:
    """Every capability some phase of the catalogue enables."""
    if catalogue is None:
        return frozenset()
    return frozenset(c for c in governance.phase_capabilities() if governance.phases_enabling_in(catalogue, c))


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue, or ``None`` without a governance model."""
    return await governance.project_catalogue(session, project_id)


async def gates_in_use(session: Any, project_id: uuid.UUID) -> bool:
    """Whether the project has gates at all. A project that never adopted a phase model has none.

    Asked of the gates and not of the model: a pinned model that cannot be read
    leaves its gates on the project, and there approval still belongs to them.
    """
    return bool(await governance.project_gates(session, project_id))


async def four_eyes(session: Any, project_id: uuid.UUID) -> bool:
    """The four-eyes setting of the project's governance model; on when the project has no model."""
    return (await governance.project_controls(session, project_id)).four_eyes
