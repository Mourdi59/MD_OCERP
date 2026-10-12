# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The defects of the second review, each pinned on PostgreSQL.

The committed figure against a contract header that carries its changes, the
reconciliation with the cost model, recompute targets, anti-splitting, schedule
re-pinning, pinned routes, who may decide (assignees, deputies, four eyes),
abort and transfer, routes edited or reassigned behind the matrix, award
drafts, the overdue sweep, gate evidence and the demo seed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.commitment_release.errors import CommitmentError
from app.modules.commitment_release.events import handle_route_event
from app.modules.commitment_release.models import CommitmentItem, CommitmentLink, CommitmentMatrix, ReleaseDecision
from app.modules.commitment_release.service import CommitmentService
from tests._pg import isolated_engine
from tests.pg.commitment_fixtures import (
    TODAY,
    World,
    add_contract,
    add_cost_line,
    add_project,
    build_world,
    decide,
    item,
    link,
    released_item,
    request,
    state,
)

pytestmark = pytest.mark.asyncio
D = Decimal


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def _committed(w: World, item_id: uuid.UUID) -> Decimal:
    async with w.factory() as s:
        svc = CommitmentService(s)
        matrix = await svc.require_matrix(w.project_id)
        project = await svc._project(w.project_id)
        _figs, committed, _why = await svc.committed_for_items(
            matrix, project, await svc.schedule_for(matrix), on_date=TODAY
        )
    return committed.get(item_id) or D("0")


async def _variation(w: World, amount: str, status: str, contract_id: uuid.UUID | None = None) -> uuid.UUID:
    from app.modules.variations.models import VariationOrder

    async with w.factory() as s:
        vo = VariationOrder(
            project_id=w.project_id,
            code=f"VO-{uuid.uuid4().hex[:6]}",
            title="Revised facade",
            final_cost_impact=D(amount),
            currency="EUR",
            status=status,
            affected_contract_id=contract_id,
        )
        s.add(vo)
        await s.commit()
        return vo.id


async def _header_takes(w: World, contract_id: uuid.UUID, variation_id: uuid.UUID, new_value: str) -> None:
    """What the platform's contract subscriber does when a variation completes: bump the header, mark the source."""
    from app.modules.contracts.models import Contract

    async with w.factory() as s:
        contract = await s.get(Contract, contract_id)
        contract.total_value = D(new_value)
        contract.metadata_ = {**(contract.metadata_ or {}), "variation_ids": [str(variation_id)]}
        await s.commit()


async def _release_row(w: World, release_id: uuid.UUID) -> ReleaseDecision:
    async with w.factory() as s:
        return await s.get(ReleaseDecision, release_id)


async def _decide(w: World, item_id: uuid.UUID, actor: uuid.UUID, decision: str = "approved", comment: str = ""):
    async with w.factory() as s:
        row = await CommitmentService(s).decide_release(
            w.project_id,
            item_id,
            decision=decision,
            comment=comment,
            conditions="",
            valid_until=None,
            actor_id=actor,
            caller_role="manager",
            today=TODAY,
        )
        await s.commit()
        return row


# ── findings 1 and 2: the committed figure ─────────────────────────────────


async def test_a_change_is_counted_once_before_and_after_it_moves_the_contract_header(world: World) -> None:
    iid = await released_item(world, "45000")
    cid = await add_contract(world, "40000")
    await link(world, iid, "contract", cid)
    vo = await _variation(world, "5000", "completed", cid)
    await link(world, iid, "variation_order", vo)
    # Not yet in the header: the contract and the change, each once.
    assert await _committed(world, iid) == D("45000")
    await _header_takes(world, cid, vo, "45000")
    # In the header now: the header alone. The old netting gave 40000, a plain sum 50000.
    assert await _committed(world, iid) == D("45000")


async def test_a_variation_counts_only_when_completed(world: World) -> None:
    iid = await released_item(world, "10000")
    vo = await _variation(world, "5000", "issued")
    await link(world, iid, "variation_order", vo)
    assert await _committed(world, iid) == D("0")
    from app.modules.variations.models import VariationOrder

    async with world.factory() as s:
        (await s.get(VariationOrder, vo)).status = "completed"
        await s.commit()
    assert await _committed(world, iid) == D("5000")


