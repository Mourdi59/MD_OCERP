# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site inventory demo seed - a stocked yard and a material ledger per project.

The module with the strongest estimate integration in the platform shipped
without a seeder, so every demo project opened it on an empty page: no storage
locations, no stock items, no movements, and therefore no material-cost variance
and no material actuals for post-calculation to read.

Nothing here is invented. Every stock item is a material line the project's own
estimate already prices, taken from the position's stored resource split, so the
item's name, unit and standard cost are the estimate's own numbers rather than a
description made up for a screen. Every consumption is booked against that same
BoQ position, and its quantity is sized from the progress the project has really
recorded, so what the ledger says was installed and what the progress module
says was installed describe one job rather than two.

What each project gets:

* three or four storage locations (yard, containers, a floor bay);
* one stock item per priced material line of a handful of its own positions,
  linked to the position that priced it;
* deliveries into stock (INBOUND), material installed against the position
  (CONSUMPTION), off-cuts and breakage (WASTE) and a relocation between two
  locations (TRANSFER).

Two numbers carry the whole story and both are drawn per position from a
deterministic per-project RNG: what the material actually cost to buy against
what the estimate allowed, and how much of it the crew actually drew per unit of
work. Their product is what post-calculation reports as the material variance,
so some positions beat the estimate on material and some lose on it, which is
the point of the report.

Every row is written through :class:`SiteInventoryService`, the same layer the
API uses, so each movement passes the same in-project reference checks and the
same schema validation as one recorded by hand. A row this seeder cannot write
is a row the application would have rejected too.

Dates are anchored to the run date, never hardcoded, so a demo opened a year
from now still shows deliveries from the last two months.

