# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The staffing service against PostgreSQL: derived status, binding, reminders, retention, rule 4 under load.

Each test builds its own throwaway database (``isolated_engine``), so commits,
row locks and the governance frame document behave as they do in production.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.staffing.errors import StaffingError
from app.modules.staffing.permissions import register_staffing_permissions
from app.modules.staffing.service import StaffingService
from tests._pg import isolated_engine
from tests.pg.staffing_fixtures import (
    START,
    admin,
    build_world,
    call,
    credential,
    days,
    fill,
    members,
    personnel_file,
    position,
    submittable_plan,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def factory():
    register_staffing_permissions()
    async with isolated_engine() as engine:
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _plan(w):
    from app.modules.staffing.models import StaffingPlan

    async with w.factory() as s:
        return (await s.execute(select(StaffingPlan).where(StaffingPlan.project_id == w.project_id))).scalar_one()


async def test_a_confirmed_fill_makes_the_position_filled_and_ending_it_reopens_it(factory) -> None:
    w = await build_world(factory, governance=False)
    pid = await position(w, "site_manager")
    fid = await fill(w, pid, (await members(w))[0].id)

    views = {v["id"]: v for v in await call(w, "position_views")}
    assert views[str(pid)]["status"] == "open"

    await call(w, "confirm_fill", fid, w.manager)
    views = {v["id"]: v for v in await call(w, "position_views")}
    assert views[str(pid)]["status"] == "filled"

    await call(w, "end_fill", fid, START + timedelta(days=10), w.manager)
    views = {v["id"]: v for v in await call(w, "position_views")}
    assert views[str(pid)]["status"] == "open"


async def test_filled_cannot_be_set_by_hand(factory) -> None:
    w = await build_world(factory, governance=False)
    pid = await position(w, "site_manager")
    with pytest.raises(StaffingError) as err:
        await call(w, "set_position_status", pid, "filled", w.manager)
    assert err.value.code == "status_is_derived"


async def test_submission_refuses_an_incomplete_plan_and_lists_what_is_missing(factory) -> None:
    w = await build_world(factory)
    await position(w, "site_manager")
    with pytest.raises(StaffingError) as err:
        await call(w, "submit", w.manager)
    codes = {v["code"] for v in err.value.violations or []}
    assert "key_role_missing" in codes
    assert (await _plan(w)).status == "draft"


async def test_a_binding_frame_document_approves_the_submitted_plan_and_freezes_a_snapshot(factory) -> None:
    from app.modules.project_governance.models import GovernanceDocument
    from app.modules.staffing.events import handle_frame_document

    w = await build_world(factory)
    await submittable_plan(w)
    await call(w, "submit", w.manager)
    plan = await _plan(w)
    assert plan.status == "in_review"
    assert plan.governance_document_id is not None

    async with w.factory() as s:
        doc = await s.get(GovernanceDocument, plan.governance_document_id)
        doc.status = "binding"
        await s.commit()
    payload = {"project_id": str(w.project_id), "document_id": str(plan.governance_document_id), "status": "binding"}
    assert await handle_frame_document(payload, session_factory=w.factory) is True
    plan = await _plan(w)
    assert plan.status == "binding"
    assert len(plan.bound_snapshot["positions"]) == 9
    # Idempotent: the second delivery of the same event changes nothing.
    assert await handle_frame_document(payload, session_factory=w.factory) is False

    # An edit after binding opens a revision; the bound snapshot stays in force.
    await position(w, "scheduler")
    plan = await _plan(w)
    assert plan.status == "revising"
    assert len(plan.bound_snapshot["positions"]) == 9


async def test_an_expiry_alert_notifies_only_rule_10_recipients_and_writes_nothing_to_the_file(factory) -> None:
    from app.modules.staffing.events import handle_expiry_alert
    from app.modules.staffing.models import PersonnelDocument
    from app.modules.teams.models import RosterMember

    w = await build_world(factory)
    person = (await members(w))[0]
    async with w.factory() as s:
        (await s.get(RosterMember, person.id)).user_id = w.editor
        await s.commit()
    pid = await position(w, "site_manager", owner_user_id=w.owner)
    await call(w, "confirm_fill", await fill(w, pid, person.id), w.manager)
    file_id = await personnel_file(w, person.id, nationality_required=True)
    cred = await credential(w, "work_permit", days(20))
    await call(w, "link_document", file_id, {"document_kind": "work_permit", "credential_id": cred}, admin(w))

    async with w.factory() as s:
        recipients = await StaffingService(s).reminder_recipients(cred)
    assert len(recipients) == 1
    _doc, users = recipients[0]
    assert w.owner in users and w.editor in users
    assert w.outsider not in users and w.decider not in users

    async with w.factory() as s:
        before = (
            await s.execute(select(PersonnelDocument).where(PersonnelDocument.credential_id == cred))
        ).scalar_one()
        snapshot = (before.updated_at, before.verified_at, before.number_last4)
    sent = await handle_expiry_alert(
        {"credential_id": str(cred), "valid_until": days(20).isoformat(), "status": "expiring_soon"},
        session_factory=w.factory,
    )
    assert sent == len(users)
    async with w.factory() as s:
        after = (await s.execute(select(PersonnelDocument).where(PersonnelDocument.credential_id == cred))).scalar_one()
        assert (after.updated_at, after.verified_at, after.number_last4) == snapshot


async def test_the_credential_sweep_fires_the_alert_for_a_credential_nobody_edited(factory) -> None:
    from app.modules.credentials.models import Credential
    from app.modules.staffing.sweep import credential_expiry_sweep

    w = await build_world(factory, governance=False)
    cred = await credential(w, "work_permit", days(10))
    async with w.factory() as s:
        (await s.get(Credential, cred)).status = "active"
        await s.commit()
    assert await credential_expiry_sweep(session_factory=w.factory) >= 1
    async with w.factory() as s:
        assert (await s.get(Credential, cred)).status == "expiring_soon"
    # Idempotent: nothing drifted, nothing updated.
    assert await credential_expiry_sweep(session_factory=w.factory) == 0


async def test_retention_sweep_anonymises_a_due_file_but_never_a_held_one(factory) -> None:
    from app.modules.credentials.models import Credential
    from app.modules.staffing.models import PersonnelFile, PositionFill, TravelRecord
    from app.modules.staffing.sweep import staffing_retention_sweep

    w = await build_world(factory, governance=False)
    people = await members(w)
    pid = await position(w, "site_supervisor_civil", headcount=2)
    fills = [await fill(w, pid, people[i].id, "0.5") for i in (0, 1)]
    files = [await personnel_file(w, people[i].id) for i in (0, 1)]
    cred = await credential(w, "employment_contract", None)
    await call(w, "link_document", files[0], {"document_kind": "employment_contract", "credential_id": cred}, admin(w))
    await call(
        w,
        "create_travel",
        files[0],
        {"kind": "mobilisation", "depart_date": date(2026, 11, 1), "cost": "120.00", "currency": "EUR"},
        admin(w),
    )
    for f in files:
        await call(w, "end_file", f, date(2020, 1, 1), admin(w))
    await call(w, "hold_file", files[1], "Pending dispute over overtime.", admin(w))
    async with w.factory() as s:
        for f in files:
            (await s.get(PersonnelFile, f)).retention_due_at = date(2021, 1, 1)
        await s.commit()

    assert await staffing_retention_sweep(session_factory=w.factory) == 1
    async with w.factory() as s:
        gone, held = await s.get(PersonnelFile, files[0]), await s.get(PersonnelFile, files[1])
        assert gone.status == "anonymised" and gone.roster_member_id is None
        assert gone.activity_counts == {"2026-11": {"travel": 1, "leave": 0}}
        assert held.status == "retention_hold" and held.roster_member_id == people[1].id
        assert await s.get(Credential, cred) is None
        assert (await s.execute(select(TravelRecord).where(TravelRecord.personnel_file_id == files[0]))).first() is None
        assert (await s.get(PositionFill, fills[0])).roster_member_id is None
        assert (await s.get(PositionFill, fills[1])).roster_member_id == people[1].id
    assert await staffing_retention_sweep(session_factory=w.factory) == 0


async def test_erasure_is_refused_while_a_statutory_retention_duty_runs(factory) -> None:
    w = await build_world(factory, catalogue_id="us", governance=False)
    person = (await members(w))[0]
    pid = await position(w, "site_manager")
    await call(w, "confirm_fill", await fill(w, pid, person.id), w.manager)
    file_id = await personnel_file(w, person.id)
    cred = await credential(w, "right_to_work_check", None)
    await call(w, "link_document", file_id, {"document_kind": "right_to_work_check", "credential_id": cred}, admin(w))

    with pytest.raises(StaffingError) as err:
        await call(w, "erase_file", file_id, "Request of the person.", admin(w))
    assert err.value.code == "retention_obligation_active"
    assert err.value.status_code == 409
    assert err.value.detail


async def test_erasure_is_refused_under_a_hold_and_needs_admin(factory) -> None:
    from app.modules.staffing.service import Actor

    w = await build_world(factory, governance=False)
    person = (await members(w))[0]
    file_id = await personnel_file(w, person.id)
    with pytest.raises(StaffingError) as err:
        await call(w, "erase_file", file_id, "Request.", Actor(w.manager, {"role": "manager", "permissions": []}))
    assert err.value.status_code == 403
    await call(w, "hold_file", file_id, "Litigation.", admin(w))
    with pytest.raises(StaffingError) as err:
        await call(w, "erase_file", file_id, "Request.", admin(w))
    assert err.value.code == "retention_hold_active"


async def test_rule_4_holds_when_two_confirms_race_for_the_same_person(factory) -> None:
    w = await build_world(factory, governance=False)
    person = (await members(w))[0]
    a = await fill(w, await position(w, "site_manager"), person.id, "0.6")
    b = await fill(w, await position(w, "hse_manager"), person.id, "0.6")

    async def confirm(fill_id):
        try:
            await call(w, "confirm_fill", fill_id, w.manager)
            return "ok"
        except StaffingError as exc:
            return exc.code

    outcomes = sorted(await asyncio.gather(confirm(a), confirm(b)))
    assert outcomes == ["ok", "person_overallocated"]
