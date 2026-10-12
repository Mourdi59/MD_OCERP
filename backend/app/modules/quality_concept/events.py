# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Mirrors of other modules' acts into the quality concept.

* ``cc.gate.released`` with ``attached_kind=cx_stage``: the stage progress row
  the gate was created for becomes ``released`` (rule 10).
* ``cc.handover.issued``: acceptance units pointing at the act become
  ``accepted`` or ``accepted_with_reservations`` (rule 15).
* ``project_governance.frame_document.state_changed`` to ``binding`` for the
  concept's frame document: the concept becomes approved and binding (rule 22).

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request),
fail-soft, idempotent. The ``apply_*`` service methods take a session and are
what the PG tests call directly.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

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


async def _run(label: str, work: Callable[[Any], Awaitable[Any]], session_factory: Any = None) -> None:
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            await work(session)
            await session.commit()
    except Exception:
        logger.warning("quality_concept: %s mirror failed", label, exc_info=True)


async def handle_gate_released(data: dict, *, session_factory: Any = None) -> None:
    if data.get("attached_kind") != "cx_stage":
        return
    gate_id = _uuid(data.get("gate_id"))
    if gate_id is None:
        return
    from app.modules.quality_concept.service import QualityConceptService

    await _run("gate", lambda s: QualityConceptService(s).apply_gate_released(gate_id), session_factory)


async def handle_handover_issued(data: dict, *, session_factory: Any = None) -> None:
    package_id = _uuid(data.get("package_id"))
    if package_id is None:
        return
    from app.modules.quality_concept.service import QualityConceptService

    await _run(
        "handover",
        lambda s: QualityConceptService(s).apply_handover_issued(package_id, data.get("issued_at")),
        session_factory,
    )


async def handle_handover_revoked(data: dict, *, session_factory: Any = None) -> None:
    package_id = _uuid(data.get("package_id"))
    if package_id is None:
        return
    from app.modules.quality_concept.service import QualityConceptService

    await _run(
        "handover revoke", lambda s: QualityConceptService(s).apply_handover_revoked(package_id), session_factory
    )


async def handle_frame_document(data: dict, *, session_factory: Any = None) -> None:
    project_id, document_id = _uuid(data.get("project_id")), _uuid(data.get("document_id"))
    if project_id is None or document_id is None:
        return
    from app.modules.quality_concept.service import QualityConceptService

    await _run(
        "governance",
        lambda s: QualityConceptService(s).apply_governance_state(
            project_id,
            document_id,
            str(data.get("status")),
            # Governance names the new revision only when a change request moved the binding one.
            change_request=bool(data.get("bound_revision_id")),
        ),
        session_factory,
    )


async def _on_gate(event: Event) -> None:
    await handle_gate_released(event.data or {})


async def _on_handover(event: Event) -> None:
    await handle_handover_issued(event.data or {})


async def _on_handover_revoked(event: Event) -> None:
    await handle_handover_revoked(event.data or {})


async def _on_frame(event: Event) -> None:
    await handle_frame_document(event.data or {})


def register_quality_concept_subscribers() -> None:
    """Wire the mirrors. ``subscribe_once`` makes a repeated call harmless.

    No flag is kept beside the bus: a flag outlives the handlers when the bus is
    emptied, and the module would never subscribe again.
    """
    event_bus.subscribe_once("cc.gate.released", _on_gate)
    event_bus.subscribe_once("cc.handover.issued", _on_handover)
    event_bus.subscribe_once("cc.handover.revoked", _on_handover_revoked)
    event_bus.subscribe_once("project_governance.frame_document.state_changed", _on_frame)
