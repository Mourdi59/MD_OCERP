# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo stakeholder register and project organisation, run by ``app.core.demo_enrichment``.

Each demo project gets the framework its country resolves to and a register a
project team would really keep before the development-to-execution gate:
authorities, the grid operator, utilities, neighbours (as groups, so no
private person is invented), the district council, a local association,
the press, the client side and the lender, each assessed on the power and
interest grid, some long enough ago to be due for review. The communication
plan has a monthly neighbour newsletter, a one-off information evening that
was held with commitments made there, an authority coordination series and a
steering committee briefing triggered by the gate. Roles are filled from the
project's own team (roster entries are created for team members that have
none), the steering committee has members and the mandate template applies.

Names are descriptive and generic, never a real company or person. Only
projects carrying the demo marker are touched; a project with settings is
skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# code, label, category, is_group, power, interest, current, desired, attitude, days since assessed
_STAKEHOLDERS: tuple[tuple[str, str, str, bool, int, int, str, str, int, int], ...] = (
    ("S-001", "Municipal planning department", "municipality", False, 5, 4, "neutral", "supportive", 0, 20),
    ("S-002", "Building permit authority", "permitting_authority", False, 5, 3, "neutral", "supportive", 0, 35),
    ("S-003", "Environmental protection agency", "specialist_authority", False, 4, 3, "neutral", "neutral", 0, 120),
    ("S-004", "Regional electricity grid operator", "grid_operator", False, 4, 2, "unaware", "supportive", 0, 40),
    ("S-005", "Water and sewer utility", "utility", False, 3, 2, "neutral", "neutral", 0, 60),
    ("S-006", "Residents along the north boundary", "neighbour", True, 3, 5, "resistant", "neutral", -1, 15),
    ("S-007", "Owners of the adjacent commercial plots", "neighbour", True, 2, 4, "neutral", "supportive", 0, 15),
    ("S-008", "General public of the district", "public", True, 2, 3, "unaware", "neutral", 0, 150),
    ("S-009", "District council", "politics", False, 4, 4, "supportive", "supportive", 1, 30),
    ("S-010", "Local cycling association", "interest_group", False, 1, 4, "resistant", "neutral", -1, 45),
    ("S-011", "Local newspaper", "media", False, 2, 3, "neutral", "neutral", 0, 200),
    ("S-012", "Client board", "client", False, 5, 5, "leading", "leading", 2, 10),
    ("S-013", "Future users' representatives", "user", True, 3, 5, "supportive", "leading", 1, 25),
    ("S-014", "Financing bank", "lender", False, 4, 2, "supportive", "supportive", 1, 90),
)


