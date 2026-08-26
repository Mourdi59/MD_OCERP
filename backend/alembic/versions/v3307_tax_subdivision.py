# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""tax: let a rate name the province it belongs to, instead of spelling it in its code.

Adds one nullable column, ``subdivision_code``, to ``oe_i18n_tax_config``,
backfills the eleven shipped sub-national rows, and constrains the column
against ``combination`` so the two can never disagree.

``v3302_tax_combination`` taught a rate how it combines with the federal rate
of the same country - replace it, or add to it. What it could not say was
*where*. The province has only ever lived inside ``tax_code`` as a naming
convention: Canada writes the tax first (``HST_ON``, ``PST_BC``), the United
States writes the state first (``CA_SALES``), nothing enforces either, and the
only code that ever read it was a helper in a test file. A convention a query
cannot filter on is not an axis, so asking the platform for Canada's tax
configuration returned all thirteen rows undifferentiated and left the caller
to work out which of them applied to a job in Ontario.

Nullable, and that is the whole design rather than a concession. NULL is a
positive statement - this rate belongs to the country, not to a province -
which is exactly what the Canadian federal GST row is. The check constraint
below ties that meaning down:

    (combination IN ('replaces_federal','stacks_on_federal','compounds_on_federal'))
        = (subdivision_code IS NOT NULL)

Read as an equality of two booleans, it says a sub-national rate names its
subdivision and a country-wide one does not, and neither half can be relaxed
without the other being noticed. The failure it removes is the quiet one: a
provincial rate with no subdivision drops out of every per-province lookup, the
province answers with the federal 5 %, and nothing anywhere reports that a rate
was missed. Nothing was missing - it was mislabelled.

The same revision widens ``combination`` with a fifth member,
``compounds_on_federal``, for a provincial rate charged on the federal-inclusive
amount. That is not decorative either: 7 % stacked on 5 % is 12 %, and 7 %
compounded on 5 % is 12.35 %. No Canadian jurisdiction does this today - Quebec
was the last, and stopped on 2013-01-01 when it moved the QST to a pre-GST base
and raised the rate from 9.5 % to 9.975 % so the amount payable did not move -
but a model that cannot express the ordering cannot express that history, or a
retroactive claim reaching back into it. The member needs no DDL: ``combination``
is a plain ``String(20)`` with no database-level enumeration, so widening the
tuple in the model is the whole change. It is written down here because a reader
looking for when the fifth value appeared will look at the revisions.

**On the mechanism that actually reaches installs.** This revision runs only
where somebody runs alembic. The embedded-PostgreSQL runtime builds its schema
with ``create_all`` and *stamps* alembic rather than running it, healing later
columns out of the models at boot (``app/core/postgres_migrator.py``). There the
column arrives empty and this backfill never executes. So the backfill is
duplicated as the ``tax_subdivision_backfill`` entry in
``app/core/data_repairs.py``, which the boot path runs on every start, after the
schema heal, with a ledger and a health signal behind it. It writes only where
the value is still NULL and shares its table with the one below - a test asserts
the two tables are identical so they cannot drift apart. Neither copy is
redundant: this one is what an operator running ``alembic upgrade head`` gets,
the other is what everyone else gets.

What an unrepaired install would otherwise report is worth stating plainly,
because it is worse than an empty column sounds. Every Canadian rate would be
present and none of them labelled, so a lookup for Ontario would find no
provincial rate, observe that Ontario is a province the platform knows, and
answer "federal only, 5 %" - the wrong total, with the same confidence as
Alberta's correct one. The resolver refuses to make that claim while any
sub-national row is unlabelled, so the repair failing is loud rather than
quiet; the repair is what makes it right.

