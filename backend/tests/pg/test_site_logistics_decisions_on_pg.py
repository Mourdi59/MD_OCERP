# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Three decisions about deliveries and permits, against PostgreSQL.

1. A site without a time zone keeps booking and approving deliveries. The
   opening hours are not compared on any clock; the delivery, the plan findings
   and the validation say so as a warning. With a zone the hours are enforced.
2. Two approvals of one slot queue instead of both reading the approved set
   before either commits. A read never waits behind that queue.
3. A heavy transport is ready for the gate with a granted permit only.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.site_logistics import models as m
from app.modules.site_logistics.permissions import register_site_logistics_permissions
from app.modules.site_logistics.plan_service import LogisticsPlanService, PlanPerms
from app.modules.site_logistics.schemas import DeliveryCreate, DeliveryUpdate
from app.modules.site_logistics.service import SiteLogisticsService
from tests._pg import isolated_engine
from tests.pg.site_logistics_fixtures import BASE, SITE, World, build_world, client_as, window

pytestmark = pytest.mark.asyncio

OK = {"allowed": True, "applies": True, "reason": None}
UNCHECKED = [{"code": "gate_hours_unchecked", "severity": "warning", "field": "site_timezone"}]


@pytest_asyncio.fixture
async def world():
    register_site_logistics_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


@pytest_asyncio.fixture
async def bare():
    """A project as an upgrade finds it: no logistics concept, so no site time zone."""
    register_site_logistics_permissions()
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory, start_plan=False)


def _utc(day, hour: int) -> str:
    return datetime.combine(day, time(hour, 0), tzinfo=UTC).isoformat()


