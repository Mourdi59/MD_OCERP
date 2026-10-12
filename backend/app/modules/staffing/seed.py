# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo staffing plan for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the staffing catalogue its country resolves to and the
plan a project lead would be working on a month into construction:

* development: the owner's lead team, on the project for eight months;
* execution: the site team that started a month ago, one person arriving in
  ten days, one position open and one being recruited through a resource
  request;
* operation: the operator's build-up before commissioning, still open, with
  the knowledge handovers into it already linked.

Nothing a submission would refuse is left in the plan. Every person on a
confirmed position has a personnel file with the documents their role asks
for, recorded through the service so each validity record carries its derived
status from the first day. Three documents run out inside 30, 60 and 90 days,
one required document is missing and one is waived, so the compliance matrix
and the upcoming view show every state. Travel (one trip done, one
mobilisation next week, one rotation) and leave (one approved, one requested)
fill the rest. Money is in the project's own currency; a project without one
gets its trips without a cost.

The plan stays ``draft``: submission and approval go through the governance
gate, never through a seeder. People come from the teams roster (seeded first
when the project has none), so no name is invented here. Only projects
carrying the demo marker are touched; a project that already has a plan is
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

# (role, phase, entry offset in days from today, exit offset or None, stored status)
POSITIONS: tuple[tuple[str, str, int, int | None, str], ...] = (
    ("project_director", "development", -240, None, "open"),
    ("project_manager", "development", -240, None, "open"),
    ("design_manager", "development", -240, None, "open"),
    ("cost_manager", "development", -210, None, "open"),
    ("contract_manager", "development", -180, None, "open"),
    ("site_manager", "execution", -30, None, "open"),
    ("hse_manager", "execution", -30, None, "open"),
    ("site_supervisor_civil", "execution", -30, None, "open"),
    ("document_controller", "execution", 10, None, "open"),
    ("quality_manager", "execution", 30, None, "open"),
    ("site_supervisor_mep", "execution", 45, 400, "recruiting"),
    ("commissioning_manager", "execution", 300, None, "open"),
    ("operator_plant_manager", "operation", 330, None, "open"),
    ("operator_shift_lead", "operation", 360, None, "open"),
)
# One roster member per role, in roster order; the roles further down stay vacant.
FILLED = (
    "project_director",
    "project_manager",
    "design_manager",
    "cost_manager",
    "contract_manager",
    "site_manager",
    "hse_manager",
    "site_supervisor_civil",
    "document_controller",
)
COMMISSIONING_IN_DAYS = 420
PERMIT_HOLDER = "site_supervisor_civil"
# (role, document kind) -> days until the document expires. The three windows of the upcoming view.
EXPIRING: dict[tuple[str, str], int] = {
    (PERMIT_HOLDER, "work_permit"): 20,
    ("hse_manager", "safety_training"): 45,
    ("site_manager", "occupational_health_certificate"): 80,
}
MISSING = ("hse_manager", "qualification")
WAIVED = ("site_manager", "professional_licence")
# Kinds without an end date: a contract runs until the assignment ends.
OPEN_ENDED = ("employment_contract",)
HANDOVERS = (
    ("project_manager", "operator_plant_manager", 30, "Open items, commissioning sequence, operator training plan."),
    ("design_manager", "commissioning_manager", 20, "Design intent, test and acceptance criteria, as-built status."),
)


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
            # One project that cannot be seeded must not take the rest of the demo estate with it.
            logger.warning("staffing demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


def _day(today: date, offset: int | None) -> date | None:
    return None if offset is None else today + timedelta(days=offset)


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.projects.models import Project
    from app.modules.staffing import rules
    from app.modules.staffing.service import Actor, StaffingService
    from app.modules.teams.models import RosterMember
    from app.modules.teams.seed import seed_teams_roster

    await seed_teams_roster(session, project_id=project_id)
    members = list(
        (
            await session.execute(
                select(RosterMember)
                .where(RosterMember.project_id == project_id)
                .order_by(RosterMember.created_at, RosterMember.id)
            )
        ).scalars()
    )
    project = await session.get(Project, project_id)
    owner = project.owner_id
    # The project owner plans the demo and is the line manager of every position, which is what lets
    # them open the files. The erase permission is not needed and not taken.
    actor = Actor(owner, personnel_read=True, personnel_edit=True, assign_owner=True, manage=True)
    currency = (getattr(project, "currency", "") or "").strip()
    priced = len(currency) == 3 and currency.isalpha()
    svc = StaffingService(session)
    today = datetime.now(UTC).date()

    await svc.set_plan(
        project_id,
        actor_id=owner,
        tenant_id=None,
        commissioning_date=today + timedelta(days=COMMISSIONING_IN_DAYS),
    )
    catalogue = await svc.catalogue_for(await svc.require_plan(project_id))
    counts = {"positions": 0, "fills": 0, "files": 0, "documents": 0}

    positions: dict[str, Any] = {}
    for role_code, phase, entry, leaving, status in POSITIONS:
        if catalogue.role(role_code) is None:
            continue
        row = await svc.create_position(
            project_id,
            {
                "role_code": role_code,
                "phase": phase,
                "entry_date": _day(today, entry),
                "exit_date": _day(today, leaving),
                "owner_user_id": owner,
                "recruiting_channel": "agency" if status == "recruiting" else None,
            },
            actor,
        )
        if status != "open":
            await svc.set_position_status(project_id, row.id, status, owner)
        if status == "recruiting":
            await svc.request_resource(project_id, row.id, owner)
        positions[role_code] = row
        counts["positions"] += 1

    fills: dict[str, Any] = {}
    files: dict[str, Any] = {}
    for role_code, member in zip([r for r in FILLED if r in positions], members, strict=False):
        position = positions[role_code]
        fill = await svc.create_fill(
            project_id,
            position.id,
            {"roster_member_id": member.id, "fte_share": str(position.fte), "from_date": position.entry_date},
            owner,
        )
        await svc.confirm_fill(project_id, fill.id, actor)
        fills[role_code] = fill
        counts["fills"] += 1

        needs_permit = role_code == PERMIT_HOLDER
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
        files[role_code] = pfile
        counts["files"] += 1
        hired = position.entry_date - timedelta(days=30)
        for kind_code in rules.required_document_kinds(catalogue, [role_code], "employee", needs_permit):
            kind = catalogue.document_kind(kind_code)
            if kind is None or (role_code, kind_code) == MISSING:
                continue
            if (role_code, kind_code) == WAIVED:
                await svc.waive_document(
                    project_id,
                    pfile.id,
                    kind_code,
                    "Renewal filed with the registration body; confirmation of receipt is on file.",
                    actor,
                )
                continue
            if kind_code in OPEN_ENDED:
                valid_until = None
            else:
                valid_until = today + timedelta(days=EXPIRING.get((role_code, kind_code), 400))
            await svc.record_document(
                project_id,
                pfile.id,
                {
                    "document_kind": kind_code,
                    "issued_at": hired,
                    "valid_until": valid_until,
                    "number_last4": "4821" if kind.store_number else None,
                    "fit_for_role": "yes" if kind_code == "occupational_health_certificate" else None,
                },
                actor,
            )
            counts["documents"] += 1

    def trip(kind: str, depart: int, back: int | None, amount: str) -> dict[str, Any]:
        priced_part = {"cost": amount, "currency": currency} if priced else {}
        return {
            "kind": kind,
            "from_place": "Home city",
            "to_place": "Site",
            "depart_date": today + timedelta(days=depart),
            "return_date": _day(today, back),
            **priced_part,
        }

    if "document_controller" in files:
        # Arrives one day before the first working day.
        await svc.create_travel(
            project_id, files["document_controller"].id, trip("mobilisation", 9, None, "380.00"), actor
        )
    if "site_manager" in files:
        await svc.create_travel(project_id, files["site_manager"].id, trip("rotation", 20, 34, "240.00"), actor)
    if "project_manager" in files:
        done = await svc.create_travel(
            project_id, files["project_manager"].id, trip("business", -20, -18, "510.00"), actor
        )
        for status in ("booked", "done"):
            await svc.update_travel(project_id, files["project_manager"].id, done.id, {"status": status}, actor)
    if "cost_manager" in files:
        leave, _warnings = await svc.create_leave(
            project_id,
            files["cost_manager"].id,
            {
                "leave_type": "annual",
                "from_date": today + timedelta(days=40),
                "to_date": today + timedelta(days=51),
            },
            actor,
        )
        await svc.set_leave_status(project_id, files["cost_manager"].id, leave.id, "approved", actor)
    if "design_manager" in files:
        await svc.create_leave(
            project_id,
            files["design_manager"].id,
            {
                "leave_type": "training",
                "from_date": today + timedelta(days=15),
                "to_date": today + timedelta(days=17),
            },
            actor,
        )

    for giver, receiver, overlap, scope in HANDOVERS:
        if giver in fills and receiver in positions:
            await svc.create_handover(
                project_id,
                {
                    "from_fill_id": fills[giver].id,
                    "to_position_id": positions[receiver].id,
                    "overlap_days": overlap,
                    "scope": scope,
                },
                owner,
            )
    return counts