The constraint is a model-level ``CheckConstraint``, so the heal adds it too,
and it does so on the first boot after upgrade rather than waiting for the data
to be right. ``_heal_constraints`` issues checks as ``ADD CONSTRAINT ... NOT
VALID``, which enforces the rule on every new and updated row without scanning
the rows already there. So the eleven shipped rows sit unlabelled and in breach
for the moment between the column arriving and the backfill running, no
statement fails over them, and the backfill's own ``UPDATE`` is checked and
satisfies the rule by construction - it only ever gives a sub-national row the
subdivision it belongs to. The window in which a *new* mislabelled row could be
written is therefore never open on either path.

Adding the constraint here as well, after the backfill and without ``NOT
VALID``, means the alembic path gets it fully validated: on that path the rows
are correct by the time it goes on, so there is no reason to accept a
constraint PostgreSQL has not checked.

Idempotent - inspector-guarded, so a re-run on a partially migrated database
skips what is already there.

Revision ID: v3307_tax_subdivision
Revises: v3306_tolerance_profile_currency
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "v3307_tax_subdivision"
down_revision: Union[str, Sequence[str], None] = "v3306_tolerance_profile_currency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_i18n_tax_config"
_COLUMN = "subdivision_code"
_INDEX = "ix_tax_config_country_subdivision"

# The constraint's BARE name, exactly as the model declares it. It is handed to
# ``op.create_check_constraint`` and ``op.drop_constraint`` unchanged, and the
# metadata's ``ck_%(table_name)s_%(constraint_name)s`` convention builds the
# finished name on both sides. One name, one convention, one result.
#
# The previous version of this file held the finished name instead and added the
# constraint by explicit DDL to stop the convention applying twice. That worked
# on the way up and broke on the way down, because ``op.drop_constraint`` runs
# the convention too: it was handed the already-prefixed name and asked the
# database for
# ``ck_oe_i18n_tax_config_ck_oe_i18n_tax_config_subdivision_06f1``
# - prefix twice, then truncated to 63 characters with a hash - which of course
# does not exist. Measured, not inferred: rendering a ``CheckConstraint`` under
# this convention with an already-prefixed name reproduces that string exactly,
# hash included, while the same test on a UniqueConstraint and an Index passes
# the name through untouched. Only ``ck`` interpolates ``%(constraint_name)s``,
# so only check constraints can double.
#
# The lesson worth keeping: the upgrade and the downgrade each looked right on
# its own, and only the round trip - the one lane that runs both - could see
# that they disagreed about a name. So neither side spells the finished name.
_CONSTRAINT_NAME = "subdivision_matches_combination"


def _constraint_candidates() -> set[str]:
    """Names this constraint may be carrying in a live database.

    The introspection guards below compare against what the database really
    calls the constraint, so they need the finished name, while the operations
    need the bare one. Deriving the finished name here rather than writing it
    down keeps a single source: the convention is read from the same
    ``target_metadata`` that ``op.create_check_constraint`` will consult, so a
    change to the convention moves both together.

    Returns:
        Every name the constraint could legitimately be under - the convention's
        answer, and the bare name for a database built without a convention.
    """
    names = {_CONSTRAINT_NAME}
    try:
        metadata = op.get_context().opts.get("target_metadata")
        template = getattr(metadata, "naming_convention", {}).get("ck")
    except Exception:  # noqa: BLE001 - a revision must not fail over introspection
        template = None
    if template:
        names.add(template % {"table_name": _TABLE, "constraint_name": _CONSTRAINT_NAME})
    else:
        # No convention available on this context. Fall back to the format the
        # application declares, so the guard still recognises a database that
        # was built by the ORM.
        names.add(f"ck_{_TABLE}_{_CONSTRAINT_NAME}")
    return names


