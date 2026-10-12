# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 22).

For a gate attempt and one management area: every matrix item that names this
gate (``gate_code``) and this area (``governance_area_code``) must be released
(or committed, or closed) or explicitly deferred with a reason. One evidence
item per area that has such items. An area without items answers nothing when
every item of the gate sits in an area of the project, and ``unknown`` when
some name an area the project no longer has: those items would otherwise be
seen by no evidence call at all. Registered
non-blocking, in line with the ``warn`` default (lead decision a): the gate
page shows the open items, the decider decides.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "commitment_release.items_released_by_gate"
_DONE = ("released", "committed", "closed")


async def items_released_by_gate(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.commitment_release.repository import CommitmentRepository
    from app.modules.project_governance.public import project_areas

    on_gate = [
        i
        for i in await CommitmentRepository(session).list_items(project_id)
        if i.gate_code == attempt.gate_code and i.status not in ("aborted", "transferred")
    ]
    items = [i for i in on_gate if i.governance_area_code == area.code]
    if not items:
        known = {a.code for a in await project_areas(session, project_id)}
        stray = sorted(i.code for i in on_gate if i.governance_area_code not in known)
        if not stray:
            return []
        return [
            EvidenceItem(
                code=f"commitments_unplaced:{attempt.gate_code}:{area.code}",
                state="unknown",
                label_key="commitment.evidence.items_without_area",
                link=("commitment_matrix", str(project_id)),
                detail=", ".join(stray),
            )
        ]
    open_items = [i.code for i in items if i.status not in _DONE and not i.deferred]
    return [
        EvidenceItem(
            code=f"commitments_released:{attempt.gate_code}:{area.code}",
            state="not_met" if open_items else "met",
            label_key="commitment.evidence.items_released_by_gate",
            link=("commitment_matrix", str(project_id)),
            detail=", ".join(sorted(open_items)),
        )
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", items_released_by_gate, name=PROVIDER_NAME, blocking=False)
