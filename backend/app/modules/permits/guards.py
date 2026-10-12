# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The state and permission tests of every permits write, in one place and without a database.

Each write method of the service calls its guard before it changes anything,
and the ``can`` flags a record is served with are the very same guards run
dry (:func:`flag`). A button therefore follows the server: the reason it is
disabled is the error code the write would answer with.

A guard raises :class:`~app.modules.permits.errors.PermitError`. Raised through
:func:`not_applicable` the action makes no sense for the record as it stands
(a start notice on a permit already started): the flag says ``applies: False``
and the client leaves the action out. Raised plainly the action belongs to the
record but is refused for now (``applies: True``, ``allowed: False``).

What a guard cannot know before the body arrives (a date in the future, a
missing document, a link to another project) stays in the write.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from app.modules.permits.errors import PermitError, conflict, forbidden
from app.modules.permits.fsm import APPLICATION_FSM, CONDITION_FSM, PERMIT_FSM, USER_TARGETS

DECIDABLE: tuple[str, ...] = ("submitted", "validated", "under_review", "info_requested")
# The targets a user may move an application to (``fsm.USER_TARGETS``) in the order the work goes;
# ``decided`` comes only from a decision.
TARGET_ORDER: tuple[str, ...] = (
    "preparing",
    "internal_review",
    "submitted",
    "validated",
    "under_review",
    "info_requested",
    "withdrawn",
)
PERMIT_TARGETS: tuple[str, ...] = ("suspended", "in_force", "revoked", "expired", "lapsed")
CLOSED_APPLICATION: tuple[str, ...] = ("decided", "withdrawn")
CLOCK_NOT_RUNNING: tuple[str, ...] = ("planned", "preparing", "internal_review", "decided", "withdrawn")
CLOSED_FOR_EDIT: tuple[str, ...] = ("superseded", "waived")
CLOSED_FOR_EVIDENCE: tuple[str, ...] = ("superseded", "waived", "discharged")
EVIDENCE_ON_RECORD: tuple[str, ...] = ("discharged", "not_triggered", "waived", "superseded")
DISCHARGE_MODES: tuple[str, ...] = ("self_certified", "not_triggered", "waived_by_authority")
# What a gate reads of a condition: settled while it is open, by a holder of ``permits.manage``.
GATE_FIELDS: tuple[str, ...] = ("kind", "trigger", "requires_authority_approval", "gate_condition_id", "purpose")


@dataclass(frozen=True)
class Caller:
    """Who asks and what the router found them permitted to do. The service never sees a role."""

    actor_id: uuid.UUID | None
    edit: bool = False
    manage: bool = False
    verify: bool = False


def not_applicable(code: str, status_code: int = 409, detail: str | None = None) -> PermitError:
    """A refusal that means "this action is not for this record", not "not now"."""
    exc = PermitError(code, status_code, detail=detail)
    exc.applies = False  # type: ignore[attr-defined]
    return exc


def flag(*checks: Callable[[], Any]) -> dict[str, Any]:
    """Run the guards of one write dry: ``{allowed, applies, reason}`` with the code the write would refuse with.

    The checks come in the order the write makes them, the permission first. ``applies`` is
    a fact about the record and never about who asks, so every check runs: a "not for this
    record" from any of them wins, and a reader sees the same set of actions as an editor.
    Where the action does belong to the record the reason is the first refusal in order.
    """
    first: PermitError | None = None
    for check in checks:
        try:
            check()
        except PermitError as exc:
            if not getattr(exc, "applies", True):
                return refused(exc.code, applies=False)
            first = first or exc
    if first is not None:
        return refused(first.code)
    return {"allowed": True, "applies": True, "reason": None}


def refused(code: str, *, applies: bool = True) -> dict[str, Any]:
    return {"allowed": False, "applies": applies, "reason": code}


# ── permissions (what the route dependency enforces) ───────────────────────


def needs_edit(caller: Caller) -> None:
    if not caller.edit:
        raise forbidden("edit_required")


def needs_manage(caller: Caller) -> None:
    if not caller.manage:
        raise forbidden("manage_required")


def needs_verify(caller: Caller) -> None:
    if not caller.verify:
        raise forbidden("verify_required")


