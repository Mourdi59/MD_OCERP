# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Economics <-> governance events, after ``delivery_model/events.py``.

A frame document of the project changed state: the plan may now be approved by the gate that bound it.
The handler opens an isolated session, because the bus delivers after the publisher's commit.
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
    """Mirror a binding frame document onto the plan it carries."""
    if data.get("status") != "binding":
        return False
    project_id = _uuid(data.get("project_id"))
    if project_id is None:
        return False
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return False
    try:
        async with factory() as session:
            from app.modules.economics.service import EconomicsService

            changed = await EconomicsService(session).mirror_binding(project_id)
            await session.commit()
            return changed
    except Exception:
        logger.warning("economics: binding mirror failed for project %s", project_id, exc_info=True)
        return False


async def _on_frame_document(event: Event) -> None:
    await handle_frame_document(event.data or {})


def register_economics_subscribers() -> None:
    """Wire the governance subscriber of this module; safe to call again."""
    event_bus.subscribe_once("project_governance.frame_document.state_changed", _on_frame_document)