async def test_the_matrix_and_the_cost_model_differ_by_changes_that_moved_the_header_without_a_line(
    world: World,
) -> None:
    """The matrix reads the contract header; the cost model reads contract lines by cost line. A
    change that moved the header and added no line is in the first and not in the second, and that
    is the whole difference."""
    from app.modules.costmodel.repository import CostSpineRepository

    line = await add_cost_line(world, "CL-1")
    iid = await released_item(world, "45000")
    cid = await add_contract(world, "40000", cost_line_id=line)
    await link(world, iid, "contract", cid)
    vo = await _variation(world, "5000", "completed", cid)
    await _header_takes(world, cid, vo, "45000")
    async with world.factory() as s:
        by_line = await CostSpineRepository(s).committed_by_cost_line(world.project_id)
    cost_model = sum(by_line.values(), D("0"))
    matrix = await _committed(world, iid)
    assert (matrix, cost_model) == (D("45000"), D("40000"))
    assert matrix - cost_model == D("5000")


# ── finding 6: recompute may reach every recomputed state ──────────────────


async def test_linking_a_completed_contract_closes_a_released_item_and_unlinking_reopens_it(world: World) -> None:
    iid = await released_item(world, "40000")
    cid = await add_contract(world, "40000", status="completed")
    await link(world, iid, "contract", cid)
    assert (await state(world, iid)).status == "closed"
    async with world.factory() as s:
        lk = (await s.execute(select(CommitmentLink).where(CommitmentLink.item_id == iid))).scalar_one()
        await CommitmentService(s).remove_link(world.project_id, iid, lk.id, actor_id=world.requester)
        await s.commit()
    assert (await state(world, iid)).status == "released"


# ── finding 7: anti-splitting ──────────────────────────────────────────────


async def test_a_pending_request_of_the_split_group_counts_and_the_group_is_frozen(world: World) -> None:
    a = await item(world, code="SP-A", amount="30000", split_group="lot-7")
    b = await item(world, code="SP-B", amount="30000", split_group="lot-7")
    first = await request(world, a, "30000")
    assert first.required_tier == "project_manager"
    second = await request(world, b, "30000")
    # 30000 pending on A plus 30000 here is over the project manager's 50000.
    assert second.required_tier == "sponsor"
    async with world.factory() as s:
        with pytest.raises(CommitmentError) as exc:
            await CommitmentService(s).update_item(
                world.project_id, b, {"split_group": "other"}, actor_id=world.requester
            )
    assert (exc.value.code, exc.value.status_code) == ("field_frozen", 409)


# ── finding 8: re-pinning the schedule ─────────────────────────────────────


async def test_a_schedule_in_another_currency_is_refused_once_releases_exist(world: World) -> None:
    await released_item(world, "10000")
    async with world.factory() as s:
        with pytest.raises(CommitmentError) as exc:
            await CommitmentService(s).set_matrix(
                world.project_id, actor_id=world.manager, tenant_id=str(world.manager), schedule_id="us_federal_owner"
            )
    assert exc.value.code == "schedule_currency_mismatch"


# ── finding 9: a pinned route is the manager's ─────────────────────────────


async def _route(w: World, approver: uuid.UUID, project: bool = True) -> uuid.UUID:
    from app.modules.approval_routes.schemas import RouteCreate, StepCreate
    from app.modules.approval_routes.service import ApprovalRouteService

    async with w.factory() as s:
        route = await ApprovalRouteService(s).create_route(
            RouteCreate(
                project_id=w.project_id if project else None,
                name=f"hand built {uuid.uuid4().hex[:6]}",
                target_kind="commitment_release",
                steps=[StepCreate(ordinal=1, approver_user_id=approver, mode="any")],
            ),
            created_by=w.manager,
        )
        await s.commit()
        return route.id


async def _pin(w: World, tier: str, route_id: uuid.UUID) -> None:
    async with w.factory() as s:
        await CommitmentService(s).pin_tier_route(w.project_id, tier, route_id, actor_id=w.manager)
        await s.commit()


async def _matrix(w: World) -> CommitmentMatrix:
    async with w.factory() as s:
        return (
            await s.execute(select(CommitmentMatrix).where(CommitmentMatrix.project_id == w.project_id))
        ).scalar_one()


