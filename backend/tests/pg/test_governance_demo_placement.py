# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The governance demo seed leaves the demo projects at different, deliberate moments.

The module seeders read a project's state through the governance port: the gate
into the phase that enables ``construction_start`` is undecided (preparation
story) or decided (running site). So every assertion about a placement here is
made through that port, the way a module seeder would ask.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.project_governance.events as gov_events
from app.core.partner_pack import discovery
from app.modules.project_governance import catalogue as cat
from app.modules.project_governance import catalogue_packs, public, seed
from app.modules.project_governance import evidence as evd
from app.modules.project_governance.models import (
    GovernanceCheck,
    GovernanceDecision,
    GovernanceDocument,
    GovernanceModel,
)
from app.modules.project_governance.seed import seed_project_governance_demo
from tests._pg import isolated_engine

pytestmark = pytest.mark.asyncio

DEMO = "demo@openconstructionerp.com"
MANAGER = "manager@openconstructionerp.com"
ESTIMATOR = "estimator@openconstructionerp.com"
PACK_MODEL = "pack_model"
PACK_PATH = "catalogues/phase_model/pack_model_v1.json"
DEMO_PATH = "demo/demo_project.json"


@pytest_asyncio.fixture
async def factory(monkeypatch: pytest.MonkeyPatch):
    # Only the providers a test registers: on an integrated branch the modules have theirs.
    providers = dict(evd._REGISTRY)
    evd._REGISTRY.clear()
    async with isolated_engine() as engine:
        f = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(gov_events, "async_session_factory", f)
        yield f
    evd._REGISTRY.clear()
    evd._REGISTRY.update(providers)


async def _estate(factory, *demo_ids: str, locale: str = "en") -> dict[str, uuid.UUID]:
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    async with factory() as s:
        users: dict[str, uuid.UUID] = {}
        for email, role in ((DEMO, "admin"), (ESTIMATOR, "estimator"), (MANAGER, "manager")):
            users[email] = uuid.uuid4()
            s.add(
                User(
                    id=users[email],
                    email=email,
                    hashed_password="x",
                    full_name=email.split("@")[0].title(),
                    role=role,
                    locale="en",
                    is_active=True,
                    metadata_={},
                )
            )
        await s.flush()
        projects: dict[str, uuid.UUID] = {}
        for demo_id in demo_ids:
            projects[demo_id] = uuid.uuid4()
            s.add(
                Project(
                    id=projects[demo_id],
                    name=f"Demo {demo_id}",
                    currency="EUR",
                    status="active",
                    locale=locale,
                    owner_id=users[DEMO],
                    metadata_={"demo_id": demo_id},
                )
            )
        await s.commit()
    return projects | {"manager": users[MANAGER]}


async def _seed(factory, estate: dict[str, uuid.UUID]) -> dict[str, int]:
    async with factory() as s:
        counts = await seed_project_governance_demo(s, [v for k, v in estate.items() if k != "manager"])
        await s.commit()
    return counts


async def _asked_through_the_port(factory, pid: uuid.UUID, capability: str = "construction_start") -> dict[str, Any]:
    """What a module seeder reads: the phase, the phases enabling the capability, the gate into them."""
    async with factory() as s:
        controls = await public.project_controls(s, pid)
        enabling = await public.phases_enabling(s, pid, capability)
        gates = await public.project_gates(s, pid)
    into = [g for g in gates if g.to_phase in enabling]
    assert len(into) == 1, [g.code for g in into]
    return {"phase": controls.current_phase, "enabling": enabling, "gate": into[0], "gates": gates}


async def _decisions(factory, pid: uuid.UUID) -> list[GovernanceDecision]:
    async with factory() as s:
        rows = await s.execute(
            select(GovernanceDecision)
            .where(GovernanceDecision.project_id == pid)
            .order_by(GovernanceDecision.decided_at)
        )
        return list(rows.scalars())


