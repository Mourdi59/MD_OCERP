"""Alembic up/down round-trip tests (Wave 3-D / Task #237).

Goal: catch the "missing or broken downgrade()" CI bug class — a
recent migration whose ``downgrade()`` is empty or doesn't reverse what
``upgrade()`` did. The cheapest way to surface that is to run
``upgrade -> downgrade -> upgrade`` cycles on a fresh PostgreSQL DB.

Schema-creation reality (see ``app/main.py`` ~L1395):
  * The init revision ``129188e46db8`` is intentionally a no-op — its
    docstring says "Tables are created by SQLAlchemy at app startup".
  * The app boots by running ``Base.metadata.create_all()`` first,
    *then* ``alembic upgrade head`` (Alembic only carries column-level
    or new-table deltas after the metadata create).
  * Therefore plain ``alembic upgrade head`` on an empty DB doesn't
    work — e.g. ``v270_position_version_column`` does
    ``inspector.get_columns("oe_boq_position")`` which raises
    ``NoSuchTableError`` because that table comes from create_all,
    not from a migration. This is **expected** project behaviour, not
    a bug to fix here.

Test strategy (mirrors production, isolated per revision):
  1. ``Base.metadata.create_all()`` to lay down the schema at head.
  2. ``alembic stamp head`` to mark all migrations as applied.
  3. For each recent revision ``R``:
     a. ``stamp R`` - move the version marker to exactly R without
        touching the schema (already at head from create_all).
     b. ``downgrade R^`` - run *only* R's own ``downgrade()`` (one step).
     c. ``upgrade R`` - run *only* R's own ``upgrade()`` (one step back).
     d. Assert: post-cycle schema matches pre-cycle schema.

  The earlier design downgraded the whole chain head->R^ then re-upgraded
  to head, which dragged in every legacy migration body between head and
  R^. On PostgreSQL a single broken legacy downgrade aborts the
  transaction and masks the revision actually under test. Isolating to
  R's own one-step cycle attributes any failure to R and nothing else.

Isolation: every test gets its own throwaway PostgreSQL database
(created from scratch, dropped on teardown). ``DATABASE_SYNC_URL``
is monkeypatched so that Alembic's ``env.py`` targets the throwaway
DB, not the dev/production database.

PostgreSQL-only revisions that require extensions or dialect features
unavailable in the unit cluster can be added to ``PG_DOWNGRADE_BROKEN_REVS``
with a one-line reason each; they will be xfailed rather than skipped so
any unexpected recovery is surfaced.

Runtime: ~5-15 s per parametrized rev on a warm interpreter. Tier
``integration``.
"""

from __future__ import annotations

import ast
import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

# Project paths — anchored to this file so the tests work regardless
# of pytest's rootdir / CWD.
THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parent.parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Older revisions we keep exercising by name. These are not the newest any
# more; they are here because each one once broke and the coverage is worth
# keeping regardless of how far behind head it falls.
LEGACY_REVISIONS: list[str] = [
    "v3151_cost_spine",
    "v290_dashboards_presets",
    "v280_4d_schedule_eac",
    "v270_position_version_column",
    "eb1cef6f5fce",  # v262 merge node
    "v261_eac_alias_catalog_seed",
    "v260a_eac_aliases_tables",
    "v260_jobs_runner",
    "v260_eac_v2_core",
    "v250_dashboards_snapshot",
]

# How many revisions back from head to always round-trip.
NEWEST_REVISION_WINDOW = 14


def _revision_graph() -> dict[str, tuple[str, ...]]:
    """Map every revision id to its parents, read from the files as text.

    Deliberately not ``ScriptDirectory.walk_revisions``. That imports each
    migration module, and ``v3121_geo_raster_overlay`` imports ``app.database``
    at module level, which refuses to load without a PostgreSQL ``DATABASE_URL``.
    Using it here would make merely collecting this file depend on a running
    database. Parsing the headers keeps collection free of that.
    """
    graph: dict[str, tuple[str, ...]] = {}
    for path in sorted((BACKEND_DIR / "alembic" / "versions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target, value = node.target.id, node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target, value = node.targets[0].id, node.value
            else:
                continue
            if target not in ("revision", "down_revision") or value is None:
                continue
            try:
                found[target] = ast.literal_eval(value)
            except ValueError:  # computed, not a literal - nothing to read
                continue
        rev = found.get("revision")
        if not isinstance(rev, str):
            continue
        down = found.get("down_revision")
        if isinstance(down, str):
            graph[rev] = (down,)
        elif isinstance(down, (tuple, list)):
            graph[rev] = tuple(str(d) for d in down)
        else:
            graph[rev] = ()
    return graph


_SCHEMA_OP_PREFIXES = ("add_", "alter_", "create_", "drop_", "rename_")


def _changes_schema(source: str, func_name: str) -> bool:
    """True if ``func_name`` in ``source`` calls an Alembic op that alters schema.

    ``op.get_bind`` and ``op.get_context`` are how a data migration reaches the
    connection, so their presence is not evidence of a schema change.
    """
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef) or node.name != func_name:
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Attribute):
                if inner.attr == "batch_alter_table" or inner.attr.startswith(_SCHEMA_OP_PREFIXES):
                    return True
    return False


