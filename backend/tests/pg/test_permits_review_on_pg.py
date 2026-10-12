# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits review pins on real PostgreSQL: gate evidence, four-eyes, gate-read fields, variation, links."""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.permits import evidence as permits_evidence
from app.modules.permits import hosting as hst
from app.modules.permits.errors import PermitError
from app.modules.permits.models import ConditionDischarge, PermitRoadmap
from app.modules.permits.service import PermitService
from app.modules.project_governance.evidence import GateAttempt
from tests._pg import isolated_engine
from tests.pg.governance_fixtures import add_route
from tests.pg.permits_fixtures import (
    TODAY,
    World,
    add_project,
    application,
    build_world,
    cond,
    decide,
    depend,
    file,
    move,
    requirement,
    state,
)

pytestmark = pytest.mark.asyncio

BUILDING = "baugenehmigung"
EARLY = "vorzeitiger_baubeginn"


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def _code(coro) -> tuple[int, str]:
    with pytest.raises(PermitError) as exc:
        await coro
    return exc.value.status_code, exc.value.code


async def _granted(w: World, *conditions: dict) -> tuple[uuid.UUID, object, dict]:
    rid = await requirement(w, BUILDING)
    aid = await file(w, rid)
    out = await decide(w, aid, "granted_with_conditions", conditions=list(conditions))
    async with w.factory() as s:
        rows = await PermitService(s).repo.conditions_of_permit(w.project_id, out["permit"].id)
    return rid, out["permit"], {c.number: c for c in rows}


async def _conds(w: World, permit_id) -> dict:
    async with w.factory() as s:
        return {c.number: c for c in await PermitService(s).repo.conditions_of_permit(w.project_id, permit_id)}


async def _certify(w: World, cid: uuid.UUID, by: uuid.UUID, can_manage: bool) -> None:
    async with w.factory() as s:
        svc = PermitService(s)
        await svc.add_evidence(
            w.project_id, cid, {"kind": "photo", "note": "Photo"}, actor_id=by, can_manage=can_manage
        )
        await svc.submit_evidence(w.project_id, cid, actor_id=by, can_manage=can_manage)
        await s.commit()


# ── findings 1 and 2: the blocking provider never answers with silence, at risk is not met ──


async def _governed(w: World) -> tuple[object, list]:
    """Pin the neutral governance model; return its gate into construction and its areas."""
    from app.modules.project_governance.models import GovernanceGate
    from app.modules.project_governance.service import GovernanceService

    async with w.factory() as s:
        svc = GovernanceService(s)
        await svc.set_model(
            w.project_id,
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            actor_id=w.manager,
            tenant_id=str(w.manager),
        )
        await s.commit()
        gates = (await s.execute(select(GovernanceGate).where(GovernanceGate.project_id == w.project_id))).scalars()
        gate = next(g for g in gates if g.to_phase == "construction")
        return gate, list(await svc.repo.list_areas(w.project_id))


async def test_a_model_that_does_not_say_where_permits_live_gets_unknown_not_silence(world: World) -> None:
    await _granted(world, cond("1", "suspensive"))
    gate, areas = await _governed(world)
    attempt = GateAttempt(gate.id, gate.code, 1)
    async with world.factory() as s:
        for provider in (permits_evidence.start_and_handover, permits_evidence.roadmap_and_register):
            items = await provider(s, world.project_id, attempt, areas[0])
            assert [i.state for i in items] == ["unknown"], provider.__name__
            assert items[0].detail == "no_area_hosts_permits"


