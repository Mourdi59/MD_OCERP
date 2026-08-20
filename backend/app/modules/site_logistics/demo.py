# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo gates, laydown zones and deliveries for a demo project.

Called from the demo project installer once the project's bill exists, so the
site-logistics board opens with a working day on it instead of an empty page,
and - the point of the module's link to the estimate - with deliveries booked
against real positions of that project's own bill. Without this the coverage
table has nothing to cover and the whole integration is invisible.

Every window is anchored to the day the demo is installed rather than to a
constant. A delivery board is about the next few days; a seed anchored to a
fixed date would show a schedule that is months stale by the time anybody
opens it.

The data is written to satisfy the module's own rules, because a demo that
trips its own validation teaches the wrong thing: every window sits inside its
gate's operating hours, and no two approved deliveries overlap on one gate.
Supplier names are supplied by the caller from the demo template's own vetted
companies - this seeder invents no company names.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# (name, open, close, capacity, note)
_GATES: tuple[tuple[str, str, str, int, str], ...] = (
    ("North gate", "07:00", "18:00", 2, "Main vehicle entrance. Banksman on duty for reversing."),
    ("South gate", "07:30", "16:00", 1, "Narrow approach, rigid vehicles only. No articulated deliveries."),
)

# (name, capacity description, usage note)
_ZONES: tuple[tuple[str, str, str], ...] = (
    ("Laydown A - north", "420 m2 / 60 t", "Reinforcement and formwork. Keep the crane radius clear."),
    ("Laydown B - compound", "180 m2", "Packaged materials and small plant. Covered storage at the east end."),
)

# (day offset from today, start hour, duration in hours, gate index, status,
#  share of the position quantity this drop carries, free-text cargo for the
#  drop that no bill line prices)
#
# Read as a working week: two drops already unloaded, one on site now, two
# approved and coming, one still waiting on the gate and one refused.
_DELIVERIES: tuple[tuple[int, int, int, int, str, str, str | None], ...] = (
    (-6, 8, 2, 0, "completed", "0.25", None),
    (-3, 9, 2, 0, "completed", "0.20", None),
    (0, 10, 2, 0, "arrived", "0.15", None),
    (1, 8, 2, 0, "approved", "0.20", None),
    (2, 13, 2, 1, "approved", "0.10", None),
    (3, 9, 2, 0, "requested", "0.10", None),
    (4, 8, 1, 1, "rejected", "0.05", "Site welfare unit exchange"),
)


def _window(base: datetime, day_offset: int, hour: int, hours: int) -> tuple[datetime, datetime]:
    """Return a ``(start, end)`` window on the given day, on the hour."""
    day = (base + timedelta(days=day_offset)).date()
    start = datetime.combine(day, time(hour=hour))
    return start, start + timedelta(hours=hours)