async def test_a_pinned_route_survives_new_assignments_and_a_forced_regeneration(world: World) -> None:
    route_id = await _route(world, world.sponsor)
    await _pin(world, "project_manager", route_id)
    async with world.factory() as s:
        svc = CommitmentService(s)
        await svc.put_assignments(
            world.project_id,
            [{"project_role": "owner_pm", "user_id": world.board}],
            actor_id=world.manager,
            today=TODAY,
        )
        report = await svc.generate_routes(world.project_id, actor_id=world.manager, today=TODAY, force=True)
        await s.commit()
    assert report["project_manager"] == "pinned"
    assert (await _matrix(world)).tier_routes["project_manager"] == str(route_id)


async def test_a_route_of_no_project_cannot_be_pinned(world: World) -> None:
    route_id = await _route(world, world.sponsor, project=False)
    with pytest.raises(CommitmentError) as exc:
        await _pin(world, "project_manager", route_id)
    assert exc.value.code == "route_must_belong_to_project"


# ── finding 13 and four eyes: who decides ──────────────────────────────────


async def test_every_assignee_of_an_any_tier_and_a_deputy_can_decide(world: World) -> None:
    async with world.factory() as s:
        await CommitmentService(s).put_assignments(
            world.project_id,
            [
                {"project_role": "owner_pm", "user_id": world.pm, "deputy_user_id": world.sponsor},
                {"project_role": "owner_pm", "user_id": world.board},
                {"project_role": "owner_sponsor", "user_id": world.sponsor},
                {"project_role": "owner_board_member", "user_id": world.board},
            ],
            actor_id=world.manager,
            today=TODAY,
        )
        await s.commit()
    # The second assignee, who has no step of their own on the route.
    first = await item(world, code="ANY-1", amount="10000")
    await request(world, first, "10000")
    row = await _decide(world, first, world.board)
    assert (row.outcome, row.decided_by, row.on_behalf_of) == ("released", world.board, None)
    # The deputy of the first assignee decides in that assignee's name.
    second = await item(world, code="ANY-2", amount="10000")
    await request(world, second, "10000")
    row = await _decide(world, second, world.sponsor)
    assert (row.outcome, row.decided_by, row.on_behalf_of) == ("released", world.sponsor, world.pm)
    assert (await state(world, second)).status == "released"


async def test_an_outsider_and_whoever_confirmed_a_precondition_cannot_decide(world: World) -> None:
    iid = await item(world, amount="10000")
    async with world.factory() as s:
        svc = CommitmentService(s)
        pre = await svc.add_precondition(
            world.project_id, iid, kind="manual", ref_id=None, text="Brief signed", actor_id=world.requester
        )
        await svc.confirm_precondition(
            world.project_id, iid, pre.id, met=True, evidence_ref="minute 4", actor_id=world.pm, manage=True
        )
        await s.commit()
    with pytest.raises(CommitmentError) as exc:
        # The only holder of the tier confirmed the evidence, so nobody is left to decide.
        await request(world, iid, "10000")
    assert exc.value.code == "four_eyes_no_approver"

    other = await item(world, code="CR-2", amount="10000")
    await request(world, other, "10000")
    for actor, code in ((world.outsider, "not_entitled_decider"), (world.requester, "four_eyes_violation")):
        with pytest.raises(CommitmentError) as exc:
            await _decide(world, other, actor)
        assert (exc.value.code, exc.value.status_code) == (code, 403)
    with pytest.raises(CommitmentError) as exc:
        await _decide(world, other, world.pm, decision="rejected")
    assert exc.value.code == "rationale_required"
    assert (await state(world, other)).status == "release_requested"


async def test_the_owner_and_the_gate_fields_are_frozen_for_an_editor_and_after_planned(world: World) -> None:
    iid = await item(world, amount="10000")
    async with world.factory() as s:
        with pytest.raises(CommitmentError) as exc:
            await CommitmentService(s).update_item(
                world.project_id, iid, {"owner_user_id": world.pm}, actor_id=world.requester
            )
    assert exc.value.code == "manage_required"
    await decide(world, await request(world, iid, "10000"), world.pm)
    async with world.factory() as s:
        with pytest.raises(CommitmentError) as exc:
            await CommitmentService(s).update_item(
                world.project_id,
                iid,
                {"deferred": True, "deferred_reason": "later"},
                actor_id=world.manager,
                manage=True,
            )
    assert exc.value.code == "field_frozen"


