# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Bring an existing install's Romanian VAT rows up to the 2025 reform.

What changed in the world
-------------------------
Romania raised the standard VAT rate from 19 % to 21 % with effect from
1 August 2025, and in the same move abolished both of its reduced rates - 5 %
and 9 % - and replaced them with a single 11 % band. Sources are cited on
:data:`ROMANIA_VAT_SOURCES` below, and the rates themselves live in
``seed_data/tax_configurations.json``, which is what a new install gets.

Why an existing install does not get it
---------------------------------------
``seed.py`` seeds ``oe_i18n_tax_config`` only when the table is empty. Every
database seeded before the reform therefore still carries one open Romanian
row at 19 %, and no reduced rate at all, and no amount of shipping a corrected
seed file changes that. The product does not run ``alembic upgrade`` either -
the schema moves at boot through the auto-migrator and ``create_all``, neither
of which executes a revision body - so the repair that reaches a real customer
is this function, registered as ``romania_vat_2025`` in
``app/modules/i18n_foundation/repairs.py`` and run on every start.

Close and add, never rewrite
----------------------------
The 19 % row is **not** edited to say 21 %. It is closed - given the
``effective_to`` of ``2025-07-31`` that the reform gives it - and the 21 % row
is inserted alongside. Three things follow from that, and they are the reason
the shape was chosen:

* A document priced on a date before 2025-08-01 still resolves at 19 %. An
  estimate or an invoice already issued at the old rate keeps its value, which
  a rate rewrite would have quietly changed underneath it.
* Re-running is a no-op. After the first pass the 19 % row carries an
  ``effective_to``, so it no longer matches the shape this looks for.
* Nothing is destroyed, so an operator who disagrees can see both rows and
  decide.

What it will not touch
----------------------
The repair recognises the row the seeder wrote and nothing else: country
``RO``, tax code ``TVA``, rate ``19.0``, effective from ``2017-01-01``, still
open. Any Romanian row that differs in any of those - a different rate, a
different code, an ``effective_to`` somebody already set - is left exactly as
it is, and the whole standard-rate step is skipped.

Be plain about the limit of that guard, because it is the question that
matters and it does not have a clean answer: **it distinguishes an untouched
shipped row from an edited one, and it cannot distinguish a tenant who is
deliberately holding 19 % from one nobody ever updated.** Both look identical
in the table, because holding the old rate deliberately requires no edit. What
makes the repair safe anyway is not the guard but the close-and-add shape: a
tenant who wanted 19 % for historical work still gets 19 % for every date
before the reform, and a tenant who wants it for *new* work has one row to
re-open rather than a lost rate to reconstruct.

It must not leave the country unpriceable
-----------------------------------------
``resolve`` answers a country-wide question by picking the row flagged
``is_default``, and refuses with ``default_rate_ambiguous`` when the rows in
force do not name exactly one. That refusal returns no rate at all, which is
correct for data nobody can interpret and catastrophic to *cause*: adding a
second unflagged row to an install whose single row was also unflagged turns a
database that was quietly pricing at its own rate into one that cannot price
at all.

