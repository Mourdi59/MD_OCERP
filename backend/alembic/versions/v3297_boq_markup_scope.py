# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""boq: let a markup line be confined to a position and override a bill-wide one.

Adds two nullable columns to ``oe_boq_markup``:

* ``scope_position_id`` — the position (usually a section) the line is
  confined to, descendants included. NULL means bill-wide, which is what every
  row that exists today is.
* ``overrides_id`` — the bill-wide line a scoped line stands in for inside its
  own subtree, or NULL for a scoped line that adds something the bill-wide
  stack does not have.

Strictly additive and behaviour-preserving on every existing database. Both
columns arrive NULL on every row, and a bill with no scoped line takes exactly
the arithmetic it took before: one cascade over the whole direct cost. No total
moves. That property is deliberate and it is asserted in
``backend/tests/unit/test_boq_markup_scope.py``, because the alternative is a
silent repricing of every estimate already stored.

``GUID`` on this platform is ``VARCHAR(36)`` on every dialect (see the
``GUID`` TypeDecorator in ``app/database.py``), so both columns are
``sa.String(36)`` here rather than a native UUID. A native ``UUID`` column
would not join to the ``varchar(36)`` primary keys these foreign keys point
at.

``overrides_id`` is ``ON DELETE SET NULL``, not CASCADE: deleting the company
line should leave the section's own number standing as an ordinary scoped line
rather than delete a figure the estimator entered by hand.

Idempotent — inspector-guarded, so a re-run on a partially migrated database
skips whatever is already present.

Revision ID: v3297_boq_markup_scope
Revises: v3296_certified_payroll
Create Date: 2026-08-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3297_boq_markup_scope"
down_revision: Union[str, Sequence[str], None] = "v3296_certified_payroll"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_boq_markup"
_SCOPE = "scope_position_id"
_OVERRIDES = "overrides_id"


def upgrade() -> None:
    """Add the scope and override columns, their indexes and their keys."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    existing_idx = {i["name"] for i in inspector.get_indexes(_TABLE)}
    existing_fks = {fk.get("name") for fk in inspector.get_foreign_keys(_TABLE)}

    if _SCOPE not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _SCOPE,
                sa.String(length=36),
                nullable=True,
                comment=(
                    "Position this markup line is confined to, descendants included. "
                    "NULL = bill-wide, the company standard inherited by everything."
                ),
            ),
        )
    if _OVERRIDES not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _OVERRIDES,
                sa.String(length=36),
                nullable=True,
                comment=(
                    "Bill-wide markup line this scoped line replaces inside its own subtree. "
                    "NULL = the scoped line adds a step rather than replacing one."
                ),
            ),
        )

    if "ix_oe_boq_markup_scope_position_id" not in existing_idx:
        op.create_index("ix_oe_boq_markup_scope_position_id", _TABLE, [_SCOPE])
    if "ix_oe_boq_markup_overrides_id" not in existing_idx:
        op.create_index("ix_oe_boq_markup_overrides_id", _TABLE, [_OVERRIDES])

    if "fk_oe_boq_markup_scope_position" not in existing_fks:
        op.create_foreign_key(
            "fk_oe_boq_markup_scope_position",
            _TABLE,
            "oe_boq_position",
            [_SCOPE],
            ["id"],
            ondelete="CASCADE",
        )
    if "fk_oe_boq_markup_overrides" not in existing_fks:
        op.create_foreign_key(
            "fk_oe_boq_markup_overrides",
            _TABLE,
            _TABLE,
            [_OVERRIDES],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Drop the keys, indexes and columns, in that order."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    existing_idx = {i["name"] for i in inspector.get_indexes(_TABLE)}
    existing_fks = {fk.get("name") for fk in inspector.get_foreign_keys(_TABLE)}

    for name in ("fk_oe_boq_markup_overrides", "fk_oe_boq_markup_scope_position"):
        if name in existing_fks:
            op.drop_constraint(name, _TABLE, type_="foreignkey")
    for name in ("ix_oe_boq_markup_overrides_id", "ix_oe_boq_markup_scope_position_id"):
        if name in existing_idx:
            op.drop_index(name, table_name=_TABLE)
    for name in (_OVERRIDES, _SCOPE):
        if name in existing_cols:
            op.drop_column(_TABLE, name)
