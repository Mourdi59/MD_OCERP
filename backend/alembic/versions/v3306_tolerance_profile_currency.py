# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""supplier_catalogs: the absolute price tolerance says which currency it is in.

A tolerance profile carries two price bands: a percentage and an absolute
floor, and the band applied to a variance is the wider of the two. The
percentage is safe anywhere, because a percentage of the order total is
already denominated in the order's own currency. The floor was a bare number
with no currency recorded anywhere, and a profile is selected by name and
applied to purchase orders in every currency the tenant trades in. The column
comment above it read "absolute (currency)" while no such column existed.

Why the direction of the error matters
--------------------------------------
A floor that is too small relative to the order's currency never wins the
``max`` and changes nothing. A floor that is too large widens the band, and
the invoice is auto-matched and approved for payment with no exception raised
and nothing written down. The failure that costs money is the silent one.

This is a different question from the invoice-versus-order currency guard that
already exists in ``match_invoice``. That guard compares two documents and
declines when they disagree. An order and its invoice can agree perfectly and
still be measured against a floor written in a third currency, which that
guard never looks at.

Two cases, and the ambiguous one is empty
-----------------------------------------
There is no way to recover the currency of an existing floor by joining: a
profile is global and has no order to inherit from. But it does not need one
in the only case that ships. A floor of zero is the same amount of money in
every currency, ``max(percentage, 0)`` is the percentage, and NULL loses
nothing. Only a nonzero unlabelled floor is unrecoverable.

On a stock installation there are none, and that is measured rather than
assumed: no migration inserts a profile row, and
``ensure_default_tolerance_profile`` - which would, with a floor of zero - is
called by no application code. A nonzero floor can only arrive through
``POST /tolerance-profiles``. So the upgrade counts them and says so instead
of guessing.

Where a tenant has configured one, the floor is dropped at match time until
they label it, and ``MatchResult.absolute_tolerance_state`` reports
``dropped_unlabelled`` so the reason is visible. Dropping it narrows the band,
which turns a silent approval into an exception a human reviews. That is the
safe direction to fail in, but it is a behaviour change for that tenant, which
is why the count below is logged rather than passed over.
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3306_tolerance_profile_currency"
down_revision: Union[str, Sequence[str], None] = "v3305_crm_forecast_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_supplier_catalogs_tolerance_profile"


def upgrade() -> None:
    # DDL plus one SELECT. No existing row is rewritten: every profile keeps
    # the floor it had, and the new column arrives NULL, which is the only
    # honest thing to say about a number whose currency was never recorded.
    # Inspector-guarded, like the revisions around it. The default runtime
    # builds its schema with create_all and stamps afterwards, so on that
    # install this column already exists and an unguarded add_column raises
    # DuplicateColumn, which aborts the upgrade at this revision.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    if "currency" not in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.add_column(_TABLE, sa.Column("currency", sa.String(length=3), nullable=True))

    # Report the ambiguous bucket rather than assume it is empty. It is empty
    # on a stock installation, but this runs on tenant databases and the whole
    # point of the column is that somebody may have configured a floor.
    unlabelled = (
        op.get_bind()
        .execute(
            sa.text(f"SELECT count(*) FROM {_TABLE} WHERE price_tolerance_abs > 0"),  # noqa: S608
        )
        .scalar_one()
    )
    if unlabelled:
        logging.getLogger("alembic").warning(
            "%s profile(s) carry a nonzero price_tolerance_abs with no currency. "
            "Their absolute floor is now ignored at match time and reported as "
            "dropped_unlabelled, so those matches use the percentage band alone "
            "until a currency is set on the profile. This narrows the band, it "
            "does not widen it.",
            unlabelled,
        )


def downgrade() -> None:
    op.drop_column(_TABLE, "currency")
