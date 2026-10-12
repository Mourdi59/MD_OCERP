# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits spec rules on real PostgreSQL: binding roadmap, frame documents, corrections, validity, sweep, seed."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.permits import jobs
from app.modules.permits.errors import PermitError
from app.modules.permits.models import Permit, PermitCondition
from app.modules.permits.service import PermitService
from tests._pg import isolated_engine
from tests.pg.governance_fixtures import add_container, add_revision, add_user
from tests.pg.permits_fixtures import (
    TODAY,
    World,
    add_project,
    application,
    build_world,
    cond,
    decide,
    file,
    move,
    requirement,
)

pytestmark = pytest.mark.asyncio

BUILDING = "baugenehmigung"
NOW = datetime.now(UTC).date()


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def _code(coro) -> tuple[int, str]:
    with pytest.raises(PermitError) as exc:
        await coro
    return exc.value.status_code, exc.value.code


async def _frame_model(w: World) -> dict[str, object]:
    """Pin a governance model that carries the permit frame documents; return them by type."""
    from app.modules.project_governance.models import GovernanceDocument
    from app.modules.project_governance.service import GovernanceService

    async with w.factory() as s:
        await GovernanceService(s).set_model(
            w.project_id,
            source="shipped",
            catalogue_id="elf_module_framework",
            version=None,
            four_eyes=True,
            actor_id=w.manager,
            tenant_id=str(w.manager),
        )
        await s.commit()
        rows = (
            await s.execute(select(GovernanceDocument).where(GovernanceDocument.project_id == w.project_id))
        ).scalars()
        return {d.doc_type: d for d in rows}


# ── finding 17: one approved change request licenses one structural change ──


async def test_an_approved_change_request_is_spent_by_the_change_it_licenses(world: World) -> None:
    from app.modules.project_governance.models import GovernanceChangeRequest, GovernanceDocument

    docs = await _frame_model(world)
    doc_id = docs["dev_permit_roadmap"].id
    async with world.factory() as s:
        doc = await s.get(GovernanceDocument, doc_id)
        doc.status = "binding"
        cr = GovernanceChangeRequest(
            project_id=world.project_id,
            document_id=doc_id,
            proposed_revision_id=uuid.uuid4(),
            reason="Add the road occupation",
            status="approved",
            requested_by=world.manager,
        )
        s.add(cr)
        await s.commit()
        cr_id = cr.id
    body = {"permit_type_code": BUILDING, "responsible_user_id": world.manager}
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(svc.create_requirement(world.project_id, dict(body), actor_id=world.manager)) == (
            409,
            "roadmap_binding_change_request_required",
        )
    async with world.factory() as s:
        row = await PermitService(s).create_requirement(
            world.project_id, {**body, "change_request_id": cr_id}, actor_id=world.manager
        )
        await s.commit()
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(
            svc.create_requirement(world.project_id, {**body, "change_request_id": cr_id}, actor_id=world.manager)
        ) == (409, "change_request_already_used")
        assert await _code(
            svc.delete_requirement(world.project_id, row.id, actor_id=world.manager, change_request_id=cr_id)
        ) == (409, "change_request_already_used")
        roadmap = await svc.repo.get_roadmap(world.project_id)
        assert roadmap.consumed_change_request_ids == [str(cr_id)]


# ── finding 10, rule 18: the register export becomes a CDE revision of the frame document ──


async def test_the_register_export_is_stored_as_a_revision_of_its_frame_document(world: World) -> None:
    from app.modules.cde.models import DocumentRevision
    from app.modules.project_governance.models import GovernanceDocument

    await requirement(world, BUILDING)
    docs = await _frame_model(world)
    p = world.project_id
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(svc.publish_frame_document(p, "business_case", actor_id=world.manager)) == (
            422,
            "frame_document_type_invalid",
        )
        assert await _code(svc.publish_frame_document(p, "dev_permit_roadmap", actor_id=world.manager)) == (
            409,
            "frame_document_without_container",
        )
    async with world.factory() as s:
        container = await add_container(s, p, "permit_roadmap")
        doc = await s.get(GovernanceDocument, docs["dev_permit_roadmap"].id)
        doc.container_id = container
        await s.commit()
    async with world.factory() as s:
        out = await PermitService(s).publish_frame_document(p, "dev_permit_roadmap", actor_id=world.manager)
        await s.commit()
    async with world.factory() as s:
        revision = await s.get(DocumentRevision, uuid.UUID(out["revision_id"]))
    assert revision.container_id == container and revision.content_hash == out["content_hash"]
    assert out["register"] == "roadmap" and len(out["content_hash"]) == 64