def _newest_revisions(count: int) -> list[str]:
    """Return the newest ``count`` revision ids, walking down from the heads.

    Derived rather than typed. This list used to be written by hand and it
    stopped being updated: its newest entry was ``v3272`` while eight later
    migrations sat on disk, so the suite was green having never executed a
    single downgrade shipped in that release. A gate whose coverage is a
    literal only covers what somebody remembered to add to the literal, and
    the thing most likely to be forgotten is the migration written today,
    which is also the one most likely to be wrong.

    Walking the graph instead means a new revision is under test the moment
    it lands. A revision that genuinely cannot round-trip belongs in
    ``PG_DOWNGRADE_BROKEN_REVS`` with its reason, not outside the window.
    """
    graph = _revision_graph()
    parents = {parent for parents in graph.values() for parent in parents}
    frontier = sorted(rev for rev in graph if rev not in parents)

    newest: list[str] = []
    seen: set[str] = set()
    while frontier and len(newest) < count:
        rev = frontier.pop(0)
        if rev in seen or rev not in graph:
            continue
        seen.add(rev)
        newest.append(rev)
        frontier.extend(graph[rev])
    return newest


# Newest-first, so the most recent failures surface first.
_NEWEST = _newest_revisions(NEWEST_REVISION_WINDOW)
RECENT_REVISIONS: list[str] = _NEWEST + [rev for rev in LEGACY_REVISIONS if rev not in set(_NEWEST)]

# Revisions whose ``upgrade()`` and ``downgrade()`` are intentionally
# both ``pass`` (typically alembic-generated merge nodes). They round-
# trip vacuously; we still want to confirm they don't error, but we
# don't assert anything about schema deltas.
NOOP_BOTH_REVS: set[str] = {
    "eb1cef6f5fce",  # v262 merge — generator created empty bodies
}

# Revisions that are known to fail the downgrade/re-upgrade cycle on
# PostgreSQL due to genuine dialect-level issues that are separate bugs
# to fix. Add entries here rather than deleting the tests. Format:
#   "revision_id": "one-line reason"
PG_DOWNGRADE_BROKEN_REVS: dict[str, str] = {
    # Example: "v999_example": "downgrade drops a PG-only ENUM that upgrade doesn't recreate"
    "v260_eac_v2_core": (
        "isolation artefact, not a broken downgrade. The cycle above stamps R and runs R's own "
        "downgrade against a schema that is still at head, so this one tries to drop oe_eac_rule "
        "while oe_eac_block_graph - created much later, by v3259 - still holds "
        "fk_oe_eac_block_graph_rule_id_oe_eac_rule against it. A real head-to-v250 downgrade runs "
        "v3259's downgrade first and frees the parent, so this body is correct in the chain it "
        "actually runs in. Any revision whose downgrade drops a table a LATER migration references "
        "will fail here the same way; that is the class, and telling it apart from a genuine "
        "missing drop means asking which revision owns the dependent object, not reading the error."
    ),
}


# ─────────────────────────────────────────────────────────────────────
#  PostgreSQL helpers (mirrors _pg.py internal pattern)
# ─────────────────────────────────────────────────────────────────────


def _maintenance_db(admin_url: str) -> str:
    """The cluster database used to issue CREATE/DROP DATABASE.

    Derived from ``admin_url`` - the *original* configured URL captured
    before the per-test monkeypatch - never from the live env var. By the
    time teardown runs, ``DATABASE_SYNC_URL`` points at the throwaway DB,
    and you cannot DROP the database your own connection is bound to.
    """
    return make_url(admin_url).database or "postgres"


def _sync_url_for(admin_url: str, database: str) -> str:
    """psycopg2 SQLAlchemy URL for ``database`` on ``admin_url``'s cluster."""
    base = make_url(admin_url)
    return base.set(drivername="postgresql+psycopg2", database=database).render_as_string(hide_password=False)


