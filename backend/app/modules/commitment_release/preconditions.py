# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Port for preconditions another module can answer (SPEC: a permit is a linked record, not a tick).

A release precondition of kind ``permit`` (or any kind registered here) that carries a ``ref_id``
is read from the module that owns that record instead of from a stored tick::

    register_precondition_reader("permit", permit_is_granted)

    async def permit_is_granted(session, project_id, ref_id) -> bool: ...

The reader must answer for records of ``project_id`` only and return False for anything else. While
no module registers a kind, a precondition of that kind stays a tick a person confirms.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

PreconditionReader = Callable[[Any, uuid.UUID, str], Awaitable[bool]]
_READERS: dict[str, PreconditionReader] = {}


def register_precondition_reader(kind: str, reader: PreconditionReader) -> None:
    """Let ``reader`` answer preconditions of ``kind`` (idempotent; the last registration wins)."""
    _READERS[kind] = reader


def unregister_precondition_reader(kind: str) -> None:
    _READERS.pop(kind, None)


def precondition_reader(kind: str) -> PreconditionReader | None:
    return _READERS.get(kind)
