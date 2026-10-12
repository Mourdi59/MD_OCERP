# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Container code check hook: CDE asks, a numbering module answers, neither imports the other.

``cde`` calls :func:`check_container_code` whenever a container is created or
its code or ISO parts change. A module that holds a numbering scheme for the
project (design management) registers ONE checker at startup. With no checker
registered, or a checker that says the project pins no scheme, nothing
changes: CDE keeps accepting what it accepted before.

A checker returns a list of violations (``{"code", "field", "value"}``); an
empty list or ``None`` means the code is acceptable. Any violation refuses the
write with 422 and every violation listed, so the client can show each failing
field at once.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, status

ContainerCodeChecker = Callable[[Any, uuid.UUID, str, dict[str, Any]], Awaitable[list[dict[str, Any]] | None]]

_CHECKERS: dict[str, ContainerCodeChecker] = {}


def register_container_code_checker(name: str, checker: ContainerCodeChecker) -> None:
    """Register (or replace, by name) a checker."""
    _CHECKERS[name] = checker


def unregister_container_code_checker(name: str) -> None:
    _CHECKERS.pop(name, None)


async def check_container_code(session: Any, project_id: uuid.UUID, code: str, parts: dict[str, Any]) -> None:
    """Refuse a container code a registered checker rejects; raise 422 with every violation."""
    violations: list[dict[str, Any]] = []
    for checker in list(_CHECKERS.values()):
        found = await checker(session, project_id, code, parts)
        if found:
            violations.extend(found)
    if violations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "numbering_invalid",
                "message_key": "design.errors.numbering_invalid",
                "message": f"Container code {code!r} does not match the project's numbering scheme",
                "violations": violations,
            },
        )


__all__ = [
    "ContainerCodeChecker",
    "check_container_code",
    "register_container_code_checker",
    "unregister_container_code_checker",
]
