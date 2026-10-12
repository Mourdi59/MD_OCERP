# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for the personnel area (SPEC rule 5, section 7).

Registered on the area named by the pinned staffing catalogue
(``m05_personnel``), blocking. At a gate where the area's frame document is
required: the plan must be SUBMITTED (or later) with no error-level finding.
"Met" never needs an approved plan: the gate decision is the approval, so
requiring it before the gate would deadlock the gate that approves it. At a
gate that key positions name in ``required_by_gate``: every such position is
filled on the gate's planned date (rule 5).

A project without a staffing plan does not use the module: no evidence.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "staffing.plan_ready"
AREA = "m05_personnel"


async def plan_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.project_governance.models import GovernanceDocument
    from app.modules.staffing.service import StaffingService

    svc = StaffingService(session)
    ready = await svc.readiness(project_id, attempt.gate_code)
    if not ready.get("in_use"):
        return []
    link = ("staffing", str(project_id))
    out: list[EvidenceItem] = []
    docs = (
        (
            await session.execute(
                select(GovernanceDocument).where(
                    GovernanceDocument.project_id == project_id, GovernanceDocument.area_id == area.id
                )
            )
        )
        .scalars()
        .all()
    )
    if any(attempt.gate_code in (d.required_at_gates or []) for d in docs):
        out.append(
            EvidenceItem(
                code="staffing_plan_submitted",
                state="met" if ready["submitted"] else "not_met",
                label_key="staffing.evidence.plan_submitted",
                link=link,
                detail=ready["status"] or "",
            )
        )
        out.append(
            EvidenceItem(
                code="staffing_no_errors",
                state="not_met" if ready["errors"] else "met",
                label_key="staffing.evidence.no_errors",
                link=link,
                detail=", ".join(sorted({f"{e['code']}:{e['ref']}" for e in ready["errors"]})),
            )
        )
    if ready["key_roles_required"]:
        out.append(
            EvidenceItem(
                code="staffing_key_roles_filled",
                state="not_met" if ready["key_role_findings"] else "met",
                label_key="staffing.evidence.key_roles_filled",
                link=link,
                detail=", ".join(sorted(f["detail"] for f in ready["key_role_findings"])),
            )
        )
    return out


def register_gate_evidence() -> None:
    register_evidence_provider(AREA, plan_ready, name=PROVIDER_NAME, blocking=True)
