# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Certified payroll arithmetic, framework-free.

No database, no FastAPI, no third-party dependency, so every function here runs
the same in a unit test as in the request path. The service layer keeps the
session work and the HTTP errors; this file is the arithmetic a report, an
export, a background job or a test can reuse without booting anything.

Three things live here and nothing else:

* the week: which seven days a week-ending date covers, and how per-day payroll
  entries pivot into one row per worker per classification;
* the package comparison: which of several determinations governs when more
  than one regime covers the same work, and why;
* the pay split: basic and fringe kept apart, with the overtime multiplier
  applied to the basic rate alone.

The pay arithmetic itself is not reimplemented. It is
:mod:`app.modules.payroll.intl`, which already owns Decimal-exact regular and
overtime pay for the whole platform and now takes an explicit basic rate. Two
implementations of the same money would be two answers to the same question.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.modules.payroll.intl import (
    DEFAULT_MONEY_QUANTUM,
    DEFAULT_OVERTIME_MULTIPLIER,
    gross_pay,
    parse_iso_date,
    quantize_money,
    resolve_overtime_base,
    split_regular_overtime,
    to_decimal,
)

# Days in a payroll week. Seven, and the form prints seven columns.
DAYS_IN_PAYROLL_WEEK = 7


def week_days(week_ending: object) -> list[str]:
    """Return the seven ISO dates of the week ending on ``week_ending``.

    Ordered earliest first, so index 0 is six days before the week-ending date
    and index 6 is the week-ending date itself. The form prints the days in
    this order and the derived rows key their hours on these exact strings, so
    a reader never has to guess which day a column meant.

    Args:
        week_ending: The last day of the payroll week, ISO ``YYYY-MM-DD`` or a
            ``date``.

    Returns:
        Seven ISO date strings.

    Raises:
        ValueError: If ``week_ending`` is missing or not an ISO date.
    """
    end = parse_iso_date(week_ending, "week_ending")
    start = end - timedelta(days=DAYS_IN_PAYROLL_WEEK - 1)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(DAYS_IN_PAYROLL_WEEK)]


def is_in_week(work_date: object, week_ending: object) -> bool:
    """Return True when ``work_date`` falls inside the week ending on ``week_ending``.

    A missing or unparseable work date is not in any week and returns False
    rather than raising, because a payroll entry with no date is a data gap the
    validation rules report; it is not a reason to fail the whole pivot.
    """
    if work_date is None:
        return False
    try:
        day = parse_iso_date(work_date, "work_date")
        end = parse_iso_date(week_ending, "week_ending")
    except ValueError:
        return False
    return end - timedelta(days=DAYS_IN_PAYROLL_WEEK - 1) <= day <= end


def total_package(basic_rate: object, fringe_rate: object) -> Decimal:
    """Return the total hourly package = basic rate plus fringe rate.

    This is the figure two determinations are compared on when both cover the
    same work. It exists as a function rather than as a stored column precisely
    so that no table ever holds a blended rate that has lost the split.

    Raises:
        ValueError: If either figure is missing, non-numeric or negative.
    """
    basic = to_decimal(basic_rate, "basic_rate")
    fringe = to_decimal(fringe_rate, "fringe_rate")
    if basic < 0:
        raise ValueError(f"basic_rate must not be negative, got {basic}.")
    if fringe < 0:
        raise ValueError(f"fringe_rate must not be negative, got {fringe}.")
    return basic + fringe


