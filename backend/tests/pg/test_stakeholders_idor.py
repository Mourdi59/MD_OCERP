# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read, mask and decide in the stakeholders API, over HTTP against PostgreSQL."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.stakeholders.permissions import register_stakeholder_permissions
from app.modules.stakeholders.router import router
from tests._pg import isolated_engine
from tests.pg.stakeholders_fixtures import World, build_world, stakeholder

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/stakeholders"


@pytest_asyncio.fixture
async def world():
    register_stakeholder_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


@asynccontextmanager
async def client_as(w: World, user_id: uuid.UUID, role: str):
    from app.dependencies import get_current_user_id, get_current_user_payload, get_session

    app = FastAPI()
    app.include_router(router, prefix=BASE)

    async def _session():
        async with w.factory() as s:
            yield s
            await s.commit()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user_id] = lambda: str(user_id)
    app.dependency_overrides[get_current_user_payload] = lambda: {
        "sub": str(user_id),
        "role": role,
        "permissions": [],
        "tenant_id": str(user_id),
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://stk-test") as c:
        yield c


async def test_a_stranger_from_another_tenant_gets_404_everywhere(world: World) -> None:
    sid = await stakeholder(world, "Jane Private", category="neighbour")
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.outsider, "manager") as c:
        listed = await c.get(f"{p}/stakeholders")
        read = await c.get(f"{p}/stakeholders/{sid}")
        assessed = await c.post(f"{p}/stakeholders/{sid}/assessments", json={"scores": {"power": 3, "interest": 3}})
        exported = await c.get(f"{p}/export")
    assert [r.status_code for r in (listed, read, assessed, exported)] == [404, 404, 404, 404]


async def test_another_projects_stakeholder_is_404_inside_my_project(world: World) -> None:
    other = await build_world(world.factory)
    foreign = await stakeholder(other, "Elsewhere")
    async with client_as(world, world.editor, "editor") as c:
        r = await c.get(f"{BASE}/projects/{world.project_id}/stakeholders/{foreign}")
    assert r.status_code == 404


async def test_a_foreign_meeting_link_on_an_event_is_404(world: World) -> None:
    async with client_as(world, world.editor, "editor") as c:
        r = await c.post(
            f"{BASE}/projects/{world.project_id}/events",
            json={"title": "Info evening", "meeting_id": str(uuid.uuid4())},
        )
    assert r.status_code == 404


async def test_an_editor_without_read_personal_sees_masked_names(world: World) -> None:
    await stakeholder(world, "Jane Private", category="neighbour")
    async with client_as(world, world.editor, "editor") as c:
        r = await c.get(f"{BASE}/projects/{world.project_id}/stakeholders")
        exported = await c.get(f"{BASE}/projects/{world.project_id}/export", params={"format": "xlsx"})
    assert r.status_code == 200
    row = r.json()["items"][0]
    assert row["masked"] is True and row["name"] is None
    assert b"Jane Private" not in exported.content


async def test_a_viewer_cannot_put_mandates(world: World) -> None:
    rows = [{"decision_type": "scope_change", "holder_kind": "role", "holder_code": "client", "letter": "D"}]
    async with client_as(world, world.viewer, "viewer") as c:
        r = await c.put(f"{BASE}/projects/{world.project_id}/organisation/mandates", json={"rows": rows})
    assert r.status_code == 403
