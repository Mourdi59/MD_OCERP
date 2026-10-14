# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Gate readiness evidence of the project handbook.

Asked for the governance area that hosts the project organisation (found by catalogue tag, never by code):
the required chapters of the handbook must each have an approved version, and the data room must be
materialised so documents have somewhere to go.

Registered blocking, so it must not fail open. A project without a handbook does not use the module: no
evidence. A project whose governance catalogue does not say where the organisation lives gets one
``unknown`` item with the reason. Governance never imports this module; it calls the registry.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.modules.project_governance import public as governance
from app.modules.project_governance.evidence import (
    EvidenceItem,
    GateAttempt,
    register_evidence_link,
    register_evidence_provider,
)

PROVIDER_NAME = "project_handbook.handbook_ready"
LINK_KIND = "project_handbook"
SUBJECT = "organisation"
NO_AREA = "governance_catalogue_has_no_organisation_area"


def items(ready: dict[str, Any], folders: int, link: tuple[str, str]) -> list[EvidenceItem]:
    """The evidence items from ``ProjectHandbookService.readiness`` and the folder count; pure."""
    return [
        EvidenceItem(
            code="handbook_required_chapters_approved",
            state="met" if not ready["open"] else "not_met",
            label_key="project_handbook.evidence.required_chapters_approved",
            link=link,
            detail=", ".join(ready["open"]),
        ),
        EvidenceItem(
            code="handbook_data_room_materialised",
            state="met" if folders else "not_met",
            label_key="project_handbook.evidence.data_room_materialised",
            link=link,
            detail=str(folders),
        ),
    ]


async def handbook_ready(session: Any, project_id: uuid.UUID, attempt: GateAttempt, area: Any) -> list[EvidenceItem]:
    from app.modules.documents.models import DocumentFolder
    from app.modules.project_handbook.service import ProjectHandbookService

    svc = ProjectHandbookService(session)
    if await svc.get_handbook(project_id) is None:
        return []
    link = (LINK_KIND, str(project_id))
    host = await governance.host_for(session, project_id, SUBJECT)
    if host is None:
        areas = await governance.project_areas(session, project_id)
        first = next((a.code for a in areas if a.status == "applicable"), area.code)
        if area.code != first:
            return []
        return [
            EvidenceItem(
                code="handbook_host_unknown",
                state="unknown",
                label_key="project_handbook.evidence.area_unknown",
                link=link,
                detail=NO_AREA,
            )
        ]
    if area.code != host.area_code:
        return []
    folders = (
        await session.execute(
            select(func.count()).select_from(DocumentFolder).where(DocumentFolder.project_id == project_id)
        )
    ).scalar_one()
    return items(await svc.readiness(project_id), int(folders), link)


def register_gate_evidence() -> None:
    register_evidence_provider("*", handbook_ready, name=PROVIDER_NAME, blocking=True)
    # Where an evidence item of this module opens: the project's handbook screen.
    register_evidence_link(LINK_KIND, "/projects/{project_id}/handbook")
