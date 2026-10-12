# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Which governance area hosts design on a project: the area tagged ``hosts: ["design"]`` in its catalogue.

Governance models name their areas differently (``m07_design_management`` in
the module framework, ``scope_quality`` in the neutral model and the models
that borrow its areas, ``b`` in the steering model). The catalogue says which
one carries design; this module never hardcodes a code.
"""

from __future__ import annotations

import uuid
from typing import Any

DESIGN_TAG = "design"


def hosting_area_code(catalogue: Any) -> str | None:
    """The code of the area tagged for design, or ``None`` when the catalogue tags none."""
    return next((a.code for a in catalogue.areas if DESIGN_TAG in (getattr(a, "hosts", ()) or ())), None)


def frame_document_types(catalogue: Any) -> tuple[str, ...]:
    """Document types tagged for design (the frame document design writes its registers into)."""
    return tuple(d.code for d in catalogue.document_types if DESIGN_TAG in (getattr(d, "hosts", ()) or ()))


async def _catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)


async def project_design_area_code(session: Any, project_id: uuid.UUID) -> str | None:
    """The hosting area of the project's pinned governance model; ``None`` without a model or a tag."""
    catalogue = await _catalogue(session, project_id)
    return hosting_area_code(catalogue) if catalogue is not None else None


async def project_frame_target(session: Any, project_id: uuid.UUID) -> tuple[str | None, tuple[str, ...]]:
    """``(hosting area code, frame document types)`` of the project's pinned model."""
    catalogue = await _catalogue(session, project_id)
    if catalogue is None:
        return None, ()
    return hosting_area_code(catalogue), frame_document_types(catalogue)
