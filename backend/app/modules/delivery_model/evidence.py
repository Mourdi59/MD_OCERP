# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC section 7, lead decision 2).

The area this module reports in is the area of the carrier document: the frame
document the project's governance catalogue tags as hosting the delivery model
(``hosting.py``). No area, document or gate is matched by a literal code.

At a gate where the carrier document is required, the delivery decision must
be PROPOSED (or already approved), every risk category allocated, and no
error-level finding open. "Met" never needs an approved decision: the gate
decision is the approval, so requiring it before the gate would deadlock the
gate.

At a gate into a phase tagged as enabling procurement, every owner-furnished
item needs a procurement route and an installer (rule 10).

Registered blocking, so it must not fail open. A project that has no delivery
model does not use the module: no evidence, nothing blocks. A project that has
one but whose governance model names no carrier gets one ``unknown`` item on
its first area, with the reason, instead of silence.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "delivery_model.decision_ready"


async def _is_first_area(session: Any, project_id: uuid.UUID, area: Any) -> bool:
    from app.modules.project_governance.repository import GovernanceRepository

    asked = [a for a in await GovernanceRepository(session).list_areas(project_id) if a.applicable]
    first = min(asked, key=lambda a: (a.sort_order, a.code), default=None)
    return first is not None and first.id == area.id


async def decision_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.delivery_model import hosting, rules
    from app.modules.delivery_model.service import DeliveryModelService

    svc = DeliveryModelService(session)
    model = await svc.get_model(project_id)
    if model is None:
        return []
    link = ("delivery_model", str(project_id))
    doc, why = await hosting.carrier_document(session, project_id)
    if doc is None:
        if not await _is_first_area(session, project_id, area):
            return []
        return [
            EvidenceItem(
                code="delivery_carrier_missing",
                state="unknown",
                label_key="delivery_model.evidence.carrier_missing",
                link=link,
                detail=why or "",
            )
        ]
    if doc.area_id != area.id:
        return []
    out: list[EvidenceItem] = []
    if attempt.gate_code in (doc.required_at_gates or []):
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
    catalogue = await hosting.governance_catalogue(session, project_id)
    gates = hosting.procurement_gate_codes(catalogue) if catalogue is not None else ()
    rows = await svc.ofi_rows(project_id)
    ofi_link = ("delivery_ofi", str(project_id))
    if not gates:
        # No phase says where procurement starts, so rule 10 cannot be placed on a gate: say so where the
        # decision is checked, when there is something it would have checked.
        if rows and out:
            out.append(
                EvidenceItem(
                    code="delivery_ofi_routes",
                    state="unknown",
                    label_key="delivery_model.evidence.ofi_routes",
                    link=ofi_link,
                    detail="procurement_phase_untagged",
                )
            )
    elif attempt.gate_code in gates:
        open_items = rules.ofi_findings(rows, await svc.package_rows(project_id), procurement_released=True)
        missing = sorted(f.ref for f in open_items if f.code == "ofi_without_route")
        out.append(
            EvidenceItem(
                code="delivery_ofi_routes",
                state="not_met" if missing else "met",
                label_key="delivery_model.evidence.ofi_routes",
                link=ofi_link,
                detail=", ".join(missing),
            )
        )
    return out


def register_gate_evidence() -> None:
    register_evidence_provider("*", decision_ready, name=PROVIDER_NAME, blocking=True)