async def test_a_site_without_a_zone_books_with_a_warning_and_with_a_zone_is_checked(bare: World) -> None:
    pid = str(bare.project_id)
    day = (datetime.now(UTC) + timedelta(days=5)).date()

    def booking(start_hour: int, **extra) -> dict[str, Any]:
        return {
            "project_id": pid,
            "gate_id": gate["id"],
            "supplier_name": "Supplier",
            "window_start": _utc(day, start_hour),
            "window_end": _utc(day, start_hour + 1),
            **extra,
        }

    async with client_as(bare, bare.manager, "manager") as c:
        made = await c.post(
            f"{BASE}/gates/", json={"project_id": pid, "name": "North", "open_time": "07:00", "close_time": "18:00"}
        )
        assert made.status_code == 201, made.text
        gate = made.json()

        # Inside and outside 07:00 to 18:00 on the UTC clock: neither is compared, both are booked.
        inside = await c.post(f"{BASE}/deliveries/", json=booking(9))
        outside = await c.post(f"{BASE}/deliveries/", json=booking(20))
        assert (inside.status_code, outside.status_code) == (201, 201), (inside.text, outside.text)
        assert inside.json()["warnings"] == UNCHECKED
        assert outside.json()["warnings"] == UNCHECKED
        assert outside.json()["can"]["approve"] == OK

        approved = await c.post(f"{BASE}/deliveries/{outside.json()['id']}/approve/")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["warnings"] == UNCHECKED
        # Booked as approved in one step, and moved by an edit: the same answer on every path.
        direct = await c.post(f"{BASE}/deliveries/", json=booking(22, status="approved"))
        assert direct.status_code == 201, direct.text
        moved = await c.patch(
            f"{BASE}/deliveries/{inside.json()['id']}",
            json={"window_start": _utc(day, 5), "window_end": _utc(day, 6)},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["warnings"] == UNCHECKED
        page = await c.get(f"{BASE}/deliveries/", params={"project_id": pid})
        assert [d["warnings"] for d in page.json()] == [UNCHECKED] * 3

    async with bare.factory() as s:
        svc = LogisticsPlanService(s)
        findings = await svc.findings(bare.project_id)
        unchecked = [f for f in findings if f["code"] == "gate_hours_unchecked"]
        assert [(f["rule"], f["severity"]) for f in unchecked] == [("gate_hours_checked", "warning")]
        assert "site_timezone_missing" not in [f["code"] for f in findings]
        report = await svc.validate(bare.project_id)
        failed = {r["rule_id"] for r in report["results"] if not r["passed"]}
        assert "site_logistics.gate_hours_checked" in failed
        assert "site_logistics.site_timezone_set" not in failed
        # Reading and booking did not start a plan behind the user's back.
        assert await svc.concept(bare.project_id) is None

        await svc.put_concept(bare.project_id, {"site_timezone": "Europe/Berlin"}, bare.manager)
        await s.commit()

    async with client_as(bare, bare.manager, "manager") as c:
        # 19:00 UTC is 20:00 or 21:00 in Berlin: after the gate closed, and now that is refused.
        late = await c.post(f"{BASE}/deliveries/", json=booking(19))
        assert late.status_code == 400, late.text
        assert "closes" in str(late.json()["detail"])
        # 10:00 UTC is 11:00 or 12:00 in Berlin: inside, booked, nothing left unchecked.
        fine = await c.post(f"{BASE}/deliveries/", json=booking(10))
        assert fine.status_code == 201, fine.text
        assert fine.json()["warnings"] == []
        seen = await c.get(f"{BASE}/deliveries/{inside.json()['id']}")
        assert seen.json()["warnings"] == []

    async with bare.factory() as s:
        codes = [f["code"] for f in await LogisticsPlanService(s).findings(bare.project_id)]
        assert "gate_hours_unchecked" not in codes


def _request(pid: uuid.UUID, gate_id: uuid.UUID, start: datetime, end: datetime, **kw) -> DeliveryCreate:
    return DeliveryCreate(
        project_id=pid, gate_id=gate_id, supplier_name="Supplier", window_start=start, window_end=end, **kw
    )


async def _impatient(session: AsyncSession) -> None:
    """Give up on a lock after a moment instead of waiting for the other transaction."""
    await session.execute(sa.text("SET LOCAL lock_timeout = '400ms'"))


async def test_two_approvals_of_one_slot_queue_and_a_read_does_not(world: World) -> None:
    pid = world.project_id
    start, end = window(3, 9, 1)
    async with world.factory() as s:
        gate = m.Gate(project_id=pid, name="North", open_time="07:00", close_time="18:00")
        s.add(gate)
        await s.flush()
        legacy = SiteLogisticsService(s)
        first = await legacy.create_delivery(_request(pid, gate.id, start, end), str(world.manager))
        rival = await legacy.create_delivery(_request(pid, gate.id, start, end), str(world.manager))
        await s.commit()

    async with world.factory() as holder:
        # Another approval is between its check and its write: it holds the queue.
        await SiteLogisticsService(holder)._lock_approvals(pid, gate.id)

        async with world.factory() as s:
            await _impatient(s)
            with pytest.raises(sa.exc.DBAPIError, match="lock"):
                await SiteLogisticsService(s).approve_delivery(rival.id, user_id=str(world.manager))
        async with world.factory() as s:
            await _impatient(s)
            with pytest.raises(sa.exc.DBAPIError, match="lock"):
                await SiteLogisticsService(s).create_delivery(
                    _request(pid, gate.id, start, end, status="approved"), str(world.manager)
                )
        async with world.factory() as s:
            await _impatient(s)
            with pytest.raises(sa.exc.DBAPIError, match="lock"):
                await SiteLogisticsService(s).update_delivery(rival.id, DeliveryUpdate(status="approved"))
        async with world.factory() as s:
            # A request, an edit that approves nothing and the flags of a record do not queue.
            await _impatient(s)
            legacy = SiteLogisticsService(s)
            requested = await legacy.create_delivery(_request(pid, gate.id, start, end), str(world.manager))
            assert requested.status == "requested"
        async with world.factory() as s:
            await _impatient(s)
            legacy = SiteLogisticsService(s)
            can = await legacy.can_delivery(await legacy.get_delivery(rival.id), PlanPerms(True, True, True))
            assert can["approve"] == OK
        await holder.rollback()

    async with world.factory() as s:
        legacy = SiteLogisticsService(s)
        assert (await legacy.approve_delivery(first.id, user_id=str(world.manager))).status == "approved"
    async with world.factory() as s:
        with pytest.raises(HTTPException) as exc:
            await SiteLogisticsService(s).approve_delivery(rival.id, user_id=str(world.manager))
        assert exc.value.code == "slot_taken"
    async with world.factory() as s:
        approved = (
            await s.execute(
                sa.select(sa.func.count()).select_from(m.DeliveryBooking).where(m.DeliveryBooking.status == "approved")
            )
        ).scalar_one()
        assert approved == 1


async def test_an_applied_permit_does_not_make_a_heavy_transport_ready(world: World) -> None:
    pid = world.project_id
    day = (datetime.now(SITE) + timedelta(days=10)).date()

    async def item(svc: LogisticsPlanService) -> tuple[str, str]:
        readiness = await svc.readiness(pid)
        found = next(i for i in readiness["items"] if i["code"] == "heavy_transports_applied")
        return found["state"], found["detail"]

    async with world.factory() as s:
        svc = LogisticsPlanService(s)
        transport = await svc.create_transport(
            pid,
            {
                "direction": "inbound",
                "transport_kind": "heavy_oversize",
                "title": "Transformer",
                "gross_weight_t": Decimal("62"),
            },
            world.manager,
        )
        assert await item(svc) == ("not_met", "permit_missing: Transformer")
        permit = await svc.create_permit(
            pid,
            {
                "permit_kind": "oversize_permit",
                "reference": "OS-9",
                "covers_transport_ids": [transport.id],
                "valid_from": day,
                "valid_to": day,
            },
            world.manager,
        )
        # A draft is not an application.
        assert await item(svc) == ("not_met", "permit_missing: Transformer")
        await svc.transition_permit(pid, permit.id, "applied", world.manager)
        # The defect: this used to read as met.
        assert await item(svc) == ("not_met", "permit_applied: Transformer")
        await svc.transition_permit(pid, permit.id, "granted", world.manager)
        assert await item(svc) == ("met", "")
