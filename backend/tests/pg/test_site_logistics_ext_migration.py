# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Revision v78 builds exactly the schema the site-logistics models build, and undoes it.

Up, down, up on PostgreSQL for the fifteen new tables and the nullable columns
added to the gate, laydown zone and delivery tables. The reflected schema from
the revision must equal the one ``create_all`` produces (columns with types and
nullability, module indexes, unique constraints, foreign keys), so a fresh
install and an upgraded one cannot drift. Down must leave the three existing
tables exactly as they were before the extension.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests._pg import isolated_engine

pytestmark = pytest.mark.asyncio


def _load(name: str):
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_rev = _load("v78_site_logistics_ext")
NEW_TABLES = [t for t, _c, _i in _rev._TABLES]
EXTENDED = sorted({t for t, _c, _f, _i in _rev._EXTEND})
ADDED = {(t, c().name) for t, c, _f, _i in _rev._EXTEND}
ALL = NEW_TABLES + EXTENDED


def _run(sync_conn, direction) -> None:
    with Operations.context(MigrationContext.configure(sync_conn)):
        direction()


# ``app.core.pg_optimizations`` adds ``ix_<table>_<columns>`` on every create_all and no
# revision reproduces those. The module names its own indexes ``ix_oe_site_<short>``; the
# extension's two column indexes are compared by their exact names.
_EXTEND_INDEXES = {ix for _t, _c, _f, ix in _rev._EXTEND if ix}


def _ours(name: str | None) -> bool:
    if not name:
        return False
    return name in _EXTEND_INDEXES or (name.startswith("ix_oe_site_") and not name.startswith("ix_oe_site_logistics_"))


def _reflect(sync_conn) -> dict:
    inspector = sa.inspect(sync_conn)
    tables = set(inspector.get_table_names())
    out: dict = {"tables": tables}
    for table in ALL:
        if table not in tables:
            continue
        out[table] = {
            "columns": {c["name"]: (str(c["type"]), c["nullable"]) for c in inspector.get_columns(table)},
            "indexes": {i["name"] for i in inspector.get_indexes(table) if _ours(i.get("name"))},
            "unique": {u["name"] for u in inspector.get_unique_constraints(table) if u.get("name")},
            "fks": {(f["name"], (f.get("options") or {}).get("ondelete")) for f in inspector.get_foreign_keys(table)},
        }
    return out


async def test_revision_reproduces_the_model_schema_up_down_up() -> None:
    async with isolated_engine() as engine:
        async with engine.begin() as conn:
            from_models = await conn.run_sync(_reflect)
        assert set(ALL) <= from_models["tables"]
        async with engine.begin() as conn:
            await conn.run_sync(_run, _rev.downgrade)
            down = await conn.run_sync(_reflect)
        async with engine.begin() as conn:
            await conn.run_sync(_run, _rev.upgrade)
            first = await conn.run_sync(_reflect)
        async with engine.begin() as conn:
            await conn.run_sync(_run, _rev.downgrade)
            down_again = await conn.run_sync(_reflect)
        async with engine.begin() as conn:
            await conn.run_sync(_run, _rev.upgrade)
            second = await conn.run_sync(_reflect)

    for snapshot in (down, down_again):
        assert not set(NEW_TABLES) & snapshot["tables"]
        for table in EXTENDED:
            assert table in snapshot["tables"]
            left = {(table, c) for c in snapshot[table]["columns"]} & ADDED
            assert not left, left
    assert down == down_again
    for table in ALL:
        for key in ("columns", "indexes", "unique", "fks"):
            assert first[table][key] == from_models[table][key], (table, key)
            assert second[table][key] == from_models[table][key], (table, key)


async def test_revision_is_a_no_op_over_a_create_all_schema() -> None:
    async with isolated_engine() as engine:
        async with engine.begin() as conn:
            before = await conn.run_sync(_reflect)
            await conn.run_sync(_run, _rev.upgrade)
            after = await conn.run_sync(_reflect)
    for table in ALL:
        assert after[table] == before[table], table
