# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""i18n: bring Romania's VAT rows up to the reform of 1 August 2025.

Romania raised its standard VAT rate from 19 % to 21 % with effect from
1 August 2025, and in the same move abolished both reduced rates - 5 % and
9 % - replacing them with a single 11 % band. Sources are cited on
``ROMANIA_VAT_SOURCES`` in ``app/modules/i18n_foundation/romania_vat.py``.

``seed_data/tax_configurations.json`` carries the corrected rates, which
reaches new installations only: ``seed.py`` returns early once
``oe_i18n_tax_config`` has rows, so every database seeded before the reform
still shows one open Romanian row at 19 % and no reduced rate at all.

Close and add, never rewrite
----------------------------
The 19 % row keeps its rate and is given the ``effective_to`` the reform gives
it, ``2025-07-31``; the 21 % row is inserted alongside it. A document priced on
a date before the reform therefore still resolves at 19 %, which is the point:
an estimate or invoice already issued at the old rate must not change value
because a rate table was corrected. Rewriting the row in place would have done
exactly that, silently.

What it will not touch
----------------------
Only the row the seeder wrote, matched on all four fields it wrote - country
``RO``, tax code ``TVA``, rate ``19.0``, effective from ``2017-01-01``, still
open. Anything an operator has edited fails that match and the standard-rate
step is skipped for this database.

That guard separates an untouched shipped row from an edited one. It does not
separate a tenant deliberately holding 19 % from one nobody updated, because
holding the old rate deliberately requires no edit and the two are identical in
the table. Close-and-add is what makes the repair safe regardless: the old rate
is still the answer for every date it applied to.

Idempotent. The predicate is on the data, not on a version marker: after the
first pass the 19 % row carries an ``effective_to`` and no longer matches, and
each insert is guarded on the natural key of the row it would add.