# ── finding 10: decision correction, interruption, jurisdiction ───────────


async def test_a_correction_is_a_new_revision_and_the_permit_follows_it(world: World) -> None:
    rid = await requirement(world, BUILDING)
    out = await decide(world, await file(world, rid), "granted", reference="AZ-OLD")
    p = world.project_id
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(
            svc.correct_decision(p, out["decision"].id, {"reference": "AZ-1"}, actor_id=world.manager)
        ) == (
            422,
            "correction_needs_reason",
        )
        new = await svc.correct_decision(
            p, out["decision"].id, {"reference": "AZ-NEW", "reason": "Typing error"}, actor_id=world.manager
        )
        await s.commit()
    assert new.revision == 2 and new.supersedes_id == out["decision"].id and new.outcome == "granted"
    async with world.factory() as s:
        svc = PermitService(s)
        permit = await svc.repo.get_permit(p, out["permit"].id)
        assert permit.decision_id == new.id
        assert await _code(
            svc.correct_decision(p, out["decision"].id, {"reference": "x", "reason": "again"}, actor_id=world.manager)
        ) == (409, "decision_superseded")
        assert await svc.requirement_state(p, rid) == "granted"


async def test_interrupted_work_puts_the_permit_back_on_a_lapse_clock(world: World) -> None:
    rid = await requirement(world, BUILDING)
    out = await decide(world, await file(world, rid), "granted", served_date=NOW - timedelta(days=9))
    p, pid = world.project_id, out["permit"].id
    async with world.factory() as s:
        svc = PermitService(s)
        assert await _code(svc.notify_interruption(p, pid, NOW, resumed=False, actor_id=world.manager)) == (
            409,
            "work_not_started",
        )
        await svc.notify_start(p, pid, NOW - timedelta(days=5), actor_id=world.manager)
        assert await _code(svc.notify_start(p, pid, NOW, actor_id=world.manager)) == (409, "start_already_notified")
        assert await _code(svc.notify_start(p, pid, NOW + timedelta(days=3), actor_id=world.manager)) == (
            422,
            "date_in_future",
        )
        permit = await svc.notify_interruption(p, pid, NOW - timedelta(days=2), resumed=False, actor_id=world.manager)
        validity = await svc._validity(permit)
        assert permit.paused_since == NOW - timedelta(days=2)
        assert (permit.valid_until is not None) == (getattr(validity, "lapse_if_paused", None) is not None)
        assert await _code(svc.notify_interruption(p, pid, NOW, resumed=False, actor_id=world.manager)) == (
            409,
            "work_already_interrupted",
        )
        permit = await svc.notify_interruption(p, pid, NOW, resumed=True, actor_id=world.manager)
        assert permit.paused_since is None and permit.valid_until is None


async def test_the_default_catalogue_follows_the_projects_subdivision(world: World) -> None:
    from app.modules.projects.models import Project

    async with world.factory() as s:
        pid = await add_project(s, world.manager, [])
        (await s.get(Project, pid)).subdivision_code = "DE-BY"
        await s.commit()
    async with world.factory() as s:
        roadmap = await PermitService(s).set_roadmap(pid, tenant_id=None, actor_id=world.manager)
        await s.commit()
    assert roadmap.catalogue_id == "de_by" and roadmap.jurisdiction == "DE-BY"


# ── finding 14: a granted requirement shows the decision date and no conflict ──


