# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What other modules may read from a project's phase model, by tag and never by code.

Phase models name their phases, areas and documents differently, so a module
that matched ``"construction"`` or ``"m07_design_management"`` would work for
one model only. The catalogue says the same thing in data:

* a document type lists the subjects it ``hosts`` (``"design"``, ``"permits"``);
  the hosting area is the area that document belongs to;
* a phase lists what entering it ``enables`` (``"construction_start"``,
  ``"handover"``, ``"operation"``, ``"procurement"``).

Resolve at read time and store nothing: a project may move to another model.
Every function answers ``None`` or an empty tuple when the project has no model
or its model carries no such tag. A caller that blocks a gate must report that
as ``unknown``, never as met.

The tag vocabulary lives in :mod:`catalogue_kinds` (``register_host_subject``,
``register_phase_capability``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.project_governance.catalogue import Catalogue
from app.modules.project_governance.catalogue_kinds import (
    host_subjects,
    phase_capabilities,
    register_host_subject,
    register_phase_capability,
)
from app.modules.project_governance.catalogue_store import resolve_catalogue
from app.modules.project_governance.repository import GovernanceRepository

__all__ = [
    "Host",
    "host_for",
    "host_in",
    "host_subjects",
    "phase_capabilities",
    "phases_enabling",
    "phases_enabling_in",
    "project_catalogue",
    "register_host_subject",
    "register_phase_capability",
]


@dataclass(frozen=True)
class Host:
    """Where a subject lives in one phase model.

    Attributes:
        area_code: Code of the hosting area (the document type's own area).
        doc_type: Code of the frame document type the subject writes into.
    """

    area_code: str
    doc_type: str


def host_in(catalogue: Any, subject: str) -> Host | None:
    """The host of ``subject`` in a catalogue, or ``None`` when it tags none.

    Accepts a parsed :class:`Catalogue`. The validator guarantees at most one
    document type per subject, so the answer is never ambiguous.
    """
    doc = catalogue.host_of(subject)
    return Host(area_code=doc.area, doc_type=doc.code) if doc is not None else None


def phases_enabling_in(catalogue: Any, capability: str) -> tuple[str, ...]:
    """Codes of the phases whose entry enables ``capability``, in phase order; empty when none."""
    return tuple(p.code for p in catalogue.phases_enabling(capability))


async def project_catalogue(session: AsyncSession, project_id: uuid.UUID) -> Catalogue | None:
    """The phase model a project pinned, or ``None`` when it pinned none."""
    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await resolve_catalogue(
        session, model.catalogue_source, model.catalogue_id, model.catalogue_version, from_pin=True
    )


async def host_for(session: AsyncSession, project_id: uuid.UUID, subject: str) -> Host | None:
    """The host of ``subject`` in the project's pinned phase model.

    ``None`` when the project has no model or its model hosts the subject
    nowhere. A project pinned before its model gained the document type has no
    document row for it yet; the caller must treat a missing row as unknown.
    """
    catalogue = await project_catalogue(session, project_id)
    return host_in(catalogue, subject) if catalogue is not None else None


async def phases_enabling(session: AsyncSession, project_id: uuid.UUID, capability: str) -> tuple[str, ...]:
    """Phase codes of the project's pinned model whose entry enables ``capability``; empty when none."""
    catalogue = await project_catalogue(session, project_id)
    return phases_enabling_in(catalogue, capability) if catalogue is not None else ()
