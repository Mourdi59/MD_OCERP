# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo data for project governance, run by ``app.core.demo_enrichment``.

Every write goes through :class:`GovernanceService` (and the CDE, teams and
approval route services for the records governance hangs off), so the audit
trail, the state machines and the after-commit events are the ones a real user
would produce. A project that already carries a governance model is skipped, so
a re-run is a no-op.

What a demo project gets:

* the shipped ``neutral`` phase model, four-eyes on;
* an owner on every area, taken from the seeded demo logins;
* gate ``strategy_to_brief`` decided ``go_with_conditions`` by the manager
  login, with one condition cleared with evidence and one open with a future
  due date;
* frame documents in three states: the business case binding, the project
  handbook in review, the requirements brief a draft;
* one submitted change request against the binding business case.

The caller commits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.project_governance import evaluator as ev
from app.modules.project_governance.models import GovernanceArea, GovernanceDocument, GovernanceGate
from app.modules.project_governance.service import GovernanceService

logger = logging.getLogger(__name__)

_OWNER_EMAIL = "demo@openconstructionerp.com"
_DECIDER_EMAIL = "manager@openconstructionerp.com"
_COST_EMAIL = "estimator@openconstructionerp.com"

#: The catalogue a demo project pins; AREA_OWNERS names its areas.
DEMO_CATALOGUE = "neutral"

#: Who owns each area of DEMO_CATALOGUE: ``cost`` is the estimator login, ``owner``
#: the project owner. Written out per area so the demo reads as a story;
#: tests/unit/test_governance_demo_seed_map.py fails when it drifts from the catalogue.
AREA_OWNERS: dict[str, str] = {
    "integration": "owner",
    "scope": "owner",
    "schedule": "owner",
    "cost_finance": "cost",
    "quality": "owner",
    "resources": "owner",
    "stakeholders": "owner",
    "risk": "owner",
    "procurement": "cost",
    "hse": "owner",
}


def owner_for(area_code: str, *, owner: uuid.UUID, cost_owner: uuid.UUID) -> uuid.UUID:
    """The demo owner of an area. An unmapped area goes to the project owner, never
    to the decider: under four-eyes a decider who owns an area cannot decide."""
    return cost_owner if AREA_OWNERS.get(area_code) == "cost" else owner


_FIRST_GATE = "strategy_to_brief"
_TEAM_NAME = "Governance board"

#: ``doc_type -> (container code, title, file name)`` for the frame documents.
_DOCS: dict[str, tuple[str, str, str]] = {
    "business_case": ("GOV-BC-001", "Business case", "business-case.pdf"),
    "project_handbook": ("GOV-PH-001", "Project handbook", "project-handbook.pdf"),
    "requirements_brief": ("GOV-RB-001", "Requirements brief", "requirements-brief.pdf"),
}


async def _user_id(session: AsyncSession, email: str) -> uuid.UUID | None:
    from app.modules.users.models import User

    return (
        await session.execute(select(User.id).where(User.email == email, User.is_active.is_(True)))
    ).scalar_one_or_none()


async def _ensure_members(
    session: AsyncSession, svc: GovernanceService, project_id: uuid.UUID, owner: uuid.UUID, users: list[uuid.UUID]
) -> None:
    """Put the demo logins on the project team so they may own areas and decide."""
    from app.modules.teams.models import Team
    from app.modules.teams.schemas import AddMemberRequest, TeamCreate
    from app.modules.teams.service import TeamService

    missing = [u for u in users if not await svc.user_can_access_project(project_id, u)]
    if not missing:
        return
    teams = TeamService(session)
    team = (
        await session.execute(select(Team).where(Team.project_id == project_id, Team.name == _TEAM_NAME))
    ).scalar_one_or_none()
    if team is None:
        team = await teams.create_team(TeamCreate(project_id=project_id, name=_TEAM_NAME), actor_id=owner)
    for uid in missing:
        await teams.add_member(team.id, AddMemberRequest(user_id=uid), actor_id=owner)


