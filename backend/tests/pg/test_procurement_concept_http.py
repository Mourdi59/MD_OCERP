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
    GATE_CODES,
    OTHER_GATE,
    RELEASE_GATE,
    World,
    add_condition,
    add_contract_package,
    add_procurement_area,
    bind_frame_document,
    build_world,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]

BASE = "/api/v1/procurement-concept"
OPEN_WORKS = {"estimated_value": "900000", "currency": "EUR", "procedure_code": "open"}


@pytest_asyncio.fixture
async def world():
    register_procurement_concept_permissions()
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
    assert can["edit_plan"] == {"allowed": False, "reason": "not_procurement_owner", "applies": True}
    assert can["submit"] == {"allowed": False, "reason": "not_procurement_owner", "applies": True}
    detail = refused.json()["detail"]
    assert (refused.status_code, detail["code"]) == (403, "not_procurement_owner")
    assert detail["message_key"] == "procurement_concept.errors.not_procurement_owner"
    assert detail["message"] and detail["message"] != detail["message_key"]
    assert submit.status_code == 403

    async with client_as(world, world.area_owner, "editor") as c:
        can = (await c.get(_p(world, "/concept"))).json()["can"]
        ok = await c.put(_pkg(world), json=OPEN_WORKS)
        gate_field = await c.put(_p(world, "/concept"), json={"release_gate_code": OTHER_GATE})
    assert can["edit_plan"] == {"allowed": True, "reason": None, "applies": True}
    assert can["set_gate_fields"] == {"allowed": False, "reason": "manage_required", "applies": True}
    assert ok.status_code == 200
    assert (gate_field.status_code, gate_field.json()["detail"]["code"]) == (403, "manage_required")

    async with client_as(world, world.manager, "manager") as c:
        body = (await c.get(_p(world, "/concept"))).json()
        set_gate = await c.put(_p(world, "/concept"), json={"release_gate_code": OTHER_GATE})
    assert body["can"]["set_gate_fields"] == {"allowed": True, "reason": None, "applies": True}
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
    assert concept["can"]["edit_plan"] == {
        "allowed": False,
        "reason": "binding_requires_change_request",
        "applies": True,
    }
    assert (locked.status_code, locked.json()["detail"]["code"]) == (409, "binding_requires_change_request")
    assert ready["approved"] is True
    assert (made.status_code, made.json()["kind"]) == (201, "bid_package")


# ── `can` flags and pickers: the client mirrors no state machine ────────


async def _row(c: AsyncClient, w: World, code: str = "W1") -> dict:
    items = (await c.get(_p(w, "/packages"))).json()["items"]
    return next(i for i in items if i["contract_package"]["code"] == code)


def _no(reason: str) -> dict:
    return {"allowed": False, "reason": reason, "applies": True}


def _na(reason: str) -> dict:
    """The move does not apply to the object as it is, whoever asks: the screen hides it."""
    return {"allowed": False, "reason": reason, "applies": False}


YES = {"allowed": True, "reason": None, "applies": True}


