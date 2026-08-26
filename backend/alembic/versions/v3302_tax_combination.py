# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""tax: make a rate say how it combines with the federal rate, instead of implying it.

Adds one NOT NULL column, ``combination``, to ``oe_i18n_tax_config``.

The table has always been able to hold a sub-national rate - the province
lives in ``tax_code`` - and has never been able to say what to do with two
rates from the same country. In Canada that difference is not decorative:

* a harmonised provincial rate REPLACES the federal one. Ontario's HST is
  13 %, and adding the federal 5 % on top gives an 18 % invoice.
* a separate provincial rate STACKS on the federal one. British Columbia is
  5 + 7 = 12 %, and reading the 7 % alone understates it.

Both are ``tax_type='gst'`` and ``tax_type='sales_tax'`` respectively, but
that separation is an accident of Canadian naming rather than a rule anything
enforces, so it cannot be relied on. Before this revision the only place the
distinction existed was in the head of whoever wrote the calling code, and
the obvious implementation - federal plus my province - is correct in a
stacking province and wrong in a harmonised one. A bug that is right in the
province you tested in is a bug that ships.

The column takes one of four values, and there are four rather than three
because the federal row is neither of the provincial answers and a boolean
would have forced it into one:

* ``national`` - the country has no federal/provincial split in our data.
* ``federal`` - the country-wide rate itself.
* ``replaces_federal`` - supersedes the federal row (Canadian HST).
* ``stacks_on_federal`` - adds to the federal row (Canadian QST, PST, RST).

NOT NULL, and deliberately so. There is no "unspecified" member, because an
absent value is exactly what let a reader supply the obvious guess. Existing
rows are backfilled explicitly by country and tax code rather than being left
to the server default: the default writes ``national``, which is right for the
sixty-six rows that are, and would be wrong for the thirteen Canadian and
United States rows that are not. The backfill names them.

Two countries are touched. Canada, where the four-way distinction is live
today. And the United States, whose ``NONE`` row is named "No Federal Sales
Tax" in its own translations - it exists to state that the federal layer is
zero, which is what a state rate adds to - so it is ``federal`` and the
California row ``stacks_on_federal``. Hong Kong's identically shaped ``NONE``
row stays ``national``, because nothing sits alongside it.

Nothing computes a combined rate yet, so no behaviour changes on upgrade.
What changes is that a caller can now be written correctly, and a test can
convict one that is not.

Idempotent - inspector-guarded, so a re-run on a partially migrated database
skips what is already there.

Revision ID: v3302_tax_combination
Revises: v3301_ncr_location
Create Date: 2026-08-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3302_tax_combination"
down_revision: Union[str, Sequence[str], None] = "v3301_ncr_location"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_i18n_tax_config"
_COLUMN = "combination"

# Backfill for rows written before this revision. Keyed on country plus tax
# code, which is the only place the sub-national identity has ever lived.
# Note LIKE 'HST%' rather than 'HST\_%': the underscore is a LIKE wildcard,
# and the looser pattern is safe here because no other Canadian code starts
# with those three letters.
_BACKFILL: tuple[tuple[str, str], ...] = (
    ("federal", "country_code = 'CA' AND tax_code = 'GST'"),
    ("replaces_federal", "country_code = 'CA' AND tax_code LIKE 'HST%'"),
    (
        "stacks_on_federal",
        "country_code = 'CA' AND (tax_code LIKE 'QST%' OR tax_code LIKE 'PST%' OR tax_code LIKE 'RST%')",
    ),
    ("federal", "country_code = 'US' AND tax_code = 'NONE'"),
    ("stacks_on_federal", "country_code = 'US' AND tax_code = 'CA_SALES'"),
)

# data-rewrite-ack: table=oe_i18n_tax_config growth=bounded rows=79 as shipped, one per
# boot-repair: gap - backfills the new combination column on the shipped tax rows; the boot seeder skips the table entirely once it holds any row, so an upgraded install keeps rates that cannot say how they combine
# jurisdiction we carry a rate for; a deployment adds a row only when it adds a
# jurisdiction by hand, so the count tracks the catalogue rather than how long the
# install has run. Every row is rewritten, which is the point: the column is being
# introduced, so there is no row that already carries a correct value to preserve.
# The two statements are ordered narrowest first, the explicit sub-national cases
# and then a sweep of whatever is still NULL to the default, so a row matched by
# the first is never reconsidered by the second.


def upgrade() -> None:
    """Add ``combination``, backfill it explicitly, then make it NOT NULL."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing:
        # Added nullable first. Adding it NOT NULL in one step is the shape
        # that has silently landed as NULLABLE in this repo before, and every
        # health signal called that a clean upgrade.
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(length=20),
                nullable=True,
                server_default="national",
                comment="How this rate combines with the federal rate of the same country.",
            ),
        )

    for value, predicate in _BACKFILL:
        op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = '{value}' WHERE {predicate}")  # noqa: S608

    # Anything the seed wrote before the column existed, and any row a
    # deployment added by hand, is national by construction of the default.
    op.execute(f"UPDATE {_TABLE} SET {_COLUMN} = 'national' WHERE {_COLUMN} IS NULL")

    op.alter_column(
        _TABLE,
        _COLUMN,
        existing_type=sa.String(length=20),
        nullable=False,
        existing_server_default="national",
    )


def downgrade() -> None:
    """Drop the column, if it is there.

    This loses the distinction between a provincial rate that replaces the
    federal one and a provincial rate that adds to it, which returns the
    database to the state where that distinction lives only in the head of
    whoever writes the caller. The rates themselves are untouched.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
