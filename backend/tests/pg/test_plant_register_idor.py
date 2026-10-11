# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read and change the plant register, over HTTP against PostgreSQL; plus the API contract (rule 19).

Identity is the variable under test: a stranger from another tenant, a project
member reaching for another project's item, an editor who does not own the
equipment area, and an editor trying to approve a decision paper.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.plant_register.models import PlantItem
from app.modules.plant_register.permissions import register_plant_permissions
from app.modules.plant_register.ports import unregister_package_plan_provider
from app.modules.plant_register.router import router
from tests._pg import isolated_engine
from tests.pg.plant_fixtures import World, build_world, get, item, quote

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/plant-register"


@pytest_asyncio.fixture
async def world():
    register_plant_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)
    unregister_package_plan_provider()


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://plant-test") as c:
        yield c


async def test_a_stranger_from_another_tenant_cannot_read_or_write(world: World) -> None:
    iid = await item(world)
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.outsider, "manager") as c:
        codes = [
            (await c.get(f"{p}/items")).status_code,
            (await c.get(f"{p}/items/{iid}")).status_code,
            (await c.patch(f"{p}/items/{iid}", json={"title": "Taken"})).status_code,
            (
                await c.post(
                    f"{p}/items/{iid}/quotes",
                    json={
                        "source": "supplier_quote",
                        "enquiry_date": "2026-08-03",
                        "lead_weeks_min": 1,
                        "lead_weeks_max": 2,
                    },
                )
            ).status_code,
            (await c.get(f"{p}/long-lead")).status_code,
            (await c.get(f"{p}/export/register")).status_code,
        ]
    assert codes == [404] * 6
    assert (await get(world, PlantItem, iid)).title == "Item PL-1"


async def test_an_item_of_another_project_is_404_through_this_project(world: World) -> None:
    other = await build_world(world.factory, provider=world.provider)
    foreign = await item(other, code="X-1")
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.manager, "manager") as c:
        read = await c.get(f"{p}/items/{foreign}")
        quotes = await c.get(f"{p}/items/{foreign}/quotes")
        patched = await c.patch(f"{p}/items/{foreign}", json={"title": "Taken"})
    assert [read.status_code, quotes.status_code, patched.status_code] == [404, 404, 404]
    assert read.json()["detail"]["code"] == "item_not_found"
    assert (await get(world, PlantItem, foreign)).title == "Item X-1"


async def test_a_foreign_schedule_activity_cannot_be_linked(world: World) -> None:
    iid = await item(world)
    async with client_as(world, world.manager, "manager") as c:
        r = await c.patch(
            f"{BASE}/projects/{world.project_id}/items/{iid}", json={"need_activity_id": str(uuid.uuid4())}
        )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "link_not_found"


async def test_an_editor_who_does_not_own_the_equipment_area_cannot_write(world: World) -> None:
    p = f"{BASE}/projects/{world.project_id}"
    body = {"code": "PL-9", "title": "Chiller", "component_class_code": "chiller"}
    async with client_as(world, world.editor, "editor") as c:
        refused = await c.post(f"{p}/items", json=body)
    async with client_as(world, world.area_owner, "editor") as c:
        allowed = await c.post(f"{p}/items", json=body)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "not_equipment_owner"
    assert allowed.status_code == 201


async def test_an_editor_cannot_approve_a_decision_paper(world: World) -> None:
    from app.modules.approval_routes.schemas import DecisionSubmit
    from app.modules.approval_routes.service import ApprovalRouteService

    iid = await item(world)
    p = f"{BASE}/projects/{world.project_id}/items/{iid}/decision-paper"
    body = {
        "options": [{"code": "a", "scores": {"c": "1"}}, {"code": "b", "scores": {"c": "2"}}],
        "criteria": [{"code": "c", "weight": "1"}],
        "recommendation": "b",
        "rationale": "Better.",
    }
    async with client_as(world, world.area_owner, "editor") as c:
        created = await c.post(p, json=body)
        submitted = await c.post(f"{p}/{created.json()['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    instance_id = uuid.UUID(submitted.json()["approval_instance_id"])
    async with world.factory() as s:
        svc = ApprovalRouteService(s)
        inst = await svc.get_instance(instance_id)
        step = (await svc.repo.list_steps(inst.route_id))[0]
        with pytest.raises(HTTPException) as exc:
            await svc.submit_decision(
                inst.id,
                DecisionSubmit(step_id=step.id, decision="approved", comment=None),
                approver_id=world.editor,
                caller_role="editor",
            )
    assert exc.value.status_code == 403


async def test_list_envelope_derived_fields_and_coded_errors(world: World) -> None:
    iid = await item(world, need_date_fixed=None)
    await quote(world, iid)
    p = f"{BASE}/projects/{world.project_id}"
    async with client_as(world, world.manager, "manager") as c:
        listed = await c.get(f"{p}/items", params={"today": "2026-10-11"})
        no_enquiry = await c.post(
            f"{p}/items/{iid}/quotes", json={"source": "supplier_quote", "lead_weeks_min": 1, "lead_weeks_max": 2}
        )
        float_fee = await c.post(f"{p}/items/{iid}/slot", json={"reservation_fee": 100.5})
        catalogue = await c.get(f"{p}/catalogue")
        validation = await c.get(f"{p}/validation", params={"today": "2026-10-11"})
    body = listed.json()
    assert {"items", "total", "offset", "limit"} <= set(body)
    row = body["items"][0]
    assert row["long_lead"] is True and row["effective_lead_weeks"] == 44 and row["lead_source"] == "supplier_quote"
    assert row["basis_enquiry_date"] == "2026-08-03" and row["quote_age_days"] == 69
    assert no_enquiry.status_code == 422
    assert no_enquiry.json()["detail"]["code"] == "lead_time_without_enquiry_date"
    assert no_enquiry.json()["detail"]["message_key"] == "plant.errors.lead_time_without_enquiry_date"
    assert float_fee.status_code == 422
    assert catalogue.status_code == 200 and len(catalogue.json()["component_classes"]) == 23
    assert validation.status_code == 200 and {"items", "total"} <= set(validation.json())
