# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where procurement lives in a project's governance model, read through module 1's port.

Governance models name their areas, documents and gates differently, so this
module never matches one by code. The pinned phase model says it in tags, and
:mod:`app.modules.project_governance.public` reads them:

* the document type that hosts the subject ``procurement`` is the frame
  document that carries the concept (it becoming binding is the approval), and
  its area is the procurement area (its owner and deputy steer the concept);
* a phase that enables the capability ``procurement`` is one procurement may
  start in: the gate into that phase releases procurement.

Resolved at read time and never stored: a project may move to another model.
A model without a tag answers ``None`` / empty, and every caller treats that as
"not known", never as "nothing required".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.modules.project_governance.public import host_in, phases_enabling_in, project_catalogue

SUBJECT = "procurement"
CAPABILITY = "procurement"


@dataclass(frozen=True)
class ProcurementHosting:
    """What the pinned phase model says about procurement."""

    area_code: str | None = None
    document_types: tuple[str, ...] = ()
    release_gate_codes: tuple[str, ...] = ()


def hosting_of(catalogue: Any) -> ProcurementHosting:
    """Resolve host and releasing gates on one parsed phase model (``None`` = the project pinned none)."""
    if catalogue is None:
        return ProcurementHosting()
    host = host_in(catalogue, SUBJECT)
    phases = set(phases_enabling_in(catalogue, CAPABILITY))
    gates = tuple(g.code for g in catalogue.gates if g.to_phase in phases)
    if host is None:
        return ProcurementHosting(None, (), gates)
    return ProcurementHosting(host.area_code, (host.doc_type,), gates)


async def project_hosting(session: Any, project_id: uuid.UUID) -> ProcurementHosting:
    """The procurement hosting of the project's pinned phase model."""
    return hosting_of(await project_catalogue(session, project_id))
