# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the project governance PostgreSQL tests.

A world is a throwaway database with real users, a project, team membership,
an approval route for ``phase_gate`` and ``frame_change`` whose single step
names the decider, CDE containers with revisions, and the shipped ``neutral``
catalogue pinned. Everything commits for real, so locks and subscribers behave
as they do in production.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.project_governance import evaluator as ev
from app.modules.project_governance.models import GovernanceArea, GovernanceDocument, GovernanceGate
from app.modules.project_governance.service import GovernanceService


@dataclass
class World:
    factory: async_sessionmaker[AsyncSession]
    project_id: uuid.UUID
    manager: uuid.UUID
    decider: uuid.UUID
    owner: uuid.UUID
    editor: uuid.UUID
    outsider: uuid.UUID
    gate_route_id: uuid.UUID | None = None
    change_route_id: uuid.UUID | None = None
    containers: dict[str, uuid.UUID] = field(default_factory=dict)


async def add_user(session: AsyncSession, role: str) -> uuid.UUID:
    from app.modules.users.models import User

    uid = uuid.uuid4()
    session.add(
        User(
            id=uid,
            email=f"{role}-{uid.hex[:8]}@example.test",
            hashed_password="x",
            full_name=f"Test {role}",
            role=role,
            locale="en",
            is_active=True,
            metadata_={},
        )
    )
    await session.flush()
    return uid


async def add_project(session: AsyncSession, owner: uuid.UUID, members: list[uuid.UUID]) -> uuid.UUID:
    from app.modules.projects.models import Project
    from app.modules.teams.models import Team, TeamMembership

    pid = uuid.uuid4()
    session.add(
        Project(id=pid, name=f"Gov {pid.hex[:6]}", currency="EUR", status="active", owner_id=owner, metadata_={})
    )
    await session.flush()
    team = Team(project_id=pid, name="Core")
    session.add(team)
    await session.flush()
    for m in members:
        session.add(TeamMembership(team_id=team.id, user_id=m))
    await session.flush()
    return pid


async def add_route(session: AsyncSession, project_id: uuid.UUID, kind: str, approver: uuid.UUID) -> uuid.UUID:
    from app.modules.approval_routes.models import Route, Step

    route = Route(project_id=project_id, name=f"{kind} sign-off", target_kind=kind, is_active=True)
    session.add(route)
    await session.flush()
    session.add(Step(route_id=route.id, ordinal=1, approver_user_id=approver, mode="any"))
    await session.flush()
    return route.id


async def add_revision(session: AsyncSession, container_id: uuid.UUID, number: int, digest: str) -> uuid.UUID:
    from app.modules.cde.models import DocumentContainer, DocumentRevision

    rev = DocumentRevision(
        container_id=container_id,
        revision_code=f"P{number:02d}",
        revision_number=number,
        content_hash=digest,
        file_name=f"doc-{number}.pdf",
    )
    session.add(rev)
    await session.flush()
    container = await session.get(DocumentContainer, container_id)
    container.current_revision_id = rev.id
    await session.flush()
    return rev.id


async def add_container(session: AsyncSession, project_id: uuid.UUID, code: str) -> uuid.UUID:
    from app.modules.cde.models import DocumentContainer

    c = DocumentContainer(project_id=project_id, container_code=code, title=code, cde_state="wip")
    session.add(c)
    await session.flush()
    await add_revision(session, c.id, 1, f"{code}-hash-1")
    return c.id


async def build_world(factory: async_sessionmaker[AsyncSession], *, routes: bool = True) -> World:
    async with factory() as s:
        manager = await add_user(s, "manager")
        decider = await add_user(s, "manager")
        owner = await add_user(s, "editor")
        editor = await add_user(s, "editor")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [decider, owner, editor])
        w = World(factory, pid, manager, decider, owner, editor, outsider)
        if routes:
            w.gate_route_id = await add_route(s, pid, "phase_gate", decider)
            w.change_route_id = await add_route(s, pid, "frame_change", decider)
        for code in ("business_case", "project_handbook", "requirements_brief"):
            w.containers[code] = await add_container(s, pid, code)
        svc = GovernanceService(s)
        await svc.set_model(
            pid,
            source="shipped",
            catalogue_id="neutral",
            version=None,
            four_eyes=True,
            actor_id=manager,
            tenant_id=str(manager),
        )
        await s.commit()
    return w


async def gate(w: World, code: str) -> GovernanceGate:
    async with w.factory() as s:
        return (
            await s.execute(
                select(GovernanceGate).where(GovernanceGate.project_id == w.project_id, GovernanceGate.code == code)
            )
        ).scalar_one()


async def areas(w: World) -> dict[str, GovernanceArea]:
    async with w.factory() as s:
        return {a.code: a for a in await GovernanceService(s).repo.list_areas(w.project_id)}


async def documents(w: World) -> dict[str, GovernanceDocument]:
    async with w.factory() as s:
        return {d.doc_type: d for d in await GovernanceService(s).repo.list_documents(w.project_id)}


async def prepare_gate(
    w: World, gate_code: str, *, owner: uuid.UUID | None = None, submit: bool = True
) -> GovernanceGate:
    """Owners on every area, required documents attached and submitted, checks ready, gate in review."""
    owner = owner or w.owner
    async with w.factory() as s:
        svc = GovernanceService(s)
        for a in await svc.repo.list_areas(w.project_id):
            await svc.update_area(w.project_id, a.id, changes={"owner_user_id": owner}, actor_id=w.manager)
        g = (
            await s.execute(
                select(GovernanceGate).where(
                    GovernanceGate.project_id == w.project_id, GovernanceGate.code == gate_code
                )
            )
        ).scalar_one()
        for d in await svc.repo.list_documents(w.project_id):
            if gate_code in d.required_at_gates and d.status == "draft":
                await svc.attach_container(
                    w.project_id, d.id, container_id=w.containers[d.doc_type], actor_id=owner, role="editor"
                )
                await svc.submit_document(w.project_id, d.id, actor_id=owner, role="editor")
        await svc.start_preparation(w.project_id, g.id, actor_id=owner) if g.status == "not_started" else None
        for a in await svc.repo.list_areas(w.project_id):
            await svc.confirm_check(w.project_id, g.id, a.id, status="ready", rag="green", note="", actor_id=owner)
        if submit:
            await svc.submit_gate(w.project_id, g.id, actor_id=owner)
        await s.commit()
        return g


async def decide(
    w: World,
    gate_id: uuid.UUID,
    outcome: str = "go",
    *,
    decider: uuid.UUID | None = None,
    today: date = date(2026, 10, 11),
    **kw,
):
    req = ev.DecisionRequest(
        outcome=outcome,
        rationale=kw.pop("rationale", "" if outcome == "go" else "reason"),
        decider_id=str(decider or w.decider),
        **kw,
    )
    async with w.factory() as s:
        d = await GovernanceService(s).decide(
            w.project_id, gate_id, request=req, decider_id=decider or w.decider, role="manager", today=today
        )
        await s.commit()
        return d
