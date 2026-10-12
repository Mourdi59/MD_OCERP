# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Released commitments as the release of an advance package: two hooks, never an import from here.

An advance package is one that has to go to the market before the gate that
releases procurement is decided. An act of that gate cannot release it: the
act only exists once the gate was decided, which is after the moment the
package is for. What binds money before the gate is a commitment the owner
released on its own authority (a reserved fabrication slot, a long lead
order), and the module that keeps the commitment matrix knows those.

That module registers two callables at startup; this module imports nothing
of it::

    register_commitment_checker(check)   # (session, project_id, item_id) -> CommitmentAnswer
    register_commitment_lister(items)    # (session, project_id) -> [CommitmentOption]

Both are scoped to one project: an item of another project is ``found=False``
and is never listed. With nothing registered the service refuses the kind
(``commitment_release_unavailable``) and the picker answers no rows with that
reason, instead of taking anybody's word that an item is released.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

KIND = "commitment"
UNAVAILABLE = "commitment_release_unavailable"


@dataclass(frozen=True)
class CommitmentAnswer:
    """What the commitment matrix says about one item.

    Attributes:
        found: The item belongs to the project asked about.
        released: It holds a release decided in favour (not planned, not requested, not rejected).
    """

    found: bool
    released: bool = False


@dataclass(frozen=True)
class CommitmentOption:
    """One commitment item an advance package may name, as the picker shows it.

    Attributes:
        id: The item.
        code: Its code in the matrix.
        title: Its title.
        status: The matrix's own status word, shown as is.
        released: Whether naming it releases the package today.
        released_on: Day of the release decision, if any.
        lead_time_days: The item's lead time when the matrix records one (a long lead item has one).
    """

    id: uuid.UUID
    code: str
    title: str
    status: str
    released: bool
    released_on: date | None = None
    lead_time_days: int | None = None


CommitmentChecker = Callable[[Any, uuid.UUID, uuid.UUID], Awaitable[CommitmentAnswer]]
CommitmentLister = Callable[[Any, uuid.UUID], Awaitable[list[CommitmentOption]]]

_HOOKS: dict[str, Any] = {}


def register_commitment_checker(fn: CommitmentChecker | None) -> None:
    """Install (or with ``None`` remove) the checker of one commitment item."""
    if fn is None:
        _HOOKS.pop("checker", None)
    else:
        _HOOKS["checker"] = fn


def register_commitment_lister(fn: CommitmentLister | None) -> None:
    """Install (or with ``None`` remove) the lister behind the release picker."""
    if fn is None:
        _HOOKS.pop("lister", None)
    else:
        _HOOKS["lister"] = fn


def commitment_checker() -> CommitmentChecker | None:
    return _HOOKS.get("checker")


def commitment_lister() -> CommitmentLister | None:
    return _HOOKS.get("lister")
