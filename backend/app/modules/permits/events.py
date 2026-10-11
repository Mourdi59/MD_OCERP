# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits <-> approval routes, after ``commitment_release/events.py``.

The optional internal release before submission (lead decision k) runs as an
approval instance with ``target_kind = permit_application``. A rejected or
cancelled instance sends the application back to ``preparing``; an approved
one changes nothing by itself, it only lets the applicant file
(:meth:`PermitService._admit_submit` reads the instance). Acting only while the
application still waits on that very instance makes a late event a no-op.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only, fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

TARGET_KIND = "permit_application"
_SUBSCRIBED_FLAG = "_permits_subscribers_registered"


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


async def handle_route_event(data: dict, *, verdict: str, session_factory=None) -> None:
    """Apply one terminal route verdict to the application it targets."""
    if data.get("target_kind") != TARGET_KIND:
        return
    app_id = _uuid(data.get("target_id"))
    if app_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.permits.service import PermitService

            await PermitService(session).apply_route_verdict(
                app_id, instance_id=_uuid(data.get("instance_id")), verdict=verdict
            )
            await session.commit()
    except Exception:
        logger.debug("permits: route %s wiring failed for %s", verdict, app_id, exc_info=True)


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="rejected")


async def _on_cancelled(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="cancelled")


def register_permit_subscribers() -> None:
    """Idempotently wire the approval-route subscribers of this module."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
    event_bus.subscribe_once("approval_routes.instance.cancelled", _on_cancelled)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
