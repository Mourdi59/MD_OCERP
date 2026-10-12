# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycles of the delivery model, its packages and owner-furnished items.

Model (one per project)::

    draft -> under_evaluation -> proposed -> approved -> binding
                   ^                |                     |
                   +--- withdrawn --+       reopened <----+  (a governance change request is open)
                   +------------------------ reopened

``approved`` and ``binding`` are written only by the mirror of the governance
frame document (``events.py``): the gate decision on the contracts area is the
approval (lead decision 2). A package's ``in_procurement`` and ``awarded`` are
read from its linked procurement row and never stored.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

MODEL_STATES: tuple[str, ...] = ("draft", "under_evaluation", "proposed", "approved", "binding", "reopened")
PACKAGE_STATES: tuple[str, ...] = ("planned", "closed", "cancelled")
PACKAGE_EFFECTIVE_STATES: tuple[str, ...] = ("planned", "in_procurement", "awarded", "closed", "cancelled")
OFI_STATES: tuple[str, ...] = ("identified", "route_set", "ordered", "delivered", "handed_to_installer")

# States in which options, criteria, scores and allocations may still be edited.
EDITABLE: tuple[str, ...] = ("draft", "under_evaluation", "reopened")

MODEL_FSM = register_fsm(
    EntityFSM(
        "delivery_model",
        initial="draft",
        transitions=[
            StateTransition("draft", "under_evaluation", description="evaluation started"),
            StateTransition("reopened", "under_evaluation", description="evaluation restarted"),
            StateTransition("under_evaluation", "proposed", description="decision proposed"),
            StateTransition("reopened", "proposed", description="new decision proposed"),
            StateTransition("proposed", "under_evaluation", description="proposal withdrawn"),
            StateTransition("proposed", "approved", description="approved at the governance gate"),
            StateTransition("approved", "binding", description="frame document binding"),
            StateTransition("binding", "reopened", description="frame change request opened"),
            # The way back when the change request is rejected or the reopening is closed without a new decision.
            StateTransition("reopened", "binding", description="reopening closed, decision in force stays"),
            StateTransition("under_evaluation", "binding", description="reopening closed, decision in force stays"),
            StateTransition("proposed", "binding", description="change request rejected, decision in force stays"),
        ],
    )
)

PACKAGE_FSM = register_fsm(
    EntityFSM(
        "delivery_package",
        initial="planned",
        transitions=[
            StateTransition("planned", "closed", description="closed out"),
            StateTransition("planned", "cancelled", description="cancelled"),
            StateTransition("closed", "planned", description="reopened"),
            StateTransition("cancelled", "planned", description="reinstated"),
        ],
    )
)

OFI_FSM = register_fsm(
    EntityFSM(
        "delivery_ofi",
        initial="identified",
        transitions=[
            StateTransition("identified", "route_set", description="procurement route set"),
            StateTransition("route_set", "identified", description="route cleared"),
            StateTransition("route_set", "ordered", description="ordered"),
            StateTransition("ordered", "route_set", description="order cancelled"),
            StateTransition("ordered", "delivered", description="delivered"),
            StateTransition("delivered", "handed_to_installer", description="handed to the installing package"),
        ],
        terminal=("handed_to_installer",),
    )
)

# How the status of a linked procurement row reads in the package plan, per kind of row. Each owning
# module has its own vocabulary: "closed" is a finished tender but a bid package whose bidding ended
# without an award. A status listed nowhere reads "in_procurement": the row is out and not yet let.
LINK_STATUS: dict[str, dict[str, frozenset[str]]] = {
    "bid_package": {"planned": frozenset({"draft", "cancelled"}), "awarded": frozenset({"awarded"})},
    "tender_package": {"planned": frozenset({"draft"}), "awarded": frozenset({"awarded", "closed"})},
    "rfq": {"planned": frozenset({"draft", "cancelled"}), "awarded": frozenset({"awarded"})},
    "subcontract_agreement": {
        "planned": frozenset({"draft", "cancelled"}),
        "awarded": frozenset({"active", "suspended", "completed", "terminated"}),
    },
    "contract": {
        "planned": frozenset({"draft"}),
        "awarded": frozenset({"active", "suspended", "completed", "terminated"}),
    },
}


def effective_package_state(stored: str, link_kind: str | None, linked_status: str | None) -> str:
    """A package's state as the plan shows it: stored for closed/cancelled, else read from the linked row."""
    if stored in ("closed", "cancelled"):
        return stored
    if not link_kind or linked_status is None:
        return "planned"
    table = LINK_STATUS.get(link_kind, {})
    status = linked_status.lower()
    for state in ("planned", "awarded"):
        if status in table.get(state, frozenset()):
            return state
    return "in_procurement"


__all__ = [
    "EDITABLE",
    "LINK_STATUS",
    "MODEL_FSM",
    "MODEL_STATES",
    "OFI_FSM",
    "OFI_STATES",
    "PACKAGE_EFFECTIVE_STATES",
    "PACKAGE_FSM",
    "PACKAGE_STATES",
    "effective_package_state",
]