# ── requirements ───────────────────────────────────────────────────────────


def requirement_edit(req: Any, actor_id: uuid.UUID | None, can_manage: bool) -> None:
    if not can_manage and req.responsible_user_id != actor_id:
        raise forbidden("not_requirement_owner")


def requirement_delete(applications: list[Any]) -> None:
    if any(a.status not in ("planned", "withdrawn") for a in applications):
        raise conflict("requirement_has_applications")


# ── applications ───────────────────────────────────────────────────────────


def application_edit(app: Any) -> None:
    if app.status in CLOSED_APPLICATION:
        raise conflict("application_closed")


def application_clock(app: Any) -> None:
    if app.status in CLOSED_APPLICATION:
        # Decided or withdrawn: the authority's clock will not run again.
        raise not_applicable("clock_not_running")
    if app.status in CLOCK_NOT_RUNNING:
        raise conflict("clock_not_running")


def application_decide(app: Any) -> None:
    if app.status == "decided":
        raise not_applicable("already_decided")
    if app.status == "withdrawn":
        # Nothing is left for the authority to decide.
        raise not_applicable("application_not_decidable")
    if app.status not in DECIDABLE:
        raise conflict("application_not_decidable")


def application_transition(app: Any, target: str, internal_review: bool) -> None:
    """The shape of a user transition: a known target, a move the lifecycle has, the project's own route."""
    if target not in USER_TARGETS:
        raise PermitError("transition_not_allowed", 422)
    if app.status == target or app.status in CLOSED_APPLICATION:
        # Same-state and post-terminal moves write nothing.
        raise not_applicable("invalid_transition", detail=f"{app.status} -> {target}")
    if not APPLICATION_FSM.has_transition(app.status, target):
        raise not_applicable("invalid_transition", detail=f"{app.status} -> {target}")
    if target == "internal_review" and not internal_review:
        # The project does not release applications internally: the branch does not exist for it.
        raise not_applicable("internal_review_not_enabled")
    if target == "submitted" and internal_review and app.status == "preparing":
        raise not_applicable("internal_review_required")


# ── decisions ──────────────────────────────────────────────────────────────


def decision_current(decision: Any, newest: Any) -> None:
    if newest is None or newest.id != decision.id:
        raise not_applicable("decision_superseded")


def decision_complete_register(decision: Any, newest: Any) -> None:
    if newest is not None and newest.id != decision.id:
        raise not_applicable("decision_superseded")
    if not decision.conditions_pending:
        raise not_applicable("register_already_complete")


# ── permits ────────────────────────────────────────────────────────────────


def _permit_in_force(permit: Any) -> None:
    """A suspended permit can come back, so the action waits; any other state is final for it."""
    if permit.status == "suspended":
        raise conflict("permit_not_in_force")
    if permit.status != "in_force":
        raise not_applicable("permit_not_in_force")


def permit_start(permit: Any) -> None:
    if permit.start_notified_at is not None:
        raise not_applicable("start_already_notified")
    _permit_in_force(permit)


def permit_interruption(permit: Any, resumed: bool) -> None:
    _permit_in_force(permit)
    if permit.start_notified_at is None:
        # Work that has not started cannot be interrupted or resumed.
        raise not_applicable("work_not_started")
    if resumed and permit.paused_since is None:
        raise not_applicable("work_not_interrupted")
    if not resumed and permit.paused_since is not None:
        raise not_applicable("work_already_interrupted")


def permit_transition(permit: Any, target: str) -> None:
    if target not in PERMIT_TARGETS:
        raise PermitError("transition_not_allowed", 422)
    if target == "in_force" and permit.status == "lapsed":
        raise PermitError("lapsed_needs_extension_decision", 422)
    if not PERMIT_FSM.has_transition(permit.status, target):
        raise not_applicable("invalid_transition", detail=f"{permit.status} -> {target}")


# ── conditions ─────────────────────────────────────────────────────────────


def condition_owned(c: Any, actor_id: uuid.UUID | None, can_manage: bool) -> None:
    if not can_manage and c.owner_user_id not in (None, actor_id):
        raise forbidden("not_condition_owner")


def condition_edit(c: Any) -> None:
    if c.status in CLOSED_FOR_EDIT:
        raise not_applicable("condition_closed")


