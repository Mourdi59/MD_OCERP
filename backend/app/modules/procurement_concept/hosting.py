# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where procurement lives in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently, so this
module never matches one by code. The pinned governance catalogue says it:

* the area tagged ``hosts: ["procurement"]`` is the procurement area (its owner
  and deputy steer the concept);
* the document type tagged ``hosts: ["procurement"]`` is the frame document
  that carries the concept (it becoming binding is the approval);
* the phase tagged ``enables: ["procurement_release"]`` is the one procurement
  may start in: the gate into that phase releases procurement.

A catalogue without a tag answers ``None`` / empty, and every caller treats
that as "not known", never as "nothing required".

This is the only place that reads the tags. When module 1 publishes its own
accessor, this file is the one call site to switch.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

PROCUREMENT_TAG = "procurement"
RELEASE_TAG = "procurement_release"


@dataclass(frozen=True)
class ProcurementHosting:
    """What the pinned governance catalogue says about procurement."""

    area_code: str | None = None
    document_types: tuple[str, ...] = ()
    release_gate_codes: tuple[str, ...] = ()


def _tags(item: Any, field: str) -> tuple[str, ...]:
    return tuple(getattr(item, field, None) or ())


def hosting_of(catalogue: Any) -> ProcurementHosting:
    """Resolve the three tags on one governance catalogue."""
    if catalogue is None:
        return ProcurementHosting()
    area = next((a.code for a in catalogue.areas if PROCUREMENT_TAG in _tags(a, "hosts")), None)
    docs = tuple(d.code for d in catalogue.document_types if PROCUREMENT_TAG in _tags(d, "hosts"))
    phases = {p.code for p in catalogue.phases if RELEASE_TAG in _tags(p, "enables")}
    gates = tuple(g.code for g in catalogue.gates if g.to_phase in phases)
    return ProcurementHosting(area, docs, gates)


async def governance_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue, or ``None`` before a model is set."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)


async def project_hosting(session: Any, project_id: uuid.UUID) -> ProcurementHosting:
    """The procurement hosting of the project's pinned governance model."""
    return hosting_of(await governance_catalogue(session, project_id))
