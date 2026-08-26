# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""diary_labour_published: mark the entries whose hours already reached cost.

Diary work hours used to be handed to the labour cost flow when the entry was
submitted. Submitting says the worker has finished writing, not that anyone has
checked what they wrote, and these hours land straight on a budget line's
``actual_amount``. They now go out on approval instead, which is the rule the
desktop timesheet has always had.

That move needs a mark, otherwise every entry already submitted under the old
behaviour would publish a second time the moment somebody approved it. The
project would then carry those hours twice with nothing on screen to explain
the difference, and the first approval a user ever performed would be the thing
that broke their numbers.

``oe_field_diary_entry.labour_published_at`` is that mark, backfilled from
``submitted_at`` for every entry that reached ``submitted`` or ``approved``.
Under the old code reaching either status is exactly what published the hours,
so the backfill is a statement of what already happened rather than a guess.
Entries still in ``draft`` never published and stay null.

An entry with no ``submitted_at`` but a submitted status is stamped with
``approved_at`` and failing that with ``updated_at``, because the mark only has
to be non-null to mean "already counted" - the timestamp is for a human reading
the row later.

Revision ID: v3286_diary_labour_published
Revises: v3285_requirements_cycle
Create Date: 2026-08-11
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3286_diary_labour_published"
down_revision: Union[str, Sequence[str], None] = "v3285_requirements_cycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_ENTRY = "oe_field_diary_entry"
_COLUMN = "labour_published_at"


def _columns(table: str) -> set[str]:
    """Column names on ``table`` (empty when the table does not exist)."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


# data-rewrite-ack: table=oe_field_diary_entry growth=tenure rows=one row per field diary entry, accumulates daily across every project
# boot-repair: gap - marks the diary entries whose hours already reached cost so approval cannot publish them twice; without it the first approval on an upgraded install republishes hours already posted
def upgrade() -> None:
    present = _columns(_ENTRY)
    if not present or _COLUMN in present:
        return

    op.add_column(_ENTRY, sa.Column(_COLUMN, sa.DateTime(timezone=True), nullable=True))

    marked = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
                UPDATE {_ENTRY}
                   SET {_COLUMN} = COALESCE(submitted_at, approved_at, updated_at)
                 WHERE status IN ('submitted', 'approved')
                   AND {_COLUMN} IS NULL
                """
            )
        )
        .rowcount
    )
    if marked:
        logger.info(
            "diary_labour_published: marked %s entries whose hours were already costed on submit",
            marked,
        )


def downgrade() -> None:
    if _COLUMN in _columns(_ENTRY):
        op.drop_column(_ENTRY, _COLUMN)
