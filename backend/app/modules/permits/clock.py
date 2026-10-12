# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Statutory decision clocks (SPEC rules 4, 5, 7). Pure: no ORM, no I/O.

A clock is catalogue data: a period in a unit, the event it starts from, whether
a request for information stops it, and how it may be extended. This module
turns that data plus an application's dates and clock events into a forecast
decision date. Dates are calendar dates: an authority's period runs in days of
the authority's calendar, and the platform stores no project time zone, so the
date the user records is the date that counts.

Counting conventions (one per ``start_event``):

* ``receipt`` and ``complete``: the period runs from the day of the event, the
  event day not counted; it ends on the day that corresponds by number
  (7 months from 15 March ends 15 October; from 31 January, one month ends on
  the last day of February).
* ``day_after_receipt``: "a period of N weeks beginning with the day after
  receipt" (DMPO 2015 art. 34): the first counted day is receipt + 1 and the
  last is receipt + 1 + period - 1 day.

Stopped days (``stop_on_rfi``) and extensions are added after the base period,
in the order they were recorded. Working days use the calendar the caller
passes (the project's schedule calendar); this module never assumes a week.
"""

from __future__ import annotations

import calendar
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

WorkingDay = Callable[[date], bool]
UNITS = ("calendar_days", "working_days", "weeks", "months", "years")
EVENT_KINDS = ("stop", "resume", "extension_agreed", "extension_by_authority")


class ClockError(ValueError):
    """A clock event the catalogue does not allow. ``code`` is the API error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ClockSpec:
    """The parts of a catalogue clock this module reads."""

    period: int | None
    unit: str | None
    start_event: str = "receipt"
    stop_on_rfi: bool = False
    extension_mode: str = "none"
    extension_max: int | None = None
    extension_unit: str | None = None
    extension_reason_required: bool = False
    deemed_outcome: str = "none"
    deemed_requires_notice: bool = False

    @classmethod
    def from_catalogue(cls, clock: Any, variant: str | None = None) -> ClockSpec:
        """Build from a catalogue ``Clock`` (or a dict of the same shape); a variant overrides the period."""
        c = clock.model_dump() if hasattr(clock, "model_dump") else dict(clock or {})
        ext = c.get("extension") or {}
        period, unit = c.get("period"), c.get("unit")
        if variant:
            match = next((v for v in c.get("variants") or () if v.get("code") == variant), None)
            if match is None:
                raise ClockError("unknown_clock_variant")
            period, unit = match["period"], match["unit"]
        return cls(
            period=period,
            unit=unit,
            start_event=c.get("start_event") or "receipt",
            stop_on_rfi=bool(c.get("stop_on_rfi")),
            extension_mode=ext.get("mode") or "none",
            extension_max=ext.get("max"),
            extension_unit=ext.get("unit"),
            extension_reason_required=bool(ext.get("reason_required")),
            deemed_outcome=c.get("deemed_outcome") or "none",
            deemed_requires_notice=bool(c.get("deemed_requires_notice")),
        )


@dataclass(frozen=True)
class ClockEvent:
    kind: str
    at: date
    period: int | None = None
    unit: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class ClockResult:
    """The forecast and how it was reached. ``forecast`` is ``None`` with a ``reason`` when unknown."""

    start: date | None
    base_due: date | None
    forecast: date | None
    reason: str | None = None
    stopped_days: int = 0
    stopped_now: bool = False
    extensions: tuple[tuple[int, str, str], ...] = ()
    estimate: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat() if self.start else None,
            "base_due": self.base_due.isoformat() if self.base_due else None,
            "forecast": self.forecast.isoformat() if self.forecast else None,
            "reason": self.reason,
            "stopped_days": self.stopped_days,
            "stopped_now": self.stopped_now,
            "extensions": [{"period": p, "unit": u, "kind": k} for p, u, k in self.extensions],
            "estimate": self.estimate,
        }


def _weekday(d: date) -> bool:
    raise ClockError("working_day_calendar_missing")


def add_period(start: date, period: int, unit: str, working_day: WorkingDay | None = None) -> date:
    """``start`` plus ``period`` ``unit``; months and years clamp to the month's last day."""
    if unit == "calendar_days":
        return start + timedelta(days=period)
    if unit == "weeks":
        return start + timedelta(weeks=period)
    if unit in ("months", "years"):
        months = period * (12 if unit == "years" else 1)
        y, m = divmod(start.month - 1 + months, 12)
        year, month = start.year + y, m + 1
        return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
    if unit == "working_days":
        is_working = working_day or _weekday
        current, added = start, 0
        while added < period:
            current += timedelta(days=1)
            if is_working(current):
                added += 1
        return current
    raise ClockError("unknown_clock_unit")


def subtract_days(d: date, days: int) -> date:
    return d - timedelta(days=days)


