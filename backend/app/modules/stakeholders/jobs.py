# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The daily stakeholders sweep as a registry process (SPEC rules 4, 6 and 18).

Review-due, plan-overdue and commitment-overdue notices are sent by
``StakeholderService.sweep``. Without this process they only went out when
somebody called the sweep route by hand.

One transaction per project: a project that fails is logged at warning and
skipped, and every other project still gets its notices.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

logger = logging.getLogger(__name__)

PROCESS_ID = "stakeholders_sweep"
DAY_S = 24 * 3600
# The first pass lands after the server reports ready, never inside the boot.
SETTLE_S = 120


async def sweep_all(session_factory: Callable[[], Any] | None = None) -> dict[str, int]:
    """Sweep every project that has stakeholder settings. Returns projects swept and failed."""
    from app.modules.stakeholders.models import StakeholderSettings
    from app.modules.stakeholders.service import StakeholderService

    if session_factory is None:
        from app.database import async_session_factory

        session_factory = async_session_factory
    async with session_factory() as session:
        project_ids: list[uuid.UUID] = list((await session.execute(select(StakeholderSettings.project_id))).scalars())
    today = datetime.now(UTC).date()
    result = {"swept": 0, "failed": 0}
    for project_id in project_ids:
        try:
            async with session_factory() as session:
                await StakeholderService(session).sweep(project_id, today=today)
                await session.commit()
            result["swept"] += 1
        except Exception:
            result["failed"] += 1
            logger.warning("stakeholders sweep failed for project %s", project_id, exc_info=True)
    return result


async def sweep_tick() -> None:
    result = await sweep_all()
    logger.info("stakeholders sweep: %d projects swept, %d failed", result["swept"], result["failed"])


def register_sweep_process() -> None:
    """Declare the daily sweep (registering an id again replaces its spec); the registry starts it at boot."""
    from app.core.processes import process_registry
    from app.core.processes.base import LoopProcess
    from app.core.processes.registry import ProcessSpec
    from app.core.processes.semantic import fast_startup

    process_registry.register(
        ProcessSpec(
            id=PROCESS_ID,
            factory=lambda: LoopProcess(interval_s=DAY_S, tick=sweep_tick, initial_delay_s=SETTLE_S),
            modules=["stakeholders"],
            category="scheduler",
            start_mode="boot",
            default_enabled=True,
            legacy_enabled=True,
            estimated_ram_mb=1,
            env_override=lambda: False if fast_startup() else None,
            logger_names=[__name__],
        )
    )