async def test_tagged_model_blocks_the_gate_on_an_open_suspensive_condition(world: World, monkeypatch) -> None:
    rid, permit, conds = await _granted(world, cond("1", "suspensive", owner_user_id=world.owner_user))
    gate, areas = await _governed(world)
    host, other = areas[0], areas[1]
    tagged = {
        "areas": [{"code": host.code, "hosts": ["permits"]}],
        "phases": [{"code": gate.to_phase, "enables": ["construction_start"]}],
    }

    async def catalogue(_session, _project_id):
        return tagged

    monkeypatch.setattr(hst, "governance_catalogue", catalogue)
    attempt = GateAttempt(gate.id, gate.code, 1)
    async with world.factory() as s:
        (item,) = await permits_evidence.start_and_handover(s, world.project_id, attempt, host)
        assert item.state == "not_met" and "suspensive_condition_open" in item.detail
        assert await permits_evidence.start_and_handover(s, world.project_id, attempt, other) == []
    # An early start in force is "start at risk": still not met, and the detail says so (rule 10).
    async with world.factory() as s:
        await PermitService(s).transition_permit(
            world.project_id, permit.id, "revoked", actor_id=world.manager, reason="Revoked on appeal"
        )
        await s.commit()
    async with world.factory() as s:
        (item,) = await permits_evidence.start_and_handover(s, world.project_id, attempt, host)
    assert item.state == "not_met" and "permit_missing" in item.detail
    assert await state(world, rid) == "not_in_force"


# ── finding 3: four-eyes ──────────────────────────────────────────────────


async def test_whoever_added_or_submitted_the_evidence_cannot_verify(world: World) -> None:
    _rid, _permit, conds = await _granted(world, cond("1", owner_user_id=world.owner_user))
    cid = conds["1"].id
    # A manager acts in the owner's place: adds and submits the evidence.
    await _certify(world, cid, world.manager, True)
    async with world.factory() as s:
        svc = PermitService(s)
        p = world.project_id
        assert await _code(svc.discharge(p, cid, {"mode": "self_certified"}, actor_id=world.manager)) == (
            403,
            "verifier_is_involved",
        )
        assert await _code(svc.discharge(p, cid, {"mode": "self_certified"}, actor_id=world.owner_user)) == (
            403,
            "verifier_is_owner",
        )
        # Moving the ownership away after the evidence is in does not free the old owner to verify.
        assert await _code(
            svc.update_condition(p, cid, {"owner_user_id": world.editor}, actor_id=world.manager, can_manage=True)
        ) == (409, "condition_field_frozen")
        can = await svc.discharge_capability(p, cid, actor_id=world.manager, can_verify=True)
        assert can["self_certified"] == {"allowed": False, "reason": "verifier_is_involved"}
        can = await svc.discharge_capability(p, cid, actor_id=world.verifier, can_verify=True)
        assert can["self_certified"] == {"allowed": True, "reason": None}
        assert (await svc.discharge_capability(p, cid, actor_id=world.verifier, can_verify=False))["self_certified"][
            "reason"
        ] == "verify_required"
    async with world.factory() as s:
        row = await PermitService(s).discharge(
            world.project_id, cid, {"mode": "self_certified"}, actor_id=world.verifier
        )
        await s.commit()
    assert row.decided_by == world.manager and row.verifier_user_id == world.verifier


async def test_not_triggered_on_a_suspensive_condition_needs_a_document(world: World) -> None:
    _rid, _permit, conds = await _granted(world, cond("1", "suspensive", owner_user_id=world.owner_user))
    async with world.factory() as s:
        svc = PermitService(s)
        got = await _code(
            svc.discharge(world.project_id, conds["1"].id, {"mode": "not_triggered"}, actor_id=world.verifier)
        )
    assert got == (422, "not_triggered_needs_document")


# ── finding 4: what a gate reads needs manage and is frozen outside the first state ──


