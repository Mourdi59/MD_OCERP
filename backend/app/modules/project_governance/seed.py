# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo data for project governance, run by ``app.core.demo_enrichment``.

Every write goes through :class:`GovernanceService` (and the CDE, teams and
approval route services for the records governance hangs off), so the audit
trail, the state machines and the after-commit events are the ones a real user
would produce. Decisions are recorded by the manager login on the route the
project pins, under four-eyes; no row is written past the service. A project
that already carries a governance model is skipped, so a re-run is a no-op.

The demo projects are left at different moments on purpose, because the other
module seeders read the project's phase through the governance port and tell a
preparation story or a running-site story from it (``seed_story.PLACEMENT``):

* the project the active pack's demo file names: the pack's phase model, its
  frame documents and its gate, stopped where the file says, so a decision can
  be taken on camera;
* one project in execution: every gate up to the one into the phase that
  enables ``construction_start`` is decided;
* one project near handover: the same, and the gate into handover is in
  preparation with its documents in review;
* every other project: the first gate decided ``go_with_conditions``, one
  condition cleared and one open, frame documents in three states and one
  change request against the binding business case.

A placement that cannot be completed falls back to the last story, so a demo
project never ends up without a model. The caller commits.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_accounts import SHOWCASE_OWNER_EMAIL
from app.core.events import publish_after_commit
from app.modules.project_governance import catalogue_packs, seed_story
from app.modules.project_governance import evaluator as ev
from app.modules.project_governance.catalogue_store import resolve_catalogue
from app.modules.project_governance.evidence import GateAttempt, collect_evidence
from app.modules.project_governance.models import (
    GovernanceArea,
    GovernanceCondition,
    GovernanceDocument,
    GovernanceGate,
)
from app.modules.project_governance.seed_story import DocumentPlan, PackStory
from app.modules.project_governance.service import GovernanceService

logger = logging.getLogger(__name__)

# The logins the platform seeds for its walkthrough (``app.core.demo_accounts``).
_OWNER_EMAIL = SHOWCASE_OWNER_EMAIL
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


_TEAM_NAME = "Governance board"

#: The frame documents of the first-gate story, with the titles a reader sees in the CDE.
_DOCS: dict[str, DocumentPlan] = {
    "business_case": DocumentPlan("business_case", "GOV-BC-001", "Business case", "business-case.pdf"),
    "project_handbook": DocumentPlan("project_handbook", "GOV-PH-001", "Project handbook", "project-handbook.pdf"),
    "requirements_brief": DocumentPlan(
        "requirements_brief", "GOV-RB-001", "Requirements brief", "requirements-brief.pdf"
    ),
}

_AT_RISK_DAYS = 30
#: The condition the walk attaches to an area that passes a gate at risk. ``settle_demo_conditions``
#: finds its own conditions by this text and touches no other.
AT_RISK_CONDITION = "Close the open readiness items of this area."
_SETTLED_EVIDENCE = "The readiness evidence of this area is met."
_HANDOVER_TARGET_DAYS = 30


class SeedStop(RuntimeError):
    """A story cannot go on; the project falls back to the first-gate story."""


@dataclass(frozen=True)
class Cast:
    """The three demo logins of a project."""

    owner: uuid.UUID
    decider: uuid.UUID
    cost_owner: uuid.UUID

    def named(self, word: str) -> uuid.UUID:
        return self.cost_owner if word == "cost" else self.owner


async def _user_id(session: AsyncSession, email: str) -> uuid.UUID | None:
    from sqlalchemy import select

    from app.modules.users.models import User

    return (
        await session.execute(select(User.id).where(User.email == email, User.is_active.is_(True)))
    ).scalar_one_or_none()


async def _ensure_members(
    session: AsyncSession, svc: GovernanceService, project_id: uuid.UUID, owner: uuid.UUID, users: list[uuid.UUID]
) -> None:
    """Put the demo logins on the project team so they may own areas and decide."""
    from sqlalchemy import select

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


