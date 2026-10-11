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


async def build_world(factory: async_sessionmaker[AsyncSession], *, governance: bool = True) -> World:
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
                catalogue_id="elf_module_framework",
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
