# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where logistics sits in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently
(``m06_logistics`` in the module framework, ``schedule_logistics`` in the
neutral model, ``d`` in the steering model). This module never matches a code:

* the hosting AREA is the one tagged ``hosts: ["logistics"]``;
* the frame DOCUMENT is the document type tagged ``hosts: ["logistics"]``;
* the readiness GATES are the gates at which the catalogue requires that frame
  document; a catalogue without one falls back to the gates into a phase tagged
  ``enables: ["construction_start"]``.

Everything is resolved at read time from the project's pinned governance
catalogue, so a re-pin moves logistics with it and nothing resolved is stored.
The tags are read with ``getattr``: a catalogue model that does not carry them
yet resolves to nothing, which the callers report as unknown instead of guessing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

LOGISTICS_TAG = "logistics"
CONSTRUCTION_START_TAG = "construction_start"


def _tagged(item: Any, attribute: str, tag: str) -> bool:
    return tag in (getattr(item, attribute, ()) or ())


def hosting_area_code(catalogue: Any) -> str | None:
    """The code of the area tagged for logistics, or ``None`` when the catalogue tags none."""
    return next((a.code for a in catalogue.areas if _tagged(a, "hosts", LOGISTICS_TAG)), None)


def frame_document(catalogue: Any) -> Any | None:
    """The document type tagged for logistics (the frame document the plan is exported into)."""
    return next((d for d in catalogue.document_types if _tagged(d, "hosts", LOGISTICS_TAG)), None)


def readiness_gate_codes(catalogue: Any) -> tuple[str, ...]:
    """The gates the logistics plan has to be ready for.

    First the gates at which the tagged frame document is required. A catalogue
    that requires it nowhere (or has no such document) answers with the gates
    into a phase that enables the start of construction. Empty when neither tag
    resolves.
    """
    doc = frame_document(catalogue)
    required = tuple(getattr(doc, "required_at_gates", ()) or ()) if doc is not None else ()
    if required:
        return required
    enabling = {p.code for p in catalogue.phases if _tagged(p, "enables", CONSTRUCTION_START_TAG)}
    return tuple(g.code for g in catalogue.gates if g.to_phase in enabling)


@dataclass(frozen=True)
class GovernanceTarget:
    """Where logistics sits in one project's governance model."""

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


def target_of(catalogue: Any) -> GovernanceTarget:
    """The target a governance catalogue gives."""
    doc = frame_document(catalogue)
    return GovernanceTarget(
        has_model=True,
        area_code=hosting_area_code(catalogue),
        frame_doc_type=doc.code if doc is not None else None,
        gate_codes=readiness_gate_codes(catalogue),
    )


async def project_target(session: Any, project_id: uuid.UUID) -> GovernanceTarget:
    """The target of the project's pinned governance model; ``has_model`` False without one."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return GovernanceTarget(has_model=False)
    return target_of(await GovernanceService(session).catalogue_for(model))
