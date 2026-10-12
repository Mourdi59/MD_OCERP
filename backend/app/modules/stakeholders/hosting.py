# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where this module lives in a project's phase model.

Phase models name their areas and documents differently, so nothing here
matches a code. Module 1 says it as data and answers through its read port:
a frame document type lists the subjects it hosts, and the hosting area is the
area that document belongs to. This module has two subjects:

* ``stakeholders``: the stakeholder register, communication plan and commitments;
* ``organisation``: project roles, bodies and the mandate matrix.

They may live in different areas, or in one. A model that hosts a subject
nowhere answers ``None``, and the callers say so instead of guessing an area.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.modules.project_governance.public import Host, host_in
from app.modules.project_governance.public import project_catalogue as _project_catalogue

STAKEHOLDERS_TAG = "stakeholders"
ORGANISATION_TAG = "organisation"
SUBJECTS: tuple[str, ...] = (STAKEHOLDERS_TAG, ORGANISATION_TAG)
# Which subject each export of this module is filed under.
EXPORT_TAGS: dict[str, str] = {"register": STAKEHOLDERS_TAG, "organisation": ORGANISATION_TAG}


def host(catalogue: Any, subject: str) -> Host | None:
    """The area and frame document type hosting ``subject``, or ``None`` when the model hosts it nowhere."""
    return host_in(catalogue, subject)


def first_area_code(catalogue: Any) -> str | None:
    """The first area of the catalogue: where a finding that belongs to no area is reported once."""
    return next((a.code for a in catalogue.areas), None)


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned phase model; ``None`` when the project pinned none."""
    return await _project_catalogue(session, project_id)
