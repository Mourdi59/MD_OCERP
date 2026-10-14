# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the project handbook: findings, and which action a chapter state allows.

Everything here takes plain values and returns plain values, so the service, the validation rules and the
tests share one implementation of every check.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

ERROR = "error"
WARNING = "warning"

#: A chapter that stays in review longer than this is reported; nobody is waiting for it otherwise.
REVIEW_OVERDUE = timedelta(days=14)

#: Reasons ``can`` flags carry; also message keys ``project_handbook.errors.<reason>``.
APPROVER_IS_SUBMITTER = "approver_is_submitter"
NOT_APPLICABLE = frozenset({"not_in_review", "not_approved", "not_editable_in_state"})


@dataclass(frozen=True)
class Finding:
    """One rule finding: a stable code (also the message key), the chapter it is about, a severity."""

    code: str
    ref: str
    severity: str = ERROR
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "ref": self.ref, "severity": self.severity, "detail": self.detail}


def capability(reason: str | None, state_reason: str | None) -> dict[str, Any]:
    """One ``can`` flag: ``allowed``, the ``reason`` when not, and whether the action ``applies`` at all."""
    return {"allowed": reason is None, "reason": reason, "applies": state_reason not in NOT_APPLICABLE}


def chapter_findings(chapter: dict[str, Any], *, now: datetime | None = None) -> list[Finding]:
    """The findings of one chapter dict ``{code, status, content, owner_id, required, sources, linked_rows, submitted_at}``."""
    code = chapter["code"]
    out: list[Finding] = []
    if not chapter.get("owner_id"):
        out.append(Finding("chapter_owner_missing", code))
    if not (chapter.get("content") or "").strip():
        out.append(Finding("chapter_empty", code, ERROR if chapter.get("required") else WARNING))
    if chapter.get("required") and chapter.get("status") != "approved" and chapter.get("approved_version") is None:
        out.append(Finding("required_chapter_open", code, WARNING))
    if chapter.get("sources") and chapter.get("linked_rows") == 0:
        out.append(Finding("linked_source_empty", code, WARNING))
    submitted = chapter.get("submitted_at")
    if chapter.get("status") == "in_review" and submitted is not None:
        current = now or datetime.now(UTC)
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=UTC)
        if current - submitted > REVIEW_OVERDUE:
            out.append(Finding("review_overdue", code, WARNING))
    return out


def handbook_findings(chapters: list[dict[str, Any]], *, now: datetime | None = None) -> list[Finding]:
    """The findings of the whole handbook."""
    if not chapters:
        return [Finding("no_chapters", "handbook")]
    out: list[Finding] = []
    for chapter in chapters:
        out += chapter_findings(chapter, now=now)
    return out


def submission_blockers(chapter: dict[str, Any]) -> list[Finding]:
    """What refuses submitting this chapter: no owner, or nothing written."""
    out: list[Finding] = []
    if not chapter.get("owner_id"):
        out.append(Finding("chapter_owner_missing", chapter["code"]))
    if not (chapter.get("content") or "").strip():
        out.append(Finding("chapter_empty", chapter["code"]))
    return out


def action_refusal(action: str, status: str, *, can_edit: bool, can_manage: bool = False) -> str | None:
    """Why ``action`` is refused in ``status``; ``None`` when it is allowed.

    Actions: ``edit``, ``submit``, ``return``, ``approve``. The right to do it is checked first, then the
    state; a state reason that makes the action not apply is one of ``NOT_APPLICABLE``.
    """
    if action in ("edit", "submit") and not can_edit:
        return "permission_required"
    if action in ("return", "approve") and not can_manage:
        return "approval_permission_required"
    if action == "edit":
        return None if status in ("draft", "revising", "approved") else "not_editable_in_state"
    if action == "submit":
        return None if status in ("draft", "revising") else "already_submitted"
    if action in ("return", "approve"):
        return None if status == "in_review" else "not_in_review"
    return "unknown_action"


def approval_refusal(*, four_eyes: bool, is_submitter: bool) -> str | None:
    """With four eyes on, the person who submitted a chapter does not approve it."""
    return APPROVER_IS_SUBMITTER if four_eyes and is_submitter else None
