# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Communication plan recurrence: an RFC 5545 RRULE subset evaluated on dates (SPEC rules 6 and 7).

Supported parts: ``FREQ`` (DAILY, WEEKLY, MONTHLY, YEARLY), ``INTERVAL``,
``COUNT``, ``UNTIL`` (a date), ``BYDAY`` (``MO`` or, monthly, ``1MO`` / ``-1FR``),
``BYMONTHDAY`` (``-1`` is the last day of the month) and ``BYMONTH``. Anything
else is refused, so a rule the screen cannot show is never stored.

Occurrences are dates, not instants: a plan says "every first Monday", and a
daylight saving change cannot move a date. Nothing is pre-generated: the next
occurrence is computed from the start date and the newest occurrence already
recorded (decision f).
"""

from __future__ import annotations

from datetime import date, datetime, time

from dateutil.rrule import rrulestr

ONCE = "once"
_FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
_PARTS = ("FREQ", "INTERVAL", "COUNT", "UNTIL", "BYDAY", "BYMONTHDAY", "BYMONTH")
# A plan item that recurs more than this many times before ``today`` is a typo, not a plan.
_SCAN_LIMIT = 5000


class RecurrenceError(ValueError):
    """A frequency string outside the supported subset."""


def _parse_parts(rule: str) -> dict[str, str]:
    body = rule.strip()
    if body.upper().startswith("RRULE:"):
        body = body[6:]
    parts: dict[str, str] = {}
    for chunk in body.split(";"):
        if not chunk.strip():
            continue
        if "=" not in chunk:
            raise RecurrenceError(f"malformed part {chunk!r}")
        key, value = chunk.split("=", 1)
        key = key.strip().upper()
        if key not in _PARTS:
            raise RecurrenceError(f"unsupported part {key}")
        if key in parts:
            raise RecurrenceError(f"duplicate part {key}")
        parts[key] = value.strip().upper()
    if parts.get("FREQ") not in _FREQS:
        raise RecurrenceError("FREQ must be DAILY, WEEKLY, MONTHLY or YEARLY")
    if "COUNT" in parts and "UNTIL" in parts:
        raise RecurrenceError("COUNT and UNTIL are exclusive")
    if "UNTIL" in parts and ("T" in parts["UNTIL"] or len(parts["UNTIL"]) != 8):
        raise RecurrenceError("UNTIL must be a date YYYYMMDD")
    _check_bounds(parts)
    return parts


_MONTH_DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _ints(parts: dict[str, str], key: str, lo: int, hi: int) -> list[int]:
    out: list[int] = []
    for raw in parts[key].split(","):
        try:
            value = int(raw)
        except ValueError as exc:
            raise RecurrenceError(f"{key} must be whole numbers") from exc
        if not lo <= abs(value) <= hi or (value < 0 and key in ("INTERVAL", "COUNT", "BYMONTH")):
            raise RecurrenceError(f"{key} out of range")
        out.append(value)
    return out


def _check_bounds(parts: dict[str, str]) -> None:
    """Refuse a rule that never advances or never occurs.

    dateutil accepts ``INTERVAL=0`` and then yields the start date forever, and
    it scans to year 9999 for a rule with no occurrence (30 February, the
    sixth Monday of a month). Either would block the worker on the first read.
    """
    if "INTERVAL" in parts:
        _ints(parts, "INTERVAL", 1, 1000)
    if "COUNT" in parts:
        _ints(parts, "COUNT", 1, _SCAN_LIMIT)
    months = _ints(parts, "BYMONTH", 1, 12) if "BYMONTH" in parts else list(range(1, 13))
    if "BYMONTHDAY" in parts:
        days = _ints(parts, "BYMONTHDAY", 1, 31)
        if not any(abs(d) <= _MONTH_DAYS[m - 1] for d in days for m in months):
            raise RecurrenceError("BYMONTHDAY never occurs in BYMONTH")
    if "BYDAY" in parts:
        for raw in parts["BYDAY"].split(","):
            ordinal, day = raw[:-2], raw[-2:]
            if day not in ("MO", "TU", "WE", "TH", "FR", "SA", "SU"):
                raise RecurrenceError("BYDAY must name weekdays")
            if ordinal:
                try:
                    n = int(ordinal)
                except ValueError as exc:
                    raise RecurrenceError("BYDAY ordinal must be a whole number") from exc
                if not 1 <= abs(n) <= 5 or parts["FREQ"] not in ("MONTHLY", "YEARLY"):
                    raise RecurrenceError("BYDAY ordinal out of range")


def normalise(frequency: str | None) -> str:
    """``once`` or a validated ``FREQ=...`` string (canonical upper case, no ``RRULE:`` prefix)."""
    if frequency is None or not frequency.strip() or frequency.strip().lower() == ONCE:
        return ONCE
    parts = _parse_parts(frequency)
    out = ";".join(f"{k}={parts[k]}" for k in _PARTS if k in parts)
    try:
        rrulestr(out, dtstart=datetime(2026, 1, 1))
    except (ValueError, TypeError) as exc:
        raise RecurrenceError(str(exc)) from exc
    return out


def next_occurrence(frequency: str, starts_on: date, after: date | None, ends_on: date | None = None) -> date | None:
    """First occurrence strictly after ``after`` (or the first one at all), within ``ends_on``.

    ``once`` occurs on ``starts_on`` only.
    """
    freq = normalise(frequency)
    if freq == ONCE:
        due = starts_on if after is None or starts_on > after else None
    else:
        rule = rrulestr(freq, dtstart=datetime.combine(starts_on, time()))
        if after is None:
            first = rule.after(datetime.combine(starts_on, time()), inc=True)
        else:
            first = rule.after(datetime.combine(after, time()), inc=False)
        due = first.date() if first is not None else None
    if due is not None and ends_on is not None and due > ends_on:
        return None
    return due


def occurrences_between(frequency: str, starts_on: date, start: date, end: date) -> list[date]:
    """Occurrences in ``[start, end]`` (the communication calendar), never more than the scan limit."""
    freq = normalise(frequency)
    if freq == ONCE:
        return [starts_on] if start <= starts_on <= end else []
    rule = rrulestr(freq, dtstart=datetime.combine(starts_on, time()))
    out: list[date] = []
    for dt in rule.xafter(datetime.combine(start, time()), inc=True):
        if dt.date() > end or len(out) >= _SCAN_LIMIT:
            break
        out.append(dt.date())
    return out


def occurrence_for(
    *,
    frequency: str | None,
    trigger_kind: str | None,
    starts_on: date | None,
    held_on: date,
    next_due: date | None,
    done: list[date],
) -> date:
    """Which occurrence an event held on ``held_on`` belongs to when the caller names none (rule 7).

    The pending occurrence when it has come due, or when nothing is recorded
    yet (an early first meeting). Otherwise the latest scheduled occurrence on
    or before the day it was held: a follow-up to a meeting already recorded
    counts towards that meeting and does not consume the next one.
    """
    if next_due is not None and (next_due <= held_on or not done):
        return next_due
    if trigger_kind or starts_on is None:
        return max(done) if done else held_on
    freq = normalise(frequency)
    if freq == ONCE:
        return starts_on
    previous = rrulestr(freq, dtstart=datetime.combine(starts_on, time())).before(
        datetime.combine(held_on, time()), inc=True
    )
    return previous.date() if previous is not None else (max(done) if done else held_on)


def next_due(
    *,
    frequency: str | None,
    trigger_kind: str | None,
    starts_on: date | None,
    ends_on: date | None,
    done: list[date],
    triggered_on: date | None = None,
) -> date | None:
    """The plan item's next due date (rule 6), advanced by recorded occurrences (rule 7).

    A trigger item is due on the date its trigger fired and not before; once an
    occurrence on or after that date is recorded it waits for the next trigger.
    A scheduled item is due at the first occurrence after the newest recorded
    one; two events for one occurrence leave it where one would.
    """
    newest = max(done) if done else None
    if trigger_kind:
        if triggered_on is None or (newest is not None and newest >= triggered_on):
            return None
        return triggered_on
    if starts_on is None:
        return None
    return next_occurrence(frequency or ONCE, starts_on, newest, ends_on)
