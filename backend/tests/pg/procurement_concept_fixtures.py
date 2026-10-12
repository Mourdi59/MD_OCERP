# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the procurement concept PostgreSQL tests.

A world is a throwaway database with real users (a manager, an editor who owns
the procurement area, an editor who does not, an outsider), an EUR project with
team membership, module 3's package plan (built from its table contract when
module 3 itself is not installed in this tree), and a concept for a public
sub-central client under the shipped EU catalogue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.procurement_concept import plan_source as plan
from app.modules.procurement_concept.service import ProcurementConceptService
from tests.pg.governance_fixtures import add_project, add_user

TODAY = date(2026, 10, 11)


@dataclass
class World:
    factory: async_sessionmaker[AsyncSession]
    project_id: uuid.UUID
    manager: uuid.UUID
    area_owner: uuid.UUID
    editor: uuid.UUID
    outsider: uuid.UUID
    packages: dict[str, uuid.UUID] = field(default_factory=dict)


async def ensure_plan_tables(factory: async_sessionmaker[AsyncSession]) -> None:
    """Module 3's two tables, created from the table contract only where module 3 did not create them."""
    async with factory() as s:
        conn = await s.connection()
        await conn.run_sync(lambda c: plan.stand_in_metadata().create_all(c, checkfirst=True))
        await s.commit()


async def add_contract_package(
    w: World, code: str, kind: str, *, parent: str | None = None, need_date: str | None = None
) -> uuid.UUID:
    pid = uuid.uuid4()
    async with w.factory() as s:
        await s.execute(
            sa.insert(plan.PACKAGE_TABLE).values(
                id=pid,
                project_id=w.project_id,
                code=code,
                title=f"{code} package",
                kind=kind,
                parent_id=w.packages.get(parent) if parent else None,
                scope=f"Scope of {code}",
                wbs_ref="",
                boq_ref="",
                need_date=need_date,
                status="planned",
                sort_order=len(w.packages),
            )
        )
        await s.commit()
    w.packages[code] = pid
    return pid


async def set_delivery_form(w: World, form: str, *, public_client: bool = True) -> None:
    async with w.factory() as s:
        await s.execute(
            sa.insert(plan.MODEL_TABLE).values(
                id=uuid.uuid4(),
                project_id=w.project_id,
                selected_form_code=form,
                status="approved",
                owner_capability={"public_client": public_client},
            )
        )
        await s.commit()


async def add_procurement_area(w: World, owner: uuid.UUID, code: str = "m08_procurement") -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceArea

    async with w.factory() as s:
        area = GovernanceArea(project_id=w.project_id, code=code, sort_order=8, owner_user_id=owner)
        s.add(area)
        await s.commit()
        return area.id


async def build_world(factory: async_sessionmaker[AsyncSession], *, concept: bool = True) -> World:
    from app.modules.procurement_concept.catalogue import register_kind

    register_kind()
    await ensure_plan_tables(factory)
    async with factory() as s:
        manager = await add_user(s, "manager")
        area_owner = await add_user(s, "editor")
        editor = await add_user(s, "editor")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [area_owner, editor])
        await s.commit()
    w = World(factory, pid, manager, area_owner, editor, outsider)
    if concept:
        async with factory() as s:
            await ProcurementConceptService(s).set_concept(
                pid,
                {
                    "catalogue_source": "shipped",
                    "catalogue_id": "eu",
                    "jurisdiction": "eu",
                    "client_type": "sub_central",
                    "public_client": True,
                },
                actor_id=manager,
                role="manager",
            )
            await s.commit()
    return w


async def put(w: World, code: str, data: dict[str, Any], *, actor: uuid.UUID | None = None, role: str = "manager"):
    async with w.factory() as s:
        row = await ProcurementConceptService(s).put_package(
            w.project_id, w.packages[code], data, actor_id=actor or w.manager, role=role, tenant_id=str(w.manager)
        )
        await s.commit()
        return row


async def svc_call(w: World, fn: str, *args: Any, **kw: Any) -> Any:
    async with w.factory() as s:
        out = await getattr(ProcurementConceptService(s), fn)(*args, **kw)
        await s.commit()
        return out
