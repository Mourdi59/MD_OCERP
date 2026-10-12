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


def _early_start_conditions(owner: uuid.UUID) -> list[dict]:
    """What every early start carries (rule 10): restore the site if the permit is refused, and give security."""
    return [
        {
            "number": "1",
            "text": "If the building permit is refused, the site is restored to its previous condition.",
            "kind": "obligation",
            "trigger": "ongoing",
            "topic": "admin",
            "purpose": "restoration",
            "owner_user_id": owner,
        },
        {
            "number": "2",
            "text": "Security for the restoration is lodged with the authority before excavation starts.",
            "kind": "obligation",
            "trigger": "ongoing",
            "topic": "admin",
            "purpose": "security",
            "owner_user_id": owner,
        },
    ]


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
            pid, app.id, "preparing", actor_id=owner, can_manage=True, on_date=None, today=submitted
        )
        await svc.transition_application(
            pid, app.id, "submitted", actor_id=owner, can_manage=True, on_date=submitted, today=submitted
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
    for kind, days, reason in (
        ("stop", 160, "Authority asked for the revised drainage layout"),
        ("resume", 141, "Revised drainage layout delivered"),
    ):
        await svc.add_clock_event(
            pid, a_bld.id, {"kind": kind, "at": today - timedelta(days=days), "reason": reason}, actor_id=owner
        )
    if r_early is not None:
        # Filed while the main application was pending and granted well before it: the site was
        # cleared and excavated at the owner's risk until the building permit arrived.
        a = await file(r_early, today - timedelta(days=150), "ES-2026-0031")
        await svc.record_decision(
            pid,
            a.id,
            {
                "outcome": "granted_with_conditions",
                "decision_date": today - timedelta(days=128),
                "served_date": today - timedelta(days=126),
                "reference": "ES-2026-0031",
                "conditions": _early_start_conditions(owner),
            },
            actor_id=owner,
            today=today,
        )
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
    granted = await svc.record_decision(
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
    permit = granted["permit"]
    by_number = {c.number: c for c in await svc.repo.conditions_of_permit(pid, permit.id)}
    # The fence is up and photographed; the owner submitted the evidence and a second person has
    # yet to verify it (four eyes), so the register shows one condition waiting for its verifier.
    await svc.add_evidence(
        pid,
        by_number["3"].id,
        {"kind": "photo", "note": "Tree protection fence along the northern boundary, photographed from the gate"},
        actor_id=owner,
        can_manage=True,
    )
    await svc.submit_evidence(pid, by_number["3"].id, actor_id=owner, can_manage=True)
    # The structural calculations went to the authority, which discharged the condition itself.
    dis = await svc.create_application(
        pid,
        {
            "requirement_id": r_bld.id,
            "kind": "discharge_of_conditions",
            "parent_permit_id": permit.id,
            "discharges_condition_ids": [by_number["1"].id],
            "authority_name": "Local building authority",
            "authority_reference": "BP-2026-0112/D1",
        },
        actor_id=owner,
    )
    filed_on = today - timedelta(days=20)
    await svc.transition_application(pid, dis.id, "preparing", actor_id=owner, can_manage=True, today=filed_on)
    await svc.transition_application(
        pid, dis.id, "submitted", actor_id=owner, can_manage=True, on_date=filed_on, today=filed_on
    )
    await svc.record_decision(
        pid,
        dis.id,
        {
            "outcome": "granted",
            "decision_date": today - timedelta(days=8),
            "reference": "BP-2026-0112/D1",
            "discharged_condition_ids": [by_number["1"].id],
        },
        actor_id=owner,
        today=today,
    )
    if r_road is not None:
        a = await svc.create_application(pid, {"requirement_id": r_road.id}, actor_id=owner)
        await svc.transition_application(pid, a.id, "preparing", actor_id=owner, can_manage=True, today=today)
    return {"requirements": len(made), "conditions": len(conditions)}
