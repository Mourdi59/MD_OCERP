# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycles of applications, permits and conditions, on :class:`app.core.fsm.EntityFSM`.

Application::

    planned -> preparing -> internal_review -> submitted -> validated -> under_review -> decided
                   |  ^-----------'               |   \\___________________^    |
                   '-------------> submitted      '--> info_requested <--------'
    withdrawn from any open state

``internal_review`` is optional (project setting, lead decision k).
``decided`` is entered only by recording a decision; there is no plain transition
call for it in the API. Requirement state is derived, never stored.

Condition::

    open -> evidence_submitted -> discharged
    open -> discharge_applied -> discharged | open (authority rejected)
    open -> in_compliance <-> breach              (ongoing conditions)
    open -> not_triggered | waived                (authority only, with document)
    any live state -> superseded                  (permit varied)
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

APPLICATION_STATES: tuple[str, ...] = (
    "planned",
    "preparing",
    "internal_review",
    "submitted",
    "validated",
    "under_review",
    "info_requested",
    "decided",
    "withdrawn",
)
APPLICATION_OPEN: tuple[str, ...] = (
    "planned",
    "preparing",
    "internal_review",
    "submitted",
    "validated",
    "under_review",
    "info_requested",
)
# States a user may move an application into through the transition endpoint.
USER_TARGETS: tuple[str, ...] = (
    "preparing",
    "internal_review",
    "submitted",
    "validated",
    "under_review",
    "info_requested",
    "withdrawn",
)
APPLICATION_KINDS: tuple[str, ...] = (
    "new",
    "variation",
    "amendment_non_material",
    "extension_of_validity",
    "discharge_of_conditions",
    "early_start",
)
DECISION_OUTCOMES: tuple[str, ...] = (
    "granted",
    "granted_with_conditions",
    "partially_granted",
    "refused",
    "deemed_granted",
    "withdrawn",
)
PERMIT_STATES: tuple[str, ...] = ("in_force", "suspended", "lapsed", "revoked", "superseded", "expired")
CONDITION_STATES: tuple[str, ...] = (
    "open",
    "evidence_submitted",
    "discharge_applied",
    "discharged",
    "in_compliance",
    "breach",
    "not_triggered",
    "waived",
    "superseded",
)
DISCHARGE_MODES: tuple[str, ...] = (
    "self_certified",
    "authority_discharged",
    "deemed_discharged",
    "not_triggered",
    "waived_by_authority",
)

APPLICATION_FSM = register_fsm(
    EntityFSM(
        "permit_application",
        initial="planned",
        transitions=[
            StateTransition("planned", "preparing", description="preparation started"),
            StateTransition("preparing", "internal_review", description="sent for internal release"),
            StateTransition("internal_review", "preparing", description="returned by internal review"),
            StateTransition("internal_review", "submitted", description="released and filed"),
            StateTransition("preparing", "submitted", description="filed with the authority"),
            StateTransition("submitted", "validated", description="authority confirmed completeness"),
            StateTransition("submitted", "under_review", description="authority review started"),
            StateTransition("validated", "under_review", description="authority review started"),
            StateTransition("submitted", "info_requested", description="authority asked for information"),
            StateTransition("validated", "info_requested", description="authority asked for information"),
            StateTransition("under_review", "info_requested", description="authority asked for information"),
            StateTransition("info_requested", "under_review", description="information supplied"),
            StateTransition("submitted", "decided", description="decision recorded"),
            StateTransition("validated", "decided", description="decision recorded"),
            StateTransition("under_review", "decided", description="decision recorded"),
            StateTransition("info_requested", "decided", description="decision recorded"),
            *[
                StateTransition(s, "withdrawn", description="withdrawn")
                for s in ("planned", "preparing", "internal_review", "submitted", "validated", "under_review")
            ],
            StateTransition("info_requested", "withdrawn", description="withdrawn"),
        ],
        terminal=("decided", "withdrawn"),
    )
)

PERMIT_FSM = register_fsm(
    EntityFSM(
        "authority_permit",
        initial="in_force",
        transitions=[
            StateTransition("in_force", "suspended", description="suspended by the authority"),
            StateTransition("suspended", "in_force", description="suspension lifted"),
            StateTransition("in_force", "lapsed", description="not started within the validity period"),
            StateTransition("in_force", "revoked", description="revoked by the authority"),
            StateTransition("suspended", "revoked", description="revoked by the authority"),
            StateTransition("in_force", "superseded", description="superseded by a variation or a new decision"),
            StateTransition("suspended", "superseded", description="superseded"),
            StateTransition("in_force", "expired", description="time limit reached"),
            StateTransition("lapsed", "in_force", description="validity extended"),
        ],
        terminal=("revoked", "superseded", "expired"),
    )
)

_LIVE_CONDITION = ("open", "evidence_submitted", "discharge_applied", "discharged", "in_compliance", "breach")

CONDITION_FSM = register_fsm(
    EntityFSM(
        "permit_condition",
        initial="open",
        transitions=[
            StateTransition("open", "evidence_submitted", description="evidence submitted"),
            StateTransition("evidence_submitted", "open", description="evidence withdrawn"),
            StateTransition("evidence_submitted", "discharged", description="discharged (self certified)"),
            StateTransition("open", "discharged", description="discharged by the authority or deemed"),
            StateTransition("open", "discharge_applied", description="discharge applied for"),
            StateTransition("evidence_submitted", "discharge_applied", description="discharge applied for"),
            StateTransition("discharge_applied", "discharged", description="discharged by the authority"),
            StateTransition("discharge_applied", "open", description="discharge refused or withdrawn"),
            StateTransition("open", "in_compliance", description="ongoing condition complied with"),
            StateTransition("in_compliance", "breach", description="breach raised"),
            StateTransition("open", "breach", description="breach raised"),
            StateTransition("breach", "in_compliance", description="breach remedied"),
            StateTransition("open", "not_triggered", description="trigger did not occur"),
            StateTransition("open", "waived", description="waived by the authority"),
            StateTransition("evidence_submitted", "waived", description="waived by the authority"),
            *[StateTransition(s, "superseded", description="permit varied") for s in _LIVE_CONDITION],
            StateTransition("not_triggered", "superseded", description="permit varied"),
        ],
        terminal=("superseded", "waived"),
    )
)

__all__ = [
    "APPLICATION_FSM",
    "APPLICATION_KINDS",
    "APPLICATION_OPEN",
    "APPLICATION_STATES",
    "CONDITION_FSM",
    "CONDITION_STATES",
    "DECISION_OUTCOMES",
    "DISCHARGE_MODES",
    "PERMIT_FSM",
    "PERMIT_STATES",
    "USER_TARGETS",
]
