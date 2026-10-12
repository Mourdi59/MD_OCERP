# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycles of the staffing plan, positions, fills, personnel files, travel and leave.

Plan (one per project)::

    draft -> in_review -> approved -> binding -> revising -> in_review ...
               |                                    ^
               +--------- returned (draft) ---------+

``approved`` and ``binding`` are written only by the mirror of the governance
frame document ``m05_personnel_frame`` (``events.py``): the gate decision or an
approved frame change request is the approval (lead decision 10). Editing a
position of a binding plan moves it to ``revising``; the bound snapshot stays
in force until governance binds the next revision (rule 7).

A position's ``filled`` is derived from confirmed fills and never stored
(rule 2); the stored lifecycle is open / recruiting / on_hold / cancelled.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

PLAN_STATES: tuple[str, ...] = ("draft", "in_review", "approved", "binding", "revising")
POSITION_STATES: tuple[str, ...] = ("open", "recruiting", "on_hold", "cancelled")
POSITION_EFFECTIVE_STATES: tuple[str, ...] = ("open", "recruiting", "filled", "on_hold", "cancelled")
FILL_STATES: tuple[str, ...] = ("proposed", "confirmed", "ended")
FILE_STATES: tuple[str, ...] = ("active", "ended", "retention_hold", "anonymised")
TRAVEL_STATES: tuple[str, ...] = ("planned", "booked", "done", "cancelled")
LEAVE_STATES: tuple[str, ...] = ("requested", "approved", "taken", "cancelled")

# Plan states in which positions are edited without opening a revision.
PLAN_EDITABLE: tuple[str, ...] = ("draft", "revising")

PLAN_FSM = register_fsm(
    EntityFSM(
        "staffing_plan",
        initial="draft",
        transitions=[
            StateTransition("draft", "in_review", description="plan submitted"),
            StateTransition("revising", "in_review", description="revision submitted"),
            StateTransition("in_review", "draft", description="plan returned"),
            StateTransition("in_review", "approved", description="approved through governance"),
            StateTransition("approved", "binding", description="frame document binding"),
            StateTransition("binding", "revising", description="revision opened"),
            StateTransition("approved", "revising", description="revision opened"),
        ],
    )
)

POSITION_FSM = register_fsm(
    EntityFSM(
        "staffing_position",
        initial="open",
        transitions=[
            StateTransition("open", "recruiting", description="recruiting started"),
            StateTransition("recruiting", "open", description="recruiting stopped"),
            StateTransition("open", "on_hold", description="put on hold"),
            StateTransition("recruiting", "on_hold", description="put on hold"),
            StateTransition("on_hold", "open", description="resumed"),
            StateTransition("open", "cancelled", description="cancelled"),
            StateTransition("recruiting", "cancelled", description="cancelled"),
            StateTransition("on_hold", "cancelled", description="cancelled"),
        ],
        terminal=("cancelled",),
    )
)

FILL_FSM = register_fsm(
    EntityFSM(
        "staffing_fill",
        initial="proposed",
        transitions=[
            StateTransition("proposed", "confirmed", description="fill confirmed"),
            StateTransition("confirmed", "ended", description="fill ended"),
            StateTransition("proposed", "ended", description="proposal dropped"),
        ],
        terminal=("ended",),
    )
)

FILE_FSM = register_fsm(
    EntityFSM(
        "staffing_personnel_file",
        initial="active",
        transitions=[
            StateTransition("active", "ended", description="assignment ended"),
            StateTransition("ended", "active", description="assignment resumed"),
            StateTransition("active", "retention_hold", description="legal hold"),
            StateTransition("ended", "retention_hold", description="legal hold"),
            StateTransition("retention_hold", "ended", description="legal hold released"),
            StateTransition("ended", "anonymised", description="retention reached or erasure"),
            StateTransition("active", "anonymised", description="erasure request"),
        ],
        terminal=("anonymised",),
    )
)

TRAVEL_FSM = register_fsm(
    EntityFSM(
        "staffing_travel",
        initial="planned",
        transitions=[
            StateTransition("planned", "booked", description="booked"),
            StateTransition("booked", "done", description="travelled"),
            StateTransition("planned", "cancelled", description="cancelled"),
            StateTransition("booked", "cancelled", description="cancelled"),
        ],
        terminal=("done", "cancelled"),
    )
)

LEAVE_FSM = register_fsm(
    EntityFSM(
        "staffing_leave",
        initial="requested",
        transitions=[
            StateTransition("requested", "approved", description="approved"),
            StateTransition("approved", "taken", description="taken"),
            StateTransition("requested", "cancelled", description="cancelled"),
            StateTransition("approved", "cancelled", description="cancelled"),
        ],
        terminal=("taken", "cancelled"),
    )
)

__all__ = [
    "FILE_FSM",
    "FILE_STATES",
    "FILL_FSM",
    "FILL_STATES",
    "LEAVE_FSM",
    "LEAVE_STATES",
    "PLAN_EDITABLE",
    "PLAN_FSM",
    "PLAN_STATES",
    "POSITION_EFFECTIVE_STATES",
    "POSITION_FSM",
    "POSITION_STATES",
    "TRAVEL_FSM",
    "TRAVEL_STATES",
]
