# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""PG: the last three currency revisions run against a schema that already has them.

The default runtime does not migrate its way to the current schema. ``env.py``
short-circuits a blank database to ``create_all`` plus ``stamp heads``, so the
tables are built from the models and the stamp is written afterwards. Every
install made that way has the current columns and a stamp that stops moving,
and the next release leaves it behind: the schema is right, the bookkeeping is
old, and ``alembic upgrade head`` is what an operator reaches for.

On such a database that command used to die. Twenty four of the twenty seven
revisions between v3273 and the head guard their DDL on an inspector and skip
what is already there; v3304, v3305 and v3306 did not, so the first of them
raised ``DuplicateColumn: column "currency" of relation
"oe_supplier_catalogs_stock_balance" already exists``, the transaction rolled
back, and the two revisions behind it never ran. The failure is not visible
from a fresh install, because a fresh install executes no revision at all, and
it is not visible from a chain test, because the chain is well formed. It is
only visible with a schema in front of it that already has the columns.

So that is what these build: each table in its post-migration shape, in a
schema of its own, with the revision's real ``upgrade()`` run over it. Each
test has a control on the other side, a table in the pre-migration shape, so a
guard that skipped everything unconditionally would fail here rather than pass
twice.

Gated by ``OE_TEST_DB=pg`` (see conftest).
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

_VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
_SCHEMA = "rerun_probe"

# Each case: the revision file, the table the guard protects, the column it
# adds, and the DDL for the table in each of the two shapes. "after" is what
# create_all leaves behind; "before" is what the revision was written for.
_CASES = {
    "v3305_crm_forecast_currency": {
        "table": "oe_crm_forecast",
        "column": "by_currency",
        "before": "CREATE TABLE oe_crm_forecast (id uuid PRIMARY KEY, period varchar(16))",
        "after": (
            "CREATE TABLE oe_crm_forecast ("
            "id uuid PRIMARY KEY, period varchar(16), by_currency json, mixed_currency boolean)"
        ),
    },
    "v3306_tolerance_profile_currency": {
        "table": "oe_supplier_catalogs_tolerance_profile",
        "column": "currency",
        "before": (
            "CREATE TABLE oe_supplier_catalogs_tolerance_profile ("
            "id uuid PRIMARY KEY, price_tolerance_abs numeric(18, 4) NOT NULL DEFAULT 0)"
        ),
        "after": (
            "CREATE TABLE oe_supplier_catalogs_tolerance_profile ("
            "id uuid PRIMARY KEY, price_tolerance_abs numeric(18, 4) NOT NULL DEFAULT 0, "
            "currency varchar(3))"
        ),
    },
}

# v3304 touches four tables and follows its DDL with a classification pass, so
# it gets its own fixtures rather than a row in the table above.
_V3304_BEFORE = """
CREATE TABLE oe_supplier_catalogs_po (id uuid PRIMARY KEY, currency varchar(10) NOT NULL DEFAULT 'EUR');
CREATE TABLE oe_supplier_catalogs_gr (id uuid PRIMARY KEY, po_id uuid NOT NULL);
CREATE TABLE oe_supplier_catalogs_stock_balance (
    id uuid PRIMARY KEY,
    warehouse_id uuid NOT NULL,
    catalog_item_id uuid NOT NULL,
    batch_lot varchar(100) NOT NULL DEFAULT '',
    quantity_on_hand numeric(18, 4) NOT NULL DEFAULT 0,
    unit_cost_avg numeric(18, 4) NOT NULL DEFAULT 0
);
CREATE TABLE oe_supplier_catalogs_stock_movement (
    id uuid PRIMARY KEY,
    warehouse_id uuid NOT NULL,
    catalog_item_id uuid NOT NULL,
    movement_type varchar(20) NOT NULL,
    quantity numeric(18, 4) NOT NULL DEFAULT 0,
    unit_cost numeric(18, 4) NOT NULL DEFAULT 0,
    reference_type varchar(32),
    reference_id varchar(36),
    batch_lot varchar(100)
);
"""