def condition_frozen(c: Any, fields: Iterable[str]) -> None:
    """What a gate reads and who the owner is are settled while the condition is open."""
    names = sorted(fields)
    if names and c.status != "open":
        raise conflict("condition_field_frozen", detail=",".join(names))


def condition_assign(c: Any) -> None:
    condition_edit(c)
    condition_frozen(c, ("owner_user_id",))


def condition_gate_fields(c: Any) -> None:
    condition_edit(c)
    condition_frozen(c, GATE_FIELDS)


def condition_add_evidence(c: Any) -> None:
    if c.status in CLOSED_FOR_EVIDENCE:
        raise not_applicable("condition_closed")


def condition_remove_evidence(c: Any) -> None:
    if c.status in EVIDENCE_ON_RECORD:
        # What a discharge relied on stays on record.
        raise not_applicable("condition_closed")


def condition_submit_evidence(c: Any, evidence_count: int) -> None:
    if not c.confirmed:
        raise conflict("condition_not_confirmed")
    if not CONDITION_FSM.has_transition(c.status, "evidence_submitted"):
        raise not_applicable("invalid_transition", detail=f"{c.status} -> evidence_submitted")
    if evidence_count == 0:
        raise PermitError("evidence_required", 422)


def condition_ongoing(c: Any, target: str) -> None:
    if c.trigger != "ongoing":
        raise not_applicable("condition_not_ongoing", 422)
    if not CONDITION_FSM.has_transition(c.status, target):
        raise not_applicable("invalid_transition", detail=f"{c.status} -> {target}")


def condition_confirm(c: Any) -> None:
    if c.confirmed:
        raise not_applicable("condition_already_confirmed")


def condition_link_requirement(c: Any) -> None:
    """Rule 23: a condition carries at most one tracked limit."""
    if c.requirement_id is not None:
        raise not_applicable("condition_already_linked")


def condition_discharge(
    c: Any, mode: str, actor_id: uuid.UUID | None, involved: Iterable[Any], *, has_document: bool
) -> str:
    """Every rule of a manual discharge (rule 13, always four-eyes); returns the state it leads to.

    ``involved`` is everyone who cannot be the second pair of eyes: the owner, whoever
    submitted the evidence and whoever added a piece of it.
    """
    if not c.confirmed:
        raise conflict("condition_not_confirmed")
    # A condition that is settled has no discharge left; one still on its way can get there.
    no_path = not_applicable if c.status in EVIDENCE_ON_RECORD else conflict
    if mode not in DISCHARGE_MODES:
        # authority_discharged / deemed_discharged come only from a decided discharge application.
        raise PermitError("discharge_needs_application", 422)
    if mode == "self_certified":
        if c.requires_authority_approval:
            # Only the authority discharges this one: self certification is not a way for it.
            raise not_applicable("authority_discharge_required", 422)
        if c.owner_user_id is None:
            raise PermitError("condition_needs_owner", 422)
        if c.status != "evidence_submitted":
            raise no_path("evidence_not_submitted")
        target = "discharged"
    else:
        target = "not_triggered" if mode == "not_triggered" else "waived"
        if not CONDITION_FSM.has_transition(c.status, target):
            raise no_path("invalid_transition", detail=f"{c.status} -> {target}")
        if mode == "waived_by_authority" and not has_document:
            raise PermitError("waiver_needs_document", 422)
        # "The trigger never occurred" releases a suspensive condition, or one only the
        # authority may discharge, on one person's word. That word needs a document behind it.
        strict = c.kind == "suspensive" or c.requires_authority_approval
        if mode == "not_triggered" and strict and not has_document:
            raise PermitError("not_triggered_needs_document", 422)
    if c.owner_user_id == actor_id:
        raise forbidden("verifier_is_owner")
    if actor_id in set(involved):
        raise forbidden("verifier_is_involved")
    return target


# ── the frame document and the notice ──────────────────────────────────────


def frame_document(doc: Any) -> None:
    """The governance document hosting permits can take a new revision."""
    if doc is None:
        raise PermitError("frame_document_not_found", 404)
    if doc.container_id is None:
        raise conflict("frame_document_without_container")
    if doc.read_only:
        raise conflict("frame_document_read_only")