# ── finding 12: a verdict that waited behind a withdrawal ──────────────────


async def test_a_verdict_does_not_undo_a_withdrawal_it_read_before(world: World) -> None:
    iid = await item(world, amount="10000")
    d = await request(world, iid, "10000")
    async with world.factory() as s:
        svc = CommitmentService(s)
        seen = await svc.repo.get_release(d.id)
        assert seen.outcome == "pending"
        async with world.factory() as other:
            await CommitmentService(other).withdraw_release(
                world.project_id, iid, actor_id=world.requester, reason="wrong item"
            )
            await other.commit()
        applied = await svc.apply_route_verdict(
            d.id, instance_id=d.approval_instance_id, verdict="approved", decided_by=str(world.pm)
        )
        await s.commit()
    assert applied is False
    assert (await _release_row(world, d.id)).outcome == "withdrawn"
    assert (await state(world, iid)).status == "planned"


# ── finding 14: abort and transfer ─────────────────────────────────────────


async def _terms(w: World, item_id: uuid.UUID, charge: str) -> None:
    async with w.factory() as s:
        await CommitmentService(s).put_abort_terms(
            w.project_id,
            item_id,
            {"basis_code": "custom", "other_charge_estimate": charge, "source_note": "test"},
            actor_id=w.manager,
            manage=True,
            tenant_id=str(w.manager),
        )
        await s.commit()


async def _abort(w: World, item_id: uuid.UUID):
    async with w.factory() as s:
        row = await CommitmentService(s).request_abort(
            w.project_id, item_id, reason="Scheme cancelled", actor_id=w.requester, today=TODAY
        )
        await s.commit()
        return row


async def test_an_abort_is_decided_on_the_tier_of_its_residual_loss_and_ends_the_item(world: World) -> None:
    iid = await released_item(world, "40000")
    cid = await add_contract(world, "40000")
    await link(world, iid, "contract", cid)
    with pytest.raises(CommitmentError) as exc:
        await _abort(world, iid)
    assert exc.value.code == "abort_exposure_unknown"
    await _terms(world, iid, "10000")
    row = await _abort(world, iid)
    assert (row.purpose, row.required_tier, row.requested_amount) == ("abort", "sponsor", D("10000"))
    assert (await state(world, iid)).status == "release_requested"
    row = await _decide(world, iid, world.sponsor)
    assert row.outcome == "aborted"
    assert (await state(world, iid)).status == "aborted"


async def test_a_transfer_moves_the_links_and_ends_the_item_for_a_manager_only(world: World) -> None:
    src = await released_item(world, "40000")
    cid = await add_contract(world, "40000")
    await link(world, src, "contract", cid)
    dst = await item(world, code="CR-T", amount="40000")

    async def transfer(manage: bool):
        async with world.factory() as s:
            await CommitmentService(s).transfer_item(
                world.project_id,
                src,
                target_project_id=world.project_id,
                target_item_id=dst,
                reason="Package merged",
                actor_id=world.manager,
                manage=manage,
            )
            await s.commit()

    with pytest.raises(CommitmentError) as exc:
        await transfer(False)
    assert exc.value.code == "manage_required"
    await transfer(True)
    source = await state(world, src)
    assert (source.status, source.transferred_to_item_id) == ("transferred", dst)
    async with world.factory() as s:
        owners = (
            (await s.execute(select(CommitmentLink.item_id).where(CommitmentLink.target_id == cid))).scalars().all()
        )
    assert owners == [dst]


# ── findings 25 to 27: approval routes behind the matrix ───────────────────


