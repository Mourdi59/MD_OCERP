# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The commitment guard: one call a document module makes before it binds money.

A module that creates or increases a commitment (award, contract activation or
value change, PO approval or issue, change or variation approval, contingency
drawdown) calls::

    verdict = await commitment_guard.enforce(
        session, project_id=..., kind="purchase_order", document_id=po.id,
        new_amount=Decimal(...), currency="EUR", actor_id=user_id,
    )

and attaches ``verdict.as_dict()`` to its response when ``verdict.result ==
"warn"``. ``enforce`` raises a 409 with code ``commitment_not_released`` (or
``commitment_not_in_matrix``) when the project's matrix is set to ``block``.

A change that is not linked itself but adds to a document that is (a change
order or variation on a contract) passes ``parent_kind`` / ``parent_id``: its
``new_amount`` is then checked as an addition on top of what the parent's item
already commits. ``gross_amount`` is passed where a document knows both and the
schedule may count gross.

The same owner may also answer :func:`change_threshold`: the amount above which
a change needs more than the lowest approval tier. A module with its own fixed
"high value" constant asks it and keeps the constant when the answer is None
(no matrix on the project).

The module that owns the matrix registers the checker on startup. When it is
absent or disabled, nothing is registered and every check answers ``ok``: no
behaviour change for an install without the matrix. A checker that raises is
logged and answers ``ok`` too; the guard must never break a document module's
own write.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

RESULTS = ("ok", "warn", "block")


@dataclass(frozen=True)
class GuardVerdict:
    """The answer for one document: ``ok``, ``warn`` or ``block``, with coded reasons."""

    result: str = "ok"
    reasons: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    item_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"result": self.result, "reasons": list(self.reasons), "item_id": self.item_id}


Checker = Callable[..., Awaitable[GuardVerdict]]
_CHECKER: dict[str, Checker] = {}
ThresholdProvider = Callable[..., Awaitable["Decimal | None"]]
_THRESHOLD: dict[str, ThresholdProvider] = {}


def register_commitment_guard(checker: Checker) -> None:
    """Install the checker (idempotent; the last registration wins)."""
    _CHECKER["default"] = checker


def unregister_commitment_guard() -> None:
    """Remove the checker (tests, module disabled)."""
    _CHECKER.pop("default", None)


def register_change_threshold(provider: ThresholdProvider) -> None:
    """Install the change-threshold provider (idempotent; the last registration wins)."""
    _THRESHOLD["default"] = provider


def unregister_change_threshold() -> None:
    _THRESHOLD.pop("default", None)


async def change_threshold(session: Any, *, project_id: uuid.UUID, currency: str) -> Decimal | None:
    """The project's change threshold in ``currency``; None when there is no provider, no matrix or no rate."""
    provider = _THRESHOLD.get("default")
    if provider is None:
        return None
    try:
        async with session.begin_nested():
            return await provider(session, project_id=project_id, currency=currency)
    except Exception:
        logger.exception("change threshold failed for project %s; the module constant applies", project_id)
        return None


async def check(
    session: Any,
    *,
    project_id: uuid.UUID,
    kind: str,
    document_id: uuid.UUID | None,
    new_amount: Decimal,
    currency: str,
    actor_id: uuid.UUID | str | None = None,
    parent_kind: str | None = None,
    parent_id: uuid.UUID | None = None,
    gross_amount: Decimal | None = None,
) -> GuardVerdict:
    """Ask the registered checker; ``ok`` when there is none or it fails."""
    checker = _CHECKER.get("default")
    if checker is None:
        return GuardVerdict()
    try:
        async with session.begin_nested():
            return await checker(
                session,
                project_id=project_id,
                kind=kind,
                document_id=document_id,
                new_amount=new_amount,
                currency=currency,
                actor_id=actor_id,
                parent_kind=parent_kind,
                parent_id=parent_id,
                gross_amount=gross_amount,
            )
    except Exception:
        logger.exception("commitment guard failed for %s %s; treated as ok", kind, document_id)
        return GuardVerdict()


async def enforce(session: Any, **kwargs: Any) -> GuardVerdict:
    """:func:`check`, raising HTTP 409 on ``block``."""
    verdict = await check(session, **kwargs)
    if verdict.result == "block":
        from fastapi import HTTPException

        code = verdict.reasons[0]["code"] if verdict.reasons else "commitment_not_released"
        raise HTTPException(
            status_code=409,
            detail={"code": code, "message_key": f"commitment.errors.{code}", "guard": verdict.as_dict()},
        )
    return verdict
