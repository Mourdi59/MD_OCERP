# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The procurement concept against the real governance module, and the demo seed, on PostgreSQL.

The governance world pins the shipped neutral model. Its catalogue does not tag
a procurement area or a release gate in this tree, so the tests hand the module
the resolved hosting and name the gate and the frame document on the concept,
which is exactly what a manager does in such a project.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.procurement_concept.events as pc_events
import app.modules.project_governance.events as gov_events
from app.modules.procurement_concept import plan_source as plan
from app.modules.procurement_concept.catalogue import register_kind
from app.modules.procurement_concept.evidence import PROVIDER_NAME, concept_ready, register_gate_evidence
from app.modules.procurement_concept.hosting import ProcurementHosting
from app.modules.procurement_concept.models import (
    AwardPackage,
    BidderCandidate,
    FrameworkAgreement,
    ProcurementConcept,
)
from app.modules.procurement_concept.seed import seed_procurement_concept_demo
from app.modules.procurement_concept.service import ProcurementConceptService
from app.modules.project_governance.errors import GovernanceError
from app.modules.project_governance.evidence import GateAttempt, unregister_evidence_provider
from tests._pg import isolated_engine
from tests.pg.governance_fixtures import World, areas, build_world, decide, documents, gate, prepare_gate
from tests.pg.procurement_concept_fixtures import ensure_plan_tables, patch_hosting

pytestmark = pytest.mark.asyncio

G1 = "strategy_to_brief"
G2 = "brief_to_concept"
AREA = "contracts_procurement"
FRAME_DOC = "business_case"


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    register_kind()
    patch_hosting(monkeypatch, ProcurementHosting(AREA, (), ()))
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(gov_events, "async_session_factory", factory)
        monkeypatch.setattr(pc_events, "async_session_factory", factory)
        await ensure_plan_tables(factory)
        yield await build_world(factory)
    unregister_evidence_provider(PROVIDER_NAME)


async def _concept(w: World, **extra) -> None:
    async with w.factory() as s:
        await ProcurementConceptService(s).set_concept(
            w.project_id,
            {"catalogue_source": "shipped", "catalogue_id": "neutral", **extra},
            actor_id=w.manager,
            can_manage=True,
            tenant_id=str(w.manager),
        )
        await s.commit()


async def _submit(w: World) -> None:
    async with w.factory() as s:
        await ProcurementConceptService(s).transition(w.project_id, "in_review", actor_id=w.owner, can_manage=True)
        await s.commit()


async def _stored(w: World) -> ProcurementConcept:
    async with w.factory() as s:
        return (
            await s.execute(sa.select(ProcurementConcept).where(ProcurementConcept.project_id == w.project_id))
        ).scalar_one()


async def _evidence(w: World, gate_code: str, area_code: str) -> list:
    g = await gate(w, gate_code)
    area = (await areas(w))[area_code]
    async with w.factory() as s:
        return await concept_ready(s, w.project_id, GateAttempt(g.id, g.code, g.attempt_no or 1), area)


async def test_evidence_is_met_not_met_or_unknown_and_never_silently_empty(world: World) -> None:
    assert await _evidence(world, G1, AREA) == []  # no concept: the module has nothing to say
    await _concept(world)
    # A concept exists but nothing names or tags the release gate: unknown, with the reason.
    (item,) = await _evidence(world, G1, AREA)
    assert (item.state, item.detail) == ("unknown", "release_gate_unresolved")
    await _concept(world, release_gate_code=G1)
    (item,) = await _evidence(world, G1, AREA)
    assert item.state == "not_met"
    # One item per gate, on one area; another gate is not this module's business.
    assert await _evidence(world, G1, "cost_finance") == []
    assert await _evidence(world, G2, AREA) == []
    await _submit(world)
    (item,) = await _evidence(world, G1, AREA)
    assert item.state == "met"