async def test_a_step_is_handed_off_only_by_its_approver_or_a_manager_and_never_to_the_requester(
    world: World,
) -> None:
    from app.modules.approval_routes.service import ApprovalRouteService

    iid = await item(world, amount="10000")
    d = await request(world, iid, "10000")
    async with world.factory() as s:
        svc = ApprovalRouteService(s)
        with pytest.raises(HTTPException) as exc:
            await svc.reassign_current_step(
                d.approval_instance_id, to_user_id=world.board, actor_id=world.requester, caller_role="editor"
            )
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await svc.reassign_current_step(
                d.approval_instance_id, to_user_id=world.requester, actor_id=world.manager, manage=True
            )
        assert exc.value.status_code == 422
        handed = await svc.reassign_current_step(
            d.approval_instance_id, to_user_id=world.board, actor_id=world.pm, caller_role="manager"
        )
        assert handed.current_assignee_user_id == world.board


async def test_an_approval_by_someone_who_does_not_hold_the_tier_releases_nothing(world: World) -> None:
    from app.modules.approval_routes.service import ApprovalRouteService

    iid = await item(world, amount="10000")
    d = await request(world, iid, "10000")
    async with world.factory() as s:
        # A manager of routes hands the project manager's step to the sponsor's colleague on the board.
        await ApprovalRouteService(s).reassign_current_step(
            d.approval_instance_id, to_user_id=world.board, actor_id=world.manager, manage=True
        )
        await s.commit()
    assert await decide(world, d, world.board) == "approved"
    row = await _release_row(world, d.id)
    assert (row.outcome, row.rationale) == ("rejected", "decider_not_tier_holder")
    assert (await state(world, iid)).status == "planned"


async def test_a_generated_route_edited_behind_the_matrix_is_refused_until_a_manager_pins_it(world: World) -> None:
    from app.modules.approval_routes.models import Step

    route_id = uuid.UUID((await _matrix(world)).tier_routes["project_manager"])
    async with world.factory() as s:
        step = (await s.execute(select(Step).where(Step.route_id == route_id))).scalar_one()
        step.approver_user_id = None
        step.approver_role = "editor"
        await s.commit()
    iid = await item(world, amount="10000")
    with pytest.raises(CommitmentError) as exc:
        await request(world, iid, "10000")
    assert (exc.value.code, exc.value.status_code) == ("route_changed_since_accepted", 409)
    await _pin(world, "project_manager", route_id)
    assert (await request(world, iid, "10000")).outcome == "pending"


async def test_a_cancel_in_approval_routes_names_who_cancelled(world: World, monkeypatch) -> None:
    import app.modules.approval_routes.service as routes_service

    published: list[tuple[str, dict]] = []
    monkeypatch.setattr(routes_service, "_safe_publish", lambda name, data: published.append((name, data)))
    iid = await item(world, amount="10000")
    d = await request(world, iid, "10000")
    async with world.factory() as s:
        await routes_service.ApprovalRouteService(s).cancel_instance(
            d.approval_instance_id, actor_id=world.manager, reason="superseded"
        )
        await s.commit()
    name, data = published[-1]
    assert name == "approval_routes.instance.cancelled"
    assert data["cancelled_by"] == str(world.manager)
    await handle_route_event(data, verdict="cancelled", session_factory=world.factory)
    row = await _release_row(world, d.id)
    assert (row.outcome, row.decided_by) == ("withdrawn", world.manager)


# ── finding 15: what an award drafted follows the award ────────────────────


async def test_a_contract_drafted_from_an_award_is_linked_to_the_item_of_the_award(world: World) -> None:
    from app.modules.bid_management.models import BidPackage

    iid = await released_item(world, "40000")
    async with world.factory() as s:
        pkg = BidPackage(
            project_id=world.project_id, code=f"BP-{uuid.uuid4().hex[:6]}", currency="EUR", status="awarded"
        )
        s.add(pkg)
        await s.commit()
        pkg_id = pkg.id
    await link(world, iid, "bid_package", pkg_id)
    cid = await add_contract(world, "30000", meta={"bid_package_id": str(pkg_id)})
    stranger = await add_contract(world, "30000", meta={"bid_package_id": str(uuid.uuid4())})
    async with world.factory() as s:
        assert await CommitmentService(s).adopt_award_drafts(world.project_id) == 1
        await s.commit()
    async with world.factory() as s:
        assert await CommitmentService(s).adopt_award_drafts(world.project_id) == 0
        linked = (
            (await s.execute(select(CommitmentLink.target_id).where(CommitmentLink.kind == "contract"))).scalars().all()
        )
    assert linked == [cid]
    assert stranger not in linked
    assert (await state(world, iid)).status == "committed"


