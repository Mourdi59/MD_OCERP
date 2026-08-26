"""Add a monotonic ``seq`` to ``oe_progress_entry`` so "latest wins" is well defined.

Progress entries are append-only: a mistake is corrected by recording a new
entry, and the reading that counts is the latest one. That rule had no reliable
ordering key behind it.

``recorded_at`` defaults to ``now()``, and in PostgreSQL ``now()`` is the
TRANSACTION timestamp - every row written by one transaction carries exactly the
same value, by design rather than by coincidence. ``created_at`` is a per-row
Python ``datetime.now()`` whose granularity is about 1 ms on Windows against
about 1 ns on Linux, so on a coarse clock rows inserted in one flush share it
too. With both tied the winner fell through to the primary key, a random uuid4.
The ordering was stable but arbitrary: a re-imported corrections file, where
every row lands in one transaction, picked its winner by uuid sort. The old
MAX(percent_complete) rule at least failed predictably (always the most
optimistic reading); ordering by uuid trades that for a coin toss.

``seq`` is assigned by the database on INSERT and strictly increases, which is
the only thing in the table that can order rows written inside one transaction.

Two alternatives were considered and rejected, because they are what the next
person will reach for:

* ``ctid`` - the physical row location. Monotonic for plain appends, but VACUUM
  FULL, pg_repack and any UPDATE rewrite it, so an ordering built on it changes
  under maintenance that is supposed to be invisible.
* ``xmin`` - the inserting transaction id. Identical for every row written by
  one transaction, which is precisely the case this column exists to resolve,
  and it wraps around.

Backfill is explicit and deterministic: existing rows are numbered by
``recorded_at, created_at, id``, the best order the historical data can still be
said to have, so the sequence agrees with it rather than with physical layout.
The identity sequence then restarts above the highest backfilled value.

Inspector-guarded so re-running on an already-migrated DB is a no-op.

Revision ID: v3258_progress_entry_seq
Revises: v3257_takeoff_scale_source
Create Date: 2026-07-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3258_progress_entry_seq"
down_revision: Union[str, Sequence[str], None] = "v3257_takeoff_scale_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "oe_progress_entry"
_COLUMN = "seq"
_SEQUENCE = "oe_progress_entry_seq_seq"
_INDEXES = (
    ("ix_progress_entry_position_seq", ["boq_position_id", "seq"]),
    ("ix_progress_entry_project_seq", ["project_id", "seq"]),
)


# data-rewrite-ack: table=oe_progress_entry growth=tenure rows=daily/periodic site progress log, the textbook tenure-tracking shape
# boot-repair: boot-path=backend/app/modules/progress/seq_repair.py::repair_progress_entry_seq
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _TABLE not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_cols:
        # Nullable first: the table may already hold rows, and they need a
        # deterministic number before the column can be NOT NULL.
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.BigInteger(), nullable=True))

        op.execute(
            sa.text(
                f"""
                UPDATE {_TABLE} AS e
                SET {_COLUMN} = ranked.rn
                FROM (
                    SELECT id,
                           row_number() OVER (ORDER BY recorded_at, created_at, id) AS rn
                    FROM {_TABLE}
                ) AS ranked
                WHERE e.id = ranked.id
                """
            )
        )

        op.alter_column(_TABLE, _COLUMN, nullable=False)

        # A named sequence with a DEFAULT, matching exactly what create_all
        # builds from the model. The two schema paths must agree: a database
        # built by create_all and one built by Alembic have to be the same
        # shape, or "latest wins" holds on one and not the other.
        op.execute(sa.text(f"CREATE SEQUENCE IF NOT EXISTS {_SEQUENCE} OWNED BY {_TABLE}.{_COLUMN}"))
        op.execute(sa.text(f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} SET DEFAULT nextval('{_SEQUENCE}')"))

        # Start the sequence above the highest backfilled value; the third
        # argument false makes the NEXT nextval() return exactly this number.
        next_value = bind.execute(sa.text(f"SELECT COALESCE(MAX({_COLUMN}), 0) + 1 FROM {_TABLE}")).scalar() or 1
        op.execute(sa.text(f"SELECT setval('{_SEQUENCE}', {int(next_value)}, false)"))

        op.create_unique_constraint(f"uq_progress_entry_{_COLUMN}", _TABLE, [_COLUMN])

    existing_indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    for name, columns in _INDEXES:
        if name not in existing_indexes:
            op.create_index(name, _TABLE, columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _TABLE not in inspector.get_table_names():
        return

    existing_indexes = {i["name"] for i in inspector.get_indexes(_TABLE)}
    for name, _columns in _INDEXES:
        if name in existing_indexes:
            op.drop_index(name, table_name=_TABLE)

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_cols:
        # OWNED BY means dropping the column drops the sequence with it.
        op.drop_column(_TABLE, _COLUMN)
    op.execute(sa.text(f"DROP SEQUENCE IF EXISTS {_SEQUENCE}"))
