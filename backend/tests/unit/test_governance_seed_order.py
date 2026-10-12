"""The governance demo seed pins the phase model before any module seeder runs.

The seed skips a project that already has a model. A module seeder that ran
first and pinned one would leave the demo project without area owners, gates
and decisions, so the order is part of the contract.
"""

from __future__ import annotations

import ast
import inspect

from app.core import demo_enrichment


def _line_of(tree: ast.AST, predicate) -> int:
    lines = [node.lineno for node in ast.walk(tree) if predicate(node)]
    assert len(lines) == 1, lines
    return lines[0]


def test_governance_is_seeded_before_the_module_seeders() -> None:
    tree = ast.parse(inspect.getsource(demo_enrichment))
    governance = _line_of(
        tree,
        lambda n: (
            isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "seed_project_governance_demo"
        ),
    )
    module_loop = _line_of(
        tree,
        lambda n: isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "_module_seeders",
    )
    assert governance < module_loop


def test_conditions_are_settled_after_the_module_seeders() -> None:
    """Settling asks the module providers again, so it is worth nothing before they have rows."""
    tree = ast.parse(inspect.getsource(demo_enrichment))
    settle = _line_of(
        tree,
        lambda n: isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "settle_demo_conditions",
    )
    module_loop = _line_of(
        tree,
        lambda n: isinstance(n, ast.For) and isinstance(n.iter, ast.Name) and n.iter.id == "_module_seeders",
    )
    assert settle > module_loop