def _connect_admin(admin_url: str):
    """Autocommit psycopg2 connection to the maintenance database.

    Connects to the cluster's maintenance DB (the one named in the
    original ``admin_url``), not the throwaway, so CREATE/DROP DATABASE
    run from a connection that is not itself the target. ``admin_url``
    carries the SQLAlchemy ``postgresql+psycopg2`` driver form; raw
    ``psycopg2.connect`` only accepts a libpq ``postgresql://`` URI, so
    the driver suffix is stripped here.
    """
    base = make_url(admin_url)
    maint = base.set(drivername="postgresql", database=_maintenance_db(admin_url)).render_as_string(hide_password=False)
    conn = psycopg2.connect(maint)
    conn.autocommit = True
    return conn


def _terminate_backends(cur, db_name: str) -> None:
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (db_name,),
    )


def _create_throwaway_db(admin_url: str, db_name: str) -> None:
    """Create a fresh, empty PostgreSQL database for one test."""
    conn = _connect_admin(admin_url)
    try:
        conn.cursor().execute(f'CREATE DATABASE "{db_name}"')
    finally:
        conn.close()


def _drop_throwaway_db(admin_url: str, db_name: str) -> None:
    """Drop the throwaway database, terminating any leftover connections first."""
    conn = _connect_admin(admin_url)
    try:
        cur = conn.cursor()
        _terminate_backends(cur, db_name)
        cur.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
        cur.close()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────
#  Alembic config builder
# ─────────────────────────────────────────────────────────────────────


def _make_alembic_config(sync_url: str) -> Config:
    """Build an Alembic Config pointing at ``sync_url``.

    Override both the ini ``sqlalchemy.url`` entry (for completeness)
    and set the env var so ``alembic/env.py`` (which reads
    ``settings.database_sync_url`` directly) targets the throwaway DB.
    The ``DATABASE_SYNC_URL`` env var monkeypatch is applied by the
    ``pg_throwaway`` fixture before this function is called.
    """
    cfg = Config(str(ALEMBIC_INI))
    # ``script_location`` is normally relative to the .ini file; make it
    # explicit so a temp CWD doesn't break resolution.
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


# ─────────────────────────────────────────────────────────────────────
#  Model import helper
# ─────────────────────────────────────────────────────────────────────


def _import_all_models() -> None:
    """Mirror what ``alembic/env.py`` imports - populates Base.metadata.

    Done lazily (function-local imports) so this expensive step only
    runs when an actual round-trip test executes, not at collection.

    Uses the same pkgutil catch-all as ``alembic/env.py`` rather than a
    hand-maintained list. A static list silently drifts: it was missing
    ``property_dev`` (and others), so ``Base.metadata.create_all`` never
    materialised ``oe_property_dev_custom_template`` and any downgrade
    body that reflected that table (e.g. v3137) raised ``NoSuchTableError``
    on PostgreSQL. Sweeping every module guarantees create_all reproduces
    the exact production schema shape.
    """
    import importlib
    import pkgutil

    from app import modules as _modules_pkg

    # Core-level tables that live outside app.modules.* and so are not
    # reached by the module sweep below.
    from app.core import audit  # noqa: F401
    from app.core import audit_log as _audit_log  # noqa: F401  # oe_activity_log
    from app.core import job_run as _job_run  # noqa: F401  # oe_job_run
    from app.core.translation import cache as _tcache  # noqa: F401  # oe_translation_cache

    _modules_dir = os.path.dirname(_modules_pkg.__file__)
    for _entry in pkgutil.iter_modules([_modules_dir]):
        if not _entry.ispkg:
            continue
        try:
            importlib.import_module(f"app.modules.{_entry.name}.models")
        except Exception:  # noqa: BLE001 - mirror env.py: a bad module never aborts the sweep
            pass


# ─────────────────────────────────────────────────────────────────────
#  Schema bootstrap
# ─────────────────────────────────────────────────────────────────────


def _create_all_then_stamp(sync_url: str, cfg: Config) -> None:
    """Mirror app boot: create_all on a sync PostgreSQL engine, then stamp head.

    This is the only realistic starting point for downgrade tests —
    ``upgrade head`` from base does not work on this project (see
    module docstring).
    """
    _import_all_models()  # populate Base.metadata

    from app.database import Base

    eng = create_engine(sync_url)
    try:
        Base.metadata.create_all(eng)
    finally:
        eng.dispose()

    command.stamp(cfg, "head")


# ─────────────────────────────────────────────────────────────────────
#  Schema snapshot
# ─────────────────────────────────────────────────────────────────────


def _schema_snapshot(sync_url: str) -> dict[str, list[str]]:
    """Return ``{table: sorted(column_names)}`` for the database at ``sync_url``.

    Skips ``alembic_version`` (its row content changes between
    upgrade/downgrade by design) and PostgreSQL system tables.
    """
    eng = create_engine(sync_url)
    try:
        insp = inspect(eng)
        out: dict[str, list[str]] = {}
        for table in sorted(insp.get_table_names()):
            if table == "alembic_version":
                continue
            cols = sorted(c["name"] for c in insp.get_columns(table))
            out[table] = cols
        return out
    finally:
        eng.dispose()


