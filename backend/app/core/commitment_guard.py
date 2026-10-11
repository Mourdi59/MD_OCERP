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


def register_commitment_guard(checker: Checker) -> None:
    """Install the checker (idempotent; the last registration wins)."""
    _CHECKER["default"] = checker


def unregister_commitment_guard() -> None:
    """Remove the checker (tests, module disabled)."""
    _CHECKER.pop("default", None)


async def check(
    session: Any,
    *,
    project_id: uuid.UUID,
    kind: str,
    document_id: uuid.UUID | None,
    new_amount: Decimal,
    currency: str,
    actor_id: uuid.UUID | str | None = None,
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
