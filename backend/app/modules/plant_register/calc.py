# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the plant register: dates, lead time, route, scoring.

No database, no clock: every function takes ``today`` and the rows it judges,
so each numbered SPEC rule is a table-driven unit test. Days are whole calendar
days (Decision 8); weeks are whole weeks; money never appears here except in
the decision-paper cost, which stays ``Decimal``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.modules.plant_register.ports import CommitmentRef, OwnerFurnishedRef, PackagePlan

ITEM_STATES: tuple[str, ...] = (
    "identified",
    "specified",
    "enquired",
    "route_set",
    "ordered",
    "manufactured",
    "delivered",
    "installed",
    "commissioned",
    "handed_over",
)
LEAD_BASES: tuple[str, ...] = ("from_order", "from_approved_drawings", "from_down_payment")
NO_MARKET_EVIDENCE = "catalogue_default"


def state_rank(state: str) -> int:
    """Position in the lifecycle; ``cancelled`` and unknown states rank -1."""
    return ITEM_STATES.index(state) if state in ITEM_STATES else -1


def at_least(state: str, target: str) -> bool:
    return state_rank(state) >= state_rank(target)


def is_ordered(state: str) -> bool:
    return at_least(state, "ordered")


# ── need date and order date (rule 5) ─────────────────────────────────────


def parse_day(value: Any) -> date | None:
    """A calendar day from a ``date`` or an ISO string; anything else is ``None``."""
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def need_date(
    *, activity_late_start: Any = None, activity_start: Any = None, fixed: date | None = None
) -> tuple[date | None, str]:
    """The date the plant is needed on site and where it came from.

    Activity late start first (the last responsible moment), then its planned
    start, then a fixed date the owner typed. ``none`` when nothing is known.
    """
    late = parse_day(activity_late_start)
    if late is not None:
        return late, "activity_late_start"
    start = parse_day(activity_start)
    if start is not None:
        return start, "activity_start"
    if fixed is not None:
        return fixed, "fixed"
    return None, "none"


@dataclass(frozen=True)
class Buffers:
    """Days subtracted after the lead time; catalogue defaults, overridable per item."""

    transport_days: int
    install_lead_days: int
    approval_buffer_days: int
    drawing_review_days: int

    @classmethod
    def merged(cls, defaults: Any, override: Mapping[str, Any] | None) -> Buffers:
        o = dict(override or {})

        def pick(name: str) -> int:
            v = o.get(name)
            return int(v) if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else int(getattr(defaults, name))

        return cls(
            pick("transport_days"),
            pick("install_lead_days"),
            pick("approval_buffer_days"),
            pick("drawing_review_days"),
        )


def latest_order_date(
    need: date | None,
    lead_weeks: int | None,
    lead_basis: str | None,
    buffers: Buffers,
    *,
    review_period_days: int | None = None,
) -> date | None:
    """``need - lead*7 - transport - install - approval buffer`` (minus drawing review when the
    lead runs from approved drawings: the linked submittal's review period, else the catalogue's).
    """
    if need is None or lead_weeks is None:
        return None
    days = lead_weeks * 7 + buffers.transport_days + buffers.install_lead_days + buffers.approval_buffer_days
    if lead_basis == "from_approved_drawings":
        days += review_period_days if review_period_days is not None else buffers.drawing_review_days
    return need - timedelta(days=days)


# ── lead time (rules 2, 3, 4, 6) ──────────────────────────────────────────


@dataclass(frozen=True)
class QuoteView:
    """The quote fields the rules read."""

    id: uuid.UUID | None
    source: str
    enquiry_date: date
    response_date: date | None
    lead_weeks_min: int
    lead_weeks_max: int
    lead_basis: str
    is_basis: bool
    superseded: bool = False


def quote_errors(
    *, enquiry_date: date | None, response_date: date | None, lead_min: int, lead_max: int, today: date
) -> list[str]:
    """Rule 2 plus range sanity. Error codes, empty when the quote may be recorded."""
    if enquiry_date is None:
        return ["lead_time_without_enquiry_date"]
    errors: list[str] = []
    if enquiry_date > today:
        errors.append("enquiry_date_in_future")
    if response_date is not None and response_date < enquiry_date:
        errors.append("response_before_enquiry")
    if lead_min < 0 or lead_max < lead_min:
        errors.append("lead_weeks_range_invalid")
    return errors


