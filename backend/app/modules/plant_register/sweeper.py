# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The periodic job of the plant register (SPEC 8.2 "slot expiry job").

The register moves without anyone writing to it: a conversion deadline passes,
an order date comes close, an order is received in procurement, an approval
route ends. One pass does four things, each unit of work in its own
transaction so one bad row never undoes or blocks the others:

* a held slot past ``convert_by_date`` expires and its owners are told (rule 13);
* an order date that is close or has passed is notified, once per person, item
  and kind per day (rule 7);
* every item whose state is read from an order, an owner-furnished item or a
  commissioning system reads it again (rule 11). Procurement publishes its
  events before its own commit, so the event handler can miss the change; this
  pass is what makes the reading eventually right;
* a submitted decision paper whose approval route already ended takes the
  route's verdict (the event that should have carried it was lost).

Runs as a registry process (``app.core.processes``), like every other sweeper
of the platform. A failing unit is logged at warning and the pass carries on.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)

PROCESS_ID = "plant_register_sweeper"
SWEEP_INTERVAL_SECONDS = 3600


def _factory(session_factory: Any) -> Any:
    if session_factory is not None:
        return session_factory
    from app.database import async_session_factory

    return async_session_factory


async def _unit(factory: Any, label: str, work: Callable[[Any], Awaitable[bool]]) -> bool:
    """Run one unit of work in its own transaction. False when it did nothing or failed."""
    try:
        async with factory() as session:
            from app.modules.plant_register.service import PlantService

            did = await work(PlantService(session))
            await session.commit()
            return bool(did)
    except Exception:
        logger.warning("plant_register sweep: %s failed", label, exc_info=True)
        return False


async def run_once(*, today: date | None = None, session_factory: Any = None) -> dict[str, int]:
    """One pass over every project that keeps a register. Returns what it did, for the log and the tests."""
    from app.modules.plant_register import calc
    from app.modules.plant_register.models import DecisionPaper, PlantItem, SlotReservation
    from app.modules.plant_register.repository import PlantRepository

    factory = _factory(session_factory)
    day = today or datetime.now(UTC).date()
    done = {"expired_slots": 0, "order_notices": 0, "synced_items": 0, "papers": 0}

    async with factory() as session:
        repo = PlantRepository(session)
        project_ids = await repo.project_ids_with_items()
        slot_ids = [(s.project_id, s.id) for s in await repo.held_slots_due(None, day)]
        paper_ids = await repo.submitted_paper_ids()
        await session.rollback()

    for project_id, slot_id in slot_ids:

        async def expire(svc: Any, project_id: uuid.UUID = project_id, slot_id: uuid.UUID = slot_id) -> bool:
            slot = await svc.repo.get_scoped(SlotReservation, project_id, slot_id, lock=True)
            return slot is not None and await svc.expire_slot(slot, today=day)

        done["expired_slots"] += await _unit(factory, f"slot {slot_id}", expire)

    for project_id in project_ids:
        async with factory() as session:
            from app.modules.plant_register.service import PlantService

            try:
                views = await PlantService(session).item_views(project_id, today=day)
            except Exception:
                logger.warning("plant_register sweep: project %s could not be read", project_id, exc_info=True)
                continue
            due = [v["id"] for v in views if v["order_status"] in ("overdue", "due_soon")]
            read = [
                v["id"]
                for v in views
                if calc.at_least(v["item"].status, "route_set") and v["item"].status != "handed_over"
            ]
            await session.rollback()

        for item_id in due:

            async def notify(svc: Any, project_id: uuid.UUID = project_id, item_id: uuid.UUID = item_id) -> bool:
                found = await svc.item_views(project_id, today=day, only=[item_id])
                # Counted when somebody was told now; an item that is still due but was told today is not a notice.
                return bool(found) and (await svc.notify_order_date_once(found[0]))[1]

            done["order_notices"] += await _unit(factory, f"order date of item {item_id}", notify)

        for item_id in read:

            async def sync(svc: Any, project_id: uuid.UUID = project_id, item_id: uuid.UUID = item_id) -> bool:
                item = await svc.repo.get_scoped(PlantItem, project_id, item_id, lock=True)
                if item is None:
                    return False
                before = item.status
                await svc._sync(item, None)
                return item.status != before

            done["synced_items"] += await _unit(factory, f"state of item {item_id}", sync)

    for paper_id in paper_ids:

        async def reconcile(svc: Any, paper_id: uuid.UUID = paper_id) -> bool:
            paper = await svc.session.get(DecisionPaper, paper_id, with_for_update=True)
            return paper is not None and await svc.reconcile_paper(paper)

        done["papers"] += await _unit(factory, f"paper {paper_id}", reconcile)

    if any(done.values()):
        logger.info("plant_register sweep: %s", done)
    return done


async def tick() -> None:
    await run_once()


def register_plant_sweeper() -> None:
    """Declare the sweeper as a registry process; startup boots it. Registering again replaces the spec."""
    from app.core.processes import process_registry
    from app.core.processes.base import LoopProcess
    from app.core.processes.registry import ProcessSpec
    from app.core.processes.semantic import fast_startup

    process_registry.register(
        ProcessSpec(
            id=PROCESS_ID,
            factory=lambda: LoopProcess(
                interval_s=SWEEP_INTERVAL_SECONDS, tick=tick, initial_delay_s=SWEEP_INTERVAL_SECONDS
            ),
            modules=["plant_register"],
            category="scheduler",
            start_mode="boot",
            default_enabled=True,
            legacy_enabled=True,
            estimated_ram_mb=1,
            env_override=lambda: False if fast_startup() else None,
            logger_names=[__name__],
        )
    )
