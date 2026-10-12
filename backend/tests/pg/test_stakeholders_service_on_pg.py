# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The stakeholders service against PostgreSQL: append-only assessments, the
review sweep, the commitment lifecycle, the mandate matrix under concurrency."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.stakeholders.errors import StakeholderError
from app.modules.stakeholders.service import StakeholderService
from tests._pg import isolated_engine
from tests.pg.stakeholders_fixtures import TODAY, World, build_world, stakeholder

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def world():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield await build_world(factory)


async def test_assessments_append_and_classification_is_derived(world: World) -> None:
    sid = await stakeholder(world, "Residents north")
    async with world.factory() as s:
        svc = StakeholderService(s)
        await svc.assess(world.project_id, sid, {"scores": {"power": 1, "interest": 1}}, actor_id=world.editor)
        await svc.assess(world.project_id, sid, {"scores": {"power": 5, "interest": 5}}, actor_id=world.editor)
        await s.commit()
    async with world.factory() as s:
        history = await StakeholderService(s).list_assessments(world.project_id, sid)
    assert len(history) == 2
    assert history[0].classification == "manage_closely"
    assert history[1].classification == "monitor"


async def test_out_of_scale_scores_are_refused(world: World) -> None:
    sid = await stakeholder(world, "Grid")
    async with world.factory() as s:
        with pytest.raises(StakeholderError):
            await StakeholderService(s).assess(
                world.project_id, sid, {"scores": {"power": 9, "interest": 1}}, actor_id=world.editor
            )


async def test_sweep_flags_an_unassessed_stakeholder_once_past_the_interval(world: World) -> None:
    await stakeholder(world, "Council")
    async with world.factory() as s:
        counts = await StakeholderService(s).sweep(world.project_id, today=TODAY + timedelta(days=400))
        await s.commit()
    assert counts["review_due"] >= 1


async def test_commitment_agreed_directly_then_fulfilled_and_verified(world: World) -> None:
    sid = await stakeholder(world, "Neighbour east")
    async with world.factory() as s:
        svc = StakeholderService(s)
        row = await svc.create_commitment(
            world.project_id,
            {
                "stakeholder_ids": [str(sid)],
                "text": "No deliveries before 07:00",
                "category": "working_hours",
                "owner_user_id": str(world.editor),
                "due_date": TODAY + timedelta(days=30),
            },
            actor_id=world.editor,
        )
        await s.commit()
        cid = row.id
    for target in ("agreed", "in_progress", "fulfilled"):
        async with world.factory() as s:
            row, _ = await StakeholderService(s).transition_commitment(
                world.project_id, cid, target, actor_id=world.manager, today=TODAY
            )
            await s.commit()
    assert row.status == "fulfilled"
    assert isinstance(row.source_snapshot, dict)


async def test_two_deciders_for_one_type_are_refused(world: World) -> None:
    rows = [
        {"decision_type": "scope_change", "scope": "", "holder_kind": "role", "holder_code": "client", "letter": "D"},
        {"decision_type": "scope_change", "scope": "", "holder_kind": "role", "holder_code": "investor", "letter": "D"},
    ]
    async with world.factory() as s:
        with pytest.raises(StakeholderError) as exc:
            await StakeholderService(s).put_mandates(world.project_id, rows, actor_id=world.manager, today=TODAY)
    assert exc.value.code == "two_deciders"


async def test_concurrent_matrix_writes_never_leave_two_deciders(world: World) -> None:
    def matrix(code: str) -> list[dict]:
        return [
            {"decision_type": "scope_change", "scope": "", "holder_kind": "role", "holder_code": code, "letter": "D"}
        ]

    async def write(code: str) -> None:
        async with world.factory() as s:
            try:
                await StakeholderService(s).put_mandates(
                    world.project_id, matrix(code), actor_id=world.manager, today=TODAY
                )
                await s.commit()
            except StakeholderError:
                await s.rollback()

    await asyncio.gather(write("client"), write("investor"))
    async with world.factory() as s:
        rows = await StakeholderService(s).repo.mandates(world.project_id)
    deciders = [r for r in rows if r.decision_type == "scope_change" and r.scope == "" and r.letter == "D"]
    assert len(deciders) == 1


async def test_who_decides_without_an_authority_evaluator_says_not_evaluated(world: World) -> None:
    async with world.factory() as s:
        out = await StakeholderService(s).who_decides(
            world.project_id, "order_award", "", today=TODAY, amount="50000", currency="EUR"
        )
    assert out["decision_type"] == "order_award"
    assert "authority_not_evaluated" in str(out)
