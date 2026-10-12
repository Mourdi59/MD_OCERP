# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Everything the delivery model reads from a project's governance model, through its read port.

Governance models name their areas, documents and gates differently, so this
module never matches one by a literal code. The governance catalogue says it
as data, and :mod:`app.modules.project_governance.public` answers it:

* the document type that ``hosts`` the subject ``delivery_model`` is the frame
  document that carries the delivery decision record (the carrier). Its area
  is the area whose gate approves the decision.
* a phase that ``enables`` ``procurement`` is entered through the gate that
  releases procurement.

Both are resolved at read time against the model the project pins now, never
stored. A project whose governance model hosts the delivery model nowhere has
no way to approve a delivery decision: callers refuse with a coded error
instead of falling back to another document of the area.

This is the only file of the module that reads governance. Two facts are not
on the port yet and are read narrowly here: the four-eyes setting of the
project's governance model and the content hash of the bound revision.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

CARRIER_TAG = "delivery_model"
PROCUREMENT_TAG = "procurement"

# Reasons a project has no carrier document, as the API reports them.
NO_GOVERNANCE_MODEL = "governance_model_missing"
NO_CARRIER = "carrier_missing"


async def carrier_document(session: Any, project_id: uuid.UUID) -> tuple[Any | None, str | None]:
    """``(carrier document view, None)`` or ``(None, reason)`` when the project has none.

    The host can exist while the project has no document row for it (a project
    pinned before its model gained the document type): that is no carrier either.
    """
    from app.modules.project_governance import public

    catalogue = await public.project_catalogue(session, project_id)
    if catalogue is None:
        return None, NO_GOVERNANCE_MODEL
    host = public.host_in(catalogue, CARRIER_TAG)
    if host is None:
        return None, NO_CARRIER
    doc = next((d for d in await public.project_documents(session, project_id) if d.code == host.doc_type), None)
    return (doc, None) if doc is not None else (None, NO_CARRIER)


def procurement_state(
    phases: tuple[str, ...], gates: tuple[Any, ...], outcomes: tuple[str, ...]
) -> tuple[bool | None, tuple[str, ...]]:
    """``(released, guarding gate codes)`` from the phases that enable procurement and the project's gates.

    ``released`` is ``None`` when no phase says where procurement starts. A
    tagged phase no gate leads into is the phase the model starts in:
    procurement is enabled from the first day and no gate guards it.
    """
    if not phases:
        return None, ()
    guarding = tuple(g for g in gates if g.to_phase in phases)
    entered = {g.to_phase for g in gates}
    from_start = any(p not in entered for p in phases)
    return from_start or any(g.last_outcome in outcomes for g in guarding), tuple(g.code for g in guarding)


async def procurement(
    session: Any, project_id: uuid.UUID, outcomes: tuple[str, ...]
) -> tuple[bool | None, tuple[str, ...]]:
    """:func:`procurement_state` of the project's pinned governance model."""
    from app.modules.project_governance import public

    phases = await public.phases_enabling(session, project_id, PROCUREMENT_TAG)
    gates = await public.project_gates(session, project_id) if phases else ()
    return procurement_state(phases, gates, outcomes)


async def released_procurement(session: Any, project_id: uuid.UUID, outcomes: tuple[str, ...]) -> bool | None:
    """Is procurement released? ``None`` when no phase of the model carries the tag."""
    return (await procurement(session, project_id, outcomes))[0]


async def change_requests(session: Any, project_id: uuid.UUID, document_id: uuid.UUID) -> tuple[Any, ...]:
    """Change requests on one document, oldest first."""
    from app.modules.project_governance import public

    return await public.project_change_requests(session, project_id, document_id)


async def open_change_request(session: Any, project_id: uuid.UUID, document_id: uuid.UUID) -> uuid.UUID | None:
    """The undecided change request on the document, if there is one."""
    return next((cr.id for cr in await change_requests(session, project_id, document_id) if cr.open), None)


async def latest_gate_decision(
    session: Any, project_id: uuid.UUID, gate_id: uuid.UUID, outcomes: tuple[str, ...]
) -> Any | None:
    """The newest decision on the gate with one of ``outcomes``."""
    from app.modules.project_governance import public

    passed = [d for d in await public.project_gate_decisions(session, project_id, gate_id) if d.outcome in outcomes]
    return max(passed, key=lambda d: d.decided_at, default=None)


async def area(session: Any, project_id: uuid.UUID, area_id: uuid.UUID) -> Any | None:
    from app.modules.project_governance import public

    return next((a for a in await public.project_areas(session, project_id) if a.id == area_id), None)


async def first_applicable_area_id(session: Any, project_id: uuid.UUID) -> uuid.UUID | None:
    """The first area a gate asks, in display order: where a project-wide ``unknown`` is reported once."""
    from app.modules.project_governance import public

    asked = [a for a in await public.project_areas(session, project_id) if a.status == "applicable"]
    return asked[0].id if asked else None


async def four_eyes(session: Any, project_id: uuid.UUID) -> bool:
    """The four-eyes setting of the project's governance model; on when the project has no model."""
    from app.modules.project_governance.models import GovernanceModel

    setting = (
        await session.execute(select(GovernanceModel.four_eyes).where(GovernanceModel.project_id == project_id))
    ).scalar_one_or_none()
    return True if setting is None else bool(setting)


async def revision_content_hash(session: Any, revision_id: uuid.UUID | None) -> str | None:
    """Content hash of a document revision, as the document store recorded it."""
    from app.modules.cde.models import DocumentRevision

    if revision_id is None:
        return None
    return (
        await session.execute(select(DocumentRevision.content_hash).where(DocumentRevision.id == revision_id))
    ).scalar_one_or_none()
