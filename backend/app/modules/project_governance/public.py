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

import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.project_governance.catalogue import Catalogue, InvalidCatalogueError, label_of
from app.modules.project_governance.catalogue_kinds import (
    host_subjects,
    phase_capabilities,
    register_host_subject,
    register_phase_capability,
)
from app.modules.project_governance.catalogue_packs import CataloguePin, demo_module_story
from app.modules.project_governance.catalogue_store import default_catalogue_pin, resolve_catalogue
from app.modules.project_governance.errors import GovernanceError
from app.modules.project_governance.repository import GovernanceRepository
from app.modules.project_governance.seed_story import text_of as story_text

logger = logging.getLogger(__name__)

__all__ = [
    "AreaView",
    "area_views",
    "CataloguePin",
    "change_request_views",
    "condition_views",
    "control_settings",
    "ControlSettings",
    "story_text",
    "decision_views",
    "demo_module_story",
    "document_views",
    "gate_views",
    "ChangeRequestView",
    "ConditionView",
    "DecisionView",
    "DocumentView",
    "GateView",
    "Host",
    "default_catalogue_pin",
    "host_for",
    "host_in",
    "host_subjects",
    "phase_capabilities",
    "phases_enabling",
    "phases_enabling_in",
    "project_areas",
    "project_catalogue",
    "project_controls",
    "project_change_requests",
    "project_conditions",
    "project_documents",
    "project_gate_decisions",
    "project_gates",
    "register_host_subject",
    "register_phase_capability",
    "user_can_access_project",
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
    try:
        return await resolve_catalogue(
            session, model.catalogue_source, model.catalogue_id, model.catalogue_version, from_pin=True
        )
    except (GovernanceError, InvalidCatalogueError) as exc:
        # A pack that was removed, a pack file that no longer loads, a stored version the rules
        # refuse today. Every reader of this port treats None as "no model", which is what the
        # project has until somebody repairs the pin; raising would be a 500 in each of them.
        logger.warning(
            "project %s pins %s:%s@%s, which does not resolve: %s",
            project_id,
            model.catalogue_source,
            model.catalogue_id,
            model.catalogue_version,
            exc,
        )
        return None


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
        target_date: When the gate is planned: the linked schedule activity's date, else the
            gate's own; ``None`` when neither is set.
    """

    id: uuid.UUID
    code: str
    label: dict[str, Any]
    order: int
    status: str
    from_phase: str
    to_phase: str
    last_outcome: str
    target_date: date | None = None


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
        container_id: The document container holding its revisions, if one is attached.
        bound_revision_id: The revision in force, once a gate approved the document.
        approved_gate_id: The gate (``GateView.id``) whose decision approved it.
        bound_content_hash: Content hash of the bound revision as recorded when the gate approved it.
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
    container_id: uuid.UUID | None = None
    bound_revision_id: uuid.UUID | None = None
    approved_gate_id: uuid.UUID | None = None
    bound_content_hash: str | None = None


@dataclass(frozen=True)
class ControlSettings:
    """The project-wide controls other modules have to respect.

    Attributes:
        has_model: The project pinned a phase model.
        four_eyes: Whoever prepared or owns a thing must not be the one who approves it.
            ``True`` when the project has no model: a control is on until somebody with
            the authority switches it off.
        current_phase: Code of the phase the project is in; ``None`` without a model.
        stopped: A stop decision ended the project; nothing is submitted or decided any more.
    """

    has_model: bool
    four_eyes: bool
    current_phase: str | None
    stopped: bool


def control_settings(model: Any) -> ControlSettings:
    """Read model of a governance model row, or of its absence."""
    if model is None:
        return ControlSettings(has_model=False, four_eyes=True, current_phase=None, stopped=False)
    return ControlSettings(
        has_model=True,
        four_eyes=bool(model.four_eyes),
        current_phase=model.current_phase or None,
        stopped=bool(getattr(model, "stopped", False)),
    )


async def project_controls(session: AsyncSession, project_id: uuid.UUID) -> ControlSettings:
    """Four-eyes, the current phase and the stop flag of a project. Never raises for a project without a model."""
    return control_settings(await GovernanceRepository(session).get_model(project_id))


@dataclass(frozen=True)
class DecisionView:
    """One recorded decision on a gate. Decisions are immutable; a reopened gate gets a further one.

    Attributes:
        id: The decision row.
        gate_id: The gate decided.
        gate_code: That gate's code.
        attempt_no: Which attempt of the gate it closed.
        outcome: ``go``, ``go_with_conditions``, ``hold``, ``recycle`` or ``stop``.
        decided_by: The decider.
        decided_at: When it was recorded.
    """

    id: uuid.UUID
    gate_id: uuid.UUID
    gate_code: str
    attempt_no: int
    outcome: str
    decided_by: uuid.UUID
    decided_at: datetime


@dataclass(frozen=True)
class ConditionView:
    """One condition attached to a go-with-conditions decision.

    Attributes:
        id: The condition row.
        decision_id: The decision it belongs to.
        gate_id: The gate of that decision.
        gate_code: That gate's code.
        text: What has to be done.
        status: As of today: ``open``, ``overdue``, ``cleared`` or ``waived``. An open condition
            past its due date reads ``overdue`` whether or not the escalation job has run.
        severity: ``critical``, ``essential`` or ``recommended``.
        area_code: The area concerned, if one was named.
        document_type: The document type concerned, if one was named.
        owner_user_id: Who has to clear it.
        due_date: Until when, if a date was set.
        cleared_at: When it was cleared, for a cleared condition.
    """

    id: uuid.UUID
    decision_id: uuid.UUID
    gate_id: uuid.UUID
    gate_code: str
    text: str
    status: str
    severity: str
    area_code: str | None
    document_type: str | None
    owner_user_id: uuid.UUID | None
    due_date: date | None
    cleared_at: datetime | None


@dataclass(frozen=True)
class ChangeRequestView:
    """One request to make a newer revision of a binding document binding.

    Attributes:
        id: The change request row.
        document_id: The document (``DocumentView.id``).
        status: ``submitted`` while the route runs, then ``approved`` or ``rejected``.
        open: Whether it is still undecided; at most one per document is.
        reason: Why the change is asked for.
        proposed_revision_id: The revision that would become binding.
        requested_by: Who raised it.
        decided_by: Who closed it on the route; ``None`` while it is open.
        decided_at: When the route closed it.
    """

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    open: bool
    reason: str
    proposed_revision_id: uuid.UUID | None
    requested_by: uuid.UUID | None
    decided_at: datetime | None
    decided_by: uuid.UUID | None = None


def _day(value: Any) -> date | None:
    """A stored ISO day as a date; ``None`` for an empty or unreadable value."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


_NO_LABEL: dict[str, Any] = {"key": None, "text": None}


def _label(items: Any, code: str) -> dict[str, Any]:
    for item in items:
        if item.code == code:
            return label_of(item.name_key, item.labels)
    return dict(_NO_LABEL)


def gate_views(catalogue: Any, rows: Any, target_dates: Mapping[uuid.UUID, Any] | None = None) -> tuple[GateView, ...]:
    """Read models of gate rows, in gate order.

    ``target_dates`` carries the planned day per gate id where the schedule
    owns it; without it the gate's own stored date is read.
    """
    planned = target_dates or {}
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
            # The linked activity's day; the gate's own when it is not linked or the activity has none.
            target_date=_day(planned.get(g.id) or getattr(g, "target_date", None)),
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
            container_id=getattr(d, "container_id", None),
            bound_revision_id=getattr(d, "bound_revision_id", None),
            approved_gate_id=getattr(d, "approved_gate_id", None),
            bound_content_hash=getattr(d, "bound_content_hash", None) or None,
        )
        for index, d in enumerate(ordered, start=1)
    )