async def _prepare_and_decide(w: World) -> None:
    g = await prepare_gate(w, G1)
    await decide(w, g.id)


async def test_a_draft_concept_blocks_the_release_gate(world: World) -> None:
    register_gate_evidence()
    await _concept(world, release_gate_code=G1, governance_document_id=(await documents(world))[FRAME_DOC].id)
    with pytest.raises(GovernanceError):
        await _prepare_and_decide(world)
    assert (await documents(world))[FRAME_DOC].status != "binding"
    assert (await _stored(world)).state == "draft"


async def test_the_gate_decision_approves_the_submitted_concept_through_the_event_bus(world: World) -> None:
    register_gate_evidence()
    pc_events.register_procurement_concept_subscribers()
    doc = (await documents(world))[FRAME_DOC]
    await _concept(world, release_gate_code=G1, governance_document_id=doc.id)
    await _submit(world)
    g = await prepare_gate(world, G1)
    await decide(world, g.id)
    assert (await documents(world))[FRAME_DOC].status == "binding"
    for _ in range(100):
        if (await _stored(world)).state == "approved":
            break
        await asyncio.sleep(0.1)
    concept = await _stored(world)
    assert concept.state == "approved"
    assert (concept.submitted_by, concept.approved_by) == (world.owner, world.decider)
    async with world.factory() as s:
        svc = ProcurementConceptService(s)
        assert await svc.effective_state(await svc.get_concept(world.project_id)) == "binding"
        caps = await svc.capabilities(world.project_id, world.manager, True)
    assert caps["edit_plan"] == {"allowed": False, "reason": "binding_requires_change_request"}


# ── Demo seed (finding 17) ──────────────────────────────────────────────


async def _demo_project(w: World, *, currency: str, country: str, public: bool) -> uuid.UUID:
    from app.modules.projects.models import Project

    pid = uuid.uuid4()
    async with w.factory() as s:
        s.add(
            Project(
                id=pid,
                name=f"Demo {pid.hex[:6]}",
                currency=currency,
                country_code=country,
                status="active",
                owner_id=w.manager,
                metadata_={"demo_id": f"demo-{pid.hex[:6]}"},
            )
        )
        await s.flush()
        for i, (code, kind) in enumerate(
            (("GC", "construction"), ("DES", "design"), ("STL", "supply"), ("FAC", "supply_and_install"))
        ):
            await s.execute(
                sa.insert(plan.PACKAGE_TABLE).values(
                    id=uuid.uuid4(),
                    project_id=pid,
                    code=code,
                    title=f"{code} package",
                    kind=kind,
                    scope="",
                    wbs_ref="",
                    boq_ref="",
                    status="planned",
                    sort_order=i,
                )
            )
        await s.execute(
            sa.insert(plan.MODEL_TABLE).values(
                id=uuid.uuid4(),
                project_id=pid,
                selected_form_code="design_bid_build_split",
                status="approved",
                owner_capability={"public_client": public},
            )
        )
        await s.commit()
    return pid


async def _subcontractors(w: World) -> None:
    from app.modules.subcontractors.models import Subcontractor

    async with w.factory() as s:
        # A company a user registered, which would sort first under any ordering by name or tax id.
        s.add(Subcontractor(legal_name="AAA real customer company", tax_id="0000", website="https://real.example.org"))
        for n in range(1, 7):
            s.add(
                Subcontractor(
                    legal_name=f"Demo contractor {n:02d}",
                    tax_id=f"DEMO-{n:02d}",
                    website=f"https://contractor-{n:02d}.example.com",
                )
            )
        await s.commit()