async def test_package_can_flags_answer_what_the_writes_then_do(world: World) -> None:
    async with client_as(world, world.editor, "viewer") as c:
        assert (await _row(c, world))["can"]["edit"] == _no("permission_denied")
        assert (await c.get(_p(world, "/market-soundings"))).json()["can"]["create"] == _no("permission_denied")
        assert (await c.get(_p(world, "/prequal-profiles"))).json()["can"]["create"] == _no("permission_denied")
    async with client_as(world, world.editor, "editor") as c:
        can = (await _row(c, world))["can"]
        assert can["edit"] == _no("not_procurement_owner")
        assert can["create_execution"] == _na("package_not_found")
        assert (await c.get(_p(world, "/market-soundings"))).json()["can"]["create"] == YES
    async with client_as(world, world.manager, "manager") as c:
        before = (await _row(c, world))["can"]
        assert (before["edit"], before["hold"]) == (YES, _na("package_not_found"))
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
        can = (await _row(c, world))["can"]
        assert (can["edit"], can["hold"], can["cancel"], can["confirm_shortlist"]) == (YES, YES, YES, YES)
        assert can["resume"] == _na("package_not_on_hold")
        assert can["create_execution"] == _no("concept_not_approved")
        refused = await c.post(_pkg(world, tail="/execution"), json={})
        assert refused.json()["detail"]["code"] == can["create_execution"]["reason"]
        assert (await c.post(_pkg(world, tail="/state"), json={"action": "hold"})).status_code == 200
        held = (await _row(c, world))["can"]
        assert (held["resume"], held["hold"]) == (YES, _na("invalid_transition"))
        assert (await c.post(_pkg(world, tail="/state"), json={"action": "resume"})).status_code == 200
        assert (await c.post(_p(world, "/concept/submit"))).status_code == 200
    assert await bind_frame_document(world) is True
    async with client_as(world, world.manager, "manager") as c:
        can = (await _row(c, world))["can"]
        assert can["edit"] == _no("binding_requires_change_request")
        assert can["hold"] == _no("binding_requires_change_request")
        # Whether a move applies is answered before who may make it: a locked plan still tells hold from resume.
        assert can["resume"] == _na("package_not_on_hold")
        assert can["create_execution"] == YES
        assert (await c.post(_pkg(world, tail="/execution"), json={})).status_code == 201
        assert (await _row(c, world))["can"]["create_execution"] == _na("execution_exists")


async def test_candidate_profile_and_framework_can_flags(world: World) -> None:
    profile_body = {"name": "Works", "criteria": [{"code": "similar_projects", "weight": "100"}], "pass_mark": "50"}
    framework_body = {
        "code": "FW-1",
        "title": "Rebar",
        "package_kinds": ["supply"],
        "lots": [],
        "max_value": "500000",
        "currency": "EUR",
        "start_date": "2026-01-01",
        "end_date": "2028-12-31",
    }
    async with client_as(world, world.manager, "manager") as c:
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
        profile = (await c.post(_p(world, "/prequal-profiles"), json=profile_body)).json()
        listed = (await c.get(_p(world, "/prequal-profiles"))).json()
        assert listed["can"]["create"] == YES
        assert (listed["items"][0]["in_use"], listed["items"][0]["can"]["delete"]) == (False, YES)
        assert (await c.put(_pkg(world), json={"prequal_profile_id": profile["id"]})).status_code == 200
        item = (await c.get(_p(world, "/prequal-profiles"))).json()["items"][0]
        assert (item["in_use"], item["can"]["delete"]) == (True, _no("profile_in_use"))
        delete = await c.delete(_p(world, f"/prequal-profiles/{profile['id']}"))
        assert (delete.status_code, delete.json()["detail"]["code"]) == (409, "profile_in_use")
        cands = (await c.get(_pkg(world, tail="/candidates"))).json()
        assert cands["can"]["set_list"] == YES
        # The confirm flag is the confirm check: allowed exactly when the list carries no error.
        has_error = any(f["severity"] == "error" for f in cands["findings"])
        confirm = await c.post(_pkg(world, tail="/shortlist"))
        assert cands["can"]["confirm_shortlist"]["allowed"] is (not has_error)
        assert (confirm.status_code == 200) is (not has_error)
        made = (await c.post(f"{BASE}/frameworks", json=framework_body)).json()
        assert made["state"] == "draft"
        mine = (await c.get(f"{BASE}/frameworks")).json()
        assert mine["can"]["create"] == YES
        assert mine["items"][0]["can"] == {"edit": YES, "transitions": ["active", "terminated"]}
    async with client_as(world, world.editor, "editor") as c:
        cands = (await c.get(_pkg(world, tail="/candidates"))).json()["can"]
        assert (cands["add"], cands["score"], cands["reference"]) == (YES, YES, YES)
        assert cands["set_list"] == _no("not_procurement_owner")
        assert cands["delete"] == _no("not_procurement_owner")
        assert cands["confirm_shortlist"] == _no("not_procurement_owner")
        seen = (await c.get(_p(world, "/frameworks"))).json()["items"][0]["can"]
        assert seen == {"edit": _no("permission_denied"), "transitions": []}
        assert (await c.get(f"{BASE}/frameworks")).json()["can"]["create"] == _no("permission_denied")


