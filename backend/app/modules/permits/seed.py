# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo permit roadmap and condition register, run by ``app.core.demo_enrichment``.

Each demo project gets the permit catalogue its country resolves to and a
roadmap an owner would actually run: the preliminary decision (granted), the
main building permit (granted with conditions: one suspensive before-start
condition still open, a noise obligation in force, a before-occupation
condition), an early start at own risk under review, a road occupation permit
being prepared and the occupancy approval still to come. Permit types are
picked from the catalogue by category and scope, never by a national code, so
the same seeder serves every country. Everything goes through the service, so
the rows obey the same rules a user would meet.

Only projects carrying the demo marker are touched; a project that already
has a roadmap is skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def seed_permits_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the roadmap of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.permits.models import PermitRoadmap
    from app.modules.projects.models import Project

    totals = {"projects": 0, "requirements": 0, "conditions": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (
            await session.execute(select(PermitRoadmap.id).where(PermitRoadmap.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("permits demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


def _pick(types: dict, *, category: str | None = None, scope: str | None = None, route: str | None = None):
    for t in types.values():
        if category and t.category != category:
            continue
        if scope and t.scope != scope:
            continue
        if route and route not in t.triggered_by_route:
            continue
        return t
    return None


async def _seed_project(session: AsyncSession, pid: uuid.UUID) -> dict[str, int]:
    from app.modules.permits.service import PermitService
    from app.modules.projects.models import Project

    project = await session.get(Project, pid)
    owner = getattr(project, "owner_id", None)
    if owner is None:
        return {"requirements": 0, "conditions": 0}
    svc = PermitService(session)
    roadmap = await svc.set_roadmap(pid, tenant_id=None, actor_id=owner)
    types = await svc._types(roadmap)
    today = datetime.now(UTC).date()
    prelim = _pick(types, scope="preliminary")
    building = _pick(types, category="building", scope="full", route="full_permit") or _pick(
        types, scope="full", route="full_permit"
    )
    early = next(
        (
            t
            for t in types.values()
            if t.scope == "early_start" and building and building.code in {r.code for r in t.requires}
        ),
        None,
    )
    road = _pick(types, category="traffic_road")
    occupancy = _pick(types, category="occupancy")
    if building is None:
        return {"requirements": 0, "conditions": 0}

    async def req(t, title: str, **kw) -> object:
        return await svc.create_requirement(
            pid, {"permit_type_code": t.code, "title": title, "responsible_user_id": owner, **kw}, actor_id=owner
        )

    made = []
    r_pre = await req(prelim, "Preliminary decision on use and building envelope") if prelim else None
    r_bld = await req(
        building,
        "Main building permit",
        planned_submit_date=today - timedelta(days=200),
        needed_by_date=today + timedelta(days=45),
    )
    made += [r for r in (r_pre, r_bld) if r]
    if r_pre is not None:
        await svc.set_dependencies(pid, r_bld.id, [{"depends_on_id": r_pre.id, "on": "granted"}], actor_id=owner)
    r_early = (
        await req(early, "Early start of excavation at own risk", needed_by_date=today + timedelta(days=20))
        if early
        else None
    )
    r_road = (
        await req(road, "Road occupation for crane and site access", needed_by_date=today + timedelta(days=60))
        if road
        else None
    )
    r_occ = (
        await req(occupancy, "Occupancy approval", needed_by_date=today + timedelta(days=540)) if occupancy else None
    )
    made += [r for r in (r_early, r_road, r_occ) if r]
    if r_early is not None:
        await svc.set_dependencies(pid, r_early.id, [{"depends_on_id": r_bld.id, "on": "submitted"}], actor_id=owner)

    async def file(r, submitted: date, ref: str) -> object:
        app = await svc.create_application(
            pid,
            {"requirement_id": r.id, "authority_name": "Local building authority", "authority_reference": ref},
            actor_id=owner,
        )
        await svc.transition_application(
            pid, app.id, "preparing", actor_id=owner, actor_role="manager", on_date=None, today=submitted
        )
        await svc.transition_application(
            pid, app.id, "submitted", actor_id=owner, actor_role="manager", on_date=submitted, today=submitted
        )
        return app

    if r_pre is not None:
        a = await file(r_pre, today - timedelta(days=330), "PRE-2025-0418")
        await svc.record_decision(
            pid,
            a.id,
            {"outcome": "granted", "decision_date": today - timedelta(days=260), "reference": "PRE-2025-0418"},
            actor_id=owner,
            today=today,
        )
    a_bld = await file(r_bld, today - timedelta(days=190), "BP-2026-0112")
    conditions = [
        {
            "number": "1",
            "text": "Before work starts, submit the verified structural calculations for the basement retaining walls.",
            "kind": "suspensive",
            "trigger": "before_start",
            "topic": "structural",
            "owner_user_id": owner,
            "due_date": today + timedelta(days=21),
            "evidence_required": "Checked calculations with the checking engineer's report",
        },
        {
            "number": "2",
            "text": "Noisy works are permitted on working days between 07:00 and 19:00 only.",
            "kind": "obligation",
            "trigger": "ongoing",
            "topic": "noise",
            "owner_user_id": owner,
            "responsible_party": "Main contractor",
        },
        {
            "number": "3",
            "text": "A tree protection fence is installed before any excavation and kept until completion.",
            "kind": "obligation",
            "trigger": "before_start",
            "topic": "ecology",
            "owner_user_id": owner,
            "due_date": today - timedelta(days=5),
        },
        {
            "number": "4",
            "text": "Before occupation, the fire alarm system is accepted by an approved inspector.",
            "kind": "suspensive",
            "trigger": "before_occupation",
            "topic": "fire",
            "owner_user_id": owner,
        },
        {
            "number": "5",
            "text": "The permit does not replace consents required under other legislation.",
            "kind": "information",
            "trigger": "",
            "topic": "admin",
        },
    ]
    await svc.record_decision(
        pid,
        a_bld.id,
        {
            "outcome": "granted_with_conditions",
            "decision_date": today - timedelta(days=30),
            "served_date": today - timedelta(days=27),
            "reference": "BP-2026-0112",
            "conditions": conditions,
        },
        actor_id=owner,
        today=today,
    )
    if r_early is not None:
        a = await file(r_early, today - timedelta(days=12), "ES-2026-0031")
        await svc.transition_application(
            pid, a.id, "under_review", actor_id=owner, actor_role="manager", on_date=None, today=today
        )
    if r_road is not None:
        a = await svc.create_application(pid, {"requirement_id": r_road.id}, actor_id=owner)
        await svc.transition_application(
            pid, a.id, "preparing", actor_id=owner, actor_role="manager", on_date=None, today=today
        )
    return {"requirements": len(made), "conditions": len(conditions)}