async def _cleared_condition(w: World, project_id: uuid.UUID) -> tuple[uuid.UUID, str]:
    from app.modules.project_governance.models import GovernanceCondition, GovernanceDecision, GovernanceGate

    async with w.factory() as s:
        g = GovernanceGate(
            project_id=project_id, catalogue_id="neutral", code=G1, from_phase="strategy", to_phase="brief"
        )
        s.add(g)
        await s.flush()
        d = GovernanceDecision(
            project_id=project_id,
            gate_id=g.id,
            gate_code=G1,
            attempt_no=1,
            outcome="go_with_conditions",
            decided_by=w.decider,
            decided_at=datetime.now(UTC),
        )
        s.add(d)
        await s.flush()
        c = GovernanceCondition(
            project_id=project_id,
            decision_id=d.id,
            gate_id=g.id,
            gate_code=G1,
            text="Fabrication slot reserved",
            status="cleared",
            cleared_at=datetime.now(UTC),
        )
        s.add(c)
        await s.commit()
        return c.id, G1


async def _seed(w: World, pids: list[uuid.UUID]) -> dict:
    async with w.factory() as s:
        out = await seed_procurement_concept_demo(s, pids)
        await s.commit()
        return out


async def test_the_seed_leaves_a_concept_that_can_go_to_the_gate(world: World) -> None:
    await _subcontractors(world)
    pid = await _demo_project(world, currency="EUR", country="DE", public=True)
    condition_id, gate_code = await _cleared_condition(world, pid)
    assert (await _seed(world, [pid]))["projects"] == 1
    assert (await _seed(world, [pid]))["projects"] == 0  # a re-run adds nothing
    async with world.factory() as s:
        svc = ProcurementConceptService(s)
        concept = await svc.get_concept(pid)
        cat = await svc.catalogue_of(concept)
        found = await svc.findings(pid)
        rows = (await s.execute(sa.select(AwardPackage).where(AwardPackage.project_id == pid))).scalars().all()
        cands = (await s.execute(sa.select(BidderCandidate).where(BidderCandidate.project_id == pid))).scalars().all()
        from app.modules.subcontractors.models import Subcontractor

        names = sorted((await s.get(Subcontractor, c.subcontractor_id)).legal_name for c in cands if c.subcontractor_id)
        advance = next(r for r in rows if r.is_advance)
        release = await svc.advance_release_status(pid, advance, await svc.release_gate(pid, concept))
    assert "DE" in cat.jurisdiction_countries
    assert (concept.public_client, concept.state, concept.release_gate_code) == (True, "draft", gate_code)
    assert concept.client_type in cat.jurisdiction(concept.jurisdiction).client_types
    assert [f for f in found if f["blocks_approval"]] == []
    assert len(rows) == 4
    assert {r.currency for r in rows} == {"EUR"}
    assert names == [f"Demo contractor {n:02d}" for n in range(1, 5)]
    assert (advance.advance_release_id, release) == (condition_id, "released")


async def test_the_seed_plans_in_the_project_currency_and_never_borrows_a_regime(world: World) -> None:
    await _subcontractors(world)
    pid = await _demo_project(world, currency="JPY", country="JP", public=True)
    await _seed(world, [pid])
    async with world.factory() as s:
        concept = await ProcurementConceptService(s).get_concept(pid)
        rows = (await s.execute(sa.select(AwardPackage).where(AwardPackage.project_id == pid))).scalars().all()
        fw = (
            (await s.execute(sa.select(FrameworkAgreement).where(FrameworkAgreement.tenant_id == str(world.manager))))
            .scalars()
            .one()
        )
        found = await ProcurementConceptService(s).findings(pid)
    # No shipped catalogue covers this country in this currency: no threshold regime is pretended.
    assert (concept.catalogue_id, concept.public_client, concept.client_type) == ("neutral", False, "private")
    assert {r.currency for r in rows} == {"JPY"} and fw.currency == "JPY"
    assert max(r.estimated_value for r in rows) == Decimal("2400000") * 150
    # Without a cleared condition nothing is planned as an advance package it could never release.
    assert [r for r in rows if r.is_advance] == []
    assert [f for f in found if f["severity"] == "error"] == []
