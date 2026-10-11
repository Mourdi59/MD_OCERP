# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC section 7, lead decision 2).

For the contracts area named by the pinned delivery catalogue's
``governance_areas``: at a gate where the area's frame document is required,
the delivery decision must be PROPOSED (or already approved), every risk
category allocated, and no error-level finding open. "Met" never needs an
approved decision: the gate decision is the approval, so requiring it before
the gate would deadlock the gate.

At a gate that releases procurement (catalogue ``procurement_release_gates``),
every owner-furnished item needs a procurement route and an installer
(rule 10). A project pins one phase catalogue, so exactly one of the
``governance_areas`` exists in it and the item appears once.

Registered blocking. A project that has no delivery model does not use the
module: no evidence, nothing blocks.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "delivery_model.decision_ready"


async def decision_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.delivery_model import rules
    from app.modules.delivery_model.service import DeliveryModelService
    from app.modules.project_governance.models import GovernanceDocument

    svc = DeliveryModelService(session)
    model = await svc.get_model(project_id)
    if model is None:
        return []
    catalogue = await svc.catalogue_for(model)
    if area.code not in catalogue.governance_areas:
        return []
    out: list[EvidenceItem] = []
    link = ("delivery_model", str(project_id))
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
    required_here = any(attempt.gate_code in (d.required_at_gates or []) for d in docs)
    if required_here:
        ready = await svc.readiness(project_id)
        errors = ready["errors"]
        out.append(
            EvidenceItem(
                code="delivery_decision_proposed",
                state="met" if ready["decision_present"] else "not_met",
                label_key="delivery_model.evidence.decision_proposed",
                link=link,
                detail=ready["status"] or "",
            )
        )
        out.append(
            EvidenceItem(
                code="delivery_risks_allocated",
                state="met" if ready["risks_allocated"] else "not_met",
                label_key="delivery_model.evidence.risks_allocated",
                link=link,
                detail=", ".join(sorted(e["ref"] for e in errors if e["code"] == "risk_unallocated")),
            )
        )
        others = [e for e in errors if e["code"] not in ("risk_unallocated", "ofi_without_route")]
        out.append(
            EvidenceItem(
                code="delivery_no_errors",
                state="not_met" if others else "met",
                label_key="delivery_model.evidence.no_errors",
                link=link,
                detail=", ".join(sorted({f"{e['code']}:{e['ref']}" for e in others})),
            )
        )
    if attempt.gate_code in catalogue.procurement_release_gates:
        rows = await svc.ofi_rows(project_id)
        open_items = rules.ofi_findings(rows, await svc.package_rows(project_id), procurement_released=True)
        missing = sorted(f.ref for f in open_items if f.code == "ofi_without_route")
        out.append(
            EvidenceItem(
                code="delivery_ofi_routes",
                state="not_met" if missing else "met",
                label_key="delivery_model.evidence.ofi_routes",
                link=("delivery_ofi", str(project_id)),
                detail=", ".join(missing),
            )
        )
    return out


def register_gate_evidence() -> None:
    register_evidence_provider("*", decision_ready, name=PROVIDER_NAME, blocking=True)
