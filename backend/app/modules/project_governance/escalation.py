# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The periodic escalation of gate conditions that passed their due date.

Run hourly as the registry process ``governance_escalation``
(``app.core.processes.builtin``). A condition reads as overdue on every screen
from the day after its due date without this sweep; what the sweep adds is the
stored status, the audit entry, the ``condition.overdue`` event and the
notification to the decider of the gate that set the condition.

Each project is escalated inside its own savepoint, so one project that fails
does not keep the others waiting for the next hour.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.modules.project_governance.service import GovernanceService, server_today

logger = logging.getLogger(__name__)


async def escalate_all(session: AsyncSession, *, today: date) -> int:
    """Escalate the late conditions of every project that has one.

    Args:
        session: Open session; the caller commits.
        today: The date conditions are judged against.

    Returns:
        The number of conditions escalated by this pass.
    """
    svc = GovernanceService(session)
    escalated = 0
    for project_id in await svc.repo.projects_with_late_conditions(today):
        try:
            async with session.begin_nested():
                escalated += len(await svc.escalate_overdue(project_id, today=today))
        except Exception:
            logger.exception("governance escalation failed for project %s", project_id)
    return escalated


async def run_once() -> int:
    """Open a session, run one pass on the server date, commit."""
    async with async_session_factory() as session:
        escalated = await escalate_all(session, today=server_today())
        await session.commit()
    if escalated:
        logger.info("governance escalation raised %d overdue condition(s)", escalated)
    return escalated
