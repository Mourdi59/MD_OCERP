# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What a caller may do to a record, and why not, from one place.

Every function here answers with an error code or ``None``. The service raises
on the code and the API reports it as a ``can`` flag, so a button is enabled
exactly when the request would be accepted for the reasons known before the
request is made. Refusals that depend on the body of the request (a missing
rationale, a date in the future) are not predicted here.

Pure: no session, no clock. The caller passes the facts.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.modules.quality_concept import fsm

# Unit states in which the dates a deemed acceptance counts from may still be recorded.
DATES_OPEN = ("planned", "requested", "inspection_scheduled")
ACCEPTED_STATES = ("accepted", "accepted_with_reservations", "deemed_accepted")
PLAN_OPEN_STATES = ("draft", "revising")

# HTTP status of each refusal code raised through :func:`status_of`; anything else is 422.
_STATUS = {
    "invalid_transition": 409,
    "transition_owned_elsewhere": 409,
    "approver_is_requester": 403,
    "approver_added_evidence": 403,
    "proof_not_delivered": 409,
    "stage_not_passed": 409,
    "release_already_requested": 409,
    "unit_dates_locked": 409,
    "unit_not_accepted": 409,
    "survey_recorded": 409,
    "refusal_is_final": 409,
    "deemed_acceptance_not_due": 409,
    "concept_not_editable": 409,
    "binding_requires_change_request": 409,
    "concept_missing": 404,
    "edit_required": 403,
    "manage_required": 403,
    "waive_required": 403,
}


def status_of(code: str) -> int:
    return _STATUS.get(code, 422)


@dataclass(frozen=True)
class Caller:
    """Who asks, and the permissions the router found on the token."""

    user_id: uuid.UUID
    edit: bool = False
    manage: bool = False
    waive: bool = False

    def needs(self, permission: str) -> str | None:
        return None if getattr(self, permission) else f"{permission}_required"


def first(*codes: str | None) -> str | None:
    """The first refusal of several checks, in the order the service applies them."""
    return next((c for c in codes if c), None)


def flags(checks: Mapping[str, str | None]) -> dict[str, Any]:
    """``{"can": {action: bool}, "can_reason": {action: code}}``; a reason only where refused."""
    return {
        "can": {action: code is None for action, code in checks.items()},
        "can_reason": {action: code for action, code in checks.items() if code is not None},
    }


def transition_refusal(machine: str, state: str, action: str) -> str | None:
    """Whether the state machine lets a user request ``action`` now; the rationale is the body's matter."""
    try:
        fsm.next_state(machine, state, action, rationale="-")
    except fsm.TransitionError as exc:
        return exc.code
    return None


def plan_refusal(concept_state: str | None) -> str | None:
    """The plan a governance gate reads is open while the concept is drafted or revised."""
    if concept_state is None:
        return "concept_missing"
    if concept_state == "binding":
        return "binding_requires_change_request"
    return None if concept_state in PLAN_OPEN_STATES else "concept_not_editable"


def plan_row(caller: Caller, concept_state: str | None) -> dict[str, Any]:
    """Flags of a row that is part of the plan: standards, stage definitions, proofs, units."""
    code = first(caller.needs("manage"), plan_refusal(concept_state))
    return flags({"edit": code, "delete": code})


# ── proofs ─────────────────────────────────────────────────────────────────


def waiver_request_refusal(decision: str) -> str | None:
    return None if decision == "none" else "invalid_transition"


def waiver_decision_refusal(
    decision: str, requested_by: uuid.UUID | None, rationale: str, actor: uuid.UUID, four_eyes: bool
) -> str | None:
    """Rule 7. One answer for approve and reject: both need a pending request and a second person."""
    if decision != "none":
        return "invalid_transition"
    if requested_by is None or not (rationale or "").strip():
        return "waiver_not_requested"
    if four_eyes and requested_by == actor:
        return "approver_is_requester"
    return None


def accept_refusal(
    decision: str, delivery_state: str, evidence_authors: Iterable[uuid.UUID | None], actor: uuid.UUID, four_eyes: bool
) -> str | None:
    """Whoever attached the evidence does not also accept it."""
    if delivery_state != "delivered":
        return "proof_not_delivered"
    if four_eyes and any(author == actor for author in evidence_authors):
        return "approver_added_evidence"
    return transition_refusal("proof", decision, "accept")


def proof(
    caller: Caller,
    *,
    concept_state: str | None,
    decision: str,
    requested_by: uuid.UUID | None,
    rationale: str,
    delivery_state: str,
    evidence_authors: Iterable[uuid.UUID | None],
    four_eyes: bool,
) -> dict[str, Any]:
    plan = first(caller.needs("manage"), plan_refusal(concept_state))
    return flags(
        {
            "edit": plan,
            "delete": plan,
            "link_evidence": caller.needs("edit"),
            "request_waiver": first(caller.needs("edit"), waiver_request_refusal(decision)),
            "decide_waiver": first(
                caller.needs("waive"),
                waiver_decision_refusal(decision, requested_by, rationale, caller.user_id, four_eyes),
            ),
            "accept": first(
                caller.needs("edit"),
                accept_refusal(decision, delivery_state, evidence_authors, caller.user_id, four_eyes),
            ),
            "reopen": first(caller.needs("edit"), transition_refusal("proof", decision, "reopen")),
        }
    )