# ─────────────────────────────────────────────────────────────────────
#  Per-test fixture: throwaway PostgreSQL database
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def pg_throwaway(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Per-test throwaway PostgreSQL database + env vars routed at it.

    Creates a fresh, empty database on the session cluster, monkeypatches
    ``DATABASE_SYNC_URL`` (and ``DATABASE_URL``) to point at it, and
    clears the Settings cache so ``alembic/env.py`` picks up the override.
    Drops the database on teardown.

    Yields the sync psycopg2 URL string for the throwaway database.
    """
    # Capture the original (pre-monkeypatch) sync URL. All CREATE/DROP
    # DATABASE admin work uses this, never the patched env var: by the time
    # teardown runs, DATABASE_SYNC_URL points at the throwaway DB, and a
    # connection bound to that DB cannot drop it.
    admin_url = os.environ["DATABASE_SYNC_URL"]

    db_name = f"oe_mig_rt_{uuid.uuid4().hex[:16]}"
    _create_throwaway_db(admin_url, db_name)

    sync_url = _sync_url_for(admin_url, db_name)
    # Build the async URL from the sync one (replace driver).
    async_url = make_url(sync_url).set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)

    monkeypatch.setenv("DATABASE_SYNC_URL", sync_url)
    monkeypatch.setenv("DATABASE_URL", async_url)

    # Bust the cached Settings so env.py reads the override.
    from app.config import get_settings

    get_settings.cache_clear()

    try:
        yield sync_url
    finally:
        get_settings.cache_clear()
        _drop_throwaway_db(admin_url, db_name)


# ─────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────


def test_create_all_plus_stamp_head_succeeds(pg_throwaway: str) -> None:
    """Sanity: production-style boot (create_all + stamp head) works on PostgreSQL.

    If this fails, every other round-trip test in the file fails too,
    so we run it first to fail fast with a clear signal.
    """
    sync_url = pg_throwaway
    cfg = _make_alembic_config(sync_url)
    _create_all_then_stamp(sync_url, cfg)

    snap = _schema_snapshot(sync_url)
    assert snap, "create_all + stamp produced no tables"
    # Spot-check core tables created by metadata + alembic-tracked tables.
    assert "oe_projects_project" in snap
    assert "oe_boq_position" in snap
    assert "version" in snap["oe_boq_position"], (
        "v270 column not on Position model — Base.metadata.create_all should add it"
    )
    # EAC v2 tables come from create_all too (the model is in metadata).
    assert "oe_eac_ruleset" in snap, "EAC ruleset table missing from metadata"
    assert "oe_eac_parameter_aliases" in snap
    assert "oe_job_run" in snap
    assert "oe_dashboards_snapshot" in snap


@pytest.mark.parametrize("revision", RECENT_REVISIONS)
def test_revision_downgrade_reupgrade_does_not_error(pg_throwaway: str, revision: str) -> None:
    """For each recent revision R: isolate-test R's own down + up step on PostgreSQL.

    Starts from a production-style boot (create_all + stamp head), then:
      1. ``stamp R`` - move the version marker to exactly R without
         touching the schema (already at head from create_all).
      2. ``downgrade R^`` - run *only* R's ``downgrade()`` body (one step).
      3. ``upgrade R`` - run *only* R's ``upgrade()`` body (one step back).

    This is the canonical "missing/broken downgrade" detector, isolated
    so a failure is attributable to R alone and unrelated legacy bodies
    never run (they would abort the PG transaction and mask R).

    The schema matches before and after because create_all already laid
    down R's objects; R.downgrade() removes them and R.upgrade() re-adds
    them.
    """
    if revision in PG_DOWNGRADE_BROKEN_REVS:
        pytest.xfail(f"{revision} known broken on PG: {PG_DOWNGRADE_BROKEN_REVS[revision]}")

    if revision in NOOP_BOTH_REVS:
        # Empty upgrade()/downgrade() bodies (generator-emitted merge
        # nodes). There is no schema delta to cycle and a merge node
        # cannot be downgraded one step to a single parent cleanly. An
        # empty body cannot be "broken", so there is nothing to exercise.
        pytest.xfail(
            f"{revision} is a generator-emitted merge node with empty "
            f"upgrade()/downgrade() bodies - round-trip is vacuous"
        )

    sync_url = pg_throwaway
    cfg = _make_alembic_config(sync_url)
    _create_all_then_stamp(sync_url, cfg)
    snap_before = _schema_snapshot(sync_url)

    # Resolve the parent revision (the one-step downgrade target).
    script = ScriptDirectory.from_config(cfg)
    parent = script.get_revision(revision).down_revision
    parent_rev = parent[0] if isinstance(parent, tuple) else parent
    assert parent_rev, f"{revision} has no parent - can't downgrade past it"

    # Move the version marker to exactly R. The schema is already at head
    # from create_all, so this just rewrites alembic_version - no
    # migration body runs. The subsequent downgrade is then a single step
    # (R -> R^) that executes only R's own downgrade().
    command.stamp(cfg, revision)

    try:
        command.downgrade(cfg, parent_rev)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"downgrade of {revision} (target={parent_rev}) raised - "
            f"likely a missing/broken downgrade() body. Root cause: {exc!r}"
        )

    try:
        command.upgrade(cfg, revision)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"re-upgrade of {revision} raised - likely upgrade() is "
            f"non-idempotent or PG-incompatible. Root cause: {exc!r}"
        )

    snap_after = _schema_snapshot(sync_url)

    # Table set must be unchanged: a downgrade that drops a table whose
    # upgrade fails to recreate it (or a downgrade/upgrade that leaks a
    # spurious table) shows up here.
    assert set(snap_after) == set(snap_before), (
        f"Schema after round-tripping {revision} changed the table set. "
        f"Tables added by cycle: {set(snap_after) - set(snap_before)}; "
        f"tables removed by cycle: {set(snap_before) - set(snap_after)}"
    )

    # Column-level invariant for *isolated* single-step cycling: re-running
    # only R's own upgrade() recreates R's tables at their R-era shape, which
    # is a subset of the head shape whenever a *later* migration added columns
    # to one of those tables (e.g. v260_jobs_runner adds idempotency_key /
    # spool_path to the oe_eac_run table that v260_eac_v2_core created). That
    # subset divergence is expected, not a bug. What is NOT allowed is the
    # cycle introducing a column the head schema doesn't have - that signals a
    # genuine upgrade/downgrade inconsistency.
    introduced = {
        table: sorted(set(snap_after[table]) - set(snap_before[table]))
        for table in snap_after
        if set(snap_after[table]) - set(snap_before[table])
    }
    assert not introduced, (
        f"Round-tripping {revision} introduced columns absent from the head "
        f"schema (upgrade/downgrade inconsistency): {introduced}"
    )


def test_recent_migrations_have_real_downgrade_bodies() -> None:
    """Static guard: each recent migration's downgrade() is non-trivial.

    "Non-trivial" = the source contains some schema-mutating call
    (``op.drop_*``, ``op.execute(...)``, ``batch_alter_table``) — not
    just ``pass`` / a docstring. Merge revisions in ``NOOP_BOTH_REVS``
    are exempt.

    This is the cheap "lint" companion to the round-trip test above:
    it surfaces the same issue even when nobody runs the slower
    integration test.
    """
    versions_dir = BACKEND_DIR / "alembic" / "versions"
    bad: list[str] = []
    skipped_data_only: list[str] = []
    for revision in RECENT_REVISIONS:
        if revision in NOOP_BOTH_REVS:
            continue
        # Locate the migration file by matching the revision assignment at the
        # start of a line — substring matches in ``down_revision`` tuples on
        # merge nodes would give false positives (e.g. eb1cef6f5fce mentions
        # both v260_jobs_runner and v261_eac_alias_catalog_seed in its
        # down_revision), and ``down_revision = "<id>"`` literally contains
        # ``revision = "<id>"``, so the anchor is what keeps the two apart.
        #
        # Both spellings of the assignment live in the tree: the annotated
        # ``revision: str = ...`` alembic's template emits now, and the bare
        # ``revision = ...`` that 51 older files still carry. Matching only the
        # annotated one made this guard fail the moment the newest-revision
        # window slid over one of those older files, which says nothing about
        # the downgrade bodies it is here to check.
        marker = re.compile(rf'^revision(?::\s*str)?\s*=\s*"{re.escape(revision)}"', re.MULTILINE)
        candidates = [p for p in versions_dir.glob("*.py") if marker.search(p.read_text(encoding="utf-8"))]
        assert candidates, f"Couldn't locate migration file for {revision}"
        src = candidates[0].read_text(encoding="utf-8")

        # A migration that never touched the schema has nothing to reverse, and
        # demanding a schema call in its downgrade() would be asking it to undo
        # work it did not do. v3269, v3271 and v3273 are backfills: their only
        # use of ``op`` is ``op.get_bind()`` to run data statements, and each
        # documents its downgrade as a deliberate no-op. Deciding this from the
        # upgrade body rather than from a list of exempt revision ids means a
        # future backfill is judged correctly without anyone registering it,
        # and a migration that does add a column is still held to the rule.
        if not _changes_schema(src, "upgrade"):
            skipped_data_only.append(revision)
            continue

        _, _, after = src.partition("def downgrade()")
        if not after:
            bad.append(f"{revision}: no downgrade() function at all")
            continue
        body = after.split("\ndef ", 1)[0]
        # Strip docstrings / comments / blanks; check what remains.
        stripped_lines = [
            line
            for line in body.splitlines()
            if line.strip()
            and not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("'''")
        ]
        meaningful = "\n".join(stripped_lines)
        if "op." not in meaningful and "batch_alter_table" not in meaningful:
            bad.append(f"{revision}: downgrade() has no schema-mutating call")

    # Say what was not checked. An exemption nobody can see is the same shape
    # of blind spot as the short revision list this guard used to run against.
    print(f"data-only migrations exempt from the downgrade rule: {', '.join(skipped_data_only) or 'none'}")
    assert not bad, "Migrations with non-functional downgrade():\n  " + "\n  ".join(bad)


def test_dev_db_is_not_being_targeted(pg_throwaway: str) -> None:
    """Tripwire: throwaway-DB fixture must override the dev-DB env var.

    If anyone copy-pastes this file or the fixture goes wrong, we want
    a screaming failure rather than silent corruption of the dev DB.
    """
    assert "openestimate.db" not in os.environ.get("DATABASE_SYNC_URL", ""), (
        "Test fixture failed to override DATABASE_SYNC_URL — would have written to the dev DB. Aborting."
    )
    # The active DATABASE_SYNC_URL must point at a throwaway PG database.
    active_url = os.environ.get("DATABASE_SYNC_URL", "")
    assert "postgresql" in active_url, f"Expected DATABASE_SYNC_URL to be a PostgreSQL URL, got: {active_url!r}"
    assert "oe_mig_rt_" in active_url, (
        f"Expected DATABASE_SYNC_URL to contain the throwaway DB name prefix 'oe_mig_rt_', got: {active_url!r}"
    )


# ─────────────────────────────────────────────────────────────────────
#  Data migrations
#
#  A data migration cannot be checked the way the schema ones above are.
#  create_all builds the catalogue table empty and the seed catalogue in
#  the source tree already carries the post-rename names, so running
#  v3271 against a fresh test database updates zero rows and passes
#  without executing a single branch. The rows it exists to repair only
#  occur on a database seeded before the rename, so the test has to write
#  that state itself.
# ─────────────────────────────────────────────────────────────────────

_SYSTEM_TABLE = "oe_formwork_system"

_INSERT_SYSTEM = text(
    f"""
    INSERT INTO {_SYSTEM_TABLE}
        (id, created_at, updated_at, name, system_type, supplier, material,
         reuses_max, unit_rate, erect_strike_rate, strip_time_days, currency)
    VALUES
        (:id, now(), now(), :name, 'wall', :supplier, 'steel',
         100, 65.00, 16.00, 1, '')
    """  # noqa: S608 - table name is a module constant, not user input
)


def _run_revision_upgrade(sync_url: str, revision: str) -> None:
    """Execute one revision's ``upgrade()`` body against ``sync_url``.

    Not ``command.upgrade``: the database is stamped at head, so alembic
    would consider this revision already applied and do nothing. Binding
    the body to a connection runs the code under test directly.
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    cfg = _make_alembic_config(sync_url)
    module = ScriptDirectory.from_config(cfg).get_revision(revision).module

    engine = create_engine(sync_url)
    try:
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                module.upgrade()
    finally:
        engine.dispose()


def _systems_by_id(sync_url: str) -> dict[str, tuple[str, str | None]]:
    """Return ``{id: (name, supplier)}`` for every catalogue row."""
    engine = create_engine(sync_url)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT id, name, supplier FROM {_SYSTEM_TABLE}")  # noqa: S608
            ).all()
    finally:
        engine.dispose()
    return {str(row[0]): (row[1], row[2]) for row in rows}