async def seed_demo_site_logistics(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    created_by: str | None = None,
    suppliers: list[str] | None = None,
    now: datetime | None = None,
) -> int:
    """Seed gates, laydown zones and bill-linked deliveries for one project.

    Args:
        session: Open async session; the caller owns the transaction.
        project_id: Project to seed.
        created_by: Acting user id recorded on every row.
        suppliers: Company names to use as delivery suppliers, in order. The
            caller passes the demo template's own companies so no new firm
            name enters the product here.
        now: Anchor for the delivery windows; defaults to the current day.

    Returns:
        How many deliveries were written. Zero means the project's bill had no
        deliverable position, in which case nothing at all is written - a
        delivery board with no bill behind it is the state this seeder exists
        to avoid.
    """
    from sqlalchemy import select

    from app.modules.boq.models import BOQ, Position
    from app.modules.site_logistics.coverage import to_decimal
    from app.modules.site_logistics.models import DeliveryBooking, DeliveryLine, Gate, LaydownZone

    base = now or datetime.now()
    names = [s for s in (suppliers or []) if s] or ["Main Contractor"]

    # The material lines of this project's own bill: leaves, priced, in bill
    # order. Section rows are excluded the same two ways the coverage query
    # excludes them (see BillPositionRepository._deliverable_positions).
    parents = (
        select(Position.parent_id)
        .join(BOQ, Position.boq_id == BOQ.id)
        .where(BOQ.project_id == project_id, Position.parent_id.is_not(None))
        .scalar_subquery()
    )
    stmt = (
        select(Position)
        .join(BOQ, Position.boq_id == BOQ.id)
        .where(
            BOQ.project_id == project_id,
            Position.unit != "section",
            Position.unit != "",
            Position.id.not_in(parents),
        )
        .order_by(Position.boq_id.asc(), Position.sort_order.asc())
        .limit(len(_DELIVERIES))
    )
    positions = list((await session.execute(stmt)).scalars().all())
    if not positions:
        logger.debug("Project %s has no deliverable bill position, skipping logistics seed", project_id)
        return 0

    gates: list[Gate] = []
    for name, open_time, close_time, capacity, note in _GATES:
        gate = Gate(
            id=uuid.uuid4(),
            project_id=project_id,
            name=name,
            open_time=open_time,
            close_time=close_time,
            capacity_per_slot=capacity,
            notes=note,
            created_by=created_by,
            metadata_={"is_demo": True},
        )
        session.add(gate)
        gates.append(gate)

    for name, capacity_desc, usage_note in _ZONES:
        session.add(
            LaydownZone(
                id=uuid.uuid4(),
                project_id=project_id,
                name=name,
                capacity_desc=capacity_desc,
                usage_note=usage_note,
                created_by=created_by,
                metadata_={"is_demo": True},
            )
        )

    # The gates have to exist before a delivery can name one. A booking carries
    # its gate as a plain ``gate_id`` value rather than through a relationship,
    # so the unit of work has no dependency to order the inserts by and is free
    # to write the delivery first - which the foreign key then refuses.
    await session.flush()

    written = 0
    for index, (day_offset, hour, hours, gate_index, status, share, extra_cargo) in enumerate(_DELIVERIES):
        position = positions[index % len(positions)]
        window_start, window_end = _window(base, day_offset, hour, hours)
        quantity = (to_decimal(position.quantity) * Decimal(share)).quantize(Decimal("0.01"))
        if quantity <= 0:
            # A position priced at zero quantity cannot be delivered against.
            continue
        session.add(
            DeliveryBooking(
                id=uuid.uuid4(),
                project_id=project_id,
                gate_id=gates[gate_index % len(gates)].id,
                supplier_name=names[index % len(names)],
                vehicle_type="Articulated flatbed" if gate_index == 0 else "Rigid 18t",
                materials_desc=extra_cargo,
                window_start=window_start,
                window_end=window_end,
                status=status,
                created_by=created_by,
                lines=[
                    DeliveryLine(
                        id=uuid.uuid4(),
                        boq_position_id=position.id,
                        position_ordinal=position.ordinal,
                        description=position.description,
                        quantity=quantity,
                        unit=position.unit,
                        sort_order=0,
                    )
                ],
                metadata_={"is_demo": True},
            )
        )
        written += 1

    await session.flush()
    logger.debug("Seeded %d demo deliveries for project %s", written, project_id)
    return written


async def seed_site_logistics_demo(session: AsyncSession, project_ids: list[uuid.UUID]) -> dict[str, int]:
    """Seed the delivery board for every demo project that has none yet.

    The installer seeds a project as it is created, which reaches new
    installations only. Every estate that already exists - including the public
    demo the module was built for - is filled by ``demo_enrichment``, which
    re-runs over existing projects, so a module wired only into the installer
    ships to an empty board on the very installations people look at.

    Self-guards per project on an existing gate or delivery, so a re-run adds
    nothing and a board somebody is already using is left alone.

    Args:
        session: Open async session; the caller commits.
        project_ids: Projects to consider. The caller passes the demo estate
            only - a delivery is a record a real project earns, and inventing
            one inside a customer's live project is a data-integrity problem.

    Returns:
        ``{"projects": n, "deliveries": m}``, empty when nothing was written.
    """
    from sqlalchemy import select

    from app.modules.projects.models import Project
    from app.modules.site_logistics.models import DeliveryBooking, Gate

    projects = 0
    deliveries = 0
    for project_id in project_ids:
        has_gate = (
            await session.execute(select(Gate.id).where(Gate.project_id == project_id).limit(1))
        ).scalar_one_or_none()
        has_delivery = (
            await session.execute(select(DeliveryBooking.id).where(DeliveryBooking.project_id == project_id).limit(1))
        ).scalar_one_or_none()
        if has_gate is not None or has_delivery is not None:
            continue

        project = await session.get(Project, project_id)
        if project is None:
            continue
        written = await seed_demo_site_logistics(
            session,
            project_id=project_id,
            created_by=str(project.owner_id) if project.owner_id else None,
            suppliers=_template_suppliers(project),
        )
        if written:
            projects += 1
            deliveries += written

    if not deliveries:
        return {}
    return {"projects": projects, "deliveries": deliveries}


def _template_suppliers(project: object) -> list[str]:
    """Return the demo template's own tender companies as supplier names.

    The same names the installer uses, resolved from the project's demo marker,
    so the enrichment path and the install path invent no company name and do
    not disagree about who delivers to a site. An unmarked project or a missing
    template yields an empty list, which the seeder reads as "use the generic
    contractor".
    """
    try:
        from app.core.demo_projects import DEMO_TEMPLATES, _firms

        metadata = getattr(project, "metadata_", None)
        demo_id = str(metadata.get("demo_id") or "").strip() if isinstance(metadata, dict) else ""
        template = DEMO_TEMPLATES.get(demo_id)
        if template is None:
            return []
        return [name for name, _email in _firms(template)]
    except Exception:
        logger.debug("Could not resolve demo suppliers for project", exc_info=True)
        return []
