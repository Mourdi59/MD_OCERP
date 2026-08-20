# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""site_logistics: book a delivery against the bill positions it carries.

Creates one table:

    oe_site_logistics_delivery_line - a quantity of one BOQ position on one
                                      delivery booking

Strictly additive: no existing table is altered and no existing row changes, so
a delivery booked before this migration simply carries no lines and every screen
reads exactly as it did.

``boq_position_id`` is ``ON DELETE SET NULL``, not CASCADE. A delivery is a
physical event that happened; deleting the estimate line it was booked against
must not erase the record that the material arrived. The line keeps its own
``position_ordinal`` / ``description`` snapshot and reads as detached from the
bill afterwards. This is also why the module needs no equivalent of
``BOQService._scrub_activity_position_refs``: the schedule module stores its
links in a JSON array and has to sweep dead ids out by hand, while a real
foreign key is maintained by the database inside the delete transaction.

``GUID`` on this platform is ``VARCHAR(36)`` on every dialect (the ``GUID``
TypeDecorator in ``app/database.py``), so the id columns are ``sa.String(36)``
here - a native UUID column would not join to the ``varchar(36)`` primary keys
these foreign keys point at.

The embedded-PostgreSQL runtime materialises the table via ``create_all`` at
startup, so this migration mainly serves external-PostgreSQL deployments that
manage schema with Alembic. Inspector-guarded, so a re-run (or a database the
runtime already auto-created) is a no-op.

Revision ID: v3299_site_logistics_delivery_line
Revises: v3298_design_option_refs
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3299_site_logistics_delivery_line"
down_revision: Union[str, Sequence[str], None] = "v3298_design_option_refs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_site_logistics_delivery_line"
_IX_DELIVERY = "ix_site_logistics_line_delivery"
_IX_POSITION = "ix_site_logistics_line_position"


def upgrade() -> None:
    """Create the delivery-line table with its two lookup indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE in inspector.get_table_names():
        return
    # The parent table must exist; on a database where the site-logistics
    # module was never installed there is nothing to hang the line off.
    if "oe_site_logistics_delivery" not in inspector.get_table_names():
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "delivery_id",
            sa.String(length=36),
            sa.ForeignKey("oe_site_logistics_delivery.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "boq_position_id",
            sa.String(length=36),
            sa.ForeignKey("oe_boq_position.id", ondelete="SET NULL"),
            nullable=True,
            comment=(
                "Bill position this line delivers. NULL either because the line "
                "was never linked, or because the position was deleted after the "
                "delivery was booked - position_ordinal tells the two apart."
            ),
        ),
        sa.Column("position_ordinal", sa.String(length=50), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(_IX_DELIVERY, _TABLE, ["delivery_id"])
    op.create_index(_IX_POSITION, _TABLE, ["boq_position_id"])


def downgrade() -> None:
    """Drop the indexes and the table, in that order."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    existing_idx = {i["name"] for i in inspector.get_indexes(_TABLE)}
    for name in (_IX_POSITION, _IX_DELIVERY):
        if name in existing_idx:
            op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
