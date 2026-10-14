# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The engineering brief rules as pure functions. No session, no I/O.

The service builds plain dicts from its rows and calls these; the validation rule set calls the same
functions on the same payload, so every check has one implementation and every unit test drives it
without a database.

Shapes (dates are :class:`datetime.date`, quantities :class:`~decimal.Decimal`):

* requirement: ``{id, category, priority, verification_method, originator, source_ref}``
* concept item: ``{id, code, topic_code, decision, requirement_ids}``
* programme line: ``{id, code, kind_code, unit, quantity}``
* milestone: ``{id, code, kind_code, planned_date, lead_days, successor_id, gate_code,
  permit_requirement_id, activity_id}``
* gate: ``{code, order, status, target_date}`` as the governance port reports it
* activity: ``{start_date, end_date}`` of the schedule activity a milestone was published as
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

ERROR = "error"
WARNING = "warning"
ZERO = Decimal("0")
MUST = "must"
# The states of a permit roadmap requirement in which its decision has been taken.
PERMIT_DECIDED = frozenset({"granted", "partially_granted", "refused", "withdrawn"})


@dataclass(frozen=True)
class Finding:
    """One rule finding: a stable code (also the message key), the element it is about, a severity."""

    code: str
    ref: str
    severity: str = ERROR
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "ref": self.ref, "severity": self.severity, "detail": self.detail}


def dec(value: Any) -> Decimal | None:
    """An exact decimal from a string, int or Decimal; ``None`` for anything else, floats included."""
    if isinstance(value, bool | float) or value is None:
        return None
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return out if out.is_finite() else None


# ── requirements ───────────────────────────────────────────────────────────


def requirement_findings(catalogue: Any, requirements: list[Mapping[str, Any]]) -> list[Finding]:
    """The brief has requirements, covers the categories the catalogue asks for, and each can be verified."""
    out: list[Finding] = []
    if not requirements:
        out.append(Finding("no_requirements", "requirements"))
    covered = {r.get("category") for r in requirements}
    for cat in catalogue.requirement_categories:
        if cat.required and cat.code not in covered:
            out.append(Finding("category_uncovered", cat.code))
    known = {c.code for c in catalogue.requirement_categories}
    for r in requirements:
        ref = str(r["id"])
        if r.get("category") not in known:
            out.append(Finding("requirement_category_unknown", ref, WARNING, str(r.get("category") or "")))
        if r.get("priority") == MUST and not r.get("verification_method"):
            out.append(Finding("requirement_unverifiable", ref, WARNING))
        if not r.get("originator") and not r.get("source_ref"):
            out.append(Finding("requirement_without_origin", ref, WARNING))
    return out


# ── technical concept ──────────────────────────────────────────────────────


def concept_findings(
    catalogue: Any, concepts: list[Mapping[str, Any]], requirements: list[Mapping[str, Any]]
) -> list[Finding]:
    """Every required topic is decided, references resolve, and every must requirement is answered."""
    out: list[Finding] = []
    by_topic: dict[str, list[Mapping[str, Any]]] = {}
    for c in concepts:
        by_topic.setdefault(str(c["topic_code"]), []).append(c)
        if catalogue.topic(c["topic_code"]) is None:
            out.append(Finding("concept_topic_unknown", str(c["id"]), detail=str(c["topic_code"])))
    for topic in catalogue.concept_topics:
        if not topic.required:
            continue
        items = by_topic.get(topic.code, [])
        if not items:
            out.append(Finding("topic_missing", topic.code))
        elif not any(str(i.get("decision") or "").strip() for i in items):
            out.append(Finding("topic_undecided", topic.code))
    ids = {str(r["id"]) for r in requirements}
    answered: set[str] = set()
    for c in concepts:
        for rid in c.get("requirement_ids") or []:
            if str(rid) in ids:
                answered.add(str(rid))
            else:
                out.append(Finding("concept_requirement_missing", str(c["id"]), detail=str(rid)))
    for r in requirements:
        if r.get("priority") == MUST and str(r["id"]) not in answered:
            out.append(Finding("requirement_unanswered", str(r["id"]), WARNING))
    return out


