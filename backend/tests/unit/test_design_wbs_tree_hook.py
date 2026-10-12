# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""WBS rules on writes made outside the design module: the pure tree check and the core hook.

The copy, restore and projects-router paths against a database are in
``tests/pg/test_design_wbs_paths_on_pg.py``.
"""

from __future__ import annotations

import ast
import asyncio
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core import wbs_rules
from app.modules.design_management import wbs as wr

_PROJECTS = Path(__file__).resolve().parents[2] / "app" / "modules" / "projects"


def _n(code: str, parent: wr.Node | None = None, closed: bool = False) -> wr.Node:
    return wr.Node(uuid.uuid4(), parent.id if parent else None, code, closed)


def test_a_clean_tree_has_no_errors() -> None:
    root = _n("1")
    assert wr.tree_errors([root, _n("1.1", root), _n("1.2", root)]) == []


def test_duplicate_codes_are_found_case_insensitively() -> None:
    errors = wr.tree_errors([_n("A1"), _n("a1")], hierarchical=False)
    assert [e["code"] for e in errors] == ["wbs_code_duplicate"]


def test_a_child_outside_its_parent_prefix_fails_only_when_hierarchical() -> None:
    root = _n("1")
    nodes = [root, _n("2.1", root)]
    assert [e["code"] for e in wr.tree_errors(nodes, hierarchical=True)] == ["wbs_code_not_under_parent"]
    assert wr.tree_errors(nodes, hierarchical=False) == []
    assert wr.tree_errors([root, _n("1/1", root)], hierarchical=True, separator="/") == []


def test_an_open_child_under_a_closed_node_fails_and_a_closed_subtree_passes() -> None:
    root = _n("1", closed=True)
    assert [e["code"] for e in wr.tree_errors([root, _n("1.1", root)])] == ["wbs_node_closed"]
    assert wr.tree_errors([root, _n("1.1", root, closed=True)]) == []


def test_an_empty_code_fails() -> None:
    assert [e["code"] for e in wr.tree_errors([_n(" ")])] == ["wbs_code_required"]


def test_the_hook_is_a_no_op_without_checkers_and_raises_422_with_every_violation() -> None:
    pid = uuid.uuid4()
    seen: list[tuple] = []

    async def checker(session, project_id, settings_project_id):
        seen.append((project_id, settings_project_id))
        return [{"code": "wbs_code_duplicate", "value": "1"}, {"code": "wbs_node_closed", "value": "2"}]

    saved = dict(wbs_rules._CHECKERS)
    wbs_rules._CHECKERS.clear()
    try:
        asyncio.run(wbs_rules.check_wbs_tree(None, pid))
        wbs_rules.register_wbs_checker("t", checker)
        src = uuid.uuid4()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(wbs_rules.check_wbs_tree(None, pid, settings_project_id=src))
    finally:
        wbs_rules._CHECKERS.clear()
        wbs_rules._CHECKERS.update(saved)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "wbs_invalid"
    assert len(exc.value.detail["violations"]) == 2
    assert seen == [(pid, src)]


def test_design_startup_registers_the_wbs_checker() -> None:
    from app.modules.design_management import on_startup

    asyncio.run(on_startup())
    assert "design_management.wbs" in wbs_rules._CHECKERS


@pytest.mark.parametrize(
    ("file", "function"),
    [
        ("router.py", "create_wbs_node"),
        ("router.py", "update_wbs_node"),
        ("service.py", "duplicate_project"),
        ("service.py", "restore_project_from_backup"),
    ],
)
def test_every_projects_wbs_write_path_calls_the_hook(file: str, function: str) -> None:
    tree = ast.parse((_PROJECTS / file).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == function)
    called = {
        n.value.func.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
    }
    assert "check_wbs_tree" in called, function
