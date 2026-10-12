# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The procurement concept API over HTTP against PostgreSQL: who may do what, and the error contract.

Identity is the variable under test: a stranger to the project, a viewer, an
editor who does not own the procurement area, the editor who does, and a
manager. Every route runs through ``verify_project_access`` and the permission
dependencies exactly as in the application.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.procurement_concept.models import AwardPackage, ProcurementConcept
from app.modules.procurement_concept.permissions import register_procurement_concept_permissions
from app.modules.procurement_concept.router import router
from tests._pg import isolated_engine
from tests.pg.procurement_concept_fixtures import (
    OTHER_GATE,
    World,
    add_contract_package,
    add_procurement_area,
    bind_frame_document,
    build_world,
    patch_hosting,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/procurement-concept"
OPEN_WORKS = {"estimated_value": "900000", "currency": "EUR", "procedure_code": "open"}


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    register_procurement_concept_permissions()
    patch_hosting(monkeypatch)
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        w = await build_world(factory)
        await add_contract_package(w, "W1", "construction")
        await add_procurement_area(w, w.area_owner)
        yield w


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pc-test") as c:
        yield c


def _p(w: World, tail: str = "") -> str:
    return f"{BASE}/projects/{w.project_id}{tail}"


def _pkg(w: World, code: str = "W1", tail: str = "") -> str:
    return _p(w, f"/packages/{w.packages[code]}{tail}")


async def _stored_state(w: World) -> str:
    async with w.factory() as s:
        from sqlalchemy import select

        return (
            await s.execute(select(ProcurementConcept.state).where(ProcurementConcept.project_id == w.project_id))
        ).scalar_one()


async def test_a_stranger_gets_404_on_every_kind_of_route_and_changes_nothing(world: World) -> None:
    async with client_as(world, world.outsider, "manager") as c:
        answers = [
            await c.get(_p(world, "/concept")),
            await c.get(_p(world, "/packages")),
            await c.get(_p(world, "/findings")),
            await c.get(_p(world, "/frameworks")),
            await c.put(_p(world, "/concept"), json={"vat_rate_pct": "19"}),
            await c.put(_pkg(world), json=OPEN_WORKS),
            await c.post(_p(world, "/concept/submit")),
            await c.post(_pkg(world, tail="/execution"), json={}),
        ]
    assert [r.status_code for r in answers] == [404] * len(answers)
    async with world.factory() as s:
        assert await s.get(AwardPackage, world.packages["W1"]) is None
    assert await _stored_state(world) == "draft"


async def test_a_viewer_reads_and_cannot_write(world: World) -> None:
    async with client_as(world, world.editor, "viewer") as c:
        read = await c.get(_p(world, "/concept"))
        listed = await c.get(_p(world, "/packages"))
        writes = [
            await c.put(_p(world, "/concept"), json={"vat_rate_pct": "19"}),
            await c.put(_pkg(world), json=OPEN_WORKS),
            await c.post(_p(world, "/concept/submit")),
        ]
    assert read.status_code == 200
    assert {"items", "total", "offset", "limit"} <= set(listed.json())
    assert [r.status_code for r in writes] == [403, 403, 403]


async def test_there_is_no_approve_or_reopen_route(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
        assert (await c.post(_p(world, "/concept/submit"))).status_code == 200
        for action in ("approve", "reopen", "approved", "binding"):
            r = await c.post(_p(world, f"/concept/{action}"))
            assert r.status_code in (404, 405, 422), action
    assert await _stored_state(world) == "in_review"


async def test_the_can_flags_say_what_the_writes_then_enforce(world: World) -> None:
    async with client_as(world, world.editor, "editor") as c:
        can = (await c.get(_p(world, "/concept"))).json()["can"]
        refused = await c.put(_pkg(world), json=OPEN_WORKS)
        submit = await c.post(_p(world, "/concept/submit"))
    assert can["edit_plan"] == {"allowed": False, "reason": "not_procurement_owner"}
    assert can["submit"] == {"allowed": False, "reason": "not_procurement_owner"}
    detail = refused.json()["detail"]
    assert (refused.status_code, detail["code"]) == (403, "not_procurement_owner")
    assert detail["message_key"] == "procurement_concept.errors.not_procurement_owner"
    assert detail["message"] and detail["message"] != detail["message_key"]
    assert submit.status_code == 403

    async with client_as(world, world.area_owner, "editor") as c:
        can = (await c.get(_p(world, "/concept"))).json()["can"]
        ok = await c.put(_pkg(world), json=OPEN_WORKS)
        gate_field = await c.put(_p(world, "/concept"), json={"release_gate_code": OTHER_GATE})
    assert can["edit_plan"] == {"allowed": True, "reason": None}
    assert can["set_gate_fields"] == {"allowed": False, "reason": "manage_required"}
    assert ok.status_code == 200
    assert (gate_field.status_code, gate_field.json()["detail"]["code"]) == (403, "manage_required")

    async with client_as(world, world.manager, "manager") as c:
        body = (await c.get(_p(world, "/concept"))).json()
        set_gate = await c.put(_p(world, "/concept"), json={"release_gate_code": OTHER_GATE})
    assert body["can"]["set_gate_fields"] == {"allowed": True, "reason": None}
    assert set_gate.status_code == 200
    assert set_gate.json()["resolved_release_gate_code"] == OTHER_GATE


async def test_invalid_input_is_a_coded_422(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        null = await c.put(_p(world, "/concept"), json={"jurisdiction": None})
        private = await c.put(_p(world, "/concept"), json={"client_type": "private"})
        no_currency = await c.put(_pkg(world), json={"estimated_value": "100", "procedure_code": "open"})
        decimals = await c.put(_pkg(world), json={"estimated_value": "1.005", "currency": "EUR"})
        bad_id = await c.put(_p(world, "/packages/not-a-uuid"), json=OPEN_WORKS)
        gate = await c.put(_p(world, "/concept"), json={"release_gate_code": "no_such_gate"})
    assert null.status_code == 422
    assert (private.status_code, private.json()["detail"]["code"]) == (422, "public_client_needs_client_type")
    assert (no_currency.status_code, no_currency.json()["detail"]["code"]) == (422, "currency_required")
    assert decimals.status_code == 422
    assert bad_id.status_code == 422
    assert (gate.status_code, gate.json()["detail"]["code"]) == (422, "release_gate_unknown")


async def test_an_id_from_another_project_is_404_for_a_manager_of_this_one(world: World) -> None:
    other = await build_world(world.factory)
    await add_contract_package(other, "X1", "construction")
    async with client_as(world, world.manager, "manager") as c:
        r = await c.put(_p(world, f"/packages/{other.packages['X1']}"), json=OPEN_WORKS)
        t = await c.get(_p(world, f"/packages/{other.packages['X1']}/threshold"))
    assert (r.status_code, r.json()["detail"]["code"]) == (404, "package_not_found")
    assert t.status_code == 404


async def test_short_listing_and_deleting_candidates_need_steering_rights(world: World) -> None:
    from app.modules.subcontractors.models import Subcontractor

    async with world.factory() as s:
        subs = [Subcontractor(legal_name=f"Trade contractor {i}") for i in range(2)]
        s.add_all(subs)
        await s.commit()
    async with client_as(world, world.manager, "manager") as c:
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
    async with client_as(world, world.editor, "editor") as c:
        long = await c.post(_pkg(world, tail="/candidates"), json={"subcontractor_id": str(subs[0].id)})
        short = await c.post(
            _pkg(world, tail="/candidates"), json={"subcontractor_id": str(subs[1].id), "list": "short"}
        )
        cand_id = long.json()["id"]
        move = await c.patch(_p(world, f"/candidates/{cand_id}"), json={"list": "short"})
        delete = await c.delete(_p(world, f"/candidates/{cand_id}"))
    assert long.status_code == 201
    assert [short.status_code, move.status_code, delete.status_code] == [403, 403, 403]
    async with client_as(world, world.area_owner, "editor") as c:
        assert (await c.patch(_p(world, f"/candidates/{cand_id}"), json={"list": "short"})).status_code == 200
        assert (await c.delete(_p(world, f"/candidates/{cand_id}"))).status_code == 204


async def test_frameworks_belong_to_the_callers_company(world: World) -> None:
    body = {
        "code": "FW-1",
        "title": "Rebar",
        "package_kinds": ["supply"],
        "lots": [],
        "max_value": "500000",
        "currency": "EUR",
        "start_date": "2026-01-01",
        "end_date": "2028-12-31",
    }
    async with client_as(world, world.editor, "editor") as c:
        assert (await c.post(f"{BASE}/frameworks", json=body)).status_code == 403
    async with client_as(world, world.manager, "manager") as c:
        made = await c.post(f"{BASE}/frameworks", json=body)
        no_currency = await c.post(f"{BASE}/frameworks", json={**body, "code": "FW-2", "currency": ""})
        mine = await c.get(f"{BASE}/frameworks")
    assert made.status_code == 201
    assert no_currency.status_code == 422
    fw_id = made.json()["id"]
    assert [f["id"] for f in mine.json()["items"]] == [fw_id]
    async with client_as(world, world.outsider, "manager") as c:
        theirs = await c.get(f"{BASE}/frameworks")
        one = await c.get(f"{BASE}/frameworks/{fw_id}")
        ledger = await c.get(f"{BASE}/frameworks/{fw_id}/ledger")
        patch = await c.patch(f"{BASE}/frameworks/{fw_id}", json={"title": "Taken"})
        in_project = await c.get(_p(world, "/frameworks"))
    assert theirs.json()["items"] == []
    assert [one.status_code, ledger.status_code, patch.status_code, in_project.status_code] == [404, 404, 404, 404]
    # A member of the project sees the project's company frameworks, without owning them.
    async with client_as(world, world.area_owner, "editor") as c:
        seen = await c.get(_p(world, "/frameworks"))
        own = await c.get(f"{BASE}/frameworks")
    assert [f["id"] for f in seen.json()["items"]] == [fw_id]
    assert own.json()["items"] == []


async def test_submit_gate_decision_and_execution_over_http(world: World) -> None:
    async with client_as(world, world.area_owner, "editor") as c:
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
        early = await c.post(_pkg(world, tail="/execution"), json={})
        submitted = await c.post(_p(world, "/concept/submit"))
    assert (early.status_code, early.json()["detail"]["code"]) == (409, "concept_not_approved")
    assert submitted.json()["state"] == "in_review"
    assert await bind_frame_document(world, by=world.manager) is True
    async with client_as(world, world.area_owner, "editor") as c:
        concept = (await c.get(_p(world, "/concept"))).json()
        locked = await c.put(_pkg(world), json={"procedure_code": "restricted"})
        ready = (await c.get(_p(world, "/readiness"))).json()
        made = await c.post(_pkg(world, tail="/execution"), json={})
    assert (concept["state"], concept["stored_state"]) == ("binding", "approved")
    assert (concept["submitted_by"], concept["approved_by"]) == (str(world.area_owner), str(world.manager))
    assert concept["four_eyes_violated"] is False
    assert concept["can"]["edit_plan"] == {"allowed": False, "reason": "binding_requires_change_request"}
    assert (locked.status_code, locked.json()["detail"]["code"]) == (409, "binding_requires_change_request")
    assert ready["approved"] is True
    assert (made.status_code, made.json()["kind"]) == (201, "bid_package")
