# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the HSE frame: which duties apply, and what a topic's state is. No database.

Every answer is ``True``, ``False`` or ``None``. ``None`` means the facts or the
catalogue do not say; no caller reads it as "no duty" and no caller reads it as
"met". A neutral catalogue states no figures, so every duty that rests on a
figure stays ``None`` there until the project (or a tenant catalogue) supplies it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.modules.hse_frame.catalogue import Thresholds
from app.modules.hse_frame.vocab import ITEM_DONE


@dataclass(frozen=True)
class Facts:
    """What the frame knows about the project; ``None`` = not entered yet."""

    duration_working_days: int | None = None
    peak_workers: int | None = None
    person_days: int | None = None
    employers_count: int | None = None
    hazardous_work_codes: tuple[str, ...] = ()
    hazardous_works_assessed: bool = False


@dataclass(frozen=True)
class Duties:
    """Which duties the facts trigger under a catalogue's thresholds."""

    advance_notice: bool | None
    coordinator: bool | None
    plan: bool | None
    later_works_file: bool | None
    hazardous_work: bool | None

    def get(self, trigger: str | None) -> bool | None:
        """The answer for a catalogue trigger name; ``None`` trigger (no condition) is ``True``."""
        if trigger is None or trigger == "always":
            return True
        return {
            "multiple_employers": self.coordinator,
            "plan_required": self.plan,
            "advance_notice": self.advance_notice,
            "hazardous_work": self.hazardous_work,
        }.get(trigger)


def _greater(value: int | None, limit: int | None) -> bool | None:
    return None if value is None or limit is None else value > limit


def _or(*parts: bool | None) -> bool | None:
    """Three-valued OR: any True wins; all False is False; otherwise unknown."""
    if any(p is True for p in parts):
        return True
    return False if all(p is False for p in parts) else None


def _and(*parts: bool | None) -> bool | None:
    if any(p is False for p in parts):
        return False
    return True if all(p is True for p in parts) else None


def duties(facts: Facts, t: Thresholds, known_hazardous: Iterable[str]) -> Duties:
    """Evaluate the duties of one project (the advance notice, the coordinator, the plan, the later-works file)."""
    long_and_big = _and(
        _greater(facts.duration_working_days, t.advance_notice_min_working_days),
        _greater(facts.peak_workers, t.advance_notice_min_workers),
    )
    volume = _greater(facts.person_days, t.advance_notice_person_days)
    advance = _or(long_and_big, volume)
    known = set(known_hazardous)
    selected = [c for c in facts.hazardous_work_codes if c in known]
    hazardous: bool | None = True if selected else (False if facts.hazardous_works_assessed else None)
    coordinator = (
        None
        if facts.employers_count is None or t.coordinator_min_employers is None
        else facts.employers_count >= t.coordinator_min_employers
    )
    later = (
        _and(coordinator, t.later_works_file_with_coordinator)
        if t.later_works_file_with_coordinator
        else (None if t.later_works_file_with_coordinator is None else False)
    )
    return Duties(
        advance_notice=advance,
        coordinator=coordinator,
        plan=_or(advance, hazardous),
        later_works_file=later,
        hazardous_work=hazardous,
    )


def role_in_force(status: str, appointed_on: date | None, ends_on: date | None, today: date) -> bool:
    """An appointed role counts from its day until its end day (the end day itself still counts)."""
    if status != "appointed":
        return False
    if appointed_on is not None and appointed_on > today:
        return False
    return ends_on is None or ends_on >= today


def items_state(statuses: Sequence[tuple[str, str]]) -> str:
    """Readiness state of a topic read from the register: ``(obligation, status)`` of its rows.

    No rows is ``unknown``: an empty register is not a finished one. An open mandatory row is
    ``not_met``; mandatory rows all done with a recommended one open is ``warning``.
    """
    if not statuses:
        return "unknown"
    mandatory = [s for o, s in statuses if o == "mandatory"]
    if any(s not in ITEM_DONE for s in mandatory):
        return "not_met"
    if not mandatory:
        return "unknown"
    return "warning" if any(o != "mandatory" and s not in ITEM_DONE for o, s in statuses) else "met"


def roles_state(required: Sequence[tuple[str, bool | None]], in_force: Iterable[str]) -> str:
    """Readiness of the coordination topic: ``(role code, required?)`` against the roles in force."""
    held = set(in_force)
    missing = [code for code, req in required if req is True and code not in held]
    if missing:
        return "not_met"
    if any(req is None and code not in held for code, req in required):
        return "unknown"
    return "met"


def advance_notice_overdue(
    duties_: Duties, sent_on: date | None, planned_start: date | None, lead_days: int | None, today: date
) -> bool | None:
    """Whether the advance notice should already have gone out (the lead time before the start has begun)."""
    if duties_.advance_notice is not True or sent_on is not None:
        return False if duties_.advance_notice is False or sent_on is not None else None
    if planned_start is None or lead_days is None:
        return None
    return (planned_start - today).days < lead_days
