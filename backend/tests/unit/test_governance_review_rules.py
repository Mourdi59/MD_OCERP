# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Rules that guard who may move a gate or a condition, and when.

Each rule is pure and sits next to the case that must fail without it: a gate
that is un-decided by a plain "prepare", a reopen that would leave a later gate
ahead of the phase, a waiver by somebody the route never named.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.modules.project_governance import evaluator as ev
from app.modules.project_governance import router as gov_router
from app.modules.project_governance.errors import GovernanceError
from app.modules.project_governance.evaluator import AreaState

ACTOR = "actor"
OTHER = "somebody-else"


# ── preparing and resuming a gate ──


@pytest.mark.parametrize("status", ["in_preparation", "in_review", "on_hold", "decided"])
def test_only_a_gate_not_yet_started_can_be_prepared(status: str) -> None:
    assert ev.preparation_violation(status, historic=False, model_stopped=False) == "invalid_transition"


def test_preparing_a_fresh_gate_is_allowed_unless_historic_or_stopped() -> None:
    assert ev.preparation_violation("not_started", historic=False, model_stopped=False) is None
    assert ev.preparation_violation("not_started", historic=True, model_stopped=False) == "gate_historic"
    assert ev.preparation_violation("not_started", historic=False, model_stopped=True) == "project_stopped"


@pytest.mark.parametrize("status", ["not_started", "in_preparation", "in_review", "decided"])
def test_only_a_held_gate_can_be_resumed(status: str) -> None:
    assert ev.resume_violation(status, historic=False, model_stopped=False) == "gate_not_on_hold"


def test_resuming_a_held_gate_is_allowed_unless_historic_or_stopped() -> None:
    assert ev.resume_violation("on_hold", historic=False, model_stopped=False) is None
    assert ev.resume_violation("on_hold", historic=True, model_stopped=False) == "gate_historic"
    assert ev.resume_violation("on_hold", historic=False, model_stopped=True) == "project_stopped"


# ── reopening ──


def test_a_historic_gate_is_never_reopened() -> None:
    assert ev.reopen_violation("decided", "Cost overrun", historic=True) == "gate_historic"


@pytest.mark.parametrize("later", ["in_preparation", "in_review", "on_hold", "decided"])
def test_a_gate_is_not_reopened_while_a_later_gate_was_started(later: str) -> None:
    assert ev.reopen_violation("decided", "Cost overrun", later_gate_statuses=["not_started", later]) == (
        "later_gate_active"
    )


def test_a_gate_is_reopened_when_every_later_gate_is_untouched() -> None:
    assert ev.reopen_violation("decided", "Cost overrun", later_gate_statuses=["not_started", "not_started"]) is None


@pytest.mark.parametrize(
    ("outcome", "rewinds"),
    [("go", True), ("go_with_conditions", True), ("stop", False), ("hold", False), ("recycle", False)],
)
def test_reopening_rewinds_the_phase_exactly_when_the_decision_advanced_it(outcome: str, rewinds: bool) -> None:
    assert ev.reopen_rewinds_phase(outcome) is rewinds
    assert ev.decision_effects(outcome).advance_phase is rewinds


# ── authority over a decision that was already taken ──


def test_the_decider_of_the_decision_has_authority() -> None:
    assert ev.authority_violation(ACTOR, decided_by=ACTOR, route_entitled=False) is None


def test_a_user_the_gate_route_entitles_has_authority() -> None:
    assert ev.authority_violation(ACTOR, decided_by=OTHER, route_entitled=True) is None


def test_any_other_holder_of_the_decide_permission_has_none() -> None:
    assert ev.authority_violation(ACTOR, decided_by=OTHER, route_entitled=False) == "decider_not_entitled"
    assert ev.authority_violation(ACTOR, decided_by=None, route_entitled=False) == "decider_not_entitled"


# ── conditions ──


def test_clearing_is_for_the_condition_owner_or_a_manager() -> None:
    assert ev.condition_clear_violation("open", ACTOR, actor_id=ACTOR, is_manager=False) is None
    assert ev.condition_clear_violation("overdue", OTHER, actor_id=ACTOR, is_manager=True) is None
    assert ev.condition_clear_violation("open", OTHER, actor_id=ACTOR, is_manager=False) == "not_condition_owner"
    assert ev.condition_clear_violation("open", None, actor_id=ACTOR, is_manager=False) == "not_condition_owner"


@pytest.mark.parametrize("status", ["cleared", "waived"])
def test_a_closed_condition_is_neither_cleared_nor_waived(status: str) -> None:
    assert ev.condition_clear_violation(status, ACTOR, actor_id=ACTOR, is_manager=True) == "condition_not_open"
    assert (
        ev.condition_waive_violation(
            status, actor_id=ACTOR, decided_by=ACTOR, route_entitled=True, four_eyes=False, areas=(), area_code=None
        )
        == "condition_not_open"
    )


def _waive(**kw) -> str | None:
    base = dict(
        actor_id=ACTOR,
        decided_by=ACTOR,
        route_entitled=False,
        four_eyes=True,
        areas=(AreaState("A", "owner-a"), AreaState("B", "owner-b", deputy_user_id="deputy-b")),
        area_code="A",
    )
    base.update(kw)
    return ev.condition_waive_violation("open", **base)


def test_a_waiver_needs_authority_over_the_decision() -> None:
    assert _waive() is None
    assert _waive(decided_by=OTHER, route_entitled=True) is None
    assert _waive(decided_by=OTHER) == "decider_not_entitled"


