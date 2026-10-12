# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the delivery model PostgreSQL tests.

A world is a throwaway database with real users and a project that runs
governance on the shipped ``elf_module_framework`` model (eleven areas, one
gate ``development_to_execution`` at which every area's frame document is
required, including the contracts area ``m02_contract_management``), approval
routes for ``phase_gate`` and ``frame_change``, a CDE container per frame
document, and the shipped ``neutral`` delivery forms catalogue pinned.
Everything commits for real, so row locks behave as in production.

Tags. The delivery model finds its carrier document and the procurement gate
through tags in the governance catalogue (``hosts`` on a document type,
``enables`` on a phase). Module 1 adds those tags on another branch; until
they are in this tree, :func:`tag_governance` hands the service the project's
real governance catalogue with the tags added, exactly where the service reads
it. Nothing else is replaced: which document carries the tag, which document
row that is and which gate leads into the tagged phase are all resolved by the
production code. Once the shipped catalogue carries the tag the helper passes
it through untouched.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.delivery_model.service import DeliveryModelService
from app.modules.project_governance.service import GovernanceService
from tests.pg.governance_fixtures import World, add_container, add_project, add_route, add_user

GATE = "development_to_execution"
CONTRACT_DOC = "m02_contract_management_frame"


class _Tagged:
    """An object with a few attributes added or replaced; everything else is the wrapped object's."""

    def __init__(self, inner: Any, **extra: Any) -> None:
        self._inner, self._extra = inner, extra

    def __getattr__(self, name: str) -> Any:
        extra = self.__dict__["_extra"]
        return extra[name] if name in extra else getattr(self.__dict__["_inner"], name)


def tag_governance(
    monkeypatch: Any,
    *,
    documents: dict[str, tuple[str, ...]] | None = None,
    phases: dict[str, tuple[str, ...]] | None = None,
) -> None:
    """Serve governance catalogues with the delivery tags module 1 will ship (see the module docstring)."""
    from app.modules.delivery_model import hosting

    documents = {CONTRACT_DOC: (hosting.CARRIER_TAG,)} if documents is None else documents
    phases = {"execution": (hosting.PROCUREMENT_TAG,)} if phases is None else phases
    real = hosting.governance_catalogue

    async def with_tags(session: Any, project_id: uuid.UUID) -> Any:
        catalogue = await real(session, project_id)
        if catalogue is None or hosting.carrier_document_types(catalogue):
            return catalogue
        return _Tagged(
            catalogue,
            document_types=tuple(_Tagged(d, hosts=documents.get(d.code, ())) for d in catalogue.document_types),
            phases=tuple(_Tagged(p, enables=phases.get(p.code, ())) for p in catalogue.phases),
        )

    monkeypatch.setattr(hosting, "governance_catalogue", with_tags)


async def build_world(
    factory: async_sessionmaker[AsyncSession], *, governance: bool = True, catalogue_id: str = "elf_module_framework"
) -> World:
    from app.modules.delivery_model.catalogue import register_kinds

    register_kinds()
    async with factory() as s:
        manager = await add_user(s, "manager")
        decider = await add_user(s, "manager")
        owner = await add_user(s, "editor")
        editor = await add_user(s, "editor")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [decider, owner, editor])
        w = World(factory, pid, manager, decider, owner, editor, outsider)
        if governance:
            w.gate_route_id = await add_route(s, pid, "phase_gate", decider)
            w.change_route_id = await add_route(s, pid, "frame_change", decider)
            await GovernanceService(s).set_model(
                pid,
                source="shipped",
                catalogue_id=catalogue_id,
                version=None,
                four_eyes=True,
                actor_id=manager,
                tenant_id=str(manager),
            )
            for d in await GovernanceService(s).repo.list_documents(pid):
                w.containers[d.doc_type] = await add_container(s, pid, d.doc_type)
        await DeliveryModelService(s).set_model(pid, actor_id=manager, tenant_id=str(manager), catalogue_id="neutral")
        await s.commit()
    return w


