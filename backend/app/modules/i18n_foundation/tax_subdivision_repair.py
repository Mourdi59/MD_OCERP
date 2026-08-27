# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Give an existing install's Canadian tax rows the province they belong to.

What changed
------------
``v3307_tax_subdivision`` added ``subdivision_code`` to ``oe_i18n_tax_config``,
so a rate can name the province or state it applies in instead of spelling it
inside ``tax_code`` as a convention nothing enforced. The shipped seed file was
updated in the same change, so a fresh install gets the eleven sub-national
rows already labelled.

Why an existing install does not get it
---------------------------------------
Two reasons, and either alone would be enough. ``seed.py`` seeds
``oe_i18n_tax_config`` only when the table is empty, so a corrected seed file
never reaches a database that has already been seeded. And the product does not
run ``alembic upgrade``: the schema moves at boot through the auto-migrator and
``create_all``, neither of which executes a revision body, so the revision's own
backfill does not run either. What the auto-migrator *does* do is add the column
- empty.

The result on an upgraded install, without this repair, is a database where
every Canadian row is present and correct except that none of them says which
province it is for. That is not a silent wrong answer, which is the mercy of it:
the resolver reports ``subdivision_unknown`` and returns no rate rather than
falling back to the federal 5 %. It is still a working feature that arrives
broken, so it is repaired here.

Both halves of the statement, or neither
----------------------------------------
The update writes ``combination`` alongside ``subdivision_code``, because the
table's check constraint holds them to be one statement: a row carries a
subdivision exactly when its combination is sub-national. On a database seeded
before ``combination`` existed - the column arrived in v15.5.0, two releases
before the subdivision axis - the boot heal adds it and fills every existing row
with the server default ``national``. Writing only the subdivision onto such a
row puts the two halves in contradiction, and since ``NOT VALID`` exempts
existing rows but never an ``UPDATE``, PostgreSQL refuses the write. The repair
then fails on every start, health reports ``data_repairs_failed`` for as long as
the install lives, and the Canadian rates it exists to label stay unlabelled.

The values come from
:data:`~app.modules.i18n_foundation.subdivisions.SHIPPED_SUBDIVISION_COMBINATION`,
which carries what the shipped seed says for these same ten rows. On a database
that already holds the right combination - anything seeded from v15.5.0 onward -
writing it again changes nothing, so the two cohorts take the same path.

Fill, never overwrite
---------------------
The update writes only where ``subdivision_code`` is still NULL. Three things
follow, and they are why the shape was chosen:

* An operator who set a subdivision by hand - or who moved a rate to a
  different province - keeps what they set. The repair has no opinion about a
  row that already carries an answer.
* Re-running is a no-op, which the registry requires: after the first pass no
  row matches the predicate. Idempotence is a property of the statement here,
  not of a marker somewhere saying the repair already ran.
* The federal GST row is untouched. Its NULL is not a gap waiting to be filled;
  it is the positive statement that the rate belongs to the whole country, and
  writing a province into it would break the table's own check constraint.

What it will not touch
----------------------
Only the exact ``(country_code, tax_code)`` pairs this platform ships, listed in
:data:`~app.modules.i18n_foundation.subdivisions.SHIPPED_SUBDIVISION_BACKFILL`.
A jurisdiction a deployment added by hand is not guessed at from its tax code,
because the convention that would have to be parsed is precisely the one the
column exists to replace.
"""

from __future__ import annotations

import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.i18n_foundation.models import TaxConfiguration
from app.modules.i18n_foundation.subdivisions import (
    SHIPPED_SUBDIVISION_BACKFILL,
    SHIPPED_SUBDIVISION_COMBINATION,
)

logger = logging.getLogger(__name__)


async def repair_tax_subdivisions(session: AsyncSession) -> int:
    """Label the shipped sub-national tax rows with their subdivision.

    Args:
        session: An open session. The caller commits; the repair registry does.

    Returns:
        Number of rows given a subdivision by this call. Zero on every boot
        after the first, and zero on a fresh install, where the seed file
        already carries the values.
    """
    repaired = 0
    for (country_code, tax_code), subdivision in SHIPPED_SUBDIVISION_BACKFILL.items():
        result = await session.execute(
            update(TaxConfiguration)
            .where(
                TaxConfiguration.country_code == country_code,
                TaxConfiguration.tax_code == tax_code,
                TaxConfiguration.subdivision_code.is_(None),
            )
            .values(
                subdivision_code=subdivision,
                combination=SHIPPED_SUBDIVISION_COMBINATION[(country_code, tax_code)],
            )
        )
        repaired += result.rowcount or 0

    if repaired:
        logger.info("Labelled %d tax configuration rows with their subdivision.", repaired)
    return repaired