async def test_pickers_for_the_release_gate_the_advance_release_and_the_tender_package(world: World) -> None:
    from app.modules.tendering.models import TenderPackage

    other = await build_world(world.factory)
    open_condition = await add_condition(world, RELEASE_GATE, status="open")
    await add_condition(world, OTHER_GATE, status="cleared")
    async with world.factory() as s:
        own = TenderPackage(project_id=world.project_id, name="Own tender")
        foreign = TenderPackage(project_id=other.project_id, name="Foreign tender")
        s.add_all([own, foreign])
        await s.commit()
    async with client_as(world, world.outsider, "manager") as c:
        for tail in ("/gates", "/advance-releases", "/tender-packages"):
            assert (await c.get(_p(world, tail))).status_code == 404, tail
    async with client_as(world, world.manager, "manager") as c:
        gates = (await c.get(_p(world, "/gates"))).json()
        assert [g["code"] for g in gates["items"]] == list(GATE_CODES)
        assert [g["sort_order"] for g in gates["items"]] == list(range(1, len(GATE_CODES) + 1))
        assert all(set(g["label"]) == {"key", "text"} and g["label"]["key"] for g in gates["items"])
        assert {g["code"]: (g["tagged_release_gate"], g["selected"]) for g in gates["items"]} == {
            code: (code == RELEASE_GATE, code == RELEASE_GATE) for code in GATE_CODES
        }
        assert (gates["release_gate_code"], gates["resolved_release_gate_code"]) == ("", RELEASE_GATE)
        releases = (await c.get(_p(world, "/advance-releases"))).json()["items"]
        # Only acts of the release gate are offered; the cleared condition of the other gate is not.
        assert {r["gate_code"] for r in releases} == {RELEASE_GATE}
        condition = next(r for r in releases if r["kind"] == "condition")
        assert (condition["id"], condition["status"], condition["releases"]) == (str(open_condition), "open", False)
        tenders = (await c.get(_p(world, "/tender-packages"))).json()["items"]
        assert [(t["id"], t["can"]["link"]) for t in tenders] == [(str(own.id), YES)]
        assert (await c.put(_pkg(world), json=OPEN_WORKS)).status_code == 200
        assert (await c.post(_p(world, "/concept/submit"))).status_code == 200
    assert await bind_frame_document(world) is True
    async with client_as(world, world.manager, "manager") as c:
        linked = await c.post(_pkg(world, tail="/execution/link"), json={"tender_package_id": str(own.id)})
        assert linked.status_code == 201
        (tender,) = (await c.get(_p(world, "/tender-packages"))).json()["items"]
        assert (tender["linked_package_code"], tender["can"]["link"]) == ("W1", _na("execution_exists"))


async def test_catalogues_carry_their_jurisdictions_and_client_types(world: World) -> None:
    async with client_as(world, world.manager, "manager") as c:
        items = (await c.get(f"{BASE}/catalogues")).json()["items"]
    by_id = {i["id"]: i for i in items}
    assert {"eu", "neutral"} <= set(by_id)
    eu = {j["code"]: j for j in by_id["eu"]["jurisdictions"]}
    assert "sub_central" in eu["eu"]["client_types"]
    assert eu["eu"]["private_client_type"] == "private"
    # The neutral catalogue offers no public regime at all; the form can show that before anything is saved.
    assert [j["client_types"] for j in by_id["neutral"]["jurisdictions"]] == [["private"]]
    assert all(i["jurisdictions"] for i in items if i["source"] == "shipped")


