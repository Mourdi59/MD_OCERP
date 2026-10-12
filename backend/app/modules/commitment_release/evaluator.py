# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the matrix: which tier a release needs, and by when it must be decided.

No database, no I/O. The service gathers the inputs (cumulative releases in the
schedule currency, the item's flags, the linked activity's dates) and these
functions answer. Every rule here has a table test in
``tests/unit/test_commitment_evaluator.py``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.modules.commitment_release.catalogue import ANY_TYPE, AuthoritySchedule, parse_amount

ESCALATE_OUTSIDE = "escalate_outside"


@dataclass(frozen=True)
class TierResult:
    """The authority a release needs.

    Attributes:
        tier_code: The required tier, or ``None`` when the amount is above every
            band (``escalate_outside``: consent outside the schedule).
        escalate_outside: True when no band covers the amount.
        evaluated_amount: The amount the bands were read against.
        band_code: The band that matched, if any.
        raised_by: Novelty flag codes that raised the tier above the band's.
    """

    tier_code: str | None
    escalate_outside: bool
    evaluated_amount: Decimal
    band_code: str | None = None
    raised_by: tuple[str, ...] = ()


def schedule_in_force(schedules: Iterable[AuthoritySchedule], on_date: date) -> AuthoritySchedule | None:
    """The version whose effective window covers ``on_date``; latest version wins a tie."""
    covering = [
        s
        for s in schedules
        if (s.effective_from is None or s.effective_from <= on_date)
        and (s.effective_to is None or on_date <= s.effective_to)
    ]
    return max(covering, key=lambda s: s.version) if covering else None


def in_force(schedule: AuthoritySchedule, on_date: date) -> bool:
    """Whether ``on_date`` lies inside the schedule's own validity window (open on a side without a date)."""
    return schedule_in_force([schedule], on_date) is not None


def evaluated_amount(
    *,
    request: Decimal,
    released_on_item: Decimal,
    released_on_group_others: Decimal,
    aggregation: str,
) -> Decimal:
    """The amount a release is judged on.

    ``item_total`` (default): everything already released on the item plus this
    request, and for an item in a ``split_group`` everything released on the
    other items of the group too (anti-splitting). ``request_only``: the
    request alone, plus the group's other releases when the item is grouped.
    """
    if request <= 0:
        raise ValueError("a release request must be positive")
    if aggregation == "request_only":
        return request + released_on_group_others
    return released_on_item + released_on_group_others + request


def _bands_for(schedule: AuthoritySchedule, commitment_type: str) -> list:
    own = [b for b in schedule.bands if b.commitment_type == commitment_type]
    if own:
        return own
    return [b for b in schedule.bands if b.commitment_type == ANY_TYPE]


def required_tier(
    schedule: AuthoritySchedule,
    commitment_type: str,
    amount: Decimal,
    flags: Iterable[str] = (),
) -> TierResult:
    """The lowest sufficient tier for ``amount``, raised by novelty flags.

    Bands of the item's own type win over ``*`` bands. The required tier is the
    lowest whose ``max_amount`` is at least the amount (``null`` = open). A
    novelty flag that names the type or one of ``flags`` sets a minimum tier.
    Above every band the result is ``escalate_outside`` and no tier decides.

    Raises:
        ValueError: The type is not in the schedule.
    """
    if commitment_type not in schedule.type_codes():
        raise ValueError(f"commitment type {commitment_type!r} is not in schedule {schedule.id!r}")
    order = schedule.tier_order()
    bands = sorted(_bands_for(schedule, commitment_type), key=lambda b: order[b.tier])
    match = None
    for b in bands:
        if b.max_amount is None or parse_amount(b.max_amount) >= amount:
            match = b
            break
    if match is None:
        return TierResult(None, True, amount)
    tier = match.tier
    active = set(flags) | {commitment_type}
    raised: list[str] = []
    for f in schedule.novelty_flags:
        if f.code in active and order[f.min_tier] > order[tier]:
            raised.append(f.code)
    for f in schedule.novelty_flags:
        if f.code in raised and order[f.min_tier] > order[tier]:
            tier = f.min_tier
    return TierResult(tier, False, amount, match.code, tuple(sorted(raised)))


