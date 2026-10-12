# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the staffing plan (SPEC rule 5, section 7).

Asked for the governance area that hosts staffing; the area, its frame
document and the phase a key role is needed before are all found by catalogue
tag, never by code (see ``hosting``). At a gate where the frame document is
required: the plan must be SUBMITTED (or later) with no error-level finding.
"Met" never needs an approved plan: the gate decision is the approval, so
requiring it before the gate would deadlock the gate that approves it. At a
gate into a phase that enables what key positions are required before: every
such position is filled on the gate's planned date (rule 5).

Registered blocking, so it must not fail open. A project without a staffing
plan does not use the module: no evidence. A project with a plan whose
governance catalogue does not say where staffing lives gets one ``unknown``
item with the reason, and a key position whose requirement no phase enables
makes the key role item ``unknown``; neither is reported as met or left out.
Governance never imports this module; it calls the registry.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider
from app.modules.staffing import hosting

PROVIDER_NAME = "staffing.plan_ready"
NO_AREA = "governance_catalogue_has_no_staffing_area"


def applies(catalogue: Any, area_code: str, first_area_code: str, *, has_data: bool) -> tuple[bool, str]:
    """Whether this area is asked, and the reason when the answer is ``unknown``.

    Returns ``(ask, unknown_reason)``. The reason is set when the project has a
    staffing plan but the catalogue tags no area for it; it is reported once,
    under the first applicable area, not once per area.
    """
    if not has_data:
        return False, ""
    host = hosting.hosting_area_code(catalogue)
    if host is None:
        return (True, NO_AREA) if area_code == first_area_code else (False, "")
    return area_code == host, ""


def items(ready: dict[str, Any], link: tuple[str, str]) -> list[EvidenceItem]:
    """The evidence items from ``StaffingService.readiness``; pure."""
    out: list[EvidenceItem] = []
    if ready["frame_required"]:
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
    if ready["unresolved_tags"]:
        # A key position waits for something no phase of this governance model enables: no gate can check it.
        out.append(
            EvidenceItem(
                code="staffing_key_roles_filled",
                state="unknown",
                label_key="staffing.evidence.key_roles_filled",
                link=link,
                detail="no_phase_enables: " + ", ".join(ready["unresolved_tags"]),
            )
        )
    elif ready["key_roles_required"]:
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


async def plan_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.project_governance.models import GovernanceArea
    from app.modules.staffing.service import StaffingService

    svc = StaffingService(session)
    has_data = await svc.get_plan(project_id) is not None
    if not has_data:
        return []
    codes = (
        await session.execute(
            select(GovernanceArea.code)
            .where(GovernanceArea.project_id == project_id)
            .where(GovernanceArea.applicable.is_(True))
            .where(GovernanceArea.retired.is_(False))
        )
    ).scalars()
    catalogue = await svc._governance_catalogue(project_id)
    ask, unknown_reason = applies(catalogue, area.code, min(codes, default=area.code), has_data=has_data)
    if not ask:
        return []
    link = ("staffing", str(project_id))
    if unknown_reason:
        return [
            EvidenceItem(
                code="staffing_plan_submitted",
                state="unknown",
                label_key="staffing.evidence.area_unknown",
                link=link,
                detail=unknown_reason,
            )
        ]
    return items(await svc.readiness(project_id, attempt.gate_code), link)


def register_gate_evidence() -> None:
    register_evidence_provider("*", plan_ready, name=PROVIDER_NAME, blocking=True)
