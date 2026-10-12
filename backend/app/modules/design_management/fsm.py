# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""State machines of design management, built on :class:`app.core.fsm.EntityFSM`.

Every entity keeps its state in ``status`` (the FSM engine writes that
attribute); the API answers it as ``state``. Who may move a row is decided in
the service (route entitlement, four-eyes, party of the checker), not here.

Two lifecycles are not FSMs on purpose: a deliverable's state is COMPUTED from
its drawings' CDE states (rule 15; only ``waived`` is set by hand), and a
permit package's states from ``submitted`` on are READ from the linked
``review_authority`` cycle (SPEC section 3), so the FSM below only covers the
part this module owns and the sync step.
"""

from __future__ import annotations

from app.core.fsm import EntityFSM, StateTransition, register_fsm

ROLE_STATES = ("planned", "appointed", "active", "released")
APPROVAL_POINT_STATES = ("open", "in_review", "approved", "rejected")
DELIVERABLE_STATES = ("not_started", "in_progress", "issued_for_review", "accepted", "waived")
RELEASE_STATES = ("draft", "ready", "issued", "cancelled")
REVIEW_STATES = ("planned", "open", "comments_closed", "concluded")
COMMENT_STATES = ("open", "answered", "closed", "rejected")
REPORT_STATES = (
    "required",
    "commissioned",
    "in_progress",
    "submitted",
    "under_check",
    "remarks",
    "accepted",
    "rejected",
    "not_required",
)
PERMIT_STATES = (
    "assembling",
    "ready",
    "submitted",
    "under_review",
    "remarks",
    "approved",
    "partially_approved",
    "refused",
    "withdrawn",
)


def _t(a: str, b: str, d: str) -> StateTransition:
    return StateTransition(a, b, description=d)


ROLE_FSM = register_fsm(
    EntityFSM(
        "design_role",
        initial="planned",
        transitions=[
            _t("planned", "appointed", "appointed"),
            _t("appointed", "active", "started"),
            _t("planned", "active", "started without separate appointment"),
            _t("active", "released", "released from the project"),
            _t("appointed", "released", "released before start"),
        ],
        terminal=("released",),
    )
)

APPROVAL_POINT_FSM = register_fsm(
    EntityFSM(
        "design_approval_point",
        initial="open",
        transitions=[
            _t("open", "in_review", "submitted to the approval route"),
            _t("in_review", "approved", "approved by an entitled approver"),
            _t("in_review", "rejected", "rejected by an entitled approver"),
            _t("in_review", "open", "withdrawn"),
            _t("rejected", "open", "reworked"),
        ],
        terminal=("approved",),
    )
)

RELEASE_FSM = register_fsm(
    EntityFSM(
        "design_release",
        initial="draft",
        transitions=[
            _t("draft", "ready", "content checked"),
            _t("ready", "draft", "reopened for changes"),
            _t("ready", "issued", "issued as transmittals"),
            _t("draft", "cancelled", "cancelled"),
            _t("ready", "cancelled", "cancelled"),
        ],
        terminal=("issued", "cancelled"),
    )
)

REVIEW_FSM = register_fsm(
    EntityFSM(
        "design_review",
        initial="planned",
        transitions=[
            _t("planned", "open", "review opened"),
            _t("open", "comments_closed", "every comment answered and closed"),
            _t("comments_closed", "open", "comment reopened"),
            _t("comments_closed", "concluded", "outcome recorded"),
        ],
        terminal=("concluded",),
    )
)

COMMENT_FSM = register_fsm(
    EntityFSM(
        "design_review_comment",
        initial="open",
        transitions=[
            _t("open", "answered", "answered by the designer"),
            _t("answered", "closed", "accepted by the reviewer"),
            _t("answered", "open", "answer not accepted"),
            _t("open", "rejected", "comment rejected"),
            _t("answered", "rejected", "comment rejected"),
        ],
        terminal=("closed", "rejected"),
    )
)

REPORT_FSM = register_fsm(
    EntityFSM(
        "design_report",
        initial="required",
        transitions=[
            _t("required", "commissioned", "commissioned"),
            _t("commissioned", "in_progress", "work started"),
            _t("in_progress", "submitted", "submitted"),
            _t("submitted", "under_check", "under check"),
            _t("submitted", "accepted", "accepted without independent check"),
            _t("under_check", "remarks", "remarks issued"),
            _t("remarks", "in_progress", "reworked"),
            _t("under_check", "accepted", "accepted"),
            _t("under_check", "rejected", "rejected"),
            _t("rejected", "in_progress", "reworked after rejection"),
            _t("required", "not_required", "not required, with rationale"),
            _t("not_required", "required", "required again"),
        ],
        terminal=("accepted",),
    )
)

PERMIT_FSM = register_fsm(
    EntityFSM(
        "design_permit_package",
        initial="assembling",
        transitions=[
            _t("assembling", "ready", "every required item present"),
            _t("ready", "assembling", "reopened"),
            _t("ready", "submitted", "submitted, revisions pinned"),
            _t("submitted", "under_review", "authority review (from the cycle)"),
            _t("under_review", "remarks", "remarks issued (from the cycle)"),
            _t("remarks", "under_review", "resubmitted (from the cycle)"),
            _t("under_review", "approved", "approved (from the cycle)"),
            _t("under_review", "partially_approved", "partial approval"),
            _t("partially_approved", "approved", "remaining part approved"),
            _t("under_review", "refused", "refused (from the cycle)"),
            _t("assembling", "withdrawn", "withdrawn"),
            _t("ready", "withdrawn", "withdrawn"),
            _t("submitted", "withdrawn", "withdrawn"),
            _t("under_review", "withdrawn", "withdrawn"),
            _t("remarks", "withdrawn", "withdrawn"),
        ],
        terminal=("approved", "refused", "withdrawn"),
    )
)

#: ``review_authority`` cycle state -> permit package state (rule: read, never typed).
CYCLE_TO_PERMIT: dict[str, str] = {
    "submitted": "submitted",
    "under_review": "under_review",
    "remarks_issued": "remarks",
    "responding": "remarks",
    "resubmitted": "under_review",
    "approved": "approved",
    "rejected": "refused",
    "withdrawn": "withdrawn",
}

#: ``review_authority`` cycle state -> report state while an external check runs.
CYCLE_TO_REPORT: dict[str, str] = {
    "submitted": "under_check",
    "under_review": "under_check",
    "remarks_issued": "remarks",
    "responding": "remarks",
    "resubmitted": "under_check",
    "approved": "accepted",
    "rejected": "rejected",
}

ALL_FSMS = (ROLE_FSM, APPROVAL_POINT_FSM, RELEASE_FSM, REVIEW_FSM, COMMENT_FSM, REPORT_FSM, PERMIT_FSM)


def permit_path(fsm: EntityFSM, current: str, target: str) -> list[str]:
    """Shortest chain of legal states from ``current`` to ``target`` (cycle sync may skip steps)."""
    if current == target:
        return []
    frontier: list[list[str]] = [[current]]
    seen = {current}
    while frontier:
        path = frontier.pop(0)
        for nxt in fsm.allowed_from(path[-1]):
            if nxt in seen:
                continue
            if nxt == target:
                return path[1:] + [nxt]
            seen.add(nxt)
            frontier.append(path + [nxt])
    return []


__all__ = [
    "ALL_FSMS",
    "APPROVAL_POINT_FSM",
    "COMMENT_FSM",
    "CYCLE_TO_PERMIT",
    "CYCLE_TO_REPORT",
    "PERMIT_FSM",
    "RELEASE_FSM",
    "REPORT_FSM",
    "REVIEW_FSM",
    "ROLE_FSM",
    "permit_path",
]
