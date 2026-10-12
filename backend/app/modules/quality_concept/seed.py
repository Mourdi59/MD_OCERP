# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo quality concept for the demo estate.

Each demo project gets a draft concept on the neutral catalogue: two applied
standards, the catalogue commissioning stages, a partial and a total
acceptance unit under the FIDIC taking-over regime (a contract standard, so it
reads the same in every country), one handover-to-operation unit and a planned
before-survey of the neighbouring building. Everything goes through the
service, so the demo obeys the same rules as user input.

A project is skipped when it is not a demo project or already has a concept,
so a customer's live project is never written to and a re-run adds nothing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_concept import schemas as s
from app.modules.quality_concept.models import QualityConcept

logger = logging.getLogger(__name__)

_REGIME = "fidic_taking_over"


async def seed_quality_concept_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed a draft quality concept into every demo project that has none.

    Args:
        session: Async DB session. The caller commits.
        project_ids: Projects to consider.

    Returns:
        Dict with per-entity insert counts.
    """
    from app.modules.projects.models import Project
    from app.modules.quality_concept.service import QualityConceptService

    totals = {"projects": 0, "standards": 0, "stages": 0, "units": 0, "surveys": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (
        await session.execute(
            select(Project.id, Project.owner_id, Project.metadata_, Project.created_at).where(Project.id.in_(ids))
        )
    ).all()
    seeded = set(
        (await session.execute(select(QualityConcept.project_id).where(QualityConcept.project_id.in_(ids)))).scalars()
    )
    svc = QualityConceptService(session)
    for pid, owner, meta, created in rows:
        if pid in seeded or not (isinstance(meta, dict) and str(meta.get("demo_id") or "").strip()):
            continue
        start = created.date() + timedelta(days=30)
        await svc.ensure_concept(pid, owner)
        for code, title, family in (
            ("EN 206", "Concrete: specification, performance, production and conformity", "concrete"),
            ("EN 1090-2", "Execution of steel structures", "steel"),
        ):
            await svc.create_standard(
                pid, s.StandardIn(code=code, title=title, family_code=family, discipline="structure")
            )
            totals["standards"] += 1
        totals["stages"] += len(await svc.apply_catalogue_stages(pid))
        for code, title, kind, days in (
            ("AU-01", "Structure, building section A", "partial_section", 360),
            ("AU-02", "Whole works", "total", 540),
            ("AU-03", "Handover to operation", "handover_to_operation", 560),
        ):
            await svc.create_unit(
                pid,
                s.AcceptanceUnitIn(
                    code=code,
                    title=title,
                    kind=kind,
                    regime_code=_REGIME,
                    section_ref="A" if kind == "partial_section" else "",
                    planned_date=start + timedelta(days=days),
                ),
            )
            totals["units"] += 1
        await svc.create_survey(
            pid,
            s.PreservationIn(
                subject_kind="neighbour_building",
                subject_ref="NB-01",
                address="Adjacent building, north boundary",
                influence_triggers=["excavation"],
                methods=["photo", "crack_mapping"],
                planned_date=start - timedelta(days=14),
            ),
        )
        totals["surveys"] += 1
        totals["projects"] += 1
    logger.info("quality_concept demo seed: %s", totals)
    return totals
