# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo data for the formwork module.

Why this file exists at all: nothing seeded ``oe_formwork_system``. The
catalogue was reachable only through the manual ``POST /systems/seed-defaults``
button, and no demo pack wrote a system or an assignment - not even
``rc-structure-formwork``, whose own header calls the formwork systems "the
hero of the BOQ" and then puts every one of them in the bill as description
text. So a visitor opening the formwork page on a demo project found an empty
catalogue and a system chooser with nothing in it, which is exactly the
complaint that started this work: it was not clear which system you could
choose because there was no system to choose.

Two steps, in order:

1. Install the starter catalogue globally (``tenant_id=None``) if it is not
   already there. Idempotent by name, so several demo projects installing in
   the same database share one catalogue rather than each growing a copy.
2. Give the project a handful of assignments covering DIFFERENT element types,
   because a project showing three wall assignments teaches nothing about
   choosing a system, while one showing walls, columns, a slab table and the
   climbing cores shows the comparison the module is for.

Quantities are the pack's own where the pack states them and modest generic
figures otherwise. Nothing here invents a supplier or a product name: the
systems are the generic catalogue rows, which is the only naming this platform
permits.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.formwork.models import FormworkAssignment, FormworkSystem
from app.modules.formwork.service import FormworkService

logger = logging.getLogger(__name__)

# (catalogue system name, contact area m2, reuses, waste %, note).
#
# The reuse counts are deliberately NOT all the same, and none is the system's
# own maximum: a demo where every assignment claims the catalogue limit would
# model an estimator who never thought about the programme. The single-use
# liner claims one use because that is all it has.
_RC_STRUCTURE: tuple[tuple[str, str, int, str, str], ...] = (
    # Areas follow the pack's own bill: 9200 m2 of external wall, 1180 + 860 of
    # column, 20400 of slab deck, 3600 to the climbing cores, 5400 of beam.
    ("Steel framed wall panel", "9200", 45, "5.00", "External walls, 25 cm, both faces"),
    ("Girder wall formwork", "6400", 30, "5.00", "Internal walls, 30 cm"),
    ("Square column form, adjustable", "860", 40, "4.00", "Rectangular columns 40x40"),
    (
        "Circular column form, single-use liner",
        "1180",
        1,
        "8.00",
        "Round columns d=40 cm, liner stripped and scrapped each pour",
    ),
    ("Slab table form", "20400", 60, "3.00", "Flat slab decks, craned bay to bay"),
    ("Beam form, three-sided", "5400", 25, "5.00", "Downstand beams, three faces"),
    ("Slab props and primary beams", "20400", 70, "3.00", "Falsework under the decks"),
    ("Self-climbing core system", "3600", 24, "4.00", "Stair and lift cores"),
)

# Every other demo project gets a smaller spread that still crosses element
# types, so the chooser has something to compare on any project a visitor opens.
_GENERIC: tuple[tuple[str, str, int, str, str], ...] = (
    ("Steel framed wall panel", "1850", 20, "5.00", "Walls to the frame"),
    ("Aluminium slab deck panel", "2400", 25, "4.00", "Suspended slabs"),
    ("Square column form, adjustable", "320", 18, "5.00", "Columns"),
    ("Slab props and primary beams", "2400", 30, "3.00", "Falsework under the slabs"),
)


async def seed_demo_formwork(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    demo_id: str,
    tenant_id: uuid.UUID | None = None,
) -> int:
    """Seed the catalogue and this project's formwork assignments.

    Returns the number of assignments created. Safe to call twice: a project
    that already carries formwork assignments is left alone, so re-installing
    a demo does not double its formwork.
    """
    existing = await session.scalar(
        select(FormworkAssignment.id).where(FormworkAssignment.project_id == project_id).limit(1),
    )
    if existing is not None:
        return 0

    service = FormworkService(session)
    # Global rows, so every demo project on this install shares one catalogue.
    await service.seed_defaults(tenant_id=tenant_id)

    rows = _RC_STRUCTURE if demo_id == "rc-structure-formwork" else _GENERIC
    wanted = {name for name, *_ in rows}
    result = await session.execute(select(FormworkSystem).where(FormworkSystem.name.in_(wanted)))
    # A name can exist both globally and tenant-scoped; either will price the
    # assignment identically, so the first one found is fine.
    by_name: dict[str, FormworkSystem] = {}
    for system in result.scalars().all():
        by_name.setdefault(system.name, system)

    created = 0
    for name, area, reuses, waste, note in rows:
        system = by_name.get(name)
        if system is None:
            # A catalogue row that was renamed out from under this list. Skip
            # the assignment rather than fail the whole demo install for it.
            logger.debug("Formwork demo: catalogue has no system named %r, skipping", name)
            continue
        # Never seed above the physical limit: the service refuses that on the
        # API path, and demo data that could not be entered by hand is a lie
        # about what the product accepts.
        capped = min(reuses, system.reuses_max)
        assignment = FormworkAssignment(
            project_id=project_id,
            formwork_system_id=system.id,
            area_m2=Decimal(area),
            reuse_count=capped,
            waste_pct=Decimal(waste),
            notes=note,
            tenant_id=tenant_id,
        )
        service._apply_cost(assignment, system)  # noqa: SLF001 - same module's own pricing
        session.add(assignment)
        created += 1

    await session.flush()
    return created
