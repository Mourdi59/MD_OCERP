# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""formwork: describe a system as a choice, not only as a price.

Adds three columns to ``oe_formwork_system``. The catalogue could already say
what a system COSTS; it could not say what you were choosing between, which is
why the page offered a list of names and no basis for picking one.

* ``rate_basis`` (NOT NULL, default ``'purchase'``) - what ``unit_rate`` means.
  A purchase rate buys the panels and amortises over the reuse count; a per-use
  hire rate and an all-in supply-and-fix subcontract rate are already per use
  and must not be divided again. This is the only one of the three that changes
  the arithmetic, and ``'purchase'`` is exactly the behaviour every existing row
  was priced with, so no stored total moves.
* ``typical_reuses`` (NULLABLE) - the planning figure, as opposed to
  ``reuses_max``, which is the physical limit the panels survive. Deliberately
  nullable: NULL reads as "no published figure", which is honestly different
  from zero, and every row that exists today has no published figure.
* ``cycle_days`` (NOT NULL, default ``0``) - the pour-to-pour turnaround. NOT
  the same as ``strip_time_days``, which is only the floor: striking is when
  the panels CAN come off, the cycle also carries clean, move, set and align.

Strictly additive and behaviour-preserving. Every existing row lands on
``rate_basis='purchase'``, ``typical_reuses=NULL``, ``cycle_days=0``, and
``compute_cost`` on a purchase basis is byte-for-byte the formula it ran
before this revision. Nothing is re-priced.

Both halves of every NOT NULL default are present - the Python-side ``default``
in ``app/modules/formwork/models.py`` and the ``server_default`` here. The
model docstring names the v3119 fresh-install cascade as what happens when only
one half lands, so they are kept in step deliberately rather than by habit.

``server_default`` is left ON the columns rather than dropped after backfill.
For a small catalogue table there is nothing to gain by removing it, and
leaving it means a raw-SQL insert that predates the columns still succeeds.

Idempotent - inspector-guarded, so a re-run on a partially migrated database
skips whatever is already present.

Revision ID: v3300_formwork_system_choice
Revises: v3299_site_logistics_delivery_line
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3300_formwork_system_choice"
down_revision: Union[str, Sequence[str], None] = "v3299_site_logistics_delivery_line"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_formwork_system"
_RATE_BASIS = "rate_basis"
_TYPICAL = "typical_reuses"
_CYCLE = "cycle_days"
_RATE_BASIS_INDEX = "ix_oe_formwork_system_rate_basis"


def upgrade() -> None:
    """Add the three choice columns and the rate-basis index."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    existing_idx = {i["name"] for i in inspector.get_indexes(_TABLE)}

    if _RATE_BASIS not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _RATE_BASIS,
                sa.String(length=20),
                nullable=False,
                server_default="purchase",
                comment=(
                    "What unit_rate means: purchase (amortises over the reuses), "
                    "hire_per_use or subcontract (already per use, never divided)."
                ),
            ),
        )
    if _TYPICAL not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _TYPICAL,
                sa.Integer(),
                nullable=True,
                comment=(
                    "Planning reuse figure. NULL = no published figure, which is "
                    "not the same as zero. reuses_max stays the physical limit."
                ),
            ),
        )
    if _CYCLE not in existing_cols:
        op.add_column(
            _TABLE,
            sa.Column(
                _CYCLE,
                sa.Numeric(precision=6, scale=2),
                nullable=False,
                server_default="0",
                comment=(
                    "Pour-to-pour turnaround in days. strip_time_days is its "
                    "floor, not its value: the cycle also carries clean and set."
                ),
            ),
        )

    # The chooser filters the catalogue by how the rate is quoted, so this is a
    # read path rather than a reporting one. Cheap on a table this size either
    # way; the index exists because the model declares ``index=True`` and a
    # migration that disagreed with the model would show up as spurious
    # autogenerate churn on every later revision.
    if _RATE_BASIS_INDEX not in existing_idx:
        op.create_index(_RATE_BASIS_INDEX, _TABLE, [_RATE_BASIS])


def downgrade() -> None:
    """Drop the three columns and the index, if they are there.

    Losing ``typical_reuses`` and ``cycle_days`` loses catalogue data a tenant
    typed, which is the ordinary cost of reverting an additive revision. No
    priced total changes on the way back down: every row already prices as a
    purchase basis, and that is what the code without this revision assumes.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns(_TABLE)}
    existing_idx = {i["name"] for i in inspector.get_indexes(_TABLE)}

    if _RATE_BASIS_INDEX in existing_idx:
        op.drop_index(_RATE_BASIS_INDEX, table_name=_TABLE)
    for column in (_CYCLE, _TYPICAL, _RATE_BASIS):
        if column in existing_cols:
            op.drop_column(_TABLE, column)
