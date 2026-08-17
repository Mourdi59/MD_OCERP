# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""defects liability - the legal regime a warranty period came from.

Adds a nullable ``limitation_regime`` to ``oe_dlp_warranty``.

A warranty entry has always carried a period (``warranty_months``,
``warranty_end_date``) and never carried a statement of what produced it. In
Germany that omission decides claims: where the parties agreed the VOB/B the
limitation period for defect claims in building works is four years, and where
they did not the BGB gives five. A register that shows a date without its reason
cannot be checked, and being a year out is the difference between a claim that
can still be brought and one that cannot.

NULL is the point of the column, not an oversight. It means nobody chose a
regime, which is the state every existing row is in and stays in: no period is
derived for it, no date is rewritten, no validation finding is raised and the
screen shows no regime column and no badge. A team working under a legal system
with no such regime is never asked to pick one. There is deliberately no server
default, because a default would be this platform choosing one country's law for
every project on earth.

The column is a plain VARCHAR rather than a DB enum, matching the warranty-type
and status columns beside it, so adding a regime later never needs a schema
change. The vocabulary lives in app.modules.defects_liability.limitation and is
enforced at the API edge.

``dlp_end_date`` is deliberately untouched by any of this. It decides when
retention money is released and is contractual rather than statutory, so a
statutory limitation period never moves it; the regime derives
``warranty_months`` and ``warranty_end_date`` only.

Inspector-guarded in both directions so a fresh install, whose tables env.py
already built through ``Base.metadata.create_all``, hits an idempotent no-op.
Additive: no existing column is altered and no existing row is written.

Revision ID: v3295_dlp_warranty_limitation_regime
Revises: v3294_field_time_working_time_record
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v3295_dlp_warranty_limitation_regime"
down_revision = "v3294_field_time_working_time_record"
branch_labels = None
depends_on = None

_TABLE = "oe_dlp_warranty"
_COLUMN = "limitation_regime"


def _table_state() -> tuple[bool, bool]:
    """Whether the warranty table exists, and whether it already has the column."""
    insp = sa.inspect(op.get_bind())
    if _TABLE not in insp.get_table_names():
        return False, False
    return True, any(col["name"] == _COLUMN for col in insp.get_columns(_TABLE))


def upgrade() -> None:
    """Add the nullable limitation-regime column."""
    has_table, has_column = _table_state()
    if not has_table or has_column:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=30), nullable=True))


def downgrade() -> None:
    """Drop the limitation-regime column."""
    has_table, has_column = _table_state()
    if not has_table or not has_column:
        return
    op.drop_column(_TABLE, _COLUMN)