async def _ensure_route(session: AsyncSession, project_id: uuid.UUID, kind: str, approver: uuid.UUID) -> uuid.UUID:
    """The project's own single-step route naming the decider; created unless the seed already made it.

    Governance reads only the route pinned on the model, and only a route of
    the project can be pinned, so a route without a project never counts here.
    """
    from app.modules.approval_routes.schemas import RouteCreate, StepCreate
    from app.modules.approval_routes.service import ApprovalRouteService

    routes = ApprovalRouteService(session)
    name = "Gate decision" if kind == "phase_gate" else "Frame document change"
    existing = await routes.list_routes(project_id=project_id, target_kind=kind, include_inactive=False)
    for route in existing:
        if route.project_id == project_id and route.name == name:
            return route.id
    created = await routes.create_route(
        RouteCreate(
            project_id=project_id,
            name=name,
            target_kind=kind,
            steps=[StepCreate(ordinal=1, approver_user_id=approver, mode="any")],
        ),
        created_by=approver,
    )
    return created.id


class _Stage:
    """One demo project while it is seeded: the service, the cast and the rows of its model."""

    def __init__(self, session: AsyncSession, project_id: uuid.UUID, cast: Cast, today: date) -> None:
        self.session = session
        self.project_id = project_id
        self.cast = cast
        self.today = today
        self.svc = GovernanceService(session)
        self.areas: list[GovernanceArea] = []
        self.area_owner: dict[uuid.UUID, uuid.UUID] = {}
        self.docs: dict[str, GovernanceDocument] = {}
        self.gates: dict[str, GovernanceGate] = {}

    async def open(
        self,
        *,
        source: str,
        catalogue_id: str,
        version: int | None,
        four_eyes: bool,
        owner_of: Callable[[str], uuid.UUID],
    ) -> None:
        """Team, routes, the pinned model and an owner on every area."""
        cast, pid = self.cast, self.project_id
        await _ensure_members(self.session, self.svc, pid, cast.owner, [cast.decider, cast.cost_owner])
        gate_route = await _ensure_route(self.session, pid, "phase_gate", cast.decider)
        change_route = await _ensure_route(self.session, pid, "frame_change", cast.decider)
        await self.svc.set_model(
            pid,
            source=source,
            catalogue_id=catalogue_id,
            version=version,
            four_eyes=four_eyes,
            actor_id=cast.owner,
            tenant_id=str(cast.owner),
        )
        await self.svc.update_settings(
            pid,
            four_eyes=None,
            decision_route_id=gate_route,
            change_route_id=change_route,
            fields_set={"decision_route_id", "change_route_id"},
            actor_id=cast.owner,
        )
        self.areas = list(await self.svc.repo.list_areas(pid))
        for area in self.areas:
            who = owner_of(area.code)
            await self.svc.update_area(pid, area.id, changes={"owner_user_id": who}, actor_id=cast.owner)
            self.area_owner[area.id] = who
        self.docs = {d.doc_type: d for d in await self.svc.repo.list_documents(pid)}
        self.gates = {g.code: g for g in await self.svc.repo.list_gates(pid)}

    def area_code(self, area_id: uuid.UUID) -> str:
        return next(a.code for a in self.areas if a.id == area_id)

    async def issue(self, plan: DocumentPlan) -> None:
        """A CDE container with the plan's revisions, attached to the frame document, submitted if asked."""
        from app.modules.cde.schemas import ContainerCreate, RevisionCreate
        from app.modules.cde.service import CDEService

        doc = self.docs.get(plan.doc_type)
        if doc is None:
            return
        actor = self.area_owner[doc.area_id]
        if not doc.container_id:
            cde = CDEService(self.session)
            container = await cde.create_container(
                ContainerCreate(project_id=self.project_id, container_code=plan.container_code, title=plan.title),
                user_id=str(actor),
            )
            for number in range(1, plan.revisions + 1):
                await cde.create_revision(
                    container.id,
                    RevisionCreate(
                        file_name=plan.file_name,
                        mime_type="application/pdf",
                        change_summary="First issue" if number == 1 else f"Revision {number}",
                    ),
                    user_id=str(actor),
                )
            await self.svc.attach_container(self.project_id, doc.id, container_id=container.id, actor_id=actor)
        if plan.submit and doc.status == "draft":
            await self.svc.submit_document(self.project_id, doc.id, actor_id=actor)

    async def issue_required(self, gate_code: str) -> None:
        """Every document the gate requires that is still a draft: issued and put in review."""
        for doc_type, doc in self.docs.items():
            if gate_code in (doc.required_at_gates or []) and doc.status == "draft":
                plan = _DOCS.get(doc_type) or seed_story.document_plan(doc_type)
                await self.issue(
                    DocumentPlan(plan.doc_type, plan.container_code, plan.title, plan.file_name, submit=True)
                )

    async def confirm(self, gate: GovernanceGate, area: GovernanceArea, status: str, rag: str, note: str) -> None:
        await self.svc.confirm_check(
            self.project_id, gate.id, area.id, status=status, rag=rag, note=note, actor_id=self.area_owner[area.id]
        )

    async def decide(
        self,
        gate: GovernanceGate,
        *,
        outcome: str | None = None,
        rationale: str = "",
        conditions: tuple[ev.ProposedCondition, ...] = (),
    ) -> Any:
        """Record the decision as the decider would in the dialog.

        The gate is read first. Readiness gaps in the way (a module that has no
        rows yet answers its evidence as not met, because governance seeds
        before the modules) are what a go with conditions may lift: those areas
        are named as proceeding at risk, one condition each. Without a stated
        outcome a clear gate gets a go, and any other blocker stops the story.
        """
        model = await self.svc.require_model(self.project_id)
        ctx, _, _ = await self.svc.gate_context(model, gate, self.today)
        blockers = ev.gate_blockers(ctx)
        gaps = tuple(sorted({b.area_code for b in blockers if b.code in ev.PROCEED_AT_RISK_LIFTABLE and b.area_code}))
        other = sorted({b.code for b in blockers if b.code not in ev.PROCEED_AT_RISK_LIFTABLE or not b.area_code})
        if outcome is None:
            if other:
                raise SeedStop(f"gate {gate.code} is blocked by {other}")
            outcome = "go_with_conditions" if gaps else "go"
            if gaps:
                rationale = "Readiness of some areas is still open. The gate passes at risk, each gap with an owner."
        at_risk: tuple[str, ...] = gaps if outcome == "go_with_conditions" else ()
        if at_risk:
            owner_of = {a.code: self.area_owner[a.id] for a in self.areas}
            conditions += tuple(
                ev.ProposedCondition(
                    area_code=code,
                    document_type=None,
                    text=AT_RISK_CONDITION,
                    owner_user_id=str(owner_of[code]),
                    due_date=self.today + timedelta(days=_AT_RISK_DAYS),
                    severity="essential",
                )
                for code in at_risk
            )
        request = ev.DecisionRequest(
            outcome=outcome,
            rationale=rationale,
            decider_id=str(self.cast.decider),
            conditions=conditions,
            proceed_at_risk_areas=at_risk,
            # A module that could not answer for an area is named, as the decider would in the dialog.
            acknowledged_evidence=tuple((e.area_code, e.code) for e in ev.evidence_to_acknowledge(ctx)),
        )
        return await self.svc.decide(
            self.project_id, gate.id, request=request, decider_id=self.cast.decider, role="manager", today=self.today
        )

    async def pass_gate(self, gate_code: str) -> None:
        """Take one gate from untouched to decided: documents, preparation, checks, review, decision."""
        gate = self.gates[gate_code]
        await self.issue_required(gate_code)
        await self.svc.start_preparation(self.project_id, gate.id, actor_id=self.cast.owner)
        for area in self.areas:
            await self.confirm(gate, area, "ready", "green", "Reviewed with the area owner before the gate.")
        gate = await self.svc.submit_gate(self.project_id, gate.id, actor_id=self.cast.owner)
        await self.decide(gate)


