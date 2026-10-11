# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Delivery model <-> governance and risk register events, after ``commitment_release/events.py``.

* ``project_governance.frame_document.state_changed`` with ``status = binding``:
  the frame document that carries the delivery decision became binding at a
  gate or through an approved change request.
  :meth:`DeliveryModelService.mirror_binding` locks the model and approves the
  proposed decision; a repeated event finds nothing proposed and is a no-op.
* ``risk.risk.deleted``: allocations of that project linking the risk drop the
  link and are flagged ``link_missing`` (SPEC rule 13); nothing is recreated.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request), fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

_SUBSCRIBED_FLAG = "_delivery_model_subscribers_registered"


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


async def handle_frame_document(data: dict, *, session_factory=None) -> bool:
    """Mirror a binding frame document onto the delivery decision it carries."""
    if data.get("status") != "binding":
        return False
    document_id = _uuid(data.get("document_id"))
    if document_id is None:
        return False
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return False
    try:
        async with factory() as session:
            from app.modules.delivery_model.service import DeliveryModelService

            changed = await DeliveryModelService(session).mirror_binding(_uuid(data.get("project_id")), document_id)
            await session.commit()
            return changed
    except Exception:
        logger.debug("delivery_model: binding mirror failed for %s", document_id, exc_info=True)
        return False


async def handle_risk_deleted(data: dict, *, session_factory=None) -> int:
    """Flag the allocations of the deleted risk's project that linked it."""
    project_id = _uuid(data.get("project_id"))
    risk_id = data.get("risk_id")
    if project_id is None or not risk_id:
        return 0
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return 0
    try:
        async with factory() as session:
            from app.modules.delivery_model.service import DeliveryModelService

            n = await DeliveryModelService(session).risk_deleted(project_id, str(risk_id))
            await session.commit()
            return n
    except Exception:
        logger.debug("delivery_model: risk link flag failed for %s", risk_id, exc_info=True)
        return 0


async def _on_frame_document(event: Event) -> None:
    await handle_frame_document(event.data or {})


async def _on_risk_deleted(event: Event) -> None:
    await handle_risk_deleted(event.data or {})


def register_delivery_model_subscribers() -> None:
    """Idempotently wire the governance and risk subscribers of this module."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("project_governance.frame_document.state_changed", _on_frame_document)
    event_bus.subscribe_once("risk.risk.deleted", _on_risk_deleted)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
