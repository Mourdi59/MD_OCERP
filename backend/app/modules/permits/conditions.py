# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permit and condition logic without a database: readiness per gate, validity, variation carry-forward.

Rules 9, 10, 11, 12, 14, 17 and 19 of the SPEC. The service builds the views
from rows and calls these functions; the gate evidence provider, the site
mobilisation readiness and the readiness endpoint all read the same results.

Only CONFIRMED conditions count (rule 15): an AI proposal nobody confirmed is
not a condition yet. A ``suspensive`` condition (DE Bedingung, UK
pre-commencement) keeps the permit from taking effect for its trigger; an
``obligation`` (Auflage, compliance condition) does not suspend anything but
raises ``breach_risk`` once overdue (rule 12).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.modules.permits.clock import add_period

# Condition states that still demand something of the project.
OPEN_STATES: tuple[str, ...] = ("open", "evidence_submitted", "discharge_applied", "breach")
DONE_STATES: tuple[str, ...] = ("discharged", "not_triggered", "waived", "superseded", "in_compliance")
HSE_TOPICS: tuple[str, ...] = ("hse", "environment", "noise", "traffic", "ecology", "fire")
TOPICS: tuple[str, ...] = (
    "hse",
    "environment",
    "noise",
    "traffic",
    "heritage",
    "structural",
    "fire",
    "drainage",
    "ecology",
    "design",
    "admin",
    "other",
)
LAPSE_WARNING_DAYS: tuple[int, ...] = (90, 30, 7)
GRANTED_REQ = ("granted",)
PROGRESS_REQ = ("in_progress", "granted", "partially_granted")

# Governance phase codes (both shipped governance catalogues) -> what a permit must enable for that phase.
PHASE_ENABLES: dict[str, tuple[str, ...]] = {
    "construction": ("site_start", "construction"),
    "execution": ("site_start", "construction"),
    "handover": ("occupation",),
    "operation": ("operation",),
}
START_PHASES = ("construction", "execution")
HANDOVER_PHASES = ("handover", "operation")


def text_hash(text: str) -> str:
    """Hash of a condition text with whitespace collapsed: the identity used by rule 14."""
    return hashlib.sha256(re.sub(r"\s+", " ", (text or "").strip()).encode("utf-8")).hexdigest()


def hse_relevant(topic: str, override: bool | None = None) -> bool:
    return override if override is not None else topic in HSE_TOPICS


@dataclass(frozen=True)
class CondView:
    id: str
    number: str
    permit_id: str
    kind: str
    trigger: str
    state: str
    owner_user_id: str | None = None
    confirmed: bool = True
    due_date: date | None = None
    topic: str = "other"
    gate_condition_id: str | None = None
    purpose: str = ""

    @property
    def is_open(self) -> bool:
        return self.confirmed and self.state in OPEN_STATES


@dataclass(frozen=True)
class PermitView:
    id: str
    requirement_id: str
    type_code: str
    category: str
    scope: str
    state: str
    enables: tuple[str, ...] = ()
    scope_activity_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReqView:
    id: str
    type_code: str
    category: str
    scope: str
    enables: tuple[str, ...]
    state: str
    applicable: bool = True
    schedule_conflict: bool = False
    conflict_accepted: bool = False
    conditions_pending: bool = False
    title: str = ""


@dataclass(frozen=True)
class Item:
    code: str
    state: str  # met | not_met | at_risk
    detail: str = ""
    ref: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "state": self.state, "detail": self.detail, "ref": self.ref}


@dataclass
class Readiness:
    gate: str
    status: str = "ready"  # ready | at_risk | not_ready
    items: list[Item] = field(default_factory=list)

    def add(self, item: Item) -> None:
        self.items.append(item)
        if item.state == "not_met":
            self.status = "not_ready"
        elif item.state == "at_risk" and self.status == "ready":
            self.status = "at_risk"

    def as_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "status": self.status, "items": [i.as_dict() for i in self.items]}


def is_overdue(c: CondView, today: date) -> bool:
    return c.is_open and c.due_date is not None and c.due_date < today