# ── the stories ──


async def _first_gate_story(stage: _Stage) -> None:
    """The first gate decided with conditions, documents in three states, one change request."""
    from app.modules.cde.schemas import RevisionCreate
    from app.modules.cde.service import CDEService

    cast, svc, pid, today = stage.cast, stage.svc, stage.project_id, stage.today
    await stage.open(
        source="shipped",
        catalogue_id=DEMO_CATALOGUE,
        version=None,
        four_eyes=True,
        owner_of=lambda code: owner_for(code, owner=cast.owner, cost_owner=cast.cost_owner),
    )
    for plan in _DOCS.values():
        await stage.issue(plan)
    first = seed_story.first_gate(await svc.catalogue_for(await svc.require_model(pid)))
    gate = stage.gates[first or ""]
    await stage.issue_required(gate.code)
    await svc.start_preparation(pid, gate.id, actor_id=cast.owner)
    for area in stage.areas:
        await stage.confirm(gate, area, "ready", "green", "Reviewed at the strategy workshop.")
    gate = await svc.submit_gate(pid, gate.id, actor_id=cast.owner)

    bc = stage.docs["business_case"]
    bc_area = stage.area_code(bc.area_id)
    open_area = next((a.code for a in stage.areas if a.code == "schedule"), bc_area)
    decision = await stage.decide(
        gate,
        outcome="go_with_conditions",
        rationale=(
            "The business case supports the investment. Proceed to the brief once funding is confirmed "
            "and the site survey scope is agreed."
        ),
        conditions=(
            ev.ProposedCondition(
                area_code=bc_area,
                document_type="business_case",
                text="Confirm the funding envelope in writing before the brief is issued.",
                owner_user_id=str(cast.cost_owner),
                due_date=today + timedelta(days=14),
                severity="critical",
            ),
            ev.ProposedCondition(
                area_code=open_area,
                document_type=None,
                text="Agree the site survey scope and appoint the survey consultant.",
                owner_user_id=str(cast.owner),
                due_date=today + timedelta(days=45),
                severity="essential",
            ),
        ),
    )

    conditions, _ = await svc.repo.list_conditions(pid)
    for cond in conditions:
        if cond.decision_id == decision.id and cond.document_type == "business_case":
            await svc.clear_condition(
                pid,
                cond.id,
                evidence="Funding confirmation letter filed in the CDE with the business case.",
                actor_id=cast.cost_owner,
            )

    handbook = stage.docs.get("project_handbook")
    if handbook is not None and handbook.container_id and handbook.status == "draft":
        await svc.submit_document(pid, handbook.id, actor_id=stage.area_owner[handbook.area_id])

    if bc.status == "binding" and bc.container_id:
        rev = await CDEService(stage.session).create_revision(
            bc.container_id,
            RevisionCreate(
                file_name="business-case-rev2.pdf",
                mime_type="application/pdf",
                change_summary="Updated cost plan after the market sounding",
            ),
            user_id=str(cast.cost_owner),
        )
        await svc.create_change_request(
            pid,
            bc.id,
            reason="Market sounding raised the construction cost estimate; the cost plan needs updating.",
            impact="Budget envelope rises by about four percent; the contingency is reduced accordingly.",
            proposed_revision_id=rev.id,
            actor_id=cast.cost_owner,
        )


