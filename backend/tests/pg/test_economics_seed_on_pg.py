# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The demo seed fills a demo project's economics from its own bill, and only that.

The figures are derived from the bill (every frame group rounded up to 100 000, the markups likewise
as the allowance), the sources add up to the frame to the cent, and a re-run adds nothing.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.economics.seed import PROFILES, seed_economics_demo
from tests._pg import isolated_engine
from tests.pg.economics_fixtures import build_world, call
from tests.pg.governance_fixtures import World

pytestmark = pytest.mark.asyncio


async def _mark(w: World, demo_id: str) -> None:
    from app.modules.projects.models import Project

    async with w.factory() as s:
        await s.execute(update(Project).where(Project.id == w.project_id).values(metadata_={"demo_id": demo_id}))
        await s.commit()


async def _seed(w: World) -> dict:
    async with w.factory() as s:
        out = await seed_economics_demo(s, [w.project_id])
        await s.commit()
        return out


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory, governance=False)


async def test_a_project_without_the_demo_marker_is_left_alone(world: World) -> None:
    out = await _seed(world)
    assert out["projects"] == 0
    assert (await call(world, "cost_frame"))["lines"] == []


async def test_a_demo_project_gets_a_frame_a_case_and_covering_financing(world: World) -> None:
    await _mark(world, "residential-regensburg")
    out = await _seed(world)
    assert out["ok"] is True and out["projects"] == 1

    frame = await call(world, "cost_frame")
    # direct cost 1 760 000: two cost groups carry 1 750 000, the uncoded 10 000 sits under no line
    amounts = {row["code"]: Decimal(row["amount"]) for row in frame["lines"]}
    assert len(amounts) == 2
    assert sum(amounts.values()) >= Decimal("1750000")
    for row in frame["lines"]:
        assert Decimal(row["amount"]) % Decimal("100000") == 0
        assert Decimal(row["amount"]) >= Decimal(row["estimate"])
    assert Decimal(frame["totals"]["markup_allowance"]) % Decimal("100000") == 0
    assert Decimal(frame["totals"]["markup_allowance"]) >= Decimal(frame["totals"]["markups"])

    financing = await call(world, "financing")
    assert financing["coverage"]["covered"] is True
    assert Decimal(financing["coverage"]["shortfall"]) == 0
    assert Decimal(financing["coverage"]["surplus"]) == 0
    assert Decimal(financing["coverage"]["sources_total"]) == Decimal(frame["totals"]["frame"])
    assert len(financing["sources"]) == len(PROFILES["residential-regensburg"].sources)
    for source in financing["sources"]:
        assert source["tranche_total"] == source["amount"]

    readiness = await call(world, "readiness")
    assert [f["code"] for f in readiness["errors"]] == []
    case = await call(world, "business_case")
    assert case["key_figures"]["npv"] is not None
    assert Decimal(case["key_figures"]["total_investment"]) == Decimal(frame["totals"]["frame"])


async def test_a_second_run_adds_nothing(world: World) -> None:
    await _mark(world, "school-ludwigsburg")
    first = await _seed(world)
    again = await _seed(world)
    assert first["projects"] == 1
    assert again["projects"] == 0
    assert len((await call(world, "financing"))["sources"]) == len(PROFILES["school-ludwigsburg"].sources)


async def test_a_demo_project_without_a_bill_is_skipped_with_a_reason() -> None:
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        w = await build_world(factory, governance=False, bill=False)
        await _mark(w, "residential-regensburg")
        out = await _seed(w)
    assert out["projects"] == 0
    assert out["skipped"] == [{"project_id": str(w.project_id), "reason": "no_bill"}]
