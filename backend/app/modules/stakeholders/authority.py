# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Money authority is module 2's: two hooks it registers, never an import from here (decision i).

``who_decides`` answers the role from this module's mandate matrix; when the
decision type carries a ``commitment_type`` and an amount is given, it asks the
registered authority evaluator for the tier and its approvers. Rule 10 asks the
registered release-item checker whether a commitment with a cost has a release
item and whether the project keeps a commitment matrix at all. With nothing
registered the answers say so (``authority_not_evaluated``) instead of
guessing a tier.

The commitment release module registers both at startup::

    register_authority_evaluator(evaluate)      # (session, project_id, commitment_type, amount, currency, today)
    register_release_item_checker(check)        # (session, project_id, release_item_id | None)
    register_release_item_lister(items)         # (session, project_id) -> [ReleaseItemOption]
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class AuthorityAnswer:
    """What module 2 says about an amount: the tier and who fills it, or why it cannot."""

    tier_code: str | None
    approver_user_ids: tuple[str, ...] = ()
    escalate_outside: bool = False
    schedule: str | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleaseItemAnswer:
    """``has_matrix``: the project keeps a commitment matrix; ``item_valid``: the given item is in it."""

    has_matrix: bool
    item_valid: bool
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseItemOption:
    """One release item a commitment may be linked to, as the picker shows it."""

    id: str
    code: str
    title: str


AuthorityEvaluator = Callable[[Any, uuid.UUID, str, Decimal, str, date], Awaitable[AuthorityAnswer]]
ReleaseItemChecker = Callable[[Any, uuid.UUID, uuid.UUID | None], Awaitable[ReleaseItemAnswer]]
ReleaseItemLister = Callable[[Any, uuid.UUID], Awaitable[list[ReleaseItemOption]]]

_HOOKS: dict[str, Any] = {}


def register_authority_evaluator(fn: AuthorityEvaluator | None) -> None:
    """Install (or with ``None`` remove) the tier evaluator."""
    if fn is None:
        _HOOKS.pop("authority", None)
    else:
        _HOOKS["authority"] = fn


def register_release_item_checker(fn: ReleaseItemChecker | None) -> None:
    """Install (or with ``None`` remove) the release item checker."""
    if fn is None:
        _HOOKS.pop("release_item", None)
    else:
        _HOOKS["release_item"] = fn


def register_release_item_lister(fn: ReleaseItemLister | None) -> None:
    """Install (or with ``None`` remove) the lister behind the release item picker."""
    if fn is None:
        _HOOKS.pop("release_items", None)
    else:
        _HOOKS["release_items"] = fn


def release_item_lister() -> ReleaseItemLister | None:
    return _HOOKS.get("release_items")


def authority_evaluator() -> AuthorityEvaluator | None:
    return _HOOKS.get("authority")


def release_item_checker() -> ReleaseItemChecker | None:
    return _HOOKS.get("release_item")
