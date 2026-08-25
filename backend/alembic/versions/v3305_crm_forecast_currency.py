# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""crm: the forecast snapshot keeps the currency breakdown it always computed.

``compute_forecast`` produces four money scalars and two currency fields.
``compute_and_store_forecast`` copied the scalars onto the ``Forecast`` row and
dropped ``by_currency`` and ``mixed_currency``, because there was nowhere to put
them. This adds the two columns.

The reason it mattered is not that a value went missing. ``ForecastResponse``
declared both fields with defaults - ``[]`` and ``False`` - so that
``model_validate()`` over a row that lacked them kept working. It did keep
working: ``GET /forecasts/{period}`` and ``POST /forecasts/compute`` answered
``mixed_currency: false`` and ``by_currency: []`` on every call, for every
period, whatever the deals said. A forecast blending three currencies reported
itself as single-currency with an empty breakdown, and the one field built to
warn about that was the field asserting there was nothing to warn about.

Both columns are nullable, and that is deliberate rather than convenient. A row
written before today was never checked, and ``NULL`` says so. ``False`` on a
field named ``mixed_currency`` is not an absence, it is an assurance.

No backfill, and the reason is the same one that stops other repairs in this
tree
--------------------------------------------------------------------------
The values could be recomputed - ``compute_forecast`` is pure and still there -
but recomputing them now would not reconstruct what these rows meant. A
forecast is a snapshot taken at ``computed_at``, over the opportunities as they
stood on that day. Deals have since closed, moved quarter, changed value and
changed currency. Running the computation today produces a correct forecast for
today and silently writes it into a row dated months ago, next to four scalars
that still describe the original run.

That is worse than leaving the columns empty, because the row would then look
complete while its halves described different days. So old rows stay NULL and
read as "not checked".

They do not fill themselves, and that is also deliberate. ``get_forecast``
returns a stored row untouched when one exists, so ``GET /forecasts/{period}``
- the wide-permission path, ``crm.read`` - will keep answering
``mixed_currency: null`` for an old period indefinitely. Only an explicit
``POST /forecasts/compute`` (``crm.compute_forecast``) recomputes and fills
them. Making the read recompute instead would be backfill on demand, and it
fails for the same reason the backfill does: it would run today's
opportunities into a row dated months ago. A null that persists until someone
asks for a fresh computation is the honest answer here.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3305_crm_forecast_currency"
down_revision: Union[str, Sequence[str], None] = "v3304_stock_balance_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_crm_forecast"


def upgrade() -> None:
    # Pure DDL. Nothing reads or rewrites an existing row, so there is no
    # data-rewrite acknowledgement to make and no transaction-size question to
    # ask: both columns arrive NULL and stay NULL until a period is recomputed.
    #
    # Inspector-guarded, like the revisions around it. The default runtime
    # builds its schema with create_all and stamps afterwards, so on that
    # install every column here already exists and an unguarded add_column
    # raises DuplicateColumn, which aborts the whole upgrade at this revision
    # and leaves everything after it unapplied.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns(_TABLE)}

    if "by_currency" not in existing:
        op.add_column(_TABLE, sa.Column("by_currency", sa.JSON(), nullable=True))
    if "mixed_currency" not in existing:
        op.add_column(_TABLE, sa.Column("mixed_currency", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "mixed_currency")
    op.drop_column(_TABLE, "by_currency")