async def test_a_granted_requirement_raises_no_schedule_conflict(world: World) -> None:
    rid = await requirement(world, BUILDING, needed_by_date=TODAY + timedelta(days=5))
    aid = await file(world, rid, TODAY - timedelta(days=20))
    async with world.factory() as s:
        before = {r["requirement_id"]: r for r in (await PermitService(s).timeline(world.project_id, TODAY))["items"]}
    assert before[str(rid)]["schedule_conflict"] is True
    await decide(world, aid, "granted", decision_date=TODAY - timedelta(days=2))
    async with world.factory() as s:
        after = {r["requirement_id"]: r for r in (await PermitService(s).timeline(world.project_id, TODAY))["items"]}
    row = after[str(rid)]
    assert row["schedule_conflict"] is False and row["forecast_decision"] == (TODAY - timedelta(days=2)).isoformat()


# ── findings 18 and 21: the deemed discharge runs on the discharge type's own clock ──


async def test_a_deemed_discharge_is_proposed_and_recorded_with_its_notice() -> None:
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            manager = await add_user(s, "manager")
            pid = await add_project(s, manager, [], country="GB")
            await PermitService(s).set_roadmap(pid, tenant_id=None, actor_id=manager, jurisdiction="GB-ENG")
            container = await add_container(s, pid, "notice")
            notice = await add_revision(s, container, 2, "b" * 64)
            await s.commit()
        w = World(factory, pid, manager, manager, manager, manager, manager, uuid.uuid4())
        main = await requirement(w, "full_planning_permission")
        out = await decide(
            w,
            await file(w, main),
            "granted_with_conditions",
            conditions=[cond("1", "suspensive", requires_authority_approval=True)],
        )
        async with factory() as s:
            (c,) = await PermitService(s).repo.conditions_of_permit(pid, out["permit"].id)
        discharge_req = await requirement(w, "discharge_of_conditions")
        body = {
            "kind": "discharge_of_conditions",
            "parent_permit_id": out["permit"].id,
            "discharges_condition_ids": [c.id],
        }
        # Filed under a requirement of the discharge type, the application runs on that type's own clock.
        aid = await application(w, discharge_req, **body)
        await move(w, aid, "preparing")
        await move(w, aid, "submitted", TODAY - timedelta(days=120))
        async with factory() as s:
            status = await PermitService(s).deemed_status(pid, aid, TODAY)
        assert status["proposal"] == "deemed_discharged" and status["requires_notice"] is True
        with pytest.raises(PermitError) as exc:
            await decide(w, aid, "deemed_granted")
        assert exc.value.code == "deemed_needs_notice"
        res = await decide(w, aid, "deemed_granted", document_revision_id=notice)
        assert res["decision"].deemed is True and res["permit"] is None
        async with factory() as s:
            svc = PermitService(s)
            assert (await svc.repo.get_condition(pid, c.id)).status == "discharged"
            (row,) = await svc.repo.list_discharges(pid, c.id)
            assert row.mode == "deemed_discharged"


# ── finding 10, rule 17 and finding 22: the scheduled sweep ───────────────


async def test_the_sweep_handles_each_row_in_its_own_transaction(world: World, monkeypatch, caplog) -> None:
    rid = await requirement(world, BUILDING)
    out = await decide(
        world,
        await file(world, rid),
        "granted_with_conditions",
        served_date=TODAY - timedelta(days=9),
        conditions=[
            cond("1", owner_user_id=world.owner_user, due_date=NOW - timedelta(days=60)),
            cond("2", owner_user_id=world.owner_user, due_date=NOW - timedelta(days=60)),
        ],
    )
    p = world.project_id
    async with world.factory() as s:
        permit = await s.get(Permit, out["permit"].id)
        permit.valid_until = NOW - timedelta(days=1)
        ids = {c.number: c.id for c in await PermitService(s).repo.conditions_of_permit(p, permit.id)}
        await s.commit()
    real = PermitService.sweep_condition

    async def flaky(self, project_id, cid, today):
        if cid == ids["1"]:
            raise RuntimeError("boom")
        return await real(self, project_id, cid, today)

    monkeypatch.setattr(PermitService, "sweep_condition", flaky)
    with caplog.at_level(logging.WARNING, logger="app.modules.permits.jobs"):
        counts = await jobs.run_sweep_once(world.factory, NOW)
    assert counts["failed"] == 1 and counts["lapsed"] == 1 and counts["projects"] == 1
    assert any("permits sweep failed" in r.message for r in caplog.records)
    async with world.factory() as s:
        assert (await s.get(Permit, out["permit"].id)).status == "lapsed"
        one, two = await s.get(PermitCondition, ids["1"]), await s.get(PermitCondition, ids["2"])
        assert one.overdue_notified_at is None and two.overdue_notified_at is not None
        # No area hosts permits in this project, so nobody could be told: it stays due for escalation.
        assert two.escalated_at is None
    assert counts["notified"] + counts["unescalated"] >= 1


