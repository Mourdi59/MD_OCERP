# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Everything the economics module reads from a project's governance model, through its read port.

Governance models name their areas, documents and gates differently, so this
module never matches one by a literal code. The governance catalogue says it as
data: the document type that ``hosts`` the subject ``economics`` is the frame
document that carries the business case, the cost frame and the financing plan
(the carrier). Its area is the area whose gate approves them. A project whose
model hosts the subject nowhere has no gate to approve with and refuses with a
coded error rather than approving on another document.

This is the only file of the module that reads governance, and it reads
nothing but :mod:`app.modules.project_governance.public`.
"""

from __future__ import annotations

import uuid
from typing import Any

CARRIER_TAG = "economics"

NO_GOVERNANCE_MODEL = "governance_model_missing"
NO_CARRIER = "carrier_missing"


async def carrier_document(session: Any, project_id: uuid.UUID) -> tuple[Any | None, str | None]:
    """``(carrier document view, None)`` or ``(None, reason)`` when the project has none."""
    from app.modules.project_governance import public

    catalogue = await public.project_catalogue(session, project_id)
    if catalogue is None:
        return None, NO_GOVERNANCE_MODEL
    host = public.host_in(catalogue, CARRIER_TAG)
    if host is None:
        return None, NO_CARRIER
    doc = next((d for d in await public.project_documents(session, project_id) if d.code == host.doc_type), None)
    return (doc, None) if doc is not None else (None, NO_CARRIER)


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


async def first_applicable_area_id(session: Any, project_id: uuid.UUID) -> uuid.UUID | None:
    """The first area a gate asks, in display order: where a project-wide ``unknown`` is reported once."""
    from app.modules.project_governance import public

    asked = [a for a in await public.project_areas(session, project_id) if a.status == "applicable"]
    return asked[0].id if asked else None


async def four_eyes(session: Any, project_id: uuid.UUID) -> bool:
    """The four-eyes setting of the project's governance model; on when the project has no model."""
    from app.modules.project_governance import public

    return (await public.project_controls(session, project_id)).four_eyes


async def gates_in_use(session: Any, project_id: uuid.UUID) -> bool:
    """Whether the project has gates at all. A project that never adopted a phase model has none."""
    from app.modules.project_governance import public

    return bool(await public.project_gates(session, project_id))
