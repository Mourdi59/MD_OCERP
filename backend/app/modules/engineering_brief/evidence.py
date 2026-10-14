# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the engineering brief.

Asked for the governance area that hosts the brief; the area and its frame document are found by
catalogue tag, never by code (see ``hosting``). At a gate where the frame document is required: the brief
must be SUBMITTED (or later) with no error-level finding. "Met" never needs an approved brief: the gate
decision is the approval, so requiring it before the gate would deadlock the gate that approves it.

At every gate the framework schedule must carry a dated milestone for that gate: a gate nobody planned in
the schedule is a gate whose date nobody owns.

Registered blocking, so it must not fail open. A project without a brief does not use the module: no
evidence. A project with a brief whose governance catalogue does not say where the brief lives gets one
``unknown`` item with the reason, and a missing frame document row is ``unknown`` too, never met.
Governance never imports this module; it calls the registry.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.engineering_brief import hosting
from app.modules.project_governance.evidence import (
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

PROVIDER_NAME = "engineering_brief.brief_ready"
LINK_KIND = "engineering_brief"
NO_AREA = "governance_catalogue_has_no_engineering_brief_area"
NO_DOCUMENT = "project_has_no_frame_document_for_engineering_brief"


def applies(catalogue: Any, area_code: str, first_area_code: str) -> tuple[bool, str]:
    """Whether this area is asked, and the reason when the answer is ``unknown``.

    The reason is set when the project has a brief but the catalogue tags no area for it; it is reported
    once, under the first applicable area, not once per area.
    """
    host = hosting.host(catalogue)
    if host is None:
        return (True, NO_AREA) if area_code == first_area_code else (False, "")
    return area_code == host.area_code, ""


def items(ready: dict[str, Any], link: tuple[str, str]) -> list[EvidenceItem]:
    """The evidence items from ``EngineeringBriefService.readiness``; pure."""
    out: list[EvidenceItem] = []
    if ready["frame_document_missing"]:
        out.append(
            EvidenceItem(
                code="brief_frame_document_missing",
                state="unknown",
                label_key="engineering_brief.evidence.frame_document_missing",
                link=link,
                detail=NO_DOCUMENT,
            )
        )
    if ready["frame_required"]:
        out.append(
            EvidenceItem(
                code="brief_submitted",
                state="met" if ready["submitted"] else "not_met",
                label_key="engineering_brief.evidence.brief_submitted",
                link=link,
                detail=ready["status"] or "",
            )
        )
        out.append(
            EvidenceItem(
                code="brief_no_errors",
                state="not_met" if ready["errors"] else "met",
                label_key="engineering_brief.evidence.no_errors",
                link=link,
                detail=", ".join(sorted({f"{e['code']}:{e['ref']}" for e in ready["errors"]})),
            )
        )
    if ready["frame_required"]:
        for code, key, (state, detail) in (
            ("site_analysis_done", "site_analysis", ready["site_analysis"]),
            ("suitability_studies_done", "suitability", ready["suitability"]),
            ("requirements_specification_issued", "specification", ready["specification"]),
        ):
            out.append(
                EvidenceItem(
                    code=code,
                    state=state,
                    label_key=f"engineering_brief.evidence.{key}",
                    link=link,
                    detail=detail,
                )
            )
    out.append(
        EvidenceItem(
            code="brief_gate_milestone",
            state="met" if ready["gate_milestone"] and ready["gate_dated"] else "not_met",
            label_key="engineering_brief.evidence.gate_milestone",
            link=link,
            detail="" if ready["gate_milestone"] else "gate_without_milestone",
        )
    )
    return out


async def brief_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.engineering_brief.service import EngineeringBriefService
    from app.modules.project_governance import public as governance

    svc = EngineeringBriefService(session)
    if await svc.get_brief(project_id) is None:
        return []
    areas = await governance.project_areas(session, project_id)
    first = next((a.code for a in areas if a.status == "applicable"), area.code)
    ask, unknown_reason = applies(await svc._governance_catalogue(project_id), area.code, first)
    if not ask:
        return []
    link = (LINK_KIND, str(project_id))
    if unknown_reason:
        return [
            EvidenceItem(
                code="brief_host_unknown",
                state="unknown",
                label_key="engineering_brief.evidence.area_unknown",
                link=link,
                detail=unknown_reason,
            )
        ]
    return items(await svc.readiness(project_id, attempt.gate_code), link)


def register_gate_evidence() -> None:
    register_evidence_provider("*", brief_ready, name=PROVIDER_NAME, blocking=True)
    # Where an evidence item of this module opens: the project's engineering brief screen.
    register_evidence_link(LINK_KIND, "/projects/{project_id}/engineering-brief")
