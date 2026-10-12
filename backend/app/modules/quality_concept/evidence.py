# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the quality concept (spec section 7).

Asked at the gate into a phase that enables the start of construction, for the
governance area that hosts quality; both are found by catalogue tag, never by
code (see ``hosting``). Three items: the concept is ready to be approved, the
plan has no error findings (rules 1 and 2), and every subject under a
triggering activity has a before survey planned.

"Ready to be approved" is ``in_review`` without error findings, or already
approved or binding. It cannot be "approved": the concept is approved by the
frame document's binding event, and governance publishes that event inside the
very decision this evidence feeds.

Registered blocking, so it must not fail open. Whenever it cannot answer (no
tag in the catalogue, no concept) it returns an ``unknown`` item with a reason
instead of an empty list. Governance never imports this module; it calls the
registry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider
from app.modules.quality_concept import hosting

PROVIDER_NAME = "quality_concept.readiness"
READY_STATES = ("approved", "binding")


def readiness_items(readiness: dict[str, Any], link: tuple[str, str]) -> list[EvidenceItem]:
    """The three evidence items from ``QualityConceptService.readiness``; pure."""
    if not readiness["concept"]:
        # The model hosts quality and nobody wrote the concept: that is a missing deliverable, not a doubt.
        return [
            EvidenceItem(
                code="quality_concept.approved",
                state="not_met",
                label_key="quality_concept.evidence.approved",
                link=link,
                detail="quality_concept_missing",
            )
        ]
    errors = sorted({e["code"] for e in readiness["errors"]})
    state = readiness["state"]
    ready = state in READY_STATES or (state == "in_review" and not errors)
    return [
        EvidenceItem(
            code="quality_concept.approved",
            state="met" if ready else "not_met",
            label_key="quality_concept.evidence.approved",
            link=link,
            detail="" if ready else state,
        ),
        EvidenceItem(
            code="quality_concept.complete",
            state="not_met" if errors else "met",
            label_key="quality_concept.evidence.complete",
            link=link,
            detail=", ".join(errors),
        ),
        EvidenceItem(
            code="quality_concept.preservation_planned",
            state="not_met" if readiness["preservation_unplanned"] else "met",
            label_key="quality_concept.evidence.preservation_planned",
            link=link,
            detail=", ".join(readiness["preservation_unplanned"]),
        ),
    ]


def _unknown(reason: str, link: tuple[str, str]) -> EvidenceItem:
    return EvidenceItem(
        code="quality_concept.approved",
        state="unknown",
        label_key="quality_concept.evidence.approved",
        link=link,
        detail=reason,
    )


def applies(
    catalogue: Any, area_code: str, first_area_code: str, to_phase: str | None, has_data: bool
) -> tuple[bool, str]:
    """Whether this area at this gate is asked, and the reason when the answer is ``unknown``.

    Returns ``(ask, unknown_reason)``. ``unknown_reason`` is set when the module holds data
    for the project but the catalogue does not say where quality lives or which phase starts
    construction; it is reported once, under the first applicable area, not once per area.
    """
    found = hosting.host(catalogue)
    host = found.area_code if found is not None else None
    phases = hosting.phases_enabling(catalogue, hosting.CONSTRUCTION_START)
    if host is None or not phases:
        if not has_data or area_code != first_area_code:
            return False, ""
        return True, "governance_catalogue_has_no_quality_area" if host is None else "no_phase_enables_construction"
    if area_code != host or to_phase not in phases:
        return False, ""
    return True, ""


def unknown_reason(catalogue: Any, *, has_data: bool, has_frame_document: bool) -> str | None:
    """Why the gate into construction would answer ``unknown`` for this project; ``None`` when it can read the concept.

    The same reasons, in the same order, as ``quality_readiness`` gives the gate. A project
    without a phase model, or one that never used the module, is asked nothing.
    """
    if catalogue is None or not has_data:
        return None
    if hosting.host(catalogue) is None:
        return "governance_catalogue_has_no_quality_area"
    if not hosting.phases_enabling(catalogue, hosting.CONSTRUCTION_START):
        return "no_phase_enables_construction"
    if not has_frame_document:
        return "quality_frame_document_missing"
    return None


async def gate_detail(session: Any, project_id: uuid.UUID) -> str | None:
    """``unknown_reason`` of a project, for the readiness screen."""
    from app.modules.quality_concept.service import QualityConceptService

    catalogue = await hosting.project_catalogue(session, project_id)
    if catalogue is None:
        return None
    svc = QualityConceptService(session)
    return unknown_reason(
        catalogue,
        has_data=await svc.concept_state(project_id) is not None,
        has_frame_document=bool(await svc._frame_documents(project_id)),
    )


async def quality_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.project_governance import public
    from app.modules.quality_concept.service import QualityConceptService

    catalogue = await hosting.project_catalogue(session, project_id)
    if catalogue is None:
        return []
    svc = QualityConceptService(session)
    has_data = await svc.concept(project_id) is not None
    gates = await public.project_gates(session, project_id)
    gate = next((g for g in gates if g.id == attempt.gate_id), None)
    areas = await public.project_areas(session, project_id)
    codes = [a.code for a in areas if a.status == "applicable"]
    ask, unknown_reason = applies(
        catalogue, area.code, min(codes, default=area.code), gate.to_phase if gate else None, has_data
    )
    if not ask:
        return []
    link = ("quality_concept", str(project_id))
    if unknown_reason:
        return [_unknown(unknown_reason, link)]
    if not await svc._frame_documents(project_id):
        # The model hosts quality, but this project was pinned before the document type existed.
        return [_unknown("quality_frame_document_missing", link)]
    return readiness_items(await svc.readiness(project_id, datetime.now(UTC).date()), link)


def register_gate_evidence() -> None:
    register_evidence_provider("*", quality_readiness, name=PROVIDER_NAME, blocking=True)
