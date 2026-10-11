# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read, edit and propose, over HTTP against PostgreSQL; plus the API contract.

Identity is the variable under test: a stranger from another tenant, a project
member reaching for another project's package or procurement row, and an
editor trying to propose (manager only). There is no approve route to attack:
the governance gate approves the decision (lead decision 2).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.delivery_model.permissions import register_delivery_model_permissions
from app.modules.delivery_model.router import router
from tests._pg import isolated_engine
from tests.pg.delivery_fixtures import build_world, call, compare, state
from tests.pg.governance_fixtures import World

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/delivery-model"


@pytest_asyncio.fixture
async def world():
    register_delivery_model_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory, governance=False)


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://dm-test") as c:
        yield c


async def _contract(w: World) -> uuid.UUID:
    from app.modules.contracts.models import Contract

    async with w.factory() as s:
        c = Contract(
            project_id=w.project_id,
            code=f"C-{uuid.uuid4().hex[:6]}",
            title="Works",
            contract_type="lump_sum",
            counterparty_type="subcontractor",
            total_value=Decimal("100000"),
            currency="EUR",
            status="active",
            metadata_={},
        )
        s.add(c)
        await s.commit()
        return c.id


async def test_a_stranger_from_another_tenant_cannot_read_edit_or_propose(world: World) -> None:
    ids = await compare(world)
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.outsider, "manager") as c:
        responses = [
            await c.get(f"{p}/model"),
            await c.get(f"{p}/comparison"),
            await c.get(f"{p}/allocations"),
            await c.get(f"{p}/packages"),
            await c.get(f"{p}/decisions"),
            await c.get(f"{p}/export?what=decision&format=xlsx"),
            await c.post(f"{p}/options", json={"form_code": "cm_at_risk"}),
            await c.put(f"{p}/allocations/insurance", json={"party": "owner"}),
            await c.post(f"{p}/decision", json={"option_id": str(ids["design_build"]), "rationale": "x"}),
        ]
    assert [r.status_code for r in responses] == [404] * len(responses)
    assert (await state(world)).status == "under_evaluation"


async def test_another_projects_rows_are_404_and_not_linked(world: World) -> None:
    other = await build_world(world.factory, governance=False)
    foreign_contract = await _contract(other)
    await compare(world)
    pkg = await call(
        world,
        "create_package",
        {"code": "P1", "title": "Works", "kind": "construction", "builds": True, "party": "contractor"},
        world.manager,
    )
    foreign_pkg = await call(
        other,
        "create_package",
        {"code": "P9", "title": "Other", "kind": "construction", "builds": True, "party": "contractor"},
        other.manager,
    )
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.editor, "editor") as c:
        link = await c.put(
            f"{p}/packages/{pkg.id}/link", json={"link_kind": "contract", "link_id": str(foreign_contract)}
        )
        reach = await c.patch(f"{p}/packages/{foreign_pkg.id}", json={"title": "mine now"})
        ofi = await c.post(f"{p}/ofi", json={"code": "O1", "description": "Pump", "package_id": str(foreign_pkg.id)})
    assert [link.status_code, reach.status_code, ofi.status_code] == [404, 404, 404]
    assert link.json()["detail"]["code"] == "linked_record_not_found"
    views = await call(world, "package_views")
    assert views[0]["link"] is None


async def test_an_editor_cannot_propose_or_pin(world: World) -> None:
    ids = await compare(world)
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.editor, "editor") as c:
        proposed = await c.post(f"{p}/decision", json={"option_id": str(ids["design_build"]), "rationale": "x"})
        pinned = await c.post(
            f"{p}/model/catalogue",
            json={"catalogue_source": "shipped", "catalogue_id": "neutral", "form_mapping": {}, "category_mapping": {}},
        )
        edited = await c.put(f"{p}/allocations/insurance", json={"party": "insurer", "basis": "insurance"})
    assert [proposed.status_code, pinned.status_code, edited.status_code] == [403, 403, 200]


async def test_api_contract_envelope_and_coded_errors(world: World) -> None:
    ids = await compare(world, ("design_build",))
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.manager, "manager") as c:
        options = await c.get(f"{p}/options")
        single = await c.post(f"{p}/decision", json={"option_id": str(ids["design_build"]), "rationale": "why"})
        float_weight = await c.patch(f"{p}/criteria", json={"weights": {"innovation": 7.5}})
        unknown_form = await c.post(f"{p}/options", json={"form_code": "no_such_form"})
        missing = await c.get(f"{p}/decision")
        consistency = await c.get(f"{p}/packages/consistency")
        validation = await c.get(f"{p}/validation")
        export = await c.get(f"{p}/export?what=matrix&format=pdf")
    body = options.json()
    assert {"items", "total", "offset", "limit"} <= set(body) and body["total"] == 1
    assert single.status_code == 422
    assert single.json()["detail"]["code"] == "single_option_decision"
    assert single.json()["detail"]["message_key"] == "delivery_model.errors.single_option_decision"
    assert float_weight.status_code == 422
    assert unknown_form.status_code == 422 and unknown_form.json()["detail"]["code"] == "form_unknown"
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "decision_missing"
    assert {"items", "total", "errors", "warnings"} <= set(consistency.json())
    rules = {f["rule_id"] for f in validation.json()["items"]}
    assert len(rules) == 11
    assert export.status_code == 200 and export.content[:4] == b"%PDF"