async def test_the_demo_estate_has_a_project_before_the_construction_gate_one_in_execution_and_one_near_handover(
    factory,
) -> None:
    estate = await _estate(factory, "office-london", "residential-berlin", "medical-us")
    assert (await _seed(factory, estate))["projects"] == 3
    today = datetime.now(UTC).date()

    before = await _asked_through_the_port(factory, estate["office-london"])
    assert before["enabling"] == ("construction",)
    assert before["phase"] == "brief"
    assert before["gate"].status == "not_started"

    running = await _asked_through_the_port(factory, estate["residential-berlin"])
    assert running["enabling"] == ("construction",)
    assert running["phase"] == "construction"
    assert (running["gate"].status, running["gate"].last_outcome) == ("decided", "go")
    walked = [g for g in running["gates"] if g.order <= running["gate"].order]
    assert len(walked) == 8 and all(g.status == "decided" for g in walked)
    assert [g.status for g in running["gates"] if g.order > running["gate"].order] == ["not_started", "not_started"]
    decisions = await _decisions(factory, estate["residential-berlin"])
    assert len(decisions) == 8
    # The real path: the manager login on the pinned route, never an owner of an area.
    assert {d.decided_by for d in decisions} == {estate["manager"]}
    assert all(d.approval_instance_id is not None and d.snapshot["four_eyes"] is True for d in decisions)

    late = await _asked_through_the_port(factory, estate["medical-us"])
    assert late["phase"] == "construction"
    assert late["gate"].status == "decided"
    handover = await _asked_through_the_port(factory, estate["medical-us"], "handover")
    assert handover["enabling"] == ("handover",)
    assert handover["gate"].status == "in_preparation"
    assert handover["gate"].target_date == today + timedelta(days=30)
    async with factory() as s:
        pid = estate["medical-us"]
        docs = {
            d.doc_type: d
            for d in (await s.execute(select(GovernanceDocument).where(GovernanceDocument.project_id == pid))).scalars()
        }
        required = [d for d in docs.values() if handover["gate"].code in (d.required_at_gates or [])]
        assert sorted(d.doc_type for d in required) == ["handover_documentation", "health_safety_file"]
        assert {d.status for d in required} == {"in_review"}
        checks = list(
            (
                await s.execute(
                    select(GovernanceCheck).where(
                        GovernanceCheck.project_id == pid, GovernanceCheck.gate_id == handover["gate"].id
                    )
                )
            ).scalars()
        )
    statuses = sorted(c.status for c in checks if c.status != "not_assessed")
    assert statuses == ["ready"] * 8 + ["ready_with_risks"]
    # Handover is not decided, so a module that tells handover apart still sees a running site.
    assert (await _asked_through_the_port(factory, estate["residential-berlin"], "handover"))["gate"].status == (
        "not_started"
    )


async def test_a_module_that_has_no_rows_yet_does_not_stop_the_walk(factory) -> None:
    """Governance seeds before the modules, so a blocking provider answers not met on the way."""

    async def _nothing_yet(session, project_id, attempt, area):
        if area.code != "procurement":
            return []
        return [evd.EvidenceItem(code="packages_planned", state="not_met")]

    evd.register_evidence_provider("*", _nothing_yet, name="probe_empty_module", blocking=True)
    estate = await _estate(factory, "residential-berlin")
    assert (await _seed(factory, estate))["projects"] == 1

    running = await _asked_through_the_port(factory, estate["residential-berlin"])
    assert running["phase"] == "construction"
    decisions = await _decisions(factory, estate["residential-berlin"])
    assert len(decisions) == 8
    assert {d.outcome for d in decisions} == {"go_with_conditions"}
    assert all(d.proceed_at_risk_areas == ["procurement"] for d in decisions)


async def test_a_placement_that_cannot_be_completed_leaves_the_first_gate_story(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _breaks(stage, *, near_handover: bool) -> None:
        await stage.open(
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            owner_of=lambda code: stage.cast.owner,
        )
        raise seed.SeedStop("a gate on the way is blocked")

    monkeypatch.setattr(seed, "_execution_story", _breaks)
    estate = await _estate(factory, "residential-berlin")
    assert (await _seed(factory, estate))["projects"] == 1

    state = await _asked_through_the_port(factory, estate["residential-berlin"])
    assert state["phase"] == "brief"
    decisions = await _decisions(factory, estate["residential-berlin"])
    assert [d.outcome for d in decisions] == ["go_with_conditions"]
    async with factory() as s:
        models = (
            await s.execute(select(GovernanceModel).where(GovernanceModel.project_id == estate["residential-berlin"]))
        ).scalars()
        assert len(list(models)) == 1


# ── the project of the active pack ──


def _pack_body() -> dict[str, Any]:
    body = json.loads((cat.CATALOGUE_DIR / "elf_module_framework.json").read_text(encoding="utf-8"))
    body["id"] = PACK_MODEL
    body["version"] = 1
    return body


def _demo_file(body: dict[str, Any]) -> dict[str, Any]:
    areas = [a["code"] for a in body["areas"]]
    return {
        "schema_version": 1,
        "project": {"demo_template_id": "office-frankfurt"},
        "pins": [{"kind": "phase_model", "source": "pack", "id": PACK_MODEL, "version": 1}],
        "governance": {
            "four_eyes": True,
            "area_owners": {code: ("cost" if i in (7, 8) else "owner") for i, code in enumerate(areas)},
            "frame_documents": [
                {
                    "doc_type": d["code"],
                    "container_code": f"GOV-M{i:02d}",
                    "title": {"en": f"Frame {i}", "de": f"Rahmendokument {i}"},
                    "file_name": f"frame-{i}.pdf",
                    "revisions": 2,
                    "state": "draft" if i == 2 else "in_review",
                }
                for i, d in enumerate(body["document_types"])
            ],
            "gate": {
                "code": body["gates"][0]["code"],
                "target_in_days": 21,
                "stop_at": "in_preparation",
                "checks": [
                    {
                        "area": code,
                        "status": "not_assessed" if i == 2 else "ready",
                        "rag": "" if i == 2 else "green",
                        "note": {"en": "Fine", "de": "In Ordnung"},
                    }
                    for i, code in enumerate(areas)
                ],
                "decision": None,
            },
        },
    }


@pytest.fixture
def active_pack(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], bytes]:
    body = _pack_body()
    manifest = SimpleNamespace(
        slug="demo-pack",
        metadata={
            "catalogues": [{"kind": "phase_model", "id": PACK_MODEL, "version": 1, "path": PACK_PATH}],
            "demo": {"path": DEMO_PATH},
        },
    )
    files = {
        ("demo-pack", PACK_PATH): json.dumps(body).encode("utf-8"),
        ("demo-pack", DEMO_PATH): json.dumps(_demo_file(body)).encode("utf-8"),
    }
    monkeypatch.setattr(discovery, "get_active_pack", lambda: manifest)
    monkeypatch.setattr(discovery, "discover_packs", lambda: [manifest])
    monkeypatch.setattr(discovery, "read_pack_file", lambda slug, rel: files.get((slug, rel)))
    catalogue_packs.clear_pack_catalogue_cache()
    yield files
    catalogue_packs.clear_pack_catalogue_cache()


