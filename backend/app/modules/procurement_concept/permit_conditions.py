# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permit conditions seen as lot requirements (module 2 into module 3).

A condition that binds the works (everything that is not an administrative filing)
must reach the bidders: it goes into the requirements of every lot that is still to
be awarded. ``permits`` owns the conditions and is read through ``permits.public``;
nothing is copied. A condition in a closed state (discharged, waived, not triggered,
superseded) no longer binds a new lot.

When ``permits`` is not installed the answer is ``available: False``, never an empty list.
"""

from __future__ import annotations

import uuid
from typing import Any

# Topics that are filings between owner and authority; they do not bind a contractor.
OWNER_ONLY_TOPICS = ("admin",)
BINDING_STATES = ("open", "evidence_submitted", "discharge_applied", "breach")


def derive(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lot requirements from permit conditions; pure."""
    out: list[dict[str, Any]] = []
    for r in rows:
        if r["state"] not in BINDING_STATES:
            continue
        out.append(
            {
                "condition_id": r["id"],
                "permit_id": r["permit_id"],
                "permit_reference": r["permit_reference"],
                "number": r["number"],
                "requirement": r["text"],
                "trigger": r["trigger"],
                "due_date": r["due_date"],
                "topic": r["topic"],
                "responsible_party": r["responsible_party"],
                "evidence_required": r["evidence_required"],
                "for_tender_documents": r["topic"] not in OWNER_ONLY_TOPICS,
            }
        )
    return out


async def load(session: Any, project_id: uuid.UUID) -> dict[str, Any]:
    """``{available, items[], tender_count}``; ``items`` are the requirements every open lot inherits."""
    try:
        from app.modules.permits import public as permits_public
    except ImportError:
        return {"available": False, "reason": "permits_not_installed", "items": [], "tender_count": 0}
    items = derive(await permits_public.list_conditions(session, project_id, open_only=True))
    return {
        "available": True,
        "reason": "",
        "items": items,
        "tender_count": sum(1 for i in items if i["for_tender_documents"]),
    }
