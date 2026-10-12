# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Port for soft links into modules that site logistics does not import.

A transport can name a plant item, a utility demand a plant position and a
permit an authority permit. Those rows live in other modules, so the owning
module plugs in a resolver that says which project a row belongs to::

    from app.modules.site_logistics.links import register_link_resolver

    async def plant_item_project(session, row_id):
        return await session.scalar(select(PlantItem.project_id).where(PlantItem.id == row_id))

    register_link_resolver("plant_item", plant_item_project)

The plan service accepts such a link only when the resolver answers with the
project of the request. While no resolver is registered the link is refused
(``link_target_unavailable``): an id nobody can check is not stored.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

LINK_KINDS = ("plant_item", "plant_position", "authority_permit")

# (session, row id) -> the project the row belongs to, or None when there is no such row.
LinkResolver = Callable[[Any, uuid.UUID], Awaitable[uuid.UUID | None]]

_RESOLVERS: dict[str, LinkResolver] = {}


def register_link_resolver(kind: str, resolver: LinkResolver) -> None:
    """Register (or replace) the resolver of one link kind."""
    if kind not in LINK_KINDS:
        raise ValueError(f"unknown link kind {kind!r}, expected one of {LINK_KINDS}")
    _RESOLVERS[kind] = resolver


def unregister_link_resolver(kind: str) -> None:
    _RESOLVERS.pop(kind, None)


def resolver(kind: str) -> LinkResolver | None:
    """The resolver of a link kind, ``None`` while its module has not registered one."""
    return _RESOLVERS.get(kind)
