# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The two properties ``tests/_pg.py`` exists to provide, asserted directly.

Both are expensive enough to be tempting to weaken, and both fail silently when
weakened, which is why they are pinned here rather than trusted to the suite.

**Every test database bounds a single statement.** A test that hangs inside a
query returns no verdict at all: nothing passes, nothing fails, nothing turns
red, and the silence reads exactly like health. ``lock_timeout`` does not cover
it - that bounds waiting for a lock, not running - and the per-test kill above
it takes the whole process without naming the statement, where there is one at
all: ``addopts`` carries no ``--timeout``, so a local run has nothing above this
bound. ``statement_timeout`` turns that case into one named failure. A bound
nobody reads back is not a bound, so these tests ask the server, over each of
the four ways ``_pg.py`` hands out a connection, rather than trusting the
``ALTER DATABASE`` to have landed.

**A throwaway database is genuinely throwaway.** ``isolated_engine`` clones a
database per call, which is the dominant cost of the suites that use it, so
"just widen the fixture scope" is a standing proposal. It is unsafe, and
measurably so: pointing all 16 ``isolated_engine`` unit files at one shared
database (and, separately, at one per module) failed the same 7 tests in
``test_erpchat_feedback``, ``test_match_analytics`` and
``test_partner_pack_full_install_stream``, every one of them on a count that had
absorbed a previous test's rows - ``assert 8 == 4``, ``assert 3 == 1``,
``assert 0 == 15``. Every leak was inside a single file, so module scope is no
safer than session scope. ``test_postgres_migrator_indexes`` raises the stakes
past rows: it drops indexes to simulate an old install, so what leaks there is
the schema.

A suite passing after such a change would not have proved anything - the tests
would simply never have read each other's leftovers. So the check below reads
them on purpose, and carries its own teeth: it asserts the leftovers ARE visible
when the database is reused, so the isolation half cannot pass by being blind.
"""

from __future__ import annotations

import sys

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests._pg import (
    LOCK_TIMEOUT_S,
    STATEMENT_TIMEOUT_S,
    isolated_database_url,
    isolated_engine,
    schema_inspection_engine,
    transactional_session,
)

#: ``pg_settings`` reports this one in milliseconds, which is the only reading
#: with no unit to get wrong: ``SHOW`` renders 60 seconds as the string
#: ``'1min'``.
_READ_BOUND_MS = "SELECT setting::bigint FROM pg_settings WHERE name = 'statement_timeout'"

_EXPECTED_MS = STATEMENT_TIMEOUT_S * 1000


@pytest_asyncio.fixture(scope="module")
async def engine():
    """One throwaway database for the read-only checks - cloning one is not free."""
    async with isolated_engine() as eng:
        yield eng


async def test_isolated_engine_databases_bound_a_statement(engine) -> None:
    """The bound is in force on the connection a test actually gets."""
    async with engine.connect() as conn:
        observed = (await conn.execute(text(_READ_BOUND_MS))).scalar_one()
    assert observed == _EXPECTED_MS, (
        f"statement_timeout on {engine.url.database} reads {observed}ms, expected {_EXPECTED_MS}ms"
    )


async def test_the_bound_reaches_a_session_and_not_just_the_engine(engine) -> None:
    """Application code opens sessions, not connections - check the path it uses."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        observed = (await session.execute(text(_READ_BOUND_MS))).scalar_one()
    assert observed == _EXPECTED_MS


async def test_the_bound_reaches_an_engine_built_from_a_handed_out_url() -> None:
    """``isolated_database_url`` hands out a URL, so nothing sets connect args for it.

    This is the entry point a ``connect_args`` on ``isolated_engine`` would have
    missed entirely: its callers build their own engine, one per event loop. The
    bound has to live on the database for this to hold.
    """
    with isolated_database_url() as url:
        own_engine = create_async_engine(url, future=True)
        try:
            async with own_engine.connect() as conn:
                observed = (await conn.execute(text(_READ_BOUND_MS))).scalar_one()
        finally:
            await own_engine.dispose()
    assert observed == _EXPECTED_MS


async def test_the_bound_reaches_the_shared_transactional_database() -> None:
    """``transactional_session`` is the widest population of the four by far.

    Every unit and module fixture that needs a session goes through it, against
    the one long-lived ``oe_test_unit`` database. A guard that covered only the
    per-test clones would leave most of the suite unbounded while reading green.
    """
    async with transactional_session() as session:
        observed = (await session.execute(text(_READ_BOUND_MS))).scalar_one()
    assert observed == _EXPECTED_MS


