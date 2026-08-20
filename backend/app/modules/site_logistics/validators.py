# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics validation - delivery window rules.

Two layers share the pure helpers in this file:

* The service (``service.py``) calls the helpers directly to *enforce* the
  rules at write time, raising ``HTTPException(400)`` with a clear message so a
  bad booking is never persisted.
* Three first-class :class:`ValidationRule` classes wrap the same helpers for
  the platform validation pipeline / traffic-light dashboard, satisfying the
  "no module without validation" requirement. The third one reaches across to
  the estimate: a delivery is booked against bill positions, so a position
  taking delivery of more than it prices is a finding.

The helpers are deliberately pure (stdlib ``datetime`` only, no ORM, no DB) so
they are trivially unit-testable and run on every deployment.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.core.validation.engine import (
    RuleCategory,
    RuleResult,
    Severity,
    ValidationContext,
    ValidationRule,
    rule_registry,
)
from app.modules.site_logistics.coverage import (
    BillLine,
    DeliveredLine,
    coverage_by_position,
    to_decimal,
)

logger = logging.getLogger(__name__)


# ── Pure helpers (no DB, unit-tested) ──────────────────────────────────────


def parse_hhmm(value: str | None) -> int | None:
    """Parse an ``"HH:MM"`` 24h string into minutes-since-midnight.

    Returns ``None`` for a missing or malformed value so callers can treat an
    unconfigured gate window as "no restriction" rather than a hard failure.
    """
    if not value or not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def delivery_within_gate_hours(
    open_time: str | None,
    close_time: str | None,
    window_start: datetime,
    window_end: datetime,
) -> tuple[bool, str | None]:
    """Check a delivery window falls inside a gate's daily operating hours.

    Returns ``(ok, reason)``. ``reason`` is a plain-English explanation when the
    window is rejected, and ``None`` when it passes. A gate with no configured
    hours (either bound missing/malformed) is treated as unrestricted -> passes.
    """
    if window_end <= window_start:
        return False, "Delivery window end must be after its start"

    open_min = parse_hhmm(open_time)
    close_min = parse_hhmm(close_time)
    if open_min is None or close_min is None:
        # Gate hours not configured - nothing to constrain against.
        return True, None
    if close_min <= open_min:
        # Non-sensical gate window; don't block deliveries on gate misconfig.
        return True, None

    # Gate hours are a time-of-day window, so a booking that crosses midnight
    # cannot sit inside a single day's opening hours.
    if window_start.date() != window_end.date():
        return False, "Delivery window must start and end on the same day as the gate's opening hours"

    start_min = window_start.hour * 60 + window_start.minute
    end_min = window_end.hour * 60 + window_end.minute
    if start_min < open_min:
        return False, f"Delivery starts before the gate opens ({open_time})"
    if end_min > close_min:
        return False, f"Delivery ends after the gate closes ({close_time})"
    return True, None


def windows_overlap(
    a_start: datetime,
    a_end: datetime,
    b_start: datetime,
    b_end: datetime,
) -> bool:
    """True when two half-open time windows ``[start, end)`` overlap.

    Touching windows (one ends exactly when the next starts) do NOT overlap, so
    back-to-back slots are allowed.
    """
    return a_start < b_end and a_end > b_start


def find_first_overlap(
    new_start: datetime,
    new_end: datetime,
    existing: Iterable[tuple[datetime, datetime]],
) -> tuple[datetime, datetime] | None:
    """Return the first existing window that overlaps ``[new_start, new_end)``.

    ``None`` when the new window is clear. Used to reject a second approved
    delivery that would clash on the same gate.
    """
    for start, end in existing:
        if windows_overlap(new_start, new_end, start, end):
            return start, end
    return None


# ── Validation-pipeline wrappers ───────────────────────────────────────────


def _as_dt(value: Any) -> datetime | None:
    """Coerce a datetime or ISO-8601 string into a datetime, else ``None``."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _deliveries(context: ValidationContext) -> list[dict[str, Any]]:
    data = context.data
    if isinstance(data, dict):
        items = data.get("deliveries", [])
        return [d for d in items if isinstance(d, dict)]
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _gates(context: ValidationContext) -> dict[str, dict[str, Any]]:
    data = context.data
    if isinstance(data, dict) and isinstance(data.get("gates"), dict):
        return {str(k): v for k, v in data["gates"].items() if isinstance(v, dict)}
    return {}


def _bill_positions(context: ValidationContext) -> list[BillLine]:
    """Read the bill positions out of a validation context, if it carries any."""
    data = context.data
    if not isinstance(data, dict):
        return []
    rows = data.get("bill_positions", [])
    if not isinstance(rows, list):
        return []
    out: list[BillLine] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(
            BillLine(
                position_id=str(row.get("id")),
                boq_id=str(row.get("boq_id") or ""),
                ordinal=str(row.get("ordinal") or ""),
                description=str(row.get("description") or ""),
                unit=str(row.get("unit") or ""),
                quantity=to_decimal(row.get("quantity")),
                unit_rate=to_decimal(row.get("unit_rate")),
            )
        )
    return out


def _delivery_lines(context: ValidationContext) -> list[DeliveredLine]:
    """Flatten every delivery's lines into ``(position, quantity, status)`` facts."""
    out: list[DeliveredLine] = []
    for delivery in _deliveries(context):
        lines = delivery.get("lines") or []
        if not isinstance(lines, list):
            continue
        for line in lines:
            if not isinstance(line, dict):
                continue
            position_id = line.get("boq_position_id")
            if not position_id:
                continue
            out.append(
                DeliveredLine(
                    position_id=str(position_id),
                    quantity=to_decimal(line.get("quantity")),
                    status=str(delivery.get("status") or ""),
                )
            )
    return out


