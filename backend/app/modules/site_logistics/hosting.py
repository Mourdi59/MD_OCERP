# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the logistics plan sits in a project's phase model, read through the governance port.

Phase models name their areas, documents and gates differently, so this module
never matches a code. It asks :mod:`app.modules.project_governance.public`:

* the HOST of subject ``site_logistics`` is the frame document type the plan is
  exported into, and with it the area that document belongs to;
* the readiness GATES are the gates into a phase whose entry enables
  ``construction_start``.

Everything is resolved at read time from the project's pinned model, so a
re-pin moves logistics with it and nothing resolved is stored. When the model
answers nothing the callers report ``unknown`` with the reason below; they
never treat it as met.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

SUBJECT = "site_logistics"
CAPABILITY = "construction_start"


@dataclass(frozen=True)
class GovernanceTarget:
    """Where logistics sits in one project's phase model."""

    has_model: bool
    area_code: str | None = None
    frame_doc_type: str | None = None
    gate_codes: tuple[str, ...] = ()

    @property
    def reason(self) -> str | None:
        """Why the target cannot be used, as a stable code; ``None`` when it is complete."""
        if not self.has_model:
            return "no_governance_model"
        if self.area_code is None:
            return "no_area_hosts_logistics"
        if not self.gate_codes:
            return "no_gate_for_logistics"
        return None


def target_in(catalogue: Any) -> GovernanceTarget:
    """The target a parsed phase model gives (pure; the gates are the catalogue's)."""
    from app.modules.project_governance.public import host_in, phases_enabling_in

    host = host_in(catalogue, SUBJECT)
    phases = set(phases_enabling_in(catalogue, CAPABILITY))
    return GovernanceTarget(
        has_model=True,
        area_code=host.area_code if host is not None else None,
        frame_doc_type=host.doc_type if host is not None else None,
        gate_codes=tuple(g.code for g in catalogue.gates if g.to_phase in phases),
    )


async def project_target(session: Any, project_id: uuid.UUID) -> GovernanceTarget:
    """The target of the project's pinned phase model; ``has_model`` False without one.

    The gates are the project's own gate rows, so a gate of a model the project
    left is not answered for.
    """
    from app.modules.project_governance.public import (
        host_in,
        phases_enabling_in,
        project_catalogue,
        project_gates,
    )

    catalogue = await project_catalogue(session, project_id)
    if catalogue is None:
        return GovernanceTarget(has_model=False)
    host = host_in(catalogue, SUBJECT)
    phases = set(phases_enabling_in(catalogue, CAPABILITY))
    gates = await project_gates(session, project_id) if phases else ()
    return GovernanceTarget(
        has_model=True,
        area_code=host.area_code if host is not None else None,
        frame_doc_type=host.doc_type if host is not None else None,
        gate_codes=tuple(g.code for g in gates if g.to_phase in phases),
    )


async def area_owner(session: Any, project_id: uuid.UUID, area_code: str | None) -> uuid.UUID | None:
    """The owner of the hosting area, the addressee of logistics notifications."""
    from app.modules.project_governance.public import project_areas

    if area_code is None:
        return None
    return next((a.owner_user_id for a in await project_areas(session, project_id) if a.code == area_code), None)


async def first_applicable_area(session: Any, project_id: uuid.UUID) -> str | None:
    """The first applicable area of the project: where a plan the model does not place reports itself."""
    from app.modules.project_governance.public import project_areas

    return next((a.code for a in await project_areas(session, project_id) if a.status == "applicable"), None)


async def frame_document_bound(session: Any, project_id: uuid.UUID, doc_type: str) -> bool | None:
    """Whether the frame document has a revision bound (the export happened); ``None`` without a document row.

    A project pinned before its model gained the document type has no row for
    it, which is unknown, not "not exported".
    """
    from app.modules.project_governance.public import project_documents

    rows = [d for d in await project_documents(session, project_id) if d.code == doc_type]
    if not rows:
        return None
    return any(d.bound_revision_id is not None for d in rows)
