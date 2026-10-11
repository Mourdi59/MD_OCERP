# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read, link, release and decide, over HTTP against PostgreSQL; plus the API contract.

Identity is the variable under test: a stranger from another tenant, a
project member reaching for another project's document, an editor touching
the matrix, and a holder of a lower tier trying to decide a higher one.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.commitment_release.permissions import register_commitment_permissions
from app.modules.commitment_release.router import router
from tests._pg import isolated_engine
from tests.pg.commitment_fixtures import World, add_contract, build_world, item, request, state

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/commitment-release"


@pytest_asyncio.fixture
async def world():
    register_commitment_permissions()
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://cmt-test") as c:
        yield c


async def test_a_stranger_from_another_tenant_cannot_read_link_or_release(world: World) -> None:
    iid = await item(world, amount="10000")
    cid = await add_contract(world, "10000")
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.outsider, "manager") as c:
        listed = await c.get(f"{p}/items")
        read = await c.get(f"{p}/items/{iid}")
        linked = await c.post(f"{p}/items/{iid}/links", json={"kind": "contract", "document_id": str(cid)})
        released = await c.post(f"{p}/items/{iid}/releases", json={"amount": "10000"})
    assert [r.status_code for r in (listed, read, linked, released)] == [404, 404, 404, 404]
    assert (await state(world, iid)).status == "planned"


async def test_another_projects_document_is_404_and_is_not_linked(world: World) -> None:
    other = await build_world(world.factory)
    foreign = await add_contract(other, "10000")
    iid = await item(world, amount="10000")
    async with client_as(world, world.requester, "editor") as c:
        r = await c.post(
            f"{BASE}/projects/{world.project_id}/items/{iid}/links",
            json={"kind": "contract", "document_id": str(foreign)},
        )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "document_not_found"


async def test_an_editor_cannot_pin_the_schedule(world: World) -> None:
    async with client_as(world, world.requester, "editor") as c:
        r = await c.put(f"{BASE}/projects/{world.project_id}/matrix", json={"enforcement": "off"})
    assert r.status_code == 403


async def test_a_lower_tier_holder_cannot_decide_a_higher_tier_release(world: World) -> None:
    from app.modules.approval_routes.schemas import DecisionSubmit
    from app.modules.approval_routes.service import ApprovalRouteService

    iid = await item(world, amount="400000")
    d = await request(world, iid, "400000")
    assert d.required_tier == "sponsor"
    async with world.factory() as s:
        svc = ApprovalRouteService(s)
        inst = await svc.get_instance(d.approval_instance_id)
        step = (await svc.repo.list_steps(inst.route_id))[0]
        with pytest.raises(HTTPException) as exc:
            await svc.submit_decision(
                inst.id,
                DecisionSubmit(step_id=step.id, decision="approved", comment=None),
                approver_id=world.pm,
                caller_role="manager",
            )
    assert exc.value.status_code == 403
    assert (await state(world, iid)).status == "release_requested"


async def test_list_envelope_and_coded_validation_errors(world: World) -> None:
    await item(world, code="CR-A", amount="10000")
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.requester, "editor") as c:
        listed = await c.get(f"{p}/items")
        bad = await c.post(
            f"{p}/items",
            json={"code": "CR-B", "title": "x", "commitment_type": "no_such_type", "planned_source": "manual"},
        )
        float_amount = await c.post(f"{p}/items/{uuid.uuid4()}/releases", json={"amount": 10000.5})
    body = listed.json()
    assert {"items", "total", "offset", "limit"} <= set(body)
    assert body["total"] == 1
    assert bad.status_code == 422
    assert float_amount.status_code == 422