def test_the_bound_reaches_the_schema_inspection_engine() -> None:
    """The fourth entry point, and the only synchronous one."""
    sync_engine = schema_inspection_engine()
    try:
        with sync_engine.connect() as conn:
            observed = conn.execute(text(_READ_BOUND_MS)).scalar_one()
    finally:
        sync_engine.dispose()
    assert observed == _EXPECTED_MS


async def test_an_overrunning_statement_fails_by_name(engine) -> None:
    """The point of the bound: a hang becomes a named failure, not silence.

    Lowered for this one transaction so the test costs a fraction of a second
    rather than :data:`STATEMENT_TIMEOUT_S`. That a session-level value wins over
    the per-database one is itself part of the contract - it is the escape hatch
    a test with a legitimately long statement uses.

    ``SET LOCAL`` and an explicit rollback, not a bare ``SET``. This engine
    pools its connections, so a bare ``SET`` would ride back into the pool and
    hand the next test in this file a 250ms bound it never asked for. In a file
    whose subject is state leaking between tests, leaving that behind would be
    a poor joke.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL statement_timeout = '250ms'"))
            with pytest.raises(DBAPIError) as caught:
                await conn.execute(text("SELECT pg_sleep(5)"))
        finally:
            await trans.rollback()
    assert "statement timeout" in str(caught.value).lower(), str(caught.value)

    # And the connection came back clean.
    async with engine.connect() as conn:
        assert (await conn.execute(text(_READ_BOUND_MS))).scalar_one() == _EXPECTED_MS


def test_the_bounds_stay_ordered() -> None:
    """Which timeout fires first is a design decision, not an accident.

    ``lock_timeout`` must stay the shorter of the two so that a statement stuck
    waiting for a lock still reports the clearer "lock timeout", leaving
    ``statement_timeout`` to catch what it cannot: a statement that is running
    rather than waiting. And the statement bound must stay well under the
    idle-in-transaction bound ``conftest`` sets and under every lane's per-test
    kill (300s in Backend CI, 900s nightly), so the named failure is what
    reaches the log rather than a killed process.

    The idle bound is read out of the already-imported ``conftest`` rather than
    copied here as a literal. A copy would keep this green after someone lowered
    the original below 60s, which is precisely the ordering this test exists to
    defend. Looked up through :data:`sys.modules` because importing ``conftest``
    by name a second time would boot a second PostgreSQL cluster.
    """
    assert STATEMENT_TIMEOUT_S > LOCK_TIMEOUT_S

    conftest = sys.modules.get("tests.conftest")
    assert conftest is not None, "tests/conftest.py should already be imported under this name by pytest"
    assert STATEMENT_TIMEOUT_S < conftest._IDLE_IN_TRANSACTION_TIMEOUT_S


async def test_two_isolated_engines_share_neither_schema_nor_rows() -> None:
    """Widening the fixture scope would break the 7 tests named in the docstring.

    Asserted in both directions on purpose. The first half checks that a second
    clone cannot see what the first one wrote. On its own that would also pass if
    the write never landed or the read were aimed at nothing, which is the shape
    of green that means nothing. So the second half re-reads the first database
    through a fresh engine and requires the leftovers to be right there - if they
    are not, the isolation assertion above had no teeth and this test says so.

    Both a table and a row, because the two suites at risk lose different things:
    the counting tests leak rows, ``test_postgres_migrator_indexes`` leaks a
    schema change.
    """
    probe = "fixture_isolation_probe"

    async with isolated_engine() as first:
        first_url = first.url
        async with first.begin() as conn:
            await conn.execute(text(f"CREATE TABLE {probe} (note text)"))
            await conn.execute(text(f"INSERT INTO {probe} (note) VALUES ('left behind')"))

        async with isolated_engine() as second:
            assert second.url.database != first_url.database
            async with second.connect() as conn:
                leaked = (await conn.execute(text("SELECT to_regclass(:name)"), {"name": probe})).scalar_one()
            assert leaked is None, (
                f"{probe} created on {first_url.database} is visible on {second.url.database}: "
                "the fixture is handing out a shared database"
            )

        # Teeth: the same read, aimed at the database that WAS written to.
        witness = create_async_engine(first_url, future=True)
        try:
            async with witness.connect() as conn:
                rows = (await conn.execute(text(f"SELECT note FROM {probe}"))).scalars().all()
        finally:
            await witness.dispose()
        assert rows == ["left behind"], (
            "the probe row is not readable even on its own database, so the isolation assertion above proved nothing"
        )
