# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the plant register sits in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently, so this
module never matches one by its code. The pinned catalogue says it, through
the governance read port (``project_governance.public``):

* the document type that hosts subject ``plant`` is the frame document the
  register reports into, and that document's area hosts the register (its
  owner and deputy may edit, its owner is told about order dates and slots);
* the gate into the phase that enables ``construction_start`` is the one the
  readiness evidence is collected for.

Everything is resolved at read time, so re-pinning the governance model moves
the register with it. A catalogue that carries no tag resolves to nothing, and
the callers say so (an ``unknown`` evidence item, no area owner) instead of
guessing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

PLANT_SUBJECT = "plant"
CONSTRUCTION_START = "construction_start"


@dataclass(frozen=True)
class PlantHost:
    """What the pinned governance catalogue says about the plant register."""

    area_code: str | None = None
    document_types: tuple[str, ...] = ()
    gate_codes: tuple[str, ...] = ()
    # Where an "it could not be resolved" evidence item is shown when nothing is tagged.
    first_area_code: str | None = None


def read_host(catalogue: Any) -> PlantHost:
    """Resolve the plant host of one governance catalogue."""
    from app.modules.project_governance.public import host_in, phases_enabling_in

    host = host_in(catalogue, PLANT_SUBJECT)
    phases = set(phases_enabling_in(catalogue, CONSTRUCTION_START))
    areas = sorted(catalogue.areas, key=lambda a: a.order)
    return PlantHost(
        area_code=host.area_code if host else None,
        document_types=(host.doc_type,) if host else (),
        gate_codes=tuple(g.code for g in catalogue.gates if g.to_phase in phases),
        first_area_code=areas[0].code if areas else None,
    )


async def project_host(session: Any, project_id: uuid.UUID) -> PlantHost | None:
    """The plant host of the project's pinned governance model; ``None`` when the project pins none."""
    from app.modules.project_governance.public import project_catalogue

    catalogue = await project_catalogue(session, project_id)
    return None if catalogue is None else read_host(catalogue)
