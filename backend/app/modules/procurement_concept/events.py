# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Execution read-back (SPEC rule 16): the bidding stack moves award packages, never a person.

* ``bid_management.package.published`` -> ``in_tender``
* ``bid_management.package.awarded``   -> ``awarded``
* ``rfq.awarded``                      -> ``awarded``

The award package is found through the execution link on module 3's
ContractPackage (``link_kind``, ``link_id``), never through the vehicle's own
status: ``publish_detached`` may deliver before the publishing transaction
commits. :meth:`ProcurementConceptService.read_back` locks the row and only
moves forward, so a repeated or late event is a no-op.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request), fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

_SUBSCRIBED_FLAG = "_procurement_concept_subscribers_registered"

# event name -> (link kind, payload key of the vehicle id, target state)
READ_BACK_EVENTS: dict[str, tuple[str, str, str]] = {
    "bid_management.package.published": ("bid_package", "package_id", "in_tender"),
    "bid_management.package.awarded": ("bid_package", "package_id", "awarded"),
    "rfq.awarded": ("rfq", "rfq_id", "awarded"),
}


async def _can_open_isolated_session() -> bool:
    try:
        async with async_session_factory() as probe:
            dialect = getattr(getattr(probe.get_bind(), "dialect", None), "name", "") or ""
        return dialect == "postgresql"
    except Exception:
        return False


async def handle_read_back(name: str, data: dict, *, session_factory=None) -> str | None:
    """Apply one execution event; returns the package state afterwards (``None`` = not ours)."""
    spec = READ_BACK_EVENTS.get(name)
    if spec is None:
        return None
    link_kind, key, target = spec
    try:
        vehicle_id = uuid.UUID(str(data.get(key)))
    except (ValueError, TypeError):
        return None
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return None
    try:
        async with factory() as session:
            from app.modules.procurement_concept.service import ProcurementConceptService

            row = await ProcurementConceptService(session).read_back(link_kind, vehicle_id, target)
            await session.commit()
            return row.state if row is not None else None
    except Exception:
        logger.debug("procurement_concept: read-back of %s failed for %s", name, vehicle_id, exc_info=True)
        return None


async def _on_event(event: Event) -> None:
    await handle_read_back(event.name, event.data or {})


def register_procurement_concept_subscribers() -> None:
    """Idempotently wire the read-back subscribers."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    for name in READ_BACK_EVENTS:
        event_bus.subscribe_once(name, _on_event)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
