# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the delivery decision lives in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently, so this
module never matches one by a literal code. The governance catalogue says it
as data:

* a document type tagged ``hosts: ["delivery_model"]`` is the frame document
  that carries the delivery decision record (the carrier). Its area is the
  area whose gate approves the decision.
* a phase tagged ``enables: ["procurement"]`` is entered through the gate that
  releases procurement.

Both are read through the governance catalogue's own accessors
(``host_of`` and ``phases_enabling``) at read time against the catalogue the
project pins now, never stored. A project whose governance model tags no carrier has no way to
approve a delivery decision: callers refuse with a coded error instead of
falling back to another document of the area.
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


def carrier_document_type(catalogue: Any) -> str | None:
    """Code of the document type that hosts the delivery decision, or ``None`` when the model names none.

    Governance validates that a subject is hosted by at most one document type.
    """
    doc = catalogue.host_of(CARRIER_TAG)
    return doc.code if doc is not None else None


def procurement_gate_codes(catalogue: Any) -> tuple[str, ...]:
    """Codes of the gates leading into a phase tagged as enabling procurement."""
    phases = {p.code for p in catalogue.phases_enabling(PROCUREMENT_TAG)}
    return tuple(g.code for g in catalogue.gates if g.to_phase in phases)


async def governance_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The governance catalogue the project pins, or ``None`` without a governance model."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)


async def carrier_document(session: Any, project_id: uuid.UUID) -> tuple[Any | None, str | None]:
    """``(carrier frame document, None)`` or ``(None, reason)`` when the project has none."""
    from app.modules.project_governance.models import GovernanceDocument

    catalogue = await governance_catalogue(session, project_id)
    if catalogue is None:
        return None, NO_GOVERNANCE_MODEL
    doc_type = carrier_document_type(catalogue)
    if doc_type is None:
        return None, NO_CARRIER
    stmt = select(GovernanceDocument).where(
        GovernanceDocument.project_id == project_id, GovernanceDocument.doc_type == doc_type
    )
    doc = (await session.execute(stmt)).scalars().first()
    return (doc, None) if doc is not None else (None, NO_CARRIER)


async def released_procurement(session: Any, project_id: uuid.UUID, outcomes: tuple[str, ...]) -> bool | None:
    """Has a gate into a procurement-enabling phase been passed? ``None`` when no phase carries the tag."""
    from app.modules.project_governance.models import GovernanceGate

    catalogue = await governance_catalogue(session, project_id)
    if catalogue is None:
        return None
    codes = procurement_gate_codes(catalogue)
    if not codes:
        return None
    stmt = select(GovernanceGate.id).where(
        GovernanceGate.project_id == project_id,
        GovernanceGate.code.in_(codes),
        GovernanceGate.historic.is_(False),
        GovernanceGate.last_outcome.in_(outcomes),
    )
    return (await session.execute(stmt)).first() is not None