async def test_gate_read_fields_need_manage_and_freeze(world: World) -> None:
    rid = await requirement(world, BUILDING, responsible_user_id=world.owner_user)
    p = world.project_id
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(svc.update_requirement(p, rid, {"title": "x"}, actor_id=world.editor, can_manage=False)) == (
            403,
            "not_requirement_owner",
        )
        for change in (
            {"applicable": False, "applicability_rationale": "Not needed"},
            {"conflict_accepted": True},
            {"responsible_user_id": world.editor},
        ):
            assert await _code(
                svc.update_requirement(p, rid, dict(change), actor_id=world.owner_user, can_manage=False)
            ) == (403, "manage_required"), change
        row = await svc.update_requirement(p, rid, {"title": "Mine"}, actor_id=world.owner_user, can_manage=False)
        assert row.title == "Mine"
        await s.commit()
    aid = await file(world, rid)
    async with world.factory() as s:
        assert await _code(
            PermitService(s).update_requirement(
                p, rid, {"applicable": False, "applicability_rationale": "x"}, actor_id=world.manager, can_manage=True
            )
        ) == (409, "requirement_field_frozen")
    out = await decide(
        world, aid, "granted_with_conditions", conditions=[cond("1", "suspensive", owner_user_id=world.owner_user)]
    )
    cid = (await _conds(world, out["permit"].id))["1"].id
    async with world.factory() as s:
        svc = PermitService(s)
        for change in ({"kind": "information"}, {"trigger": "ongoing"}, {"requires_authority_approval": True}):
            assert await _code(
                svc.update_condition(p, cid, dict(change), actor_id=world.owner_user, can_manage=False)
            ) == (403, "manage_required"), change
    await _certify(world, cid, world.owner_user, False)
    async with world.factory() as s:
        assert await _code(
            PermitService(s).update_condition(p, cid, {"kind": "information"}, actor_id=world.manager, can_manage=True)
        ) == (409, "condition_field_frozen")


# ── finding 6: "conditions to follow" postpones the early-start test, it does not waive it ──


async def test_early_start_register_cannot_be_completed_without_restoration(world: World) -> None:
    main = await requirement(world, BUILDING)
    await file(world, main)
    rid = await requirement(world, EARLY)
    aid = await file(world, rid, TODAY - timedelta(days=30))
    out = await decide(world, aid, "granted", conditions_pending=True)
    async with world.factory() as s:
        svc = PermitService(s)
        got = await _code(svc.complete_register(world.project_id, out["decision"].id, actor_id=world.manager))
        assert got == (422, "early_start_needs_restoration_and_security")
    async with world.factory() as s:
        svc = PermitService(s)
        for number, purpose in (("1", "restoration"), ("2", "security")):
            await svc.create_condition(
                world.project_id,
                out["permit"].id,
                cond(number, trigger="ongoing", purpose=purpose),
                actor_id=world.manager,
            )
        dec = await svc.complete_register(world.project_id, out["decision"].id, actor_id=world.manager)
        assert dec.conditions_pending is False
        assert await _code(svc.complete_register(world.project_id, dec.id, actor_id=world.manager)) == (
            409,
            "register_already_complete",
        )


# ── finding 7: variation ──────────────────────────────────────────────────