def basis_quote(quotes: Iterable[QuoteView]) -> QuoteView | None:
    live = [q for q in quotes if q.is_basis and not q.superseded]
    return live[0] if len(live) == 1 else None


def basis_count(quotes: Iterable[QuoteView]) -> int:
    return sum(1 for q in quotes if q.is_basis and not q.superseded)


def effective_lead(basis: QuoteView | None, catalogue_max: int | None) -> tuple[int | None, str]:
    """Rule: basis quote max weeks, else the class default flagged ``catalogue_default``."""
    if basis is not None:
        return basis.lead_weeks_max, basis.source
    if catalogue_max is not None:
        return catalogue_max, NO_MARKET_EVIDENCE
    return None, "none"


def quote_age_days(quote: QuoteView | None, today: date) -> int | None:
    """Age of the information: from the response if there is one, else from the enquiry."""
    if quote is None:
        return None
    return (today - (quote.response_date or quote.enquiry_date)).days


def is_stale(age_days: int | None, max_age_days: int) -> bool:
    return age_days is not None and age_days > max_age_days


def has_market_evidence(lead_source: str, market_sources: set[str]) -> bool:
    """Rule 6: a catalogue default or an expert estimate is not market evidence."""
    return lead_source in market_sources


def is_long_lead(effective_weeks: int | None, threshold: int, override: bool | None) -> bool:
    """Derived, never stored (Decision 2); a manual override (with reason) wins either way."""
    if override is not None:
        return override
    return effective_weeks is not None and effective_weeks >= threshold


def order_status(latest: date | None, today: date, ordered: bool, warn_days: int) -> str:
    """Rule 7: ``overdue`` (error), ``due_soon`` (warning) or ``ok``."""
    if ordered or latest is None:
        return "ok"
    if latest < today:
        return "overdue"
    if (latest - today).days <= warn_days:
        return "due_soon"
    return "ok"


# ── route (rule 10) ───────────────────────────────────────────────────────


OWNER_FURNISHED_ROUTES = ("owner_furnished_contractor_installed", "owner_furnished_owner_installed")
PROCUREMENT_ROUTES = ("contractor_furnished_installed", *OWNER_FURNISHED_ROUTES, "owner_procured_novated")


def needs_ofi(route: str | None) -> bool:
    return route in (*OWNER_FURNISHED_ROUTES, "owner_procured_novated")


def route_errors(
    route: str | None,
    package_id: uuid.UUID | None,
    ofi: OwnerFurnishedRef | None,
    plan: PackagePlan | None,
) -> list[str]:
    """Rule 10. Every error is ``route_inconsistent_with_package_plan`` plus a reason suffix."""
    base = "route_inconsistent_with_package_plan"
    if route is None:
        return ["route_missing"]
    if plan is None:
        return ["package_plan_unavailable"]
    pkg = plan.package(package_id)
    if package_id is not None and pkg is None:
        return [f"{base}:package_not_in_plan"]
    if route == "contractor_furnished_installed":
        if pkg is None:
            return [f"{base}:package_required"]
        if not pkg.supplies:
            return [f"{base}:package_does_not_supply"]
        if plan.single_owner_package_id is not None and pkg.id != plan.single_owner_package_id:
            return [f"{base}:single_package_form"]
        return []
    if ofi is None:
        return [f"{base}:owner_furnished_item_required"]
    if route == "owner_furnished_contractor_installed":
        if pkg is None:
            return [f"{base}:package_required"]
        if ofi.installer_package_id != pkg.id:
            return [f"{base}:installer_mismatch"]
        return []
    if route == "owner_furnished_owner_installed":
        if ofi.installer_package_id is not None:
            return [f"{base}:owner_installs"]
        return []
    if route == "owner_procured_novated":
        if pkg is None:
            return [f"{base}:package_required"]
        return []
    return ["unknown_route"]


# ── requirements (rules 8, 15, 17) ────────────────────────────────────────


