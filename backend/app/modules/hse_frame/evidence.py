# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the HSE frame for the governance module.

One BLOCKING provider, registered for every area. It names no area and no gate:
:mod:`app.modules.hse_frame.hosting` resolves both through the governance read
port from the project's pinned phase model each time it is asked.

* No frame yet (``started``): nothing. Opening the screen does not arm the gate.
* The catalogue places the frame (a tagged area and at least one gate): each
  readiness item becomes one evidence item on that area at those gates.
* A frame exists but the catalogue does not place it: one ``unknown`` item that
  carries the reason, so the gate page shows that the frame could not be
  assessed instead of showing nothing. ``unknown`` never blocks.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import (
    ANY_AREA,
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

PROVIDER = "hse_frame.readiness"
LINK_KIND = "hse_frame"
LINK_ROUTE = "/projects/{project_id}/hse-frame"


async def hse_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    """Evidence items of the HSE frame for one area of a gate attempt."""
    from app.modules.hse_frame import hosting
    from app.modules.hse_frame.service import HseFrameService

    svc = HseFrameService(session)
    code = getattr(area, "code", None)
    target = await hosting.project_target(session, project_id)
    reason = target.reason
    if reason is None:
        if code != target.area_code or attempt.gate_code not in target.gate_codes:
            return []
        if not await svc.started(project_id):
            return []
        readiness = await svc.readiness(project_id)
        return [
            EvidenceItem(
                code=f"hse_frame:{item['code']}",
                state=item["state"],
                label_key=f"hse_frame.evidence.{item['code']}",
                link=(LINK_KIND, str(project_id)),
                detail=item["detail"],
            )
            for item in readiness["items"]
        ]
    anchor = target.area_code or await hosting.first_applicable_area(session, project_id)
    if code != anchor or not await svc.started(project_id):
        return []
    return [
        EvidenceItem(
            code="hse_frame:unresolved",
            state="unknown",
            label_key="hse_frame.evidence.unresolved",
            link=(LINK_KIND, str(project_id)),
            detail=reason,
        )
    ]


def register_gate_evidence() -> None:
    """Register the provider and where its links open (idempotent, by name)."""
    register_evidence_provider(ANY_AREA, hse_readiness, name=PROVIDER, blocking=True)
    register_evidence_link(LINK_KIND, LINK_ROUTE)