def test_v3271_renames_only_the_rows_it_should(pg_throwaway: str) -> None:
    """v3271 renames trademarked catalogue rows without touching tenant edits.

    Five rows covering every branch the revision has:

    * a plain trademarked row, which must be renamed and lose its supplier;
    * the one pair carrying a non-ASCII character, which must move too - if
      the literal in the migration ever stops byte-matching the column, this
      is the row that catches it;
    * a trademarked row whose supplier the tenant repointed at their own hire
      yard, where the name must move and that supplier value must survive;
    * a trademarked row whose replacement name is already present, which the
      duplicate guard must leave alone;
    * a row the tenant renamed themselves, which must not be touched at all
      even though its supplier still reads as a brand.
    """
    cfg = _make_alembic_config(pg_throwaway)
    _create_all_then_stamp(pg_throwaway, cfg)

    plain = str(uuid.uuid4())
    non_ascii = str(uuid.uuid4())
    tenant_supplier = str(uuid.uuid4())
    would_duplicate = str(uuid.uuid4())
    already_present = str(uuid.uuid4())
    tenant_renamed = str(uuid.uuid4())

    seeded = [
        {"id": plain, "name": "Doka Framax Xlife", "supplier": "Doka"},
        {"id": non_ascii, "name": "Hünnebeck MANTO", "supplier": "Hünnebeck"},
        {"id": tenant_supplier, "name": "PERI MAXIMO", "supplier": "Central hire yard"},
        {"id": would_duplicate, "name": "Doka Dokadek 30", "supplier": "Doka"},
        {"id": already_present, "name": "Aluminium slab deck panel", "supplier": None},
        {"id": tenant_renamed, "name": "Site-built wall shutter", "supplier": "Doka"},
    ]
    engine = create_engine(pg_throwaway)
    try:
        with engine.begin() as conn:
            for row in seeded:
                conn.execute(_INSERT_SYSTEM, row)
    finally:
        engine.dispose()

    _run_revision_upgrade(pg_throwaway, "v3271_formwork_debrand")
    after = _systems_by_id(pg_throwaway)

    assert after[plain] == ("Steel framed wall panel", None)
    assert after[non_ascii] == ("Crane-set steel wall panel", None), (
        "the non-ASCII pair did not move - the literal no longer matches the column"
    )
    assert after[tenant_supplier] == (
        "Steel wall panel, single-side tie",
        "Central hire yard",
    ), "a supplier the tenant set themselves was cleared"
    assert after[would_duplicate] == ("Doka Dokadek 30", "Doka"), (
        "renamed onto a name already present for this tenant, creating a duplicate"
    )
    assert after[already_present] == ("Aluminium slab deck panel", None)
    assert after[tenant_renamed] == ("Site-built wall shutter", "Doka"), "a row the tenant renamed was rewritten"

    # Idempotent: a second run must be a no-op, including for the row the
    # duplicate guard declined to touch.
    _run_revision_upgrade(pg_throwaway, "v3271_formwork_debrand")
    assert _systems_by_id(pg_throwaway) == after