async def _ensure_route(session: AsyncSession, project_id: uuid.UUID, kind: str, approver: uuid.UUID) -> None:
    """A single-step route naming the decider, unless the project already has one."""
    from app.modules.approval_routes.schemas import RouteCreate, StepCreate
    from app.modules.approval_routes.service import ApprovalRouteService

    routes = ApprovalRouteService(session)
    existing = await routes.list_routes(project_id=project_id, target_kind=kind, include_inactive=False)
    if any(r.project_id in (None, project_id) for r in existing):
        return
    name = "Gate decision" if kind == "phase_gate" else "Frame document change"
    await routes.create_route(
        RouteCreate(
            project_id=project_id,
            name=name,
            target_kind=kind,
            steps=[StepCreate(ordinal=1, approver_user_id=approver, mode="any")],
        ),
        created_by=approver,
    )


async def _container(session: AsyncSession, project_id: uuid.UUID, doc_type: str, actor: uuid.UUID) -> uuid.UUID:
    """A CDE container with a first revision for one frame document."""
    from app.modules.cde.schemas import ContainerCreate, RevisionCreate
    from app.modules.cde.service import CDEService

    code, title, file_name = _DOCS[doc_type]
    cde = CDEService(session)
    container = await cde.create_container(
        ContainerCreate(project_id=project_id, container_code=code, title=title), user_id=str(actor)
    )
    await cde.create_revision(
        container.id,
        RevisionCreate(file_name=file_name, mime_type="application/pdf", change_summary="First issue"),
        user_id=str(actor),
    )
    return container.id


