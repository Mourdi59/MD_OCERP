# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycles of commitments, plan items and engagement events, on :class:`app.core.fsm.EntityFSM`.

Commitment (SPEC 3, rules 10, 18, 19)::

    proposed -> agreed -> in_progress -> fulfilled -> verified
        \\          \\          \\             \\
         +----------+----------+-------------+--> withdrawn (rationale, under mandate)
                    agreed / in_progress ------> breached (confirmed, rationale)
                    breached -> in_progress | fulfilled | withdrawn

``breached`` as a flag (overdue) is computed on read; the state is the
confirmed breach. ``proposed -> agreed`` and any ``-> withdrawn`` are mandate
decisions (rule 10), checked by the service before the FSM runs.

Plan item: ``planned -> active -> paused -> active``, ``completed`` and
``cancelled`` end it. Event: ``planned -> held | cancelled``; an event may also
be recorded straight as ``held``.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

COMMITMENT_STATES: tuple[str, ...] = (
    "proposed",
    "agreed",
    "in_progress",
    "fulfilled",
    "verified",
    "withdrawn",
    "breached",
)
COMMITMENT_OPEN: tuple[str, ...] = ("proposed", "agreed", "in_progress", "breached")
# Transitions that are a decision of type ``stakeholder_commitment`` (rule 10).
MANDATE_TARGETS: tuple[str, ...] = ("agreed", "withdrawn")

PLAN_STATES: tuple[str, ...] = ("planned", "active", "paused", "completed", "cancelled")
EVENT_STATES: tuple[str, ...] = ("planned", "held", "cancelled")


def _transitions(pairs: list[tuple[str, str, str]]) -> list[StateTransition]:
    return [StateTransition(a, b, description=d) for a, b, d in pairs]


COMMITMENT_FSM = register_fsm(
    EntityFSM(
        "stakeholder_commitment",
        initial="proposed",
        transitions=_transitions(
            [
                ("proposed", "agreed", "agreed under mandate"),
                ("agreed", "in_progress", "work started"),
                ("agreed", "fulfilled", "fulfilled"),
                ("in_progress", "fulfilled", "fulfilled"),
                ("fulfilled", "verified", "verified and loop closed"),
                ("fulfilled", "in_progress", "verification failed"),
                ("proposed", "withdrawn", "withdrawn under mandate"),
                ("agreed", "withdrawn", "withdrawn under mandate"),
                ("in_progress", "withdrawn", "withdrawn under mandate"),
                ("agreed", "breached", "breach confirmed"),
                ("in_progress", "breached", "breach confirmed"),
                ("breached", "in_progress", "remedy started"),
                ("breached", "fulfilled", "fulfilled late"),
                ("breached", "withdrawn", "withdrawn under mandate"),
            ]
        ),
        terminal=("verified", "withdrawn"),
    )
)

PLAN_FSM = register_fsm(
    EntityFSM(
        "stakeholder_plan_item",
        initial="planned",
        transitions=_transitions(
            [
                ("planned", "active", "activated"),
                ("active", "paused", "paused"),
                ("paused", "active", "resumed"),
                ("planned", "cancelled", "cancelled"),
                ("active", "cancelled", "cancelled"),
                ("paused", "cancelled", "cancelled"),
                ("active", "completed", "completed"),
                ("paused", "completed", "completed"),
            ]
        ),
        terminal=("completed", "cancelled"),
    )
)

EVENT_FSM = register_fsm(
    EntityFSM(
        "stakeholder_engagement_event",
        initial="planned",
        transitions=_transitions([("planned", "held", "held"), ("planned", "cancelled", "cancelled")]),
        terminal=("held", "cancelled"),
    )
)

__all__ = [
    "COMMITMENT_FSM",
    "COMMITMENT_OPEN",
    "COMMITMENT_STATES",
    "EVENT_FSM",
    "EVENT_STATES",
    "MANDATE_TARGETS",
    "PLAN_FSM",
    "PLAN_STATES",
]