def test_v3271_lands_an_upgraded_install_on_the_shipped_catalogue(pg_throwaway: str) -> None:
    """An upgraded install ends up with the names a fresh install has.

    This test cannot check the *old* names and does not try to. It seeds from
    ``_RENAMES``, so a mistyped old-name literal would be inserted mistyped,
    found renamed, and passed - measured, that exact mutation went green here
    while ``test_v3271_renames_only_the_rows_it_should`` caught it, because
    that one spells the trademarked names out independently of the migration.
    Drift in the old names is its job, not this one's.

    What this test owns is the other half: the migration and the shipped
    catalogue must agree on where the rows land. ``default_seed_systems()`` is
    the denominator, so re-wording a catalogue row without updating the
    revision fails here rather than leaving upgraded and fresh installs with
    two different names for the same system.
    """
    cfg = _make_alembic_config(pg_throwaway)
    _create_all_then_stamp(pg_throwaway, cfg)

    module = ScriptDirectory.from_config(cfg).get_revision("v3271_formwork_debrand").module
    renames = module._RENAMES  # noqa: SLF001 - the mapping is the thing under test

    from app.modules.formwork.schemas import default_seed_systems

    catalogue = {row["name"] for row in default_seed_systems()}
    written = {new_name for _old, _supplier, new_name in renames}
    assert written <= catalogue, (
        f"revision renames rows to names a fresh install does not have: {sorted(written - catalogue)}"
    )
    assert len(renames) == 8, f"expected eight renamed rows, mapping carries {len(renames)}"

    engine = create_engine(pg_throwaway)
    try:
        with engine.begin() as conn:
            for old_name, old_supplier, _new_name in renames:
                conn.execute(
                    _INSERT_SYSTEM,
                    {"id": str(uuid.uuid4()), "name": old_name, "supplier": old_supplier},
                )
    finally:
        engine.dispose()

    _run_revision_upgrade(pg_throwaway, "v3271_formwork_debrand")

    after = _systems_by_id(pg_throwaway)
    surviving = {name for name, _supplier in after.values()}
    assert surviving <= catalogue, f"rows left carrying a name no fresh install has: {sorted(surviving - catalogue)}"

    suppliers = {supplier for _name, supplier in after.values()}
    assert suppliers == {None}, f"brand suppliers still in the catalogue: {suppliers - {None}}"