class SiteLogisticsGateHoursRule(ValidationRule):
    """Every delivery must fall inside its gate's operating hours."""

    rule_id = "site_logistics.delivery_within_gate_hours"
    name = "Delivery within gate hours"
    standard = "site_logistics"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "A booked delivery window must fall within its gate's open/close hours"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        gates = _gates(context)
        results: list[RuleResult] = []
        for d in _deliveries(context):
            gate_id = d.get("gate_id")
            gate = gates.get(str(gate_id)) if gate_id is not None else None
            if gate is None:
                continue
            start = _as_dt(d.get("window_start"))
            end = _as_dt(d.get("window_end"))
            if start is None or end is None:
                continue
            ok, reason = delivery_within_gate_hours(
                gate.get("open_time"),
                gate.get("close_time"),
                start,
                end,
            )
            supplier = d.get("supplier_name") or "delivery"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=ok,
                    message="OK" if ok else f"{supplier}: {reason}",
                    element_ref=str(d.get("id") or ""),
                    suggestion=None if ok else "Move the delivery inside the gate's operating hours",
                )
            )
        return results


class SiteLogisticsDeliveryOverlapRule(ValidationRule):
    """Two approved deliveries on the same gate must not overlap in time."""

    rule_id = "site_logistics.no_approved_overlap"
    name = "No overlapping approved deliveries"
    standard = "site_logistics"
    severity = Severity.ERROR
    category = RuleCategory.CONSISTENCY
    description = "Two approved deliveries on the same gate must not overlap in their time windows"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        results: list[RuleResult] = []
        # Group approved deliveries by gate, preserving the running list so each
        # booking is only checked against those already seen (one row per clash).
        seen: dict[str, list[tuple[datetime, datetime]]] = {}
        for d in _deliveries(context):
            if d.get("status") != "approved":
                continue
            gate_id = d.get("gate_id")
            if gate_id is None:
                continue
            start = _as_dt(d.get("window_start"))
            end = _as_dt(d.get("window_end"))
            if start is None or end is None:
                continue
            key = str(gate_id)
            clash = find_first_overlap(start, end, seen.get(key, []))
            supplier = d.get("supplier_name") or "delivery"
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=clash is None,
                    message="OK" if clash is None else f"{supplier} overlaps another approved delivery on this gate",
                    element_ref=str(d.get("id") or ""),
                    suggestion=None if clash is None else "Pick a free slot or a different gate",
                )
            )
            seen.setdefault(key, []).append((start, end))
        return results


class SiteLogisticsOverDeliveryRule(ValidationRule):
    """No bill position may take delivery of more than the estimate priced."""

    rule_id = "site_logistics.no_over_delivery"
    name = "Deliveries stay within the bill"
    standard = "site_logistics"
    severity = Severity.WARNING
    category = RuleCategory.COMPLETENESS
    description = "The quantity delivered against a bill position must not exceed the quantity it prices"

    async def validate(self, context: ValidationContext) -> list[RuleResult]:
        bill = _bill_positions(context)
        if not bill:
            return []
        coverage = coverage_by_position(bill, _delivery_lines(context))
        results: list[RuleResult] = []
        for entry in bill:
            cov = coverage[str(entry.position_id)]
            if cov.delivery_line_count == 0:
                # Nothing booked against this line yet - the rule has nothing
                # to say, and a row per untouched position would drown the
                # report in noise.
                continue
            ordinal = entry.ordinal or entry.position_id
            results.append(
                RuleResult(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    category=self.category,
                    passed=not cov.over_delivered,
                    message=(
                        "OK"
                        if not cov.over_delivered
                        else (
                            f"{ordinal}: {cov.delivered_quantity} {entry.unit} delivered against "
                            f"{entry.quantity} {entry.unit} in the bill"
                        )
                    ),
                    element_ref=str(entry.position_id),
                    suggestion=(
                        None
                        if not cov.over_delivered
                        else "Check the delivery quantities, or raise a variation for the extra quantity"
                    ),
                )
            )
        return results


def register_site_logistics_validation_rules() -> None:
    """Register the site-logistics rules with the platform rule registry."""
    rule_registry.register(SiteLogisticsGateHoursRule(), ["site_logistics"])
    rule_registry.register(SiteLogisticsDeliveryOverlapRule(), ["site_logistics"])
    rule_registry.register(SiteLogisticsOverDeliveryRule(), ["site_logistics"])
    logger.debug("site_logistics: registered 3 validation rules")