That is reachable from here. An install carrying an operator's own ``TVA`` row
that is not flagged skips the standard-rate step and still gets the reduced
band, and now has two rows and no default. So the writes are planned first,
the planned result is run through ``resolve``, and nothing is applied unless
Romania still answers with a rate afterwards. A repair that cannot improve an
install is expected to leave it alone; one that would break it must.
"""

from __future__ import annotations

import logging
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.i18n_foundation.models import TaxConfiguration
from app.modules.i18n_foundation.tax_rules import (
    TaxRateRow,
    resolve,
    row_from_mapping,
    row_from_orm,
    validate_tax_row,
)

logger = logging.getLogger(__name__)

#: Where every figure in this module comes from, so a reader checking a rate
#: against the law does not have to guess which publication was used.
#:
#: * Standard 21 % and the single reduced band 11 %, both from 1 August 2025,
#:   replacing 19 % standard and the 5 % / 9 % reduced pair: PwC Worldwide Tax
#:   Summaries, Romania - Significant developments, read 2026-08-26
#:   (https://taxsummaries.pwc.com/romania/corporate/significant-developments).
#: * The same two rates independently: European Commission, Your Europe, "VAT
#:   rules and rates", which tabulates Romania as standard 21, reduced 11, with
#:   no super-reduced and no parking rate, read 2026-08-26
#:   (https://europa.eu/youreurope/business/taxation/vat/vat-rules-rates/index_en.htm).
#: * What the 11 % band covers, itemised: PwC Worldwide Tax Summaries, Romania
#:   - Other taxes, read 2026-08-26. Construction services and building
#:   materials are not in it; they are standard-rated. Housing is not in it
#:   either, beyond named institutional buildings (elderly homes, children's
#:   homes, rehabilitation centres for minors with disabilities).
ROMANIA_VAT_SOURCES: Final = (
    "PwC Worldwide Tax Summaries - Romania, Significant developments (read 2026-08-26)",
    "European Commission, Your Europe - VAT rules and rates (read 2026-08-26)",
)

_COUNTRY: Final = "RO"

#: The last day the old standard rate applied. The reform takes effect on the
#: first of August, so the window it closes ends on the thirty-first of July.
OLD_STANDARD_LAST_DAY: Final = "2025-07-31"

#: First day of the reformed rates.
REFORM_FIRST_DAY: Final = "2025-08-01"

#: The exact row the seeder wrote before the reform, field by field. All four
#: have to match: the rate alone would also match a row an operator had edited
#: a date on, and matching on country and code alone would rewrite a rate
#: somebody set deliberately.
_SHIPPED_OLD_STANDARD: Final = {
    "tax_code": "TVA",
    "rate_pct": "19.0",
    "effective_from": "2017-01-01",
}

_NEW_STANDARD: Final = {
    "tax_name": "VAT Standard (TVA)",
    "tax_name_translations": {"en": "VAT Standard", "ro": "TVA cota standard"},
    "tax_code": "TVA",
    "rate_pct": "21.0",
    "tax_type": "vat",
    "combination": "national",
    "effective_from": REFORM_FIRST_DAY,
    "effective_to": None,
    "is_default": True,
}

_NEW_REDUCED: Final = {
    "tax_name": "VAT Reduced (TVA)",
    "tax_name_translations": {"en": "VAT Reduced", "ro": "TVA cota redusa"},
    "tax_code": "TVA_RED",
    "rate_pct": "11.0",
    "tax_type": "vat",
    "combination": "national",
    "effective_from": REFORM_FIRST_DAY,
    "effective_to": None,
    "is_default": False,
}


async def _romanian_rows(session: AsyncSession) -> list[TaxConfiguration]:
    """Every Romanian tax row on this install, in insertion-independent order."""
    result = await session.execute(
        select(TaxConfiguration)
        .where(TaxConfiguration.country_code == _COUNTRY)
        .order_by(TaxConfiguration.effective_from, TaxConfiguration.tax_code)
    )
    return list(result.scalars().all())


def _matches_shipped_old_standard(row: TaxConfiguration) -> bool:
    """Whether this row is the pre-reform standard rate exactly as shipped.

    Args:
        row: A Romanian tax configuration row.

    Returns:
        True only when every field the seeder wrote is still what it wrote and
        the row is still open. An install that edited any of them is telling
        us it manages this rate itself.
    """
    return (
        row.tax_code == _SHIPPED_OLD_STANDARD["tax_code"]
        and row.rate_pct == _SHIPPED_OLD_STANDARD["rate_pct"]
        and row.effective_from == _SHIPPED_OLD_STANDARD["effective_from"]
        and row.effective_to is None
    )


def _already_present(rows: list[TaxConfiguration], spec: dict) -> bool:
    """Whether a row matching ``spec``'s natural key is already on file.

    The natural key of a shipped rate row is its country, its tax code, its
    percentage and the date it starts. Two rows agreeing on all four are the
    same rate stated twice, whoever wrote the second one.
    """
    return any(
        row.tax_code == spec["tax_code"]
        and row.rate_pct == spec["rate_pct"]
        and row.effective_from == spec["effective_from"]
        for row in rows
    )


def _build(spec: dict) -> TaxConfiguration:
    """Turn one of the specs above into a row, through the write rules.

    ``validate_tax_row`` runs here for the same reason the seed loader runs it:
    this is a write path into ``oe_i18n_tax_config`` that does not pass through
    the API schema, and a repair that bypasses the rules is a new unguarded
    way to write a row the resolver cannot read.
    """
    validate_tax_row(_COUNTRY, spec["combination"], None)
    return TaxConfiguration(
        country_code=_COUNTRY,
        tax_name=spec["tax_name"],
        tax_name_translations=dict(spec["tax_name_translations"]),
        tax_code=spec["tax_code"],
        rate_pct=spec["rate_pct"],
        tax_type=spec["tax_type"],
        combination=spec["combination"],
        subdivision_code=None,
        effective_from=spec["effective_from"],
        effective_to=spec["effective_to"],
        is_default=spec["is_default"],
        metadata_={},
    )


def _projected(
    rows: list[TaxConfiguration],
    closing: list[TaxConfiguration],
    additions: list[dict],
) -> list[TaxRateRow]:
    """The Romanian rows as they would read once the planned writes landed.

    Args:
        rows: Every Romanian row currently on file.
        closing: The subset about to be given an ``effective_to`` and unflagged.
        additions: Specs about to be inserted.

    Returns:
        Flattened rows for :func:`resolve`, built without touching the session
        so the plan can be rejected with nothing written.
    """
    marked = {id(row) for row in closing}
    projected = [
        row_from_orm(row)._replace(effective_to=OLD_STANDARD_LAST_DAY, is_default=False)
        if id(row) in marked
        else row_from_orm(row)
        for row in rows
    ]
    projected.extend(row_from_mapping({**spec, "country_code": _COUNTRY}) for spec in additions)
    return projected


async def repair_romanian_vat_rates(session: AsyncSession) -> int:
    """Give an already-seeded database the Romanian rates in force since the reform.

    Two steps, gated independently, because an install can need either without
    needing the other. A database seeded before the reform needs both; one
    seeded after the standard-rate split shipped but before the reduced band
    did needs only the second.

    Step one, the standard rate. When the pre-reform row is still there exactly
    as the seeder wrote it, close it at 2025-07-31 and insert the 21 % row. The
    closed row keeps its rate, so every date before the reform still resolves
    at 19 %.

    Step two, the reduced rate. When this install carries our Romanian standard
    rows at all and has no ``TVA_RED`` row, insert the 11 % band.

    Both steps are planned before either is applied, and the planned result is
    resolved before anything is written. An install the plan would leave unable
    to name a standard rate is left exactly as it was, because a country that
    prices at a rate somebody else chose is in better shape than one that
    cannot price at all.

    Args:
        session: Open session. The caller owns the transaction and commits;
            this function only flushes.

    Returns:
        Rows changed - closed plus inserted. Zero on every run after the first,
        which is the idempotence contract :class:`app.core.data_repairs.DataRepair`
        requires, and zero as well on an install the plan would leave
        unpriceable.
    """
    rows = await _romanian_rows(session)
    if not rows:
        # Nothing Romanian has ever been seeded here. The corrected seed file
        # is the only thing this database will see, and inserting rates into a
        # table this install does not use is not a repair.
        return 0

    # ── Plan ─────────────────────────────────────────────────────────────────
    closing = [row for row in rows if _matches_shipped_old_standard(row)]

    additions: list[dict] = []
    if closing and not _already_present(rows, _NEW_STANDARD):
        additions.append(_NEW_STANDARD)

    # Deliberately not gated on ``closing``: the reduced band is missing from
    # every install seeded before it shipped, including those that already
    # carry the 19/21 split. ``carries_our_standard`` is what keeps this off a
    # database whose Romanian rates somebody else maintains.
    carries_our_standard = any(row.tax_code == _SHIPPED_OLD_STANDARD["tax_code"] for row in rows)
    has_reduced = any(row.tax_code == _NEW_REDUCED["tax_code"] for row in rows)
    if carries_our_standard and not has_reduced and not _already_present(rows, _NEW_REDUCED):
        additions.append(_NEW_REDUCED)

    if not closing and not additions:
        return 0

    # ── Refuse a plan that would cost the country its rate ────────────────────
    outcome = resolve(_projected(rows, closing, additions), _COUNTRY)
    if not outcome.resolved:
        logger.warning(
            "Romanian VAT: leaving this install alone - the repair would have left it unable to "
            "resolve a standard rate (%s: %s). Its Romanian rows are not the ones we shipped, so "
            "they need whoever maintains them, not this repair.",
            outcome.status,
            outcome.reason,
        )
        return 0

    # ── Apply ────────────────────────────────────────────────────────────────
    changed = 0
    for row in closing:
        row.effective_to = OLD_STANDARD_LAST_DAY
        # The shipped file flags the closed row false and the open one true,
        # so the repaired database matches a fresh install field for field.
        row.is_default = False
        changed += 1
        logger.info(
            "Romanian VAT: closed the %s%% standard rate at %s; it stays in force for every earlier date.",
            row.rate_pct,
            OLD_STANDARD_LAST_DAY,
        )

    for spec in additions:
        session.add(_build(spec))
        changed += 1
        logger.info(
            "Romanian VAT: added the %s%% rate (%s) effective %s.",
            spec["rate_pct"],
            spec["tax_code"],
            REFORM_FIRST_DAY,
        )

    if changed:
        await session.flush()
    return changed