# ─────────────────────────────────────────────────────────────────────
#  v3272 - the assignment -> schedule activity link
# ─────────────────────────────────────────────────────────────────────

_ASSIGNMENT_TABLE = "oe_resources_assignment"
_ACTIVITY_FK = "fk_oe_resources_assignment_activity_id_oe_schedule_activity"


def _activity_fk(sync_url: str) -> dict[str, object] | None:
    """Reflect the assignment -> activity foreign key back, or None."""
    engine = create_engine(sync_url)
    try:
        for fk in inspect(engine).get_foreign_keys(_ASSIGNMENT_TABLE):
            if fk.get("name") == _ACTIVITY_FK:
                return fk
        return None
    finally:
        engine.dispose()


def test_v3272_creates_the_activity_foreign_key(pg_throwaway: str) -> None:
    """The FK is the migration's whole payload, and only this asserts it.

    ``create_all`` already lays down ``activity_id`` and its index, because
    the column is on the model. What it cannot lay down is the constraint:
    the ORM deliberately carries no ``ForeignKey`` for it, so the resources
    module still imports on an install where the schedule module is absent.
    That leaves the migration as the only thing that ever creates it.

    A migration that ran without raising is not a migration that created a
    constraint. ``upgrade()`` returns early when the target table is missing
    and swallows a refused ``create_foreign_key``, and both of those silent
    paths look exactly like success from outside. Reflecting the constraint
    back is what tells them apart.
    """
    cfg = _make_alembic_config(pg_throwaway)
    _create_all_then_stamp(pg_throwaway, cfg)

    # Negative control. Without it this test cannot tell the migration's work
    # from what the model had already produced.
    assert _activity_fk(pg_throwaway) is None, "create_all already made the FK - this test would prove nothing"

    _run_revision_upgrade(pg_throwaway, "v3272_assignment_activity_link")

    fk = _activity_fk(pg_throwaway)
    assert fk is not None, f"{_ACTIVITY_FK} absent after the revision ran"
    assert fk["referred_table"] == "oe_schedule_activity"
    assert fk["constrained_columns"] == ["activity_id"]
    assert fk["referred_columns"] == ["id"]

    # Deleting a Gantt bar must not take the booking history with it.
    options = fk.get("options") or {}
    assert isinstance(options, dict)
    assert options.get("ondelete") == "SET NULL", f"expected SET NULL, reflected {options!r}"


