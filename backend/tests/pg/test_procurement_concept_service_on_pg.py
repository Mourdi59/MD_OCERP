# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Procurement concept service on PostgreSQL: approval, binding, execution, read-back, frameworks, shortlist, schedule.

Each test is a SPEC rule with the case that would pass if the rule were missing.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.procurement_concept import plan_source as plan
from app.modules.procurement_concept.errors import ProcurementError
from app.modules.procurement_concept.events import handle_read_back
from app.modules.procurement_concept.models import AwardPackage
from app.modules.procurement_concept.service import ProcurementConceptService
from tests._pg import isolated_engine
from tests.pg.procurement_concept_fixtures import (
    World,
    add_contract_package,
    add_procurement_area,
    build_world,
    put,
    set_delivery_form,
    svc_call,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def _state(w: World, code: str) -> str:
    async with w.factory() as s:
        return (await s.get(AwardPackage, w.packages[code])).state


async def _three_lots(w: World, procedure: str) -> None:
    for code in ("W1", "W2", "W3"):
        await add_contract_package(w, code, "construction")
        await put(w, code, {"estimated_value": "2000000", "currency": "EUR", "procedure_code": procedure})


async def test_public_client_three_lots_above_eu_threshold_force_open_procedure(world: World) -> None:
    """E2E path (SPEC 8.7): 3 x 2m works lots aggregate to 6m; a direct award blocks approval, open passes."""
    await _three_lots(world, "direct_award")
    await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.manager, role="manager")
    with pytest.raises(ProcurementError) as exc:
        await svc_call(world, "transition", world.project_id, "approved", actor_id=world.manager, role="manager")
    assert exc.value.code == "concept_has_blocking_findings"
    assert {v["code"] for v in exc.value.violations} == {"lot_splitting_avoids_threshold"}
    await svc_call(world, "transition", world.project_id, "draft", actor_id=world.manager, role="manager")
    for code in ("W1", "W2", "W3"):
        await put(world, code, {"procedure_code": "open"})
    await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.manager, role="manager")
    concept = await svc_call(world, "transition", world.project_id, "approved", actor_id=world.manager, role="manager")
    assert concept.state == "approved"


async def test_every_contract_package_needs_an_award_package_before_review(world: World) -> None:
    await add_contract_package(world, "W1", "construction")
    await add_contract_package(world, "PA", "project_agreement")
    with pytest.raises(ProcurementError) as exc:
        await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.manager, role="manager")
    assert [v["ref"] for v in exc.value.violations] == ["W1"]
    await put(world, "W1", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
    concept = await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.manager, role="manager")
    assert concept.state == "in_review"
    with pytest.raises(ProcurementError) as kind:
        await put(world, "PA", {"procedure_code": "open"})
    assert kind.value.code in ("package_kind_not_procured", "concept_locked")


async def test_editor_without_procurement_ownership_cannot_steer_or_approve(world: World) -> None:
    await add_contract_package(world, "W1", "construction")
    with pytest.raises(ProcurementError) as exc:
        await put(world, "W1", {"procedure_code": "open"}, actor=world.editor, role="editor")
    assert exc.value.status_code == 403
    await add_procurement_area(world, world.area_owner)
    row = await put(
        world,
        "W1",
        {"estimated_value": "1", "currency": "EUR", "procedure_code": "open"},
        actor=world.area_owner,
        role="editor",
    )
    assert row.state == "procedure_set"
    await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.area_owner, role="editor")
    with pytest.raises(ProcurementError) as denied:
        await svc_call(world, "transition", world.project_id, "approved", actor_id=world.editor, role="editor")
    assert denied.value.status_code == 403
    ok = await svc_call(world, "transition", world.project_id, "approved", actor_id=world.area_owner, role="editor")
    assert ok.state == "approved"


