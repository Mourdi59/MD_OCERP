# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plant register <-> approval routes and procurement wiring.

* ``plant_decision_paper``: completion of the paper's approval route approves
  the paper and freezes its snapshot; a rejection rejects it; a cancelled route
  returns it to draft. Acts only on the instance the paper started.
* ``procurement``: a purchase order that an item links moved; the item's
  ``ordered`` / ``delivered`` state is read again (rule 11), forward or back.
  The names are the ones procurement really publishes
  (``procurement.events.PUBLISHED_EVENTS``): a goods receipt is
  ``procurement.gr.confirmed`` (it carries ``po_id``), there is no
  ``po.received`` or ``po.completed`` event.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request),
fail-soft. Procurement publishes detached, before its request commits, so a
handler can read the order's previous status and do nothing. Nothing here
retries: the periodic job (``sweeper``) reads every linked source again and
closes that gap, and a failure is logged at warning so it is seen.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

TARGET_KIND = "plant_decision_paper"
# Every procurement event after which a linked order may support a different item state.
PO_EVENTS = (
    "procurement.po.issued",
    "procurement.po.updated",
    "procurement.po.cancelled",
    "procurement.po.reverted",
    "procurement.po.deleted",
    "procurement.gr.confirmed",
)
ROUTE_EVENTS = {
    "approval_routes.instance.completed": "approved",
    "approval_routes.instance.rejected": "rejected",
    "approval_routes.instance.cancelled": "cancelled",
}


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
        logger.warning("plant_register: approval %s wiring failed for %s", decision, target_id, exc_info=True)


async def handle_po_event(data: dict, *, session_factory=None) -> None:
    """Re-read the state of every item that links this purchase order."""
    po_id = _uuid(data.get("po_id"))
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
        logger.warning("plant_register: purchase order sync failed for %s", po_id, exc_info=True)


def _on_route(decision: str):
    async def handler(event: Event) -> None:
        await handle_route_event(event.data or {}, decision=decision)

    return handler


async def _on_po(event: Event) -> None:
    await handle_po_event(event.data or {})


_ROUTE_HANDLERS = {name: _on_route(decision) for name, decision in ROUTE_EVENTS.items()}


def register_plant_subscribers() -> None:
    """Wire the subscribers of this module; safe to call again.

    ``subscribe_once`` is what makes a second call harmless. A flag kept beside
    the bus would outlive the handlers whenever the bus is emptied, and the
    module would then never hear an approval or a purchase order event again.
    """
    for name, handler in _ROUTE_HANDLERS.items():
        event_bus.subscribe_once(name, handler)
    for name in PO_EVENTS:
        event_bus.subscribe_once(name, _on_po)
