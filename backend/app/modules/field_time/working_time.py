# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""Statutory working-time records: the regimes, and the dates they produce.

Some countries oblige an employer to record the start, the end and the duration
of each worker's daily working time, to have that record in existence within a
few days of the work, and to keep it for a fixed number of years. Germany does
it for the construction sector through the minimum wage act: the record has to
exist no later than seven days after the day worked, and it has to be kept for
at least two years. A main contractor is answerable for its subcontractors'
minimum wage, which is why the record names the employer of every worker on the
site and not only the main contractor's own staff.

A timesheet carries no regime until somebody chooses one, and a timesheet with
no regime is not late, has no retention window and is displayed exactly as it
was before this module existed. Most of the platform's users work under no such
obligation and must never be asked to answer for one.

What this module is *not*: it does not decide how long a shift was. That is
:func:`app.modules.field_time.field_time_math.worked_hours`, which derives the
duration from the start time, the end time and the unpaid break for every
timesheet line that carries them, regime or no regime. A duration that could
disagree with the times that produced it would be worthless to an auditor, so
there is only ever one of them, and it is derived.

Pure by construction: no I/O, no ORM, no FastAPI, so every date rule here is
unit-testable without a database, like the rest of the field-time engine.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.modules.field_time.field_time_math import to_decimal

# Who employs the worker on a line. The main contractor is liable for the
# minimum wage its subcontractors pay, so "whose worker is this" is part of the
# record and not a detail of the payroll run. NULL / absent means nobody stated
# it, which is a visible gap in an audit export rather than an implied "ours".
EMPLOYER_OWN = "own"
EMPLOYER_SUBCONTRACTOR = "subcontractor"
ALL_EMPLOYER_KINDS: tuple[str, ...] = (EMPLOYER_OWN, EMPLOYER_SUBCONTRACTOR)


@dataclass(frozen=True)
class WorkingTimeRegimeSpec:
    """One statutory working-time recording regime.

    Attributes:
        code: The stored code, e.g. ``"milog"``.
        label: English name, the fallback the UI shows when a locale has no
            translation for the code.
        provision: The provision the duties come from, for the audit export
            header so a reader can check the rule rather than trust us.
        record_within_days: How many days after the day worked the record must
            exist. A record made later is still a record; it is late.
        retention_years: How many years the record has to be kept for, counted
            from the day the record was due.
        summary: One English sentence on what the regime obliges, shown to
            whoever is choosing a regime.
    """

    code: str
    label: str
    provision: str
    record_within_days: int
    retention_years: int
    summary: str


WORKING_TIME_REGIMES: tuple[WorkingTimeRegimeSpec, ...] = (
    WorkingTimeRegimeSpec(
        code="milog",
        label="Germany, minimum wage act working-time record",
        provision="MiLoG § 17 (1)",
        record_within_days=7,
        retention_years=2,
        summary=(
            "Record the start, the end and the duration of every worker's daily working time "
            "within seven days of the day worked, and keep the record for at least two years. "
            "It covers the main contractor's own staff and its subcontractors' workers alike, "
            "because the main contractor answers for the minimum wage they are paid."
        ),
    ),
)

# Canonical ordered tuple of the shipped codes, so the schemas, the router and
# the tests all read the vocabulary from one place.
ALL_WORKING_TIME_REGIMES: tuple[str, ...] = tuple(spec.code for spec in WORKING_TIME_REGIMES)

_BY_CODE: dict[str, WorkingTimeRegimeSpec] = {spec.code: spec for spec in WORKING_TIME_REGIMES}


def regime_for(code: str | None) -> WorkingTimeRegimeSpec | None:
    """The regime with this code, or ``None``.

    ``None`` in means no regime was chosen, which is the state every timesheet
    starts in. An unknown code also answers ``None``: a stored value this build
    does not know is treated as no regime rather than as a guess at which one
    was meant.

    Args:
        code: The stored regime code, or ``None``.

    Returns:
        The matching :class:`WorkingTimeRegimeSpec`, or ``None``.
    """
    if not code:
        return None
    return _BY_CODE.get(str(code).strip().lower())


