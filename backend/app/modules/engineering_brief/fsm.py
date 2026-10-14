# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycles of the engineering brief and of its concept items.

Brief (one per project)::

    draft -> in_review -> approved -> binding -> revising -> in_review ...
               |                                    ^
               +--------- returned (draft) ---------+

``approved`` and ``binding`` are written only by the mirror of the governance frame document
(``events.py``) or by a hand approval on a project without gates: the gate decision or an approved
frame change request is the approval. Editing a binding brief moves it to ``revising``; the bound
snapshot stays in force until governance binds the next revision.

A concept item is ``open`` until its decision is written down, then ``agreed``; both move freely.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

BRIEF_STATES: tuple[str, ...] = ("draft", "in_review", "approved", "binding", "revising")
CONCEPT_STATES: tuple[str, ...] = ("open", "agreed")

# Brief states in which content is edited without opening a revision.
BRIEF_EDITABLE: tuple[str, ...] = ("draft", "revising")

BRIEF_FSM = register_fsm(
    EntityFSM(
        "engineering_brief",
        initial="draft",
        transitions=[
            StateTransition("draft", "in_review", description="brief submitted"),
            StateTransition("revising", "in_review", description="revision submitted"),
            StateTransition("in_review", "draft", description="brief returned"),
            StateTransition("in_review", "approved", description="approved through governance"),
            StateTransition("approved", "binding", description="frame document binding"),
            StateTransition("binding", "revising", description="revision opened"),
            StateTransition("approved", "revising", description="revision opened"),
        ],
    )
)

CONCEPT_FSM = register_fsm(
    EntityFSM(
        "engineering_brief_concept",
        initial="open",
        transitions=[
            StateTransition("open", "agreed", description="decision agreed"),
            StateTransition("agreed", "open", description="decision reopened"),
        ],
    )
)

__all__ = ["BRIEF_EDITABLE", "BRIEF_FSM", "BRIEF_STATES", "CONCEPT_FSM", "CONCEPT_STATES"]
