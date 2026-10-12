# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 20).

For the area that owns the register (settings ``owner_area_code``, default
``m01_project_management``) the provider returns five items: register present,
key stakeholders planned, mandates complete, roles filled, commitments
tracked, each with its counts in ``detail``. A project that has not pinned a
framework yet answers nothing for any area; module 1 decides how to weigh the
items, so the provider is registered non-blocking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "stakeholders.governance_readiness"
CHECKS: tuple[str, ...] = (
    "register_present",
    "key_stakeholders_planned",
    "mandates_complete",
    "roles_filled",
    "commitments_tracked",
)


def _detail(check: dict[str, Any]) -> str:
    return ", ".join(
        f"{k}={','.join(v) if isinstance(v, list) else v}" for k, v in sorted(check.items()) if k != "status"
    )


async def governance_readiness(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.stakeholders.service import StakeholderService

    svc = StakeholderService(session)
    settings = await svc.get_settings(project_id)
    if settings is None or area.code != settings.owner_area_code:
        return []
    checks = await svc.readiness(project_id, today=datetime.now(UTC).date())
    return [
        EvidenceItem(
            code=f"stakeholders:{code}",
            state=checks[code]["status"],
            label_key=f"stakeholders.evidence.{code}",
            link=("stakeholders", str(project_id)),
            detail=_detail(checks[code]),
        )
        for code in CHECKS
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", governance_readiness, name=PROVIDER_NAME, blocking=False)
