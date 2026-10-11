# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plant register <-> approval routes and procurement wiring.

* ``plant_decision_paper``: completion of the paper's approval route approves
  the paper and freezes its snapshot; a rejection rejects it. Acts only on the
  instance the paper started.
* ``procurement.po.*``: a purchase order that an item links moved; the item's
  ``ordered`` / ``delivered`` state is read again (rule 11).

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request),
fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

TARGET_KIND = "plant_decision_paper"
_SUBSCRIBED_FLAG = "_plant_register_subscribers_registered"
PO_EVENTS = ("procurement.po.issued", "procurement.po.updated", "procurement.po.received", "procurement.po.completed")


async def _can_open_isolated_session() -> bool:
    try:
        async with async_session_factory() as probe:
            dialect = getattr(getattr(probe.get_bind(), "dialect", None), "name", "") or ""
        return dialect == "postgresql"
    except Exception:
        return False


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def handle_route_event(data: dict, *, decision: str, session_factory=None) -> None:
    """Apply one terminal route verdict to the decision paper it targets."""
    if data.get("target_kind") != TARGET_KIND:
        return
    target_id = _uuid(data.get("target_id"))
    if target_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.plant_register.service import PlantService

            await PlantService(session).apply_paper_verdict(
                target_id, _uuid(data.get("instance_id")), decision=decision
            )
            await session.commit()
    except Exception:
        logger.debug("plant_register: approval %s wiring failed for %s", decision, target_id, exc_info=True)


async def handle_po_event(data: dict, *, session_factory=None) -> None:
    """Re-read the state of every item that links this purchase order."""
    po_id = next((_uuid(data.get(k)) for k in ("po_id", "purchase_order_id", "id") if data.get(k)), None)
    if po_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.plant_register.service import PlantService

            svc = PlantService(session)
            for item in await svc.repo.items_by_purchase_order(po_id):
                await svc.sync_item_state(item.project_id, item.id, actor_id=None)
            await session.commit()
    except Exception:
        logger.debug("plant_register: purchase order sync failed for %s", po_id, exc_info=True)


async def _on_completed(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="approved")


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="rejected")


async def _on_po(event: Event) -> None:
    await handle_po_event(event.data or {})


def register_plant_subscribers() -> None:
    """Idempotently wire the subscribers of this module."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("approval_routes.instance.completed", _on_completed)
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
    for name in PO_EVENTS:
        event_bus.subscribe_once(name, _on_po)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
