# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Build a database exactly as the PREVIOUS release builds one, then seed it.

Half one of the upgrade lane. This script runs in a virtualenv that has the
PREVIOUS release installed from PyPI and nothing of this working tree in it;
``verify_upgrade_from_previous_release.py`` then runs the CURRENT code against
the database this leaves behind.

Why a whole separate interpreter
--------------------------------
The point of the lane is that every other lane starts from an empty database,
so the only thing they test is a fresh install, while almost every real user is
upgrading. An aged database cannot be faked from the current tree: whatever the
current metadata declares is by definition current, and a database built from
it is not old. The only honest source of an old schema is the old code.

Why the app is booted rather than migrated
------------------------------------------
``alembic upgrade head`` cannot produce this database, twice over. On an empty
database ``alembic/env.py`` short-circuits to ``create_all`` plus a stamp at
head, so it would build the CURRENT schema and prove nothing. And the releases
before 15.4.0 do not ship ``alembic.ini`` or the revision tree in their wheel
at all, so there is no migration entry point in this interpreter to call.

What a real install of the previous release does is boot the app once, which
imports every module's models and calls ``Base.metadata.create_all``. That is
what this does, through the previous release's own ``create_app`` and its own
lifespan, so the schema comes out of the old code's own hands.

Provenance is asserted, not assumed
-----------------------------------
A mis-wired ``PYTHONPATH`` that resolved ``app`` back to the working tree would
produce a database at the current schema and every downstream check would pass
on it. Two guards stop that: the installed distribution's version has to equal
``OE_UPGRADE_FROM_VERSION``, and the imported ``app`` package has to live
outside this repository.

Rows, not just tables
---------------------
The database is seeded with a user, a project and one NCR before it is handed
over. Rows matter for two separate reasons. PostgreSQL accepts
``ADD COLUMN ... NOT NULL`` with no default on an EMPTY table and rejects it
only when rows exist, so an unseeded database would let the exact schema change
the auto-migrate helper cannot perform sail straight through. And the read path
the verifier exercises returns an empty list rather than a row unless something
is there to read.

Environment:
    OE_UPGRADE_FROM_VERSION  Required. The release this interpreter must hold.
    DATABASE_URL             Required. Async URL of the empty target database.
    DATABASE_SYNC_URL        Required. Sync URL of the same database.
    OE_UPGRADE_AGED_STATE    Required. Path to write the handover JSON to.
    OE_UPGRADE_TABLE_FLOOR   Optional. Minimum table count, default 500.
                             Release 15.3.1 builds 624 oe_* tables; the floor
                             is there to catch a half-imported install, not to
                             track the exact number.

Exit code 0 on success, 1 on any failed check.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

# Credentials for the account this script seeds. They are read back by the
# verifier, which logs in with them to prove a real read path answers 200 and
# not 401. Throwaway, in a database that exists for the length of one CI job.
SEED_EMAIL = "upgrade-lane@datadrivenconstruction.io"
SEED_PASSWORD = "upgrade-lane-probe-1"


def fail(message: str) -> None:
    """Print a failure and leave immediately."""
    print(f"FAIL  {message}")
    sys.exit(1)


def main() -> int:
    expected_version = os.environ.get("OE_UPGRADE_FROM_VERSION", "").strip()
    sync_url = os.environ.get("DATABASE_SYNC_URL", "").strip()
    state_path = os.environ.get("OE_UPGRADE_AGED_STATE", "").strip()
    table_floor = int(os.environ.get("OE_UPGRADE_TABLE_FLOOR", "500"))

    if not expected_version:
        fail("OE_UPGRADE_FROM_VERSION is not set; without it nothing proves which release built this database")
    if not sync_url:
        fail("DATABASE_SYNC_URL is not set")
    if not state_path:
        fail("OE_UPGRADE_AGED_STATE is not set")

    # ── Provenance, before anything touches the database ────────────────────
    from importlib.metadata import version as dist_version

    installed = dist_version("openconstructionerp")
    if installed != expected_version:
        fail(f"this interpreter holds openconstructionerp {installed}, not the expected {expected_version}")
    print(f"OK    installed release is {installed}")

    import app

    app_root = Path(app.__file__).resolve().parent
    repo_backend = Path(__file__).resolve().parent.parent
    if repo_backend in app_root.parents or app_root == repo_backend / "app":
        fail(f"'app' resolved to the working tree at {app_root}; this would age a database to the CURRENT schema")
    print(f"OK    'app' resolves outside the working tree, at {app_root}")

    # ── Let the previous release build its own schema ───────────────────────
    from fastapi.testclient import TestClient

    from app.main import create_app

    print(f"..    booting openconstructionerp {installed} once against the empty database")
    with TestClient(create_app()) as client:
        response = client.get("/api/health")
        print(f"OK    the previous release booted and answered /api/health with {response.status_code}")

    # ── What the boot actually left behind ──────────────────────────────────
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    engine = sa.create_engine(sync_url, poolclass=sa.pool.NullPool)
    inspector = sa.inspect(engine)
    tables = sorted(inspector.get_table_names())
    app_tables = [t for t in tables if t.startswith("oe_")]
    print(f"OK    the aged database carries {len(app_tables)} oe_* tables")

    # A thin or half-broken install produces FEWER tables, and the current
    # code's create_all would then quietly supply the rest - a lane that
    # reports a healed upgrade when what it really did was a fresh install of
    # whatever was missing. The floor is the guard against that shape.
    if len(app_tables) < table_floor:
        fail(
            f"only {len(app_tables)} oe_* tables were created, below the floor of {table_floor}; "
            "the previous release's model imports did not all succeed, so this database is not "
            "a faithful copy of what that release builds"
        )

    aged_revision: str | None = None
    if "alembic_version" in tables:
        with engine.connect() as conn:
            aged_revision = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    print(f"OK    alembic revision recorded by the previous release: {aged_revision!r}")

    # ── Seed rows, through the previous release's own models ────────────────
    from app.modules.ncr.models import NCR
    from app.modules.projects.models import Project
    from app.modules.users.models import User
    from app.modules.users.service import hash_password

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    ncr_id = uuid.uuid4()
    with Session(engine) as session:
        session.add(
            User(
                id=user_id,
                email=SEED_EMAIL,
                hashed_password=hash_password(SEED_PASSWORD),
                full_name="Upgrade Lane",
                role="admin",
            )
        )
        session.flush()
        session.add(Project(id=project_id, name="Upgrade Lane Project", owner_id=user_id, currency="EUR"))
        session.flush()
        session.add(
            NCR(
                id=ncr_id,
                project_id=project_id,
                ncr_number="NCR-001",
                title="Row written by the previous release",
                description=(
                    "This row exists so the current code has to migrate a table that is not empty. "
                    "PostgreSQL accepts ADD COLUMN ... NOT NULL with no default on an empty table."
                ),
                ncr_type="workmanship",
                severity="major",
            )
        )
        session.commit()
    print("OK    seeded one user, one project and one NCR through the previous release's models")

    engine.dispose()

    state = {
        "aged_from_version": installed,
        "aged_revision": aged_revision,
        "app_table_count": len(app_tables),
        "user_id": str(user_id),
        "user_email": SEED_EMAIL,
        "user_password": SEED_PASSWORD,
        "project_id": str(project_id),
        "ncr_id": str(ncr_id),
    }
    Path(state_path).write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"OK    handover written to {state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
