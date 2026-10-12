# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Stakeholders subscribers: approval verdicts on commitments and plan triggers.

* ``approval_routes.instance.completed|rejected|cancelled`` with target kind
  ``stakeholder_commitment``: the pending agree or withdraw of a commitment is
  applied (approved) or dropped (anything else), rule 10.
* ``project_governance.gate.submitted``: plan items with ``trigger_kind: gate``
  (all gates, or the one named in ``trigger_ref``) become due today, rule 6.
* The names in ``service.EVENT_TRIGGERS``: plan items with
  ``trigger_kind: event`` listening to that name become due today.

Same constraints as module 1's subscribers: an isolated session, PostgreSQL
only (a second writer on SQLite would deadlock the request), fail-soft.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

TARGET_KIND = "stakeholder_commitment"
GATE_SUBMITTED = "project_governance.gate.submitted"
_SUBSCRIBED_FLAG = "_stakeholders_subscribers_registered"


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


async def handle_route_event(data: dict, *, verdict: str, session_factory=None) -> bool:
    """Apply one terminal route verdict to the commitment whose approval it was."""
    if data.get("target_kind") != TARGET_KIND:
        return False
    instance_id = _uuid(data.get("instance_id"))
    if instance_id is None:
        return False
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return False
    try:
        async with factory() as session:
            from app.modules.stakeholders.service import StakeholderService

            done = await StakeholderService(session).apply_route_verdict(
                instance_id, verdict=verdict, decided_by=_uuid(data.get("decided_by"))
            )
            await session.commit()
            return done
    except Exception:
        logger.debug("stakeholders: route %s wiring failed for %s", verdict, instance_id, exc_info=True)
        return False


async def handle_trigger(name: str, data: dict, *, session_factory=None) -> int:
    """Fire the plan triggers of one project for a gate submission or a listened event."""
    from app.modules.stakeholders.service import EVENT_TRIGGERS

    project_id = _uuid(data.get("project_id"))
    if project_id is None or (name != GATE_SUBMITTED and name not in EVENT_TRIGGERS):
        return 0
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return 0
    try:
        async with factory() as session:
            from app.modules.stakeholders.service import StakeholderService

            svc = StakeholderService(session)
            if await svc.get_settings(project_id) is None:
                return 0
            today = datetime.now(UTC).date()
            if name == GATE_SUBMITTED:
                from app.modules.project_governance.models import GovernanceGate

                gate = await session.get(GovernanceGate, _uuid(data.get("gate_id")) or uuid.uuid4())
                fired = await svc.fire_trigger(project_id, "gate", gate.code if gate else "", on=today)
            else:
                fired = await svc.fire_trigger(project_id, "event", name, on=today)
            await session.commit()
            return fired
    except Exception:
        logger.debug("stakeholders: trigger %s failed for %s", name, project_id, exc_info=True)
        return 0


async def _on_completed(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="approved")


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="rejected")


async def _on_cancelled(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="cancelled")


async def _on_trigger(event: Event) -> None:
    await handle_trigger(event.name, event.data or {})


def register_stakeholder_subscribers() -> None:
    """Idempotently wire the subscribers of this module."""
    from app.modules.stakeholders.service import EVENT_TRIGGERS

    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("approval_routes.instance.completed", _on_completed)
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
    event_bus.subscribe_once("approval_routes.instance.cancelled", _on_cancelled)
    for name in (GATE_SUBMITTED, *EVENT_TRIGGERS):
        event_bus.subscribe_once(name, _on_trigger)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)
