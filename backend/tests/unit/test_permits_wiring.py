# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits module wiring: router guards, approval kind, messages, model/migration parity, rule set."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import re
import typing
from datetime import date
from pathlib import Path

import pytest

from app.modules.permits import router as permits_router
from app.modules.permits.messages import is_key_present

MODULE_DIR = Path(permits_router.__file__).parent
MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "v73_permits.py"


def test_every_project_handler_verifies_access() -> None:
    """Rule 24: a project-scoped handler reaches ``verify_project_access`` (directly or through ``_svc``)."""
    for route in permits_router.router.routes:
        if "{project_id}" not in route.path:
            continue
        src = inspect.getsource(route.endpoint)
        if "_ongoing(" in src:
            src += inspect.getsource(permits_router._ongoing)
        assert "_svc(" in src or "verify_project_access" in src, route.path
    assert "verify_project_access" in inspect.getsource(permits_router._svc)


def test_decisions_need_manage_and_discharge_needs_verify() -> None:
    perms = {}
    for route in permits_router.router.routes:
        deps = [d.dependency for d in route.dependencies]
        perms[(route.path, tuple(route.methods))] = {getattr(d, "permission", None) for d in deps}
    decision = next(v for (p, _m), v in perms.items() if p.endswith("/decision"))
    assert decision == {"permits.manage"}
    discharge = next(v for (p, _m), v in perms.items() if p.endswith("/discharge"))
    assert discharge == {"permits.verify"}
    # Reading the notice with the AI writes proposals: it is an editor's action and takes no body.
    extract = next(r for r in permits_router.router.routes if r.path.endswith("/condition-proposals/extract"))
    assert {getattr(d.dependency, "permission", None) for d in extract.dependencies} == {"permits.edit"}
    assert set(inspect.signature(extract.endpoint).parameters) == {"project_id", "permit_id", "session", "user_id"}


def test_every_record_read_is_served_with_what_the_caller_may_do() -> None:
    """A button follows the server: each read of a record a user acts on builds its ``can`` from the caller."""
    reads = {
        "/projects/{project_id}/roadmap",
        "/projects/{project_id}/requirements",
        "/projects/{project_id}/applications",
        "/projects/{project_id}/applications/{application_id}",
        "/projects/{project_id}/permits",
        "/projects/{project_id}/conditions",
        "/projects/{project_id}/conditions/{condition_id}",
    }
    seen = set()
    for route in permits_router.router.routes:
        if "GET" in route.methods and route.path.removeprefix(permits_router.router.prefix) in reads:
            assert "_caller(payload, user_id)" in inspect.getsource(route.endpoint), route.path
            seen.add(route.path.removeprefix(permits_router.router.prefix))
    assert seen == reads
    # Nothing but the guards decides a flag: the service builds every one through ``guards``.
    from app.modules.permits.service import PermitService

    for name in ("roadmap_can", "requirement_can", "application_can", "decision_can", "permit_can", "condition_can"):
        assert "guards.flag(" in inspect.getsource(getattr(PermitService, name)), name


def test_approval_target_kind_registered_in_model_and_schema() -> None:
    from app.modules.approval_routes.models import TARGET_KINDS
    from app.modules.approval_routes.schemas import TargetKindLiteral

    assert "permit_application" in TARGET_KINDS
    assert "permit_application" in typing.get_args(TargetKindLiteral)


def test_every_error_code_has_an_english_and_german_message() -> None:
    codes: set[str] = set()
    for path in MODULE_DIR.glob("*.py"):
        codes |= set(
            re.findall(
                r'(?:PermitError|not_found|conflict|forbidden|not_applicable|refused|ClockError)\(\s*"([a-z_]+)"',
                path.read_text("utf-8"),
            )
        )
    assert len(codes) > 50
    for code in codes:
        for loc in ("en", "de"):
            assert is_key_present(f"permits.errors.{code}", loc), (code, loc)


def test_every_rule_has_messages() -> None:
    from app.modules.permits.validators import PERMIT_RULES

    for rule in PERMIT_RULES:
        for loc in ("en", "de"):
            assert is_key_present(f"permits.rules.{rule.key}.fail", loc), rule.key
            assert is_key_present(f"permits.rules.{rule.key}.suggestion", loc), rule.key


