# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Engineering brief subscribers, after ``staffing/events.py``.

* ``project_governance.frame_document.state_changed`` with ``status = binding``: the frame document that
  carries the brief became binding; :meth:`EngineeringBriefService.mirror_binding` approves and freezes
  the submitted brief. A repeated event finds nothing in review and is a no-op.

Same constraints as the governance subscribers: an isolated session, PostgreSQL only (a second writer on
SQLite would deadlock the request). A failure is logged at warning and does not reach the publisher. A
missed binding event is not lost: the brief catches up the next time it is read
(``EngineeringBriefService.brief_view``).
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)


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
    """Mirror a binding frame document onto the brief it carries."""
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
            from app.modules.engineering_brief.service import EngineeringBriefService

            changed = await EngineeringBriefService(session).mirror_binding(_uuid(data.get("project_id")), document_id)
            await session.commit()
            return changed
    except Exception:
        logger.warning("engineering_brief: binding mirror failed for document %s", document_id, exc_info=True)
        return False


async def _on_frame_document(event: Event) -> None:
    await handle_frame_document(event.data or {})


def register_engineering_brief_subscribers() -> None:
    """Idempotently wire the governance subscriber of this module."""
    # No flag of our own: ``subscribe_once`` looks at the bus as it is, so a bus that was emptied or
    # restored gets the handler again on the next call.
    event_bus.subscribe_once("project_governance.frame_document.state_changed", _on_frame_document)
