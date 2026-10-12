# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""WBS tree check hook: ``projects`` stores the tree, a rules module answers, neither imports the other.

``projects`` calls :func:`check_wbs_tree` after every write path that does not
go through the design module's own WBS endpoints: node create and update on the
projects router, project duplication and restore from a backup. The check reads
the project's tree as flushed, so it judges the result, not the request.

``settings_project_id`` names the project whose settings decide the rules when
the written project has none yet (a fresh copy takes its source's). With no
checker registered nothing changes. Any violation refuses the write with 422
and every violation listed; the caller's transaction is rolled back by the
exception.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status

WbsTreeChecker = Callable[[Any, uuid.UUID, uuid.UUID | None], Awaitable[list[dict[str, Any]] | None]]

_CHECKERS: dict[str, WbsTreeChecker] = {}


def register_wbs_checker(name: str, checker: WbsTreeChecker) -> None:
    """Register (or replace, by name) a checker."""
    _CHECKERS[name] = checker


def unregister_wbs_checker(name: str) -> None:
    _CHECKERS.pop(name, None)


async def check_wbs_tree(session: Any, project_id: uuid.UUID, *, settings_project_id: uuid.UUID | None = None) -> None:
    """Refuse a WBS tree a registered checker rejects; raise 422 with every violation."""
    violations: list[dict[str, Any]] = []
    for checker in list(_CHECKERS.values()):
        found = await checker(session, project_id, settings_project_id)
        if found:
            violations.extend(found)
    if violations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "wbs_invalid",
                "message_key": "design.errors.wbs_invalid",
                "message": "The work breakdown structure breaks the project's WBS rules",
                "violations": violations,
            },
        )


__all__ = ["WbsTreeChecker", "check_wbs_tree", "register_wbs_checker", "unregister_wbs_checker"]
