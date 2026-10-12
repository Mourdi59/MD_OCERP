# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence for module 1 (SPEC rule 19).

Two providers, registered for every area (``"*"``). Which area and which gate
they answer for is asked of module 1's read port at the moment the gate asks
(:mod:`app.modules.permits.hosting`); no area, document or phase code appears
here and nothing resolved is stored.

* ``permits.roadmap_and_register`` (advisory): on the area hosting the roadmap,
  every requirement the gate's target phase needs is filed or granted and no
  schedule conflict is left unaccepted; on the area hosting the condition
  register, the register is complete.
* ``permits.start_and_handover`` (BLOCKING): on the area hosting the roadmap, for
  a gate into a phase tagged as the start of construction, no open before-start
  suspensive condition and every before-start obligation discharged or accepted
  as a gate condition; for a gate into a phase tagged handover or operation, no
  open before-occupation condition and the occupancy permit granted.

Evidence states are met / not_met / unknown. "At risk" (an early start, a
partial permit, an obligation accepted at the gate) is reported as ``not_met``
with a detail that says so: the gate can then pass only as go with conditions
with the area accepted at risk. It is never reported as met (rule 10).

A project with a roadmap whose governance model does not say where permits
live, has no row yet for the document that hosts them, or tags no phase at
all, gets one ``unknown`` item with the reason on every area. A provider that has data must not answer with silence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from app.modules.permits.hosting import Hosting, project_hosting
from app.modules.project_governance.evidence import (
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

ROADMAP_PROVIDER = "permits.roadmap_and_register"
GATE_PROVIDER = "permits.start_and_handover"
# Reasons of an ``unknown`` item (also the i18n key suffix under ``permits.evidence.unresolved``).
NO_HOSTING_AREA = "no_area_hosts_permits"
NO_PHASE_TAGS = "no_phase_enables_tag"
NO_FRAME_DOCUMENT = "no_frame_document"


async def _missing(session: Any, project_id: uuid.UUID, hosting: Hosting) -> str | None:
    """Why the place of permits in the governance model cannot be answered for, or ``None`` when it can."""
    from app.modules.project_governance import public

    if hosting.roadmap_area is None:
        return NO_HOSTING_AREA
    if hosting.doc_type is not None:
        # A project pinned before its model gained the document type has no row for it yet.
        documents = await public.project_documents(session, project_id)
        if not any(d.code == hosting.doc_type for d in documents):
            return NO_FRAME_DOCUMENT
    return None


async def _context(session: Any, project_id: uuid.UUID, attempt: GateAttempt) -> tuple[Any, Hosting, Any]:
    """The roadmap, where the model hosts permits, and the gate being read (``None`` when unknown)."""
    from app.modules.permits.repository import PermitRepository
    from app.modules.project_governance import public

    roadmap = await PermitRepository(session).get_roadmap(project_id)
    if roadmap is None:
        return None, Hosting(), None
    gates = await public.project_gates(session, project_id)
    gate = next((g for g in gates if g.id == attempt.gate_id), None)
    return roadmap, await project_hosting(session, project_id, roadmap), gate


def needed_from(gate: Any, today: date) -> date | None:
    """The date a gate's permits check is made for: the gate's target date, never earlier than today.

    The day is the server's. A gate without a target date gives ``None``: nothing can then be
    shown to be needed later, so every missing permit blocks.
    """
    target = getattr(gate, "target_date", None)
    return max(target, today) if target is not None else None


def unresolved(provider: str, attempt: GateAttempt, reason: str, project_id: uuid.UUID) -> EvidenceItem:
    return EvidenceItem(
        code=f"permits_unresolved:{provider}:{attempt.gate_code}",
        state="unknown",
        label_key=f"permits.evidence.unresolved.{reason}",
        link=("permits", str(project_id)),
        detail=reason,
    )


def to_evidence(readiness: dict[str, Any], code: str, label: str, project_id: uuid.UUID) -> EvidenceItem:
    """One evidence item per readiness check; anything not plainly met is ``not_met`` and says why.

    A ``warning`` is carried in the detail and does not change the state: the item can be
    ``met`` and still say what is due later.
    """
    said = [i for i in readiness["items"] if i["state"] != "met"]
    prefix = {"at_risk": "at_risk ", "warning": "warning "}
    return EvidenceItem(
        code=code,
        state="not_met" if any(i["state"] != "warning" for i in said) else "met",
        label_key=label,
        link=("permits", str(project_id)),
        detail=", ".join(f"{prefix.get(i['state'], '')}{i['code']}:{i['detail']}" for i in said),
    )


async def roadmap_and_register(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.permits.service import PermitService

    roadmap, hosting, read = await _context(session, project_id, attempt)
    phase = getattr(read, "to_phase", None)
    if roadmap is None:
        return []
    if (reason := await _missing(session, project_id, hosting)) is not None:
        return [unresolved(ROADMAP_PROVIDER, attempt, reason, project_id)]
    svc = PermitService(session)
    today = datetime.now(UTC).date()
    out: list[EvidenceItem] = []
    if area.code == hosting.roadmap_area:
        if not hosting.phases_tagged:
            out.append(unresolved(ROADMAP_PROVIDER, attempt, NO_PHASE_TAGS, project_id))
        r = await svc.readiness(project_id, "roadmap", today, enables=hosting.enables(phase))
        out.append(to_evidence(r, f"permits_roadmap:{attempt.gate_code}", "permits.evidence.roadmap", project_id))
    if area.code == hosting.conditions_area:
        r = await svc.readiness(project_id, "register", today)
        out.append(to_evidence(r, f"permits_register:{attempt.gate_code}", "permits.evidence.register", project_id))
    return out


async def start_and_handover(
    session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any
) -> list[EvidenceItem]:
    from app.modules.permits.service import PermitService

    roadmap, hosting, read = await _context(session, project_id, attempt)
    phase = getattr(read, "to_phase", None)
    if roadmap is None:
        return []
    if (reason := await _missing(session, project_id, hosting)) is not None:
        return [unresolved(GATE_PROVIDER, attempt, reason, project_id)]
    if area.code != hosting.roadmap_area:
        return []
    if not hosting.phases_tagged:
        return [unresolved(GATE_PROVIDER, attempt, NO_PHASE_TAGS, project_id)]
    svc = PermitService(session)
    today = datetime.now(UTC).date()
    out: list[EvidenceItem] = []
    for gate in hosting.gates(phase):
        r = await svc.readiness(project_id, gate, today, needed_from=needed_from(read, today))
        out.append(to_evidence(r, f"permits_{gate}:{attempt.gate_code}", f"permits.evidence.{gate}", project_id))
    return out


def register_gate_evidence() -> None:
    register_evidence_provider("*", roadmap_and_register, name=ROADMAP_PROVIDER, blocking=False)
    register_evidence_provider("*", start_and_handover, name=GATE_PROVIDER, blocking=True)
    # Items link as ("permits", project_id): the project's permits tab.
    register_evidence_link("permits", "/projects/{project_id}/permits")
