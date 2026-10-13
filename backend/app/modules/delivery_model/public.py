# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What other modules may read from a project's delivery model.

Small frozen read models, so no module has to import this module's
repository, service or ORM rows. Every function is scoped to one project and
answers an empty tuple or ``None`` when the project has no delivery model.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.delivery_model.repository import DeliveryModelRepository

__all__ = ["PackageView", "project_packages"]


@dataclass(frozen=True)
class PackageView:
    """One contract package of a project's package plan.

    Attributes:
        id: The package row.
        code: The package code, unique within the project.
        title: The package title as the project wrote it.
        kind: ``design``, ``construction``, ``design_and_construction`` and so on.
        status: ``planned``, ``closed`` or ``cancelled`` as stored (not the linked record's state).
        party: Catalogue code of the party that holds the package.
        designs: The package carries design.
        builds: The package carries construction.
        supplies: The package carries supply.
        parent_id: The package it sits under, if any.
        need_date: ISO day the package is needed by, if one is set.
    """

    id: uuid.UUID
    code: str
    title: str
    kind: str
    status: str
    party: str
    designs: bool
    builds: bool
    supplies: bool
    parent_id: uuid.UUID | None
    need_date: str | None


async def project_packages(session: AsyncSession, project_id: uuid.UUID) -> tuple[PackageView, ...]:
    """The project's contract packages in plan order; empty when it has none.

    The caller has already checked that its user may open the project.
    """
    rows = await DeliveryModelRepository(session).packages(project_id)
    return tuple(
        PackageView(
            id=p.id,
            code=p.code,
            title=p.title,
            kind=p.kind,
            status=p.status,
            party=p.party,
            designs=bool(p.designs),
            builds=bool(p.builds),
            supplies=bool(p.supplies),
            parent_id=p.parent_id,
            need_date=str(p.need_date) if p.need_date else None,
        )
        for p in rows
    )
