# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the risk register.

Asked once per gate, under the first applicable area of the project's phase
model, and only for a project that keeps risks: a project without any is asked
nothing. Two items: every open risk has an owner, and every open risk of tier
high or critical has a mitigation strategy.

Registered non-blocking. The risk register is a platform module, not hosted by
a frame document, so a thin register is said at the gate and never stops it.
Governance never imports this module; it calls the registry.
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

PROVIDER_NAME = "risk.register_ready"
CLOSED = ("closed", "mitigated", "occurred")
SERIOUS_TIERS = ("high", "critical")
EVIDENCE_ROUTE = "/risks"


def items_for(risks: list[Any], link: tuple[str, str]) -> list[EvidenceItem]:
    """The two evidence items for a project's risks; pure."""
    open_risks = [r for r in risks if r.status not in CLOSED]
    no_owner = sorted(r.code for r in open_risks if not (r.owner_name or r.owner_user_id))
    no_plan = sorted(
        r.code for r in open_risks if (r.risk_tier or "") in SERIOUS_TIERS and not (r.mitigation_strategy or "").strip()
    )
    return [
        EvidenceItem(
            code="risk.owners_assigned",
            state="not_met" if no_owner else "met",
            label_key="risk.evidence.owners_assigned",
            link=link,
            detail=", ".join(no_owner),
        ),
        EvidenceItem(
            code="risk.serious_mitigated",
            state="not_met" if no_plan else "met",
            label_key="risk.evidence.serious_mitigated",
            link=link,
            detail=", ".join(no_plan),
        ),
    ]


async def register_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.project_governance import public
    from app.modules.risk.repository import RiskRepository

    risks = await RiskRepository(session).all_for_project(project_id)
    if not risks:
        return []
    codes = [a.code for a in await public.project_areas(session, project_id) if a.status == "applicable"]
    if area.code != min(codes, default=area.code):
        return []
    return items_for(list(risks), ("risk", str(project_id)))


def register_gate_evidence() -> None:
    register_evidence_link("risk", EVIDENCE_ROUTE)
    register_evidence_provider("*", register_ready, name=PROVIDER_NAME, blocking=False)
