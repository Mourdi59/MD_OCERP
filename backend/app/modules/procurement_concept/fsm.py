# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""State machines of the procurement concept (SPEC section 3).

``binding`` of a concept is never a target here: it is read from governance
(the m08 frame document is binding and no change request is open). The
package states ``in_tender`` and ``awarded`` are reached only through
:data:`READ_BACK_TARGETS`, i.e. from the execution vehicle's events, never by
hand.
"""

from __future__ import annotations

CONCEPT_STATES = ("draft", "in_review", "approved", "binding", "reopened")
CONCEPT_FSM: dict[str, tuple[str, ...]] = {
    "draft": ("in_review",),
    "in_review": ("draft", "approved"),
    "approved": ("reopened",),
    "reopened": ("in_review",),
    "binding": (),
}

PACKAGE_STATES = ("planned", "procedure_set", "shortlisted", "in_tender", "awarded", "cancelled", "on_hold")
PACKAGE_FSM: dict[str, tuple[str, ...]] = {
    "planned": ("procedure_set", "on_hold", "cancelled"),
    "procedure_set": ("planned", "shortlisted", "on_hold", "cancelled"),
    "shortlisted": ("procedure_set", "on_hold", "cancelled"),
    "in_tender": ("cancelled",),
    "awarded": (),
    "cancelled": (),
    # Resuming returns to the state the hold was taken from (``state_before``).
    "on_hold": ("planned", "procedure_set", "shortlisted", "cancelled"),
}
# Targets only the execution read-back may write.
READ_BACK_TARGETS = ("in_tender", "awarded")
READ_BACK_ORDER = {"planned": 0, "procedure_set": 1, "shortlisted": 2, "in_tender": 3, "awarded": 4}

FRAMEWORK_STATES = ("draft", "active", "expired", "exhausted", "terminated")
FRAMEWORK_FSM: dict[str, tuple[str, ...]] = {
    "draft": ("active", "terminated"),
    "active": ("expired", "exhausted", "terminated"),
    "exhausted": ("active", "terminated"),
    "expired": (),
    "terminated": (),
}


def can_transition(fsm: dict[str, tuple[str, ...]], current: str, target: str) -> bool:
    """Whether ``current -> target`` is an edge of ``fsm``."""
    return target in fsm.get(current, ())


def can_set_package_state_by_hand(current: str, target: str) -> bool:
    """Manual package moves: every edge except the read-back targets."""
    return target not in READ_BACK_TARGETS and can_transition(PACKAGE_FSM, current, target)


def read_back_target(current: str, target: str) -> str | None:
    """The state an execution event moves a package to, or ``None`` when it would not move it.

    Idempotent and monotone: a repeated or late event (``published`` after
    ``awarded``) never moves a package backwards; cancelled packages stay.
    """
    if target not in READ_BACK_TARGETS or current == "cancelled":
        return None
    if READ_BACK_ORDER.get(current, -1) >= READ_BACK_ORDER[target]:
        return None
    return target
