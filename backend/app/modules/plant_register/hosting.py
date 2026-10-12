# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where the plant register sits in a project's governance model, read from catalogue tags.

Governance models name their areas, documents and gates differently, so this
module never matches one by its code. The pinned catalogue says it:

* the document type tagged ``hosts: ["plant"]`` is the frame document the
  register reports into, and that document's area hosts the register (its
  owner and deputy may edit, its owner is told about order dates and slots);
* the gate into the phase tagged ``enables: ["construction_start"]`` is the
  one the readiness evidence is collected for.

Everything is resolved at read time, so re-pinning the governance model moves
the register with it. A catalogue that carries no tag resolves to nothing, and
the callers say so (an ``unknown`` evidence item, no area owner) instead of
guessing.

``Host``, ``host_in`` and ``phases_enabling_in`` have the names and shapes of
``app.modules.project_governance.public``; once that port is on this branch
they are imported from there and the three definitions below go.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

PLANT_SUBJECT = "plant"
CONSTRUCTION_START = "construction_start"


@dataclass(frozen=True)
class Host:
    area_code: str  # the hosting area = the document type's own area
    doc_type: str  # the frame document type the subject writes into


def tags(entry: Any, field: str) -> tuple[str, ...]:
    """The tag list ``field`` (``hosts`` or ``enables``) of one catalogue entry; empty when it has none."""
    return tuple(getattr(entry, field, None) or ())


def host_in(catalogue: Any, subject: str) -> Host | None:
    """The document type tagged for ``subject`` and its area, or ``None`` when the catalogue tags none."""
    doc = next((d for d in catalogue.document_types if subject in tags(d, "hosts")), None)
    return None if doc is None else Host(doc.area, doc.code)


def phases_enabling_in(catalogue: Any, capability: str) -> tuple[str, ...]:
    """Codes of the phases whose start enables ``capability``, in catalogue order."""
    return tuple(p.code for p in sorted(catalogue.phases, key=lambda p: p.order) if capability in tags(p, "enables"))


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
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return read_host(await GovernanceService(session).catalogue_for(model))
