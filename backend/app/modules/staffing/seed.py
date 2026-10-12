# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo staffing plan for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the staffing catalogue its country resolves to and the
plan a project lead would actually be working on: the execution-phase key
roles planned from the catalogue, the commissioning manager added for the
handover into operation, the first people of the project roster on those
positions, and their personnel files with the documents the roles require.
One person needs a work permit that runs out in about three weeks, so the
expiry reminder and the compliance matrix have something to show; one
mobilisation trip and one approved annual leave fill the upcoming view.

The plan stays ``draft``: submission and approval go through the governance
gate of the personnel area, never through a seeder. People come from the
teams roster (seeded first when the project has none), so no name is invented
here. Only projects carrying the demo marker are touched; a project that
already has a plan is skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

EXECUTION_ROLES = ["project_manager", "site_manager", "hse_manager", "site_supervisor_civil", "document_controller"]
# The person whose work permit lapses soon (index into the filled roles above).
PERMIT_HOLDER = 3
PERMIT_EXPIRES_IN_DAYS = 20


async def seed_staffing_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the staffing plan of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.projects.models import Project
    from app.modules.staffing.models import StaffingPlan

    totals = {"projects": 0, "positions": 0, "fills": 0, "files": 0, "documents": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (
            await session.execute(select(StaffingPlan.id).where(StaffingPlan.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("staffing demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.credentials.models import Credential
    from app.modules.projects.models import Project
    from app.modules.staffing.models import StaffingPosition
    from app.modules.staffing.service import Actor, StaffingService
    from app.modules.teams.models import RosterMember
    from app.modules.teams.seed import seed_teams_roster

    await seed_teams_roster(session, project_id=project_id)
    members = list(
        (
            await session.execute(
                select(RosterMember).where(RosterMember.project_id == project_id).order_by(RosterMember.created_at, RosterMember.id)
            )
        ).scalars()
    )
    project = await session.get(Project, project_id)
    owner = project.owner_id
    actor = Actor(owner, {"role": "admin"})
    svc = StaffingService(session)
    today = datetime.now(UTC).date()
    start = today - timedelta(days=30)

    await svc.set_plan(project_id, actor_id=owner, tenant_id=None, commissioning_date=today + timedelta(days=420))
    positions = await svc.positions_from_catalogue(project_id, "execution", EXECUTION_ROLES, start, owner)
    commissioning = await svc.create_position(
        project_id,
        {"role_code": "commissioning_manager", "phase": "execution", "entry_date": today + timedelta(days=300)},
        owner,
    )
    for p in [*positions, commissioning]:
        row = await svc._child(StaffingPosition, project_id, p.id, "position_not_found")
        row.owner_user_id = owner
    await session.flush()

    catalogue = await svc.catalogue_for(await svc.require_plan(project_id))
    by_role = {p.role_code: p for p in positions}
    counts = {"positions": len(positions) + 1, "fills": 0, "files": 0, "documents": 0}
    fills = {}
    for index, (role_code, member) in enumerate(zip(EXECUTION_ROLES, members, strict=False)):
        position = by_role.get(role_code)
        if position is None:
            continue
        fill = await svc.create_fill(
            project_id, position.id, {"roster_member_id": member.id, "fte_share": "1", "from_date": start}, owner
        )
        await svc.confirm_fill(project_id, fill.id, owner)
        fills[role_code] = fill
        counts["fills"] += 1

        needs_permit = index == PERMIT_HOLDER
        pfile = await svc.create_file(
            project_id,
            {
                "roster_member_id": member.id,
                "employer_organisation": member.company_name or "",
                "employment_basis": "employee",
                "nationality_required": needs_permit,
                "lawful_basis": "contract",
            },
            actor,
        )
        counts["files"] += 1
        role = catalogue.role(role_code)
        kinds = list(role.required_document_kinds if role else [])
        if needs_permit:
            kinds.append("work_permit")
        for kind_code in kinds:
            kind = catalogue.document_kind(kind_code)
            if kind is None:
                continue
            if kind_code == "work_permit":
                valid_until = today + timedelta(days=PERMIT_EXPIRES_IN_DAYS)
            elif kind.credential_type in ("employment_contract", "certification"):
                valid_until = None
            else:
                valid_until = today + timedelta(days=365)
            cred = Credential(
                project_id=project_id,
                holder_name=member.display_name or "",
                holder_kind="person",
                credential_type=kind.credential_type,
                issued_at=start - timedelta(days=30),
                valid_until=valid_until,
                notify_days_before=kind.default_notify_days_before,
            )
            session.add(cred)
            await session.flush()
            await svc.link_document(
                project_id,
                pfile.id,
                {
                    "document_kind": kind_code,
                    "credential_id": cred.id,
                    "number_last4": "4821" if kind.store_number else None,
                    "fit_for_role": "yes" if kind_code == "occupational_health_certificate" else None,
                },
                actor,
            )
            counts["documents"] += 1
        if index == 1:
            await svc.create_travel(
                project_id,
                pfile.id,
                {
                    "kind": "rotation",
                    "from_place": "Home city",
                    "to_place": "Site",
                    "depart_date": today + timedelta(days=9),
                    "return_date": today + timedelta(days=23),
                    "cost": "380.00",
                    "currency": getattr(project, "currency", "") or "EUR",
                },
                actor,
            )
        if index == 4:
            leave, _warnings = await svc.create_leave(
                project_id,
                pfile.id,
                {
                    "leave_type": "annual",
                    "from_date": today + timedelta(days=40),
                    "to_date": today + timedelta(days=51),
                },
                actor,
            )
            await svc.set_leave_status(project_id, pfile.id, leave.id, "approved", actor)

    if "project_manager" in fills:
        await svc.create_handover(
            project_id,
            {
                "from_fill_id": fills["project_manager"].id,
                "to_position_id": commissioning.id,
                "overlap_days": 30,
                "scope": "Open punch items, commissioning sequence, operator training schedule.",
            },
            owner,
        )
    return counts
