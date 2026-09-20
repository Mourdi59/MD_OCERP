# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Backfilling a healed column is half the repair; the column itself must move.

``oe_funding_obligation.detail_params`` arrives in two different shapes. An
installation that takes the migration gets it from ``add_column`` with
``nullable=False`` and a default. An installation whose tables came from
``Base.metadata.create_all`` plus the boot heal gets it from the heal, which
renders a column default into DDL only when the default has a literal
spelling. ``default=dict`` is a callable and has none, so there the column
lands nullable with no default.

The migration used to answer only half of that. It backfilled the NULL rows,
which is what the reading code needs, and left the column declaration alone,
which is what ``/api/health`` reads. So a healed installation went on
reporting ``schema_matches_models=false`` for its whole life over a column
whose rows were by then all populated. That is a standing false alarm, and the
cost of one is that it teaches an operator to read a degraded status as
normal, which is exactly how a real drift later goes unnoticed.

These tests run ``upgrade()`` against a recording double, because the point
being pinned is which statements are emitted on which path, and that is
decided before any database sees them. Three scenarios, and the value is in
the pair rather than in any one of them: the healed path proves the tightening
is not trapped inside the ``if`` that path skips, and the migration path
proves it was not written for the healed path alone. A change that satisfies
either one by itself fails the other.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

_MIGRATION = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "v41_funding_obligation_detail.py"
_TABLE = "oe_funding_obligation"
_PARAMS_COLUMN = "detail_params"
_KEY_COLUMN = "detail_key"


def _load() -> ModuleType:
    """Import the revision by path; ``alembic/versions`` is not a package."""
    spec = importlib.util.spec_from_file_location("v41_funding_obligation_detail", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingOp:
    """Stands in for ``alembic.op`` and remembers the order of what it is told."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.added: dict[str, sa.Column[Any]] = {}

    def get_bind(self) -> object:
        return object()

    def add_column(self, table: str, column: sa.Column[Any]) -> None:
        self.added[column.name] = column
        self.calls.append(("add_column", f"{table}.{column.name}"))

    def execute(self, statement: object) -> None:
        self.calls.append(("execute", str(statement)))

    def drop_column(self, table: str, column: str) -> None:  # pragma: no cover - downgrade only
        self.calls.append(("drop_column", f"{table}.{column}"))

    def sql(self) -> list[str]:
        return [payload for kind, payload in self.calls if kind == "execute"]


def _run(monkeypatch: pytest.MonkeyPatch, *, tables: list[str], columns: list[str]) -> _RecordingOp:
    """Run ``upgrade()`` over a database described by its catalog alone."""
    module = _load()
    recorder = _RecordingOp()

    inspector = SimpleNamespace(
        get_table_names=lambda: tables,
        get_columns=lambda table: [{"name": name} for name in columns],
    )
    # Only the name inside the revision is rebound, not sqlalchemy itself, so
    # a fake inspector cannot leak into anything else the suite imports.
    fake_sa = SimpleNamespace(
        inspect=lambda bind: inspector,
        Column=sa.Column,
        String=sa.String,
        JSON=sa.JSON,
        text=sa.text,
    )
    monkeypatch.setattr(module, "op", recorder)
    monkeypatch.setattr(module, "sa", fake_sa)

    module.upgrade()
    return recorder


def _tightening(recorder: _RecordingOp) -> list[str]:
    upper = [statement.upper() for statement in recorder.sql()]
    return [s for s in upper if "ALTER COLUMN" in s and "SET NOT NULL" in s and _PARAMS_COLUMN.upper() in s]


def _backfill_index(recorder: _RecordingOp) -> int:
    for index, statement in enumerate(recorder.sql()):
        if statement.upper().startswith("UPDATE") and "IS NULL" in statement.upper():
            return index
    return -1


def test_the_healed_path_tightens_the_column_it_backfills(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both columns already exist, so every ``add_column`` guard is skipped.

    This is the shape a boot-healed database is in, and it is the one the
    repair has to reach. If the tightening is written inside either guard it
    disappears here, which is how the column stayed nullable forever.
    """
    recorder = _run(monkeypatch, tables=[_TABLE], columns=["id", _KEY_COLUMN, _PARAMS_COLUMN])

    assert recorder.added == {}, "a column that already exists must not be added again"
    assert _tightening(recorder), "a healed database must have its nullable column tightened, not only backfilled"


def test_the_tightening_follows_the_backfill_and_never_precedes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Order is the safety property, not a detail of style.

    ``SET NOT NULL`` scans the table and refuses if a single NULL is left, so
    tightening before the backfill would abort the upgrade on precisely the
    databases the revision exists to repair, and only on those. It would pass
    every test written against an empty table.
    """
    recorder = _run(monkeypatch, tables=[_TABLE], columns=["id", _KEY_COLUMN, _PARAMS_COLUMN])

    backfill = _backfill_index(recorder)
    assert backfill >= 0, "the revision must still backfill the NULL rows"

    statements = [s.upper() for s in recorder.sql()]
    tightened = [i for i, s in enumerate(statements) if "SET NOT NULL" in s]
    assert tightened, "nothing tightened the column"
    assert min(tightened) > backfill, "the column is tightened before the NULLs are removed, which aborts the upgrade"


def test_the_migration_path_gets_the_same_shape_as_the_healed_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither column exists yet, so both are added by the revision itself.

    The tightening is a no-op here, and it is still asserted. Writing it under
    a second guard would leave two code paths whose agreement nothing checks,
    and the whole defect being fixed is two paths that were assumed to agree.
    """
    recorder = _run(monkeypatch, tables=[_TABLE], columns=["id"])

    assert set(recorder.added) == {_KEY_COLUMN, _PARAMS_COLUMN}
    params = recorder.added[_PARAMS_COLUMN]
    assert params.nullable is False, "the freshly added column must arrive NOT NULL"
    assert params.server_default is not None, "the freshly added column must arrive with a default"
    assert _tightening(recorder), "the tightening must be unconditional, not written for the healed path alone"


def test_a_database_without_the_table_is_left_untouched(monkeypatch: pytest.MonkeyPatch) -> None:
    """A deployment that does not carry this module must not be altered.

    The early return is what keeps the revision from stopping an upgrade on an
    installation the funding module was never enabled on, and an unconditional
    ALTER placed above it would undo that.
    """
    recorder = _run(monkeypatch, tables=["oe_project"], columns=[])

    assert recorder.calls == []