def breach_risk(c: CondView, today: date) -> bool:
    """Rule 12: an overdue obligation does not suspend the permit but is a breach risk."""
    return c.kind == "obligation" and is_overdue(c, today)


def _in_force(p: PermitView) -> bool:
    return p.state == "in_force"


def start_readiness(reqs: Sequence[ReqView], permits: Sequence[PermitView], conds: Sequence[CondView]) -> Readiness:
    """Rules 10, 12, 19 (construction gate) and 20 (site mobilisation)."""
    out = Readiness("start")
    live = [p for p in permits if _in_force(p)]
    early = [p for p in live if p.scope == "early_start" and "site_start" in p.enables]
    for r in reqs:
        if not r.applicable or "site_start" not in r.enables or r.scope in ("early_start", "partial"):
            continue
        has_permit = any(p.requirement_id == r.id for p in live)
        if r.state == "granted" and has_permit:
            out.add(Item("permit_granted", "met", r.title or r.type_code, r.id))
        elif r.state == "partially_granted" and has_permit:
            out.add(Item("permit_partial", "at_risk", r.title or r.type_code, r.id))
        elif early:
            # Rule 10: an early start permit is "start at risk", never the full permit.
            out.add(Item("start_at_risk_early_start", "at_risk", r.title or r.type_code, r.id))
        else:
            out.add(Item("permit_missing", "not_met", r.title or r.type_code, r.id))
    live_ids = {p.id for p in live}
    for c in conds:
        if not c.confirmed or c.permit_id not in live_ids or c.trigger != "before_start":
            continue
        if c.kind == "suspensive" and c.is_open:
            out.add(Item("suspensive_condition_open", "not_met", c.number, c.id))
        elif c.kind == "obligation" and c.is_open and not c.gate_condition_id:
            out.add(Item("before_start_obligation_open", "not_met", c.number, c.id))
        elif c.kind == "obligation" and c.is_open:
            out.add(Item("before_start_obligation_accepted_at_gate", "at_risk", c.number, c.id))
    return out


def handover_readiness(reqs: Sequence[ReqView], permits: Sequence[PermitView], conds: Sequence[CondView]) -> Readiness:
    """Rule 19 (handover gate): no open before-occupation condition, occupancy permits granted."""
    out = Readiness("handover")
    live = {p.id for p in permits if _in_force(p)}
    for r in reqs:
        if r.applicable and r.category == "occupancy":
            ok = r.state == "granted"
            out.add(Item("occupancy_permit", "met" if ok else "not_met", r.title or r.type_code, r.id))
    for c in conds:
        if c.confirmed and c.permit_id in live and c.trigger == "before_occupation" and c.is_open:
            out.add(Item("before_occupation_condition_open", "not_met", c.number, c.id))
    return out


def roadmap_readiness(reqs: Sequence[ReqView], next_phase: str | None) -> Readiness:
    """Rule 19, roadmap area: every requirement the next phase needs is filed or granted, no open conflict."""
    out = Readiness("roadmap")
    wanted = set(PHASE_ENABLES.get(next_phase or "", ()))
    for r in reqs:
        if not r.applicable:
            continue
        if wanted & set(r.enables):
            ok = r.state in PROGRESS_REQ
            out.add(Item("requirement_filed", "met" if ok else "not_met", r.title or r.type_code, r.id))
        if r.schedule_conflict and not r.conflict_accepted:
            out.add(Item("schedule_conflict", "not_met", r.title or r.type_code, r.id))
    return out


def register_readiness(reqs: Sequence[ReqView], conds: Sequence[CondView]) -> Readiness:
    """Rule 19, conditions area: register complete, every condition with owner and trigger."""
    out = Readiness("register")
    for r in reqs:
        if r.conditions_pending:
            out.add(Item("conditions_pending", "not_met", r.title or r.type_code, r.id))
    for c in conds:
        if not c.confirmed or c.state not in OPEN_STATES:
            continue
        if not c.owner_user_id:
            out.add(Item("condition_without_owner", "not_met", c.number, c.id))
        if not c.trigger:
            out.add(Item("condition_without_trigger", "not_met", c.number, c.id))
    if not out.items:
        out.add(Item("register_complete", "met"))
    return out


