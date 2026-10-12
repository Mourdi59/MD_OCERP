# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Staffing subscribers, after ``delivery_model/events.py``.

* ``project_governance.frame_document.state_changed`` with ``status = binding``:
  the m05 frame document that carries the plan became binding;
  :meth:`StaffingService.mirror_binding` approves and freezes the submitted
  plan. A repeated event finds nothing in review and is a no-op.
* ``credentials.expiry.alert``: a linked credential entered ``expiring_soon``
  or ``expired``; reminders go to rule 10 recipients only (position owners,
  the m05 area owner, the person). The body carries kind and date, never a
  number or a health detail.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request), fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

_SUBSCRIBED_FLAG = "_staffing_subscribers_registered"


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
    """Mirror a binding m05 frame document onto the plan it carries."""
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
            from app.modules.staffing.service import StaffingService

            changed = await StaffingService(session).mirror_binding(_uuid(data.get("project_id")), document_id)
            await session.commit()
            return changed
    except Exception:
        logger.debug("staffing: binding mirror failed for %s", document_id, exc_info=True)
        return False


async def handle_expiry_alert(data: dict, *, session_factory=None) -> int:
    """Send rule 10 reminders for a credential linked to a personnel document."""
    if _uuid(data.get("credential_id")) is None:
        return 0
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return 0
    try:
        async with factory() as session:
            from app.modules.staffing.service import StaffingService

            sent = await StaffingService(session).send_expiry_reminders(data)
            await session.commit()
            return sent
    except Exception:
        logger.debug("staffing: expiry reminder failed for %s", data.get("credential_id"), exc_info=True)
        return 0


async def _on_frame_document(event: Event) -> None:
    await handle_frame_document(event.data or {})


async def _on_expiry_alert(event: Event) -> None:
    await handle_expiry_alert(event.data or {})


def register_staffing_subscribers() -> None:
    """Idempotently wire the governance and credentials subscribers of this module."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("project_governance.frame_document.state_changed", _on_frame_document)
    event_bus.subscribe_once("credentials.expiry.alert", _on_expiry_alert)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
