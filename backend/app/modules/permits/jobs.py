# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The scheduled permits sweep (SPEC rules 9 and 17).

Every hour, for every project with a permit roadmap: notify the owner and the
project lead of an overdue condition, escalate it to the area owner once the
project's escalation days have passed, and lapse a permit whose work did not
start within its validity or stayed interrupted beyond the catalogue period.

Each condition and each permit is handled in its own transaction, so one row
that fails does not undo or stop the others. A failure is logged at warning
with the project and the row and counted in the result; the next pass tries it
again. The platform's process registry calls :func:`run_sweep_once` through
``app.core.processes.builtin.permits_tick``.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _one(factory: Callable[[], Any], project_id: uuid.UUID, kind: str, row_id: uuid.UUID, today: date) -> str:
    """Sweep one row in its own transaction. Returns what happened: a counter name of the result."""
    from app.modules.permits.service import PermitService

    try:
        async with factory() as session:
            svc = PermitService(session)
            if kind == "permit":
                done = "lapsed" if await svc.sweep_permit(project_id, row_id, today) else "unchanged"
            else:
                out = await svc.sweep_condition(project_id, row_id, today)
                done = next((k for k in ("escalated", "notified", "unescalated") if out[k]), "unchanged")
            await session.commit()
            return done
    except Exception:
        logger.warning("permits sweep failed for %s %s of project %s", kind, row_id, project_id, exc_info=True)
        return "failed"


async def run_sweep_once(factory: Callable[[], Any] | None = None, today: date | None = None) -> dict[str, int]:
    """One pass over every project with a roadmap. ``factory`` opens a session (the application's by default)."""
    from app.modules.permits.models import PermitRoadmap
    from app.modules.permits.service import PermitService

    if factory is None:
        from app.database import async_session_factory

        factory = async_session_factory
    today = today or datetime.now(UTC).date()
    counts = {"projects": 0, "notified": 0, "escalated": 0, "unescalated": 0, "lapsed": 0, "unchanged": 0, "failed": 0}
    async with factory() as session:
        project_ids = list((await session.execute(select(PermitRoadmap.project_id))).scalars().all())
    for project_id in project_ids:
        try:
            async with factory() as session:
                targets = await PermitService(session).sweep_targets(project_id, today)
        except Exception:
            logger.warning("permits sweep could not read project %s", project_id, exc_info=True)
            counts["failed"] += 1
            continue
        counts["projects"] += 1
        for kind, name in (("condition", "conditions"), ("permit", "permits")):
            for row_id in targets[name]:
                counts[await _one(factory, project_id, kind, row_id, today)] += 1
    return counts
