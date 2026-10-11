# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo commitment matrix for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the authority schedule its country resolves to, the
project owner and a team member as tier holders, generated tier routes and
four items an owner would actually plan: a works package linked to the
project's first subcontractor contract when there is one, a long-lead supply
with a supplier cancellation schedule, a design appointment released in
tranches (first tranche requested) and a contingency drawdown. Amounts are
manual estimates scaled from nothing invented: the works item reads its
committed figure from the linked contract, the others are labelled estimates.

Only projects carrying the demo marker are touched; a project that already
has a matrix is skipped, so a re-run never duplicates. Runs after the
contracts and cost-model seeders, whose documents it links.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

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


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.commitment_release.service import CommitmentService
    from app.modules.contracts.models import Contract
    from app.modules.projects.models import Project

    counts = {"items": 0, "links": 0, "releases": 0}
    project = await session.get(Project, project_id)
    owner = project.owner_id
    if owner is None:
        return counts
    other = await _team_member(session, project_id, owner)
    today = datetime.now(UTC).date()
    ccy = (project.currency or "EUR").strip().upper() or "EUR"
    svc = CommitmentService(session)
    matrix = await svc.set_matrix(project_id, actor_id=owner, tenant_id=None)
    schedule = await svc.schedule_for(matrix)
    roles = [t.approver.ref for t in schedule.tiers if t.approver.kind == "project_role"]
    # The owner fills the lowest tier; a second person (when the team has one)
    # the tiers above, so a release can be requested without four-eyes refusing it.
    assignments = []
    for i, role in enumerate(roles):
        holder = owner if i == 0 or other is None else other
        assignments.append({"project_role": role, "user_id": holder, "valid_from": today - timedelta(days=30)})
    await svc.put_assignments(project_id, assignments, actor_id=owner, today=today)

    contract = (
        await session.execute(
            select(Contract)
            .where(Contract.project_id == project_id, Contract.counterparty_type == "subcontractor")
            .order_by(Contract.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()

    works = await svc.create_item(
        project_id,
        {
            "code": "CR-001",
            "title": "Structural works package",
            "commitment_type": "works",
            "planned_source": "manual",
            "planned_manual_amount": "1850000",
            "currency": ccy,
            "lead_time_days": 45,
            "decision_buffer_days": 10,
            "latest_decision_date_fixed": (today + timedelta(days=21)).isoformat(),
        },
        actor_id=owner,
    )
    counts["items"] += 1
    if contract is not None:
        await svc.add_link(project_id, works.id, "contract", contract.id, actor_id=owner)
        counts["links"] += 1
    basis = "de_bgb_648" if (project.country_code or "").upper() == "DE" else "custom"
    await svc.put_abort_terms(
        project_id,
        works.id,
        {
            "basis_code": basis,
            "other_charge_estimate": None if basis == "de_bgb_648" else "40000",
            "source_note": "Demo terms",
        },
        actor_id=owner,
        role="admin",
    )

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
        },
        actor_id=owner,
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
        role="admin",
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
        actor_id=owner,
    )
    counts["items"] += 1
    await svc.add_precondition(
        project_id, design.id, kind="manual", ref_id=None, text="Client brief signed off", actor_id=owner
    )
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
        actor_id=owner,
    )
    counts["items"] += 1
    if other is not None:
        try:
            async with session.begin_nested():
                await svc.request_release(
                    project_id,
                    design.id,
                    amount="40000",
                    currency=ccy,
                    tranche_note="First tranche: concept design",
                    external_approval_ref="",
                    actor_id=other,
                    today=date.today(),
                )
            counts["releases"] += 1
        except Exception:
            logger.debug("commitment_release demo: first tranche not requested for %s", project_id, exc_info=True)
    return counts
