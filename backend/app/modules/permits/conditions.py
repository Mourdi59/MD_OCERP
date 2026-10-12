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
GRANTED_REQ = ("granted", "partially_granted")
# Condition states a variation carries over when the text is unchanged (rule 14).
KEPT_IF_SAME_TEXT: tuple[str, ...] = ("discharged", "in_compliance", "not_triggered", "waived", "evidence_submitted")
# Carried whatever the new text says: a breach never closes itself (rule 16) and a pending
# discharge application keeps naming the condition it was filed for.
KEPT_ALWAYS: tuple[str, ...] = ("breach", "discharge_applied")


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
    # Type codes the permit's own type lists under ``requires``: what an early start runs ahead of.
    requires: tuple[str, ...] = ()


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
    # The newest application is with the authority (filed, not yet decided).
    submitted: bool = False
    # The date the roadmap says the permit must be in hand.
    needed_by: date | None = None


@dataclass(frozen=True)
class Item:
    code: str
    # ``warning`` is said and never blocks: it does not change the status of the check.
    state: str  # met | not_met | at_risk | warning
    detail: str = ""
    ref: str | None = None
    # A permit needed later: what it is and the day, apart from the sentence, for the screen to format.
    title: str | None = None
    needed_by: date | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "state": self.state, "detail": self.detail, "ref": self.ref}
        if self.needed_by is not None:
            out["title"] = self.title
            out["needed_by"] = self.needed_by.isoformat()
        return out


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


def start_readiness(
    reqs: Sequence[ReqView],
    permits: Sequence[PermitView],
    conds: Sequence[CondView],
    needed_from: date | None = None,
) -> Readiness:
    """Rules 10, 12, 19 (construction gate) and 20 (site mobilisation).

    ``needed_from`` is the date the check is made for: the target date of the gate being read.
    A permit not yet granted blocks when the roadmap needs it on or before that date, and
    also when the roadmap gives it no date at all, because an undated permit cannot be shown
    to be needed later. One the roadmap needs after that date is a ``warning`` that names
    the date: said, never silent, and not a blocker. Without ``needed_from`` (the site is to
    start now) every missing permit blocks.
    """
    out = Readiness("start")
    live = [p for p in permits if _in_force(p)]
    early = [p for p in live if p.scope == "early_start" and "site_start" in p.enables]
    for r in reqs:
        if not r.applicable or "site_start" not in r.enables or r.scope in ("early_start", "partial"):
            continue
        has_permit = any(p.requirement_id == r.id for p in live)
        # Rule 10: an early start runs ahead of the one permit its type names, and only while the
        # authority has not refused that permit. It is "start at risk", never the full permit.
        ahead = r.state != "refused" and any(r.type_code in p.requires for p in early)
        if r.state == "granted" and has_permit:
            out.add(Item("permit_granted", "met", r.title or r.type_code, r.id))
        elif r.state == "partially_granted" and has_permit:
            out.add(Item("permit_partial", "at_risk", r.title or r.type_code, r.id))
        elif ahead:
            out.add(Item("start_at_risk_early_start", "at_risk", r.title or r.type_code, r.id))
        elif needed_from is not None and r.needed_by is not None and r.needed_by > needed_from:
            name = r.title or r.type_code
            out.add(Item("permit_due_later", "warning", f"{name} {r.needed_by.isoformat()}", r.id, name, r.needed_by))
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


def roadmap_readiness(reqs: Sequence[ReqView], enables: Iterable[str]) -> Readiness:
    """Rule 19, roadmap area: every requirement the next phase needs is filed or granted, no open conflict.

    ``enables`` is what the next phase needs a permit for (``site_start``, ``occupation``, ...); the
    caller resolves it from the phase tags of the governance catalogue. A requirement still being
    prepared is not filed.
    """
    out = Readiness("roadmap")
    wanted = set(enables)
    for r in reqs:
        if not r.applicable:
            continue
        if wanted & set(r.enables):
            ok = r.state in GRANTED_REQ or (r.state == "in_progress" and r.submitted)
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


def paused_until(paused_since: date, validity: Any, working_day: Any = None) -> date | None:
    """Lapse date of a started permit whose work stopped on ``paused_since``; ``None`` without such a period."""
    lapse = getattr(validity, "lapse_if_paused", None) if validity is not None else None
    if lapse is None:
        return None
    return add_period(paused_since, lapse.period, lapse.unit, working_day)


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
    # An AI proposal nobody confirmed stays a proposal on the varied permit (rule 15).
    confirmed: bool = True


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
    confirmed: bool = True
    replaced: bool = False  # the variation itself states this number


def carry_forward(
    old: Sequence[OldCondition], replaced: Sequence[NewCondition], removed_numbers: Iterable[str] = ()
) -> list[Carried]:
    """The conditions of the varied permit.

    Every live old condition is superseded by the caller. Those the variation
    replaces (same number) take the new text; those it removes vanish; the rest
    are copied forward. A copy or replacement whose text hash equals the old one
    keeps its closed state (discharged, in compliance, not triggered, waived) or
    its submitted evidence; otherwise it reopens. A breach and a pending discharge
    application are carried whatever the text says. An unconfirmed proposal stays
    unconfirmed unless the variation itself states the condition.
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
        keep = o.state if o.state in KEPT_ALWAYS or (same and o.state in KEPT_IF_SAME_TEXT) else None
        out.append(
            Carried(
                o.number,
                text,
                new.kind if new else o.kind,
                new.trigger if new else o.trigger,
                o.id,
                keep,
                confirmed=True if new else o.confirmed,
                replaced=new is not None,
            )
        )
    for n in by_number.values():
        out.append(Carried(n.number, n.text, n.kind, n.trigger, None, None, replaced=True))
    return out


def escalation_due(due: date, today: date, escalation_days: int) -> bool:
    """Rule 17: escalate to the area owner after the project's escalation days."""
    return today > due + timedelta(days=escalation_days)