Revision ID: v3308_romania_vat_2025
Revises: v3307_tax_subdivision
Create Date: 2026-08-26
"""

from __future__ import annotations

from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "v3308_romania_vat_2025"
down_revision: Union[str, Sequence[str], None] = "v3307_tax_subdivision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_i18n_tax_config"

_COUNTRY = "RO"
_OLD_STANDARD_LAST_DAY = "2025-07-31"
_REFORM_FIRST_DAY = "2025-08-01"

# The pre-reform row exactly as the seeder wrote it. Written out here rather
# than imported from the application: a revision has to keep meaning what it
# meant on the day it was written, and app code moves.
_OLD_CODE = "TVA"
_OLD_RATE = "19.0"
_OLD_FROM = "2017-01-01"

_NEW_ROWS = (
    {
        "tax_name": "VAT Standard (TVA)",
        "tax_name_translations": {"en": "VAT Standard", "ro": "TVA cota standard"},
        "tax_code": "TVA",
        "rate_pct": "21.0",
        "is_default": True,
    },
    {
        "tax_name": "VAT Reduced (TVA)",
        "tax_name_translations": {"en": "VAT Reduced", "ro": "TVA cota redusa"},
        "tax_code": "TVA_RED",
        "rate_pct": "11.0",
        "is_default": False,
    },
)


# data-rewrite-ack: table=oe_i18n_tax_config growth=bounded rows=81 as shipped, one per
# country and rate tier we carry; a deployment gains a row only when somebody adds a rate
# by hand, so the count tracks the catalogue rather than how long the install has run. At
# most one row is closed and two inserted, and only where the value still matches what the
# seeder wrote.
# boot-repair: registry=romania_vat_2025
def _wanted(spec: dict, existing: Sequence, stale: Sequence, carries_our_standard: bool) -> bool:
    """Whether ``spec`` is a row this install is missing and should be given.

    The standard row belongs to the split; only add it where the split was
    actually applied here. The reduced band is missing from every database
    seeded before it shipped, including one that already has the split, so it
    is gated only on our rows being present at all.
    """
    if spec["tax_code"] == _OLD_CODE and not stale:
        return False
    if not carries_our_standard:
        return False
    return not any(
        r.tax_code == spec["tax_code"] and r.rate_pct == spec["rate_pct"] and r.effective_from == _REFORM_FIRST_DAY
        for r in existing
    )


def _still_names_one_standard_rate(existing: Sequence, stale: Sequence, additions: Sequence) -> bool:
    """Whether the country would still resolve to a rate once the plan landed.

    Mirrors ``_country_wide_standard`` in
    ``app/modules/i18n_foundation/tax_rules.py``: a country-wide question is
    answered by the one row flagged ``is_default``, or by the single row on
    file when there is exactly one and nothing is flagged. Anything else is
    ``default_rate_ambiguous``, which returns no rate at all.

    Deliberately restated here rather than imported. A revision has to keep
    doing what it did on the day it was written, and importing live rule code
    would let a later edit change what an applied upgrade means. The boot
    repair, which is what reaches real installs, calls ``resolve`` itself; the
    test suite runs both halves over the same fixtures so this copy cannot
    drift unnoticed.
    """
    today = date.today().isoformat()
    closing = {(r.tax_code, r.rate_pct, r.effective_from) for r in stale}

    in_force = []
    for row in existing:
        key = (row.tax_code, row.rate_pct, row.effective_from)
        effective_to = _OLD_STANDARD_LAST_DAY if key in closing else row.effective_to
        is_default = False if key in closing else bool(row.is_default)
        if (row.effective_from or "") <= today and (effective_to is None or effective_to >= today):
            in_force.append(is_default)
    in_force.extend(bool(spec["is_default"]) for spec in additions if today >= _REFORM_FIRST_DAY)

    flagged = sum(1 for is_default in in_force if is_default)
    return flagged == 1 or (flagged == 0 and len(in_force) == 1)


def _repair_rows(bind: Connection) -> tuple[int, int]:
    """Close the stale Romanian standard rate and add the reformed rates.

    Takes a connection rather than reaching for ``op.get_bind()`` itself so the
    same statements can be run against a real database in a test.

    Args:
        bind: Open connection to run the statements on.

    Returns:
        ``(rows closed, rows inserted)``.
    """
    existing = bind.execute(
        sa.text(  # noqa: S608 - table name is a module constant, not input
            f"SELECT tax_code, rate_pct, effective_from, effective_to, is_default "
            f"FROM {_TABLE} WHERE country_code = :cc"
        ),
        {"cc": _COUNTRY},
    ).fetchall()

    if not existing:
        return 0, 0

    stale = [
        r
        for r in existing
        if r.tax_code == _OLD_CODE
        and r.rate_pct == _OLD_RATE
        and r.effective_from == _OLD_FROM
        and r.effective_to is None
    ]

    carries_our_standard = any(r.tax_code == _OLD_CODE for r in existing)
    additions = [spec for spec in _NEW_ROWS if _wanted(spec, existing, stale, carries_our_standard)]

    if not stale and not additions:
        return 0, 0

    if not _still_names_one_standard_rate(existing, stale, additions):
        # Same refusal the boot repair makes, and for the same reason: adding an
        # unflagged band beside rows that already fail to name a default leaves
        # the country with no resolvable rate at all. See the note on
        # ``repair_romanian_vat_rates``.
        return 0, 0

    closed = 0
    if stale:
        result = bind.execute(
            sa.text(  # noqa: S608 - table name is a module constant, not input
                f"UPDATE {_TABLE} SET effective_to = :last_day, is_default = false "
                f"WHERE country_code = :cc AND tax_code = :code AND rate_pct = :rate "
                f"AND effective_from = :start AND effective_to IS NULL"
            ),
            {
                "last_day": _OLD_STANDARD_LAST_DAY,
                "cc": _COUNTRY,
                "code": _OLD_CODE,
                "rate": _OLD_RATE,
                "start": _OLD_FROM,
            },
        )
        closed = result.rowcount or 0

    inserted = 0
    for spec in additions:
        # ``id`` is VARCHAR(36) on every dialect (see ``GUID`` in
        # app/database.py), hence the cast. ``metadata``, ``created_at`` and
        # ``updated_at`` are left to their server defaults rather than named
        # here - they are NOT NULL with literal defaults, so a shorter
        # statement is also the one with fewer ways to be wrong.
        bind.execute(
            sa.text(  # noqa: S608 - table name is a module constant, not input
                f"INSERT INTO {_TABLE} "
                f"(id, country_code, tax_name, tax_name_translations, tax_code, rate_pct, tax_type, "
                f" combination, subdivision_code, effective_from, effective_to, is_default) "
                f"VALUES (gen_random_uuid()::text, :cc, :name, :translations, :code, :rate, 'vat', "
                f" 'national', NULL, :start, NULL, :is_default)"
            ).bindparams(sa.bindparam("translations", type_=sa.JSON)),
            {
                "cc": _COUNTRY,
                "name": spec["tax_name"],
                "translations": spec["tax_name_translations"],
                "code": spec["tax_code"],
                "rate": spec["rate_pct"],
                "start": _REFORM_FIRST_DAY,
                "is_default": spec["is_default"],
            },
        )
        inserted += 1

    return closed, inserted


def upgrade() -> None:
    """Close the 19 % Romanian row and add the 21 % standard and 11 % reduced rates."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        # Nothing has ever been seeded here; the corrected seed file is the
        # only thing this database will ever see.
        return

    closed, inserted = _repair_rows(bind)
    print(f"  v3308: Romanian VAT - closed {closed} stale row(s), inserted {inserted} new rate(s).")


def downgrade() -> None:
    # No-op, deliberately. Reverting means deleting the rates in force today
    # and re-opening a rate that expired in July 2025, which is to say putting
    # a known-wrong figure back on a customer's invoices. An operator who wants
    # the old shape can set the dates by hand; both rows are still there.
    pass
