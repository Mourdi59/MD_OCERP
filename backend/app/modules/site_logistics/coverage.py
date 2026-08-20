# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Bill coverage arithmetic: what the estimate ordered against what has arrived.

The site-logistics board books deliveries against BOQ positions, so every
position can be read back as a small ledger:

    bill quantity  = what the estimate says has to be built
    delivered      = the lines on deliveries that reached the site
    booked         = the lines on deliveries still inbound
    outstanding    = bill - delivered - booked, i.e. what nobody has arranged yet

Deliberately pure: stdlib ``decimal`` only, no ORM and no DB, so the numbers on
the page are unit-tested directly and the same helpers can back a validation
rule. The repository supplies plain rows; this module does the arithmetic.

A rejected delivery counts towards nothing - it holds no slot and nothing is
coming - and "delivered" is kept apart from "booked" on purpose: a lorry that is
still on the motorway has not covered a bill line, and a quantity surveyor
reading one number that quietly mixed the two would sign off work that is not
there.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

__all__ = [
    "BOOKED_STATUSES",
    "DELIVERED_STATUSES",
    "BillLine",
    "DeliveredLine",
    "PositionCoverage",
    "coverage_by_position",
    "to_decimal",
]

#: Delivery statuses whose lines count as physically on site.
DELIVERED_STATUSES: tuple[str, ...] = ("arrived", "completed")
#: Delivery statuses whose lines are arranged but have not arrived yet.
#: ``rejected`` is in neither tuple - it holds no slot and brings nothing.
BOOKED_STATUSES: tuple[str, ...] = ("requested", "approved")

_ZERO = Decimal("0")


def to_decimal(value: object) -> Decimal:
    """Coerce a stored quantity or rate into a ``Decimal``, never raising.

    BOQ positions keep ``quantity`` / ``unit_rate`` as strings (see the comment
    on :class:`app.modules.boq.models.Position`), and a hand-edited bill can
    hold a blank or a value with a stray unit in it. A coverage table must
    still render, so anything unparseable reads as zero rather than a 500.

    Args:
        value: A Decimal, int, float, string or None.

    Returns:
        The value as a Decimal, or ``Decimal("0")`` when it cannot be parsed.
    """
    if isinstance(value, Decimal):
        return value
    if value is None:
        return _ZERO
    if isinstance(value, bool):
        # bool is an int subclass; a flag is not a quantity.
        return _ZERO
    if isinstance(value, int | float):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return _ZERO
    text = str(value).strip()
    if not text:
        return _ZERO
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return _ZERO


@dataclass(frozen=True)
class BillLine:
    """One BOQ position as the coverage table needs it."""

    position_id: str
    boq_id: str
    ordinal: str
    description: str
    unit: str
    quantity: Decimal
    unit_rate: Decimal


@dataclass(frozen=True)
class DeliveredLine:
    """One delivery line: a quantity against a position, at a delivery status."""

    position_id: str
    quantity: Decimal
    status: str


@dataclass(frozen=True)
class PositionCoverage:
    """The delivery ledger of a single bill position."""

    position_id: str
    delivered_quantity: Decimal
    booked_quantity: Decimal
    outstanding_quantity: Decimal
    delivered_value: Decimal
    delivery_line_count: int
    over_delivered: bool


def coverage_by_position(
    bill: Iterable[BillLine],
    lines: Iterable[DeliveredLine],
) -> dict[str, PositionCoverage]:
    """Fold delivery lines onto bill positions.

    Args:
        bill: The positions to report on. Positions with no delivery line still
            get a row, showing everything outstanding - that is the whole point
            of the table.
        lines: Delivery lines. Lines whose position is not in ``bill`` are
            ignored (a detached line, or a position filtered out of the view).

    Returns:
        A mapping of position id to its :class:`PositionCoverage`. Quantities
        are never clamped: an over-delivery shows as a negative outstanding and
        raises ``over_delivered``, because hiding it is how a site ends up
        paying for concrete it did not order.
    """
    delivered: dict[str, Decimal] = {}
    booked: dict[str, Decimal] = {}
    counts: dict[str, int] = {}

    for line in lines:
        pid = str(line.position_id)
        qty = line.quantity if isinstance(line.quantity, Decimal) else to_decimal(line.quantity)
        if line.status in DELIVERED_STATUSES:
            delivered[pid] = delivered.get(pid, _ZERO) + qty
        elif line.status in BOOKED_STATUSES:
            booked[pid] = booked.get(pid, _ZERO) + qty
        else:
            # Rejected (or an unknown status from a future release): counts
            # towards no bucket, but the line still exists on the booking.
            counts[pid] = counts.get(pid, 0) + 1
            continue
        counts[pid] = counts.get(pid, 0) + 1

    result: dict[str, PositionCoverage] = {}
    for entry in bill:
        pid = str(entry.position_id)
        got = delivered.get(pid, _ZERO)
        due = booked.get(pid, _ZERO)
        result[pid] = PositionCoverage(
            position_id=pid,
            delivered_quantity=got,
            booked_quantity=due,
            outstanding_quantity=entry.quantity - got - due,
            delivered_value=got * entry.unit_rate,
            delivery_line_count=counts.get(pid, 0),
            over_delivered=got > entry.quantity,
        )
    return result