async def project_gates(session: AsyncSession, project_id: uuid.UUID) -> tuple[GateView, ...]:
    """The gates of the project's current phase model, in order; empty without a model.

    Gates of a model the project left (historic) are not listed.
    """
    from app.modules.project_governance.service import GovernanceService

    catalogue = await project_catalogue(session, project_id)
    if catalogue is None:
        return ()
    rows = await GovernanceRepository(session).list_gates(project_id)
    return gate_views(catalogue, rows, await GovernanceService(session).gate_target_dates(rows))


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


def decision_views(rows: Any) -> tuple[DecisionView, ...]:
    """Read models of decision rows, oldest first."""
    ordered = sorted(rows, key=lambda d: (d.decided_at, d.attempt_no))
    return tuple(
        DecisionView(
            id=d.id,
            gate_id=d.gate_id,
            gate_code=d.gate_code,
            attempt_no=d.attempt_no,
            outcome=d.outcome,
            decided_by=d.decided_by,
            decided_at=d.decided_at,
        )
        for d in ordered
    )


def condition_views(rows: Any, today: date) -> tuple[ConditionView, ...]:
    """Read models of condition rows with their status as of ``today``, by due date and then text."""
    from app.modules.project_governance.service import effective_condition_status

    views = [
        ConditionView(
            id=c.id,
            decision_id=c.decision_id,
            gate_id=c.gate_id,
            gate_code=c.gate_code,
            text=c.text,
            status=effective_condition_status(c, today),
            severity=c.severity,
            area_code=c.area_code,
            document_type=c.document_type,
            owner_user_id=c.owner_user_id,
            due_date=_day(c.due_date),
            cleared_at=c.cleared_at,
        )
        for c in rows
    ]
    return tuple(sorted(views, key=lambda v: (v.due_date is None, v.due_date or date.max, v.text, str(v.id))))


