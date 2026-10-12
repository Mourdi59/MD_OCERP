# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1: area ``m06_logistics`` at ``development_to_execution``.

One BLOCKING provider, registered for the area code. It answers only for the
gate ``development_to_execution`` (the gate at which the catalogue requires
frame document ``m06_logistics_frame``) and only once the project has started a
logistics plan, so a project that never opened the plan is not blocked by an
empty one. Each readiness item of :meth:`LogisticsPlanService.readiness`
becomes one evidence item, so the gate page lists every open point.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER = "site_logistics.m06_readiness"
AREA = "m06_logistics"
GATE = "development_to_execution"


async def logistics_readiness(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    """Evidence items for the logistics area of a gate attempt."""
    from sqlalchemy import select

    from app.modules.site_logistics.models import LogisticsConcept
    from app.modules.site_logistics.plan_service import LogisticsPlanService

    if getattr(area, "code", None) != AREA or attempt.gate_code != GATE:
        return []
    started = (
        await session.execute(select(LogisticsConcept.id).where(LogisticsConcept.project_id == project_id))
    ).scalar_one_or_none()
    if started is None:
        return []
    readiness = await LogisticsPlanService(session).readiness(project_id)
    return [
        EvidenceItem(
            code=f"site_logistics:{item['code']}",
            state=item["state"],
            label_key=f"site_logistics.evidence.{item['code']}",
            link=("site_logistics", str(project_id)),
            detail=item["detail"],
        )
        for item in readiness["items"]
    ]


def register_gate_evidence() -> None:
    """Register the provider (idempotent, by name)."""
    register_evidence_provider(AREA, logistics_readiness, name=PROVIDER, blocking=True)
