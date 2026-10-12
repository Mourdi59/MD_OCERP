# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1: the procurement area at the gate that releases procurement.

For the procurement area (``m08_procurement`` in the module framework catalogue,
``contracts_procurement`` in the neutral one) and only at the concept's release
gate: one item "concept approved with no blocking finding". Nothing for other
areas or gates, and nothing for a project without a concept. Registered
blocking: procurement must not be released on a concept that has not passed
its own rules.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "procurement_concept.concept_ready"
AREA_CODES = ("m08_procurement", "contracts_procurement")


async def concept_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.procurement_concept.service import ProcurementConceptService

    svc = ProcurementConceptService(session)
    concept = await svc.find_concept(project_id)
    if concept is None or attempt.gate_code != concept.release_gate_code:
        return []
    ready = await svc.readiness(project_id)
    met = ready["approved"] and ready["blocking"] == 0
    return [
        EvidenceItem(
            code=f"procurement_concept_ready:{attempt.gate_code}",
            state="met" if met else "not_met",
            label_key="procurement_concept.evidence.concept_ready",
            link=("procurement_concept", str(project_id)),
            detail=f"{ready['state']}; blocking={ready['blocking']}",
        )
    ]


def register_gate_evidence() -> None:
    for code in AREA_CODES:
        register_evidence_provider(code, concept_ready, name=f"{PROVIDER_NAME}:{code}", blocking=True)