async def call(w: World, fn: str, *args: Any, **kw: Any) -> Any:
    """Run one service method in its own committed session."""
    async with w.factory() as s:
        out = await getattr(DeliveryModelService(s), fn)(w.project_id, *args, **kw)
        await s.commit()
        return out


async def compare(
    w: World, forms: tuple[str, ...] = ("design_bid_build_single", "design_build")
) -> dict[str, uuid.UUID]:
    """Add the forms as options and score them with the catalogue defaults."""
    ids = {}
    for code in forms:
        row = await call(w, "add_option", code, overrides={}, notes="", actor_id=w.manager)
        ids[code] = row.id
    await call(w, "prefill_scores", w.manager)
    return ids


async def propose(w: World, option_id: uuid.UUID, **kw: Any) -> Any:
    return await call(
        w,
        "propose",
        option_id=option_id,
        rationale=kw.pop("rationale", "Single point of responsibility and a fixed price at award."),
        owner_capability=None,
        dispositions=kw.pop("dispositions", {}),
        actor_id=kw.pop("actor_id", w.manager),
    )


async def state(w: World) -> Any:
    from sqlalchemy import select

    from app.modules.delivery_model.models import DeliveryModel

    async with w.factory() as s:
        return (await s.execute(select(DeliveryModel).where(DeliveryModel.project_id == w.project_id))).scalar_one()


async def align_allocations(w: World) -> None:
    """Put every risk category on the default of the form in use and confirm the matrix."""
    matrix = await call(w, "allocation_matrix")
    for item in matrix["items"]:
        default = item["default"]
        if default is None:
            continue
        await call(
            w,
            "put_allocation",
            item["category_code"],
            {"party": default["party"], "basis": default["basis"], "shares": default["shares"] or {}, "rationale": ""},
            w.manager,
        )
    await call(w, "confirm_allocations", None, w.manager)


async def view(w: World, **kw: Any) -> dict[str, Any]:
    """The model as the API returns it, read in its own committed session (the catch-up may write)."""
    return await call(w, "model_view", **kw)


async def decisions(w: World) -> dict[str, dict[str, Any]]:
    """Decision views by form code."""
    return {d["form_code"]: d for d in await call(w, "decision_views")}


async def change_request(w: World, *, reason: str = "The owner cannot staff the design review") -> uuid.UUID:
    """A newer revision of the carrier document and a governance change request for it."""
    from sqlalchemy import func, select

    from app.modules.cde.models import DocumentRevision
    from tests.pg.governance_fixtures import add_revision, documents

    doc = (await documents(w))[CONTRACT_DOC]
    async with w.factory() as s:
        container = w.containers[CONTRACT_DOC]
        count = select(func.count()).select_from(DocumentRevision).where(DocumentRevision.container_id == container)
        n = (await s.execute(count)).scalar_one()
        await add_revision(s, container, n + 1, f"m02-hash-{n + 1}")
        cr = await GovernanceService(s).create_change_request(
            w.project_id,
            doc.id,
            reason=reason,
            impact="Delivery form",
            proposed_revision_id=None,
            actor_id=w.manager,
            role="manager",
        )
        await s.commit()
        return cr.id


async def settle_change_request(w: World, cr_id: uuid.UUID, verdict: str, *, by: uuid.UUID | None = None) -> None:
    """Governance's own verdict on the change request, then the event its subscriber would deliver."""
    from app.modules.delivery_model.events import handle_frame_document
    from tests.pg.governance_fixtures import documents

    async with w.factory() as s:
        await GovernanceService(s).apply_change_decision(cr_id, decision=verdict, decided_by=by or w.decider)
        await s.commit()
    if verdict == "approved":
        doc = (await documents(w))[CONTRACT_DOC]
        await handle_frame_document(
            {"project_id": str(w.project_id), "document_id": str(doc.id), "status": "binding"},
            session_factory=w.factory,
        )
