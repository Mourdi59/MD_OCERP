# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for governance area ``m10_quality`` (spec section 7).

Three items: the concept is approved, the plan has no error findings (rules 1
and 2), and every subject with a triggering activity has a planned before
survey. Asked only at ``development_to_execution`` gates. Registered blocking:
the frame document of this area is required at that gate, so a concept that
is not approved is a real blocker, not advice. Governance never imports this
module; it calls the registry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "quality_concept.readiness"
AREA_CODE = "m10_quality"
GATE_CODES = ("development_to_execution",)


async def quality_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.quality_concept.service import QualityConceptService

    if attempt.gate_code not in GATE_CODES:
        return []
    r = await QualityConceptService(session).readiness(project_id, datetime.now(UTC).date())
    link = ("quality_concept", str(project_id))
    return [
        EvidenceItem(
            code="quality_concept.approved",
            state="met" if r["approved"] else "not_met",
            label_key="quality_concept.evidence.approved",
            link=link,
        ),
        EvidenceItem(
            code="quality_concept.complete",
            state="met" if r["concept"] and not r["errors"] else "not_met",
            label_key="quality_concept.evidence.complete",
            link=link,
            detail=", ".join(sorted({e["code"] for e in r["errors"]})),
        ),
        EvidenceItem(
            code="quality_concept.preservation_planned",
            state="met" if r["concept"] and not r["preservation_unplanned"] else "not_met",
            label_key="quality_concept.evidence.preservation_planned",
            link=link,
            detail=", ".join(sorted({e["ref"] for e in r["preservation_unplanned"]})),
        ),
    ]


def register_gate_evidence() -> None:
    register_evidence_provider(AREA_CODE, quality_readiness, name=PROVIDER_NAME, blocking=True)