# ── stages ─────────────────────────────────────────────────────────────────


def release_request_refusal(state: str, gate_status: str | None) -> str | None:
    """Rule 10: a passed (or stale) stage asks for its hold gate once."""
    if state not in ("passed", "stale"):
        return "stage_not_passed"
    if gate_status == "pending":
        return "release_already_requested"
    return None


def stage_progress(caller: Caller, *, state: str, computed_state: str, gate_status: str | None) -> dict[str, Any]:
    """``computed_state`` is the state after the preconditions were read; opening a test refreshes to it."""
    edit, manage = caller.needs("edit"), caller.needs("manage")
    return flags(
        {
            "open_test": first(edit, transition_refusal("stage", computed_state, "open_test")),
            "record_pass": first(edit, transition_refusal("stage", state, "pass")),
            "record_fail": first(edit, transition_refusal("stage", state, "fail")),
            "request_release": first(edit, release_request_refusal(state, gate_status)),
            "link_evidence": edit,
            "not_applicable": first(manage, transition_refusal("stage", state, "not_applicable")),
            "reinstate": first(manage, transition_refusal("stage", state, "reinstate")),
            "set_dependencies": manage,
        }
    )


# ── acceptance ─────────────────────────────────────────────────────────────


def dates_refusal(state: str) -> str | None:
    return None if state in DATES_OPEN else "unit_dates_locked"


def effect_refusal(state: str) -> str | None:
    return None if state in ACCEPTED_STATES else "unit_not_accepted"


def acceptance_unit(
    caller: Caller,
    *,
    concept_state: str | None,
    state: str,
    has_regime: bool,
    blocked: bool,
    deemed_due: bool,
) -> dict[str, Any]:
    """``blocked``: preconditions stay unmet even when every reservable one is taken as a reservation."""
    edit, manage = caller.needs("edit"), caller.needs("manage")
    plan = first(manage, plan_refusal(concept_state))
    request = first(
        edit,
        transition_refusal("acceptance", state, "request"),
        None if has_regime else "acceptance_regime_missing",
        "acceptance_preconditions_unmet" if blocked else None,
    )
    deemed = first(
        manage,
        transition_refusal("acceptance", state, "confirm_deemed"),
        None if deemed_due else "deemed_acceptance_not_due",
    )
    return flags(
        {
            "edit": plan,
            "delete": plan,
            # The handover act is linked after the plan is bound, so it is not a plan edit.
            "link_handover": manage,
            "request": request,
            "record_dates": first(edit, dates_refusal(state)),
            "schedule_inspection": first(manage, transition_refusal("acceptance", state, "schedule_inspection")),
            "withdraw": first(manage, transition_refusal("acceptance", state, "withdraw")),
            "refuse": first(manage, transition_refusal("acceptance", state, "refuse")),
            "confirm_deemed": deemed,
            "confirm_effect": first(manage, effect_refusal(state)),
        }
    )


# ── preservation, certification, expert reports ────────────────────────────


def survey_action_refusal(state: str, action: str, access_refused: bool) -> str | None:
    if action == "refuse_access" and access_refused:
        return "refusal_is_final"
    return transition_refusal("preservation", state, action)


def survey_delete_refusal(state: str) -> str | None:
    return None if state == "planned" else "survey_recorded"


def pair_refusal(phase: str) -> str | None:
    return None if phase == "after" else "only_after_surveys_pair"


SURVEY_ACTIONS = ("invite", "record_survey", "refuse_access", "issue_report", "close")


def survey(caller: Caller, *, state: str, phase: str, access_refused: bool) -> dict[str, Any]:
    edit = caller.needs("edit")
    checks = {a: first(edit, survey_action_refusal(state, a, access_refused)) for a in SURVEY_ACTIONS}
    return flags(
        {
            "edit": edit,
            "link_evidence": edit,
            **checks,
            "pair": first(edit, pair_refusal(phase)),
            "delete": first(edit, survey_delete_refusal(state)),
        }
    )


def certification(caller: Caller, *, state: str) -> dict[str, Any]:
    manage = caller.needs("manage")
    actions = sorted({a for transitions in fsm.CERTIFICATION.values() for a in transitions})
    return flags(
        {
            "edit": manage,
            "delete": manage,
            "add_credits": manage,
            **{a: first(manage, transition_refusal("certification", state, a)) for a in actions},
        }
    )


def credit(caller: Caller, *, state: str) -> dict[str, Any]:
    edit, manage = caller.needs("edit"), caller.needs("manage")
    actions = sorted({a for transitions in fsm.CREDIT.values() for a in transitions})
    return flags(
        {
            "edit": edit,
            "delete": manage,
            "link_evidence": edit,
            **{a: first(edit, transition_refusal("credit", state, a)) for a in actions},
        }
    )


def editable(caller: Caller, permission: str = "edit") -> dict[str, Any]:
    """Rows any holder of ``permission`` changes at any time: expert reports."""
    code = caller.needs(permission)
    return flags({"edit": code, "delete": code, "link_evidence": caller.needs("edit")})