async def test_the_project_of_the_pack_stops_where_its_demo_file_says(factory, active_pack) -> None:
    estate = await _estate(factory, "office-frankfurt", "office-london", locale="de")
    assert (await _seed(factory, estate))["projects"] == 2
    pid = estate["office-frankfurt"]
    body = _pack_body()

    async with factory() as s:
        model = (await s.execute(select(GovernanceModel).where(GovernanceModel.project_id == pid))).scalar_one()
        other = (
            await s.execute(select(GovernanceModel).where(GovernanceModel.project_id == estate["office-london"]))
        ).scalar_one()
    assert (model.catalogue_source, model.catalogue_id, model.catalogue_version) == ("pack", PACK_MODEL, 1)
    # The file names one project. Every other one keeps the built-in story.
    assert (other.catalogue_source, other.catalogue_id) == ("shipped", "neutral")

    filmed = await _asked_through_the_port(factory, pid)
    assert filmed["phase"] == body["gates"][0]["from_phase"]
    assert filmed["gate"].code == body["gates"][0]["code"]
    assert filmed["gate"].status == "in_preparation"
    assert filmed["gate"].target_date == datetime.now(UTC).date() + timedelta(days=21)
    assert await _decisions(factory, pid) == []

    async with factory() as s:
        from app.modules.cde.models import DocumentContainer, DocumentRevision

        docs = list((await s.execute(select(GovernanceDocument).where(GovernanceDocument.project_id == pid))).scalars())
        titles = set(
            (await s.execute(select(DocumentContainer.title).where(DocumentContainer.project_id == pid))).scalars()
        )
        revisions = (
            await s.execute(
                select(DocumentRevision.id)
                .join(DocumentContainer, DocumentContainer.id == DocumentRevision.container_id)
                .where(DocumentContainer.project_id == pid)
            )
        ).all()
        checks = list(
            (
                await s.execute(
                    select(GovernanceCheck).where(GovernanceCheck.project_id == pid, GovernanceCheck.status == "ready")
                )
            ).scalars()
        )
    drafts = [d.doc_type for d in docs if d.status == "draft"]
    assert drafts == [body["document_types"][2]["code"]]
    assert {d.status for d in docs} == {"draft", "in_review"}
    assert all(d.status not in ("approved_at_gate", "binding") for d in docs)
    assert "Rahmendokument 0" in titles and "Frame 0" not in titles
    assert len(revisions) == 2 * len(body["document_types"])
    assert len(checks) == len(body["areas"]) - 1
    assert {c.note for c in checks} == {"In Ordnung"}


async def test_a_demo_file_that_breaks_a_rule_leaves_the_built_in_story(factory, active_pack) -> None:
    broken = _demo_file(_pack_body())
    broken["governance"]["frame_documents"][0]["state"] = "binding"
    active_pack[("demo-pack", DEMO_PATH)] = json.dumps(broken).encode("utf-8")
    estate = await _estate(factory, "office-frankfurt")
    assert (await _seed(factory, estate))["projects"] == 1

    async with factory() as s:
        model = (
            await s.execute(select(GovernanceModel).where(GovernanceModel.project_id == estate["office-frankfurt"]))
        ).scalar_one()
    assert (model.catalogue_source, model.catalogue_id) == ("shipped", "neutral")
    assert [d.outcome for d in await _decisions(factory, estate["office-frankfurt"])] == ["go_with_conditions"]
