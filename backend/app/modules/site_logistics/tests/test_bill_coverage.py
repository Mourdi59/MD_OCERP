# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""DB-free tests for the bill-coverage arithmetic.

Exercises the pure fold in ``coverage.py`` - the numbers the logistics page
prints against every estimate line - plus the over-delivery validation rule that
reads the same helper. No ORM / DB import, so this runs on every deployment.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from app.core.validation.engine import ValidationContext
from app.modules.site_logistics.coverage import (
    BOOKED_STATUSES,
    DELIVERED_STATUSES,
    BillLine,
    DeliveredLine,
    coverage_by_position,
    to_decimal,
)
from app.modules.site_logistics.validators import SiteLogisticsOverDeliveryRule


def _bill(position_id: str = "p1", quantity: str = "100", unit_rate: str = "85.50") -> BillLine:
    return BillLine(
        position_id=position_id,
        boq_id="b1",
        ordinal="03.10.020",
        description="C30/37 in-situ concrete to slabs",
        unit="m3",
        quantity=Decimal(quantity),
        unit_rate=Decimal(unit_rate),
    )


# ── to_decimal ─────────────────────────────────────────────────────────────


def test_to_decimal_parses_the_strings_a_bill_stores() -> None:
    assert to_decimal("120.5000") == Decimal("120.5000")
    assert to_decimal(Decimal("7")) == Decimal("7")
    assert to_decimal(3) == Decimal("3")


def test_to_decimal_never_raises_on_a_hand_edited_bill() -> None:
    # A blank, a stray unit, a None - the coverage table must still render.
    assert to_decimal("") == Decimal("0")
    assert to_decimal("   ") == Decimal("0")
    assert to_decimal("12 m3") == Decimal("0")
    assert to_decimal(None) == Decimal("0")
    assert to_decimal(True) == Decimal("0")


# ── coverage_by_position ───────────────────────────────────────────────────


def test_a_position_with_no_deliveries_is_entirely_outstanding() -> None:
    coverage = coverage_by_position([_bill()], [])
    row = coverage["p1"]
    assert row.delivered_quantity == Decimal("0")
    assert row.booked_quantity == Decimal("0")
    assert row.outstanding_quantity == Decimal("100")
    assert row.delivered_value == Decimal("0")
    assert row.delivery_line_count == 0
    assert row.over_delivered is False


def test_arrived_counts_as_delivered_and_is_priced_at_the_bill_rate() -> None:
    coverage = coverage_by_position(
        [_bill()],
        [DeliveredLine("p1", Decimal("40"), "arrived")],
    )
    row = coverage["p1"]
    assert row.delivered_quantity == Decimal("40")
    assert row.delivered_value == Decimal("40") * Decimal("85.50")
    assert row.outstanding_quantity == Decimal("60")


def test_requested_and_approved_are_booked_not_delivered() -> None:
    coverage = coverage_by_position(
        [_bill()],
        [
            DeliveredLine("p1", Decimal("30"), "requested"),
            DeliveredLine("p1", Decimal("20"), "approved"),
        ],
    )
    row = coverage["p1"]
    # Nothing has arrived, so nothing is on site and nothing has value.
    assert row.delivered_quantity == Decimal("0")
    assert row.delivered_value == Decimal("0")
    assert row.booked_quantity == Decimal("50")
    assert row.outstanding_quantity == Decimal("50")


def test_a_rejected_delivery_covers_nothing() -> None:
    coverage = coverage_by_position(
        [_bill()],
        [DeliveredLine("p1", Decimal("500"), "rejected")],
    )
    row = coverage["p1"]
    assert row.delivered_quantity == Decimal("0")
    assert row.booked_quantity == Decimal("0")
    assert row.outstanding_quantity == Decimal("100")
    # It still exists on the booking, so the line is counted.
    assert row.delivery_line_count == 1


def test_the_two_status_buckets_never_overlap() -> None:
    assert not set(DELIVERED_STATUSES) & set(BOOKED_STATUSES)
    assert "rejected" not in set(DELIVERED_STATUSES) | set(BOOKED_STATUSES)


def test_several_drops_of_the_same_position_add_up() -> None:
    coverage = coverage_by_position(
        [_bill()],
        [
            DeliveredLine("p1", Decimal("25"), "completed"),
            DeliveredLine("p1", Decimal("25"), "arrived"),
            DeliveredLine("p1", Decimal("10"), "approved"),
        ],
    )
    row = coverage["p1"]
    assert row.delivered_quantity == Decimal("50")
    assert row.booked_quantity == Decimal("10")
    assert row.outstanding_quantity == Decimal("40")
    assert row.delivery_line_count == 3


def test_over_delivery_shows_as_a_negative_outstanding_and_is_flagged() -> None:
    coverage = coverage_by_position(
        [_bill(quantity="100")],
        [DeliveredLine("p1", Decimal("140"), "completed")],
    )
    row = coverage["p1"]
    assert row.over_delivered is True
    assert row.outstanding_quantity == Decimal("-40")


def test_lines_for_an_unknown_position_are_ignored() -> None:
    coverage = coverage_by_position(
        [_bill()],
        [DeliveredLine("gone", Decimal("999"), "completed")],
    )
    assert set(coverage) == {"p1"}
    assert coverage["p1"].delivered_quantity == Decimal("0")


# ── The validation rule that reads the same fold ───────────────────────────


def _context(bill_positions: list[dict], deliveries: list[dict]) -> ValidationContext:
    return ValidationContext(data={"bill_positions": bill_positions, "deliveries": deliveries})


def test_over_delivery_rule_flags_the_position_that_took_too_much() -> None:
    context = _context(
        [{"id": "p1", "ordinal": "03.10.020", "unit": "m3", "quantity": "100", "unit_rate": "85.50"}],
        [
            {
                "id": "d1",
                "status": "completed",
                "lines": [{"boq_position_id": "p1", "quantity": "140"}],
            }
        ],
    )
    results = asyncio.run(SiteLogisticsOverDeliveryRule().validate(context))
    assert len(results) == 1
    assert results[0].passed is False
    assert "03.10.020" in results[0].message


def test_over_delivery_rule_passes_a_position_inside_its_bill_quantity() -> None:
    context = _context(
        [{"id": "p1", "ordinal": "03.10.020", "unit": "m3", "quantity": "100", "unit_rate": "85.50"}],
        [
            {
                "id": "d1",
                "status": "arrived",
                "lines": [{"boq_position_id": "p1", "quantity": "60"}],
            }
        ],
    )
    results = asyncio.run(SiteLogisticsOverDeliveryRule().validate(context))
    assert len(results) == 1
    assert results[0].passed is True


def test_over_delivery_rule_stays_silent_on_positions_nobody_booked_against() -> None:
    context = _context(
        [{"id": "p1", "ordinal": "03.10.020", "unit": "m3", "quantity": "100", "unit_rate": "85.50"}],
        [],
    )
    assert asyncio.run(SiteLogisticsOverDeliveryRule().validate(context)) == []


def test_over_delivery_rule_ignores_a_delivery_line_with_no_bill_position() -> None:
    # A skip or a welfare unit: real cargo, but nothing in the bill to exceed.
    context = _context(
        [{"id": "p1", "ordinal": "03.10.020", "unit": "m3", "quantity": "100", "unit_rate": "85.50"}],
        [{"id": "d1", "status": "completed", "lines": [{"description": "Skip exchange", "quantity": "1"}]}],
    )
    assert asyncio.run(SiteLogisticsOverDeliveryRule().validate(context)) == []