# ── finding 17: the overdue escalation ─────────────────────────────────────


async def test_an_overdue_decision_is_escalated_once_per_date(world: World) -> None:
    from app.core.audit_log import ActivityLog
    from app.modules.commitment_release.sweep import sweep_once

    iid = await item(world, amount="10000", latest_decision_date_fixed="2026-10-01")
    await item(world, code="CR-OK", amount="10000", latest_decision_date_fixed="2026-12-01")
    first = await sweep_once(world.factory, today=TODAY)
    second = await sweep_once(world.factory, today=TODAY)
    assert (first["escalations"], first["failures"]) == (1, 0)
    assert (second["escalations"], second["failures"]) == (0, 0)
    async with world.factory() as s:
        rows = (
            (await s.execute(select(ActivityLog).where(ActivityLog.action == "decision_overdue_escalated")))
            .scalars()
            .all()
        )
    assert [r.entity_id for r in rows] == [str(iid)]
    assert str(world.requester) in rows[0].metadata_["notified"]
    assert str(world.pm) in rows[0].metadata_["notified"]


# ── gate evidence ──────────────────────────────────────────────────────────


async def test_items_naming_an_area_the_project_does_not_have_read_as_unknown_not_as_nothing(world: World) -> None:
    from app.modules.commitment_release.evidence import items_released_by_gate
    from app.modules.project_governance.evidence import GateAttempt

    await item(world, code="CR-G1", amount="10000", gate_code="G1", governance_area_code="ghost")
    attempt = GateAttempt(gate_id=uuid.uuid4(), gate_code="G1", attempt_no=1)
    async with world.factory() as s:
        elsewhere = await items_released_by_gate(s, world.project_id, attempt, SimpleNamespace(code="cost"))
        own = await items_released_by_gate(s, world.project_id, attempt, SimpleNamespace(code="ghost"))
        other_gate = await items_released_by_gate(
            s,
            world.project_id,
            GateAttempt(gate_id=uuid.uuid4(), gate_code="G2", attempt_no=1),
            SimpleNamespace(code="cost"),
        )
    assert [(e.state, e.detail) for e in elsewhere] == [("unknown", "CR-G1")]
    assert [(e.state, e.detail) for e in own] == [("not_met", "CR-G1")]
    assert other_gate == []


# ── findings 18 to 20: the demo seed ───────────────────────────────────────


async def test_the_demo_seed_shows_a_released_item_a_decided_tranche_and_a_pending_one(world: World) -> None:
    from app.modules.commitment_release import seed
    from app.modules.contracts.models import Contract

    async with world.factory() as s:
        pid = await add_project(s, world.manager, [world.requester])
        s.add(
            Contract(
                project_id=pid,
                code="SC-DEMO",
                title="Structure",
                counterparty_type="subcontractor",
                total_value=D("1200000"),
                currency="EUR",
                status="active",
                metadata_={},
            )
        )
        await s.flush()
        counts = await seed._seed_project(s, pid)
        await s.commit()
    assert counts == {"items": 4, "links": 1, "releases": 3}
    async with world.factory() as s:
        items = {
            i.code: i
            for i in (await s.execute(select(CommitmentItem).where(CommitmentItem.project_id == pid))).scalars()
        }
        releases = (
            (
                await s.execute(
                    select(ReleaseDecision)
                    .where(ReleaseDecision.project_id == pid)
                    .order_by(ReleaseDecision.created_at)
                )
            )
            .scalars()
            .all()
        )
        exposure = await CommitmentService(s).exposure(pid, as_of=TODAY)
    assert {c: i.status for c, i in items.items()} == {
        "CR-001": "committed",
        "CR-002": "planned",
        "CR-003": "release_requested",
        "CR-004": "planned",
    }
    assert [r.outcome for r in releases] == ["released", "released", "pending"]
    assert all(r.decided_at is None or r.created_at < r.decided_at for r in releases)
    assert {i.currency for i in items.values()} == {"EUR"}
    by_code = {row["code"]: row for row in exposure["items"]}
    # Nothing is bound on the facade item: no loss, and no gain from a salvage estimate either.
    assert D(by_code["CR-002"]["residual_loss"]) == D("0")
    assert D(by_code["CR-001"]["residual_loss"]) == D("40000")


