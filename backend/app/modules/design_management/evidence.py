# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 16, decision 9).

For the area that hosts design (tagged in the catalogue) at a gate: the phase the gate
closes (its ``from_phase``) is not ready while a required deliverable of that
phase is open, a required report of that phase is not accepted, or a major
review comment of that phase is open. One evidence item per kind of blocker,
registered BLOCKING: the governance gate refuses a plain go while it is
``not_met`` (a decider may still go with conditions on the area).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import (
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

PROVIDER_NAME = "design_management.phase_readiness"
LINK_KIND = "design_readiness"


async def phase_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.design_management.hosting import design_host
    from app.modules.design_management.service import DesignService
    from app.modules.project_governance import public

    svc = DesignService(session)
    if await svc.get_setup(project_id) is None:
        return []  # design is not set up on this project: nothing to prove
    link = (LINK_KIND, str(project_id))
    host = await design_host(session, project_id)
    if host is None:
        # Design has data but the governance model names no area for it. Saying nothing
        # would read as "nothing blocks"; say once, on the first area, that it is unknown.
        first = min((a.code for a in await public.project_areas(session, project_id)), default=None)
        if area.code != first:
            return []
        return [
            EvidenceItem(
                code="design_readiness:no_host_area",
                state="unknown",
                label_key="design.evidence.no_host_area",
                link=link,
                detail="no_host_area",
            )
        ]
    if area.code != host.area_code:
        return []
    documents = await public.project_documents(session, project_id)
    if not any(d.code == host.doc_type and d.area_code == host.area_code for d in documents):
        # Pinned before the model named a design frame document: the host exists, its row does not.
        return [
            EvidenceItem(
                code="design_readiness:no_host_document",
                state="unknown",
                label_key="design.evidence.no_host_document",
                link=link,
                detail="no_host_document",
            )
        ]
    gate = next((g for g in await public.project_gates(session, project_id) if g.id == attempt.gate_id), None)
    phase = gate.from_phase if gate is not None else None
    if not phase:
        return [
            EvidenceItem(
                code="design_readiness:no_phase",
                state="unknown",
                label_key="design.evidence.no_phase",
                link=link,
                detail="no_phase",
            )
        ]
    b = await svc.readiness(project_id, phase)
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
    # Every item links to the project's design page; the id half of the link is the project itself.
    register_evidence_link(LINK_KIND, "/projects/{project_id}/design")