def governing_classification(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Pick which determination governs, and say why in words.

    Where a job is covered by more than one regime, the obligations are
    cumulative rather than alternative: a federal determination does not satisfy
    a state one and a state determination does not satisfy the federal one. The
    contractor owes the higher of them, so the higher total package governs.

    The comparison is on the total package (basic plus fringe), which is
    ordinary practice and matches what the California regional pack already
    records about the higher rate governing where the two differ. It is an
    assumption this function states rather than hides: the reason string names
    the figures compared, so a reader can disagree with the choice on the
    evidence rather than having to reverse-engineer it.

    Args:
        candidates: Dicts each carrying at least ``authority``,
            ``basic_hourly_rate`` and ``fringe_rate``, and optionally
            ``determination_identifier`` and ``classification_title``.

    Returns:
        ``(winner, reason)``. With no candidates the winner is ``None`` and the
        reason says so. With one candidate that one governs and the reason names
        it as the only regime on file. Ties resolve to the first candidate and
        the reason records that the packages were equal.
    """
    if not candidates:
        return None, "No wage determination on file for this classification, so no rate could be established."

    priced: list[tuple[Decimal, dict[str, Any]]] = []
    for candidate in candidates:
        package = total_package(
            candidate.get("basic_hourly_rate", "0"),
            candidate.get("fringe_rate", "0"),
        )
        priced.append((package, candidate))

    if len(priced) == 1:
        package, only = priced[0]
        return only, (
            f"Only the {_authority_words(only.get('authority'))} determination "
            f"{_identifies(only)} covers this work, at a total package of {package} per hour."
        )

    best_package, best = max(priced, key=lambda pair: pair[0])
    tied = [pair for pair in priced if pair[0] == best_package]
    compared = ", ".join(
        f"{_authority_words(item.get('authority'))} {_identifies(item)} at {package}" for package, item in priced
    )
    if len(tied) > 1:
        return tied[0][1], (
            f"Two or more determinations set the same total package of {best_package} per hour "
            f"({compared}). The {_authority_words(tied[0][1].get('authority'))} determination is "
            "recorded as the governing one; the obligations are equal in amount, not discharged by each other."
        )
    return best, (
        f"The {_authority_words(best.get('authority'))} determination {_identifies(best)} governs at a "
        f"total package of {best_package} per hour, being the highest of the determinations covering this "
        f"work ({compared}). A determination under one regime does not satisfy the obligation under another, "
        "so the higher rate is owed."
    )


def _authority_words(authority: object) -> str:
    """Render an authority code as the word a reader expects in a sentence."""
    text = str(authority or "").strip().lower()
    if text == "awarding_body":
        return "awarding body"
    return text or "unattributed"


def _identifies(candidate: dict[str, Any]) -> str:
    """Render a determination identifier for a reason sentence, or a neutral phrase."""
    identifier = str(candidate.get("determination_identifier") or "").strip()
    return identifier or "on file"


def split_week_hours(
    hours_by_day: dict[str, Any],
    *,
    daily_overtime_threshold: object | None = None,
    weekly_overtime_threshold: object | None = None,
) -> tuple[dict[str, dict[str, str]], Decimal, Decimal]:
    """Split a week's per-day hours into straight and overtime hours.

    Two thresholds, because jurisdictions differ and some apply both. A daily
    threshold makes the hours beyond it on any single day overtime; a weekly
    threshold makes the hours beyond it across the week overtime. When both are
    given the daily split runs first and the weekly threshold is then applied to
    the straight hours that survived it, so an hour is never counted as overtime
    twice. When neither is given every hour is straight, which is the neutral
    default the platform's payroll arithmetic already uses: no working-time rule
    is assumed on anybody's behalf.

    Args:
        hours_by_day: ISO date string -> hours worked that day.
        daily_overtime_threshold: Hours per day after which work is overtime.
        weekly_overtime_threshold: Hours per week after which work is overtime.

    Returns:
        ``(per_day, straight_total, overtime_total)`` where ``per_day`` maps
        each ISO date to ``{"straight": ..., "overtime": ...}`` as strings.

    Raises:
        ValueError: If any hours figure is negative or not a number.
    """
    per_day: dict[str, dict[str, Decimal]] = {}
    for day in sorted(hours_by_day):
        worked = to_decimal(hours_by_day[day], f"hours_by_day[{day}]")
        if worked < 0:
            raise ValueError(f"hours_by_day[{day}] must not be negative, got {worked}.")
        straight, overtime = split_regular_overtime(worked, daily_overtime_threshold)
        per_day[day] = {"straight": straight, "overtime": overtime}

    if weekly_overtime_threshold is not None:
        remaining = to_decimal(weekly_overtime_threshold, "weekly_overtime_threshold")
        if remaining < 0:
            raise ValueError(f"weekly_overtime_threshold must not be negative, got {remaining}.")
        for day in sorted(per_day):
            straight = per_day[day]["straight"]
            allowed = min(straight, remaining)
            per_day[day]["straight"] = allowed
            per_day[day]["overtime"] += straight - allowed
            remaining -= allowed

    straight_total = sum((values["straight"] for values in per_day.values()), Decimal("0"))
    overtime_total = sum((values["overtime"] for values in per_day.values()), Decimal("0"))
    rendered = {
        day: {"straight": _plain(values["straight"]), "overtime": _plain(values["overtime"])}
        for day, values in per_day.items()
    }
    return rendered, straight_total, overtime_total


def _plain(value: Decimal) -> str:
    """Render a Decimal without exponent notation and without trailing noise."""
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def line_pay(
    straight_hours: object,
    overtime_hours: object,
    paid_basic_rate: object,
    paid_fringe_rate: object,
    *,
    overtime_multiplier: object = DEFAULT_OVERTIME_MULTIPLIER,
    quantum: Decimal = DEFAULT_MONEY_QUANTUM,
) -> dict[str, str]:
    """Compute one worker-week's gross pay from a basic rate and a fringe rate.

    The whole point of this function is the base the multiplier is applied to.
    The hourly rate paid is ``basic + fringe``, and every straight hour earns
    that. An overtime hour earns ``basic x multiplier + fringe``: the premium
    attaches to the basic wage only, and the fringe is paid at its face value on
    the overtime hour just as on a straight one. Applying the multiplier to
    ``basic + fringe`` overstates the fringe and is the error this module exists
    to make unrepresentable.

    Returns a dict of Decimal-as-string figures: ``paid_rate``,
    ``overtime_base_rate``, ``straight_pay``, ``overtime_pay``, ``gross_amount``
    and the ``overtime_multiplier`` used.

    Raises:
        ValueError: If any figure is negative, non-numeric or non-finite.
    """
    basic = to_decimal(paid_basic_rate, "paid_basic_rate")
    fringe = to_decimal(paid_fringe_rate, "paid_fringe_rate")
    if basic < 0:
        raise ValueError(f"paid_basic_rate must not be negative, got {basic}.")
    if fringe < 0:
        raise ValueError(f"paid_fringe_rate must not be negative, got {fringe}.")
    paid_rate = basic + fringe

    straight = to_decimal(straight_hours, "straight_hours")
    overtime = to_decimal(overtime_hours, "overtime_hours")
    multiplier = to_decimal(overtime_multiplier, "overtime_multiplier")

    # Delegated to the platform's payroll arithmetic so there is one
    # implementation of overtime money, with the basic rate stated explicitly.
    gross = gross_pay(straight, overtime, paid_rate, multiplier, basic_rate=basic, quantum=quantum)
    straight_pay = quantize_money(straight * paid_rate, quantum)
    base, flat = resolve_overtime_base(paid_rate, basic)
    ot_pay = quantize_money(overtime * ((base * multiplier) + flat), quantum)

    return {
        "paid_rate": _plain(paid_rate),
        "overtime_base_rate": _plain(base),
        "overtime_multiplier": _plain(multiplier),
        "straight_pay": str(straight_pay),
        "overtime_pay": str(ot_pay),
        "gross_amount": str(gross),
    }


def underpaid_by(
    paid_basic_rate: object,
    paid_fringe_rate: object,
    required_basic_rate: object,
    required_fringe_rate: object,
) -> Decimal:
    """Return how far a paid package falls below a required one, per hour.

    Zero when the package paid meets or exceeds the package required. The
    comparison is on the total package, so a contractor discharging more of the
    rate as fringe and less as basic wage is not reported as underpaying, which
    is a lawful arrangement. A shortfall in the basic rate alone is a separate
    question the validation rules ask separately, because the overtime base
    depends on the basic rate and a low basic rate underpays overtime even when
    the package is whole.
    """
    paid = total_package(paid_basic_rate, paid_fringe_rate)
    required = total_package(required_basic_rate, required_fringe_rate)
    shortfall = required - paid
    return shortfall if shortfall > 0 else Decimal("0")


def week_ending_for(work_date: object, week_ends_on: int = 6) -> str:
    """Return the ISO week-ending date of the week containing ``work_date``.

    ``week_ends_on`` is a weekday index in Python's convention (Monday 0 through
    Sunday 6), defaulting to Sunday, which is the commonest construction payroll
    week. It is a parameter and not a constant because the payroll week is set
    by the contractor's own practice, not by this platform.

    Raises:
        ValueError: If ``work_date`` is missing or not an ISO date, or if
            ``week_ends_on`` is outside 0-6.
    """
    if not isinstance(week_ends_on, int) or not 0 <= week_ends_on <= 6:
        raise ValueError(f"week_ends_on must be a weekday index from 0 (Monday) to 6 (Sunday), got {week_ends_on!r}.")
    day: date = parse_iso_date(work_date, "work_date")
    ahead = (week_ends_on - day.weekday()) % DAYS_IN_PAYROLL_WEEK
    return (day + timedelta(days=ahead)).isoformat()


__all__ = [
    "DAYS_IN_PAYROLL_WEEK",
    "governing_classification",
    "is_in_week",
    "line_pay",
    "split_week_hours",
    "total_package",
    "underpaid_by",
    "week_days",
    "week_ending_for",
]