async def _seed_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    owner: uuid.UUID,
    decider: uuid.UUID,
    cost_owner: uuid.UUID,
    today: date,
) -> None:
    from app.modules.cde.schemas import RevisionCreate
    from app.modules.cde.service import CDEService

    svc = GovernanceService(session)
    await _ensure_members(session, svc, project_id, owner, [decider, cost_owner])
    await _ensure_route(session, project_id, "phase_gate", decider)
    await _ensure_route(session, project_id, "frame_change", decider)
    await svc.set_model(
        project_id,
        source="shipped",
        catalogue_id=DEMO_CATALOGUE,
        version=None,
        four_eyes=True,
        actor_id=owner,
        tenant_id=str(owner),
    )

    areas: list[GovernanceArea] = await svc.repo.list_areas(project_id)
    area_owner: dict[uuid.UUID, uuid.UUID] = {}
    for area in areas:
        who = owner_for(area.code, owner=owner, cost_owner=cost_owner)
        await svc.update_area(project_id, area.id, changes={"owner_user_id": who}, actor_id=owner)
        area_owner[area.id] = who
    area_code = {a.id: a.code for a in areas}

    docs: dict[str, GovernanceDocument] = {d.doc_type: d for d in await svc.repo.list_documents(project_id)}
    for doc_type in _DOCS:
        doc = docs.get(doc_type)
        if doc is None:
            continue
        actor = area_owner[doc.area_id]
        container_id = await _container(session, project_id, doc_type, actor)
        await svc.attach_container(project_id, doc.id, container_id=container_id, actor_id=actor, role="editor")

    gate = (
        await session.execute(
            select(GovernanceGate).where(GovernanceGate.project_id == project_id, GovernanceGate.code == _FIRST_GATE)
        )
    ).scalar_one()
    for doc in docs.values():
        if _FIRST_GATE in (doc.required_at_gates or []) and doc.container_id:
            await svc.submit_document(project_id, doc.id, actor_id=area_owner[doc.area_id], role="editor")
    await svc.start_preparation(project_id, gate.id, actor_id=owner)
    for area in areas:
        await svc.confirm_check(
            project_id,
            gate.id,
            area.id,
            status="ready",
            rag="green",
            note="Reviewed at the strategy workshop.",
            actor_id=area_owner[area.id],
        )
    await svc.submit_gate(project_id, gate.id, actor_id=owner)

    bc = docs["business_case"]
    bc_area = area_code[bc.area_id]
    open_area = next((a.code for a in areas if a.code == "schedule"), bc_area)
    request = ev.DecisionRequest(
        outcome="go_with_conditions",
        rationale=(
            "The business case supports the investment. Proceed to the brief once funding is confirmed "
            "and the site survey scope is agreed."
        ),
        decider_id=str(decider),
        conditions=(
            ev.ProposedCondition(
                area_code=bc_area,
                document_type="business_case",
                text="Confirm the funding envelope in writing before the brief is issued.",
                owner_user_id=str(cost_owner),
                due_date=today + timedelta(days=14),
                severity="critical",
            ),
            ev.ProposedCondition(
                area_code=open_area,
                document_type=None,
                text="Agree the site survey scope and appoint the survey consultant.",
                owner_user_id=str(owner),
                due_date=today + timedelta(days=45),
                severity="essential",
            ),
        ),
    )
    decision = await svc.decide(project_id, gate.id, request=request, decider_id=decider, role="manager", today=today)

    conditions, _ = await svc.repo.list_conditions(project_id)
    for cond in conditions:
        if cond.decision_id == decision.id and cond.document_type == "business_case":
            await svc.clear_condition(
                project_id,
                cond.id,
                evidence="Funding confirmation letter filed in the CDE with the business case.",
                actor_id=cost_owner,
                role="estimator",
            )

    handbook = docs.get("project_handbook")
    if handbook is not None and handbook.container_id and handbook.status == "draft":
        await svc.submit_document(project_id, handbook.id, actor_id=area_owner[handbook.area_id], role="editor")

    if bc.status == "binding" and bc.container_id:
        rev = await CDEService(session).create_revision(
            bc.container_id,
            RevisionCreate(
                file_name="business-case-rev2.pdf",
                mime_type="application/pdf",
                change_summary="Updated cost plan after the market sounding",
            ),
            user_id=str(cost_owner),
        )
        await svc.create_change_request(
            project_id,
            bc.id,
            reason="Market sounding raised the construction cost estimate; the cost plan needs updating.",
            impact="Budget envelope rises by about four percent; the contingency is reduced accordingly.",
            proposed_revision_id=rev.id,
            actor_id=cost_owner,
            role="estimator",
        )
    await session.flush()


async def seed_project_governance_demo(session: AsyncSession, project_ids: list[uuid.UUID]) -> dict[str, int]:
    """Seed governance on each demo project that has no governance model yet.

    Args:
        session: Open session; the caller commits.
        project_ids: Demo projects, already filtered by the caller.

    Returns:
        ``{"projects": n}``, the number of projects seeded by this run.
    """
    owner_by_email = await _user_id(session, _OWNER_EMAIL)
    decider = await _user_id(session, _DECIDER_EMAIL)
    cost_owner = await _user_id(session, _COST_EMAIL)
    if decider is None:
        # Four-eyes needs a decider who owns no area; without the manager login
        # there is none, and a half-seeded gate is worse than an empty screen.
        return {"projects": 0}

    from app.modules.projects.models import Project

    svc = GovernanceService(session)
    today = datetime.now(UTC).date()
    seeded = 0
    for pid in project_ids:
        if await svc.repo.get_model(pid) is not None:
            continue
        project = await session.get(Project, pid)
        if project is None:
            continue
        owner = project.owner_id or owner_by_email
        if owner is None or owner == decider:
            continue
        try:
            async with session.begin_nested():
                await _seed_project(
                    session, pid, owner=owner, decider=decider, cost_owner=cost_owner or owner, today=today
                )
            seeded += 1
        except Exception:
            logger.warning("governance demo seed skipped for %s", pid, exc_info=True)
    return {"projects": seeded}
