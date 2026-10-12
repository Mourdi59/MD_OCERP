# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The periodic pass of the commitment matrix, run by the platform's process registry.

Two things no request does on its own: documents an award drafted are linked
to the item that holds the award (the drafts publish no event of their own),
and an item whose decision date has passed unreleased is escalated to its
owner and the holders of its tier (SPEC rule 8), once per date.

One transaction per project for the links and one per item for an escalation,
so one row that fails never undoes another. A failure is logged at warning and
the pass goes on; the next pass tries again.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 3600
PROCESS_NAME = "commitment_release_sweeper"


async def sweep_once(session_factory: Any = None, *, today: date | None = None) -> dict[str, int]:
    """One pass over every project that has a matrix. Returns what it did."""
    from app.modules.commitment_release.models import CommitmentMatrix
    from app.modules.commitment_release.service import CommitmentService

    if session_factory is None:
        from app.database import async_session_factory as session_factory
    day = today or datetime.now(UTC).date()
    done = {"projects": 0, "links": 0, "escalations": 0, "failures": 0}
    async with session_factory() as session:
        project_ids = list((await session.execute(select(CommitmentMatrix.project_id))).scalars().all())
    for project_id in project_ids:
        done["projects"] += 1
        overdue: list[Any] = []
        try:
            async with session_factory() as session:
                svc = CommitmentService(session)
                done["links"] += await svc.adopt_award_drafts(project_id)
                await session.commit()
                overdue = await svc.overdue_items(project_id, today=day)
        except Exception:
            done["failures"] += 1
            logger.warning("commitment sweep: project %s failed", project_id, exc_info=True)
        for item_id, due in overdue:
            try:
                async with session_factory() as session:
                    if await CommitmentService(session).escalate_overdue(project_id, item_id, today=day, due=due):
                        done["escalations"] += 1
                    await session.commit()
            except Exception:
                done["failures"] += 1
                logger.warning("commitment sweep: item %s of project %s failed", item_id, project_id, exc_info=True)
    return done


def register_commitment_sweeper(registry: Any) -> None:
    """Declare the sweeper in the process registry (called from the module's startup)."""
    from app.core.processes.builtin import _loop, _spec

    async def tick() -> None:
        await sweep_once()

    registry.register(
        _spec(
            PROCESS_NAME,
            _loop(SWEEP_INTERVAL_SECONDS, tick, SWEEP_INTERVAL_SECONDS),
            ["commitment_release"],
            category="maintenance",
            logger_names=[__name__],
        )
    )
