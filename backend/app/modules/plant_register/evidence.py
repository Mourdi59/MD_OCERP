# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC section 7).

Area ``m04_equipment`` at gate ``development_to_execution``: zero error-level
findings of rule set ``plant_register``; every critical item at least
``route_set`` with an approved decision paper; every long-lead item with one
fresh basis quote and either ordered or not past its latest order date; and
the frame document ``m04_equipment_frame`` attached to a CDE container.
One evidence item per condition, so the gate page says which one is missing.
Nothing for other areas or gates, nothing for a project without plant items.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "plant_register.m04_readiness"
AREA_CODE = "m04_equipment"
GATE_CODE = "development_to_execution"


async def m04_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.plant_register.repository import PlantRepository
    from app.modules.plant_register.service import PlantService

    if attempt.gate_code != GATE_CODE or area.code != AREA_CODE:
        return []
    if not await PlantRepository(session).items(project_id):
        return []
    r = await PlantService(session).readiness(project_id, today=datetime.now(UTC).date())
    link = ("plant_register", str(project_id))

    def item(code: str, ok: bool, detail: str) -> EvidenceItem:
        return EvidenceItem(
            code=f"plant:{code}",
            state="met" if ok else "not_met",
            label_key=f"plant.evidence.{code}",
            link=link,
            detail=detail,
        )

    return [
        item(
            "no_error_findings",
            not r["error_findings"],
            ", ".join(sorted({e["element_ref"] or "" for e in r["error_findings"]})),
        ),
        item("critical_route_set", not r["critical_open"], ", ".join(r["critical_open"])),
        item("long_lead_secured", not r["long_lead_open"], ", ".join(r["long_lead_open"])),
        item("frame_document_attached", r["frame_document_attached"], ""),
    ]


def register_gate_evidence() -> None:
    register_evidence_provider(AREA_CODE, m04_readiness, name=PROVIDER_NAME, blocking=True)
