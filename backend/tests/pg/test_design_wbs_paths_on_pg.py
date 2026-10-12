# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""WBS rules hold on the projects write paths: duplication and the projects router."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.models import Project, ProjectWBS
from tests._pg import isolated_engine
from tests.pg.design_fixtures import DesignWorld, build_design_world

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def world():
    from app.modules.design_management import on_startup

    await on_startup()
    async with isolated_engine() as engine:
        yield await build_design_world(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))


async def _add_raw(w: DesignWorld, *codes: tuple[str, str | None]) -> None:
    """Write nodes straight into the table, past every check, as legacy data would be."""
    async with w.factory() as s:
        ids: dict[str, object] = {}
        for code, parent in codes:
            node = ProjectWBS(project_id=w.project_id, parent_id=ids.get(parent), code=code, name=code, level=0)
            s.add(node)
            await s.flush()
            ids[code] = node.id
        await s.commit()


def _projects(session: AsyncSession):
    from app.config import get_settings
    from app.modules.projects.service import ProjectService

    return ProjectService(session, get_settings())


async def test_duplicating_a_project_with_a_broken_tree_is_refused_and_writes_nothing(world: DesignWorld) -> None:
    await _add_raw(world, ("1", None), ("2.1", "1"))  # child outside its parent's prefix, rule 2
    async with world.factory() as s:
        before = (await s.execute(select(func.count()).select_from(Project))).scalar_one()
        with pytest.raises(HTTPException) as exc:
            await _projects(s).duplicate_project(world.project_id, world.manager)
        await s.rollback()
        after = (await s.execute(select(func.count()).select_from(Project))).scalar_one()
    assert exc.value.status_code == 422
    assert [v["code"] for v in exc.value.detail["violations"]] == ["wbs_code_not_under_parent"]
    assert after == before


async def test_duplicating_a_clean_tree_still_works(world: DesignWorld) -> None:
    await _add_raw(world, ("1", None), ("1.1", "1"))
    async with world.factory() as s:
        copy = await _projects(s).duplicate_project(world.project_id, world.manager)
        await s.commit()
        codes = (await s.execute(select(ProjectWBS.code).where(ProjectWBS.project_id == copy.id))).scalars().all()
    assert sorted(codes) == ["1", "1.1"]


async def test_the_tree_check_the_projects_router_calls_refuses_a_duplicate_code(world: DesignWorld) -> None:
    from app.core.wbs_rules import check_wbs_tree

    await _add_raw(world, ("1", None))
    async with world.factory() as s:
        s.add(ProjectWBS(project_id=world.project_id, code="1", name="again", level=0))
        await s.flush()
        with pytest.raises(HTTPException) as exc:
            await check_wbs_tree(s, world.project_id)
    assert exc.value.detail["violations"][0]["code"] == "wbs_code_duplicate"