# ── finding 22: the demo seed fills every list and reads forwards in time ──


async def test_the_demo_seed_fills_every_list_in_a_plausible_order(world: World) -> None:
    from app.modules.permits.seed import seed_permits_demo
    from app.modules.projects.models import Project

    async with world.factory() as s:
        pid = await add_project(s, world.manager, [])
        (await s.get(Project, pid)).metadata_ = {"demo_id": "permits-review"}
        await s.commit()
    async with world.factory() as s:
        totals = await seed_permits_demo(s, [pid])
        await s.commit()
    assert totals["projects"] == 1
    async with world.factory() as s:
        repo = PermitService(s).repo
        apps = await repo.list_applications(pid)
        decisions = {d.application_id: d for d in await repo.list_decisions(pid)}
        reqs = {r.id: r for r in await repo.list_requirements(pid)}
        permits = await repo.list_permits(pid)
        for name, rows in (
            ("requirements", reqs),
            ("dependencies", await repo.list_dependencies(pid)),
            ("applications", apps),
            ("clock events", await repo.list_clock_events(pid)),
            ("decisions", decisions),
            ("permits", permits),
            ("conditions", await repo.list_conditions(pid)),
            ("evidence", await repo.list_evidence(pid)),
            ("discharges", await repo.list_discharges(pid)),
        ):
            assert len(rows) > 0, name
    for a in apps:
        d = decisions.get(a.id)
        if d is not None and a.submitted_at is not None:
            assert a.submitted_at <= d.decision_date, a.authority_reference
    by_scope = {p.scope: decisions_of for p in permits for decisions_of in [p]}
    if "early_start" in by_scope and "full" in by_scope:
        early = next(d for d in decisions.values() if d.id == by_scope["early_start"].decision_id)
        full = max(
            (d for d in decisions.values() if d.id in {p.decision_id for p in permits if p.scope == "full"}),
            key=lambda d: d.decision_date,
        )
        assert early.decision_date < full.decision_date


# ── finding 10, rules 2, 20, 21, 22: the ports other modules call ─────────


async def test_the_ports_answer_for_site_readiness_closeout_and_release(world: World) -> None:
    from app.modules.permits import public

    async def allocation(_session, _project_id, category: str) -> str | None:
        return "contractor" if category == "permit_conditions_change" else None

    rid = await requirement(world, BUILDING)
    out = await decide(
        world,
        await file(world, rid),
        "granted_with_conditions",
        conditions=[cond("1", "suspensive", trigger="before_occupation", requires_authority_approval=True)],
    )
    p = world.project_id
    async with world.factory() as s:
        (c,) = await PermitService(s).repo.conditions_of_permit(p, out["permit"].id)
    public.register_applicant_resolver("test_allocation", allocation)
    try:
        aid = await application(
            world,
            rid,
            kind="discharge_of_conditions",
            parent_permit_id=out["permit"].id,
            discharges_condition_ids=[c.id],
        )
    finally:
        public.unregister_applicant_resolver("test_allocation")
    await move(world, aid, "preparing")
    await move(world, aid, "submitted", TODAY - timedelta(days=20))
    await decide(world, aid, "granted")
    async with world.factory() as s:
        app = await PermitService(s).repo.get_application(p, aid)
        assert (app.applicant_role, app.applicant_source) == ("contractor", "allocation")
        assert await public.requirement_state(s, p, rid) == "granted"
        assert await public.requirement_state(s, p, uuid.uuid4()) is None
        start = await public.start_readiness(s, p)
        assert start["gate"] == "start" and start["status"] == "ready"
        (entry,) = await public.closeout_entries(s, p)
        (condition,) = entry["conditions"]
        assert condition["state"] == "discharged" and len(condition["discharges"]) == 1