async def _execution_story(stage: _Stage, *, near_handover: bool) -> None:
    """Every gate up to the start of construction decided; optionally the handover gate in preparation."""
    cast, svc, pid = stage.cast, stage.svc, stage.project_id
    await stage.open(
        source="shipped",
        catalogue_id=DEMO_CATALOGUE,
        version=None,
        four_eyes=True,
        owner_of=lambda code: owner_for(code, owner=cast.owner, cost_owner=cast.cost_owner),
    )
    catalogue = await svc.catalogue_for(await svc.require_model(pid))
    walk = seed_story.gates_until(catalogue, "construction_start")
    if not walk:
        raise SeedStop("no phase of the model enables construction_start")
    for code in walk:
        await stage.pass_gate(code)
    if not near_handover:
        return
    ahead = [code for code in seed_story.gates_until(catalogue, "handover") if code not in walk]
    if len(ahead) != 1:
        # The same phase enables both, or handover is more than one gate away: nothing to prepare.
        return
    gate = stage.gates[ahead[0]]
    await stage.issue_required(gate.code)
    await svc.start_preparation(pid, gate.id, actor_id=cast.owner)
    await svc.plan_gate(
        pid,
        gate.id,
        changes={"target_date": stage.today + timedelta(days=_HANDOVER_TARGET_DAYS)},
        actor_id=cast.owner,
    )
    # Most areas are ready; one carries a risk and the last has not been assessed yet.
    for area in stage.areas[:-2]:
        await stage.confirm(gate, area, "ready", "green", "Ready for handover.")
    for area in stage.areas[-2:-1]:
        await stage.confirm(gate, area, "ready_with_risks", "amber", "Snagging is still in progress on two floors.")