def check_extension(spec: ClockSpec, existing: Sequence[ClockEvent], new: ClockEvent) -> None:
    """Refuse an extension the catalogue does not allow (rule 4). Raises :class:`ClockError`."""
    if new.kind not in ("extension_agreed", "extension_by_authority"):
        return
    if new.period is None or new.period < 1 or new.unit not in UNITS:
        raise ClockError("extension_period_required")
    if new.kind == "extension_agreed":
        if spec.extension_mode != "by_agreement":
            raise ClockError("extension_not_allowed")
        return
    if spec.extension_mode != "by_authority_once":
        raise ClockError("extension_not_allowed")
    if any(e.kind == "extension_by_authority" for e in existing):
        raise ClockError("extension_already_used")
    if spec.extension_reason_required and not (new.reason or "").strip():
        raise ClockError("extension_reason_required")
    if new.unit != spec.extension_unit:
        raise ClockError("extension_unit_mismatch")
    if spec.extension_max is not None and new.period > spec.extension_max:
        raise ClockError("extension_exceeds_max")


def check_stop(spec: ClockSpec, existing: Sequence[ClockEvent], new: ClockEvent) -> None:
    """A stop needs a running clock, a resume needs a stopped one."""
    if new.kind not in ("stop", "resume"):
        return
    stopped = _is_stopped(existing)
    if new.kind == "stop" and stopped:
        raise ClockError("clock_already_stopped")
    if new.kind == "resume" and not stopped:
        raise ClockError("clock_not_stopped")


def _is_stopped(events: Iterable[ClockEvent]) -> bool:
    state = False
    for e in sorted(events, key=lambda e: e.at):
        if e.kind == "stop":
            state = True
        elif e.kind == "resume":
            state = False
    return state


def start_date(spec: ClockSpec, *, received_at: date | None, validated_at: date | None) -> date | None:
    """The day the period counts from, per ``start_event``; ``None`` while the event has not happened."""
    if spec.start_event == "complete":
        return validated_at
    return received_at


def forecast(
    spec: ClockSpec,
    *,
    received_at: date | None,
    validated_at: date | None = None,
    events: Sequence[ClockEvent] = (),
    today: date | None = None,
    working_day: WorkingDay | None = None,
    expected_date: date | None = None,
) -> ClockResult:
    """Forecast decision date of one application (rules 4 and 5)."""
    if spec.period is None or spec.unit is None:
        if expected_date is not None:
            return ClockResult(None, None, expected_date, reason="no_statutory_period", estimate=True)
        return ClockResult(None, None, None, reason="no_statutory_period")
    start = start_date(spec, received_at=received_at, validated_at=validated_at)
    if start is None:
        return ClockResult(None, None, None, reason="clock_not_started")
    if spec.start_event == "day_after_receipt":
        base = add_period(start + timedelta(days=1), spec.period, spec.unit, working_day) - timedelta(days=1)
    else:
        base = add_period(start, spec.period, spec.unit, working_day)
    due = base
    ordered = sorted(events, key=lambda e: e.at)
    stopped_days = 0
    stopped_now = False
    if spec.stop_on_rfi:
        open_stop: date | None = None
        for e in ordered:
            if e.kind == "stop" and open_stop is None:
                open_stop = e.at
            elif e.kind == "resume" and open_stop is not None:
                stopped_days += max((e.at - open_stop).days, 0)
                open_stop = None
        if open_stop is not None:
            stopped_now = True
            stopped_days += max(((today or open_stop) - open_stop).days, 0)
        due += timedelta(days=stopped_days)
    extensions: list[tuple[int, str, str]] = []
    for e in ordered:
        if e.kind in ("extension_agreed", "extension_by_authority") and e.period and e.unit:
            due = add_period(due, e.period, e.unit, working_day)
            extensions.append((e.period, e.unit, e.kind))
    return ClockResult(
        start,
        base,
        due,
        stopped_days=stopped_days,
        stopped_now=stopped_now,
        extensions=tuple(extensions),
    )


def duration_days(spec: ClockSpec, submit: date, working_day: WorkingDay | None = None) -> int | None:
    """Days from a submission on ``submit`` (taken as receipt and completeness) to the base decision date."""
    result = forecast(spec, received_at=submit, validated_at=submit, working_day=working_day)
    return None if result.forecast is None else (result.forecast - submit).days


def deemed_proposal(spec: ClockSpec, result: ClockResult, *, today: date, decided: bool) -> str | None:
    """The deemed outcome to PROPOSE when the clock has run out undecided (rule 7); never applied here."""
    if decided or spec.deemed_outcome == "none" or result.forecast is None or result.estimate:
        return None
    if result.stopped_now or today <= result.forecast:
        return None
    return "deemed_granted" if spec.deemed_outcome == "granted" else "deemed_discharged"
