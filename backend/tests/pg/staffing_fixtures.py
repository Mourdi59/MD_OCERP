# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the staffing PostgreSQL tests.

A world is a throwaway database with real users and a project that runs
governance on the shipped ``elf_module_framework`` model (the personnel area
``m05_personnel`` and its frame document), a demo roster from the teams seed,
and a staffing plan pinned to the requested shipped catalogue. Everything
commits for real, so row locks behave as in production.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.project_governance.service import GovernanceService
from app.modules.staffing.service import Actor, StaffingService
from tests.pg.governance_fixtures import World, add_container, add_project, add_route, add_user

GATE = "development_to_execution"
# Relative to the run day: a fill must be running today for the derived status to read ``filled``.
START = date.today() - timedelta(days=30)
COMMISSIONING = date.today() + timedelta(days=600)


def admin(w: World) -> Actor:
    return Actor(w.manager, {"role": "admin"})


async def build_world(
    factory: async_sessionmaker[AsyncSession], *, catalogue_id: str = "neutral", governance: bool = True
) -> World:
    from app.modules.staffing.catalogue import register_kinds
    from app.modules.teams.seed import seed_teams_roster

    register_kinds()
    async with factory() as s:
        manager = await add_user(s, "manager")
        decider = await add_user(s, "manager")
        owner = await add_user(s, "manager")
        editor = await add_user(s, "editor")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [decider, owner, editor])
        w = World(factory, pid, manager, decider, owner, editor, outsider)
        if governance:
            w.gate_route_id = await add_route(s, pid, "phase_gate", decider)
            w.change_route_id = await add_route(s, pid, "frame_change", decider)
            await GovernanceService(s).set_model(
                pid,
                source="shipped",
                catalogue_id="elf_module_framework",
                version=None,
                four_eyes=True,
                actor_id=manager,
                tenant_id=str(manager),
            )
            for d in await GovernanceService(s).repo.list_documents(pid):
                w.containers[d.doc_type] = await add_container(s, pid, d.doc_type)
        await seed_teams_roster(s, project_id=pid)
        await StaffingService(s).set_plan(
            pid,
            actor_id=manager,
            tenant_id=str(manager),
            catalogue_id=catalogue_id,
            commissioning_date=COMMISSIONING,
        )
        await s.commit()
    return w


async def call(w: World, fn: str, *args: Any, **kw: Any) -> Any:
    """Run one service method in its own committed session."""
    async with w.factory() as s:
        out = await getattr(StaffingService(s), fn)(w.project_id, *args, **kw)
        await s.commit()
        return out


async def members(w: World) -> list[Any]:
    from app.modules.teams.models import RosterMember

    async with w.factory() as s:
        stmt = select(RosterMember).where(RosterMember.project_id == w.project_id).order_by(RosterMember.created_at, RosterMember.id)
        return list((await s.execute(stmt)).scalars())


async def position(w: World, role_code: str, phase: str = "execution", **extra: Any) -> uuid.UUID:
    row = await call(
        w, "create_position", {"role_code": role_code, "phase": phase, "entry_date": START, **extra}, w.manager
    )
    return row.id


async def fill(w: World, position_id: uuid.UUID, member_id: uuid.UUID, share: str = "1", **extra: Any) -> uuid.UUID:
    data = {"roster_member_id": member_id, "fte_share": share, "from_date": START, **extra}
    row = await call(w, "create_fill", position_id, data, w.manager)
    return row.id


async def personnel_file(w: World, member_id: uuid.UUID, **extra: Any) -> uuid.UUID:
    row = await call(w, "create_file", {"roster_member_id": member_id, **extra}, admin(w))
    return row.id


async def credential(w: World, credential_type: str, valid_until: date | None, holder: str = "Holder") -> uuid.UUID:
    from app.modules.credentials.models import Credential

    async with w.factory() as s:
        c = Credential(
            project_id=w.project_id,
            holder_name=holder,
            holder_kind="person",
            credential_type=credential_type,
            valid_until=valid_until,
            notify_days_before=30,
        )
        s.add(c)
        await s.commit()
        return c.id


async def submittable_plan(w: World) -> dict[str, uuid.UUID]:
    """Every key role of the neutral catalogue planned, operation roles before commissioning, handovers linked."""
    ids: dict[str, uuid.UUID] = {}
    for code in (
        "project_director",
        "project_manager",
        "design_manager",
        "cost_manager",
        "contract_manager",
        "hse_manager",
        "site_manager",
        "commissioning_manager",
    ):
        ids[code] = await position(w, code)
    ids["operator_plant_manager"] = await position(w, "operator_plant_manager", "operation")
    people = await members(w)
    pm_fill = await fill(w, ids["project_manager"], people[0].id)
    dm_fill = await fill(w, ids["design_manager"], people[1].id)
    await call(
        w,
        "create_handover",
        {"from_fill_id": pm_fill, "to_position_id": ids["operator_plant_manager"], "overlap_days": 30, "scope": ""},
        w.manager,
    )
    await call(
        w,
        "create_handover",
        {"from_fill_id": dm_fill, "to_position_id": ids["commissioning_manager"], "overlap_days": 30, "scope": ""},
        w.manager,
    )
    return ids


def days(n: int) -> date:
    return date.today() + timedelta(days=n)