async def _pack_story(stage: _Stage, told: PackStory, pin: tuple[str, int]) -> None:
    """The story of the active pack's demo file, stopped where the file says."""
    cast, svc, pid = stage.cast, stage.svc, stage.project_id
    await stage.open(
        source="pack",
        catalogue_id=pin[0],
        version=pin[1],
        four_eyes=told.four_eyes,
        owner_of=lambda code: cast.named(told.area_owners.get(code, "owner")),
    )
    for plan in told.documents:
        await stage.issue(plan)
    gate = stage.gates[told.gate_code]
    if told.target_in_days is not None:
        await svc.plan_gate(
            pid,
            gate.id,
            changes={"target_date": stage.today + timedelta(days=told.target_in_days)},
            actor_id=cast.owner,
        )
    if told.stop_at == "not_started":
        return
    await svc.start_preparation(pid, gate.id, actor_id=cast.owner)
    by_code = {a.code: a for a in stage.areas}
    for check in told.checks:
        if check.status != "not_assessed":
            await stage.confirm(gate, by_code[check.area], check.status, check.rag, check.note)
    if told.stop_at == "in_preparation":
        return
    gate = await svc.submit_gate(pid, gate.id, actor_id=cast.owner)
    if told.stop_at == "in_review" or told.decision is None:
        return
    plan = told.decision
    await stage.decide(
        gate,
        outcome=plan.outcome,
        rationale=plan.rationale,
        conditions=tuple(
            ev.ProposedCondition(
                area_code=c.area,
                document_type=c.document_type,
                text=c.text,
                owner_user_id=str(cast.named(c.owner)),
                due_date=stage.today + timedelta(days=c.due_in_days),
                severity=c.severity,
            )
            for c in plan.conditions
        ),
    )


async def _pack_telling(
    session: AsyncSession, demo_id: str | None, locale: str
) -> tuple[PackStory, tuple[str, int]] | None:
    """The pack story for this project, or ``None`` when no pack tells one about it."""
    data = catalogue_packs.active_pack_demo()
    if data is None or not demo_id:
        return None
    project = data.get("project")
    if not isinstance(project, dict) or project.get("demo_template_id") != demo_id:
        return None
    try:
        pin = seed_story.pack_pin(data)
        catalogue = await resolve_catalogue(session, "pack", pin[0], pin[1])
        return seed_story.pack_story(data, catalogue, locale), pin
    except Exception:
        # A file that breaks a rule, or a catalogue that does not load: the built-in story instead.
        logger.exception("demo file of the active pack is not usable for %s", demo_id)
        return None


Story = Callable[[], Awaitable[None]]


def _stories(
    session: AsyncSession,
    project_id: uuid.UUID,
    cast: Cast,
    today: date,
    demo_id: str | None,
    telling: tuple[PackStory, tuple[str, int]] | None,
    outbox: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, Story]]:
    """The stories to try for one project, the wanted one first and the first-gate story last."""

    def stage() -> _Stage:
        # A fresh stage per try: a story that failed was rolled back with everything it loaded.
        fresh = _Stage(session, project_id, cast, today)
        fresh.svc.outbox = outbox
        return fresh

    stories: list[tuple[str, Story]] = []
    if telling is not None:
        told, pin = telling
        stories.append(("pack", lambda: _pack_story(stage(), told, pin)))
    elif demo_id in seed_story.PLACEMENT:
        placement = seed_story.PLACEMENT[demo_id]
        stories.append((placement, lambda: _execution_story(stage(), near_handover=placement == "near_handover")))
    stories.append(("first gate", lambda: _first_gate_story(stage())))
    return stories


