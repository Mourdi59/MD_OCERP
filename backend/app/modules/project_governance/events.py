# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Governance <-> approval-routes wiring, after ``submittals/approval_subscribers.py``.

Two target kinds belong to this module:

* ``phase_gate``: the route of a gate review. A gate is decided through
  ``GovernanceService.decide``, which closes the instance itself. The only
  route verdict that reaches here on its own is a rejection taken in the
  approval screen, and it sends the review back to preparation. The handler
  locks the gate and acts only while the gate is still in review on that very
  instance, so the rejection a stop or recycle decision itself fires (published
  while the deciding transaction may still be open) is a no-op once the lock
  is released.
* ``frame_change``: the route of a change request on a binding frame document.
  Completion makes the proposed revision binding, rejection closes the request.

Same constraints as the submittal subscribers: an isolated session, PostgreSQL
only (a second writer on SQLite would deadlock the request), fail-soft.
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


async def handle_route_event(data: dict, *, decision: str, session_factory=None) -> None:
    """Apply one terminal route verdict to the governance row it targets."""
    kind = data.get("target_kind")
    if kind not in ("phase_gate", "frame_change"):
        return
    target_id = _uuid(data.get("target_id"))
    instance_id = _uuid(data.get("instance_id"))
    if target_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.project_governance.service import GovernanceService

            svc = GovernanceService(session)
            if kind == "phase_gate":
                if decision == "rejected" and instance_id is not None:
                    await svc.apply_gate_route_rejection(target_id, instance_id)
            else:
                await svc.apply_change_decision(target_id, decision=decision, decided_by=data.get("decided_by"))
            await session.commit()
    except Exception:
        logger.debug("governance: approval %s wiring failed for %s %s", decision, kind, target_id, exc_info=True)


async def _on_completed(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="approved")


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="rejected")


def register_governance_subscribers() -> None:
    """Wire the approval-route subscribers of this module; safe to call again.

    No "already registered" flag is kept: the bus is emptied when an app is
    restarted inside one process, a flag would outlive that, and the module
    would never hear a route verdict again. ``subscribe_once`` already makes a
    repeated call bind nothing twice.
    """
    event_bus.subscribe_once("approval_routes.instance.completed", _on_completed)
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