async def seed_stakeholders_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed every demo project in ``project_ids`` that has no settings yet. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.projects.models import Project
    from app.modules.stakeholders.models import StakeholderSettings

    totals = {"projects": 0, "stakeholders": 0, "commitments": 0, "unfilled_roles": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (
            await session.execute(select(StakeholderSettings.id).where(StakeholderSettings.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("stakeholders demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


def gate_before_construction(gates: Any, enabling_phases: tuple[str, ...]) -> Any | None:
    """The undecided gate that opens construction, or ``None`` when the site may already run.

    ``gates`` are the governance port's gate views, ``enabling_phases`` the
    phases whose entry enables the start of construction. A project without a
    phase model, or with that gate decided, has no such gate.
    """
    return next((g for g in gates if g.to_phase in enabling_phases and g.status != "decided"), None)


async def _gate_before_construction(session: AsyncSession, project_id: uuid.UUID) -> Any | None:
    from app.modules.project_governance.public import phases_enabling, project_gates

    enabling = await phases_enabling(session, project_id, "construction_start")
    return gate_before_construction(await project_gates(session, project_id), enabling)


async def _team(session: AsyncSession, project_id: uuid.UUID, owner: uuid.UUID) -> list[uuid.UUID]:
    from app.modules.teams.models import Team, TeamMembership

    stmt = (
        select(TeamMembership.user_id)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(Team.project_id == project_id)
        .order_by(TeamMembership.created_at)
    )
    out = [owner]
    for (uid,) in (await session.execute(stmt)).all():
        if uid and uid not in out:
            out.append(uid)
    return out


async def _roster_for(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> uuid.UUID:
    """The roster entry of a team user, created when the user has none (the roster is the project's people list)."""
    from app.modules.teams.models import RosterMember
    from app.modules.users.models import User

    found = (
        await session.execute(
            select(RosterMember.id).where(RosterMember.project_id == project_id, RosterMember.user_id == user_id)
        )
    ).scalar_one_or_none()
    if found is not None:
        return found
    user = await session.get(User, user_id)
    row = RosterMember(
        project_id=project_id, user_id=user_id, display_name=(user.full_name if user else "") or "Team member"
    )
    session.add(row)
    await session.flush()
    return row.id


async def _commitment_route(session: AsyncSession, project_id: uuid.UUID, approver: uuid.UUID) -> uuid.UUID:
    """The project's own single-step route for commitments, naming ``approver``; reused when the seed made it."""
    from app.modules.approval_routes.schemas import RouteCreate, StepCreate
    from app.modules.approval_routes.service import ApprovalRouteService
    from app.modules.stakeholders.service import TARGET_KIND

    routes = ApprovalRouteService(session)
    name = "Stakeholder commitment"
    for route in await routes.list_routes(project_id=project_id, target_kind=TARGET_KIND, include_inactive=False):
        if route.project_id == project_id and route.name == name:
            return route.id
    created = await routes.create_route(
        RouteCreate(
            project_id=project_id,
            name=name,
            target_kind=TARGET_KIND,
            steps=[StepCreate(ordinal=1, approver_user_id=approver, mode="any")],
        ),
        created_by=approver,
    )
    return created.id


async def _decide(session: AsyncSession, svc: Any, instance_id: uuid.UUID, approver: uuid.UUID) -> None:
    """Approve a commitment's route instance the way its screen does, then apply the verdict.

    The subscriber applies it too when the event arrives; the second application finds nothing pending.
    """
    from app.modules.approval_routes.models import Instance, Step
    from app.modules.approval_routes.schemas import DecisionSubmit
    from app.modules.approval_routes.service import ApprovalRouteService

    instance = await session.get(Instance, instance_id)
    step = (
        await session.execute(
            select(Step).where(Step.route_id == instance.route_id, Step.ordinal == instance.current_step_ordinal)
        )
    ).scalar_one()
    await ApprovalRouteService(session).submit_decision(
        instance_id, DecisionSubmit(step_id=step.id, decision="approved"), approver_id=approver
    )
    await svc.apply_route_verdict(instance_id, verdict="approved", decided_by=approver)


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.projects.models import Project
    from app.modules.stakeholders.models import StakeholderAssessment
    from app.modules.stakeholders.service import StakeholderService
    from app.modules.teams.models import RosterMember

    project = await session.get(Project, project_id)
    owner = project.owner_id
    team = await _team(session, project_id, owner)
    pm = team[1] if len(team) > 1 else owner
    comms = team[2] if len(team) > 2 else pm
    today = datetime.now(UTC).date()
    svc = StakeholderService(session)
    # Agreeing a commitment goes through the project's commitment route; its approver is a second person.
    approver = next((u for u in team if u != owner), None)
    route = await _commitment_route(session, project_id, approver) if approver is not None else None
    await svc.put_settings(project_id, {"commitment_route_id": str(route)} if route else {}, actor_id=owner)
    # While the gate into construction is undecided the site does not run: promises about site operation
    # are agreed and nothing more, and the committee briefing for that gate is still ahead.
    gate = await _gate_before_construction(session, project_id)

    ids: dict[str, uuid.UUID] = {}
    for code, label, category, group, power, interest, cur, des, att, age in _STAKEHOLDERS:
        row = await svc.create_stakeholder(
            project_id,
            {
                "code": code,
                "display_name": label,
                "category": category,
                "is_group": group,
                "group_size_estimate": 40 if group else None,
                "relationship_owner_user_id": comms
                if category in ("neighbour", "public", "media", "interest_group")
                else pm,
            },
            actor_id=owner,
        )
        ids[code] = row.id
        a = await svc.assess(
            project_id,
            row.id,
            {
                "scores": {"power": power, "interest": interest},
                "engagement_current": cur,
                "engagement_desired": des,
                "attitude": att,
                "rationale": "Initial stakeholder analysis workshop",
            },
            actor_id=pm,
            now=datetime.now(UTC) - timedelta(days=age),
        )
        assert isinstance(a, StakeholderAssessment)
    # One drift entry: the residents were assessed resistant first, neutral attitude later.
    await svc.assess(
        project_id,
        ids["S-006"],
        {
            "scores": {"power": 3, "interest": 5},
            "engagement_current": "neutral",
            "engagement_desired": "supportive",
            "attitude": 0,
            "rationale": "After the information evening the residents' tone changed",
        },
        actor_id=comms,
    )

    newsletter = await svc.create_plan_item(
        project_id,
        {
            "title": "Neighbour newsletter",
            "purpose": "Keep the neighbourhood informed about works, deliveries and noisy phases",
            "key_message": "What happens next month, and whom to call",
            "audience_categories": ["neighbour"],
            "participation_level": "inform",
            "channel": "newsletter",
            "format_code": "neighbour_information",
            "frequency": "FREQ=MONTHLY;BYDAY=1MO",
            "starts_on": today - timedelta(days=75),
            "owner_user_id": comms,
            "status": "active",
        },
        actor_id=owner,
    )
    evening_day = today - timedelta(days=40 if gate is not None else 21)
    evening_plan = await svc.create_plan_item(
        project_id,
        {
            "title": "Information evening for residents",
            "purpose": "Present the construction logistics plan and collect concerns",
            "audience_stakeholder_ids": [str(ids["S-006"]), str(ids["S-007"]), str(ids["S-008"])],
            "participation_level": "consult",
            "channel": "information_evening",
            "format_code": "public_information_evening",
            "frequency": "once",
            "starts_on": evening_day,
            "owner_user_id": comms,
            "status": "active",
        },
        actor_id=owner,
    )
    await svc.create_plan_item(
        project_id,
        {
            "title": "Authority coordination meeting",
            "purpose": "Coordinate permit conditions and inspections",
            "audience_stakeholder_ids": [str(ids["S-002"]), str(ids["S-003"])],
            "participation_level": "consult",
            "channel": "meeting",
            "format_code": "authority_coordination_meeting",
            "frequency": "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU",
            "starts_on": today - timedelta(days=60),
            "owner_user_id": pm,
            "status": "active",
        },
        actor_id=owner,
    )
    briefing = await svc.create_plan_item(
        project_id,
        {
            "title": "Steering committee briefing",
            "purpose": "Brief the client board on stakeholder status before each decision",
            "audience_stakeholder_ids": [str(ids["S-012"])],
            "participation_level": "inform",
            "channel": "meeting",
            "format_code": "steering_committee_briefing",
            # Before each gate where the project has gates, every quarter where it is run without them.
            **(
                {"trigger_kind": "gate"}
                if await svc.gates(project_id)
                else {"frequency": "FREQ=MONTHLY;INTERVAL=3", "starts_on": today + timedelta(days=21)}
            ),
            "owner_user_id": pm,
            "status": "active",
        },
        actor_id=owner,
    )
    evening = await svc.create_event(
        project_id,
        {
            "plan_item_id": str(evening_plan.id),
            "held_on": evening_day,
            "status": "held",
            "location": "Community hall next to the site",
            "stakeholder_ids": [str(ids["S-006"]), str(ids["S-007"]), str(ids["S-008"])],
            "attendance_count": 64,
            "outcome": "Main concerns: early deliveries, dust on the access road, blocked cycle lane",
            # Forty days on, the answers have gone back to the residents; three weeks on, they are still due.
            **({"feedback_summary": "Answers to all concerns sent with the following newsletter"} if gate else {}),
        },
        actor_id=comms,
    )
    if gate is not None:
        target = gate.target_date or today + timedelta(days=21)
        await svc.create_event(
            project_id,
            {
                "plan_item_id": str(briefing.id),
                # A week before the gate, and never in the past.
                "occurrence_date": max(target - timedelta(days=7), today + timedelta(days=1)),
                "status": "planned",
                "stakeholder_ids": [str(ids["S-012"])],
            },
            actor_id=pm,
        )
    for days_ago in (70, 42):
        await svc.create_event(
            project_id,
            {
                "plan_item_id": str(newsletter.id),
                "held_on": today - timedelta(days=days_ago),
                "status": "held",
                "stakeholder_ids": [str(ids["S-006"]), str(ids["S-007"])],
            },
            actor_id=comms,
        )
    await svc.create_event(
        project_id,
        {
            "title": "Site tour for the district council",
            "participation_level": "inform",
            "format_code": "site_tour",
            "held_on": today - timedelta(days=50),
            "status": "held",
            "stakeholder_ids": [str(ids["S-009"])],
            "attendance_count": 9,
            "outcome": "Council asked for a progress update before the summer recess",
            "feedback_summary": "Update sent with the newsletter",
        },
        actor_id=pm,
    )

    commitments = 0

    async def promise(text: str, category: str, who: list[str], due: date, verification: str) -> uuid.UUID:
        nonlocal commitments
        c = await svc.create_commitment(
            project_id,
            {
                "stakeholder_ids": [str(ids[w]) for w in who],
                "source_kind": "event",
                "source_ref": str(evening.id),
                "text": text,
                "category": category,
                "owner_user_id": str(pm),
                "due_date": due,
                "verification": verification,
            },
            actor_id=comms,
        )
        commitments += 1
        return c.id

    c1 = await promise(
        "No deliveries before 07:00 on weekdays",
        "working_hours",
        ["S-006", "S-007"],
        today + timedelta(days=180),
        "Gate log of delivery times, checked weekly",
    )
    c2 = await promise(
        "Wheel washing at the site exit and weekly road sweeping",
        "traffic",
        ["S-006"],
        today + timedelta(days=30),
        "Photos in the site diary",
    )
    c3 = await promise(
        "Temporary cycle lane diversion signed before the access road closes",
        "access",
        ["S-010", "S-008"],
        today - timedelta(days=3),
        "Signage plan approved by the road authority",
    )
    c4 = await promise(
        "Monthly noise measurement report to the residents",
        "noise",
        ["S-006"],
        today + timedelta(days=10),
        "Report attached to the newsletter",
    )
    await promise(
        "Contact person and hotline number on the site hoarding",
        "information",
        ["S-006", "S-007", "S-008"],
        today + timedelta(days=7),
        "Photo of the hoarding",
    )

    # Roles from the team, then the steering committee, then decisions under the mandate.
    # The client is an organisation: a roster entry without a user account.
    client = RosterMember(project_id=project_id, display_name="Client organisation", company_name="Client")
    session.add(client)
    await session.flush()
    await svc.put_role_holders(
        project_id, "client", [{"roster_member_id": str(client.id)}], actor_id=owner, today=today
    )
    await svc.put_role_holders(
        project_id,
        "client_pm",
        [{"roster_member_id": str(await _roster_for(session, project_id, owner))}],
        actor_id=owner,
        today=today,
    )
    if pm != owner:
        # One person as client lead and project manager would propose and decide scope changes (forbidden).
        await svc.put_role_holders(
            project_id,
            "project_manager",
            [{"roster_member_id": str(await _roster_for(session, project_id, pm))}],
            actor_id=owner,
            today=today,
        )
    if comms != pm:
        await svc.put_role_holders(
            project_id,
            "communications_lead",
            [{"roster_member_id": str(await _roster_for(session, project_id, comms))}],
            actor_id=owner,
            today=today,
        )
    # The first pin created the bodies the mandate template names; the committee only needs its members.
    body = next(b for b in await svc.repo.bodies(project_id) if b.code == "steering_committee")
    await svc.put_members(
        project_id,
        body.id,
        # The project manager proposes to the committee and so does not sit on it.
        [{"role_code": "client_pm"}, *[{"user_id": str(u)} for u in team[3:5] if u not in (pm, comms)]],
        actor_id=owner,
        today=today,
    )
    for cid, steps in (
        (c1, ("agreed",)),
        (c2, ("agreed",) if gate is not None else ("agreed", "in_progress")),
        (c3, ("agreed",)),
        (c4, ("agreed",) if gate is not None else ("agreed", "fulfilled")),
    ):
        if approver is None:
            # Nobody but the owner could approve: the commitments stay proposed, which is a legal state.
            break
        for target in steps:
            await svc.transition_commitment(project_id, cid, target, actor_id=owner, today=today)
            row = next((c for c in await svc.repo.commitments(project_id) if c.id == cid), None)
            if row is not None and row.pending_target == target and row.approval_instance_id is not None:
                await _decide(session, svc, row.approval_instance_id, approver)
    if approver is None:
        logger.info(
            "stakeholders demo seed for %s: nobody besides the owner approves, commitments stay proposed", project_id
        )
    if pm != owner and gate is None:
        # Four eyes: the commitment's owner (the project manager) does not verify it; the client lead does.
        await svc.transition_commitment(
            project_id,
            c4,
            "verified",
            actor_id=owner,
            communicated_back_at=datetime.now(UTC) - timedelta(days=1),
            today=today,
        )
    # A demo project may have its owner and nobody else: the roles a second and a third person would
    # hold stay vacant, which the organisation screen shows as it is. Legal, so said at info.
    unfilled = [role for role, user in (("project_manager", pm), ("communications_lead", comms)) if user == owner]
    if pm != owner and comms == pm:
        unfilled.append("communications_lead")
    if unfilled:
        logger.info("stakeholders demo seed for %s: nobody on the team for %s", project_id, ", ".join(unfilled))
    return {"stakeholders": len(ids), "commitments": commitments, "unfilled_roles": len(unfilled)}