def test_v3272_upgrade_is_idempotent(pg_throwaway: str) -> None:
    """Running it twice must not raise, and must leave one constraint.

    Every guard in the body is an ``if not present`` check, so a second run
    is the cheapest test of all of them at once.
    """
    cfg = _make_alembic_config(pg_throwaway)
    _create_all_then_stamp(pg_throwaway, cfg)

    _run_revision_upgrade(pg_throwaway, "v3272_assignment_activity_link")
    _run_revision_upgrade(pg_throwaway, "v3272_assignment_activity_link")

    engine = create_engine(pg_throwaway)
    try:
        fks = inspect(engine).get_foreign_keys(_ASSIGNMENT_TABLE)
    finally:
        engine.dispose()

    assert [fk["name"] for fk in fks].count(_ACTIVITY_FK) == 1


def test_v3272_rebuilds_a_column_the_constraint_still_fits(pg_throwaway: str) -> None:
    """After a downgrade, the re-upgrade must rebuild the column at its own type.

    The parametrized round-trip above compares column *names*, so a column
    that comes back at the wrong type reads as unchanged. This revision was
    first written declaring ``activity_id`` as native ``uuid``, copying the
    idiom of the neighbouring v3014 columns; PostgreSQL then refused the
    constraint against ``oe_schedule_activity.id``, which ``GUID`` makes
    ``varchar(36)`` on every dialect. What proves the type is right is the
    constraint standing after the cycle, not the column existing.
    """
    cfg = _make_alembic_config(pg_throwaway)
    _create_all_then_stamp(pg_throwaway, cfg)

    command.stamp(cfg, "v3272_assignment_activity_link")
    command.downgrade(cfg, "v3271_formwork_debrand")
    command.upgrade(cfg, "v3272_assignment_activity_link")

    engine = create_engine(pg_throwaway)
    try:
        insp = inspect(engine)
        column = next(c for c in insp.get_columns(_ASSIGNMENT_TABLE) if c["name"] == "activity_id")
    finally:
        engine.dispose()

    assert "CHAR" in str(column["type"]).upper(), f"activity_id came back as {column['type']!r}"
    fk = _activity_fk(pg_throwaway)
    assert fk is not None, "the constraint did not survive a downgrade and re-upgrade"
    assert (fk.get("options") or {}).get("ondelete") == "SET NULL"
