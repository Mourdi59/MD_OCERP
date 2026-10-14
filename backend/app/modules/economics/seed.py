# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo economics for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project that has a priced bill gets a plan an owner would actually
take to the gate: a cost frame cut from the codes its bill uses (every group
rounded up to the next 100 000 so the frame carries a little headroom over the
estimate, and the bill's markups rounded up the same way as the allowance), a
business case in the project's own terms, and a financing plan whose sources
add up to the frame to the cent, the lender's share being the exact remainder.
The figures are derived from the bill, never typed in, so they follow the
estimate when the demo bill changes.

The plan is left in draft. Approval happens at the governance gate, or by hand
on a project without gates, never in a seeder.

Only projects carrying the demo marker are touched, and only those the profiles
below know; a project that already has frame lines or sources is skipped, so a
re-run never duplicates. Runs after the governance and contracts seeders.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

D = Decimal
PROPOSAL_NOTE = "Cost frame, business case and financing agreed with the client and the lenders."
STEP = D("100000")


@dataclass(frozen=True)
class Application:
    """The funding application behind a grant or subsidy source, and the programme it was made under."""

    code: str
    title: str
    programme_code: str
    programme_name: str
    authority: str
    region: str
    status: str  # submitted | approved
    submitted_on: str
    decided_on: str = ""
    expected_on: str = ""
    reference: str = ""


@dataclass(frozen=True)
class Source:
    kind: str
    name: str
    share: str | None  # share of the frame as a decimal, or None for the exact remainder
    due: tuple[str, ...]  # tranche dates, the amount split evenly, the last tranche taking the cent remainder
    rate: str | None = None
    condition: str = ""
    application: Application | None = None


@dataclass(frozen=True)
class Profile:
    discount_pct: str
    horizon: int
    build_years: int
    flows: tuple[tuple[str, str, str, int, int | None, str], ...]  # kind, label, amount, from, to, escalation
    sources: tuple[Source, ...]
    approve: bool = False  # the story has reached the decision: the plan is approved, else it waits in review


PROFILES: dict[str, Profile] = {
    # 120 flats, 11 000 m2 living area, 110 parking spaces: rent 12.00 EUR/m2 a month, parking 95 EUR a month,
    # costs of operation and upkeep about a fifth of the rent, a long holding horizon with a residual value.
    "residential-regensburg": Profile(
        approve=True,
        discount_pct="3.0",
        horizon=40,
        build_years=3,
        flows=(
            ("revenue", "Residential rent", "1584000", 3, None, "2.0"),
            ("revenue", "Parking rent", "125400", 3, None, "2.0"),
            ("operating_cost", "Operation, upkeep and management", "376000", 3, None, "2.0"),
            ("residual", "Residual value of land and building", "24000000", 40, 40, "0"),
        ),
        sources=(
            Source(
                "equity",
                "Own funds including the plot",
                "0.25",
                ("2026-11-02", "2027-06-01"),
                None,
                "Plot at book value",
            ),
            Source("bank_loan", "KfW promotional loan", "0.20", ("2027-03-01", "2028-03-01", "2029-03-01"), "1.9"),
            Source(
                "subsidy",
                "State housing subsidy",
                "0.12",
                ("2027-09-01", "2028-09-01", "2029-05-01"),
                None,
                "Paid on certified progress",
                Application(
                    code="FA-2026-001",
                    title="Mietwohnraumförderung, Neubau Donauknie",
                    programme_code="BAY-WOHNRAUM",
                    programme_name="Bayerisches Wohnraumförderungsprogramm, Mietwohnraum",
                    authority="Regierung von Oberbayern, Wohnraumförderung",
                    region="DE-BY",
                    status="approved",
                    submitted_on="2026-02-18",
                    decided_on="2026-06-30",
                    reference="WF-2026-04417",
                ),
            ),
            Source("bank_loan", "Bank loan", None, ("2027-01-15", "2027-10-15", "2028-06-15", "2029-02-15"), "3.9"),
        ),
    ),
    # A school earns no rent: the benefit is the temporary classroom leasing it replaces and the income from hiring
    # the hall, set against an operating cost of about 52 EUR/m2 of gross floor area. The case is a public one, so a
    # negative net present value is the honest figure.
    "school-ludwigsburg": Profile(
        discount_pct="2.0",
        horizon=40,
        build_years=3,
        flows=(
            ("revenue", "Avoided leasing of temporary classrooms", "640000", 3, None, "1.5"),
            ("revenue", "Hall and canteen use by third parties", "120000", 3, None, "1.5"),
            ("operating_cost", "Operation and upkeep", "546000", 3, None, "2.0"),
            ("residual", "Residual value of the building", "9000000", 40, 40, "0"),
        ),
        sources=(
            Source("equity", "Municipal budget", "0.35", ("2026-12-01", "2027-09-01", "2028-09-01")),
            Source(
                "grant",
                "State school building grant",
                "0.30",
                ("2027-06-01", "2028-06-01", "2029-03-01"),
                None,
                "Paid on proof of use",
                Application(
                    code="FA-2026-001",
                    title="Neubau Schule, Förderantrag Land",
                    programme_code="BW-SCHULBAU",
                    programme_name="Schulbauförderung Baden-Württemberg",
                    authority="Regierungspräsidium Stuttgart, Schulbauförderung",
                    region="DE-BW",
                    status="approved",
                    submitted_on="2026-03-12",
                    decided_on="2026-09-08",
                    reference="SB-2026-0873",
                ),
            ),
            Source(
                "grant",
                "Federal all-day school programme",
                "0.10",
                ("2028-03-01", "2029-03-01"),
                None,
                "",
                Application(
                    code="FA-2026-002",
                    title="Ganztagsausbau, Mittelanforderung Bund",
                    programme_code="DE-GANZTAG",
                    programme_name="Investitionsprogramm Ganztagsausbau",
                    authority="Bund, über das Land Baden-Württemberg",
                    region="DE",
                    status="submitted",
                    submitted_on="2026-09-21",
                    expected_on="2027-01-29",
                ),
            ),
            Source("bank_loan", "Municipal loan", None, ("2027-03-01", "2028-03-01", "2029-01-15"), "2.6"),
        ),
    ),
}


def round_up(value: Decimal) -> Decimal:
    """``value`` up to the next whole step of 100 000; a zero stays zero."""
    return (value / STEP).to_integral_value(rounding=ROUND_CEILING) * STEP


def split(total: Decimal, parts: int) -> list[Decimal]:
    """``total`` in ``parts`` equal amounts to the cent, the last one taking the remainder, so they add up exactly."""
    each = (total / parts).quantize(D("0.01"))
    amounts = [each] * (parts - 1)
    amounts.append(total - sum(amounts, D(0)))
    return amounts


async def seed_economics_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, Any]:
    """Seed the economics of every demo project in ``project_ids`` that has a profile and a bill. The caller commits.

    Returns counts plus ``failed`` (projects whose seed raised and was rolled back), ``skipped`` (projects
    left alone, with the reason) and ``ok`` (no failure).
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.economics.repository import EconomicsRepository
    from app.modules.projects.models import Project

    totals: dict[str, Any] = {
        "projects": 0,
        "frame_lines": 0,
        "flow_lines": 0,
        "sources": 0,
        "tranches": 0,
        "applications": 0,
        "proposed": 0,
        "approved": 0,
        "skipped": [],
        "failed": [],
        "ok": True,
    }
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (
        await session.execute(select(Project.id, Project.owner_id, Project.metadata_).where(Project.id.in_(ids)))
    ).all()
    for pid, owner, meta in rows:
        profile = PROFILES.get(demo_id_of(meta))
        if profile is None:
            continue
        repo = EconomicsRepository(session)
        if await repo.frame_lines(pid) or await repo.sources(pid):
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid, owner, profile)
        except _NoBill:
            totals["skipped"].append({"project_id": str(pid), "reason": "no_bill"})
            continue
        except Exception as exc:
            logger.error("economics demo seed failed for %s and was rolled back", pid, exc_info=True)
            totals["failed"].append({"project_id": str(pid), "reason": type(exc).__name__})
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    totals["ok"] = not totals["failed"]
    return totals


class _NoBill(Exception):
    """The project has no priced bill to cut a frame from."""


async def _seed_project(
    session: AsyncSession, pid: uuid.UUID, owner: uuid.UUID | None, profile: Profile
) -> dict[str, int]:
    from app.modules.economics import readings
    from app.modules.economics.service import EconomicsService

    service = EconomicsService(session)
    plan = await service.start(pid, owner)
    bill = await readings.read_bill(session, pid, plan.classification_standard, plan.boq_id)
    if bill is None or bill.direct_cost <= 0:
        raise _NoBill
    await service.patch_plan(
        pid,
        {
            "discount_rate_pct": D(profile.discount_pct),
            "horizon_years": profile.horizon,
            "markup_allowance": round_up(bill.markups_total),
        },
        owner,
    )
    frame = await service.generate_frame(pid, depth=1, amounts="estimate", replace=True, actor_id=owner)
    for line in frame:
        line.amount = round_up(line.amount)
    await session.flush()
    frame_total = sum((f.amount for f in frame), D(0)) + round_up(bill.markups_total)

    await service.add_flow_line(
        pid,
        {
            "kind": "investment",
            "label": "Construction and project costs",
            "source": "cost_frame",
            "year_from": 0,
            "year_to": profile.build_years - 1,
        },
        owner,
    )
    for kind, label, amount, year_from, year_to, escalation in profile.flows:
        await service.add_flow_line(
            pid,
            {
                "kind": kind,
                "label": label,
                "amount": D(amount),
                "year_from": year_from,
                "year_to": year_to,
                "escalation_pct": D(escalation),
            },
            owner,
        )

    tranches = 0
    given = D(0)
    for source in profile.sources:
        amount = (frame_total - given) if source.share is None else (frame_total * D(source.share)).quantize(D("0.01"))
        given += amount
        application_id = None
        if source.application is not None:
            application_id = await _application(session, pid, source.application, amount, frame_total)
        row = await service.add_source(
            pid,
            {
                "kind": source.kind,
                "name": source.name,
                "amount": amount,
                "interest_rate_pct": D(source.rate) if source.rate is not None else None,
                "funding_application_id": application_id,
            },
            owner,
        )
        for due, part in zip(source.due, split(amount, len(source.due)), strict=True):
            await service.add_tranche(
                pid, row.id, {"due_on": due, "amount": part, "condition": source.condition}, owner
            )
            tranches += 1
    status = await _settle(session, service, pid, owner, profile)
    return {
        "frame_lines": len(frame),
        "flow_lines": len(profile.flows) + 1,
        "sources": len(profile.sources),
        "tranches": tranches,
        "applications": sum(1 for x in profile.sources if x.application is not None),
        "proposed": int(status in ("proposed", "approved")),
        "approved": int(status == "approved"),
    }


async def _application(
    session: AsyncSession, pid: uuid.UUID, app: Application, amount: Decimal, frame_total: Decimal
) -> uuid.UUID:
    """The funding application of a grant source, filed under its programme (created once as reference data)."""
    from app.modules.funding.models import FundingApplication, FundingProgramme
    from app.modules.projects.models import Project

    country = app.region[:2]
    programme = (
        await session.execute(
            select(FundingProgramme).where(
                FundingProgramme.code == app.programme_code, FundingProgramme.country == country
            )
        )
    ).scalar_one_or_none()
    if programme is None:
        programme = FundingProgramme(
            code=app.programme_code,
            name=app.programme_name,
            authority_name=app.authority,
            authority_level="national" if app.region == country else "regional",
            country=country,
            region_code=app.region if app.region != country else "",
            instrument="grant",
            currency="EUR",
            status="open",
        )
        session.add(programme)
        await session.flush()
    project = await session.get(Project, pid)
    client = ((project.metadata_ or {}).get("client") if project is not None else "") or ""
    approved = app.status == "approved"
    row = FundingApplication(
        project_id=pid,
        programme_id=programme.id,
        code=app.code,
        title=app.title,
        applicant_name=str(client),
        applicant_type="company",
        status=app.status,
        eligible_cost_base=frame_total,
        requested_amount=amount,
        own_share_amount=frame_total - amount,
        currency="EUR",
        submitted_on=app.submitted_on,
        decision_expected_on=app.expected_on or app.decided_on,
        decided_on=app.decided_on,
        award_reference=app.reference,
        approved_amount=amount if approved else Decimal("0"),
    )
    session.add(row)
    await session.flush()
    return row.id


async def _settle(
    session: AsyncSession, service: Any, pid: uuid.UUID, owner: uuid.UUID | None, profile: Profile
) -> str:
    """Propose the plan as a team member, and let the governance decision approve it when the story reached it.

    Under four-eyes the proposer is never the person who decides, so the proposal is made by a member other
    than the gate decider where the team has one. A plan whose gate has been decided is approved by the
    service's own binding rule: the proposal is dated just before that decision, as it would have been made.
    Without gates a different team member approves by hand. Where none of that is possible the plan stays
    proposed, which is the honest state.
    """
    from datetime import timedelta

    from app.modules.economics import hosting
    from app.modules.teams.models import Team, TeamMembership

    members = list(
        (
            await session.execute(
                select(TeamMembership.user_id)
                .join(Team, Team.id == TeamMembership.team_id)
                .where(Team.project_id == pid)
            )
        )
        .scalars()
        .all()
    )
    gates = await hosting.gates_in_use(session, pid)
    doc = (await hosting.carrier_document(session, pid))[0] if gates else None
    decision = None
    if doc is not None and doc.status == "binding" and doc.approved_gate_id is not None:
        decision = await hosting.latest_gate_decision(session, pid, doc.approved_gate_id, ("go", "go_with_conditions"))
    decider = getattr(decision, "decided_by", None)
    proposer = next((m for m in members if m != decider), owner)
    try:
        await service.propose(pid, PROPOSAL_NOTE, proposer)
    except Exception:
        logger.warning("economics demo seed: the plan of %s could not be proposed", pid, exc_info=True)
        return "draft"
    plan = await service.require_plan(pid)
    if not profile.approve:
        return plan.status
    if gates:
        if decision is None or decider is None or decider == proposer:
            return plan.status
        approval = await service.repo.approval(pid, plan.current_approval_id)
        if decision.decided_at is not None and approval is not None:
            approval.proposed_at = decision.decided_at - timedelta(days=3)
            await session.flush()
        await service.sync_with_governance(pid)
    else:
        approver = next((m for m in members if m != proposer), None)
        if approver is not None:
            await service.approve_by_hand(pid, approver)
    return (await service.require_plan(pid)).status
