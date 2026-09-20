# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""funding - say what an obligation means in a form that can be translated.

``oe_funding_obligation.detail`` holds an English sentence the service wrote
when it derived the deadline from a programme's terms. Nobody using the
React client ever sees it, because that client renders the ``kind`` enum
through its own locales, but the REST response carries the sentence to every
other caller, in a product that ships in 42 languages. There is no later
moment at which that sentence can be translated: the words are data by then.

So the sentence gains the two things that make it translatable, stored beside
it rather than in place of it:

``detail_key``
    The message key the sentence renders from, for example
    ``funding.obligation_detail.final_report``. It is stored rather than
    derived from ``kind`` because one kind produces two different sentences:
    a retention deadline counted from the end of the award period reads
    differently from the same deadline recounted from the day the proof of
    use was accepted, and a caller must not have to guess which it is
    holding.

``detail_params``
    The values that key interpolates - the day count, the year count, the
    programme code, the sequence number of the draw. These are stored for
    the same reason ``due_on`` is stored rather than recomputed: a deadline
    already communicated to somebody must not be quietly reworded when the
    programme's terms are edited afterwards.

``detail`` stays exactly as it is and keeps its English. It is now the
rendered convenience for a caller with no message bundle, and the key with
its parameters is the contract.

Both columns are empty on an obligation somebody typed in. Those are their
own words, not a key into anything, and translating them would be losing
what they wrote.

Strictly additive: two new columns on one table, nothing existing touched and
no row rewritten. Inspector-guarded, so an install whose tables ``env.py``
already built through ``Base.metadata.create_all`` reaches this revision and
does nothing.

Revision ID: v41_funding_obligation_detail
Revises: v41_funding_module
Create Date: 2026-09-20
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "v41_funding_obligation_detail"
down_revision: Union[str, Sequence[str], None] = "v41_funding_module"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_funding_obligation"
_KEY_COLUMN = "detail_key"
_PARAMS_COLUMN = "detail_params"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        # Nothing to alter. The revision that creates this table runs
        # immediately before this one, so its absence means the chain never
        # got that far, and adding a column to a table that is not there
        # would stop the upgrade on a database this module does not use.
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}

    if _KEY_COLUMN not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _KEY_COLUMN,
                sa.String(length=120),
                nullable=False,
                # The rows already in the table were written before this
                # column existed, so they have no key. An empty string is
                # what a hand written obligation carries too, and both mean
                # the same thing to a reader: render the prose, there is
                # nothing to translate.
                server_default="",
            ),
        )

    if _PARAMS_COLUMN not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _PARAMS_COLUMN,
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    op.drop_column(_TABLE, _PARAMS_COLUMN)
    op.drop_column(_TABLE, _KEY_COLUMN)
