# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the design management PostgreSQL tests.

A world is the governance world (users, project, team, pinned governance model)
plus a design setup on the ``simple_sequential`` scheme, so a number needs only
a discipline, and one design role per discipline. Everything commits for real.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.design_management.service import DesignService
from tests.pg.governance_fixtures import build_world


@dataclass
class DesignWorld:
    factory: async_sessionmaker[AsyncSession]
    project_id: uuid.UUID
    manager: uuid.UUID
    approver: uuid.UUID
    editor: uuid.UUID
    outsider: uuid.UUID
    roles: dict[str, uuid.UUID] = field(default_factory=dict)


async def build_design_world(factory: async_sessionmaker[AsyncSession]) -> DesignWorld:
    gov = await build_world(factory, routes=False)
    w = DesignWorld(factory, gov.project_id, gov.manager, gov.decider, gov.editor, gov.outsider)
    async with factory() as s:
        svc = DesignService(s)
        await svc.set_setup(w.project_id, actor_id=w.manager, tenant_id=str(w.manager), scheme_id="simple_sequential")
        for code, discipline in (("ARCH", "A"), ("STRU", "S")):
            role = await svc.create_role(
                w.project_id,
                {"code": code, "title": code, "party_kind": "discipline_designer", "discipline_code": discipline},
                actor_id=w.manager,
            )
            w.roles[code] = role.id
        await s.commit()
    return w


async def drawing_with_revision(w: DesignWorld, role: str, suitability: str = "S2") -> tuple[uuid.UUID, uuid.UUID]:
    """A register drawing with one revision at ``suitability``; returns (drawing id, revision id)."""
    from tests.pg.governance_fixtures import add_revision

    async with w.factory() as s:
        drawing, container = await DesignService(s).create_drawing(
            w.project_id, {"role_id": str(w.roles[role]), "title": f"{role} plan"}, actor_id=w.editor
        )
        rev_id = await add_revision(s, container.id, 1, f"{container.container_code}-1")
        from app.modules.cde.models import DocumentRevision

        (await s.get(DocumentRevision, rev_id)).suitability_code = suitability
        await s.commit()
        return drawing.id, rev_id
