# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Which governance area and frame documents host this module on a project.

Governance models name their areas and documents differently, so nothing here
matches a code. The pinned module 1 catalogue says it as data: an area lists
what it hosts (``hosts: ["stakeholders"]``) and so does a document type
(``hosts: ["stakeholders"]`` for the stakeholder and communication plan,
``hosts: ["organisation"]`` for the project organisation and mandates).

The tags are read with ``getattr`` so this works against a module 1 catalogue
model that does not declare ``hosts`` yet: then nothing is hosted, and the
callers say so instead of guessing an area.
"""

from __future__ import annotations

import uuid
from typing import Any

STAKEHOLDERS_TAG = "stakeholders"
ORGANISATION_TAG = "organisation"
# Which tag each export of this module is filed under.
EXPORT_TAGS: dict[str, str] = {"register": STAKEHOLDERS_TAG, "organisation": ORGANISATION_TAG}


def _hosts(item: Any) -> tuple[str, ...]:
    return tuple(getattr(item, "hosts", ()) or ())


def hosting_area_code(catalogue: Any) -> str | None:
    """The code of the area tagged for stakeholders, or ``None`` when the catalogue tags none."""
    return next((a.code for a in catalogue.areas if STAKEHOLDERS_TAG in _hosts(a)), None)


def frame_document_types(catalogue: Any, tag: str) -> tuple[str, ...]:
    """Document types tagged ``tag``, in catalogue order."""
    return tuple(d.code for d in catalogue.document_types if tag in _hosts(d))


def first_area_code(catalogue: Any) -> str | None:
    """The first area of the catalogue: where a finding that belongs to no area is reported once."""
    return next((a.code for a in catalogue.areas), None)


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue; ``None`` when the project has no governance model."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)
