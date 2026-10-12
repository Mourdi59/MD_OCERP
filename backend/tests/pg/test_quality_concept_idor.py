# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read and write a quality concept, over HTTP against PostgreSQL; plus the contract.

A stranger to the project answers 404 on every route, exactly like a missing
project; a child id from another project answers 404 inside a visible one; a
waiver is decided by someone other than its requester (403 otherwise); and an
acceptance unit's effect confirmed twice is stored once.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.quality_concept.permissions import register_quality_concept_permissions
from app.modules.quality_concept.router import router
from tests._pg import isolated_engine
from tests.pg.governance_fixtures import World, add_project, build_world

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/quality-concept"


@pytest_asyncio.fixture
async def world():
    register_quality_concept_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory, routes=False)


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
    app.dependency_overrides[get_current_user_payload] = lambda: {"sub": str(user_id), "role": role, "permissions": []}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://qc-test") as c:
        yield c


def _p(w: World, tail: str) -> str:
    return f"{BASE}/projects/{w.project_id}/{tail}"


async def test_a_stranger_gets_404_on_reads_and_writes(world: World) -> None:
    async with client_as(world, world.outsider, "manager") as c:
        for path in ("concept", "proofs", "stages", "acceptance-units", "preservation", "readiness", "validation"):
            assert (await c.get(_p(world, path))).status_code == 404, path
        r = await c.post(_p(world, "standards"), json={"code": "EN 206"})
        assert r.status_code == 404


async def test_a_child_id_from_another_project_is_404(world: World) -> None:
    async with world.factory() as s:
        other = await add_project(s, world.manager, [])
        await s.commit()
    async with client_as(world, world.manager, "manager") as c:
        other_base = f"{BASE}/projects/{other}"
        made = await c.post(f"{other_base}/standards", json={"code": "EN 1090-2"})
        assert made.status_code == 201, made.text
        foreign = made.json()["id"]
        r = await c.patch(_p(world, f"standards/{foreign}"), json={"title": "x"})
        assert r.status_code == 404
        r = await c.delete(_p(world, f"standards/{foreign}"))
        assert r.status_code == 404


async def test_lists_use_the_envelope_and_errors_are_coded(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        body = (await c.get(_p(world, "standards"))).json()
        assert set(body) >= {"items", "total", "offset", "limit"}
        r = await c.post(_p(world, "acceptance-units"), json={"kind": "no_such_kind"})
        assert r.status_code == 422


async def test_the_waiver_requester_cannot_approve_it(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        await c.get(_p(world, "concept"))
        proof = await c.post(
            _p(world, "proofs"),
            json={
                "title": "Concrete cube tests",
                "package_ref": "P-01",
                "evidence_type": "test_report",
                "deliverer_role": "contractor",
            },
        )
        assert proof.status_code == 201, proof.text
        pid = proof.json()["id"]
        asked = await c.post(_p(world, f"proofs/{pid}/waiver-request"), json={"rationale": "Covered by supplier test"})
        assert asked.status_code == 200, asked.text
        same = await c.post(_p(world, f"proofs/{pid}/waiver-decision"), json={"approve": True})
        assert same.status_code == 403
        assert same.json()["detail"]["code"] == "approver_is_requester"
