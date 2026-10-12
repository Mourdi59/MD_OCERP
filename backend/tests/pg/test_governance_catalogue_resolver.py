# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The resolver keeps a tenant catalogue inside its tenant; a stored pin keeps resolving."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.project_governance.events as gov_events
from app.modules.project_governance import public
from app.modules.project_governance.catalogue_store import CatalogueStore, resolve_catalogue
from app.modules.project_governance.errors import GovernanceError
from app.modules.project_governance.service import GovernanceService
from tests._pg import isolated_engine
from tests.pg.governance_fixtures import World, add_project, build_world

pytestmark = [pytest.mark.asyncio, pytest.mark.tenant_isolation]


@pytest_asyncio.fixture
async def world(monkeypatch: pytest.MonkeyPatch):
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        monkeypatch.setattr(gov_events, "async_session_factory", factory)
        yield await build_world(factory)


async def _published(w: World, tenant: str) -> str:
    async with w.factory() as s:
        store = CatalogueStore(s)
        row = await store.create(
            tenant,
            code="acme",
            name="Acme model",
            based_on_source="shipped",
            based_on_id="neutral",
            based_on_version=None,
            actor_id=w.manager,
        )
        await store.publish(tenant, row.id, actor_id=w.manager)
        await s.commit()
        return str(row.id)


async def test_a_request_id_resolves_only_for_its_own_tenant(world: World) -> None:
    owner, stranger = str(world.manager), str(world.outsider)
    cid = await _published(world, owner)
    async with world.factory() as s:
        own = await resolve_catalogue(s, "tenant", cid, 1, tenant_id=owner)
        assert own.version == 1 and own.host_of("design") is not None
        with pytest.raises(GovernanceError) as foreign:
            await resolve_catalogue(s, "tenant", cid, 1, tenant_id=stranger)
        with pytest.raises(GovernanceError) as latest:
            await resolve_catalogue(s, "tenant", cid, None, tenant_id=stranger)
        with pytest.raises(GovernanceError) as anonymous:
            await resolve_catalogue(s, "tenant", cid, 1)
        # A shipped catalogue is public and needs no tenant.
        assert (await resolve_catalogue(s, "shipped", "neutral", None)).id == "neutral"
    assert [e.value.status_code for e in (foreign, latest, anonymous)] == [404, 404, 404]
    assert {e.value.code for e in (foreign, latest, anonymous)} == {"unknown_catalogue"}


async def test_a_retired_catalogue_is_refused_by_id_but_a_pin_on_it_keeps_resolving(world: World) -> None:
    owner = str(world.manager)
    cid = await _published(world, owner)
    async with world.factory() as s:
        pid = await add_project(s, world.manager, [world.outsider])
        await GovernanceService(s).set_model(
            pid,
            source="tenant",
            catalogue_id=cid,
            version=1,
            four_eyes=True,
            actor_id=world.manager,
            tenant_id=owner,
        )
        await CatalogueStore(s).retire(owner, uuid.UUID(cid))
        await s.commit()
    async with world.factory() as s:
        with pytest.raises(GovernanceError) as retired:
            await resolve_catalogue(s, "tenant", cid, 1, tenant_id=owner)
        # The project pinned it before; the pin, not the reader, names the version.
        service = GovernanceService(s)
        pinned = await service.catalogue_for(await service.require_model(pid))
        assert pinned.version == 1
        host = await public.host_for(s, pid, "design")
        assert host == public.Host(area_code="scope", doc_type="scope_statement")
        assert await public.phases_enabling(s, pid, "construction_start") == ("construction",)
    assert retired.value.code == "catalogue_retired" and retired.value.status_code == 409


async def test_a_project_without_a_model_hosts_nothing(world: World) -> None:
    async with world.factory() as s:
        pid = await add_project(s, world.manager, [])
        assert await public.project_catalogue(s, pid) is None
        assert await public.host_for(s, pid, "design") is None
        assert await public.phases_enabling(s, pid, "handover") == ()