_V3304_AFTER = """
CREATE TABLE oe_supplier_catalogs_po (id uuid PRIMARY KEY, currency varchar(10) NOT NULL DEFAULT 'EUR');
CREATE TABLE oe_supplier_catalogs_gr (id uuid PRIMARY KEY, po_id uuid NOT NULL);
CREATE TABLE oe_supplier_catalogs_stock_balance (
    id uuid PRIMARY KEY,
    warehouse_id uuid NOT NULL,
    catalog_item_id uuid NOT NULL,
    batch_lot varchar(100) NOT NULL DEFAULT '',
    quantity_on_hand numeric(18, 4) NOT NULL DEFAULT 0,
    unit_cost_avg numeric(18, 4),
    currency varchar(10),
    cost_state varchar(16) NOT NULL DEFAULT 'unknown'
);
CREATE TABLE oe_supplier_catalogs_stock_movement (
    id uuid PRIMARY KEY,
    warehouse_id uuid NOT NULL,
    catalog_item_id uuid NOT NULL,
    movement_type varchar(20) NOT NULL,
    quantity numeric(18, 4) NOT NULL DEFAULT 0,
    unit_cost numeric(18, 4),
    reference_type varchar(32),
    reference_id varchar(36),
    batch_lot varchar(100),
    currency varchar(10)
);
"""


def _load(revision: str):
    """Import a revision by path; ``alembic/versions`` is not a package."""
    spec = importlib.util.spec_from_file_location(f"rerun_{revision}", _VERSIONS / f"{revision}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sync_engine(pg_async_url):
    url = make_url(pg_async_url).set(drivername="postgresql+psycopg2")
    engine = create_engine(url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def probe(sync_engine):
    """Build a private schema from DDL, and drop it however the test ends."""

    def _build(ddl: str) -> None:
        with sync_engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
            conn.execute(text(f"SET search_path TO {_SCHEMA}"))
            for statement in filter(None, (s.strip() for s in ddl.split(";"))):
                conn.execute(text(statement))
            conn.commit()

    try:
        yield _build
    finally:
        with sync_engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
            conn.commit()


def _run(engine, revision: str) -> None:
    module = _load(revision)
    with engine.connect() as conn:
        conn.execute(text(f"SET search_path TO {_SCHEMA}"))
        ctx = MigrationContext.configure(connection=conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()


def _columns(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = :t"),
            {"s": _SCHEMA, "t": table},
        ).fetchall()
    return {r[0] for r in rows}


@pytest.mark.parametrize("revision", sorted(_CASES))
def test_the_revision_runs_over_a_schema_that_already_has_its_columns(sync_engine, probe, revision):
    """The failure this file exists for. Unguarded, this raises DuplicateColumn."""
    case = _CASES[revision]
    probe(case["after"])
    _run(sync_engine, revision)  # must not raise
    assert case["column"] in _columns(sync_engine, case["table"])


@pytest.mark.parametrize("revision", sorted(_CASES))
def test_the_revision_still_adds_its_column_when_it_is_missing(sync_engine, probe, revision):
    """The control. A guard that returned early every time would pass the test
    above and do nothing, and nothing is not what this revision is for."""
    case = _CASES[revision]
    probe(case["before"])
    assert case["column"] not in _columns(sync_engine, case["table"])
    _run(sync_engine, revision)
    assert case["column"] in _columns(sync_engine, case["table"])


def test_v3304_runs_over_a_schema_that_already_has_its_columns(sync_engine, probe):
    probe(_V3304_AFTER)
    _run(sync_engine, "v3304_stock_balance_currency")  # must not raise
    assert "cost_state" in _columns(sync_engine, "oe_supplier_catalogs_stock_balance")
    assert "currency" in _columns(sync_engine, "oe_supplier_catalogs_stock_movement")


def test_v3304_still_adds_its_columns_when_they_are_missing(sync_engine, probe):
    probe(_V3304_BEFORE)
    assert "currency" not in _columns(sync_engine, "oe_supplier_catalogs_stock_balance")
    _run(sync_engine, "v3304_stock_balance_currency")
    balance = _columns(sync_engine, "oe_supplier_catalogs_stock_balance")
    assert {"currency", "cost_state"} <= balance
    assert "currency" in _columns(sync_engine, "oe_supplier_catalogs_stock_movement")