def redundancy_ok(min_quantity: int | None, quantity: Decimal) -> bool:
    """Rule 17 (warning): N+1 needs at least two units, and so on."""
    return min_quantity is None or quantity >= min_quantity


def vendor_findings(policy: str, reason: str, vendor_id: Any) -> list[str]:
    """Rule 8: ``vendor_bound_needs_reason`` (error), ``neutral_spec_names_vendor`` (warning)."""
    if policy == "bound" and not (reason or "").strip():
        return ["vendor_bound_needs_reason"]
    if policy == "neutral" and vendor_id:
        return ["neutral_spec_names_vendor"]
    return []


def strategic_spares_ok(critical: bool, categories: Iterable[str], no_spare_reason: str) -> bool:
    """Rule 15."""
    return not critical or "strategic_spares" in set(categories) or bool((no_spare_reason or "").strip())


def delivery_limit_gaps(steps: Sequence[str], assigned: Mapping[str, Any]) -> list[str]:
    """Rule 14: catalogue steps without a party, in step order."""
    return [s for s in steps if not assigned.get(s)]


# ── decision paper (rule 9) ───────────────────────────────────────────────


def _dec(value: Any) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("decimal string expected")
    return Decimal(str(value))


def weighted_scores(options: Sequence[Mapping[str, Any]], criteria: Sequence[Mapping[str, Any]]) -> dict[str, Decimal]:
    """Weighted mean score per option code: ``sum(weight * score) / sum(weight)``, Decimal, 4 places."""
    weights = {str(c["code"]): _dec(c.get("weight", "1")) for c in criteria if c.get("code")}
    total = sum(weights.values(), Decimal(0))
    out: dict[str, Decimal] = {}
    for o in options:
        scores = o.get("scores") or {}
        acc = sum((w * _dec(scores.get(code, "0")) for code, w in weights.items()), Decimal(0))
        out[str(o.get("code"))] = (acc / total).quantize(Decimal("0.0001")) if total else Decimal(0)
    return out


def paper_errors(options: Sequence[Mapping[str, Any]], vendor_bound_reason: str) -> list[str]:
    """Rule 9: two options at least, unless the item is vendor bound for ``sole_source``."""
    if len(options) >= 2 or vendor_bound_reason == "sole_source":
        return []
    return ["decision_paper_needs_two_options"]


# ── slot fee and commitment (rule 13) ─────────────────────────────────────


def commitment_errors(ref: CommitmentRef | None, plant_item_id: uuid.UUID, fee: Decimal, currency: str) -> list[str]:
    """Why this commitment does not let a slot fee be bound; empty when it does.

    The commitment must exist in the project, be released, not be planned for
    another plant item, be in the fee's currency and cover the fee.
    """
    if ref is None:
        return ["commitment_not_found"]
    if ref.plant_item_id is not None and ref.plant_item_id != plant_item_id:
        return ["commitment_for_other_item"]
    if not ref.released:
        return ["commitment_not_released"]
    if ref.currency and ref.currency != currency:
        return ["commitment_currency_mismatch"]
    if ref.released_amount is not None and fee > ref.released_amount:
        return ["commitment_release_below_fee"]
    return []


# ── readiness at the gate to execution (SPEC 7) ───────────────────────────


def critical_open(items: Iterable[Mapping[str, Any]]) -> list[str]:
    """Codes of critical items without a set route or without an approved decision paper."""
    return [
        i["code"]
        for i in items
        if i["critical"] and (not at_least(i["status"], "route_set") or i["paper_status"] != "approved")
    ]


def long_lead_open(items: Iterable[Mapping[str, Any]]) -> list[str]:
    """Codes of long-lead items that are not secured.

    Secured means one fresh basis quote AND either ordered or a latest order
    date that has not passed. An item with no latest order date has no float
    to show, so it is open until it is ordered.
    """
    out: list[str] = []
    for i in items:
        if not i["long_lead"]:
            continue
        ordered = is_ordered(i["status"])
        quote_ok = i["basis_count"] == 1 and not i["quote_stale"]
        date_ok = ordered or (i["latest_order_date"] is not None and i["order_status"] != "overdue")
        if not (quote_ok and date_ok):
            out.append(i["code"])
    return out