# Which subdivision each shipped sub-national row belongs to, keyed on country
# plus tax code - the only place that identity has ever been recorded. Kept as
# literals rather than imported from the module: a revision has to keep working
# against the schema it was written for, and importing today's application code
# into a migration is how a revision starts failing years later because a
# constant moved. ``test_tax_subdivision_migration.py`` asserts this table
# equals ``subdivisions.SHIPPED_SUBDIVISION_BACKFILL`` so the duplication cannot
# silently diverge.
#
# HST (Nova Scotia) appears once here and twice in the table - the 15 % window
# that closed on 2025-03-31 and the 14 % one that opened the next day - and both
# rows are matched by the same predicate, which is correct: the province did not
# change, only its rate.
_BACKFILL: tuple[tuple[str, str, str], ...] = (
    ("CA", "HST_ON", "CA-ON"),
    ("CA", "HST_NS", "CA-NS"),
    ("CA", "HST_NB", "CA-NB"),
    ("CA", "HST_NL", "CA-NL"),
    ("CA", "HST_PE", "CA-PE"),
    ("CA", "QST_QC", "CA-QC"),
    ("CA", "PST_BC", "CA-BC"),
    ("CA", "PST_SK", "CA-SK"),
    ("CA", "RST_MB", "CA-MB"),
    ("US", "CA_SALES", "US-CA"),
)

_CHECK = (
    "(combination IN ('replaces_federal', 'stacks_on_federal', 'compounds_on_federal'))"
    " = (subdivision_code IS NOT NULL)"
)

# boot-repair: registry=tax_subdivision_backfill
# data-rewrite-ack: table=oe_i18n_tax_config growth=bounded rows=80 as shipped, one per
# jurisdiction and rate period we carry; a deployment adds a row only when it adds a
# jurisdiction by hand, so the count tracks the catalogue rather than how long the install
# has run. Eleven rows are written, matched by an exact (country_code, tax_code) pair rather
# than a LIKE pattern, and only where the column is still NULL - so an operator who set a
# subdivision by hand between the ADD COLUMN and this UPDATE keeps their value.


def upgrade() -> None:
    """Add ``subdivision_code``, backfill it, index it, then constrain it."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing:
        op.add_column(
            _TABLE,
            sa.Column(
                _COLUMN,
                sa.String(length=6),
                nullable=True,
                comment="ISO 3166-2 subdivision this rate belongs to; NULL means country-wide.",
            ),
        )

    # Backfill before the constraint. The other order asks the database to
    # accept a rule the rows already break, and it is right to refuse.
    for country_code, tax_code, subdivision in _BACKFILL:
        op.execute(
            sa.text(
                f"UPDATE {_TABLE} SET {_COLUMN} = :subdivision "  # noqa: S608 - table name is a module constant
                f"WHERE country_code = :country AND tax_code = :tax_code AND {_COLUMN} IS NULL"
            ).bindparams(subdivision=subdivision, country=country_code, tax_code=tax_code)
        )

    if _INDEX not in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["country_code", _COLUMN])

    existing_checks = {check["name"] for check in inspector.get_check_constraints(_TABLE)}
    if not (_constraint_candidates() & existing_checks):
        # The bare name, so the convention builds the finished one - the same
        # way the downgrade drops it. See ``_CONSTRAINT_NAME`` above.
        op.create_check_constraint(_CONSTRAINT_NAME, _TABLE, _CHECK)


def downgrade() -> None:
    """Drop the constraint, the index and the column, if they are there.

    This returns the province to living inside ``tax_code`` as a convention
    only a test helper reads, and returns the platform to being unable to
    answer "what tax applies to a job in Ontario" from the data. The rates
    themselves are untouched, and ``combination`` keeps its fifth member -
    dropping a value out of a plain string column would mean rewriting rows.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    if _constraint_candidates() & {check["name"] for check in inspector.get_check_constraints(_TABLE)}:
        op.drop_constraint(_CONSTRAINT_NAME, _TABLE, type_="check")

    if _INDEX in {index["name"] for index in inspector.get_indexes(_TABLE)}:
        op.drop_index(_INDEX, table_name=_TABLE)

    if _COLUMN in {column["name"] for column in inspector.get_columns(_TABLE)}:
        op.drop_column(_TABLE, _COLUMN)
