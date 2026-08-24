# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Repair the trademarked formwork catalogue rows an upgraded install still carries.

Why this file contains manufacturer product names
-------------------------------------------------
A brand sweep over this repository will find eight manufacturer product names in
:data:`LEGACY_BRANDED_SYSTEMS`, and this paragraph is the answer to the question that
finding them raises, so nobody has to go and ask.

They are here deliberately, they are the only copy in shipped runtime code, and they are
*search keys* rather than content. The repair needs the exact old strings to find the rows
it has to rename. Nothing here ever writes one into a database, returns one from an API or
puts one on screen: every one of them appears only on the left-hand side of a rename.
Deleting them would not de-brand anything. It would strand the rows that still carry those
names in customer databases, which is the opposite of what the brand rule exists to do.

Why a boot-path repair and not a migration
------------------------------------------
``v3271_formwork_debrand`` renames exactly these rows, and on an installation that runs
``alembic upgrade`` by hand it is the thing that does the work. The product never runs
alembic. The schema moves through :func:`app.core.postgres_migrator.postgres_auto_migrate`,
which adds sequences, columns, indexes and constraints and rewrites no data at all, and the
boot path then records the database at head with ``stamp_head_if_unstamped``.

Measured on 2026-08-22 against a database brought up through the real application boot path:
eight rows carrying the old names survived a restart, and ``alembic_version`` reported the
current head. A database that reports head has nothing downstream that will ever look again,
so the repair has to live on the boot path or it does not happen.

Fresh installs were never affected: :func:`app.modules.formwork.schemas.default_seed_systems`
has carried the plain descriptors since the debrand, and a fresh seed writes zero branded
rows. This exists for databases seeded before that change.

Scope
-----
This repairs one catalogue. It is deliberately not a general mechanism for running the data
half of a migration on the boot path; whether such a mechanism should exist is a product
decision that has been written up separately rather than answered here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.modules.formwork.models import FormworkSystem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: ``(old name, old supplier, new name)``. The new names are the descriptors in
#: ``default_seed_systems()``; keep the two in step if that catalogue is ever re-worded, or
#: an upgraded install and a fresh one will disagree. Mirrors ``_RENAMES`` in
#: ``v3271_formwork_debrand``, which stays as it is: a revision is frozen history and must
#: keep running against the schema as it was, and it is not importable from a desktop bundle
#: in any case, because that bundle ships no migration tree.
LEGACY_BRANDED_SYSTEMS: tuple[tuple[str, str, str], ...] = (
    ("Doka Framax Xlife", "Doka", "Steel framed wall panel"),
    ("Doka Dokadek 30", "Doka", "Aluminium slab deck panel"),
    ("PERI MAXIMO", "PERI", "Steel wall panel, single-side tie"),
    ("PERI SKYDECK", "PERI", "Aluminium drophead slab panel"),
    ("MEVA Mammut 350", "MEVA", "Heavy-duty steel wall panel"),
    ("Hünnebeck MANTO", "Hünnebeck", "Crane-set steel wall panel"),
    ("Ulma ENKOFORM V-100", "Ulma", "Girder wall formwork"),
    ("PERI ACS climbing", "PERI", "Self-climbing core system"),
)

_OLD_NAMES: tuple[str, ...] = tuple(old for old, _, _ in LEGACY_BRANDED_SYSTEMS)


async def repair_branded_catalogue(session: AsyncSession) -> int:
    """Rename any surviving trademarked catalogue rows in place.

    Idempotent and safe to run on every start: the predicate stops matching once a row has
    been renamed, so a second run touches nothing. The common case costs one scan of the
    catalogue table that returns nothing - ``name`` carries no index, and it does not need
    one: this table holds a product catalogue of tens of rows, not per-project data.

    Declines in exactly the place ``v3271`` declines. ``name`` carries no unique constraint,
    so an install that already holds the replacement carries both rows, and renaming blindly
    would leave two identical names in one catalogue. Those rows are left alone and counted,
    not merged and not deleted, because the old row may carry assignments and deciding which
    of the two an assignment should point at is a judgement about a tenant's own data that a
    repair running unattended on boot has no standing to make.

    Which installs those are is a larger population than it first appears, so it is written
    out here rather than left to be rediscovered. It is not only an admin who pressed
    ``POST /systems/seed-defaults``. :func:`app.modules.formwork.demo.seed_demo_formwork`
    calls ``seed_defaults(tenant_id=None)`` as the first step of installing any formwork
    demo, so an install that has ever opened a formwork demo project holds the replacement
    rows globally, silently, without anyone having chosen to seed a catalogue. If such an
    install is also old enough to carry the branded rows, it holds both, and this repair
    leaves it alone. Clearing those needs a human decision about which of the two rows the
    existing assignments follow, and that decision is deliberately not made here.

    One case is probably stricter here than in ``v3271``. Where a tenant holds two rows under
    the SAME old name, this loop renames the first and the session autoflushes it before the
    next clash query runs, so the second is blocked and counted - that half is measured, in
    ``test_two_rows_under_one_old_name_keep_the_second``. The migration is expected to rename
    both, because its single ``UPDATE`` evaluates ``NOT EXISTS`` against the snapshot the
    statement started from, but that is read off the SQL and has not been run, so treat it as
    reasoning rather than as a measurement. Either way this side is the safe one: two rows
    sharing a name is the state the rename exists to avoid, so leaving the duplicate visible
    under its old name - where the next boot retries it - beats writing the collision.

    A supplier value is cleared only where it still holds the original brand, so a tenant who
    repointed the row at their own hire yard keeps that edit. No rate is touched, so nothing
    can move under an existing estimate.

    Args:
        session: An open async session. The caller owns the transaction and must commit.

    Returns:
        The number of rows actually renamed.
    """
    surviving = (
        (await session.execute(select(FormworkSystem).where(FormworkSystem.name.in_(_OLD_NAMES)))).scalars().all()
    )
    if not surviving:
        return 0

    by_old: dict[str, tuple[str, str]] = {old: (supplier, new) for old, supplier, new in LEGACY_BRANDED_SYSTEMS}
    renamed = 0
    blocked = 0

    for row in surviving:
        old_supplier, new_name = by_old[row.name]
        clash = (
            await session.execute(
                select(FormworkSystem.id).where(
                    FormworkSystem.name == new_name,
                    # Null-safe: a single-tenant install leaves tenant_id NULL, where a plain
                    # equality never matches and the duplicate guard would not fire at all.
                    FormworkSystem.tenant_id.is_not_distinct_from(row.tenant_id),
                )
            )
        ).first()
        if clash is not None:
            blocked += 1
            logger.warning(
                "formwork catalogue: %r left alone, %r already exists for that tenant",
                row.name,
                new_name,
            )
            continue
        if row.supplier == old_supplier:
            row.supplier = None
        row.name = new_name
        renamed += 1

    await session.flush()
    logger.info(
        "formwork catalogue de-branded: %d row(s) renamed, %d left for the duplicate guard",
        renamed,
        blocked,
    )
    return renamed
