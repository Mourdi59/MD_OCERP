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
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import (
    EVIDENCE_STATES,
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

PROVIDER_NAME = "commitment_release.items_released_by_gate"
LINK_KIND = "commitment_matrix"
LINK_ROUTE = "/projects/{project_id}/commitments"
_DONE = ("released", "committed", "closed")

# An item past its latest decision date with nothing released is outstanding and blocks nothing:
# its own evidence item, so the decider can name it at a go. The governance module serves the
# state ``warning`` for that; on a governance version without it the item is ``met`` and still
# says what is outstanding.
DECISION_OVERDUE = "commitment_decision_overdue"
WARNING_STATE = "warning" if "warning" in EVIDENCE_STATES else "met"


async def overdue_decisions(
    session: Any, project_id: uuid.UUID, gate_code: str, items: list[Any]
) -> list[EvidenceItem]:
    """One evidence item per item of the gate whose decision date has passed, coded by the item id."""
    from app.modules.commitment_release.service import CommitmentService

    if not items:
        return []
    today = datetime.now(UTC).date()
    views = await CommitmentService(session).item_views(project_id, today=today, item_ids=[i.id for i in items])
    return [
        EvidenceItem(
            code=f"{DECISION_OVERDUE}:{gate_code}:{v['id']}",
            state=WARNING_STATE,
            label_key="commitment.evidence.decision_overdue",
            link=(LINK_KIND, str(project_id)),
            detail=f"{v['code']} {v['latest_decision_date']}",
        )
        for v in sorted(views["items"], key=lambda v: v["code"])
        if v["decision_overdue"]
    ]


async def items_released_by_gate(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.commitment_release.repository import CommitmentRepository
    from app.modules.project_governance.public import host_for, project_areas

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
            host = await host_for(session, project_id, "commitment_release")
            if host is None or host.area_code != area.code:
                # Not this module's area: it has nothing to say here.
                return []
            # On the area that hosts commitment release an empty answer would read as covered.
            # No item names this gate, so whether money has to be released by it is not known.
            return [
                EvidenceItem(
                    code=f"commitments_none:{attempt.gate_code}:{area.code}",
                    state="unknown",
                    label_key="commitment.evidence.no_items_for_gate",
                    link=(LINK_KIND, str(project_id)),
                )
            ]
        return [
            EvidenceItem(
                code=f"commitments_unplaced:{attempt.gate_code}:{area.code}",
                state="unknown",
                label_key="commitment.evidence.items_without_area",
                link=(LINK_KIND, str(project_id)),
                detail=", ".join(stray),
            )
        ]
    open_items = [i.code for i in items if i.status not in _DONE and not i.deferred]
    return [
        *await overdue_decisions(session, project_id, attempt.gate_code, items),
        EvidenceItem(
            code=f"commitments_released:{attempt.gate_code}:{area.code}",
            state="not_met" if open_items else "met",
            label_key="commitment.evidence.items_released_by_gate",
            link=(LINK_KIND, str(project_id)),
            detail=", ".join(sorted(open_items)),
        ),
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", items_released_by_gate, name=PROVIDER_NAME, blocking=False)
    # Where the gate screen opens an evidence item of this module: the matrix of the project.
    register_evidence_link(LINK_KIND, LINK_ROUTE)