# ── the governance read port ───────────────────────────────────────────────


async def test_gates_areas_and_documents_come_from_the_governance_port(world: World) -> None:
    from app.modules.project_governance.public import project_areas, project_documents, project_gates
    from app.modules.project_governance.service import GovernanceService

    async with world.factory() as s:
        await GovernanceService(s).set_model(
            world.project_id,
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            actor_id=world.manager,
            tenant_id=str(world.manager),
        )
        await s.commit()
    async with world.factory() as s:
        gates = await project_gates(s, world.project_id)
        areas = await project_areas(s, world.project_id)
        documents = await project_documents(s, world.project_id)
        refs = await CommitmentService(s).references(world.project_id)
    assert gates
    assert areas
    assert documents
    assert refs["has_model"] is True
    assert [g["code"] for g in refs["gates"]] == [g.code for g in gates]
    assert [g["name"] for g in refs["gates"]] == [g.label for g in gates]
    assert {g["status"] for g in refs["gates"]} == {g.status for g in gates}
    assert [a["code"] for a in refs["areas"]] == [a.code for a in areas]
    assert [(d["id"], d["doc_type"], d["area_code"]) for d in refs["frame_documents"]] == [
        (str(d.id), d.code, d.area_code) for d in documents
    ]

    gate, area = gates[0].code, areas[0].code
    for fields, code in (
        ({"gate_code": gate, "governance_area_code": "no-such-area"}, "governance_area_unknown"),
        ({"gate_code": "no-such-gate", "governance_area_code": area}, "gate_unknown"),
    ):
        with pytest.raises(CommitmentError) as exc:
            await item(world, code="CR-X", amount="10000", **fields)
        assert exc.value.code == code
    await item(world, code="CR-OK", amount="10000", gate_code=gate, governance_area_code=area)

    async with world.factory() as s:
        svc = CommitmentService(s)
        # Nothing is decided and nothing is binding yet, and an id the project does not own is not met.
        assert await svc._gate_state(world.project_id, gate) == "open"
        assert await svc._document_state(world.project_id, str(documents[0].id)) == "open"
        assert await svc._document_state(world.project_id, str(uuid.uuid4())) == "open"
        assert await svc._document_state(world.project_id, "not-a-uuid") == "open"


async def test_a_handed_over_item_names_its_successor_only_to_a_reader_of_the_receiving_project(
    world: World,
) -> None:
    async with world.factory() as s:
        other = await add_project(s, world.manager, [])
        await CommitmentService(s).set_matrix(
            other, actor_id=world.manager, tenant_id=str(world.manager), schedule_id="neutral"
        )
        target = await CommitmentService(s).create_item(
            other,
            {
                "code": "CR-T",
                "title": "Receiving item",
                "commitment_type": "design",
                "planned_source": "manual",
                "planned_manual_amount": "10000",
                "currency": "EUR",
            },
            actor_id=world.manager,
        )
        await s.commit()
    iid = await item(world, code="CR-S", amount="10000")
    async with world.factory() as s:
        await CommitmentService(s).transfer_item(
            world.project_id,
            iid,
            target_project_id=other,
            target_item_id=target.id,
            reason="Package moved",
            actor_id=world.manager,
            manage=True,
        )
        await s.commit()

    async def successor(actor: uuid.UUID) -> dict:
        async with world.factory() as s:
            data = await CommitmentService(s).item_views(world.project_id, today=TODAY, item_ids=[iid], actor_id=actor)
        return data["items"][0]["transferred_to"]

    seen = await successor(world.manager)
    assert seen == {
        "project_id": str(other),
        "item_id": str(target.id),
        "same_project": False,
        "can_open": True,
        "project_name": seen["project_name"],
        "code": "CR-T",
        "title": "Receiving item",
    }
    assert seen["project_name"]
    hidden = await successor(world.requester)
    assert (hidden["project_id"], hidden["item_id"], hidden["can_open"]) == (str(other), str(target.id), False)
    assert (hidden["project_name"], hidden["code"], hidden["title"]) == (None, None, None)