# ── programme ──────────────────────────────────────────────────────────────


def programme_findings(catalogue: Any, lines: list[Mapping[str, Any]]) -> list[Finding]:
    """The programme has lines, each of a known kind with a unit and a positive quantity."""
    out: list[Finding] = []
    if not lines:
        out.append(Finding("programme_missing", "programme"))
    for ln in lines:
        ref = str(ln["id"])
        if catalogue.programme_kind(ln["kind_code"]) is None:
            out.append(Finding("programme_kind_unknown", ref, detail=str(ln["kind_code"])))
        if not str(ln.get("unit") or "").strip():
            out.append(Finding("programme_unit_missing", ref))
        qty = dec(ln.get("quantity"))
        if qty is None or qty <= ZERO:
            out.append(Finding("programme_quantity_invalid", ref))
    return out


# ── framework schedule ─────────────────────────────────────────────────────


def _day(value: Any) -> date | None:
    return value if isinstance(value, date) else None


def chain_cycles(milestones: Iterable[Mapping[str, Any]]) -> set[str]:
    """Ids of milestones whose successor chain leads back to themselves."""
    succ = {str(m["id"]): (str(m["successor_id"]) if m.get("successor_id") else None) for m in milestones}
    bad: set[str] = set()
    for start in succ:
        seen: set[str] = set()
        cur: str | None = start
        while cur is not None and cur in succ:
            if cur in seen:
                bad.add(start)
                break
            seen.add(cur)
            cur = succ[cur]
    return bad


def schedule_findings(
    catalogue: Any,
    milestones: list[Mapping[str, Any]],
    gates: list[Mapping[str, Any]],
    *,
    operation_proof_date: date | None,
    permit_states: Mapping[str, str | None] | None = None,
    activities: Mapping[str, Mapping[str, Any] | None] | None = None,
) -> list[Finding]:
    """Anchor, backward consistency, and the binding of the milestones to the project's gates."""
    out: list[Finding] = []
    permit_states = permit_states or {}
    activities = activities or {}
    by_id = {str(m["id"]): m for m in milestones}
    anchor_kind, gate_kind = catalogue.anchor_kind, catalogue.gate_kind
    anchors = [m for m in milestones if m["kind_code"] == anchor_kind]

    if operation_proof_date is None:
        out.append(Finding("operation_proof_missing", "operation_proof_date"))
    if not anchors:
        out.append(Finding("anchor_milestone_missing", "milestones"))
    for a in anchors:
        d = _day(a.get("planned_date"))
        if operation_proof_date is not None and d is not None and d != operation_proof_date:
            out.append(Finding("anchor_date_differs", str(a["id"]), detail=d.isoformat()))
    cyclic = chain_cycles(milestones)

    for m in milestones:
        ref = str(m["id"])
        if catalogue.milestone_kind(m["kind_code"]) is None:
            out.append(Finding("milestone_kind_unknown", ref, detail=str(m["kind_code"])))
        d = _day(m.get("planned_date"))
        if d is None:
            out.append(Finding("milestone_date_missing", ref))
        if ref in cyclic:
            out.append(Finding("successor_cycle", ref))
            continue
        succ_id = str(m["successor_id"]) if m.get("successor_id") else None
        if succ_id is not None and succ_id not in by_id:
            out.append(Finding("successor_unknown", ref))
        elif succ_id is None and m["kind_code"] not in (anchor_kind, gate_kind):
            out.append(Finding("milestone_unchained", ref, WARNING))
        if succ_id in by_id and d is not None:
            sd = _day(by_id[succ_id].get("planned_date"))
            lead = int(m.get("lead_days") or 0)
            if sd is not None and d > sd - timedelta(days=lead):
                out.append(Finding("milestone_too_late", ref, detail=(sd - timedelta(days=lead)).isoformat()))
        permit_id = m.get("permit_requirement_id")
        if permit_id is not None and permit_states.get(str(permit_id)) is None:
            out.append(Finding("permit_requirement_unknown", ref))
        act_id = m.get("activity_id")
        if act_id is not None:
            act = activities.get(str(act_id))
            if act is None:
                out.append(Finding("activity_missing", ref, WARNING))
            elif d is not None and str(act.get("start_date")) != d.isoformat():
                out.append(Finding("schedule_out_of_sync", ref, WARNING, str(act.get("start_date"))))

    out += gate_binding_findings(catalogue, milestones, gates)
    return out


