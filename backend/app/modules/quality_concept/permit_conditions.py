# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permit conditions seen as quality requirements and checks (module 2 into module 10).

``permits`` owns the conditions. This module reads the consolidated list through
``permits.public.list_conditions`` and derives, per condition, a quality check
whose state follows the condition's own state. Nothing is copied or stored, so a
condition discharged in ``permits`` is proven here the moment it is discharged.

When ``permits`` is not installed the answer is ``available: False``, never an
empty list, which would read as "no conditions".
"""

from __future__ import annotations

import uuid
from typing import Any

# Condition state -> state of the derived quality check.
CHECK_STATE: dict[str, str] = {
    "open": "to_prove",
    "evidence_submitted": "in_verification",
    "discharge_applied": "in_verification",
    "breach": "failed",
    "discharged": "proven",
    "in_compliance": "proven",
    "waived": "not_required",
    "not_triggered": "not_required",
}
# A check in one of these states still blocks the start of construction when its trigger is ``before_start``.
UNPROVEN = ("to_prove", "in_verification", "failed")


def check_state(condition_state: str) -> str:
    return CHECK_STATE.get(condition_state, "to_prove")


def derive(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One quality requirement and check per permit condition; pure."""
    out: list[dict[str, Any]] = []
    for r in rows:
        state = check_state(r["state"])
        out.append(
            {
                "condition_id": r["id"],
                "permit_id": r["permit_id"],
                "permit_reference": r["permit_reference"],
                "permit_type_code": r["permit_type_code"],
                "number": r["number"],
                "requirement": r["text"],
                "evidence_required": r["evidence_required"],
                "trigger": r["trigger"],
                "due_date": r["due_date"],
                "topic": r["topic"],
                "responsible_party": r["responsible_party"],
                "owner_user_id": r["owner_user_id"],
                "condition_state": r["state"],
                "check_state": state,
                "blocks_start": r["trigger"] == "before_start" and state in UNPROVEN,
            }
        )
    return out


def summary(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(items), "proven": 0, "unproven": 0, "failed": 0, "blocks_start": 0}
    for i in items:
        counts["proven"] += i["check_state"] == "proven"
        counts["unproven"] += i["check_state"] in UNPROVEN
        counts["failed"] += i["check_state"] == "failed"
        counts["blocks_start"] += bool(i["blocks_start"])
    return counts


async def load(session: Any, project_id: uuid.UUID) -> dict[str, Any]:
    """``{available, items[], summary}`` for one project the caller already has access to."""
    try:
        from app.modules.permits import public as permits_public
    except ImportError:
        return {"available": False, "reason": "permits_not_installed", "items": [], "summary": summary([])}
    items = derive(await permits_public.list_conditions(session, project_id))
    return {"available": True, "reason": "", "items": items, "summary": summary(items)}
