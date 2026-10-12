# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""State machines of project governance, built on :class:`app.core.fsm.EntityFSM`.

Gate lifecycle::

    not_started -> in_preparation -> in_review -> decided
                        ^               |  |         |
                        |               |  +-> on_hold
                        +---------------+-------+----+

``in_review -> in_preparation`` covers three causes: the approval route was
rejected, the decider chose *recycle*, or the submitter withdrew. A hold, a
recycle and a reopen each close the current attempt; the next attempt starts
in preparation with ``attempt_no + 1``. The decision of the closed attempt is
kept untouched, which is why reopening is a transition and not a reset.

Frame document release lifecycle::

    draft <-> in_review -> approved_at_gate -> binding <-> superseded

A binding document is never moved back to draft. A new revision of a binding
document is a change request, and the binding revision stays in force until
the change is approved (see ``service.GovernanceService.apply_change_decision``).
A binding document is superseded when the project moves to a phase model that
no longer has its document type: it leaves the frame, its bound revision stays
on record. It is binding again when a later model change brings the type back.

Role gates are not declared on the transitions: who may move a gate is a
question of route entitlement and area ownership, answered in the service,
not of the global role.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

GATE_STATES: tuple[str, ...] = ("not_started", "in_preparation", "in_review", "on_hold", "decided")
DOCUMENT_STATES: tuple[str, ...] = ("draft", "in_review", "approved_at_gate", "binding", "superseded")

GATE_FSM = register_fsm(
    EntityFSM(
        "governance_gate",
        initial="not_started",
        transitions=[
            StateTransition("not_started", "in_preparation", description="preparation started"),
            StateTransition("in_preparation", "in_review", description="submitted for review"),
            StateTransition("in_review", "in_preparation", description="returned, recycled or withdrawn"),
            StateTransition("in_review", "on_hold", description="decision: hold"),
            StateTransition("in_review", "decided", description="decision: go, go with conditions or stop"),
            StateTransition("on_hold", "in_preparation", description="hold resumed as a new attempt"),
            StateTransition("decided", "in_preparation", description="reopened as a new attempt"),
        ],
    )
)

DOCUMENT_FSM = register_fsm(
    EntityFSM(
        "governance_frame_document",
        initial="draft",
        transitions=[
            StateTransition("draft", "in_review", description="submitted for the gate"),
            StateTransition("in_review", "draft", description="returned to draft"),
            StateTransition("in_review", "approved_at_gate", description="approved by a gate decision"),
            StateTransition("approved_at_gate", "binding", description="binding after the gate"),
            StateTransition("binding", "superseded", description="document type left the phase model"),
            StateTransition("superseded", "binding", description="document type back in the phase model"),
        ],
    )
)

__all__ = ["DOCUMENT_FSM", "DOCUMENT_STATES", "GATE_FSM", "GATE_STATES"]