def lowest_tier_ceiling(schedule: AuthoritySchedule, commitment_type: str) -> Decimal:
    """The largest amount of ``commitment_type`` the schedule's lowest tier may still approve (SPEC rule 20).

    This is what replaces a module's own fixed "high value" constant for a project
    with a schedule: an amount above it needs more than the lowest tier. ``0`` when
    a novelty flag on the type lifts even the smallest amount above the lowest tier;
    ``Decimal("Infinity")`` when the lowest tier's band is open.

    Raises:
        ValueError: The type is not in the schedule.
    """
    lowest = schedule.tiers[0].code if schedule.tiers else None
    if required_tier(schedule, commitment_type, Decimal("0")).tier_code != lowest:
        return Decimal("0")
    order = schedule.tier_order()
    for b in sorted(_bands_for(schedule, commitment_type), key=lambda b: order[b.tier]):
        if b.tier == lowest:
            return Decimal("Infinity") if b.max_amount is None else parse_amount(b.max_amount)
    return Decimal("0")


def tolerance_ceiling(released: Decimal, absolute: Decimal, percent: Decimal) -> Decimal:
    """What a linked amount may reach before the release must be renewed: the larger allowance wins."""
    return released + max(absolute, released * percent)


@dataclass(frozen=True)
class DecisionDate:
    """``latest`` decision date and which input it was computed from.

    ``basis``: ``late_start`` (CPM ran), ``start_date`` (no CPM, planned start used),
    ``fixed`` (entered on the item) or ``none`` (nothing to compute from).
    """

    latest: date | None
    basis: str
    need_date: date | None = None


def _day(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def latest_decision_date(
    *,
    late_start: object = None,
    start_date: object = None,
    fixed: object = None,
    lead_time_days: int | None = None,
    decision_buffer_days: int | None = None,
) -> DecisionDate:
    """Last responsible moment: need date minus lead time minus decision buffer.

    The need date is the linked activity's ``late_start``; without a CPM run it
    is the activity's ``start_date``. A date fixed on the item is used only when
    no activity date is known.
    """
    lead = timedelta(days=max(lead_time_days or 0, 0) + max(decision_buffer_days or 0, 0))
    for basis, raw in (("late_start", late_start), ("start_date", start_date)):
        need = _day(raw)
        if need is not None:
            return DecisionDate(need - lead, basis, need)
    fixed_day = _day(fixed)
    if fixed_day is not None:
        return DecisionDate(fixed_day, "fixed", None)
    return DecisionDate(None, "none", None)


RELEASED_STATES = frozenset({"released", "committed", "closed", "re_release_required"})


def decision_overdue(latest: date | None, today: date, status: str, released_amount: Decimal) -> bool:
    """Past the latest decision date with nothing released (a flag, never a state)."""
    if latest is None or today <= latest:
        return False
    if status in ("aborted", "transferred", "closed", "on_hold"):
        return False
    return released_amount <= 0 and status not in RELEASED_STATES


def release_in_force(released: Decimal, expired: Decimal, committed: Decimal) -> Decimal:
    """How much of an item's released money still authorises a commitment.

    ``expired`` is the part of ``released`` whose ``valid_until`` has passed. It keeps covering
    what is committed today, so nothing already bound loses its release, and it authorises nothing
    beyond that: the uncommitted rest of an expired release is gone until a new release is decided.
    Committed money is set against the expired part first, which is the reading that takes the
    least away from a release still in date.
    """
    if expired <= 0:
        return released
    kept = min(expired, committed) if committed > 0 else Decimal("0")
    return released - expired + kept
