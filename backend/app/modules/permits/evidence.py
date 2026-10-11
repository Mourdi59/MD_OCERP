# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 19).

Two providers, registered for every area (``"*"``) and deciding relevance per
area from the roadmap's own area codes (resolved from the project's pinned
governance model when the roadmap was created, e.g. ``m02_contract_management``
in the ELF catalogue, ``contracts_procurement`` in the neutral one):

* ``permits.roadmap_and_register`` (non-blocking): on the roadmap area, every
  requirement the gate's target phase needs is filed or granted and no schedule
  conflict is left unaccepted; on the conditions area, the register is complete.
* ``permits.start_and_handover`` (BLOCKING): on the roadmap area of a gate into
  construction / execution, no open before-start suspensive condition and every
  before-start obligation discharged or accepted as a gate condition; of a gate
  into handover / operation, no open before-occupation condition and the
  occupancy permit granted. A suspensive condition suspends the permit, so the
  gate must not pass on a warning (rule 12).

The phase is the gate's ``to_phase``; :data:`conditions.PHASE_ENABLES` maps the
phase codes of both shipped governance catalogues.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.permits.conditions import HANDOVER_PHASES, START_PHASES
from app.modules.project_governance.evidence import EvidenceItem, GateAttempt, register_evidence_provider

ROADMAP_PROVIDER = "permits.roadmap_and_register"
GATE_PROVIDER = "permits.start_and_handover"


async def _context(session: Any, project_id: uuid.UUID, attempt: GateAttempt) -> tuple[Any, str | None]:
    from app.modules.permits.repository import PermitRepository
    from app.modules.project_governance.models import GovernanceGate

    roadmap = await PermitRepository(session).get_roadmap(project_id)
    gate = await session.get(GovernanceGate, attempt.gate_id)
    return roadmap, getattr(gate, "to_phase", None)


def _items(readiness: dict[str, Any], code: str, label: str, project_id: uuid.UUID) -> list[EvidenceItem]:
    failing = [i for i in readiness["items"] if i["state"] == "not_met"]
    return [
        EvidenceItem(
            code=code,
            state="not_met" if failing else "met",
            label_key=label,
            link=("permits", str(project_id)),
            detail=", ".join(f"{i['code']}:{i['detail']}" for i in failing),
        )
    ]


async def roadmap_and_register(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.permits.service import PermitService

    roadmap, phase = await _context(session, project_id, attempt)
    if roadmap is None:
        return []
    svc = PermitService(session)
    today = datetime.now(UTC).date()
    out: list[EvidenceItem] = []
    if area.code == roadmap.roadmap_area_code:
        r = await svc.readiness(
            project_id, phase if phase in ("construction", "execution", "handover", "operation") else "roadmap", today
        )
        out += _items(r, f"permits_roadmap:{attempt.gate_code}", "permits.evidence.roadmap", project_id)
    if area.code == roadmap.conditions_area_code:
        r = await svc.readiness(project_id, "register", today)
        out += _items(r, f"permits_register:{attempt.gate_code}", "permits.evidence.register", project_id)
    return out


async def start_and_handover(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.permits.service import PermitService

    roadmap, phase = await _context(session, project_id, attempt)
    if roadmap is None or area.code != roadmap.roadmap_area_code:
        return []
    if phase in START_PHASES:
        gate, label = "start", "permits.evidence.start"
    elif phase in HANDOVER_PHASES:
        gate, label = "handover", "permits.evidence.handover"
    else:
        return []
    r = await PermitService(session).readiness(project_id, gate, datetime.now(UTC).date())
    return _items(r, f"permits_{gate}:{attempt.gate_code}", label, project_id)


def register_gate_evidence() -> None:
    register_evidence_provider("*", roadmap_and_register, name=ROADMAP_PROVIDER, blocking=False)
    register_evidence_provider("*", start_and_handover, name=GATE_PROVIDER, blocking=True)