def change_request_views(rows: Any) -> tuple[ChangeRequestView, ...]:
    """Read models of change request rows, in the order given (oldest first from the repository)."""
    return tuple(
        ChangeRequestView(
            id=r.id,
            document_id=r.document_id,
            status=r.status,
            open=r.status == "submitted",
            reason=r.reason or "",
            proposed_revision_id=r.proposed_revision_id,
            requested_by=r.requested_by,
            decided_at=r.decided_at,
            decided_by=r.decided_by,
        )
        for r in rows
    )


def rows_of_gates(rows: Iterable[Any], current: Any, *, asked: uuid.UUID | None = None) -> list[Any]:
    """Rows of the gates of the current phase model, or of the one gate that was asked for.

    Without ``asked``, rows of a gate the project left with its earlier model
    are dropped, as :func:`project_gates` drops the gate itself. A caller that
    names a gate gets that gate's rows, historic or not.
    """
    if asked is not None:
        return [r for r in rows if r.gate_id == asked]
    return [r for r in rows if r.gate_id in current]


async def _current_gate_ids(repo: GovernanceRepository, project_id: uuid.UUID) -> frozenset[uuid.UUID]:
    return frozenset(g.id for g in await repo.list_gates(project_id))


async def project_gate_decisions(
    session: AsyncSession, project_id: uuid.UUID, gate_id: uuid.UUID | None = None
) -> tuple[DecisionView, ...]:
    """Decisions of one gate, or of every gate of the project, oldest first.

    A gate id of another project lists nothing: the project filter always applies.
    """
    repo = GovernanceRepository(session)
    rows = await repo.list_decisions(project_id, gate_id)
    return decision_views(rows_of_gates(rows, await _current_gate_ids(repo, project_id), asked=gate_id))


async def project_conditions(
    session: AsyncSession, project_id: uuid.UUID, gate_id: uuid.UUID | None = None
) -> tuple[ConditionView, ...]:
    """Conditions of one gate, or of the whole project, with their status as of the server's today."""
    from app.modules.project_governance.service import server_today

    repo = GovernanceRepository(session)
    rows, _ = await repo.list_conditions(project_id)
    rows = rows_of_gates(rows, await _current_gate_ids(repo, project_id), asked=gate_id)
    return condition_views(rows, server_today())


async def project_change_requests(
    session: AsyncSession, project_id: uuid.UUID, document_id: uuid.UUID | None = None, *, open_only: bool = False
) -> tuple[ChangeRequestView, ...]:
    """Change requests of one document, or of the whole project, oldest first.

    With ``open_only`` only the undecided ones, which is what a steering check
    before touching a binding document needs.
    """
    views = change_request_views(await GovernanceRepository(session).list_change_requests(project_id, document_id))
    return tuple(v for v in views if v.open) if open_only else views


async def user_can_access_project(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Whether a user may be named on this project: its owner, a member of one of its teams, or an admin.

    The same answer governance uses before it accepts an area owner or a
    condition owner. ``False`` for an unknown project or user.
    """
    from app.modules.project_governance.service import GovernanceService

    return await GovernanceService(session).user_can_access_project(project_id, user_id)
