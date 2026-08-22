# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""ncr: give a non-conformity a place, not just a description of one.

Adds three nullable columns to ``oe_ncr_ncr``.

``location_description`` has always been able to say "grid B4, level 2 slab
soffit". That reads well in a report and cannot be drawn on a map, so the
register and the project map have never been able to answer the same question.
These columns close that: an inspector who records a position gets a pin.

* ``location_lat`` / ``location_lon`` (NULLABLE, ``Numeric(10, 7)``) - WGS84,
  the same precision ``oe_geo_hub_anchor`` stores, so a pin and a project
  anchor round-trip at the same resolution and no comparison between them
  loses digits.
* ``location_accuracy_m`` (NULLABLE, ``Numeric(6, 2)``) - horizontal accuracy
  of the fix in metres. A phone GPS is tens of metres and a survey instrument
  is centimetres; recording which one it was is the difference between a pin
  you can dig next to and a pin you cannot.

All three are nullable with no server default, and that is the whole point.
NULL means "nobody recorded a position", which is honestly different from
0/0 - a real coordinate in the Gulf of Guinea, and exactly the value a NOT
NULL default would have written into every historical row. Every NCR that
exists before this revision comes out of it unlocated, which is what it is.

Strictly additive and behaviour-preserving: nothing reads these columns unless
they are populated, no existing row changes, and an NCR created without
coordinates behaves precisely as it did before.

There is no index. The columns are read per-row on the way to the map, never
filtered or sorted on, and an index on a column that is NULL for most of the
table would cost writes and buy nothing. Add one if a bbox query over NCRs
ever becomes a real access path.

Idempotent - inspector-guarded, so a re-run on a partially migrated database
skips whatever is already there.

Revision ID: v3301_ncr_location
Revises: v3300_formwork_system_choice
Create Date: 2026-08-21
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3301_ncr_location"
down_revision: Union[str, Sequence[str], None] = "v3300_formwork_system_choice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_ncr_ncr"
_LAT = "location_lat"
_LON = "location_lon"
_ACCURACY = "location_accuracy_m"


def upgrade() -> None:
    """Add the three location columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}

    if _LAT not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _LAT,
                sa.Numeric(precision=10, scale=7),
                nullable=True,
                comment="WGS84 latitude of the non-conformity. NULL = no position was recorded.",
            ),
        )
    if _LON not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _LON,
                sa.Numeric(precision=10, scale=7),
                nullable=True,
                comment="WGS84 longitude of the non-conformity. NULL = no position was recorded.",
            ),
        )
    if _ACCURACY not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _ACCURACY,
                sa.Numeric(precision=6, scale=2),
                nullable=True,
                comment="Horizontal accuracy of the fix in metres. NULL = not reported, not perfect.",
            ),
        )


def downgrade() -> None:
    """Drop the three columns, if they are there.

    This loses positions an inspector recorded in the field, which is the
    ordinary cost of reverting an additive revision. Nothing else moves: no
    NCR's status, number, severity or cost impact depends on these columns,
    and the code without this revision never asked for them.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    for column in (_ACCURACY, _LON, _LAT):
        if column in existing:
            op.drop_column(_TABLE, column)
