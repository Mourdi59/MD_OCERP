# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Backfill addresses on demo projects created before the v3.2.0 seed update.

Before v3.2.0 (2026-05-16) the demo-project seed did not write the
``address`` column, so every project created from a fresh install on a
v3.0.x / v3.1.x build has ``address IS NULL``. The project-card map on
the /projects page used to gate rendering on ``mapEnabled && address``
(now dropped in v5.4.4), and the project-detail Map+Weather panel still
hides itself entirely when the project has no address. Both surfaces
went silent for users who never re-seeded.

This migration repairs the data side: when a project carries our
``is_demo = true`` marker AND its ``metadata.demo_id`` matches one of
the five canonical templates, populate ``address`` with the same dict
the current seed would write. Non-demo projects are NEVER touched —
the migration won't guess addresses for user-created records.

Idempotent: only UPDATEs rows where ``address IS NULL``. Re-running is
safe; rows the user has since populated keep their values.

SQLite + PostgreSQL — both store the column as JSON / JSONB, so we use
``sa.text()`` with bind parameters that SQLAlchemy will serialise via
the column's JSON type on either engine.

Revision ID: v3145_demo_project_addresses
Revises: v3144_audit_log_extend
Create Date: 2026-05-28
"""

from __future__ import annotations

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3145_demo_project_addresses"
down_revision: Union[str, None] = "v3144_audit_log_extend"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "oe_projects"

# Canonical addresses keyed by ``metadata.demo_id`` — copied verbatim
# from ``backend/app/core/demo_projects.py`` (search for ``address=``).
# Keeping them hardcoded here means the migration is hermetic and won't
# break if the template file is later moved or restructured.
_DEMO_ADDRESSES: dict[str, dict[str, object]] = {
    "residential-berlin": {
        "street": "Chausseestraße 45",
        "city": "Berlin",
        "postcode": "10115",
        "country": "Germany",
        "lat": 52.5316,
        "lng": 13.3766,
    },
    "office-london": {
        "street": "1 Canada Square",
        "city": "London",
        "postcode": "E14 5AB",
        "country": "United Kingdom",
        "lat": 51.5054,
        "lng": -0.0235,
    },
    "medical-us": {
        "street": "350 W 14th St",
        "city": "Cleveland",
        "state": "Ohio",
        "postcode": "44113",
        "country": "United States",
        "lat": 41.4847,
        "lng": -81.6953,
    },
    "warehouse-dubai": {
        "street": "Jebel Ali Free Zone",
        "city": "Dubai",
        "country": "United Arab Emirates",
        "lat": 25.0150,
        "lng": 55.0612,
    },
    "school-paris": {
        "street": "Rue de Belleville 120",
        "city": "Paris",
        "postcode": "75020",
        "country": "France",
        "lat": 48.8740,
        "lng": 2.3833,
    },
}


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    return table in sa.inspect(bind).get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


# Dead guard, tracked as #144: no migration has ever created a table named
# "oe_projects" (the model's __tablename__ has been "oe_projects_project"
# since it was introduced), so _table_exists(bind, _TABLE) below is always
# False and the backfill below it has never executed on any database. Do
# not "fix" this by changing the literal - this revision is applied history
# on every install that reached it, and an edited v3145 never re-runs there
# (a fresh install has no pre-3.2.0 demo projects to repair either). Any
# real fix has to be a new forward revision at head, targeting
# oe_projects_project - and it needs its own reference addresses, not the
# ones hardcoded below: read against the live demo box (2026-08-12) showed
# the current demo_projects.py seed no longer agrees with _DEMO_ADDRESSES
# (e.g. medical-us is Houston in the live seed, Cleveland here), so copying
# them into a forward fix would repair one defect by writing another. No
# NULL address turned up on that box - but every demo project there was
# created after the 2026-05-16 seed fix, so it cannot speak for an install
# seeded before 3.2.0 and never reseeded, which is the population this
# guard was meant to repair and the only one this repo cannot inspect.
# Read this as cannot-reproduce-on-the-only-install-we-can-check, not as
# not-a-bug: the question stays open, and no forward revision gets written
# on evidence that never covered the population it would be fixing.
# data-rewrite-ack: table=oe_projects growth=dead-code rows=#144: guard above is always False (table never existed), statement has never executed on any database this repo can inspect
# boot-repair: none - the statement names oe_projects and the projects table is oe_projects_project, so it rewrites nothing on any current schema; its own data-rewrite-ack already classifies this dead-code
def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        logger.info("v3145: %s table absent, skipping demo address backfill.", _TABLE)
        return
    if not _column_exists(bind, _TABLE, "address"):
        logger.info("v3145: %s.address column absent, skipping.", _TABLE)
        return
    if not _column_exists(bind, _TABLE, "metadata"):
        logger.info("v3145: %s.metadata column absent, skipping.", _TABLE)
        return

    # Bulk-fetch every demo project lacking an address; iterate in
    # Python so we can dispatch by demo_id without writing one UPDATE
    # per template. The result set is tiny (5 demo templates × any
    # number of multi-tenant seedings — still measured in tens).
    rows = bind.execute(sa.text("SELECT id, metadata FROM oe_projects WHERE address IS NULL")).fetchall()

    updated = 0
    for row in rows:
        project_id = row[0]
        metadata_raw = row[1]
        meta: dict[str, object] = {}
        if isinstance(metadata_raw, dict):
            meta = metadata_raw
        elif isinstance(metadata_raw, str) and metadata_raw:
            try:
                parsed = json.loads(metadata_raw)
                if isinstance(parsed, dict):
                    meta = parsed
            except (TypeError, ValueError):
                meta = {}
        if not meta.get("is_demo"):
            continue
        demo_id = meta.get("demo_id")
        if not isinstance(demo_id, str):
            continue
        canonical = _DEMO_ADDRESSES.get(demo_id)
        if canonical is None:
            continue
        bind.execute(
            sa.text("UPDATE oe_projects SET address = :addr WHERE id = :pid").bindparams(
                sa.bindparam("addr", value=json.dumps(canonical), type_=sa.JSON()),
                sa.bindparam("pid", value=project_id),
            )
        )
        updated += 1

    if updated:
        logger.info("v3145: backfilled address on %d demo project(s).", updated)
    else:
        logger.info("v3145: no demo projects required address backfill.")


def downgrade() -> None:
    # Intentionally one-way — the backfill is a data correction, not a
    # schema change, and rolling back would re-NULL addresses that
    # users may have edited since the upgrade.
    pass
