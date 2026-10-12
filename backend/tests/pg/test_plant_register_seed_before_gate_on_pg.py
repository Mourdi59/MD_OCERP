# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The demo register of the recorded project stands before the gate, on PostgreSQL.

The project whose phase model is pinned from a pack is seeded as one day of
its life: in development, three weeks before the gate that enables construction
start. Nothing may contradict that day: no item past ``ordered``, need dates
after the construction start, long-lead order dates before the gate date.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.plant_register import seed
from app.modules.plant_register.models import DecisionPaper, ItService, PlantItem, SlotReservation
from app.modules.plant_register.ports import unregister_commitment_provider, unregister_package_plan_provider
from app.modules.plant_register.service import PlantService
from tests._pg import isolated_engine
from tests.pg.plant_fixtures import World, build_world

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)
    unregister_package_plan_provider()
    unregister_commitment_provider()


async def _as_demo_project(w: World) -> None:
    from app.modules.approval_routes.models import Route, Step
    from app.modules.projects.models import Project

    async with w.factory() as s:
        project = await s.get(Project, w.project_id)
        project.metadata_ = {"demo_id": "plant-demo"}
        project.currency = "CAD"
        for step in (await s.execute(select(Step).where(Step.route_id == w.route_id))).scalars():
            await s.delete(step)
        await s.delete(await s.get(Route, w.route_id))
        await s.commit()


async def test_a_project_with_a_shipped_phase_model_is_not_the_recorded_one(world: World) -> None:
    async with world.factory() as s:
        assert await seed._pins_a_pack_model(s, world.project_id) is False


async def test_the_recorded_project_is_seeded_as_the_day_before_its_gate(world: World, monkeypatch) -> None:
    await _as_demo_project(world)

    async def recorded(session, project_id) -> bool:
        return True

    monkeypatch.setattr(seed, "_pins_a_pack_model", recorded)
    today = datetime.now(UTC).date()
    async with world.factory() as s:
        out = await seed.seed_plant_register_demo(s, [world.project_id])
        await s.commit()
    assert out["projects"] == 1 and out["items"] == 13

    async with world.factory() as s:
        items = list((await s.execute(select(PlantItem).where(PlantItem.project_id == world.project_id))).scalars())
        slots = list(
            (await s.execute(select(SlotReservation).where(SlotReservation.project_id == world.project_id))).scalars()
        )
        papers = list(
            (await s.execute(select(DecisionPaper).where(DecisionPaper.project_id == world.project_id))).scalars()
        )
        services = list((await s.execute(select(ItService).where(ItService.project_id == world.project_id))).scalars())
        views = await PlantService(s).item_views(world.project_id, today=today)

    # Nothing of execution has happened: one item is ordered, none is further.
    assert {i.status for i in items} == {"identified", "specified", "enquired", "route_set", "ordered", "cancelled"}
    assert [i.code for i in items if i.status == "ordered"] == ["PL-005"]
    by_code = {i.code: i for i in items}
    assert by_code["PL-001"].status == "enquired"
    assert sorted(s.status for s in slots) == ["held", "requested"]
    assert [p.status for p in papers] == ["approved"]

    start = today + timedelta(days=seed.CONSTRUCTION_START_DAYS)
    gate = today + timedelta(days=seed.GATE_TARGET_DAYS)
    assert all(i.need_date_fixed > start for i in items)
    long_lead = [v for v in views if v["long_lead"] and v["item"].status != "cancelled"]
    assert len(long_lead) >= 5
    # Each long-lead item has to be ordered before the gate date, and none is overdue on the seed day.
    assert {v["code"]: v["latest_order_date"] for v in long_lead if not today <= v["latest_order_date"] < gate} == {}
    assert len({v["latest_order_date"] for v in long_lead}) > 1
    assert "overdue" not in {v["order_status"] for v in views}

    assert {x.status for x in services} == {"planned"}
    assert all(x.needed_from >= today + timedelta(days=30) for x in services)
