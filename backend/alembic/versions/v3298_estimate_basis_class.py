# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""estimate_basis: carry the number, its provenance and its accuracy class.

Adds nine additive columns to ``oe_estimate_basis_document``. They fall into two
halves, and the split is the point of the change.

Derived, written by the generator and never typed:

* ``currency`` — the estimate's currency, resolved from the project when the
  caller does not state one. Without it the figures on the page render with no
  symbol at all.
* ``financials`` — the money snapshot at generation time: direct cost, markups
  total, grand total, and the two flags the BOQ roll-up raises when a total is
  not safe to read as final (mixed currency, unresolved escalation).
* ``provenance`` — where the estimate's lines came from (measured, imported,
  catalogue, hand-entered), the machine-proposed lines and their confidence, the
  model bindings that have drifted, and the class the platform SUGGESTS from
  that evidence.
* ``pricing_date`` — the date the priced rates are current to.

Human judgement, written only by an estimator:

* ``estimate_class`` — an AACE 18R-97 class, 1 to 5, lower being more defined.
  The same 1-5 space the BOQ module's classification endpoint already returns.
  Deliberately NULLABLE WITH NO DEFAULT: the platform suggests a class in
  ``provenance`` but must never store one on a person's behalf, so an
  unanswered document has to be able to read as unanswered.
* ``accuracy_low_pct`` / ``accuracy_high_pct`` — signed percentage bounds as
  Decimal-as-string, seeded from the chosen class's published range and
  editable, because a house may run tighter or wider bands than the standard's.
  String rather than Numeric for the same reason every money column on this
  platform is a string: SQLite degrades Numeric to REAL.
* ``market_conditions`` / ``contingency_rationale`` — the two paragraphs no
  derivation can write.

Strictly additive. Every existing row keeps the document it already was: the
derived columns arrive empty and fill on the next regenerate, and the judgement
columns arrive unanswered, which is the truth about a document nobody has
answered them on.

Idempotent — inspector-guarded, so a re-run on a partially migrated database
skips whatever is already present.

Revision ID: v3298_estimate_basis_class
Revises: v3297_boq_markup_scope
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3298_estimate_basis_class"
down_revision: Union[str, Sequence[str], None] = "v3297_boq_markup_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_estimate_basis_document"

# (name, column factory, comment). Ordered as they read on the document.
_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("currency", "string8", "ISO currency code of the figures below. Resolved from the project when unstated."),
    (
        "financials",
        "json",
        "Money snapshot at generation: direct_cost, markups_total, grand_total and the not-final flags.",
    ),
    (
        "provenance",
        "json",
        "Where the lines came from, the machine-proposed ones, and the estimate class the platform suggests.",
    ),
    ("pricing_date", "string40", "Date the priced rates are current to."),
    (
        "estimate_class",
        "integer",
        "AACE 18R-97 estimate class 1-5, lower is more defined. NULL = the estimator has not stated one.",
    ),
    ("accuracy_low_pct", "string20", "Signed lower accuracy bound as a percentage, Decimal-as-string."),
    ("accuracy_high_pct", "string20", "Signed upper accuracy bound as a percentage, Decimal-as-string."),
    ("market_conditions", "text", "The estimator's statement of the market the estimate was priced into."),
    ("contingency_rationale", "text", "The estimator's reason for the size of the contingency."),
)


def _column(name: str, kind: str, comment: str) -> sa.Column:
    """Build one additive column of the set.

    Every column is NOT NULL with a server default except ``estimate_class``
    and ``pricing_date``: those two mean "nobody has said", and a default would
    turn the absence of an answer into an answer.
    """
    if kind == "integer":
        return sa.Column(name, sa.Integer(), nullable=True, comment=comment)
    if kind == "json":
        return sa.Column(name, sa.JSON(), nullable=False, server_default="{}", comment=comment)
    if kind == "text":
        return sa.Column(name, sa.Text(), nullable=False, server_default="", comment=comment)
    if kind == "string40":
        return sa.Column(name, sa.String(length=40), nullable=True, comment=comment)
    length = 8 if kind == "string8" else 20
    return sa.Column(name, sa.String(length=length), nullable=False, server_default="", comment=comment)


def upgrade() -> None:
    """Add the derived-figures and human-judgement columns."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, kind, comment in _COLUMNS:
        if name not in existing:
            op.add_column(_TABLE, _column(name, kind, comment))


def downgrade() -> None:
    """Drop the added columns, newest-listed first."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns(_TABLE)}
    for name, _kind, _comment in reversed(_COLUMNS):
        if name in existing:
            op.drop_column(_TABLE, name)