async def _attempt(
    session: AsyncSession,
    name: str,
    project_id: uuid.UUID,
    story: Story,
    outbox: list[tuple[str, dict[str, Any]]],
) -> bool:
    """Run one story in its own savepoint; a story that fails leaves nothing behind.

    Governance events of the story wait in ``outbox`` and are handed to the bus
    only once the savepoint is released. An event deferred inside a savepoint
    that is then rolled back would still fire on the outer commit.
    """
    outbox.clear()
    try:
        async with session.begin_nested():
            await story()
            await session.flush()
        for event_name, data in outbox:
            publish_after_commit(session, event_name, data, source_module="project_governance")
        outbox.clear()
        return True
    except Exception:
        outbox.clear()
        # Kept from stopping the other projects, but loud: a silent skip reads as "0 projects".
        logger.exception("governance demo seed: the %s story failed for %s", name, project_id)
        return False


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
        cast = Cast(owner=owner, decider=decider, cost_owner=cost_owner or owner)
        demo_id = (project.metadata_ or {}).get("demo_id") if isinstance(project.metadata_, dict) else None
        telling = await _pack_telling(session, demo_id, getattr(project, "locale", None) or "en")
        outbox: list[tuple[str, dict[str, Any]]] = []
        for name, story in _stories(session, pid, cast, today, demo_id, telling, outbox):
            if await _attempt(session, name, pid, story, outbox):
                seeded += 1
                break
    return {"projects": seeded}


async def settle_demo_conditions(session: AsyncSession, project_ids: list[uuid.UUID] | None = None) -> dict[str, int]:
    """Clear the at-risk conditions of the walk whose area now reads ready. Run AFTER the module seeders.

    Governance seeds first, so a module without rows answers its evidence as
    not met and the walk passes the gate with the area at risk and one open
    condition. Once the modules have seeded, this step asks the same providers
    again for the gate the condition belongs to. Where no blocking provider
    says not met or unknown for the area any more, the owner of the condition
    clears it through the service, with the evidence as the reason. Every other
    condition stays open with its due date. Safe to run again.

    Args:
        session: Open session; the caller commits.
        project_ids: Limit to these projects; every project when omitted.

    Returns:
        ``{"cleared": n, "left_open": m}`` over the conditions the walk created.
    """
    from sqlalchemy import select

    stmt = select(GovernanceCondition).where(
        GovernanceCondition.text == AT_RISK_CONDITION,
        GovernanceCondition.status.in_(("open", "overdue")),
        GovernanceCondition.area_code.is_not(None),
        GovernanceCondition.owner_user_id.is_not(None),
    )
    if project_ids is not None:
        stmt = stmt.where(GovernanceCondition.project_id.in_(project_ids))
    conditions = list((await session.execute(stmt.order_by(GovernanceCondition.created_at))).scalars())
    svc = GovernanceService(session)
    cleared = 0
    for cond in conditions:
        try:
            async with session.begin_nested():
                gate = await svc.repo.get_gate(cond.project_id, cond.gate_id)
                area = next((a for a in await svc.repo.list_areas(cond.project_id) if a.code == cond.area_code), None)
                if gate is None or area is None:
                    continue
                collected = await collect_evidence(
                    session, cond.project_id, GateAttempt(gate.id, gate.code, gate.attempt_no), [area]
                )
                if any(e.blocking and e.item.state in ("not_met", "unknown") for e in collected):
                    continue
                await svc.clear_condition(
                    cond.project_id, cond.id, evidence=_SETTLED_EVIDENCE, actor_id=cond.owner_user_id
                )
                cleared += 1
        except Exception:
            logger.exception("governance demo seed: could not settle condition %s", cond.id)
    return {"cleared": cleared, "left_open": len(conditions) - cleared}