async def test_the_cost_reference_picker_lists_what_the_package_body_then_accepts(world: World) -> None:
    from app.modules.boq.models import BOQ, Position

    other = await build_world(world.factory)
    async with world.factory() as s:
        own = BOQ(project_id=world.project_id, name="Main bill")
        foreign = BOQ(project_id=other.project_id, name="Their bill")
        s.add_all([own, foreign])
        await s.flush()
        section = Position(boq_id=own.id, ordinal="01", description="Structure", unit="section", sort_order=1)
        foreign_section = Position(boq_id=foreign.id, ordinal="01", description="Theirs", unit="section")
        s.add_all([section, foreign_section])
        await s.flush()
        line = Position(
            boq_id=own.id, parent_id=section.id, ordinal="01.001", description="Concrete", unit="m3", quantity="12.5"
        )
        s.add(line)
        await s.commit()
    async with client_as(world, world.outsider, "manager") as c:
        assert (await c.get(_p(world, "/cost-refs"))).status_code == 404
    async with client_as(world, world.manager, "manager") as c:
        items = (await c.get(_p(world, "/cost-refs"))).json()["items"]
        assert [(i["kind"], i["id"], i["code"], i["title"], i["positions"]) for i in items] == [
            ("boq_section", str(section.id), "01", "Structure", 1)
        ]
        ok = await c.put(
            _pkg(world), json={**OPEN_WORKS, "cost_ref_kind": "boq_section", "cost_ref_id": items[0]["id"]}
        )
        assert (ok.status_code, ok.json()["cost_ref_id"]) == (200, str(section.id))
        # A section of another project, and a priced line of this one, are not on the list and not accepted.
        for bad in (foreign_section.id, line.id):
            r = await c.put(_pkg(world), json={"cost_ref_kind": "boq_section", "cost_ref_id": str(bad)})
            assert (r.status_code, r.json()["detail"]["code"]) == (404, "cost_reference_not_found")
        lots = await c.post(
            f"{BASE}/frameworks",
            json={
                "code": "FW-L",
                "max_value": "1",
                "currency": "EUR",
                "start_date": "2026-01-01",
                "end_date": "2027-01-01",
                "lots": [{"code": "L1", "title": "Rebar", "surprise": 1}],
            },
        )
        assert lots.status_code == 422


async def test_a_framework_supplier_link_can_be_changed_and_cleared(world: World) -> None:
    from app.modules.subcontractors.models import Subcontractor

    async with world.factory() as s:
        company = Subcontractor(legal_name="Rebar supplier", tax_id="FW-LINK-1")
        s.add(company)
        await s.commit()
    body = {
        "code": "FW-LINK",
        "max_value": "500000",
        "currency": "EUR",
        "start_date": "2026-01-01",
        "end_date": "2028-12-31",
    }
    async with client_as(world, world.manager, "manager") as c:
        fw = f"{BASE}/frameworks/{(await c.post(f'{BASE}/frameworks', json=body)).json()['id']}"
        unknown = await c.patch(fw, json={"subcontractor_id": str(uuid.uuid4()), "vendor_id": None})
        unknown_vendor = await c.patch(fw, json={"subcontractor_id": None, "vendor_id": str(uuid.uuid4())})
        linked = await c.patch(
            fw, json={"subcontractor_id": str(company.id), "vendor_id": None, "supplier_name": "Rebar supplier"}
        )
        kept = await c.patch(fw, json={"title": "Rebar 2026"})
        cleared = await c.patch(fw, json={"subcontractor_id": None})
    for refused in (unknown, unknown_vendor):
        assert (refused.status_code, refused.json()["detail"]["code"]) == (404, "company_not_found")
    assert (linked.status_code, linked.json()["subcontractor_id"], linked.json()["vendor_id"]) == (
        200,
        str(company.id),
        None,
    )
    # A patch that does not name the link keeps it; an explicit null clears it.
    assert kept.json()["subcontractor_id"] == str(company.id)
    assert (cleared.status_code, cleared.json()["subcontractor_id"]) == (200, None)
