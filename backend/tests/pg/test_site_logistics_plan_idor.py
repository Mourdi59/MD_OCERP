# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Who may read and change a logistics plan, over HTTP against PostgreSQL.

A stranger to the project is 404 on every plan route; an id of another
project's row is 404 inside an accessible project; an editor cannot move a
transport (approve) and does not see customs values.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.site_logistics.permissions import register_site_logistics_permissions
from app.modules.site_logistics.plan_service import LogisticsPlanService
from tests._pg import isolated_engine
from tests.pg.site_logistics_fixtures import BASE, World, build_world, client_as, square, window

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]


@pytest_asyncio.fixture
async def world():
    register_site_logistics_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def _seed_rows(w: World) -> dict:
    start, end = window(5, 8, 2)
    async with w.factory() as s:
        svc = LogisticsPlanService(s)
        stage = (await svc.stages(w.project_id))[0]
        area = await svc.create_area(
            w.project_id, {"code": "Y1", "name": "Yard", "area_kind": "storage", "geometry": square(10)}, w.manager
        )
        transport = await svc.create_transport(
            w.project_id,
            {
                "direction": "inbound",
                "transport_kind": "inbound_delivery",
                "title": "Rebar",
                "planned_window_start": start,
                "planned_window_end": end,
            },
            w.manager,
        )
        case = await svc.create_customs(
            w.project_id,
            {
                "direction": "import",
                "title": "Switchgear",
                "incoterm": "FCA",
                "transport_mode": "road",
                "customs_value": Decimal("1000.00"),
                "currency": "EUR",
            },
            w.manager,
            can_see_values=True,
        )
        await s.commit()
        return {"stage": stage.id, "area": area.id, "transport": transport.id, "case": case.id}


@pytest.mark.parametrize(
    "path",
    [
        "stages",
        "areas",
        "balance",
        "media",
        "concept",
        "transports",
        "permits",
        "customs",
        "neighbourhood",
        "neighbour-issues",
        "coordination",
        "readiness",
        "catalogue",
        "frame-summary",
    ],
)
async def test_a_stranger_gets_404_on_every_plan_list(world: World, path: str) -> None:
    async with client_as(world, world.outsider, "manager") as c:
        r = await c.get(f"{BASE}/projects/{world.project_id}/{path}")
    assert r.status_code == 404, r.text


async def test_a_stranger_cannot_write(world: World) -> None:
    async with client_as(world, world.outsider, "manager") as c:
        r = await c.post(f"{BASE}/projects/{world.project_id}/stages", json={"code": "x", "title": "X"})
    assert r.status_code == 404


async def test_ids_of_another_project_are_404(world: World) -> None:
    other = await build_world(world.factory)
    rows = await _seed_rows(other)
    pid = world.project_id
    async with client_as(world, world.manager, "manager") as c:
        responses = [
            await c.patch(f"{BASE}/projects/{pid}/stages/{rows['stage']}", json={"title": "Taken"}),
            await c.patch(f"{BASE}/projects/{pid}/areas/{rows['area']}", json={"name": "Taken"}),
            await c.get(f"{BASE}/projects/{pid}/transports/{rows['transport']}"),
            await c.post(
                f"{BASE}/projects/{pid}/transports/{rows['transport']}/transition", json={"target": "cancelled"}
            ),
            await c.get(f"{BASE}/projects/{pid}/customs/{rows['case']}"),
            await c.delete(f"{BASE}/projects/{pid}/customs/{rows['case']}"),
            await c.post(
                f"{BASE}/projects/{pid}/permits",
                json={"permit_kind": "oversize_permit", "transport_id": str(rows["transport"])},
            ),
            await c.put(
                f"{BASE}/projects/{pid}/areas/{rows['area']}/allocations",
                json={"items": [{"stage_id": str(rows["stage"]), "allocated_m2": "1"}]},
            ),
        ]
    assert [r.status_code for r in responses] == [404] * len(responses), [r.text for r in responses]
    for r in responses:
        assert r.json()["detail"]["code"].endswith("not_found")


async def test_a_stage_of_another_project_cannot_be_allocated(world: World) -> None:
    other = await build_world(world.factory)
    foreign = await _seed_rows(other)
    own = await _seed_rows(world)
    async with client_as(world, world.manager, "manager") as c:
        r = await c.put(
            f"{BASE}/projects/{world.project_id}/areas/{own['area']}/allocations",
            json={"items": [{"stage_id": str(foreign["stage"]), "allocated_m2": "1"}]},
        )
    assert r.status_code == 404


async def test_an_editor_cannot_move_a_transport_but_a_manager_can(world: World) -> None:
    rows = await _seed_rows(world)
    url = f"{BASE}/projects/{world.project_id}/transports/{rows['transport']}/transition"
    async with client_as(world, world.editor, "editor") as c:
        denied = await c.post(url, json={"target": "scheduled"})
    async with client_as(world, world.manager, "manager") as c:
        allowed = await c.post(url, json={"target": "scheduled"})
    assert denied.status_code == 403
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["state"] == "scheduled"


async def test_customs_values_are_hidden_from_an_editor(world: World) -> None:
    rows = await _seed_rows(world)
    url = f"{BASE}/projects/{world.project_id}/customs/{rows['case']}"
    async with client_as(world, world.editor, "editor") as c:
        editor_view = (await c.get(url)).json()
    async with client_as(world, world.manager, "manager") as c:
        manager_view = (await c.get(url)).json()
    assert editor_view["values_hidden"] is True and editor_view["customs_value"] is None
    assert manager_view["values_hidden"] is False and manager_view["customs_value"] == "1000.00"


async def test_list_envelope_and_coded_errors(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        listed = await c.get(f"{BASE}/projects/{world.project_id}/stages")
        bad = await c.post(f"{BASE}/projects/{world.project_id}/areas", json={"code": "Z", "area_kind": "moon_base"})
    assert set(listed.json()) == {"items", "total", "offset", "limit"}
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert detail["code"] == "unknown_area_kind"
    assert detail["message_key"] == "site_logistics.errors.unknown_area_kind"
    assert detail["message"] and "site_logistics." not in detail["message"]
