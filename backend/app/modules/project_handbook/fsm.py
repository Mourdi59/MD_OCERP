# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Lifecycle of a handbook chapter.

::

    draft -> in_review -> approved -> revising -> in_review ...
               |
               +--------- returned (draft)

Editing an approved chapter opens a revision (``revising``); the approved version stays in force until
the next one is approved. A chapter in review stands still. With four eyes on, the approver is never the
submitter.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

CHAPTER_STATES: tuple[str, ...] = ("draft", "in_review", "approved", "revising")
# States in which the text is edited.
CHAPTER_EDITABLE: tuple[str, ...] = ("draft", "revising")

CHAPTER_FSM = register_fsm(
    EntityFSM(
        "project_handbook_chapter",
        initial="draft",
        transitions=[
            StateTransition("draft", "in_review", description="chapter submitted"),
            StateTransition("revising", "in_review", description="revision submitted"),
            StateTransition("in_review", "draft", description="chapter returned"),
            StateTransition("in_review", "revising", description="revision returned"),
            StateTransition("in_review", "approved", description="chapter approved"),
            StateTransition("approved", "revising", description="revision opened"),
        ],
    )
)

__all__ = ["CHAPTER_EDITABLE", "CHAPTER_FSM", "CHAPTER_STATES"]
