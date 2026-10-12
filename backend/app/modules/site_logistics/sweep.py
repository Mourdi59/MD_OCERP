# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The periodic sweep of the dated logistics rules.

Three rules depend on the calendar or on another module and so cannot wait for
somebody to open a page: permits that expire or are about to (rule 7),
complaints past their response date (rule 18) and transports whose goods were
received (rule 19). The platform's process registry runs :func:`sweep_tick`
on an interval.

Every item gets its own session and transaction, so one row that fails does not
roll back the rows before it and does not stop the rows after it. A failure is
logged at warning with the item it belongs to and the sweep carries on. Dates
are the server's date on each site's clock, never a value from a request.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

PROCESS_ID = "site_logistics_sweep"
SWEEP_INTERVAL_S = 3600.0
SWEEP_INITIAL_DELAY_S = 120.0


async def _in_own_transaction(what: str, item: Any, work: Callable[[Any], Awaitable[Any]]) -> bool:
    """Run ``work(service)`` in a session of its own; commit on success, log and roll back on failure."""
    from app.database import async_session_factory
    from app.modules.site_logistics.plan_service import LogisticsPlanService

    async with async_session_factory() as session:
        try:
            changed = await work(LogisticsPlanService(session))
            await session.commit()
        except Exception:
            # One bad row must not stop the sweep; it is retried on the next tick.
            await session.rollback()
            logger.warning("site_logistics sweep: %s %s failed", what, item, exc_info=True)
            return False
        return bool(changed)


async def _items() -> dict[str, list[tuple[uuid.UUID, uuid.UUID]]]:
    """What there is to look at, read in one short session: ``(project_id, id)`` pairs per kind."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.modules.site_logistics.models import NeighbourIssue, Transport, TransportPermit

    async with async_session_factory() as session:
        permits = (
            await session.execute(
                select(TransportPermit.project_id, TransportPermit.id).where(TransportPermit.state == "granted")
            )
        ).all()
        complaints = (
            await session.execute(
                select(NeighbourIssue.project_id, NeighbourIssue.id).where(
                    NeighbourIssue.state != "closed", NeighbourIssue.overdue_notified_on.is_(None)
                )
            )
        ).all()
        receiving = (
            await session.execute(
                select(Transport.project_id).where(Transport.state == "in_transit", Transport.po_id.isnot(None))
            )
        ).all()
    return {
        "permit": [(p, i) for p, i in permits],
        "complaint": [(p, i) for p, i in complaints],
        "arrivals": sorted({(p, p) for (p,) in receiving}),
    }


async def sweep_tick() -> dict[str, int]:
    """One pass over every project. Returns what changed, for the log and for tests."""
    items = await _items()
    counts = {"permits": 0, "complaints": 0, "arrival_projects": 0}
    for project_id, permit_id in items["permit"]:
        if await _in_own_transaction(
            "permit", permit_id, lambda svc, p=project_id, i=permit_id: svc.sweep_permit(p, i)
        ):
            counts["permits"] += 1
    for project_id, complaint_id in items["complaint"]:
        if await _in_own_transaction(
            "complaint", complaint_id, lambda svc, p=project_id, i=complaint_id: svc.sweep_complaint(p, i)
        ):
            counts["complaints"] += 1
    for project_id, _same in items["arrivals"]:
        if await _in_own_transaction("arrivals of project", project_id, lambda svc, p=project_id: svc.sync_arrivals(p)):
            counts["arrival_projects"] += 1
    if any(counts.values()):
        logger.info("site_logistics sweep: %s", counts)
    return counts


async def _tick() -> None:
    await sweep_tick()


def register_sweep_process() -> None:
    """Declare the sweep with the platform's process registry (idempotent, by id)."""
    from app.core.processes import process_registry
    from app.core.processes.base import LoopProcess
    from app.core.processes.registry import ProcessSpec
    from app.core.processes.semantic import fast_startup

    process_registry.register(
        ProcessSpec(
            id=PROCESS_ID,
            factory=lambda: LoopProcess(interval_s=SWEEP_INTERVAL_S, tick=_tick, initial_delay_s=SWEEP_INITIAL_DELAY_S),
            modules=["site_logistics"],
            category="maintenance",
            estimated_ram_mb=1,
            env_override=lambda: False if fast_startup() else None,
            logger_names=[__name__],
        )
    )