def _model_names() -> dict[str, set[str]]:
    from app.modules.permits import models

    out: dict[str, set[str]] = {}
    for obj in vars(models).values():
        table = getattr(obj, "__table__", None)
        if table is None or not table.name.startswith("oe_permits_"):
            continue
        names = {ix.name for ix in table.indexes} | {c.name for c in table.constraints if c.name}
        names |= {fk.name for c in table.columns for fk in c.foreign_keys if fk.name}
        out[table.name] = {n for n in names if n and not n.startswith("pk_")}
        out[table.name + ":columns"] = {c.name for c in table.columns}
    return out


def test_migration_matches_models() -> None:
    """Index, constraint and column names are the same strings in model and migration."""
    spec = importlib.util.spec_from_file_location("v73_permits", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "v73_permits" and mod.down_revision == "v68_project_governance"
    models = _model_names()
    tables = {t for t in models if ":" not in t}
    assert {t for t, _c, _i in mod._TABLES} == tables
    for table, columns, indexes in mod._TABLES:
        cols = columns()
        names = {n for n, _ in indexes}
        col_names = {"id", "created_at", "updated_at"}
        for c in cols:
            if hasattr(c, "foreign_keys"):
                col_names.add(c.name)
                names |= {fk.name for fk in c.foreign_keys}
            elif getattr(c, "name", None):
                names.add(c.name)
        assert names == models[table], table
        assert col_names == models[table + ":columns"], table


def test_migration_is_inspector_guarded() -> None:
    tree = ast.parse(MIGRATION.read_text("utf-8"))
    src = ast.unparse(tree)
    assert "get_table_names()" in src and "get_indexes(table)" in src


@pytest.mark.asyncio
async def test_rule_set_runs_on_a_payload() -> None:
    from app.core.validation.engine import ValidationContext
    from app.modules.permits.validators import PERMIT_RULES

    payload = {
        "today": date(2026, 10, 11).isoformat(),
        "catalogue": None,
        "requirements": [{"id": "r1", "permit_type_code": "x", "applicable": True, "applicant_role": "owner"}],
        "edges": [{"requirement": "a", "depends_on": "b", "on": "granted"}, {"requirement": "b", "depends_on": "a"}],
        "timeline": [],
        "applications": [],
        "decisions": [],
        "permits": [],
        "conditions": [
            {
                "id": "c1",
                "number": "1",
                "permit_id": "p",
                "confirmed": True,
                "state": "open",
                "kind": "suspensive",
                "trigger": "before_start",
                "owner_user_id": None,
                "overdue": False,
            },
        ],
        "discharges": [],
    }
    ctx = ValidationContext(data=payload, metadata={"locale": "de"})
    failed = set()
    for rule in PERMIT_RULES:
        for r in await rule().validate(ctx):
            if not r.passed:
                failed.add(r.rule_id)
                assert r.message and "permits.rules" not in r.message
    assert {
        "permits.requirement_has_applicant_and_owner",
        "permits.dependency_acyclic",
        "permits.condition_has_trigger_and_owner",
        "permits.suspensive_condition_blocks_start",
    } <= failed


def test_no_write_route_takes_a_date_from_the_client() -> None:
    """Review finding 5: only reads may be asked "as of"; a write happens on the server's date."""
    for route in permits_router.router.routes:
        if route.methods <= {"GET", "HEAD"}:
            continue
        assert "today" not in inspect.signature(route.endpoint).parameters, route.path


def test_the_service_is_told_what_the_caller_may_do_never_a_role() -> None:
    """Lead decision: permission checks live in the router and reach the service as booleans."""
    from app.modules.permits import service

    assert not re.search(r"\bactor_role\b|\brole: str", inspect.getsource(service.PermitService))
    assert not re.search(r"[\"'](admin|manager|editor|viewer)[\"']", inspect.getsource(service))
    assert "permission_registry.role_has_permission" in inspect.getsource(permits_router._can)


def test_the_sweep_is_a_registered_periodic_process() -> None:
    """Review finding 10, rule 17: escalation does not depend on somebody pressing a button."""
    from app.core.processes import builtin

    src = inspect.getsource(builtin.register_builtin_processes)
    assert '"permits_sweep"' in src and "permits_tick" in src
    assert "run_sweep_once" in inspect.getsource(builtin.permits_tick)
