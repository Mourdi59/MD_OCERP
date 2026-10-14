# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for the economics of a project.

The area this module reports in is the area of the carrier document: the frame document the project's
governance catalogue tags as hosting the economics (``hosting.py``). No area, document or gate is matched
by a literal code.

At a gate where the carrier document is required the plan must be PROPOSED (or already approved), the
financing must cover the investment, and no error-level finding may be open. "Met" never needs an approved
plan: the gate decision is the approval, so requiring it before the gate would deadlock the gate.

Registered blocking, so it must not fail open. A project that has no plan does not use the module: no
evidence, nothing blocks. A project that has one but whose governance model names no carrier gets one
``unknown`` item on its first area, with the reason, instead of silence.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.economics import rules
from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "economics.plan_ready"
FINANCING_CODES = ("financing_shortfall", "no_sources")

# Where the gate screen opens an evidence item of this module: the project's economics page.
EVIDENCE_ROUTE = "/projects/{project_id}/economics"


async def plan_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.economics import hosting
    from app.modules.economics.service import EconomicsService

    svc = EconomicsService(session)
    plan = await svc.get_plan(project_id)
    if plan is None:
        return []
    link = ("economics", str(project_id))
    doc, why = await hosting.carrier_document(session, project_id)
    if doc is None:
        if await hosting.first_applicable_area_id(session, project_id) != area.id:
            return []
        return [
            EvidenceItem(
                code="economics_carrier_missing",
                state="unknown",
                label_key="economics.evidence.carrier_missing",
                link=link,
                detail=why or "",
            )
        ]
    if doc.area_id != area.id or attempt.gate_code not in (doc.required_at_gates or []):
        return []
    ready = await svc.readiness(project_id)
    errors = ready["errors"]
    financing = [e for e in errors if e["code"] in FINANCING_CODES]
    others = [e for e in errors if e["code"] not in FINANCING_CODES]
    state = rules.register_state(await svc.validation_payload(project_id))
    return [
        *_register_items(state, link),
        EvidenceItem(
            code="economics_proposed",
            state="met" if ready["proposed"] else "not_met",
            label_key="economics.evidence.proposed",
            link=link,
            detail=ready["status"] or "",
        ),
        EvidenceItem(
            code="economics_financing_covered",
            state="not_met" if financing else "met",
            label_key="economics.evidence.financing_covered",
            link=link,
            detail=", ".join(sorted(e["code"] for e in financing)),
        ),
        EvidenceItem(
            code="economics_no_errors",
            state="not_met" if others else "met",
            label_key="economics.evidence.no_errors",
            link=link,
            detail=", ".join(sorted({f"{e['code']}:{e['ref']}" for e in others})),
        ),
    ]


_REGISTER_ITEMS = (
    ("securities", "economics_securities_in_place", "economics.evidence.securities_in_place"),
    ("insurance", "economics_insurance_in_place", "economics.evidence.insurance_in_place"),
    ("tax", "economics_tax_clarified", "economics.evidence.tax_clarified"),
    ("receivables_payables", "economics_receivables_payables_set", "economics.evidence.receivables_payables_set"),
    ("administration", "economics_administration_set", "economics.evidence.administration_set"),
)


def _register_items(state: dict[str, bool], link: tuple[str, str]) -> list[EvidenceItem]:
    return [
        EvidenceItem(code=code, state="met" if state[key] else "not_met", label_key=label, link=link)
        for key, code, label in _REGISTER_ITEMS
    ]


def register_gate_evidence() -> None:
    from app.modules.project_governance.evidence import register_evidence_link

    register_evidence_link("economics", EVIDENCE_ROUTE)
    register_evidence_provider("*", plan_ready, name=PROVIDER_NAME, blocking=True)