async def test_variation_carries_state_evidence_discharge_and_pending_applications(world: World) -> None:
    rid, parent, conds = await _granted(
        world,
        cond("1", owner_user_id=world.owner_user),
        cond("2", "suspensive", requires_authority_approval=True),
        cond("3", trigger="ongoing", owner_user_id=world.owner_user),
    )
    p = world.project_id
    await _certify(world, conds["1"].id, world.owner_user, False)
    async with world.factory() as s:
        svc = PermitService(s)
        await svc.discharge(p, conds["1"].id, {"mode": "self_certified"}, actor_id=world.verifier)
        await svc.add_evidence(
            p, conds["3"].id, {"kind": "report", "note": "Log kept"}, actor_id=world.owner_user, can_manage=False
        )
        proposal = {**cond("9", trigger="ongoing"), "confidence": "0.6"}
        await svc.propose_conditions(p, parent.id, [proposal], actor_id=world.manager)
        await s.commit()
    pending = await application(
        world, rid, kind="discharge_of_conditions", parent_permit_id=parent.id, discharges_condition_ids=[conds["2"].id]
    )
    await move(world, pending, "preparing")
    await move(world, pending, "submitted", TODAY - timedelta(days=20))
    var = await application(world, rid, kind="variation", parent_permit_id=parent.id)
    await move(world, var, "preparing")
    await move(world, var, "submitted", TODAY - timedelta(days=15))
    child = (await decide(world, var, "granted"))["permit"]
    new = await _conds(world, child.id)
    assert new["1"].status == "discharged" and new["2"].status == "discharge_applied" and new["3"].status == "open"
    assert new["9"].confirmed is False and new["9"].source == "ai_extracted"
    async with world.factory() as s:
        svc = PermitService(s)
        assert len(await svc.repo.list_evidence(p, new["1"].id)) == 1
        assert len(await svc.repo.list_evidence(p, new["3"].id)) == 1
        (carried,) = await svc.repo.list_discharges(p, new["1"].id)
        assert carried.carried_from_id is not None and carried.verifier_user_id == world.verifier
        app = await svc.repo.get_application(p, pending)
        assert [str(i) for i in app.discharges_condition_ids] == [str(new["2"].id)]
    # The authority's answer to the pending discharge application reaches the varied permit.
    await decide(world, pending, "granted")
    assert (await _conds(world, child.id))["2"].status == "discharged"
    # The superseded parent takes no further variation, nor does a revoked permit.
    async with world.factory() as s:
        assert await _code(
            PermitService(s).create_application(
                p, {"requirement_id": rid, "kind": "variation", "parent_permit_id": parent.id}, actor_id=world.manager
            )
        ) == (409, "parent_permit_not_live")


# ── finding 9: the approval route is checked before it is stored ──────────


async def test_an_approval_route_of_another_project_is_refused(world: World) -> None:
    async with world.factory() as s:
        other = await add_project(s, world.outsider, [])
        foreign = await add_route(s, other, "permit_application", world.outsider)
        wrong_kind = await add_route(s, world.project_id, "phase_gate", world.manager)
        own = await add_route(s, world.project_id, "permit_application", world.manager)
        await s.commit()

    async def put(route_id) -> PermitRoadmap:
        async with world.factory() as s:
            row = await PermitService(s).set_roadmap(
                world.project_id, tenant_id=None, actor_id=world.manager, settings={"approval_route_id": route_id}
            )
            await s.commit()
            return row

    assert await _code(put(foreign)) == (404, "approval_route_not_found")
    assert await _code(put(uuid.uuid4())) == (404, "approval_route_not_found")
    assert await _code(put(wrong_kind)) == (422, "approval_route_not_usable")
    assert (await put(own)).approval_route_id == own


# ── findings 12, 13, 15, 16 ───────────────────────────────────────────────


async def test_duplicate_dependency_and_unverifiable_or_foreign_links(world: World) -> None:
    from tests.pg.governance_fixtures import add_container, add_revision

    pre = await requirement(world, "bauvoranfrage")
    rid = await requirement(world, BUILDING)
    p = world.project_id
    async with world.factory() as s:
        other = await add_project(s, world.outsider, [])
        container = await add_container(s, other, "foreign")
        revision = await add_revision(s, container, 1, "a" * 64)
        await s.commit()
    async with world.factory() as s:
        svc = PermitService(s)
        edge = {"depends_on_id": pre, "on": "granted"}
        assert await _code(svc.set_dependencies(p, rid, [edge, dict(edge)], actor_id=world.manager)) == (
            422,
            "dependency_duplicate",
        )
        assert await _code(svc._check_link("cde_revision", revision, p)) == (404, "cde_revision_not_found")
        assert await _code(svc._check_link("activity", uuid.uuid4(), p)) == (404, "activity_not_found")
        assert await _code(svc._check_link("gate_condition", uuid.uuid4(), p)) == (404, "gate_condition_not_found")
        assert await _code(svc._check_link("delivery_model", uuid.uuid4(), p)) == (422, "link_unverifiable")
        await svc._check_link("cde_revision", None, p)


