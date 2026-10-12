# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design <-> approval-routes wiring and the CDE numbering hook.

Target kinds ``design_approval_point`` and ``design_release`` (decision 14).
A terminal outcome (approved, rejected or cancelled) reaches here and is
applied once, only to the instance the row started (rule 22: whoever the
route entitles decides; four-eyes is re-checked on the decider). A cancelled
route returns the row to its editable state. ``DesignService.catch_up_approvals``
applies the same outcome on read when this subscriber did not run.

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request),
fail-soft.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

_SUBSCRIBED_FLAG = "_design_management_approval_subscribers_registered"
CHECKER_NAME = "design_management.numbering"


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
    """Apply one terminal route outcome to the approval point or release it targets."""
    kind = data.get("target_kind")
    if kind not in ("design_approval_point", "design_release"):
        return
    target_id = _uuid(data.get("target_id"))
    if target_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.design_management.service import DesignService

            svc = DesignService(session)
            apply = svc.apply_approval_verdict if kind == "design_approval_point" else svc.apply_release_verdict
            await apply(target_id, _uuid(data.get("instance_id")), decision=decision, decided_by=data.get("decided_by"))
            await session.commit()
    except Exception:
        # Fail-soft towards the route (its decision is already committed), loud in the log:
        # the row stays waiting until the next list read catches it up.
        logger.warning("design: %s %s was not applied to %s", kind, decision, target_id, exc_info=True)


async def _on_completed(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="approved")


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="rejected")


async def _on_cancelled(event: Event) -> None:
    await handle_route_event(event.data or {}, decision="cancelled")


def register_design_subscribers() -> None:
    """Idempotently wire the approval-route subscribers of this module."""
    if getattr(event_bus, _SUBSCRIBED_FLAG, False):
        return
    event_bus.subscribe_once("approval_routes.instance.completed", _on_completed)
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
    event_bus.subscribe_once("approval_routes.instance.cancelled", _on_cancelled)
    setattr(event_bus, _SUBSCRIBED_FLAG, True)


async def numbering_checker(session: Any, project_id: uuid.UUID, code: str, parts: dict[str, Any]):
    from app.modules.design_management.service import DesignService

    return await DesignService(session).check_container_code(project_id, code, parts)


def register_numbering_hook() -> None:
    from app.core.cde_naming import register_container_code_checker
    from app.core.wbs_rules import register_wbs_checker

    register_container_code_checker(CHECKER_NAME, numbering_checker)
    register_wbs_checker(WBS_CHECKER_NAME, wbs_checker)


WBS_CHECKER_NAME = "design_management.wbs"


async def wbs_checker(session: Any, project_id: uuid.UUID):
    from app.modules.design_management.service import DesignService

    return await DesignService(session).wbs_tree_violations(project_id)
