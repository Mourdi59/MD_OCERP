# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""State machines of the quality concept, as data.

Each machine is a mapping ``state -> {action: next_state}``. Actions marked in
``MIRROR_ACTIONS`` are only applied from another module's event or record (the
governance frame document, a released hold gate, an issued handover
certificate); the service refuses them on a user request, so a state that the
other module owns can never be set here alone.
"""

from __future__ import annotations

CONCEPT = {
    "draft": {"submit": "in_review"},
    "in_review": {"return": "draft", "approve": "approved"},
    "approved": {"bind": "binding", "revise": "revising"},
    "binding": {},
    "revising": {"submit": "in_review"},
}

CERTIFICATION = {
    "planned": {"register": "registered", "abandon": "abandoned"},
    "registered": {
        "assess_design": "design_assessed",
        "assess_post_construction": "post_construction_assessed",
        "abandon": "abandoned",
    },
    "design_assessed": {"assess_post_construction": "post_construction_assessed", "abandon": "abandoned"},
    "post_construction_assessed": {"certify": "certified", "miss_level": "level_missed", "abandon": "abandoned"},
    "certified": {},
    "level_missed": {},
    "abandoned": {},
}

CREDIT = {
    "targeted": {"submit_evidence": "evidence_submitted", "drop": "dropped"},
    "evidence_submitted": {
        "achieve": "achieved",
        "not_achieve": "not_achieved",
        "return": "targeted",
        "drop": "dropped",
    },
    "achieved": {},
    "not_achieved": {"submit_evidence": "evidence_submitted"},
    "dropped": {"reinstate": "targeted"},
}

# Stored proof decision; open | partly_delivered | delivered are derived from links on read.
PROOF_DECISION = {
    "none": {"accept": "accepted", "waive": "waived"},
    "accepted": {"reopen": "none"},
    "waived": {"reopen": "none"},
}

# ``blocked`` and ``ready`` are recomputed from preconditions; ``released`` only from a gate.
STAGE = {
    "blocked": {"mark_ready": "ready", "not_applicable": "not_applicable"},
    "ready": {"mark_blocked": "blocked", "open_test": "in_test", "not_applicable": "not_applicable"},
    "in_test": {"pass": "passed", "fail": "failed", "not_applicable": "not_applicable"},
    "failed": {"open_test": "in_test"},
    "passed": {"release": "released", "open_test": "in_test", "fail": "failed"},
    "released": {"open_test": "in_test", "go_stale": "stale"},
    "stale": {"release": "released", "open_test": "in_test"},
    "not_applicable": {"reinstate": "blocked"},
}

ACCEPTANCE = {
    "planned": {"request": "requested", "confirm_deemed": "deemed_accepted"},
    "requested": {
        "schedule_inspection": "inspection_scheduled",
        "accept": "accepted",
        "accept_with_reservations": "accepted_with_reservations",
        "refuse": "refused",
        "withdraw": "planned",
        "confirm_deemed": "deemed_accepted",
    },
    "inspection_scheduled": {
        "accept": "accepted",
        "accept_with_reservations": "accepted_with_reservations",
        "refuse": "refused",
        "confirm_deemed": "deemed_accepted",
    },
    "refused": {"request": "requested"},
    "accepted": {"revoke": "requested"},
    "accepted_with_reservations": {"revoke": "requested"},
    "deemed_accepted": {},
}

PRESERVATION = {
    "planned": {"invite": "invited", "record_survey": "surveyed", "refuse_access": "access_refused"},
    "invited": {"record_survey": "surveyed", "refuse_access": "access_refused"},
    "surveyed": {"issue_report": "report_issued"},
    "report_issued": {"close": "closed"},
    "closed": {},
    "access_refused": {"close": "closed"},
}

MACHINES: dict[str, dict[str, dict[str, str]]] = {
    "concept": CONCEPT,
    "certification": CERTIFICATION,
    "credit": CREDIT,
    "proof": PROOF_DECISION,
    "stage": STAGE,
    "acceptance": ACCEPTANCE,
    "preservation": PRESERVATION,
}

# Actions a user request may never trigger: another module's record decides them.
MIRROR_ACTIONS: dict[str, frozenset[str]] = {
    "concept": frozenset({"approve", "bind"}),
    "stage": frozenset({"release", "go_stale", "mark_ready", "mark_blocked"}),
    "acceptance": frozenset({"accept", "accept_with_reservations", "revoke"}),
}

# Actions that need a rationale in the request.
RATIONALE_ACTIONS: dict[str, frozenset[str]] = {
    "certification": frozenset({"abandon"}),
    "proof": frozenset({"waive"}),
    "stage": frozenset({"not_applicable"}),
    "acceptance": frozenset({"refuse"}),
    "preservation": frozenset({"refuse_access"}),
}


class TransitionError(Exception):
    """A refused transition; ``code`` is the API error code."""

    def __init__(self, code: str, machine: str, state: str, action: str) -> None:
        super().__init__(f"{machine}: {code} ({state} -> {action})")
        self.code = code
        self.machine = machine
        self.state = state
        self.action = action


def next_state(machine: str, state: str, action: str, *, mirror: bool = False, rationale: str = "") -> str:
    """The state ``action`` leads to from ``state``, or :class:`TransitionError`.

    Args:
        machine: Key of :data:`MACHINES`.
        state: Current state.
        action: Requested action.
        mirror: True when another module's record drives the change.
        rationale: Text the request carries; required for :data:`RATIONALE_ACTIONS`.
    """
    table = MACHINES[machine]
    if action in MIRROR_ACTIONS.get(machine, frozenset()) and not mirror:
        raise TransitionError("transition_owned_elsewhere", machine, state, action)
    target = table.get(state, {}).get(action)
    if target is None:
        raise TransitionError("invalid_transition", machine, state, action)
    if action in RATIONALE_ACTIONS.get(machine, frozenset()) and not rationale.strip():
        raise TransitionError("rationale_required", machine, state, action)
    return target


def allowed_actions(machine: str, state: str, *, mirror: bool = False) -> list[str]:
    """Actions available from ``state`` (user actions only unless ``mirror``)."""
    owned = MIRROR_ACTIONS.get(machine, frozenset())
    return sorted(a for a in MACHINES[machine].get(state, {}) if mirror or a not in owned)
