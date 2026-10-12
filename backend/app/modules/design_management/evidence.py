# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 16, decision 9).

For the design area (``m07_design_management``) at a gate: the phase the gate
closes (its ``from_phase``) is not ready while a required deliverable of that
phase is open, a required report of that phase is not accepted, or a major
review comment of that phase is open. One evidence item per kind of blocker,
registered BLOCKING: the governance gate refuses a plain go while it is
``not_met`` (a decider may still go with conditions on the area).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "design_management.phase_readiness"
DESIGN_AREAS = ("m07_design_management",)


async def phase_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.design_management.service import DesignService
    from app.modules.project_governance.models import GovernanceGate

    if area.code not in DESIGN_AREAS:
        return []
    svc = DesignService(session)
    if await svc.get_setup(project_id) is None:
        return []
    gate = await session.get(GovernanceGate, attempt.gate_id)
    phase = getattr(gate, "from_phase", None)
    if not phase:
        return []
    b = await svc.readiness(project_id, phase)
    link = ("design_readiness", str(project_id))
    return [
        EvidenceItem(
            code=f"design_deliverables:{phase}",
            state="not_met" if b.deliverables else "met",
            label_key="design.evidence.deliverables",
            link=link,
            detail=", ".join(b.deliverables),
        ),
        EvidenceItem(
            code=f"design_reports:{phase}",
            state="not_met" if b.reports else "met",
            label_key="design.evidence.reports",
            link=link,
            detail=", ".join(b.reports),
        ),
        EvidenceItem(
            code=f"design_major_comments:{phase}",
            state="not_met" if b.major_comments else "met",
            label_key="design.evidence.major_comments",
            link=link,
            detail=str(b.major_comments) if b.major_comments else "",
        ),
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", phase_readiness, name=PROVIDER_NAME, blocking=True)
