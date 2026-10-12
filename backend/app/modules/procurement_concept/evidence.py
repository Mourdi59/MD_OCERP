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

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider
from app.modules.project_governance.public import project_areas

PROVIDER_NAME = "procurement_concept.concept_ready"
LABEL_KEY = "procurement_concept.evidence.concept_ready"


async def _anchor_area_code(session: Any, project_id: uuid.UUID, tagged: str | None) -> str | None:
    """The area the item is reported on: the tagged one, else the project's first area."""
    live = [a for a in await project_areas(session, project_id) if a.status == "applicable"]
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
    link = ("procurement_concept", str(project_id))
    anchor = await _anchor_area_code(session, project_id, hosting.area_code)
    if anchor is None:
        # Governance lists no applicable area for the project (it pinned no phase model, or every area is
        # switched off), so there is no area to report on. Whoever asks gets the reason, not silence.
        return [
            EvidenceItem(
                code="procurement_concept_ready:procurement_area_unresolved",
                state="unknown",
                label_key=LABEL_KEY,
                link=link,
                detail="procurement_area_unresolved",
            )
        ]
    if area.code != anchor:
        return []
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
    if await svc._frame_document(project_id, concept) is None:
        # The model hosts procurement nowhere, or the project has no document row for the host yet (it was
        # pinned before the model gained it), and no document is named on the concept. Nothing could approve
        # the concept, so the answer is not "met".
        return [
            EvidenceItem(
                code=f"procurement_concept_ready:{attempt.gate_code}",
                state="unknown",
                label_key=LABEL_KEY,
                link=link,
                detail="frame_document_unresolved",
            )
        ]
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
