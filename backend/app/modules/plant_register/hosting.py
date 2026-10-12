# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the plant register sits in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently, so this
module never matches one by its code. The pinned catalogue says it:

* the area tagged ``hosts: ["plant"]`` owns the register (its owner and deputy
  may edit, its owner is told about order dates and expired slots);
* the document type tagged ``hosts: ["plant"]`` is the frame document the
  register reports into;
* the gate into the phase tagged ``enables: ["construction_start"]`` is the
  one the readiness evidence is collected for.

Everything is resolved at read time, so re-pinning the governance model moves
the register with it. A catalogue that carries no tag resolves to nothing, and
the callers say so (an ``unknown`` evidence item, no area owner) instead of
guessing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

PLANT_TAG = "plant"
CONSTRUCTION_START = "construction_start"


@dataclass(frozen=True)
class PlantHost:
    """What the pinned governance catalogue says about the plant register."""

    area_code: str | None = None
    document_types: tuple[str, ...] = ()
    gate_codes: tuple[str, ...] = ()
    # Where an "it could not be resolved" evidence item is shown when no area is tagged.
    first_area_code: str | None = None


def tags(entry: Any, field: str) -> tuple[str, ...]:
    """The tag list ``field`` (``hosts`` or ``enables``) of one catalogue entry; empty when it has none."""
    return tuple(getattr(entry, field, None) or ())


def read_host(catalogue: Any) -> PlantHost:
    """Resolve the plant host of one governance catalogue."""
    areas = sorted(catalogue.areas, key=lambda a: a.order)
    area = next((a.code for a in areas if PLANT_TAG in tags(a, "hosts")), None)
    phases = {p.code for p in catalogue.phases if CONSTRUCTION_START in tags(p, "enables")}
    return PlantHost(
        area_code=area,
        document_types=tuple(
            d.code for d in catalogue.document_types if PLANT_TAG in tags(d, "hosts") and d.area == area
        ),
        gate_codes=tuple(g.code for g in catalogue.gates if g.to_phase in phases),
        first_area_code=areas[0].code if areas else None,
    )


async def project_host(session: Any, project_id: uuid.UUID) -> PlantHost | None:
    """The plant host of the project's pinned governance model; ``None`` when the project pins none."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return read_host(await GovernanceService(session).catalogue_for(model))
