# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commitment release <-> approval routes and document events, after ``project_governance/events.py``.

* ``approval_routes.instance.completed | rejected | cancelled`` with
  ``target_kind = commitment_release``: the release request named by
  ``target_id`` is closed. :meth:`CommitmentService.apply_route_verdict` locks
  the item and acts only while the request is still pending on that very
  instance, so a late or repeated event is a no-op.
* Document events that change a linked amount or status
  (``contracts.contract.amended|signed|closed``, ``variations.contract_sum.updated``,
  ``changeorder.approved``, ``procurement.po.*``): every item of the affected
  projects is recomputed, because the once-only rule can move an amount
  between items (a change counted on its own item comes out of its contract's).

Same constraints as the governance subscribers: an isolated session,
PostgreSQL only (a second writer on SQLite would deadlock the request), fail-soft.
"""

from __future__ import annotations

import logging
import uuid

from app.core.events import Event, event_bus
from app.database import async_session_factory

logger = logging.getLogger(__name__)

TARGET_KIND = "commitment_release"

# event name -> (link kind, payload keys that may carry the document id)
DOCUMENT_EVENTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "contracts.contract.amended": ("contract", ("contract_id", "id")),
    "contracts.contract.signed": ("contract", ("contract_id", "id")),
    "contracts.contract.closed": ("contract", ("contract_id", "id")),
    "variations.contract_sum.updated": ("contract", ("contract_id",)),
    "changeorder.approved": ("change_order", ("change_order_id", "order_id", "id")),
    "procurement.po.updated": ("purchase_order", ("po_id", "purchase_order_id", "id")),
    "procurement.po.approved": ("purchase_order", ("po_id", "purchase_order_id", "id")),
    "procurement.po.issued": ("purchase_order", ("po_id", "purchase_order_id", "id")),
    "procurement.po.cancelled": ("purchase_order", ("po_id", "purchase_order_id", "id")),
}


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
    """Apply one terminal route verdict to the release request it targets."""
    if data.get("target_kind") != TARGET_KIND:
        return
    release_id = _uuid(data.get("target_id"))
    if release_id is None:
        return
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return
    try:
        async with factory() as session:
            from app.modules.commitment_release.service import CommitmentService

            await CommitmentService(session).apply_route_verdict(
                release_id,
                instance_id=_uuid(data.get("instance_id")),
                verdict=verdict,
                decided_by=data.get("decided_by") or data.get("cancelled_by"),
                comment=data.get("comment") or data.get("reason"),
            )
            await session.commit()
    except Exception:
        logger.error("commitment: route %s verdict was not applied to release %s", verdict, release_id, exc_info=True)


async def handle_document_event(name: str, data: dict, *, session_factory=None) -> int:
    """Recompute every item of the projects whose links name the document. Returns items touched."""
    spec = DOCUMENT_EVENTS.get(name)
    if spec is None:
        return 0
    kind, keys = spec
    doc_id = next((u for u in (_uuid(data.get(k)) for k in keys) if u is not None), None)
    if doc_id is None:
        return 0
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return 0
    touched = 0
    try:
        async with factory() as session:
            from app.modules.commitment_release.service import CommitmentService

            svc = CommitmentService(session)
            links = await svc.repo.links_for_documents(kind, [doc_id])
            for project_id in {lk.project_id for lk in links}:
                for item_id in [i.id for i in await svc.repo.list_items(project_id)]:
                    # One savepoint per item: an item that cannot be recomputed must not undo its siblings.
                    try:
                        async with session.begin_nested():
                            await svc.recompute_item(project_id, item_id)
                        touched += 1
                    except Exception:
                        logger.error(
                            "commitment: recompute of item %s after %s (%s) failed",
                            item_id,
                            name,
                            doc_id,
                            exc_info=True,
                        )
            await session.commit()
    except Exception:
        logger.error("commitment: recompute after %s failed for %s", name, doc_id, exc_info=True)
    return touched


async def handle_award_draft(data: dict, *, session_factory=None) -> int:
    """Link what an award drafted to the item that holds the award. Returns links written."""
    project_id = _uuid(data.get("project_id"))
    if project_id is None:
        return 0
    factory = session_factory or async_session_factory
    if session_factory is None and not await _can_open_isolated_session():
        return 0
    try:
        async with factory() as session:
            from app.modules.commitment_release.service import CommitmentService

            written = await CommitmentService(session).adopt_award_drafts(project_id)
            await session.commit()
            return written
    except Exception:
        logger.error("commitment: award drafts of project %s were not linked", project_id, exc_info=True)
        return 0


async def _on_award_draft(event: Event) -> None:
    await handle_award_draft(event.data or {})


async def _on_completed(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="approved")


async def _on_rejected(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="rejected")


async def _on_cancelled(event: Event) -> None:
    await handle_route_event(event.data or {}, verdict="cancelled")


async def _on_document(event: Event) -> None:
    await handle_document_event(event.name, event.data or {})


def register_commitment_subscribers() -> None:
    """Wire the approval-route and document subscribers of this module; safe to call again.

    ``subscribe_once`` is what makes a second call harmless. A flag kept beside the bus would
    outlive the handlers whenever the bus is emptied (an app restarted in one process), and the
    module would then never hear a decision, a cancellation or a signed document again.
    """
    event_bus.subscribe_once("approval_routes.instance.completed", _on_completed)
    event_bus.subscribe_once("approval_routes.instance.rejected", _on_rejected)
    event_bus.subscribe_once("approval_routes.instance.cancelled", _on_cancelled)
    for name in DOCUMENT_EVENTS:
        event_bus.subscribe_once(name, _on_document)
    # The order of the same award is drafted without an event; the sweeper links it.
    event_bus.subscribe_once("contracts.contract.drafted_from_bid_award", _on_award_draft)