def test_under_four_eyes_the_owner_of_the_conditions_area_may_not_waive_it() -> None:
    assert _waive(actor_id="owner-a", decided_by="owner-a") == "decider_is_area_owner"
    # The owner of another area is not judging their own work.
    assert _waive(actor_id="owner-b", decided_by="owner-b") is None
    assert _waive(actor_id="deputy-b", decided_by="deputy-b", area_code="B") == "decider_is_area_owner"
    # A condition on no area concerns every area.
    assert _waive(actor_id="owner-b", decided_by="owner-b", area_code=None) == "decider_is_area_owner"
    assert _waive(actor_id="owner-a", decided_by="owner-a", four_eyes=False) is None


# ── proceed at risk ──


def test_only_readiness_gaps_are_liftable_by_proceeding_at_risk() -> None:
    assert frozenset({"area_not_ready", "evidence_not_met"}) == ev.PROCEED_AT_RISK_LIFTABLE
    assert "check_stale" not in ev.PROCEED_AT_RISK_LIFTABLE


# ── stop ──


def test_a_stop_freezes_binding_documents_too() -> None:
    def doc(doc_id: str, status: str, *, read_only: bool = False) -> ev.DocumentState:
        return ev.DocumentState(
            id=doc_id,
            area_code="A",
            doc_type=doc_id,
            required=True,
            status=status,
            container_id="c1",
            current_revision_id="rev-1",
            read_only=read_only,
        )

    docs = (
        doc("draft", "draft"),
        doc("binding", "binding"),
        doc("superseded", "superseded"),
        doc("frozen", "draft", read_only=True),
    )
    assert ev.documents_to_freeze(docs) == ("draft", "binding")


# ── router: the server date is the only date on a write ──


def _handlers() -> dict[str, ast.AsyncFunctionDef]:
    tree = ast.parse(Path(inspect.getfile(gov_router)).read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.decorator_list}


def test_no_write_route_takes_a_date_from_the_client() -> None:
    writes = [r for r in gov_router.router.routes if set(r.methods) & {"POST", "PUT", "PATCH", "DELETE"}]
    assert len(writes) >= 20
    offenders = [r.name for r in writes if "today" in inspect.signature(r.endpoint).parameters]
    assert offenders == []


def test_the_caller_capabilities_of_a_gate_use_the_server_date() -> None:
    """``can`` must agree with what the decide endpoint does, and that one ignores ``?today=``."""
    handler = _handlers()["get_gate"]
    calls = [
        n
        for n in ast.walk(handler)
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in {"decide_capability", "gate_capability"}
    ]
    assert calls, "get_gate no longer asks for capabilities"
    for call in calls:
        for kw in call.keywords:
            if kw.arg == "today":
                assert "today" not in {n.id for n in ast.walk(kw.value) if isinstance(n, ast.Name)}


# ── no role strings in the service ──


def test_the_service_never_compares_a_role_string() -> None:
    import app.modules.project_governance.service as service

    source = Path(inspect.getfile(service)).read_text(encoding="utf-8")
    assert "_MANAGER_ROLES" not in source
    tree = ast.parse(source)
    literals = {
        c.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        for c in ast.walk(n)
        if isinstance(c, ast.Constant) and isinstance(c.value, str)
    }
    assert literals & {"admin", "manager", "owner", "superuser"} == set()


def test_reopen_resume_waive_and_add_condition_pass_the_callers_role_to_the_route_check() -> None:
    """Their authority is the route's, so each handler has to hand the service the caller's role."""
    handlers = _handlers()
    for name in ("reopen_gate", "resume_gate", "waive_condition", "add_condition"):
        kws = {kw.arg for n in ast.walk(handlers[name]) if isinstance(n, ast.Call) for kw in n.keywords}
        assert "role" in kws, name


# ── a bad clone source is a 404, not a crash ──


class _NoCatalogues:
    async def list_tenant_catalogues(self, *_a, **_k):
        return []

    async def get_tenant_catalogue(self, *_a, **_k):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize("based_on_id", ["not-a-uuid", None, ""])
async def test_cloning_a_tenant_catalogue_by_a_bad_id_answers_unknown_catalogue(based_on_id: str | None) -> None:
    from app.modules.project_governance.catalogue_store import CatalogueStore

    store = CatalogueStore.__new__(CatalogueStore)
    store.session = None
    store.repo = _NoCatalogues()
    with pytest.raises(GovernanceError) as exc:
        await store.create(
            "tenant-1",
            code="mine",
            name="Mine",
            based_on_source="tenant",
            based_on_id=based_on_id,
            based_on_version=None,
            actor_id=None,
        )
    assert exc.value.code == "unknown_catalogue" and exc.value.status_code == 404


# ── indexes the hot reads need ──


def test_checks_and_conditions_are_indexed_for_their_readers() -> None:
    from app.modules.project_governance.models import GovernanceCheck, GovernanceCondition

    def columns(model) -> set[tuple[str, ...]]:
        return {tuple(c.name for c in ix.columns) for ix in model.__table__.indexes}

    assert ("project_id",) in columns(GovernanceCheck)
    assert ("decision_id",) in columns(GovernanceCondition)


def test_the_migration_declares_the_same_indexes_as_the_models() -> None:
    import importlib.util

    import app.modules.project_governance.models as models

    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "v68_project_governance.py"
    spec = importlib.util.spec_from_file_location("v68_project_governance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    declared = {(table, name, tuple(cols)) for table, _c, indexes in module._TABLES for name, cols in indexes}
    in_models = {
        (t.name, ix.name, tuple(c.name for c in ix.columns))
        for t in models.Base.metadata.tables.values()
        if t.name.startswith("oe_governance_")
        for ix in t.indexes
    }
    assert declared == in_models
