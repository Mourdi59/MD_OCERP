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

The listing calls (``project_gates``, ``project_areas``, ``project_documents``)
answer small frozen read models for pickers and evidence providers, so no
module has to import this module's repository or ORM rows.

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

from app.modules.project_governance.catalogue import Catalogue, label_of
from app.modules.project_governance.catalogue_kinds import (
    host_subjects,
    phase_capabilities,
    register_host_subject,
    register_phase_capability,
)
from app.modules.project_governance.catalogue_store import resolve_catalogue
from app.modules.project_governance.repository import GovernanceRepository

__all__ = [
    "AreaView",
    "DocumentView",
    "GateView",
    "Host",
    "host_for",
    "host_in",
    "host_subjects",
    "phase_capabilities",
    "phases_enabling",
    "phases_enabling_in",
    "project_areas",
    "project_catalogue",
    "project_documents",
    "project_gates",
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


# ── listings ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateView:
    """One gate of a project's current phase model.

    Attributes:
        id: The gate row.
        code: Catalogue code of the gate; never match on it, use ``to_phase`` with ``phases_enabling``.
        label: ``{"key": i18n key or None, "text": {locale: text} or None}``, as the API returns it.
        order: Position among the project's gates, ascending.
        status: ``not_started``, ``in_preparation``, ``in_review``, ``on_hold`` or ``decided``.
        from_phase: Phase the gate leaves.
        to_phase: Phase the gate opens.
        last_outcome: Outcome of the latest decision, ``""`` before the first.
    """

    id: uuid.UUID
    code: str
    label: dict[str, Any]
    order: int
    status: str
    from_phase: str
    to_phase: str
    last_outcome: str


@dataclass(frozen=True)
class AreaView:
    """One management area of a project.

    Attributes:
        id: The area row.
        code: Catalogue code of the area; find the one you need with ``host_for``.
        label: ``{"key", "text"}`` as the API returns it; ``name_override`` wins when set.
        name_override: The project's own name for the area, ``""`` when none.
        order: Position among the project's areas, ascending.
        status: ``applicable`` or ``not_applicable``.
        owner_user_id: The area owner, if one is named.
        deputy_user_id: The deputy, if one is named.
    """

    id: uuid.UUID
    code: str
    label: dict[str, Any]
    name_override: str
    order: int
    status: str
    owner_user_id: uuid.UUID | None
    deputy_user_id: uuid.UUID | None


@dataclass(frozen=True)
class DocumentView:
    """One frame document of a project.

    Attributes:
        id: The document row.
        code: The document type code.
        label: ``{"key", "text"}`` as the API returns it.
        order: Position in the list, ascending (area order, then code).
        status: ``draft``, ``in_review``, ``approved_at_gate``, ``binding`` or ``superseded``.
        area_id: The area row the document belongs to.
        area_code: That area's code.
        required_at_gates: Codes of the gates that need this document.
        read_only: Frozen by a stop decision.
    """

    id: uuid.UUID
    code: str
    label: dict[str, Any]
    order: int
    status: str
    area_id: uuid.UUID
    area_code: str
    required_at_gates: tuple[str, ...]
    read_only: bool


_NO_LABEL: dict[str, Any] = {"key": None, "text": None}


def _label(items: Any, code: str) -> dict[str, Any]:
    for item in items:
        if item.code == code:
            return label_of(item.name_key, item.labels)
    return dict(_NO_LABEL)


def gate_views(catalogue: Any, rows: Any) -> tuple[GateView, ...]:
    """Read models of gate rows, in gate order."""
    ordered = sorted(rows, key=lambda g: (g.sort_order, g.code))
    return tuple(
        GateView(
            id=g.id,
            code=g.code,
            label=_label(catalogue.gates, g.code),
            order=index,
            status=g.status,
            from_phase=g.from_phase,
            to_phase=g.to_phase,
            last_outcome=g.last_outcome or "",
        )
        for index, g in enumerate(ordered, start=1)
    )


def area_views(catalogue: Any, rows: Any) -> tuple[AreaView, ...]:
    """Read models of area rows, in area order."""
    ordered = sorted(rows, key=lambda a: (a.sort_order, a.code))
    return tuple(
        AreaView(
            id=a.id,
            code=a.code,
            label=_label(catalogue.areas, a.code),
            name_override=a.name_override or "",
            order=index,
            status="applicable" if a.applicable else "not_applicable",
            owner_user_id=a.owner_user_id,
            deputy_user_id=a.deputy_user_id,
        )
        for index, a in enumerate(ordered, start=1)
    )


def document_views(catalogue: Any, rows: Any, areas: tuple[AreaView, ...]) -> tuple[DocumentView, ...]:
    """Read models of document rows, by area order and then document type."""
    by_id = {a.id: a for a in areas}
    kept = [d for d in rows if d.area_id in by_id]
    ordered = sorted(kept, key=lambda d: (by_id[d.area_id].order, d.doc_type))
    return tuple(
        DocumentView(
            id=d.id,
            code=d.doc_type,
            label=_label(catalogue.document_types, d.doc_type),
            order=index,
            status=d.status,
            area_id=d.area_id,
            area_code=by_id[d.area_id].code,
            required_at_gates=tuple(d.required_at_gates or ()),
            read_only=bool(d.read_only),
        )
        for index, d in enumerate(ordered, start=1)
    )


async def project_gates(session: AsyncSession, project_id: uuid.UUID) -> tuple[GateView, ...]:
    """The gates of the project's current phase model, in order; empty without a model.

    Gates of a model the project left (historic) are not listed.
    """
    catalogue = await project_catalogue(session, project_id)
    if catalogue is None:
        return ()
    return gate_views(catalogue, await GovernanceRepository(session).list_gates(project_id))


async def project_areas(session: AsyncSession, project_id: uuid.UUID) -> tuple[AreaView, ...]:
    """The management areas of the project, in order; empty without a model.

    Areas retired by a model change are not listed.
    """
    catalogue = await project_catalogue(session, project_id)
    if catalogue is None:
        return ()
    return area_views(catalogue, await GovernanceRepository(session).list_areas(project_id))


async def project_documents(session: AsyncSession, project_id: uuid.UUID) -> tuple[DocumentView, ...]:
    """The frame documents of the project's live areas; empty without a model."""
    catalogue = await project_catalogue(session, project_id)
    if catalogue is None:
        return ()
    repo = GovernanceRepository(session)
    areas = area_views(catalogue, await repo.list_areas(project_id))
    return document_views(catalogue, await repo.list_documents(project_id), areas)