Idempotent per project: a project that already carries a stock item or a
movement is left untouched, so a re-run never doubles the ledger.
"""

from __future__ import annotations

import logging
import random
import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.price_breakdown import ResourceKind, coerce_kind
from app.modules.site_inventory.ledger import MovementType
from app.modules.site_inventory.models import StockItem, StockMovement
from app.modules.site_inventory.schemas import (
    LocationCreate,
    MovementCreate,
    StockItemCreate,
)
from app.modules.site_inventory.service import SiteInventoryService

logger = logging.getLogger(__name__)

_SEED = 4711
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")

# Storage locations a site yard actually has. Each project is dealt a sample of
# these rather than a rotation through them: a rotation over a pool of six hands
# out six pictures however many projects there are, while a sample of four from
# six gives fifteen distinct sets, and which four a project gets is drawn from
# its own id so a re-seed reproduces it.
_LOCATIONS: tuple[tuple[str, str, str], ...] = (
    ("Main laydown yard", "YARD-01", "North gate, hardstanding"),
    ("Site container A", "CNT-A", "Compound, next to the site office"),
    ("Site container B, consumables", "CNT-B", "Compound, rear row"),
    ("Rebar stockyard", "YARD-RB", "East boundary, covered racks"),
    ("Covered store, finishes", "STORE-01", "Ground floor, core B"),
    ("Level 2 floor bay", "BAY-L2", "Level 2, grid C/4"),
)

# How many locations a project opens. Indexed by the project's position in the
# call rather than drawn, so two neighbouring projects never look alike.
_LOCATION_COUNTS: tuple[int, ...] = (4, 3, 4, 3)

# How many of a project's own positions are metered. A store does not track
# every line of a several-hundred-line bill; it tracks the material that costs
# money and moves. Indexed by the project's position in the call, and past the
# end of the tuple a whole span is added so the counts stay distinct rather than
# repeating every fourth project.
_METERED_POSITIONS: tuple[int, ...] = (9, 7, 11, 8)
_METERED_SPAN = max(_METERED_POSITIONS) - min(_METERED_POSITIONS) + 1

# What the material actually cost to buy, as a multiple of the rate the estimate
# allowed. Below 1 the buyer beat the estimate, above it the market moved.
_PURCHASE_FACTOR_MIN = Decimal("0.88")
_PURCHASE_FACTOR_MAX = Decimal("1.16")

# How much material the crew drew per unit of work installed, as a multiple of
# the estimate's allowance. Above 1 the gang over-ordered or over-cut.
_DRAW_FACTOR_MIN = Decimal("0.96")
_DRAW_FACTOR_MAX = Decimal("1.12")

# Off-cuts and breakage found in the yard, as a share of what was consumed.
_WASTE_SHARE_MIN = Decimal("0.005")
_WASTE_SHARE_MAX = Decimal("0.025")

# How often a metered material books the waste it computed. Not every position
# in a yard has a waste ticket against it, so this is drawn - but the first
# material that consumed anything books its waste whatever the draw says. The
# waste ratio is the number the report exists to state, and a project whose
# materials all came up the other way states zero, which reads as a broken
# screen rather than as the draw it is. At the smallest register the seeder
# produces that is seven draws, so it happened about once in every two hundred
# and seventy projects before the first one was reserved.
_WASTE_DRAW_SHARE = 0.55

# What is still standing on site after the consumption booked so far, as a share
# of it. A store that has consumed everything it ever received reads as a store
# nobody has delivered to this month.
_ON_HAND_SHARE_MIN = Decimal("0.08")
_ON_HAND_SHARE_MAX = Decimal("0.30")

# Where a project sits when it has recorded no progress at all: the metered
# positions are treated as part built rather than untouched, because a store
# with deliveries and no consumption teaches nothing. Only used as a fallback,
# and only ever applied to a position the estimate really priced.
_ASSUMED_INSTALLED_MIN = Decimal("0.25")
_ASSUMED_INSTALLED_MAX = Decimal("0.65")

# Deliveries land across the last two months, consumption follows a delivery.
_DELIVERY_WINDOW_DAYS = 62
_MIN_CONSUMPTION_LAG_DAYS = 1
_MAX_CONSUMPTION_LAG_DAYS = 9

# Notes a storeman writes. Factual and about the material only.
_INBOUND_NOTES: tuple[str, ...] = (
    "Delivery checked against the delivery note, no damage.",
    "Delivery received, one pallet short, balance to follow.",
    "Delivery offloaded to the yard, tickets filed.",
    "Part delivery, remainder scheduled for next week.",
)
_CONSUMPTION_NOTES: tuple[str, ...] = (
    "Drawn by the gang for the works in progress.",
    "Issued to the crew against the works order.",
    "Drawn for the section under construction this week.",
)
_WASTE_NOTES: tuple[str, ...] = (
    "Off-cuts, not reusable.",
    "Damaged in handling, written off.",
    "Broken on offload, replaced from stock.",
)
_TRANSFER_NOTE = "Relocated closer to the workface."

# How many stock items one position contributes at most. A position usually
# prices one material line; where it prices more, the two biggest are metered
# and the rest stay in the estimate where they were priced.
_MAX_ITEMS_PER_POSITION = 2

# Deliveries per item. A single delivery reads as a purchase order, two or three
# read as a store being replenished.
_MIN_DELIVERIES = 1
_MAX_DELIVERIES = 3


def _rng_for(project_id: uuid.UUID) -> random.Random:
    """A deterministic RNG per project, so a re-seed reproduces the ledger."""
    return random.Random(f"{_SEED}:{project_id}")


def _dec(value: object, default: str = "0") -> Decimal:
    """Coerce an arbitrary stored value to a finite ``Decimal``, never raising."""
    if isinstance(value, Decimal):
        return value if value.is_finite() else Decimal(default)
    if value is None or value == "":
        return Decimal(default)
    try:
        out = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)
    return out if out.is_finite() else Decimal(default)


def _between(rng: random.Random, low: Decimal, high: Decimal) -> Decimal:
    """A ``Decimal`` drawn uniformly from ``[low, high]``, to four places.

    Drawn through ``randrange`` over the integer thousandths rather than through
    ``random()``, so the value is exact rather than a float rounded afterwards.
    """
    lo = int(low * 1000)
    hi = int(high * 1000)
    if hi <= lo:
        return low
    return Decimal(rng.randrange(lo, hi + 1)) / Decimal("1000")


def _money(value: Decimal) -> str:
    """Render a money magnitude the way the schemas expect it (2 dp string)."""
    return str(value.quantize(Decimal("0.01")))


def _qty(value: Decimal) -> str:
    """Render a quantity the way the schemas expect it (4 dp string)."""
    return str(value.quantize(Decimal("0.0001")))


class _MeteredMaterial:
    """One material line of one position, as this seeder meters it.

    Everything on it comes from the estimate: the name and unit the position's
    resource split states, the money that split allows per position unit, and
    the position it was priced against.
    """

    __slots__ = (
        "bill_quantity",
        "code",
        "description",
        "installed_quantity",
        "name",
        "position_id",
        "unit",
        "unit_cost",
    )

    def __init__(
        self,
        *,
        position_id: uuid.UUID,
        name: str,
        code: str,
        unit: str,
        unit_cost: Decimal,
        bill_quantity: Decimal,
        installed_quantity: Decimal,
        description: str,
    ) -> None:
        self.position_id = position_id
        self.name = name
        self.code = code
        self.unit = unit
        self.unit_cost = unit_cost
        self.bill_quantity = bill_quantity
        self.installed_quantity = installed_quantity
        self.description = description


def _material_lines(resources: object) -> list[dict[str, Any]]:
    """The material entries of a position's stored resource split.

    The split is the estimate's own per-unit buildup, so a material entry states
    what one unit of the position costs in material and in which unit it is
    measured. Anything that is not a dict, or whose type maps to another cost
    category, is left where it was priced.
    """
    if not isinstance(resources, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in resources:
        if not isinstance(entry, dict):
            continue
        kind = coerce_kind(entry.get("type") or entry.get("resource_type") or entry.get("kind"))
        if kind is ResourceKind.MATERIAL:
            out.append(entry)
    return out


def _per_unit_cost(resource: dict[str, Any]) -> Decimal:
    """Material money one position unit carries, from the estimate's own split.

    Prefers ``quantity * unit_rate`` so the figure survives a factor edit that
    left a stale ``total`` behind, exactly the rule the BoQ cost breakdown and
    post-calculation both use.
    """
    quantity = resource.get("quantity")
    rate = resource.get("unit_rate")
    if quantity is not None and rate is not None:
        return _dec(quantity) * _dec(rate)
    return _dec(resource.get("total"))


async def _project_currency(session: AsyncSession, project_id: uuid.UUID) -> str:
    """Best-effort project base currency (empty string when unknown)."""
    try:
        from app.modules.projects.models import Project

        row = (await session.execute(select(Project.currency).where(Project.id == project_id))).first()
    except Exception:
        logger.debug("Project currency unavailable for project=%s", project_id)
        return ""
    if not row or not row[0]:
        return ""
    return str(row[0]).strip()[:3].upper()


async def _installed_fractions(
    session: AsyncSession,
    project_id: uuid.UUID,
    position_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, Decimal]:
    """Installed share per position, from the progress the project recorded.

    The same source post-calculation reads, so the quantity this seeder consumes
    and the quantity that report calls installed come from one place. Returns an
    empty map when the progress module is unavailable or has no readings, and
    the caller then falls back to an assumed share rather than to zero.
    """
    if not position_ids:
        return {}
    try:
        from app.modules.progress.repository import ProgressRepository

        pct_by_pid = await ProgressRepository(session).latest_pct_for_positions(project_id, list(position_ids))
    except Exception:
        logger.debug("Progress readings unavailable for project=%s", project_id)
        return {}
    out: dict[uuid.UUID, Decimal] = {}
    for pid, pct in pct_by_pid.items():
        share = _dec(pct) / _HUNDRED
        if share > _ZERO:
            out[pid] = min(share, Decimal("1"))
    return out


async def _metered_materials(
    session: AsyncSession,
    project_id: uuid.UUID,
    rng: random.Random,
    limit: int,
) -> list[_MeteredMaterial]:
    """Pick the positions this project meters, and their priced material lines.

    A position qualifies when the estimate priced it (a quantity and a material
    line in its resource split); the biggest-spending ones are offered first,
    because those are the ones a store actually tracks, and the sample is drawn
    from that shortlist so two projects meter different work.
    """
    try:
        from app.modules.boq.models import BOQ, Position

        stmt = (
            select(
                Position.id,
                Position.reference_code,
                Position.ordinal,
                Position.description,
                Position.unit,
                Position.quantity,
                Position.total,
                Position.metadata_,
            )
            .join(BOQ, Position.boq_id == BOQ.id)
            .where(BOQ.project_id == project_id)
            .order_by(Position.ordinal)
        )
        rows = (await session.execute(stmt)).all()
    except Exception:
        logger.debug("BOQ lookup unavailable for project=%s", project_id)
        return []

    candidates: list[tuple[Decimal, uuid.UUID, str, str, Decimal, list[dict[str, Any]]]] = []
    for pid, reference_code, ordinal, description, unit, quantity, total, metadata in rows:
        bill_quantity = _dec(quantity)
        if bill_quantity <= _ZERO:
            continue
        resources = metadata.get("resources") if isinstance(metadata, dict) else None
        materials = _material_lines(resources)
        if not materials:
            continue
        ref = str(reference_code or ordinal or "").strip()
        candidates.append(
            (
                _dec(total),
                pid,
                ref,
                str(description or "").strip(),
                bill_quantity,
                materials,
            ),
        )
    if not candidates:
        return []

    candidates.sort(key=lambda row: row[0], reverse=True)
    shortlist = candidates[: max(limit * 2, limit)]
    picked = rng.sample(shortlist, k=min(limit, len(shortlist)))
    picked.sort(key=lambda row: row[2])

    installed = await _installed_fractions(session, project_id, [row[1] for row in picked])

    out: list[_MeteredMaterial] = []
    for _total, pid, ref, description, bill_quantity, materials in picked:
        share = installed.get(pid)
        if share is None:
            share = _between(rng, _ASSUMED_INSTALLED_MIN, _ASSUMED_INSTALLED_MAX)
        ranked = sorted(materials, key=_per_unit_cost, reverse=True)[:_MAX_ITEMS_PER_POSITION]
        for index, resource in enumerate(ranked, start=1):
            unit_cost = _per_unit_cost(resource)
            if unit_cost <= _ZERO:
                # A material line priced at nothing would put a zero unit cost
                # on every movement, and a zero unit cost is what makes an
                # actual cost unknowable rather than free.
                continue
            name = str(resource.get("name") or description or "").strip()
            if not name:
                continue
            code = str(resource.get("code") or f"{ref}-M{index}").strip()
            out.append(
                _MeteredMaterial(
                    position_id=pid,
                    name=name[:255],
                    code=code[:64],
                    unit=str(resource.get("unit") or "").strip()[:20],
                    unit_cost=unit_cost,
                    bill_quantity=bill_quantity,
                    installed_quantity=bill_quantity * share,
                    description=description,
                ),
            )
    return out


async def _seed_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    actor_id: str | None,
    ordinal: int,
) -> dict[str, int]:
    """Seed one project's yard and ledger. Returns per-entity counts."""
    empty = {"projects": 0, "locations": 0, "items": 0, "movements": 0}

    already_item = (
        (await session.execute(select(StockItem.id).where(StockItem.project_id == project_id).limit(1)))
        .scalars()
        .first()
    )
    already_movement = (
        (await session.execute(select(StockMovement.id).where(StockMovement.project_id == project_id).limit(1)))
        .scalars()
        .first()
    )
    if already_item is not None or already_movement is not None:
        return empty

    rng = _rng_for(project_id)
    slot = ordinal % len(_METERED_POSITIONS)
    metered = _METERED_POSITIONS[slot] + (ordinal // len(_METERED_POSITIONS)) * _METERED_SPAN
    materials = await _metered_materials(session, project_id, rng, metered)
    if not materials:
        # Without a priced bill carrying a material buildup there is nothing
        # honest to meter: every item here is a line the estimate priced.
        logger.debug("Site inventory demo skipped for project=%s (no priced material lines)", project_id)
        return empty

    currency = await _project_currency(session, project_id)
    service = SiteInventoryService(session)
    counts = {"projects": 1, "locations": 0, "items": 0, "movements": 0}

    location_count = _LOCATION_COUNTS[ordinal % len(_LOCATION_COUNTS)]
    chosen = rng.sample(_LOCATIONS, k=min(location_count, len(_LOCATIONS)))
    locations: list[uuid.UUID] = []
    for name, code, address in chosen:
        location = await service.create_location(
            project_id,
            LocationCreate(name=name, code=code, address=address),
        )
        locations.append(location.id)
        counts["locations"] += 1

    today = datetime.now(UTC)

    # Cleared by the first material that books waste, drawn or reserved, so the
    # report always has a ratio to state and only one material is ever forced.
    reserve_waste = True

    for material in materials:
        home = rng.choice(locations)
        item = await service.create_item(
            project_id,
            StockItemCreate(
                name=material.name,
                sku=material.code,
                unit=material.unit,
                boq_position_id=material.position_id,
                default_location_id=home,
                standard_unit_cost=_money(material.unit_cost),
                currency=currency,
                reorder_point=_qty(material.bill_quantity / Decimal("20")),
            ),
        )
        counts["items"] += 1

        # The two numbers the whole report turns on, drawn once per item so the
        # position tells one consistent story across its movements.
        purchase_factor = _between(rng, _PURCHASE_FACTOR_MIN, _PURCHASE_FACTOR_MAX)
        draw_factor = _between(rng, _DRAW_FACTOR_MIN, _DRAW_FACTOR_MAX)
        paid_unit_cost = material.unit_cost * purchase_factor
        consumed = material.installed_quantity * draw_factor
        if consumed <= _ZERO:
            continue
        wasted = consumed * _between(rng, _WASTE_SHARE_MIN, _WASTE_SHARE_MAX)
        on_hand = consumed * _between(rng, _ON_HAND_SHARE_MIN, _ON_HAND_SHARE_MAX)
        delivered = consumed + wasted + on_hand

        # Deliveries first, so stock is never drawn before it arrived.
        delivery_count = rng.randint(_MIN_DELIVERIES, _MAX_DELIVERIES)
        first_delivery_age = rng.randint(
            _MAX_CONSUMPTION_LAG_DAYS + 1,
            _DELIVERY_WINDOW_DAYS,
        )
        for leg in range(delivery_count):
            # Split the delivered quantity across the legs, the last one taking
            # the remainder so the legs sum exactly to what arrived.
            if leg == delivery_count - 1:
                leg_quantity = delivered - (delivered / delivery_count * (delivery_count - 1))
            else:
                leg_quantity = delivered / delivery_count
            if leg_quantity <= _ZERO:
                continue
            age = max(first_delivery_age - leg * rng.randint(3, 9), 1)
            await service.record_movement(
                project_id,
                MovementCreate(
                    item_id=item.id,
                    movement_type=MovementType.INBOUND.value,
                    quantity=_qty(leg_quantity),
                    unit_cost=_money(paid_unit_cost),
                    currency=currency,
                    location_id=home,
                    occurred_at=today - timedelta(days=age),
                    note=rng.choice(_INBOUND_NOTES),
                ),
                actor_id,
            )
            counts["movements"] += 1

        consumption_age = max(
            first_delivery_age - rng.randint(_MIN_CONSUMPTION_LAG_DAYS, _MAX_CONSUMPTION_LAG_DAYS),
            0,
        )
        await service.record_movement(
            project_id,
            MovementCreate(
                item_id=item.id,
                movement_type=MovementType.CONSUMPTION.value,
                quantity=_qty(consumed),
                unit_cost=_money(paid_unit_cost),
                currency=currency,
                location_id=home,
                boq_position_id=material.position_id,
                occurred_at=today - timedelta(days=consumption_age),
                note=rng.choice(_CONSUMPTION_NOTES),
            ),
            actor_id,
        )
        counts["movements"] += 1

        if wasted > _ZERO:
            # The draw is made either way, so reserving the first material does
            # not shift the generator for anything that follows it.
            drawn = rng.random() < _WASTE_DRAW_SHARE
            if reserve_waste or drawn:
                reserve_waste = False
                await service.record_movement(
                    project_id,
                    MovementCreate(
                        item_id=item.id,
                        movement_type=MovementType.WASTE.value,
                        quantity=_qty(wasted),
                        unit_cost=_money(paid_unit_cost),
                        currency=currency,
                        location_id=home,
                        occurred_at=today - timedelta(days=max(consumption_age - 1, 0)),
                        note=rng.choice(_WASTE_NOTES),
                    ),
                    actor_id,
                )
                counts["movements"] += 1

        if len(locations) > 1 and on_hand > _ZERO and rng.random() < 0.3:
            destination = rng.choice([loc for loc in locations if loc != home])
            await service.record_movement(
                project_id,
                MovementCreate(
                    item_id=item.id,
                    movement_type=MovementType.TRANSFER.value,
                    quantity=_qty(on_hand / Decimal("2")),
                    unit_cost=_money(paid_unit_cost),
                    currency=currency,
                    location_id=home,
                    to_location_id=destination,
                    occurred_at=today - timedelta(days=max(consumption_age - 2, 0)),
                    note=_TRANSFER_NOTE,
                ),
                actor_id,
            )
            counts["movements"] += 1

    return counts


async def seed_site_inventory_demo(
    session: AsyncSession,
    project_ids: Iterable[uuid.UUID],
) -> dict[str, int]:
    """Populate the site-inventory yard and ledger for the given demo projects.

    Args:
        session: Async DB session. The caller commits.
        project_ids: Projects to seed. Each is skipped when it already carries a
            stock item or a movement, and when its bill prices no material.

    Returns:
        Dict with per-entity insert counts across every project seeded.
    """
    totals = {"projects": 0, "locations": 0, "items": 0, "movements": 0}
    ids = list(project_ids)
    if not ids:
        return totals

    from app.modules.projects.models import Project

    rows = (await session.execute(select(Project.id, Project.owner_id).where(Project.id.in_(ids)))).all()
    owners = {pid: str(owner) if owner else None for pid, owner in rows}

    for ordinal, project_id in enumerate(ids):
        if project_id not in owners:
            continue
        try:
            # A SAVEPOINT per project, so one project that cannot be seeded
            # costs only its own rows. Catching the exception is not enough on
            # PostgreSQL: a failed statement aborts the whole transaction, and
            # every later project would then fail on a poisoned session rather
            # than on anything wrong with itself.
            async with session.begin_nested():
                counts = await _seed_project(session, project_id, owners[project_id], ordinal)
        except Exception:
            logger.warning("Site inventory demo seed skipped for project=%s (non-fatal)", project_id, exc_info=True)
            continue
        for key, value in counts.items():
            totals[key] += value
    return totals
