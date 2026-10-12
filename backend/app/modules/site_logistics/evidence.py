# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the logistics plan for the governance module.

One BLOCKING provider, registered for every area. It names no area and no gate:
:mod:`app.modules.site_logistics.hosting` resolves both from the tags of the
project's pinned governance catalogue each time it is asked.

* No plan content yet (see :meth:`LogisticsPlanService.plan_started`): nothing.
  Opening the logistics tab does not arm the gate.
* The catalogue places logistics (a tagged area and at least one gate): each
  readiness item becomes one evidence item on that area at those gates.
* A plan exists but the catalogue does not place it: one ``unknown`` item that
  carries the reason, so the gate page shows that logistics could not be
  assessed instead of showing nothing. ``unknown`` never blocks.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import ANY_AREA, EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER = "site_logistics.plan_readiness"


async def _anchor_area_code(session: Any, project_id: uuid.UUID) -> str | None:
    """The first applicable area of the project: where an unplaced plan reports itself."""
    from sqlalchemy import select

    from app.modules.project_governance.models import GovernanceArea

    return (
        await session.execute(
            select(GovernanceArea.code)
            .where(
                GovernanceArea.project_id == project_id,
                GovernanceArea.applicable.is_(True),
                GovernanceArea.retired.is_(False),
            )
            .order_by(GovernanceArea.sort_order, GovernanceArea.code)
            .limit(1)
        )
    ).scalar_one_or_none()


async def logistics_readiness(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    """Evidence items of the logistics plan for one area of a gate attempt."""
    from app.modules.site_logistics.plan_service import LogisticsPlanService

    svc = LogisticsPlanService(session)
    code = getattr(area, "code", None)
    target = await svc.governance_target(project_id)
    reason = target.reason
    if reason is None:
        if code != target.area_code or attempt.gate_code not in target.gate_codes:
            return []
        if not await svc.plan_started(project_id):
            return []
        readiness = await svc.readiness(project_id)
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
    anchor = target.area_code or await _anchor_area_code(session, project_id)
    if code != anchor or not await svc.plan_started(project_id):
        return []
    return [
        EvidenceItem(
            code="site_logistics:unresolved",
            state="unknown",
            label_key="site_logistics.evidence.unresolved",
            link=("site_logistics", str(project_id)),
            detail=reason,
        )
    ]


def register_gate_evidence() -> None:
    """Register the provider (idempotent, by name)."""
    register_evidence_provider(ANY_AREA, logistics_readiness, name=PROVIDER, blocking=True)
