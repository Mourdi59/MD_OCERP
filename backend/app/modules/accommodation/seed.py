# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo seed data for the accommodation module.

Loaded on demand via ``await seed_accommodation(session, project_ids)``.

Creates, per seeded project, one or two housing blocks (a worker camp and
a rental block), each with several rooms, a mix of occupied and vacant
bookings, and a few billable charges on the occupied rooms.

The seed is idempotent. It short-circuits and returns an empty dict when
an accommodation row already exists for the first project id, so it is
safe to call twice. It also avoids touching lazy relationship attributes
after a flush (which would raise MissingGreenlet under async SQLAlchemy)
by keeping created rows in local lists.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.accommodation.models import (
    Accommodation,
    Booking,
    Charge,
    Room,
)

logger = logging.getLogger(__name__)

# Up to two housing blocks per project. Each tuple is
# (name_suffix, kind, address, currency, base_rate, room_count, occupied_count).
_BLOCK_SPECS: list[tuple[str, str, str, str, str, int, int]] = [
    ("Worker Camp North", "worker_camp", "Site Road 1, North Gate", "EUR", "0", 6, 4),
    ("Rental Block A", "rental", "12 Market Street", "EUR", "650", 4, 2),
]

# Free-text occupants for the filled bookings (no Contacts dependency).
_OCCUPANTS: list[str] = [
    "Anna Schmidt",
    "Marco Rossi",
    "Pavel Novak",
    "Liam O'Brien",
    "Sofia Garcia",
    "Tomasz Kowalski",
]


async def _seed_one_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    project_index: int,
) -> dict[str, int]:
    """Seed a single project's accommodation blocks, rooms, bookings, charges.

    Args:
        session: Open async DB session.
        project_id: Project to seed against.
        project_index: Zero-based index used to keep room labels unique.

    Returns:
        Counts for the rows created for this project.
    """
    counts = {"accommodations": 0, "rooms": 0, "bookings": 0, "charges": 0}

    for block_idx, spec in enumerate(_BLOCK_SPECS):
        name_suffix, kind, address, currency, base_rate, room_count, occupied = spec
        accommodation = Accommodation(
            project_id=project_id,
            name=name_suffix,
            kind=kind,
            address=address,
            capacity_total=room_count,
            notes=f"{kind.replace('_', ' ').capitalize()} block, {room_count} rooms.",
            metadata_={"seed": True, "demo": True},
        )
        session.add(accommodation)
        await session.flush()
        counts["accommodations"] += 1

        # Create rooms; keep occupied/vacant split. Track rooms locally so we
        # never read accommodation.rooms (lazy load -> MissingGreenlet).
        rooms: list[Room] = []
        for room_idx in range(room_count):
            is_occupied = room_idx < occupied
            label = f"P{project_index:02d}-B{block_idx}-R{room_idx + 1:02d}"
            room = Room(
                accommodation_id=accommodation.id,
                label=label,
                capacity=2 if kind == "worker_camp" else 1,
                base_rate=Decimal(base_rate),
                base_rate_currency=currency,
                status="occupied" if is_occupied else "available",
                metadata_={"seed": True},
            )
            session.add(room)
            rooms.append(room)
        await session.flush()
        counts["rooms"] += len(rooms)

        # Bookings for the occupied rooms. Vacant rooms get no booking.
        bookings: list[Booking] = []
        for room_idx, room in enumerate(rooms):
            if room.status != "occupied":
                continue
            occupant = _OCCUPANTS[(block_idx * room_count + room_idx) % len(_OCCUPANTS)]
            # Open-ended residency for camps, fixed term for rentals.
            check_out = None if kind == "worker_camp" else date(2026, 12, 31)
            booking = Booking(
                room_id=room.id,
                occupant_name=occupant,
                check_in=date(2026, 5, 1),
                check_out=check_out,
                status="checked_in",
                source="manual",
                metadata_={"seed": True},
            )
            session.add(booking)
            bookings.append(booking)
        await session.flush()
        counts["bookings"] += len(bookings)

        # A few charges on the bookings (base rent + one extra on the first).
        for booking_idx, booking in enumerate(bookings):
            rent_amount = Decimal(base_rate) if Decimal(base_rate) > 0 else Decimal("0")
            session.add(
                Charge(
                    booking_id=booking.id,
                    kind="base_rent",
                    description="Monthly base rent",
                    amount=rent_amount,
                    currency=currency,
                    period_start=date(2026, 5, 1),
                    period_end=date(2026, 5, 31),
                    status="pending",
                    metadata_={"seed": True},
                )
            )
            counts["charges"] += 1
            if booking_idx == 0:
                session.add(
                    Charge(
                        booking_id=booking.id,
                        kind="extra",
                        description="Cleaning service",
                        amount=Decimal("45.00"),
                        currency=currency,
                        period_start=date(2026, 5, 1),
                        period_end=date(2026, 5, 31),
                        status="pending",
                        metadata_={"seed": True},
                    )
                )
                counts["charges"] += 1
        await session.flush()

    return counts


async def seed_accommodation(
    session: AsyncSession,
    project_ids: list[uuid.UUID],
) -> dict[str, int]:
    """Seed deterministic demo data for the accommodation module.

    Seeds every project the caller names, which the demo enrichment curates.
    Idempotent per project: one that already has an accommodation row is left
    alone while the rest are still filled.

    Args:
        session: Open async DB session.
        project_ids: Projects to seed against.

    Returns:
        Aggregated counts of rows inserted per entity, or an empty dict when
        the data already exists.
    """
    if not project_ids:
        logger.info("accommodation seed skipped: no project ids provided")
        return {}

    # Every project the caller named, rather than a prefix chosen here. The
    # caller decides which projects the demo fills (see _FOCUS_DEMO_IDS in
    # demo_enrichment); slicing again here would silently drop the tail of a
    # list somebody curated on purpose.
    targets: list[uuid.UUID] = list(project_ids)

    totals = {"accommodations": 0, "rooms": 0, "bookings": 0, "charges": 0}
    for idx, pid in enumerate(targets):
        # Asked per project rather than once on the first id. Guarding on
        # the flagship meant that once it had rows, every project added to the
        # curated set later was skipped forever, so widening the set only ever
        # took effect on a database that started empty.
        # The enumerate runs over the whole list rather than a filtered one:
        # the index picks this project's room names and booking dates, so
        # dropping a seeded project would renumber every project behind it.
        seeded = await session.execute(select(Accommodation.id).where(Accommodation.project_id == pid).limit(1))
        if seeded.scalar_one_or_none() is not None:
            continue
        counts = await _seed_one_project(session, pid, idx)
        for key, value in counts.items():
            totals[key] += value

    await session.flush()
    logger.info("accommodation seed complete: %s", totals)
    return totals
