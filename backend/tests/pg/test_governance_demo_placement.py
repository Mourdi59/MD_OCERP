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
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.project_governance.events as gov_events
from app.core import demo_cast, demo_enrichment
from app.core.demo_accounts import DEMO_ACCOUNT_EMAILS, is_reserved_mail_domain
from app.core.partner_pack import discovery
from app.modules.project_governance import catalogue as cat
from app.modules.project_governance import catalogue_packs, public, seed
from app.modules.project_governance import evidence as evd
from app.modules.project_governance.models import (
    GovernanceCheck,
    GovernanceCondition,
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


async def _estate(factory, *demo_ids: str, locale: str = "en", owner_only: bool = False) -> dict[str, uuid.UUID]:
    """Demo projects with the three demo logins, or (``owner_only``) as a pack install leaves them."""
    from app.modules.projects.models import Project
    from app.modules.users.models import User

    async with factory() as s:
        users: dict[str, uuid.UUID] = {}
        logins = ((DEMO, "admin"), (ESTIMATOR, "estimator"), (MANAGER, "manager"))
        for email, role in logins[:1] if owner_only else logins:
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
    return projects | {"manager": users.get(MANAGER, users[DEMO])}


async def _seed(factory, estate: dict[str, uuid.UUID]) -> dict[str, Any]:
    async with factory() as s:
        counts = await seed_project_governance_demo(s, [v for k, v in estate.items() if k != "manager"])
        await s.commit()
    return counts


def _told(result: dict[str, Any], estate: dict[str, uuid.UUID]) -> dict[str, tuple[str, str | None, str | None]]:
    """Per demo id what the seed result says: planned moment, reached moment, fallback reason."""
    names = {str(pid): demo_id for demo_id, pid in estate.items() if demo_id != "manager"}
    assert len(result["placements"]) == len(names), result["placements"]
    return {names[r["project_id"]]: (r["planned"], r["reached"], r["fallback_reason"]) for r in result["placements"]}


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
    result = await _seed(factory, estate)
    assert result["projects"] == 3
    # A named demo project that fell back to the first-gate story fails here, with its reason.
    assert result["fallbacks"] == []
    assert result["ok"] is True
    assert _told(result, estate) == {
        "office-london": ("first_gate", "first_gate", None),
        "residential-berlin": ("execution", "execution", None),
        "medical-us": ("near_handover", "near_handover", None),
    }
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
    result = await _seed(factory, estate)
    assert result["projects"] == 1
    assert result["fallbacks"] == []

    running = await _asked_through_the_port(factory, estate["residential-berlin"])
    assert running["phase"] == "construction"
    decisions = await _decisions(factory, estate["residential-berlin"])
    assert len(decisions) == 8
    assert {d.outcome for d in decisions} == {"go_with_conditions"}
    assert all(d.proceed_at_risk_areas == ["procurement"] for d in decisions)


async def test_a_placement_that_cannot_be_completed_leaves_the_first_gate_story_and_says_so(
    factory, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _breaks(stage, *, near_handover: bool) -> None:
        await stage.open(
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            owner_of=lambda code: stage.cast.owner,
        )
        raise seed.SeedStop("gate_blocked", "a gate on the way is blocked")

    monkeypatch.setattr(seed, "_execution_story", _breaks)
    estate = await _estate(factory, "residential-berlin")
    with caplog.at_level(logging.ERROR, logger="app.modules.project_governance.seed"):
        result = await _seed(factory, estate)
    assert result["projects"] == 1
    # The project has a model, and the result says it is not the one that was planned.
    assert _told(result, estate) == {"residential-berlin": ("execution", "first_gate", "gate_blocked")}
    assert [r["demo_id"] for r in result["fallbacks"]] == ["residential-berlin"]
    assert result["ok"] is False
    said = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR and "was planned at" in r.getMessage()]
    assert len(said) == 1
    assert "residential-berlin" in said[0] and "gate_blocked" in said[0]

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
    result = await _seed(factory, estate)
    assert result["projects"] == 2
    assert result["fallbacks"] == []
    assert (result["pack_demo_file"], result["ok"]) == ("read", True)
    assert _told(result, estate) == {
        "office-frankfurt": ("pack", "pack", None),
        "office-london": ("first_gate", "first_gate", None),
    }
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
    result = await _seed(factory, estate)
    assert result["projects"] == 1
    # The built-in story was written without an error of its own; the plan was the pack story.
    assert _told(result, estate) == {"office-frankfurt": ("pack", "first_gate", "demo_file_invalid")}
    assert result["ok"] is False

    async with factory() as s:
        model = (
            await s.execute(select(GovernanceModel).where(GovernanceModel.project_id == estate["office-frankfurt"]))
        ).scalar_one()
    assert (model.catalogue_source, model.catalogue_id) == ("shipped", "neutral")
    assert [d.outcome for d in await _decisions(factory, estate["office-frankfurt"])] == ["go_with_conditions"]


async def test_a_demo_file_nobody_can_read_fails_the_result_although_every_project_has_a_story(
    factory, active_pack
) -> None:
    active_pack[("demo-pack", DEMO_PATH)] = b"{not json"
    estate = await _estate(factory, "office-frankfurt")
    result = await _seed(factory, estate)
    # The file that names the project did not load, so no row can carry the miss.
    assert _told(result, estate) == {"office-frankfurt": ("first_gate", "first_gate", None)}
    assert (result["pack_demo_file"], result["ok"]) == ("unreadable", False)


async def test_a_seed_that_writes_nothing_names_every_project_and_why(factory, monkeypatch: pytest.MonkeyPatch) -> None:
    estate = await _estate(factory, "office-london", "medical-us", owner_only=True)
    asked = estate | {"gone": uuid.uuid4()}
    result = await _seed(factory, asked)
    assert result["projects"] == 0
    assert _told(result, asked) == {
        "office-london": ("first_gate", None, "no_decider"),
        "medical-us": ("near_handover", None, "no_decider"),
        "gone": ("first_gate", None, "project_not_found"),
    }
    assert len(result["fallbacks"]) == 3
    assert result["ok"] is False


# ── a project with nobody but its owner ──


async def _users(factory) -> dict[str, Any]:
    from app.modules.users.models import User

    async with factory() as s:
        return {u.email: u for u in (await s.execute(select(User))).scalars()}


async def test_an_installation_without_the_demo_logins_gets_a_cast_and_every_project_its_moment(
    factory, caplog: pytest.LogCaptureFixture
) -> None:
    """What a pack install leaves: demo projects, their owner, nobody else."""
    estate = await _estate(factory, "office-london", "residential-berlin", "medical-us", owner_only=True)
    pids = [v for k, v in estate.items() if k != "manager"]
    with caplog.at_level(logging.INFO):
        cast = await demo_enrichment._demo_cast(factory)
        seeded = await demo_enrichment._seed_governance(factory, pids)
    assert cast == {"present": [], "created": ["decider", "cost"], "blocked": [], "ok": True}
    assert seeded["fallbacks"] == []
    assert seeded["ok"] is True
    assert _told(seeded, estate) == {
        "office-london": ("first_gate", "first_gate", None),
        "residential-berlin": ("execution", "execution", None),
        "medical-us": ("near_handover", "near_handover", None),
    }
    loud = [
        f"{r.name}: {r.getMessage()}"
        for r in caplog.records
        if r.levelno >= logging.WARNING and r.name.startswith(("app.modules.project_governance", "app.core.demo"))
    ]
    assert loud == []

    users = await _users(factory)
    stand_ins = {u.email: u for u in users.values() if (u.metadata_ or {}).get(demo_cast.CAST_TAG)}
    assert set(stand_ins) == {"demo-decider@example.com", "demo-cost-owner@example.com"}
    # No stand-in is a login of the passwordless demo sign-in, and none can receive mail.
    assert not set(stand_ins) & DEMO_ACCOUNT_EMAILS
    assert all(is_reserved_mail_domain(email) for email in stand_ins)
    # The installation still reads as one nobody has taken over: the next person to
    # register is the first real one, and is handed admin.
    from app.modules.users.repository import UserRepository

    async with factory() as s:
        users_repo = UserRepository(s)
        assert await users_repo.has_real_user() is False
        assert await users_repo.has_real_active_user() is False
    decisions = await _decisions(factory, estate["residential-berlin"])
    assert decisions and {d.decided_by for d in decisions} == {stand_ins["demo-decider@example.com"].id}
    assert estate["manager"] not in {d.decided_by for d in decisions}  # the owner decided nothing


async def test_the_cast_is_the_demo_logins_where_the_installation_has_them(factory) -> None:
    estate = await _estate(factory, "medical-us")
    cast = await demo_enrichment._demo_cast(factory)
    assert cast == {"present": ["decider", "cost"], "created": [], "blocked": [], "ok": True}
    assert set(await _users(factory)) == {DEMO, ESTIMATOR, MANAGER}
    async with factory() as s:
        assert (await demo_cast.find_cast(s))["decider"] == estate["manager"]


async def test_filling_the_cast_twice_creates_nobody_twice(factory) -> None:
    await _estate(factory, "office-london", owner_only=True)
    first = await demo_enrichment._demo_cast(factory)
    before = set(await _users(factory))
    second = await demo_enrichment._demo_cast(factory)
    assert first["created"] == ["decider", "cost"]
    assert second == {"present": ["decider", "cost"], "created": [], "blocked": [], "ok": True}
    assert set(await _users(factory)) == before


async def test_an_address_that_belongs_to_somebody_is_not_taken_over(factory) -> None:
    from app.modules.users.models import User

    estate = await _estate(factory, "medical-us", owner_only=True)
    real = uuid.uuid4()
    async with factory() as s:
        s.add(
            User(
                id=real,
                email="demo-decider@example.com",
                hashed_password="x",
                full_name="Somebody",
                role="viewer",
                locale="en",
                is_active=True,
                metadata_={},
            )
        )
        await s.commit()
    cast = await demo_enrichment._demo_cast(factory)
    assert (cast["blocked"], cast["created"], cast["ok"]) == (["decider"], ["cost"], False)
    users = await _users(factory)
    assert (users["demo-decider@example.com"].role, users["demo-decider@example.com"].full_name) == (
        "viewer",
        "Somebody",
    )
    result = await _seed(factory, estate)
    assert _told(result, estate) == {"medical-us": ("near_handover", None, "no_decider")}


async def test_the_stand_ins_leave_with_the_last_demo_project_and_not_before(factory) -> None:
    from app.config import get_settings
    from app.modules.projects.models import Project
    from app.modules.projects.service import ProjectService

    estate = await _estate(factory, "office-london", owner_only=True)
    await demo_enrichment._demo_cast(factory)
    await demo_enrichment._seed_governance(factory, [estate["office-london"]])
    async with factory() as s:
        assert await demo_cast.remove_demo_cast(s) == 0  # a demo project still names them
        await s.commit()
    assert len(await _users(factory)) == 3

    async with factory() as s:
        assert await ProjectService(s, get_settings()).purge_demo_projects() == 1
        await s.commit()
    async with factory() as s:
        assert (await s.execute(select(Project))).scalars().all() == []
    assert set(await _users(factory)) == {DEMO}


async def test_a_second_run_skips_what_the_first_one_seeded_and_reports_no_fallback(factory) -> None:
    estate = await _estate(factory, "medical-us")
    assert (await _seed(factory, estate))["ok"] is True
    again = await _seed(factory, estate)
    assert again["projects"] == 0
    assert [(r["planned"], r["reached"], r["skipped"]) for r in again["placements"]] == [("near_handover", None, True)]
    assert (again["fallbacks"], again["ok"]) == ([], True)


# ── after the module seeders ──


async def test_conditions_of_the_walk_are_cleared_once_the_module_answers_met(factory) -> None:
    answer = {"state": "not_met"}

    async def _module(session, project_id, attempt, area):
        if area.code != "procurement":
            return []
        return [evd.EvidenceItem(code="packages_planned", state=answer["state"])]

    evd.register_evidence_provider("*", _module, name="probe_module", blocking=True)
    estate = await _estate(factory, "residential-berlin", "office-london")
    await _seed(factory, estate)
    pid = estate["residential-berlin"]

    async def _conditions(project: uuid.UUID) -> list[GovernanceCondition]:
        async with factory() as s:
            rows = await s.execute(select(GovernanceCondition).where(GovernanceCondition.project_id == project))
            return list(rows.scalars())

    async def _settle() -> dict[str, int]:
        async with factory() as s:
            out = await seed.settle_demo_conditions(s)
            await s.commit()
        return out

    at_risk = [c for c in await _conditions(pid) if c.text == seed.AT_RISK_CONDITION]
    assert len(at_risk) == 8 and {c.status for c in at_risk} == {"open"}
    # The first-gate story of the other project passed its gate at risk too, next to its own two conditions.
    london = await _conditions(estate["office-london"])
    own = sorted((c.text, c.status) for c in london if c.text != seed.AT_RISK_CONDITION)
    assert len(own) == 2 and len(london) == 3

    # The module has no rows yet: nothing is cleared.
    assert await _settle() == {"cleared": 0, "left_open": 9}
    assert {c.status for c in await _conditions(pid)} == {"open"}

    answer["state"] = "met"
    assert await _settle() == {"cleared": 9, "left_open": 0}
    after = [c for c in await _conditions(pid) if c.text == seed.AT_RISK_CONDITION]
    assert {c.status for c in after} == {"cleared"}
    # Cleared by the owner of the condition, who is the owner of the area, with a reason.
    assert all(c.cleared_by == c.owner_user_id and c.evidence.strip() for c in after)
    assert estate["manager"] not in {c.cleared_by for c in after}
    # Conditions the walk did not create are not this step's to touch.
    london = await _conditions(estate["office-london"])
    assert sorted((c.text, c.status) for c in london if c.text != seed.AT_RISK_CONDITION) == own
    assert await _settle() == {"cleared": 0, "left_open": 0}


# ── events and savepoints ──


async def test_pin_of_current_core_behaviour_a_rolled_back_savepoint_still_fires_its_deferred_events(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pin of what ``app.core.events.publish_after_commit`` does today. It is a defect, not a contract.

    An event deferred inside a savepoint fires on the outer commit although the
    savepoint was rolled back and its rows are gone. Governance works around it
    for its own events (the outbox in ``seed._attempt``); events of the other
    services a story calls are still exposed.

    Whoever fixes the core: this test fails on your change, as it should. Flip
    the last assertion to ``not in`` and remove the outbox from the seed.
    """
    from sqlalchemy import text

    from app.core.events import event_bus, publish_after_commit

    fired: list[str] = []
    monkeypatch.setattr(event_bus, "publish_detached", lambda name, data=None, **kw: fired.append(name))
    async with factory() as s:
        await s.execute(text("SELECT 1"))
        try:
            async with s.begin_nested():
                publish_after_commit(s, "project_governance.probe.rolled_back", {})
                raise RuntimeError("the story failed")
        except RuntimeError:
            pass
        publish_after_commit(s, "project_governance.probe.kept", {})
        assert fired == []
        await s.commit()
    assert "project_governance.probe.kept" in fired
    assert "project_governance.probe.rolled_back" in fired


async def test_a_story_that_was_rolled_back_publishes_none_of_its_governance_events(
    factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.events import event_bus

    fired: list[tuple[str, dict]] = []
    monkeypatch.setattr(event_bus, "publish_detached", lambda name, data=None, **kw: fired.append((name, data or {})))

    async def _breaks(stage, *, near_handover: bool) -> None:
        await stage.open(
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            owner_of=lambda code: stage.cast.owner,
        )
        raise seed.SeedStop("gate_blocked", "a gate on the way is blocked")

    monkeypatch.setattr(seed, "_execution_story", _breaks)
    estate = await _estate(factory, "residential-berlin")
    assert (await _seed(factory, estate))["projects"] == 1

    pinned = [data for name, data in fired if name == "project_governance.model.set"]
    # Two stories pinned a model, one of them was rolled back. One event.
    assert len(pinned) == 1
    assert pinned[0]["project_id"] == str(estate["residential-berlin"])
