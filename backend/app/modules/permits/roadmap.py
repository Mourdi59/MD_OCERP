# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Roadmap arithmetic: dependency graph, derived requirement state and timeline (rules 3, 6). Pure.

``Dependency`` edges point from a requirement to the one it waits for, typed
``granted`` (the other must be decided in our favour first) or ``submitted``
(it must at least be filed). The timeline walks the graph backwards from each
requirement's needed-by date: a prerequisite typed ``granted`` must be decided
by the time its dependant has to be filed, one typed ``submitted`` must be
filed no later than its dependant.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

GRANTED_OUTCOMES = ("granted", "granted_with_conditions", "deemed_granted")
REQUIREMENT_STATES = (
    "not_started",
    "in_progress",
    "granted",
    "partially_granted",
    "refused",
    "not_applicable",
    "blocked",
)
SUBMITTED_STATES = ("submitted", "validated", "under_review", "info_requested", "decided")


@dataclass(frozen=True)
class Edge:
    requirement: str
    depends_on: str
    on: str = "granted"


def find_cycle(edges: Iterable[Edge]) -> list[str] | None:
    """A cycle in the dependency graph as a list of nodes, or ``None``."""
    graph: dict[str, list[str]] = {}
    for e in edges:
        graph.setdefault(e.requirement, []).append(e.depends_on)
    white, grey, black = 0, 1, 2
    color: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        color[n] = grey
        stack.append(n)
        for m in graph.get(n, ()):
            c = color.get(m, white)
            if c == grey:
                return stack[stack.index(m) :] + [m]
            if c == white and (found := visit(m)) is not None:
                return found
        stack.pop()
        color[n] = black
        return None

    for node in list(graph):
        if color.get(node, white) == white and (found := visit(node)) is not None:
            return found
    return None


@dataclass(frozen=True)
class AttemptView:
    """The newest application of a requirement (``kind`` ``new`` only) and its current decision outcome."""

    state: str
    outcome: str | None = None


def derive_state(applicable: bool, latest: AttemptView | None, deps_met: bool) -> str:
    """Derived requirement state (never stored, SPEC section 3)."""
    if not applicable:
        return "not_applicable"
    if latest is not None:
        if latest.state == "decided" and latest.outcome:
            if latest.outcome in GRANTED_OUTCOMES:
                return "granted"
            if latest.outcome == "partially_granted":
                return "partially_granted"
            if latest.outcome == "refused":
                return "refused"
            if latest.outcome == "withdrawn":
                return "not_started" if deps_met else "blocked"
        if latest.state == "withdrawn":
            return "not_started" if deps_met else "blocked"
        if latest.state in SUBMITTED_STATES:
            return "in_progress"
        if latest.state in ("preparing", "internal_review") and deps_met:
            return "in_progress"
    return "not_started" if deps_met else "blocked"


def unmet_dependencies(
    requirement_id: str, edges: Sequence[Edge], states: Mapping[str, str], submitted: Mapping[str, bool]
) -> list[str]:
    """Prerequisites of one requirement that do not satisfy their edge yet (rule 3)."""
    out = []
    for e in edges:
        if e.requirement != requirement_id:
            continue
        state = states.get(e.depends_on, "not_started")
        if state == "not_applicable":
            continue
        ok = state == "granted" if e.on == "granted" else (submitted.get(e.depends_on, False) or state == "granted")
        if not ok:
            out.append(e.depends_on)
    return out


@dataclass(frozen=True)
class TimelineInput:
    id: str
    needed_by: date | None
    date_basis: str | None
    duration_days: int | None
    buffer_days: int = 0
    forecast: date | None = None
    forecast_reason: str | None = None
    planned_submit: date | None = None
    conflict_accepted: bool = False


@dataclass
class TimelineRow:
    id: str
    needed_by: date | None
    date_basis: str | None
    latest_decision: date | None
    latest_submit: date | None
    forecast: date | None
    forecast_reason: str | None
    schedule_conflict: bool = False
    conflict_days: int = 0
    conflict_accepted: bool = False
    derived_from: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        def iso(d: date | None) -> str | None:
            return d.isoformat() if d else None

        return {
            "requirement_id": self.id,
            "needed_by": iso(self.needed_by),
            "date_basis": self.date_basis,
            "latest_decision": iso(self.latest_decision),
            "latest_submit": iso(self.latest_submit),
            "forecast_decision": iso(self.forecast),
            "forecast_reason": self.forecast_reason,
            "schedule_conflict": self.schedule_conflict,
            "conflict_days": self.conflict_days,
            "conflict_accepted": self.conflict_accepted,
            "derived_from": self.derived_from,
        }


def needed_by(activity: Mapping[str, Any] | None, fixed: date | None) -> tuple[date | None, str | None]:
    """Rule 6: the linked activity's late start, else early start, else constraint date, else the fixed date."""
    if activity:
        for name in ("late_start", "early_start", "constraint_date"):
            value = _iso(activity.get(name))
            if value is not None:
                return value, name
    if fixed is not None:
        return fixed, "fixed_date"
    return None, None


def _iso(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def timeline(rows: Sequence[TimelineInput], edges: Sequence[Edge]) -> list[TimelineRow]:
    """Latest decision and submit dates through the dependency chain, forecasts and conflicts (rule 6).

    Assumes an acyclic graph (cycles are refused at write). Dependants are
    resolved before their prerequisites, so a prerequisite inherits the
    tightest date any dependant imposes.
    """
    by_id = {r.id: r for r in rows}
    out = {r.id: TimelineRow(r.id, r.needed_by, r.date_basis, None, None, r.forecast, r.forecast_reason) for r in rows}
    for r in rows:
        out[r.id].conflict_accepted = r.conflict_accepted
    dependants: dict[str, list[Edge]] = {}
    for e in edges:
        if e.requirement in by_id and e.depends_on in by_id:
            dependants.setdefault(e.depends_on, []).append(e)
    done: set[str] = set()

    def resolve(rid: str) -> None:
        if rid in done:
            return
        done.add(rid)
        row, spec = out[rid], by_id[rid]
        for e in dependants.get(rid, ()):
            resolve(e.requirement)
            child = out[e.requirement]
            if child.latest_submit is None:
                continue
            if e.on == "granted":
                if row.needed_by is None or child.latest_submit < row.needed_by:
                    row.needed_by, row.date_basis = child.latest_submit, "dependency"
                    row.derived_from = [e.requirement]
            else:
                bound = child.latest_submit
                if row.latest_submit is None or bound < row.latest_submit:
                    row.latest_submit = bound
                    row.derived_from = [e.requirement]
        if row.needed_by is not None:
            row.latest_decision = row.needed_by - timedelta(days=spec.buffer_days)
            if spec.duration_days is not None:
                own = row.latest_decision - timedelta(days=spec.duration_days)
                row.latest_submit = own if row.latest_submit is None else min(row.latest_submit, own)
        if row.forecast is None and spec.planned_submit is not None and spec.duration_days is not None:
            row.forecast = spec.planned_submit + timedelta(days=spec.duration_days)
            row.forecast_reason = row.forecast_reason or "planned_submit"
        if row.forecast is not None and row.latest_decision is not None and row.forecast > row.latest_decision:
            row.schedule_conflict = True
            row.conflict_days = (row.forecast - row.latest_decision).days

    for r in rows:
        resolve(r.id)
    return [out[r.id] for r in rows]
