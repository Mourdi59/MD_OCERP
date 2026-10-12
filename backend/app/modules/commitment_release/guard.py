# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The checker this module installs into :mod:`app.core.commitment_guard`.

Every ``warn`` and ``block`` leaves one audit row (entity ``commitment_guard``,
action ``guard_warn`` / ``guard_block``). A ``warn`` is written in the caller's
session, so it commits with the write it warned about. A ``block`` is written
in its own session and committed at once: the caller is about to roll back the
refused write, and the refusal must survive that rollback.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from app.core.commitment_guard import GuardVerdict

logger = logging.getLogger(__name__)

# Tests point this at their isolated database; production reads app.database.
session_factory: Any = None


def _factory() -> Any:
    if session_factory is not None:
        return session_factory
    from app.database import async_session_factory

    return async_session_factory


async def record_verdict(
    session: Any,
    out: dict[str, Any],
    *,
    kind: str,
    document_id: uuid.UUID | None,
    actor_id: Any,
    project_id: uuid.UUID,
) -> None:
    """Write the audit row of a ``warn`` (caller's session) or ``block`` (own, committed session)."""
    from app.core.audit_log import log_activity

    result = out["result"]
    if result == "ok":
        return
    kwargs = {
        "actor_id": None if actor_id is None else str(actor_id),
        "entity_type": "commitment_guard",
        "entity_id": None if document_id is None else str(document_id),
        "action": f"guard_{result}",
        "module": "commitment_release",
        "parent_entity_type": "project",
        "parent_entity_id": str(project_id),
        "metadata": {"kind": kind, "project_id": str(project_id), **out},
    }
    if result == "warn":
        await log_activity(session, **kwargs)
        return
    try:
        async with _factory()() as own:
            await log_activity(own, **kwargs)
            await own.commit()
    except Exception:
        # The refusal itself must still happen; a lost trail is logged, not raised.
        logger.exception("commitment guard: could not record the block of %s %s", kind, document_id)


async def check_document(
    session: Any,
    *,
    project_id: uuid.UUID,
    kind: str,
    document_id: uuid.UUID | None,
    new_amount: Decimal,
    currency: str,
    actor_id: Any = None,
    parent_kind: str | None = None,
    parent_id: uuid.UUID | None = None,
    gross_amount: Decimal | None = None,
) -> GuardVerdict:
    """``ok | warn | block`` for binding ``new_amount`` on a document, per the project's enforcement."""
    from app.modules.commitment_release.service import CommitmentService

    out = await CommitmentService(session).check_document(
        project_id,
        kind=kind,
        document_id=document_id,
        new_amount=new_amount,
        currency=currency,
        actor_id=actor_id,
        parent_kind=parent_kind,
        parent_id=parent_id,
        gross_amount=gross_amount,
    )
    await record_verdict(session, out, kind=kind, document_id=document_id, actor_id=actor_id, project_id=project_id)
    return GuardVerdict(result=out["result"], reasons=tuple(out["reasons"]), item_id=out.get("item_id"))


async def enforcement_of(session: Any, *, project_id: uuid.UUID) -> str | None:
    """What the project's matrix enforces; None when it has no matrix. Asked when a check failed."""
    from app.modules.commitment_release.repository import CommitmentRepository

    matrix = await CommitmentRepository(session).get_matrix(project_id)
    return None if matrix is None else str(matrix.enforcement)


async def change_threshold(session: Any, *, project_id: uuid.UUID, currency: str) -> Decimal | None:
    """SPEC rule 20: the most a change may be before it needs more than the schedule's lowest tier.

    In ``currency`` (the change's own). None when the project has no matrix, or the schedule
    currency has no rate to ``currency``: the caller then keeps its own constant.
    """
    from datetime import UTC, datetime

    from app.modules.commitment_release import evaluator as ev
    from app.modules.commitment_release.fx import FxRateMissing
    from app.modules.commitment_release.service import CommitmentService

    svc = CommitmentService(session)
    matrix = await svc.repo.get_matrix(project_id)
    if matrix is None:
        return None
    schedule = await svc.schedule_for(matrix)
    if "change" not in schedule.type_codes():
        return None
    ceiling = ev.lowest_tier_ceiling(schedule, "change")
    if not ceiling.is_finite() or ceiling == 0:
        return ceiling
    project = await svc._project(project_id)
    try:
        quote = await svc.quote(
            matrix, project, svc.schedule_currency(schedule, project), currency, datetime.now(UTC).date()
        )
    except FxRateMissing:
        logger.warning(
            "change threshold: no rate into %s for project %s; module constant applies", currency, project_id
        )
        return None
    return quote.apply(ceiling)
