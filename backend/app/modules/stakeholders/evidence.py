# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 20).

For the area that hosts this module the provider returns five items: register
present, key stakeholders planned, mandates complete, roles filled,
commitments tracked, each with its counts in ``detail``.

Which area that is comes from data: the project's own override in the
settings, else the governance catalogue's ``hosts`` tag (see ``hosting``). No
area code is matched here. When the project has a register but no area hosts
it, the provider does not go quiet: it reports one ``unknown`` item on the
first area of the catalogue, so the gate shows that the stakeholder evidence
could not be placed instead of passing without it.

A project that has not pinned a framework has no register and answers nothing.
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
NO_HOST_CODE = "stakeholders:host_area"
NO_HOST_DETAIL = "no_governance_area_hosts_stakeholders"


def _detail(check: dict[str, Any]) -> str:
    return ", ".join(
        f"{k}={','.join(v) if isinstance(v, list) else v}" for k, v in sorted(check.items()) if k != "status"
    )


def placement(area_code: str, host: str | None, first_area: str | None) -> str:
    """What the provider answers for one area: ``items``, ``unplaced`` or ``nothing``.

    ``unplaced`` is the single ``unknown`` item, reported once (on the first
    area) when no area hosts the module.
    """
    if host is not None:
        return "items" if area_code == host else "nothing"
    return "unplaced" if first_area is not None and area_code == first_area else "nothing"


async def governance_readiness(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.stakeholders import hosting
    from app.modules.stakeholders.service import StakeholderService

    svc = StakeholderService(session)
    settings = await svc.get_settings(project_id)
    if settings is None:
        return []
    host = await svc.host_area_code(project_id, settings)
    first = None
    if host is None:
        catalogue = await hosting.project_catalogue(session, project_id)
        first = hosting.first_area_code(catalogue) if catalogue is not None else None
    where = placement(area.code, host, first)
    link = ("stakeholders", str(project_id))
    if where == "nothing":
        return []
    if where == "unplaced":
        return [
            EvidenceItem(
                code=NO_HOST_CODE,
                state="unknown",
                label_key="stakeholders.evidence.host_area",
                link=link,
                detail=NO_HOST_DETAIL,
            )
        ]
    checks = await svc.readiness(project_id, today=datetime.now(UTC).date())
    return [
        EvidenceItem(
            code=f"stakeholders:{code}",
            state=checks[code]["status"],
            label_key=f"stakeholders.evidence.{code}",
            link=link,
            detail=_detail(checks[code]),
        )
        for code in CHECKS
    ]


def register_gate_evidence() -> None:
    register_evidence_provider("*", governance_readiness, name=PROVIDER_NAME, blocking=False)
