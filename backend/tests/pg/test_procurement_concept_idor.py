# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Procurement concept ids are bound to their project and frameworks to their company.

An id from project B used under project A, or a framework id used by another
company, answers 404 and changes nothing.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.procurement_concept.errors import ProcurementError
from app.modules.procurement_concept.models import BidderCandidate, MarketSounding
from tests._pg import isolated_engine
from tests.pg.procurement_concept_fixtures import World, add_contract_package, build_world, put, svc_call

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]


@pytest_asyncio.fixture
async def pair():
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        a = await build_world(factory)
        b = await build_world(factory)
        await add_contract_package(a, "W1", "construction")
        await add_contract_package(b, "W1", "construction")
        await put(a, "W1", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
        await put(b, "W1", {"estimated_value": "100000", "currency": "EUR", "procedure_code": "open"})
        yield a, b


async def _404(w: World, fn: str, *args, **kw) -> None:
    with pytest.raises(ProcurementError) as exc:
        await svc_call(w, fn, *args, **kw)
    assert exc.value.status_code == 404, exc.value.code


async def test_award_package_of_another_project_is_not_found(pair) -> None:
    a, b = pair
    with pytest.raises(ProcurementError) as exc:
        await svc_call(
            a,
            "put_package",
            a.project_id,
            b.packages["W1"],
            {"procedure_code": "restricted"},
            actor_id=a.manager,
            role="manager",
            tenant_id=str(a.manager),
        )
    assert exc.value.status_code == 404
    await _404(
        a,
        "create_execution",
        a.project_id,
        b.packages["W1"],
        vehicle=None,
        submission_deadline=None,
        actor_id=a.manager,
        role="manager",
    )


async def test_candidate_and_sounding_ids_are_bound_to_their_project(pair) -> None:
    from app.modules.subcontractors.models import Subcontractor

    a, b = pair
    async with b.factory() as s:
        sub = Subcontractor(legal_name="Trade contractor")
        s.add(sub)
        await s.commit()
    cand: BidderCandidate = await svc_call(
        b,
        "add_candidate",
        b.project_id,
        b.packages["W1"],
        {"subcontractor_id": sub.id, "list": "long"},
        actor_id=b.manager,
    )
    snd: MarketSounding = await svc_call(
        b,
        "save_sounding",
        b.project_id,
        {"trade": "Rebar", "held_on": "2026-09-01", "package_ids": [b.packages["W1"]]},
        actor_id=b.manager,
    )
    await _404(a, "patch_candidate", a.project_id, cand.id, {"list": "short"}, actor_id=a.manager)
    await _404(a, "delete_candidate", a.project_id, cand.id, actor_id=a.manager)
    await _404(a, "delete_sounding", a.project_id, snd.id, actor_id=a.manager)
    await _404(
        a,
        "save_sounding",
        a.project_id,
        {"trade": "x", "held_on": "2026-09-01"},
        actor_id=a.manager,
        sounding_id=snd.id,
    )
    # A sounding in A cannot point at B's package either.
    await _404(
        a,
        "save_sounding",
        a.project_id,
        {"trade": "x", "held_on": "2026-09-01", "package_ids": [b.packages["W1"]]},
        actor_id=a.manager,
    )
    # The rows in B are untouched.
    async with b.factory() as s:
        assert (await s.get(BidderCandidate, cand.id)).list_kind == "long"
        assert await s.get(MarketSounding, snd.id) is not None


async def test_framework_of_another_company_is_invisible(pair) -> None:
    a, b = pair
    fw = await svc_call(
        b,
        "create_framework",
        str(b.manager),
        {
            "code": "FW-B",
            "title": "Formwork",
            "package_kinds": ["supply"],
            "lots": [],
            "max_value": "100000",
            "currency": "EUR",
            "start_date": date(2026, 1, 1),
            "end_date": date(2028, 1, 1),
        },
        actor_id=b.manager,
    )
    assert [f.id for f in await svc_call(a, "list_frameworks", str(a.manager))] == []
    assert await svc_call(a, "list_frameworks", None) == []
    await _404(a, "patch_framework", str(a.manager), fw.id, {"title": "taken"}, actor_id=a.manager)
    await _404(a, "ledger", str(a.manager), fw.id)
    await add_contract_package(a, "S1", "supply")
    with pytest.raises(ProcurementError) as exc:
        await put(a, "S1", {"procedure_code": "framework_call_off", "framework_agreement_id": fw.id})
    assert exc.value.status_code == 404


async def test_concept_of_a_project_without_one_is_not_found(pair) -> None:
    a, _ = pair
    await _404(a, "get_concept", uuid.uuid4())
