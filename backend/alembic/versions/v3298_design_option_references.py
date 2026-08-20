# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design options — reference the project's schedule and carbon work.

A design option could only ever hold a model and the bill generated from it, so
the comparison could only ever answer what an alternative costs. This adds the
two references that let it answer the other questions a client asks of a design
alternative — when it finishes and what it emits — plus the figures read off
them, and a marker saying whether the option's bill was generated here or linked
from an estimate the project already held.

Strictly additive: seven nullable/defaulted columns on
``oe_design_options_option`` and two indexes. No existing column is touched and
no data is rewritten, so an option that predates this migration reads exactly as
it did, with every new figure at its "not answered" value.

Idempotent — inspector-guarded, so a re-run against a partially migrated
database skips whatever is already there.

Revision ID: v3298_design_option_refs
Revises: v3298_estimate_basis_class, v3298_teams_roster
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.database import GUID

# revision identifiers, used by Alembic.
revision: str = "v3298_design_option_refs"
# Two sibling revisions landed on ``v3297_boq_markup_scope`` at the same time, so
# this one chains after both and closes the fan-out rather than adding a third
# tip. Merging here touches no other revision's file; the alternative was three
# heads, which stops ``alembic upgrade head`` outright.
down_revision: Union[str, Sequence[str], None] = ("v3298_estimate_basis_class", "v3298_teams_roster")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_design_options_option"

# (column, type, server_default). Cross-module references are plain GUID-width
# strings with no foreign key, matching how the option already stores its BIM
# model and BOQ ids; the figures are Decimal-as-string like every other number
# on this table.
_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("schedule_id", GUID(), None),
    ("carbon_inventory_id", GUID(), None),
    ("boq_source", sa.String(length=20), ""),
    ("duration_days", sa.String(length=20), "0"),
    ("finish_date", sa.String(length=40), ""),
    ("embodied_carbon_kg", sa.String(length=50), "0"),
    ("carbon_per_m2", sa.String(length=50), "0"),
)

_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_oe_design_options_option_schedule_id", "schedule_id"),
    ("ix_oe_design_options_option_carbon_inventory_id", "carbon_inventory_id"),
)


def _existing_columns(inspector: sa.Inspector) -> set[str]:
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def _existing_indexes(inspector: sa.Inspector) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes(_TABLE)}


def upgrade() -> None:
    """Add the reference columns and their indexes, skipping what already exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        # The module's own table is created by the metadata bootstrap on a fresh
        # install, where these columns arrive with it. Nothing to widen.
        return

    present = _existing_columns(inspector)
    for name, type_, default in _COLUMNS:
        if name in present:
            continue
        op.add_column(
            _TABLE,
            sa.Column(
                name,
                type_,
                nullable=default is None,
                server_default=default,
            ),
        )

    inspector = sa.inspect(bind)
    indexes = _existing_indexes(inspector)
    columns = _existing_columns(inspector)
    for index_name, column_name in _INDEXES:
        if index_name in indexes or column_name not in columns:
            continue
        op.create_index(index_name, _TABLE, [column_name])


def downgrade() -> None:
    """Drop the reference columns and their indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    indexes = _existing_indexes(inspector)
    for index_name, _column_name in _INDEXES:
        if index_name in indexes:
            op.drop_index(index_name, table_name=_TABLE)

    present = _existing_columns(inspector)
    for name, _type, _default in _COLUMNS:
        if name in present:
            op.drop_column(_TABLE, name)
