# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1: the procurement concept at the gate that releases procurement.

One item, "concept submitted with no blocking finding", reported on the area
the governance catalogue tags as hosting procurement and only at the gate that
releases procurement (:mod:`hosting`; no area or gate is matched by code).
The item does not ask for an approved concept: the gate decision is the
approval, so asking for it would make the gate unpassable.

Registered blocking, and it never fails open:

* a project without a concept has nothing to report (no data, no item);
* a concept whose release gate cannot be resolved is ``unknown`` at every gate,
  because this module cannot tell which gate it should hold;
* when the catalogue tags no area for procurement, the item is reported on the
  first area of the project instead of being dropped.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "procurement_concept.concept_ready"
LABEL_KEY = "procurement_concept.evidence.concept_ready"


async def _anchor_area_code(session: Any, project_id: uuid.UUID, tagged: str | None) -> str | None:
    """The area the item is reported on: the tagged one, else the project's first area."""
    from app.modules.project_governance.models import GovernanceArea

    rows = (
        (
            await session.execute(
                select(GovernanceArea)
                .where(GovernanceArea.project_id == project_id, GovernanceArea.retired.is_(False))
                .order_by(GovernanceArea.sort_order, GovernanceArea.code)
            )
        )
        .scalars()
        .all()
    )
    live = [a for a in rows if getattr(a, "applicable", True)]
    if tagged is not None and any(a.code == tagged for a in live):
        return tagged
    return live[0].code if live else None


async def concept_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.procurement_concept.service import ProcurementConceptService

    svc = ProcurementConceptService(session)
    concept = await svc.find_concept(project_id)
    if concept is None:
        return []
    hosting = await svc.hosting(project_id)
    if area.code != await _anchor_area_code(session, project_id, hosting.area_code):
        return []
    link = ("procurement_concept", str(project_id))
    gate = await svc.release_gate(project_id, concept)
    if gate is None:
        return [
            EvidenceItem(
                code="procurement_concept_ready:release_gate_unresolved",
                state="unknown",
                label_key=LABEL_KEY,
                link=link,
                detail="release_gate_unresolved",
            )
        ]
    if attempt.gate_id != gate.id:
        return []
    ready = await svc.readiness(project_id)
    return [
        EvidenceItem(
            code=f"procurement_concept_ready:{attempt.gate_code}",
            state="met" if ready["ready_for_gate"] else "not_met",
            label_key=LABEL_KEY,
            link=link,
            detail=f"{ready['state']}; blocking={ready['blocking']}",
        )
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", concept_ready, name=PROVIDER_NAME, blocking=True)
