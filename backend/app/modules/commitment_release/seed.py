# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo commitment matrix for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the authority schedule its catalogue data resolves to,
the project owner as holder of every tier and a second person (a team member,
else another demo login) who plans and requests, so that four eyes holds. The
four items are the ones an owner would plan:

* a works package, released in full and then linked to the first subcontractor
  contract of the project, so it reads committed against a release;
* a long-lead supply that is still planned and past its decision date, with a
  supplier cancellation schedule;
* a design appointment released in tranches: the first decided, the second
  waiting for its approver;
* a contingency drawdown, planned.

Money is in the currency of the project; a project without one is skipped. The
abort terms use the ``custom`` basis with an entered charge: a statutory basis
is chosen by a person from the catalogue, never by this seeder. Requests and
decisions are dated a few days back so the history reads in order.

Only projects carrying the demo marker are touched; a project that already
has a matrix is skipped, so a re-run never duplicates. Runs after the
contracts and cost-model seeders, whose documents it links.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def seed_commitment_release_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the matrix of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.commitment_release.models import CommitmentMatrix
    from app.modules.projects.models import Project

    totals = {"projects": 0, "items": 0, "links": 0, "releases": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    demo = [pid for pid, meta in rows if demo_id_of(meta)]
    for pid in demo:
        has = (
            await session.execute(select(CommitmentMatrix.id).where(CommitmentMatrix.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("commitment_release demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _team_member(session: AsyncSession, project_id: uuid.UUID, exclude: uuid.UUID | None) -> uuid.UUID | None:
    from app.modules.teams.models import Team, TeamMembership

    stmt = (
        select(TeamMembership.user_id)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(Team.project_id == project_id)
        .order_by(TeamMembership.created_at)
    )
    for (uid,) in (await session.execute(stmt)).all():
        if uid and uid != exclude:
            return uid
    return None


async def _second_person(session: AsyncSession, project_id: uuid.UUID, owner: uuid.UUID) -> uuid.UUID | None:
    """Who plans and requests while the owner approves: a team member, else another demo login."""
    from app.core.demo_accounts import DEMO_ACCOUNT_EMAILS
    from app.modules.users.models import User

    member = await _team_member(session, project_id, owner)
    if member is not None:
        return member
    stmt = (
        select(User.id)
        .where(User.email.in_(sorted(DEMO_ACCOUNT_EMAILS)), User.is_active.is_(True), User.id != owner)
        .order_by(User.email)
    )
    return (await session.execute(stmt)).scalars().first()


async def _release(
    svc: Any,
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    amount: str,
    currency: str,
    *,
    requester: uuid.UUID,
    approver: uuid.UUID | None,
    note: str,
    days_ago: int,
    conditions: str = "",
) -> bool:
    """Request a release and, with ``approver``, decide it. False (and a warning) when it is refused."""
    from app.modules.commitment_release.errors import CommitmentError

    today = datetime.now(UTC).date()
    try:
        async with svc.session.begin_nested():
            preview = svc.evaluation_out(await svc.preview_release(project_id, item_id, amount, currency, today=today))
            row = await svc.request_release(
                project_id,
                item_id,
                amount=amount,
                currency=currency,
                tranche_note=note,
                external_approval_ref="Owner board minute (demo)" if preview["escalate_outside"] else "",
                actor_id=requester,
                today=today,
            )
            row.created_at = datetime.now(UTC) - timedelta(days=days_ago)
            # A tier every assignee decides has one step each; the owner holds them all here.
            for _step in range(8):
                if approver is None or row.outcome != "pending":
                    break
                row = await svc.decide_release(
                    project_id,
                    item_id,
                    decision="approved",
                    comment="",
                    conditions=conditions,
                    valid_until=None,
                    actor_id=approver,
                    caller_role="admin",
                    today=today,
                )
            if row.decided_at is not None:
                row.decided_at = datetime.now(UTC) - timedelta(days=max(days_ago - 3, 0))
            await svc.session.flush()
    except CommitmentError as exc:
        logger.warning("commitment_release demo: release of %s on %s refused: %s", item_id, project_id, exc.code)
        return False
    return True


async def _readiness_fields(session: AsyncSession, project_id: uuid.UUID) -> dict[str, str]:
    """The gate and the management area a demo item is read at, from the project's own phase model.

    The gate is the one that opens the phase which enables procurement; the area is the one that
    hosts commitment release. Nothing is named when the project has no model or the model says
    neither, so no code of any catalogue is written here.
    """
    from app.modules.project_governance.public import host_for, phases_enabling, project_areas, project_gates

    host = await host_for(session, project_id, "commitment_release")
    phases = set(await phases_enabling(session, project_id, "procurement"))
    gate = next((g.code for g in await project_gates(session, project_id) if g.to_phase in phases), None)
    areas = {a.code for a in await project_areas(session, project_id)}
    if host is None or gate is None or host.area_code not in areas:
        return {}
    return {"gate_code": gate, "governance_area_code": host.area_code}


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.commitment_release.service import CommitmentService
    from app.modules.contracts.models import Contract
    from app.modules.projects.models import Project

    counts = {"items": 0, "links": 0, "releases": 0, "scenarios": 0}
    project = await session.get(Project, project_id)
    owner = project.owner_id
    ccy = (project.currency or "").strip().upper()
    if owner is None or not ccy:
        # No owner to hold the tiers, or no currency to plan in: nothing honest can be seeded.
        logger.warning("commitment_release demo: project %s has no owner or no currency, skipped", project_id)
        return counts
    planner = await _second_person(session, project_id, owner)
    if planner is None:
        # Four eyes: the owner holds the tiers and cannot approve a request of their own.
        logger.warning(
            "commitment_release demo: project %s has nobody but its owner, items are seeded without a release",
            project_id,
        )
    author = planner or owner
    readiness = await _readiness_fields(session, project_id)
    today = datetime.now(UTC).date()
    svc = CommitmentService(session)
    matrix = await svc.set_matrix(project_id, actor_id=owner, tenant_id=None)
    schedule = await svc.schedule_for(matrix)
    roles = [t.approver.ref for t in schedule.tiers if t.approver.kind == "project_role"]
    await svc.put_assignments(
        project_id,
        [{"project_role": r, "user_id": owner, "valid_from": today - timedelta(days=60)} for r in roles],
        actor_id=owner,
        today=today,
    )

    contract = (
        await session.execute(
            select(Contract)
            .where(Contract.project_id == project_id, Contract.counterparty_type == "subcontractor")
            .order_by(Contract.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    works_amount = str(contract.total_value) if contract is not None and contract.total_value else "1850000"
    works_ccy = (contract.currency if contract is not None and contract.currency else ccy).strip().upper()

    works = await svc.create_item(
        project_id,
        {
            "code": "CR-001",
            "title": "Structural works package",
            "commitment_type": "works",
            "planned_source": "manual",
            "planned_manual_amount": works_amount,
            "currency": works_ccy,
            "lead_time_days": 45,
            "decision_buffer_days": 10,
            "latest_decision_date_fixed": (today - timedelta(days=14)).isoformat(),
            **readiness,
        },
        actor_id=author,
    )
    counts["items"] += 1
    await svc.put_abort_terms(
        project_id,
        works.id,
        {"basis_code": "custom", "other_charge_estimate": "40000", "source_note": "Demo estimate, not from a contract"},
        actor_id=owner,
        manage=True,
    )
    if planner is not None and await _release(
        svc,
        project_id,
        works.id,
        works_amount,
        works_ccy,
        requester=planner,
        approver=owner,
        note="Full package",
        days_ago=21,
    ):
        counts["releases"] += 1
        if contract is not None:
            # Linked only once released, so the contract never reads committed against nothing.
            await svc.add_link(project_id, works.id, "contract", contract.id, actor_id=author, manage=True)
            counts["links"] += 1

    facade = await svc.create_item(
        project_id,
        {
            "code": "CR-002",
            "title": "Long-lead facade units",
            "commitment_type": "supplies",
            "planned_source": "manual",
            "planned_manual_amount": "420000",
            "currency": ccy,
            "lead_time_days": 120,
            "decision_buffer_days": 14,
            "latest_decision_date_fixed": (today - timedelta(days=5)).isoformat(),
            **readiness,
        },
        actor_id=author,
    )
    counts["items"] += 1
    await svc.put_abort_terms(
        project_id,
        facade.id,
        {
            "basis_code": "supply_cancellation_schedule",
            "cancellation_schedule": [
                {"milestone": "order", "from_date": today.isoformat(), "charge_pct": "0.10"},
                {
                    "milestone": "fabrication",
                    "from_date": (today + timedelta(days=60)).isoformat(),
                    "charge_pct": "0.50",
                },
                {"milestone": "shipped", "progress_pct": "0.9", "charge_pct": "0.95"},
            ],
            "transferable": "resale",
            "salvage_value_estimate": "60000",
            "source_note": "Supplier quotation, cancellation terms",
        },
        actor_id=owner,
        manage=True,
    )

    design = await svc.create_item(
        project_id,
        {
            "code": "CR-003",
            "title": "Design appointment to stage 3",
            "commitment_type": "design",
            "planned_source": "manual",
            "planned_manual_amount": "260000",
            "currency": ccy,
            "latest_decision_date_fixed": (today + timedelta(days=45)).isoformat(),
        },
        actor_id=author,
    )
    counts["items"] += 1
    brief = await svc.add_precondition(
        project_id, design.id, kind="manual", ref_id=None, text="Client brief signed off", actor_id=author
    )
    await svc.confirm_precondition(
        project_id, design.id, brief.id, met=True, evidence_ref="Brief rev. C, signed", actor_id=author
    )
    if planner is not None:
        if await _release(
            svc,
            project_id,
            design.id,
            "40000",
            ccy,
            requester=planner,
            approver=owner,
            note="First tranche: concept design",
            days_ago=12,
            conditions="Stage 2 report before the next tranche",
        ):
            counts["releases"] += 1
            if await _release(
                svc,
                project_id,
                design.id,
                "60000",
                ccy,
                requester=planner,
                approver=None,
                note="Second tranche: developed design",
                days_ago=2,
            ):
                counts["releases"] += 1

    await svc.create_item(
        project_id,
        {
            "code": "CR-004",
            "title": "Contingency drawdown for ground conditions",
            "commitment_type": "contingency_drawdown",
            "planned_source": "manual",
            "planned_manual_amount": "75000",
            "currency": ccy,
        },
        actor_id=author,
    )
    counts["items"] += 1
    await svc.save_scenario(project_id, as_of=today, label="Stop today", actor_id=owner)
    counts["scenarios"] += 1
    return counts