def gate_binding_findings(
    catalogue: Any, milestones: list[Mapping[str, Any]], gates: list[Mapping[str, Any]]
) -> list[Finding]:
    """Every gate of the project has exactly one milestone, dated like the gate and in the gates' order."""
    out: list[Finding] = []
    gate_kind = catalogue.gate_kind
    gate_by_code = {str(g["code"]): g for g in gates}
    bound: dict[str, list[Mapping[str, Any]]] = {}
    for m in milestones:
        ref = str(m["id"])
        code = m.get("gate_code")
        is_gate_kind = m["kind_code"] == gate_kind
        if code and not is_gate_kind:
            out.append(Finding("gate_code_on_wrong_kind", ref))
        elif is_gate_kind and not code:
            out.append(Finding("gate_milestone_without_gate", ref))
        if code:
            if str(code) not in gate_by_code:
                out.append(Finding("gate_unknown", ref, detail=str(code)))
            else:
                bound.setdefault(str(code), []).append(m)
    for code, g in gate_by_code.items():
        rows = bound.get(code, [])
        if not rows:
            out.append(Finding("gate_without_milestone", code))
            continue
        if len(rows) > 1:
            out.append(Finding("gate_milestone_duplicate", code))
        target = _day(g.get("target_date"))
        d = _day(rows[0].get("planned_date"))
        if target is not None and d is not None and d != target and g.get("status") != "decided":
            out.append(Finding("gate_date_differs", str(rows[0]["id"]), WARNING, target.isoformat()))
        # A published gate milestone is meant to own the gate's date: the gate links to its schedule activity.
        activity = rows[0].get("activity_id")
        if (
            activity is not None
            and g.get("status") != "decided"
            and str(g.get("schedule_activity_id") or "") != str(activity)
        ):
            out.append(Finding("gate_not_bound_to_schedule", str(rows[0]["id"]), WARNING, code))
    ordered = sorted((g for g in gates if str(g["code"]) in bound), key=lambda g: g["order"])
    previous: date | None = None
    for g in ordered:
        d = _day(bound[str(g["code"])][0].get("planned_date"))
        if d is None:
            continue
        if previous is not None and d < previous:
            out.append(Finding("gates_out_of_order", str(bound[str(g["code"])][0]["id"])))
        previous = d
    return out


def backplan(
    milestones: list[Mapping[str, Any]], *, anchor_kind: str | None, gate_kind: str | None
) -> tuple[list[dict[str, Any]], list[str]]:
    """Dates a backward plan from the anchor gives, as ``({id, code, from, to}, unreached ids)``.

    A milestone's date is its successor's date minus its lead days. The anchor and every gate milestone
    keep the date they have: the anchor is the starting point and a gate date belongs to the governance
    model. A milestone whose chain does not end in a dated anchor or gate milestone is ``unreached``.
    """
    by_id = {str(m["id"]): m for m in milestones}
    fixed = {str(m["id"]) for m in milestones if m["kind_code"] in (anchor_kind, gate_kind) or m.get("gate_code")}
    cyclic = chain_cycles(milestones)
    memo: dict[str, date | None] = {}

    def date_of(mid: str, depth: int = 0) -> date | None:
        if mid in memo:
            return memo[mid]
        m = by_id[mid]
        if mid in fixed:
            memo[mid] = _day(m.get("planned_date"))
        elif mid in cyclic or depth > len(by_id) or not m.get("successor_id") or str(m["successor_id"]) not in by_id:
            memo[mid] = None
        else:
            base = date_of(str(m["successor_id"]), depth + 1)
            memo[mid] = base - timedelta(days=int(m.get("lead_days") or 0)) if base is not None else None
        return memo[mid]

    changes: list[dict[str, Any]] = []
    unreached: list[str] = []
    for m in milestones:
        mid = str(m["id"])
        if mid in fixed:
            continue
        new = date_of(mid)
        if new is None:
            unreached.append(mid)
        else:
            old = _day(m.get("planned_date"))
            changes.append(
                {
                    "id": mid,
                    "code": m["code"],
                    "from": old.isoformat() if old else None,
                    "to": new.isoformat(),
                    "changed": old != new,
                }
            )
    return changes, unreached