def _add_years(day: date, years: int) -> date:
    """``day`` shifted by whole years, clamping 29 February to 28 February."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, month=2, day=28)


@dataclass(frozen=True)
class RecordTimeliness:
    """Whether one day's record was in existence in time, and for how long it lives.

    Attributes:
        deadline: The last day the record could have been made on.
        days_taken: Days between the day worked and the day the record was made.
            Negative when the record was made before the day it covers.
        late: True when the record was made after ``deadline``.
        retain_until: The last day the record has to be kept, a floor rather
            than an expiry. Nothing is ever deleted on the strength of it.
    """

    deadline: date
    days_taken: int
    late: bool
    retain_until: date


def record_deadline(work_date: date, spec: WorkingTimeRegimeSpec) -> date:
    """The last day a record of ``work_date`` could be made on without being late."""
    return work_date + timedelta(days=spec.record_within_days)


def retain_until(work_date: date, spec: WorkingTimeRegimeSpec) -> date:
    """The last day a record of ``work_date`` has to be kept.

    Counted from the day the record was due (the day worked plus the recording
    window), not from the day worked, because that is the point the duty
    attaches to. The statute says "at least", so the later of two defensible
    anchors can only over-retain, and this module never deletes anything on the
    strength of the answer - it only says what falls inside the window.
    """
    return _add_years(record_deadline(work_date, spec), spec.retention_years)


def timeliness(
    work_date: date,
    recorded_at: datetime | date | None,
    spec: WorkingTimeRegimeSpec,
) -> RecordTimeliness | None:
    """Judge one day's record against its regime.

    The day the record was made is the calendar date of ``recorded_at`` in the
    timezone that value carries; a timesheet stamps it in UTC. A record made on
    the deadline itself is on time - the duty is to have it within the window,
    not before it.

    Args:
        work_date: The day the work was performed.
        recorded_at: When the record came into existence, or None when that is
            not known (nothing can be judged, so the answer is None).
        spec: The regime to judge against.

    Returns:
        A :class:`RecordTimeliness`, or ``None`` when there is nothing to judge.
    """
    if recorded_at is None:
        return None
    made_on = recorded_at.date() if isinstance(recorded_at, datetime) else recorded_at
    if not isinstance(made_on, date):
        return None
    deadline = record_deadline(work_date, spec)
    return RecordTimeliness(
        deadline=deadline,
        days_taken=(made_on - work_date).days,
        late=made_on > deadline,
        retain_until=retain_until(work_date, spec),
    )


def within_retention(work_date: date, spec: WorkingTimeRegimeSpec, today: date) -> bool:
    """True while a record of ``work_date`` still has to be kept on ``today``."""
    return today <= retain_until(work_date, spec)


# ── The worker-day, which is the unit an auditor asks for ────────────────────


@dataclass(frozen=True)
class WorkerDayRecord:
    """One worker's working time on one day, as the record keeps it.

    A worker can be booked several times in a day - one segment per cost code -
    so the day is the sum of its segments: the earliest start, the latest end,
    the total unpaid break and the total duration. ``segments_without_times``
    counts the bookings that carry hours but no clock times, which is the gap
    an audit would find, so it is reported rather than hidden.

    Attributes:
        work_date: The day worked.
        resource_id: The worker, as the string id the lines carry.
        employer_kind: One of :data:`ALL_EMPLOYER_KINDS`, or "" when nobody
            stated who employs this worker.
        employer_id: The subcontractor id when the employer is one, else None.
        started_at: Earliest start across the day's segments, or None.
        ended_at: Latest end across the day's segments, or None.
        break_minutes: Total unpaid break across the segments.
        duration_hours: Total hours booked for the day.
        segments: How many bookings make up the day.
        segments_without_times: How many of them carry no start and end.
        references: The timesheet references the day is made of, sorted.
        status: The shared status of those timesheets, or "mixed".
        recorded_at: The latest of their creation instants - the point the day's
            record was complete, which is what the deadline applies to.
    """

    work_date: date
    resource_id: str
    employer_kind: str
    employer_id: str | None
    started_at: datetime | None
    ended_at: datetime | None
    break_minutes: int
    duration_hours: Decimal
    segments: int
    segments_without_times: int
    references: tuple[str, ...]
    status: str
    recorded_at: datetime | None


def _clean(value: object) -> str:
    """A stripped string for any scalar, empty for None."""
    return "" if value is None else str(value).strip()


def _as_int(value: object) -> int:
    """A non-negative int for any scalar, 0 when it cannot be read."""
    try:
        parsed = int(to_decimal(value))
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def worker_day_records(entries: Sequence[Mapping[str, Any]]) -> list[WorkerDayRecord]:
    """Fold timesheet lines into the worker-days an audit export is made of.

    Only labour is included: a statutory working-time record is about people,
    and a machine has no working time to record. Lines are grouped by day,
    worker and employer, so two lines that disagree about who employs a worker
    surface as two rows instead of one of them being picked silently.

    Args:
        entries: Mappings with ``work_date``, ``resource_id``, ``employer_kind``,
            ``employer_subcontractor_id``, ``started_at``, ``ended_at``,
            ``break_minutes``, ``hours``, ``reference``, ``status`` and
            ``recorded_at``.

    Returns:
        Worker-days sorted by day, then worker, then employer.
    """
    grouped: dict[tuple[date, str, str, str], list[Mapping[str, Any]]] = {}
    for entry in entries:
        worker = _clean(entry.get("resource_id"))
        work_date = entry.get("work_date")
        if not worker or not isinstance(work_date, date):
            continue
        kind = _clean(entry.get("employer_kind")).lower()
        if kind not in ALL_EMPLOYER_KINDS:
            kind = ""
        employer_id = _clean(entry.get("employer_subcontractor_id"))
        grouped.setdefault((work_date, worker, kind, employer_id), []).append(entry)

    records: list[WorkerDayRecord] = []
    for (work_date, worker, kind, employer_id), lines in grouped.items():
        starts = [line.get("started_at") for line in lines if isinstance(line.get("started_at"), datetime)]
        ends = [line.get("ended_at") for line in lines if isinstance(line.get("ended_at"), datetime)]
        # Comparing an aware instant with a naive one raises rather than sorts,
        # so fall back to "no bound stated" when a day mixes the two.
        started = _extreme(starts, latest=False)
        ended = _extreme(ends, latest=True)
        without_times = sum(
            1
            for line in lines
            if not isinstance(line.get("started_at"), datetime) or not isinstance(line.get("ended_at"), datetime)
        )
        statuses = {_clean(line.get("status")) for line in lines}
        stamps = [line.get("recorded_at") for line in lines if isinstance(line.get("recorded_at"), datetime)]
        records.append(
            WorkerDayRecord(
                work_date=work_date,
                resource_id=worker,
                employer_kind=kind,
                employer_id=employer_id or None,
                started_at=started,
                ended_at=ended,
                break_minutes=sum(_as_int(line.get("break_minutes")) for line in lines),
                duration_hours=sum(
                    (to_decimal(line.get("hours")) for line in lines),
                    Decimal("0"),
                ),
                segments=len(lines),
                segments_without_times=without_times,
                references=tuple(sorted({_clean(line.get("reference")) for line in lines} - {""})),
                status=statuses.pop() if len(statuses) == 1 else "mixed",
                recorded_at=_extreme(stamps, latest=True),
            ),
        )

    records.sort(key=lambda r: (r.work_date, r.resource_id, r.employer_kind, r.employer_id or ""))
    return records


def _extreme(stamps: Sequence[object], *, latest: bool) -> datetime | None:
    """The earliest or latest of some instants, or None when they cannot be compared."""
    usable = [s for s in stamps if isinstance(s, datetime)]
    if not usable:
        return None
    aware = [s for s in usable if s.tzinfo is not None]
    if aware and len(aware) != len(usable):
        return None
    return max(usable) if latest else min(usable)


__all__ = [
    "ALL_EMPLOYER_KINDS",
    "ALL_WORKING_TIME_REGIMES",
    "EMPLOYER_OWN",
    "EMPLOYER_SUBCONTRACTOR",
    "WORKING_TIME_REGIMES",
    "RecordTimeliness",
    "WorkerDayRecord",
    "WorkingTimeRegimeSpec",
    "record_deadline",
    "regime_for",
    "retain_until",
    "timeliness",
    "within_retention",
    "worker_day_records",
]