async def test_linked_evidence_needs_its_reference(world: World) -> None:
    _rid, _permit, conds = await _granted(world, cond("1", owner_user_id=world.owner_user))
    async with world.factory() as s:
        got = await _code(
            PermitService(s).add_evidence(
                world.project_id,
                conds["1"].id,
                {"kind": "inspection", "ref_id": "", "note": "Passed"},
                actor_id=world.owner_user,
                can_manage=False,
            )
        )
    assert got == (422, "evidence_ref_required")


async def test_a_catalogue_that_drops_a_used_type_cannot_be_pinned(world: World) -> None:
    await requirement(world, BUILDING)
    async with world.factory() as s:
        got = await _code(
            PermitService(s).set_roadmap(
                world.project_id,
                tenant_id=None,
                actor_id=world.manager,
                catalogue_source="shipped",
                catalogue_id="neutral",
            )
        )
    assert got == (409, "catalogue_drops_used_type")


async def test_discharge_applications_name_each_confirmed_condition_once(world: World) -> None:
    rid, permit, conds = await _granted(
        world, *(cond(n, "suspensive", requires_authority_approval=True) for n in ("1", "2"))
    )
    p = world.project_id
    ids = [conds["1"].id, conds["2"].id]
    first = await application(
        world, rid, kind="discharge_of_conditions", parent_permit_id=permit.id, discharges_condition_ids=ids
    )
    body = {
        "requirement_id": rid,
        "kind": "discharge_of_conditions",
        "parent_permit_id": permit.id,
        "discharges_condition_ids": [ids[0]],
    }
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(svc.create_application(p, dict(body), actor_id=world.manager)) == (
            409,
            "condition_in_open_discharge_application",
        )
        proposal = {**cond("9", "suspensive"), "confidence": "0.5"}
        (unconfirmed,) = await svc.propose_conditions(p, permit.id, [proposal], actor_id=world.manager)
        await s.commit()
        assert await _code(
            svc.create_application(p, {**body, "discharges_condition_ids": [unconfirmed.id]}, actor_id=world.manager)
        ) == (409, "condition_not_confirmed")
    await move(world, first, "preparing")
    await move(world, first, "submitted", TODAY - timedelta(days=20))
    # An explicit empty list means the authority discharged none of them.
    await decide(world, first, "granted", discharged_condition_ids=[])
    assert {c.status for n, c in (await _conds(world, permit.id)).items() if n in ("1", "2")} == {"open"}
    async with world.factory() as s:
        count = (await s.execute(select(func.count()).select_from(ConditionDischarge))).scalar_one()
    assert count == 0


async def test_two_first_roadmaps_at_once_leave_one_row_and_no_500(world: World) -> None:
    async with world.factory() as s:
        pid = await add_project(s, world.manager, [])
        await s.commit()

    async def put() -> None:
        async with world.factory() as s:
            await PermitService(s).set_roadmap(pid, tenant_id=None, actor_id=world.manager)
            await s.commit()

    results = await asyncio.gather(put(), put(), return_exceptions=True)
    errors = [r for r in results if isinstance(r, BaseException)]
    assert all(isinstance(e, PermitError) and e.code == "concurrent_roadmap" for e in errors), results
    async with world.factory() as s:
        rows = (
            await s.execute(select(func.count()).select_from(PermitRoadmap).where(PermitRoadmap.project_id == pid))
        ).scalar_one()
    assert rows == 1


async def test_a_dependency_on_a_revoked_permit_is_unmet_again(world: World) -> None:
    pre = await requirement(world, "bauvoranfrage")
    rid = await requirement(world, BUILDING)
    await depend(world, rid, pre)
    out = await decide(world, await file(world, pre), "granted")
    assert await state(world, rid) == "not_started"
    async with world.factory() as s:
        await PermitService(s).transition_permit(
            world.project_id, out["permit"].id, "revoked", actor_id=world.manager, reason="Withdrawn by the authority"
        )
        await s.commit()
    assert await state(world, pre) == "not_in_force"
    assert await state(world, rid) == "blocked"
