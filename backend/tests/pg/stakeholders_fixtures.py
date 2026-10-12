# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the stakeholders PostgreSQL tests.

A world is a throwaway database with real users, a project with team
membership, and the shipped ``neutral`` stakeholder framework pinned.
Everything commits for real, so locks and subscribers behave as in production.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.stakeholders.service import StakeholderService
from tests.pg.governance_fixtures import add_project, add_route, add_user

TODAY = date(2026, 10, 12)


@dataclass
class World:
    factory: async_sessionmaker[AsyncSession]
    project_id: uuid.UUID
    manager: uuid.UUID
    editor: uuid.UUID
    viewer: uuid.UUID
    outsider: uuid.UUID


async def build_world(
    factory: async_sessionmaker[AsyncSession], *, framework_id: str = "neutral", route: bool = False
) -> World:
    async with factory() as s:
        manager = await add_user(s, "manager")
        editor = await add_user(s, "editor")
        viewer = await add_user(s, "viewer")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [editor, viewer])
        data: dict = {"framework_source": "shipped", "framework_id": framework_id}
        if route:
            data["commitment_route_id"] = str(await add_route(s, pid, "stakeholder_commitment", manager))
        await StakeholderService(s).put_settings(pid, data, actor_id=manager)
        await s.commit()
    return World(factory, pid, manager, editor, viewer, outsider)


async def stakeholder(w: World, name: str, category: str = "neighbour", **extra) -> uuid.UUID:
    async with w.factory() as s:
        row = await StakeholderService(s).create_stakeholder(
            w.project_id, {"display_name": name, "category": category, **extra}, actor_id=w.editor
        )
        await s.commit()
        return row.id
