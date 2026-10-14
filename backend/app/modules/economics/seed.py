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
STEP = D("100000")


@dataclass(frozen=True)
class Source:
    kind: str
    name: str
    share: str | None  # share of the frame as a decimal, or None for the exact remainder
    due: tuple[str, ...]  # tranche dates, the amount split evenly, the last tranche taking the cent remainder
    rate: str | None = None
    condition: str = ""


@dataclass(frozen=True)
class Profile:
    discount_pct: str
    horizon: int
    build_years: int
    flows: tuple[tuple[str, str, str, int, int | None, str], ...]  # kind, label, amount, from, to, escalation
    sources: tuple[Source, ...]


PROFILES: dict[str, Profile] = {
    # 120 flats, 11 000 m2 living area, 110 parking spaces: rent 12.00 EUR/m2 a month, parking 95 EUR a month,
    # costs of operation and upkeep about a fifth of the rent, a long holding horizon with a residual value.
    "residential-regensburg": Profile(
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
            ),
            Source("grant", "Federal all-day school programme", "0.10", ("2028-03-01", "2029-03-01")),
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
        row = await service.add_source(
            pid,
            {
                "kind": source.kind,
                "name": source.name,
                "amount": amount,
                "interest_rate_pct": D(source.rate) if source.rate is not None else None,
            },
            owner,
        )
        for due, part in zip(source.due, split(amount, len(source.due)), strict=True):
            await service.add_tranche(
                pid, row.id, {"due_on": due, "amount": part, "condition": source.condition}, owner
            )
            tranches += 1
    return {
        "frame_lines": len(frame),
        "flow_lines": len(profile.flows) + 1,
        "sources": len(profile.sources),
        "tranches": tranches,
    }