async def test_binding_concept_is_changed_only_through_a_change_request(world: World) -> None:
    from app.modules.project_governance.models import GovernanceChangeRequest, GovernanceDocument

    await add_contract_package(world, "W1", "construction")
    await put(world, "W1", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
    area_id = await add_procurement_area(world, world.area_owner)
    async with world.factory() as s:
        doc = GovernanceDocument(
            project_id=world.project_id, area_id=area_id, doc_type="m08_procurement_frame", status="binding"
        )
        s.add(doc)
        await s.commit()
        doc_id = doc.id
    async with world.factory() as s:
        svc = ProcurementConceptService(s)
        assert await svc.effective_state(await svc.get_concept(world.project_id)) == "binding"
    with pytest.raises(ProcurementError) as exc:
        await put(world, "W1", {"procedure_code": "restricted"})
    assert (exc.value.code, exc.value.status_code) == ("binding_requires_change_request", 409)
    async with world.factory() as s:
        s.add(
            GovernanceChangeRequest(project_id=world.project_id, document_id=doc_id, proposed_revision_id=uuid.uuid4())
        )
        await s.commit()
    row = await put(world, "W1", {"procedure_code": "restricted"})
    assert row.procedure_code == "restricted"


async def test_without_governance_the_concept_tops_out_at_approved(world: World) -> None:
    await add_contract_package(world, "W1", "construction")
    await put(world, "W1", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
    await svc_call(world, "transition", world.project_id, "in_review", actor_id=world.manager, role="manager")
    await svc_call(world, "transition", world.project_id, "approved", actor_id=world.manager, role="manager")
    async with world.factory() as s:
        svc = ProcurementConceptService(s)
        assert await svc.effective_state(await svc.get_concept(world.project_id)) == "approved"


async def test_advance_package_without_reason_is_rejected(world: World) -> None:
    await add_contract_package(world, "S1", "supply")
    with pytest.raises(ProcurementError) as exc:
        await put(world, "S1", {"is_advance": True})
    assert exc.value.code == "advance_without_reason"


async def test_execution_creates_exactly_one_bid_package_and_reads_back_idempotently(world: World) -> None:
    from app.modules.bid_management.models import BidPackage

    await add_contract_package(world, "W1", "construction")
    await put(world, "W1", {"estimated_value": "900000", "currency": "EUR", "procedure_code": "open"})
    out = await svc_call(
        world,
        "create_execution",
        world.project_id,
        world.packages["W1"],
        vehicle=None,
        submission_deadline=None,
        actor_id=world.manager,
        role="manager",
    )
    assert out["kind"] == "bid_package"
    with pytest.raises(ProcurementError) as again:
        await svc_call(
            world,
            "create_execution",
            world.project_id,
            world.packages["W1"],
            vehicle=None,
            submission_deadline=None,
            actor_id=world.manager,
            role="manager",
        )
    assert again.value.code == "execution_exists"
    async with world.factory() as s:
        n = (
            await s.execute(
                sa.select(sa.func.count()).select_from(BidPackage).where(BidPackage.project_id == world.project_id)
            )
        ).scalar_one()
    assert n == 1
    bp = uuid.UUID(out["id"])
    assert (
        await handle_read_back(
            "bid_management.package.published", {"package_id": str(bp)}, session_factory=world.factory
        )
        == "in_tender"
    )
    assert (
        await handle_read_back(
            "bid_management.package.published", {"package_id": str(bp)}, session_factory=world.factory
        )
        == "in_tender"
    )
    assert (
        await handle_read_back("bid_management.package.awarded", {"package_id": str(bp)}, session_factory=world.factory)
        == "awarded"
    )
    # A late publish never moves an awarded package back.
    await handle_read_back("bid_management.package.published", {"package_id": str(bp)}, session_factory=world.factory)
    assert await _state(world, "W1") == "awarded"


async def test_supply_package_creates_an_rfq_never_a_bid_package(world: World) -> None:
    from app.modules.bid_management.models import BidPackage
    from app.modules.rfq_bidding.models import RFQ

    await add_contract_package(world, "S1", "supply")
    await put(world, "S1", {"estimated_value": "50000", "currency": "EUR", "procedure_code": "request_for_quotation"})
    out = await svc_call(
        world,
        "create_execution",
        world.project_id,
        world.packages["S1"],
        vehicle=None,
        submission_deadline=None,
        actor_id=world.manager,
        role="manager",
    )
    assert out["kind"] == "rfq"
    async with world.factory() as s:
        rfqs = (
            await s.execute(sa.select(sa.func.count()).select_from(RFQ).where(RFQ.project_id == world.project_id))
        ).scalar_one()
        bps = (
            await s.execute(
                sa.select(sa.func.count()).select_from(BidPackage).where(BidPackage.project_id == world.project_id)
            )
        ).scalar_one()
        link = (
            await s.execute(
                sa.select(plan.PACKAGE_TABLE.c.link_kind).where(plan.PACKAGE_TABLE.c.id == world.packages["S1"])
            )
        ).scalar_one()
    assert (rfqs, bps, link) == (1, 0, "rfq")
    assert await handle_read_back("rfq.awarded", {"rfq_id": out["id"]}, session_factory=world.factory) == "awarded"


async def test_concurrent_execution_creation_ends_with_one_link(world: World) -> None:
    from app.modules.bid_management.models import BidPackage

    await add_contract_package(world, "W1", "construction")
    await put(world, "W1", {"estimated_value": "900000", "currency": "EUR", "procedure_code": "open"})

    async def create() -> str:
        try:
            await svc_call(
                world,
                "create_execution",
                world.project_id,
                world.packages["W1"],
                vehicle=None,
                submission_deadline=None,
                actor_id=world.manager,
                role="manager",
            )
            return "ok"
        except ProcurementError as exc:
            return exc.code

    results = sorted(await asyncio.gather(create(), create()))
    assert results == ["execution_exists", "ok"]
    async with world.factory() as s:
        n = (
            await s.execute(
                sa.select(sa.func.count()).select_from(BidPackage).where(BidPackage.project_id == world.project_id)
            )
        ).scalar_one()
    assert n == 1


async def test_framework_call_off_ledger_and_exhaustion(world: World) -> None:
    tenant = str(world.manager)
    async with world.factory() as s:
        svc = ProcurementConceptService(s)
        fw = await svc.create_framework(
            tenant,
            {
                "code": "FW-1",
                "title": "Rebar",
                "package_kinds": ["supply"],
                "lots": [],
                "max_value": "500000",
                "currency": "EUR",
                "start_date": date(2026, 1, 1),
                "end_date": date(2028, 12, 31),
            },
            actor_id=world.manager,
        )
        await svc.transition_framework(tenant, fw.id, "active", actor_id=world.manager)
        await s.commit()
    await add_contract_package(world, "S1", "supply")
    await add_contract_package(world, "S2", "supply")
    await put(
        world,
        "S1",
        {
            "estimated_value": "300000",
            "currency": "EUR",
            "procedure_code": "framework_call_off",
            "framework_agreement_id": fw.id,
        },
    )
    with pytest.raises(ProcurementError) as exc:
        await put(
            world,
            "S2",
            {
                "estimated_value": "300000",
                "currency": "EUR",
                "procedure_code": "framework_call_off",
                "framework_agreement_id": fw.id,
            },
        )
    assert exc.value.code == "framework_exhausted"
    ledger = await svc_call(world, "ledger", tenant, fw.id)
    assert (ledger["call_off_value"], ledger["remaining_value"]) == ("300000.00", "200000.00")
    # Another company cannot see or call off this framework.
    with pytest.raises(ProcurementError) as other:
        await svc_call(world, "ledger", str(uuid.uuid4()), fw.id)
    assert other.value.status_code == 404


async def test_shortlist_needs_min_bidders_and_rationale_for_exclusions(world: World) -> None:
    from app.modules.subcontractors.models import Subcontractor

    await add_contract_package(world, "W1", "construction")
    await put(world, "W1", {"estimated_value": "900000", "currency": "EUR", "procedure_code": "competitive_negotiated"})
    async with world.factory() as s:
        subs = [Subcontractor(legal_name=f"Trade contractor {i}") for i in range(4)]
        s.add_all(subs)
        await s.commit()
    pkg = world.packages["W1"]
    for sub in subs[:2]:
        await svc_call(
            world,
            "add_candidate",
            world.project_id,
            pkg,
            {"subcontractor_id": sub.id, "list": "short"},
            actor_id=world.manager,
        )
    with pytest.raises(ProcurementError) as exc:
        await svc_call(world, "confirm_shortlist", world.project_id, pkg, actor_id=world.manager, role="manager")
    assert "shortlist_below_min_bidders" in {v["code"] for v in exc.value.violations}
    with pytest.raises(ProcurementError) as no_reason:
        await svc_call(
            world,
            "add_candidate",
            world.project_id,
            pkg,
            {"subcontractor_id": subs[3].id, "list": "excluded"},
            actor_id=world.manager,
        )
    assert no_reason.value.code == "excluded_candidate_without_rationale"
    await svc_call(
        world,
        "add_candidate",
        world.project_id,
        pkg,
        {"subcontractor_id": subs[2].id, "list": "short"},
        actor_id=world.manager,
    )
    row = await svc_call(world, "confirm_shortlist", world.project_id, pkg, actor_id=world.manager, role="manager")
    assert row.state == "shortlisted"


async def test_schedule_proposal_is_written_only_on_confirm_and_idempotently(world: World) -> None:
    from app.modules.schedule.models import Activity, Schedule

    await add_contract_package(world, "W1", "construction")
    await put(
        world,
        "W1",
        {"estimated_value": "900000", "currency": "EUR", "procedure_code": "open", "need_date": date(2027, 6, 30)},
    )
    view = await svc_call(world, "schedule_view", world.project_id, today=date(2026, 10, 11))
    assert view["items"][0]["proposed_award_date"] == "2027-06-30"
    assert view["items"][0]["proposed_start_date"] == "2027-03-07"
    with pytest.raises(ProcurementError) as no_schedule:
        await svc_call(
            world, "confirm_schedule", world.project_id, [world.packages["W1"]], actor_id=world.manager, role="manager"
        )
    assert no_schedule.value.code == "no_schedule"
    async with world.factory() as s:
        s.add(Schedule(project_id=world.project_id, name="Master"))
        await s.commit()
    first = await svc_call(
        world, "confirm_schedule", world.project_id, [world.packages["W1"]], actor_id=world.manager, role="manager"
    )
    second = await svc_call(
        world, "confirm_schedule", world.project_id, [world.packages["W1"]], actor_id=world.manager, role="manager"
    )
    assert first == second
    async with world.factory() as s:
        acts = (await s.execute(sa.select(Activity))).scalars().all()
    assert len(acts) == 2
    assert {a.metadata_["award_package_id"] for a in acts} == {str(world.packages["W1"])}


async def test_cm_at_risk_main_package_needs_two_stage_procedure(world: World) -> None:
    await set_delivery_form(world, "cm_at_risk")
    await add_contract_package(world, "GMP", "construction")
    await put(world, "GMP", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
    report = await svc_call(world, "consistency_report", world.project_id)
    assert [f["code"] for f in report] == ["procedure_inconsistent_with_delivery_form"]
    await put(world, "GMP", {"procedure_code": "restricted"})
    assert await svc_call(world, "consistency_report", world.project_id) == []


async def test_bid_package_tender_id_must_name_a_tender_package_of_the_same_project(world: World) -> None:
    """The dead ``oe_tendering_tender`` reference: tender_id is a TenderPackage id, checked per project."""
    from app.modules.bid_management.schemas import BidPackageCreate
    from app.modules.bid_management.service import BidManagementService
    from app.modules.tendering.models import TenderPackage

    other = await build_world(world.factory, concept=False)
    async with world.factory() as s:
        own = TenderPackage(project_id=world.project_id, name="Own tender")
        foreign = TenderPackage(project_id=other.project_id, name="Foreign tender")
        s.add_all([own, foreign])
        await s.commit()
    for tender_id, ok in ((foreign.id, False), (uuid.uuid4(), False), (own.id, True)):
        async with world.factory() as s:
            svc = BidManagementService(s)
            data = BidPackageCreate(
                project_id=world.project_id, tender_id=tender_id, code=f"BP-{uuid.uuid4().hex[:6]}", currency="EUR"
            )
            if ok:
                assert (await svc.create_package(data)).tender_id == own.id
            else:
                with pytest.raises(HTTPException) as exc:
                    await svc.create_package(data)
                assert exc.value.status_code == 404
