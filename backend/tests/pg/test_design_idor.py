# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read and write design data, over HTTP against PostgreSQL (rule 24)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.design_management.router import router
from tests._pg import isolated_engine
from tests.pg.design_fixtures import DesignWorld, build_design_world, drawing_with_revision

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/design-management"


@pytest_asyncio.fixture
async def world():
    from app.modules.design_management import on_startup

    await on_startup()
    async with isolated_engine() as engine:
        yield await build_design_world(async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False))


@asynccontextmanager
async def client_as(w: DesignWorld, user_id: uuid.UUID, role: str):
    from app.dependencies import get_current_user_id, get_current_user_payload, get_session

    app = FastAPI()
    app.include_router(router, prefix=BASE)

    async def _session():
        async with w.factory() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    app.dependency_overrides[get_current_user_payload] = lambda: {"sub": str(user_id), "role": role, "permissions": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://design-test") as c:
        yield c


async def test_a_stranger_cannot_read_or_write_the_register(world: DesignWorld) -> None:
    async with client_as(world, world.outsider, "manager") as c:
        listed = await c.get(f"{BASE}/projects/{world.project_id}/drawings")
        setup = await c.get(f"{BASE}/projects/{world.project_id}/setup")
        alloc = await c.post(
            f"{BASE}/projects/{world.project_id}/numbering/allocate", json={"role_id": str(world.roles["ARCH"])}
        )
    assert {listed.status_code, setup.status_code, alloc.status_code} == {404}


async def test_a_revision_of_another_project_cannot_enter_a_release(world: DesignWorld) -> None:
    other = await build_design_world(world.factory)
    _d, foreign_rev = await drawing_with_revision(other, "ARCH")
    async with client_as(world, world.manager, "manager") as c:
        r = await c.post(f"{BASE}/projects/{world.project_id}/releases", json={"revision_ids": [str(foreign_rev)]})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "revision_not_found"


async def test_a_role_id_from_another_project_is_404(world: DesignWorld) -> None:
    other = await build_design_world(world.factory)
    async with client_as(world, world.manager, "manager") as c:
        r = await c.patch(f"{BASE}/projects/{world.project_id}/roles/{other.roles['ARCH']}", json={"title": "x"})
    assert r.status_code == 404


async def test_an_editor_cannot_manage_the_distribution_matrix(world: DesignWorld) -> None:
    async with client_as(world, world.editor, "editor") as c:
        r = await c.post(
            f"{BASE}/projects/{world.project_id}/distribution-rules",
            json={"recipient_role_id": str(world.roles["ARCH"])},
        )
    assert r.status_code == 403
