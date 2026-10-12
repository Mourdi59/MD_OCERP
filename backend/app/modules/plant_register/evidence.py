# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for project governance (SPEC section 7).

At the gate into the phase that enables construction start, for the area that
hosts plant (both read from catalogue tags, see ``hosting.py``): zero
error-level findings of rule set ``plant_register``; every critical item at
least ``route_set`` with an approved decision paper; every long-lead item with
one fresh basis quote and either ordered or not past its latest order date;
and the frame document attached to a CDE container. One evidence item per
condition, so the gate page says which one is missing.

A project without plant items gets nothing. A project with items whose
governance model does not say where plant sits gets one ``unknown`` item with
the reason, never silence: an empty answer would read as "nothing to check".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.project_governance.evidence import ANY_AREA, EvidenceItem, GateAttempt, register_evidence_provider

PROVIDER_NAME = "plant_register.readiness"


def _unresolved(project_id: uuid.UUID, reason: str) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            code="plant:host_unresolved",
            state="unknown",
            label_key="plant.evidence.host_unresolved",
            link=("plant_register", str(project_id)),
            detail=reason,
        )
    ]


async def plant_readiness(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.plant_register.hosting import project_host
    from app.modules.plant_register.repository import PlantRepository
    from app.modules.plant_register.service import PlantService

    host = await project_host(session, project_id)
    if host is None:
        return []
    if host.area_code is None:
        # No area to hang the answer on: say it once, on the first area of the model.
        if area.code != host.first_area_code or not await PlantRepository(session).items(project_id):
            return []
        return _unresolved(project_id, "no_area_hosts_plant")
    if area.code != host.area_code:
        return []
    if host.gate_codes and attempt.gate_code not in host.gate_codes:
        return []
    if not await PlantRepository(session).items(project_id):
        return []
    if not host.gate_codes:
        return _unresolved(project_id, "no_phase_enables_construction_start")
    r = await PlantService(session).readiness(project_id, today=datetime.now(UTC).date())
    link = ("plant_register", str(project_id))

    def item(code: str, ok: bool | None, detail: str) -> EvidenceItem:
        return EvidenceItem(
            code=f"plant:{code}",
            state="unknown" if ok is None else "met" if ok else "not_met",
            label_key=f"plant.evidence.{code}",
            link=link,
            detail=detail,
        )

    frame_known = bool(host.document_types)
    return [
        item(
            "no_error_findings",
            not r["error_findings"],
            ", ".join(sorted({e["element_ref"] or "" for e in r["error_findings"]})),
        ),
        item("critical_route_set", not r["critical_open"], ", ".join(r["critical_open"])),
        item("long_lead_secured", not r["long_lead_open"], ", ".join(r["long_lead_open"])),
        item(
            "frame_document_attached",
            r["frame_document_attached"] if frame_known else None,
            "" if frame_known else "no_document_type_hosts_plant",
        ),
    ]


def register_gate_evidence() -> None:
    register_evidence_provider(ANY_AREA, plant_readiness, name=PROVIDER_NAME, blocking=True)