def submission_findings(
    catalogue: Any,
    *,
    requirements: list[Mapping[str, Any]],
    concepts: list[Mapping[str, Any]],
    programme: list[Mapping[str, Any]],
    milestones: list[Mapping[str, Any]],
    gates: list[Mapping[str, Any]],
    operation_proof_date: date | None,
    permit_states: Mapping[str, str | None] | None = None,
    activities: Mapping[str, Mapping[str, Any] | None] | None = None,
) -> list[Finding]:
    """Everything a submission is checked against, in one list."""
    return [
        *requirement_findings(catalogue, requirements),
        *concept_findings(catalogue, concepts, requirements),
        *programme_findings(catalogue, programme),
        *schedule_findings(
            catalogue,
            milestones,
            gates,
            operation_proof_date=operation_proof_date,
            permit_states=permit_states,
            activities=activities,
        ),
    ]


# ── what may be done now: one answer for the action and for its button ─────

NO_EDIT = "edit_permission_required"
NO_MANAGE = "manage_permission_required"
APPROVED_BY_GATE = "approved_by_gate_decision"
APPROVER_IS_SUBMITTER = "approver_is_submitter"
NO_APPROVE = "approval_permission_required"


def brief_action_refusal(
    action: str, status: str, *, can_edit: bool, has_frame_document: bool = True, gates_in_use: bool = True
) -> str | None:
    """Why the brief cannot be submitted, returned or edited now; ``None`` when it can.

    Completeness is not asked here: a submission of an incomplete brief answers 422 with the findings,
    which is how the user learns what is missing.
    """
    if not can_edit:
        return NO_EDIT
    if action == "submit":
        if status not in ("draft", "revising"):
            return "brief_not_editable"
        # With gates, a brief without a frame document could never be bound: it would sit in review for
        # good. Without gates it is approved by hand and needs no document.
        return None if has_frame_document or not gates_in_use else "frame_document_missing"
    if action == "return":
        return None if status == "in_review" else "brief_not_in_review"
    if action == "edit":
        # The reviewer reads everything, so it stands still while the brief is in review.
        return "brief_in_review" if status == "in_review" else None
    raise ValueError(action)


def brief_approval_refusal(
    status: str, *, can_manage: bool, gates_in_use: bool, four_eyes: bool, is_submitter: bool
) -> str | None:
    """Why this person cannot approve the brief by hand now; ``None`` when they can.

    Hand approval exists only on a project without gates: where gates are in use the gate decision
    approves and nobody does it here.
    """
    if gates_in_use:
        return APPROVED_BY_GATE
    if status != "in_review":
        return "brief_not_in_review"
    if not can_manage:
        return NO_APPROVE
    if four_eyes and is_submitter:
        return APPROVER_IS_SUBMITTER
    return None


# Refusals that mean "this action does not exist for the record as it stands": a client hides the control.
# Every other refusal is a missing right or a precondition somebody can still meet: the control is shown
# disabled, with the reason.
NOT_APPLICABLE = frozenset(
    {"already_in_state", "invalid_transition", "brief_not_editable", "brief_not_in_review", APPROVED_BY_GATE}
)


def capability(reason: str | None, state_reason: str | None) -> dict[str, Any]:
    """One ``can`` flag: ``allowed``, the ``reason`` when not, and whether the action ``applies`` at all."""
    return {"allowed": reason is None, "reason": reason, "applies": state_reason not in NOT_APPLICABLE}