def blocked_activities(
    needing: dict[str, str], partial_scopes: dict[str, Iterable[str]], req_states: dict[str, str]
) -> dict[str, str]:
    """Rule 11: activities that need a requirement granted only in part, outside the granted scope.

    ``needing`` maps activity id -> requirement id; ``partial_scopes`` maps a
    requirement id -> activity ids its partial permit covers.
    """
    out: dict[str, str] = {}
    for activity, rid in needing.items():
        state = req_states.get(rid)
        if state == "granted":
            out[activity] = "permitted"
        elif state == "partially_granted":
            out[activity] = "permitted" if activity in set(partial_scopes.get(rid, ())) else "blocked_by_permit"
        else:
            out[activity] = "blocked_by_permit"
    return out


# ── validity (rule 9) ───────────────────────────────────────────────────────


def valid_until(
    served: date | None, start_notified: date | None, validity: Any, working_day: Any = None
) -> date | None:
    """Lapse date of a permit not yet started; ``None`` once work has started or with no validity data."""
    if validity is None or served is None or start_notified is not None:
        return None
    lapse = getattr(validity, "lapse_if_not_started", None)
    if lapse is None:
        return None
    return add_period(served, lapse.period, lapse.unit, working_day)


def extended_until(current: date, validity: Any) -> date | None:
    """A decided ``extension_of_validity`` moves the lapse date by the catalogue's step."""
    step = getattr(validity, "extension_per_request", None) if validity is not None else None
    return None if step is None else add_period(current, step.period, step.unit)


def lapse_warning(until: date | None, today: date) -> dict[str, Any] | None:
    """``{level, days}`` at 90, 30 and 7 days before the lapse date, ``lapsed`` after it."""
    if until is None:
        return None
    days = (until - today).days
    if days < 0:
        return {"level": "lapsed", "days": days}
    for threshold in sorted(LAPSE_WARNING_DAYS):
        if days <= threshold:
            return {"level": f"d{threshold}", "days": days}
    return None


# ── variation carry-forward (rule 14) ───────────────────────────────────────


@dataclass(frozen=True)
class OldCondition:
    id: str
    number: str
    text: str
    kind: str
    trigger: str
    state: str


@dataclass(frozen=True)
class NewCondition:
    number: str
    text: str
    kind: str
    trigger: str


@dataclass(frozen=True)
class Carried:
    number: str
    text: str
    kind: str
    trigger: str
    original_id: str | None
    keep_state: str | None  # the state carried over, or None = reopened (``open``)


def carry_forward(
    old: Sequence[OldCondition], replaced: Sequence[NewCondition], removed_numbers: Iterable[str] = ()
) -> list[Carried]:
    """The conditions of the varied permit.

    Every live old condition is superseded by the caller. Those the variation
    replaces (same number) take the new text; those it removes vanish; the rest
    are copied forward. A copy or replacement whose text hash equals the old one
    keeps a discharged / in-compliance state with its evidence; otherwise it reopens.
    """
    by_number = {n.number: n for n in replaced}
    removed = set(removed_numbers)
    out: list[Carried] = []
    for o in old:
        if o.state == "superseded" or o.number in removed:
            continue
        new = by_number.pop(o.number, None)
        text = new.text if new else o.text
        same = text_hash(text) == text_hash(o.text)
        keep = o.state if same and o.state in ("discharged", "in_compliance", "not_triggered") else None
        out.append(
            Carried(
                o.number,
                text,
                new.kind if new else o.kind,
                new.trigger if new else o.trigger,
                o.id,
                keep,
            )
        )
    for n in by_number.values():
        out.append(Carried(n.number, n.text, n.kind, n.trigger, None, None))
    return out


def escalation_due(due: date, today: date, escalation_days: int) -> bool:
    """Rule 17: escalate to the area owner after the project's escalation days."""
    return today > due + timedelta(days=escalation_days)
