# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""State machines of the plant register, on :class:`app.core.fsm.EntityFSM`.

Plant item::

    identified -> specified -> enquired -> route_set -> ordered -> manufactured
        -> delivered -> installed -> commissioned -> handed_over      (+ cancelled)

Only the first three steps and ``manufactured`` are moved by hand
(``MANUAL_TARGETS``). ``ordered`` and ``delivered`` are READ from the linked
purchase order or owner-furnished item, ``installed`` from the OFI,
``commissioned`` from the linked commissioning system, and ``handed_over`` is
the handover act (rule 16). The service decides which source applies; the FSM
only says which steps exist. ``manufactured`` is the factory acceptance an owner
records against the order; no other module holds it.

A state that is read can move in both directions: a late reading may jump
steps forward, and a source that went away (order cancelled, link removed,
receipt reversed) takes the item back, down to ``route_set``. Every such move
is an edge here, so no state is ever assigned around the machine.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm
from app.modules.plant_register.calc import ITEM_STATES

MANUAL_TARGETS: frozenset[str] = frozenset({"specified", "enquired", "route_set", "manufactured", "cancelled"})

_LIVE = ITEM_STATES[:-1]
# States a reading can produce, plus the hand-recorded ``manufactured`` it can leave.
READ_STATES: tuple[str, ...] = ("route_set", "ordered", "delivered", "installed", "commissioned")
_CHAIN = set(zip(ITEM_STATES, ITEM_STATES[1:], strict=False))
_READ_EDGES = [(a, b) for a in (*READ_STATES, "manufactured") for b in READ_STATES if a != b and (a, b) not in _CHAIN]
ITEM_FSM = register_fsm(
    EntityFSM(
        "plant_item",
        initial="identified",
        transitions=[
            *[StateTransition(a, b) for a, b in zip(ITEM_STATES, ITEM_STATES[1:], strict=False)],
            *[StateTransition(a, b, description="read from its source") for a, b in _READ_EDGES],
            StateTransition("route_set", "specified", description="route withdrawn"),
            StateTransition("enquired", "specified", description="basis quote withdrawn"),
            *[StateTransition(s, "cancelled") for s in _LIVE],
        ],
        terminal=("handed_over", "cancelled"),
    )
)

SLOT_STATES: tuple[str, ...] = ("requested", "held", "converted_to_order", "released", "expired")
SLOT_FSM = register_fsm(
    EntityFSM(
        "plant_slot_reservation",
        initial="requested",
        transitions=[
            StateTransition("requested", "held"),
            StateTransition("requested", "released"),
            StateTransition("held", "converted_to_order"),
            StateTransition("held", "released"),
            StateTransition("held", "expired"),
        ],
        terminal=("converted_to_order", "released", "expired"),
    )
)

PAPER_STATES: tuple[str, ...] = ("draft", "submitted", "approved", "rejected")
PAPER_FSM = register_fsm(
    EntityFSM(
        "plant_decision_paper",
        initial="draft",
        transitions=[
            StateTransition("draft", "submitted"),
            StateTransition("submitted", "approved"),
            StateTransition("submitted", "rejected"),
            StateTransition("submitted", "draft", description="withdrawn"),
        ],
        terminal=("approved", "rejected"),
    )
)

SPARE_STATES: tuple[str, ...] = ("required", "specified", "delivered", "handed_over", "waived")
SPARE_FSM = register_fsm(
    EntityFSM(
        "plant_spare_part",
        initial="required",
        transitions=[
            StateTransition("required", "specified"),
            StateTransition("specified", "delivered"),
            StateTransition("delivered", "handed_over"),
            *[StateTransition(s, "waived") for s in ("required", "specified", "delivered")],
        ],
        terminal=("handed_over", "waived"),
    )
)

IT_STATES: tuple[str, ...] = ("planned", "provisioned", "retired")
IT_FSM = register_fsm(
    EntityFSM(
        "plant_it_service",
        initial="planned",
        transitions=[StateTransition("planned", "provisioned"), StateTransition("provisioned", "retired")],
        terminal=("retired",),
    )
)

__all__ = [
    "IT_FSM",
    "IT_STATES",
    "ITEM_FSM",
    "MANUAL_TARGETS",
    "PAPER_FSM",
    "PAPER_STATES",
    "READ_STATES",
    "SLOT_FSM",
    "SLOT_STATES",
    "SPARE_FSM",
    "SPARE_STATES",
]
