# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo procurement concept for the demo estate, run by ``app.core.demo_enrichment``.

Reads the package plan module 3's demo seeder wrote (``ContractPackage``), so
it must run after it; a demo project without a package plan is skipped, never
given an invented plan. Per project: a concept on the EU catalogue for a
public client (private clients get the neutral catalogue), award packages for
every package with an estimate, a procedure the threshold check allows, need
dates a few months out and supply lead times; one design package with a fee;
one long-lead supply as an advance package; a prequalification profile with
five criteria; candidates on the main works package (registered
subcontractors of the estate first, otherwise a long list of named
candidates still to be registered); three market soundings, one with a tight
capacity signal and its mitigation; and one framework agreement of the
project owner's company for supplies, called off by the supply package.

Company names are generic trade descriptions, never real firms. A project
that already has a concept is skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# (mod3 kind) -> (estimate EUR, procedure for a public client, procedure for a private one, lead days)
_DEFAULTS: dict[str, tuple[str, str, str, int]] = {
    "construction": ("2400000", "open", "restricted", 0),
    "design_and_construction": ("9800000", "competitive_negotiated", "two_stage_negotiated", 0),
    "design": ("420000", "competitive_negotiated", "restricted", 0),
    "supply": ("310000", "open", "request_for_quotation", 120),
    "supply_and_install": ("680000", "open", "restricted", 90),
    "management_services": ("260000", "restricted", "restricted", 0),
    "operation": ("150000", "open", "request_for_quotation", 0),
}
_FREE_NAMES = (
    "Regional structural works contractor",
    "Facade and envelope specialist",
    "Mechanical services installer",
    "General building contractor (mid-size)",
    "Precast concrete supplier",
)


async def seed_procurement_concept_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the concept of every demo project in ``project_ids`` that has a package plan and no concept."""
    from app.core.demo_marker import demo_id_of
    from app.modules.procurement_concept.models import ProcurementConcept
    from app.modules.projects.models import Project

    totals = {"projects": 0, "packages": 0, "candidates": 0, "soundings": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid, meta in rows:
        if not demo_id_of(meta):
            continue
        if (
            await session.execute(select(ProcurementConcept.id).where(ProcurementConcept.project_id == pid))
        ).scalar_one_or_none() is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("procurement_concept demo seed skipped for %s", pid, exc_info=True)
            continue
        if counts is None:
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int] | None:
    from app.modules.procurement_concept import plan_source as plan
    from app.modules.procurement_concept.catalogue import register_kind
    from app.modules.procurement_concept.models import (
        AwardPackage,
        BidderCandidate,
        CandidateScore,
        FrameworkAgreement,
        MarketSounding,
        PrequalProfile,
        ProcurementConcept,
        ProjectReference,
    )
    from app.modules.projects.models import Project
    from app.modules.subcontractors.models import Subcontractor

    register_kind()
    cps = await plan.list_packages(session, project_id)
    cps = [c for c in cps if c.kind in _DEFAULTS]
    if not cps:
        return None
    project = await session.get(Project, project_id)
    currency = (getattr(project, "currency", "") or "EUR").upper()
    _form, public = await plan.delivery_form(session, project_id)
    public = bool(public)
    today = datetime.now(UTC).date()
    concept = ProcurementConcept(
        project_id=project_id,
        catalogue_source="shipped",
        catalogue_id="eu" if public else "neutral",
        catalogue_version=1,
        jurisdiction="eu" if public else "none",
        client_type="sub_central" if public else "private",
        public_client=public,
        vat_rate_pct=Decimal("0"),
        state="draft",
        created_by=getattr(project, "owner_id", None),
    )
    session.add(concept)
    await session.flush()

    tenant = str(getattr(project, "owner_id", "") or "")
    framework = None
    if tenant:
        framework = (
            (
                await session.execute(
                    select(FrameworkAgreement).where(
                        FrameworkAgreement.tenant_id == tenant, FrameworkAgreement.code == "FW-SUPPLY-01"
                    )
                )
            )
            .scalars()
            .first()
        )
        if framework is None:
            framework = FrameworkAgreement(
                tenant_id=tenant,
                code="FW-SUPPLY-01",
                title="Reinforcement and precast supply framework",
                supplier_name="Precast concrete supplier",
                scope="Reinforcement steel, precast elements and delivery to site",
                package_kinds=["supply", "supply_and_install"],
                lots=[{"code": "L1", "title": "Reinforcement"}, {"code": "L2", "title": "Precast"}],
                max_value=Decimal("2500000"),
                currency=currency,
                start_date=(today - timedelta(days=200)).isoformat(),
                end_date=(today + timedelta(days=900)).isoformat(),
                call_off_mode="direct",
                source_procedure_ref="Open procedure, framework award 2025",
                state="active",
            )
            session.add(framework)
            await session.flush()

    awards: list[AwardPackage] = []
    advance_done = False
    framework_used = False
    for i, cp in enumerate(cps):
        value, pub_proc, priv_proc, lead = _DEFAULTS[cp.kind]
        need = today + timedelta(days=240 + 45 * i)
        row = AwardPackage(
            id=cp.id,
            project_id=project_id,
            split_basis="trade" if cp.kind == "construction" else "whole",
            estimated_value=Decimal(value),
            currency=currency,
            lot_group="",
            procedure_code=pub_proc if public else priv_proc,
            tender_basis="functional" if cp.kind == "design_and_construction" else "detailed",
            evaluation_method="best_value" if cp.kind in ("design", "design_and_construction") else "lowest_price",
            evaluation_weights={"price": "60", "quality": "40"}
            if cp.kind in ("design", "design_and_construction")
            else {},
            need_date=need.isoformat(),
            lead_time_days=lead or None,
            state="procedure_set",
        )
        if cp.kind == "supply" and framework is not None and not framework_used:
            row.framework_agreement_id = framework.id
            row.procedure_code = "framework_call_off"
            framework_used = True
        elif cp.kind in ("supply", "supply_and_install") and not advance_done:
            row.is_advance = True
            row.advance_reason = "Long lead item: fabrication slot must be reserved before the main tender"
            advance_done = True
        session.add(row)
        awards.append(row)
    await session.flush()

    profile = PrequalProfile(
        project_id=project_id,
        name="Standard works prequalification",
        criteria=[
            {"code": "exclusion_grounds", "kind": "pass_fail", "weight": "0"},
            {"code": "insurance_cover", "kind": "pass_fail", "weight": "0"},
            {"code": "similar_projects", "kind": "scored", "weight": "40"},
            {"code": "technical_capacity", "kind": "scored", "weight": "35"},
            {"code": "hse_record", "kind": "scored", "weight": "25"},
        ],
        pass_mark=Decimal("60"),
        validity_months=12,
    )
    session.add(profile)
    await session.flush()
    concept.default_profile_id = profile.id

    main = next(
        (a for a, c in zip(awards, cps, strict=True) if c.kind in ("construction", "design_and_construction")),
        awards[0],
    )
    subs = (await session.execute(select(Subcontractor).limit(4))).scalars().all()
    candidates = 0
    scores = [("88", "82", "75"), ("74", "70", "80"), ("65", "72", "68"), ("55", "50", "45")]
    for n, sub in enumerate(subs):
        lst = "short" if n < 3 else "excluded"
        c = BidderCandidate(
            project_id=project_id,
            package_id=main.id,
            subcontractor_id=sub.id,
            source="own_list" if n % 2 == 0 else "market_sounding",
            list_kind=lst,
            decision_rationale="" if lst == "short" else "Below the pass mark on similar projects and current workload",
        )
        session.add(c)
        await session.flush()
        s1, s2, s3 = scores[n]
        for code, passed, score in (
            ("exclusion_grounds", True, None),
            ("insurance_cover", True, None),
            ("similar_projects", None, s1),
            ("technical_capacity", None, s2),
            ("hse_record", None, s3),
        ):
            session.add(
                CandidateScore(
                    candidate_id=c.id,
                    criterion_code=code,
                    passed=passed,
                    score=None if score is None else Decimal(score),
                    evidence=[],
                )
            )
        session.add(
            ProjectReference(
                candidate_id=c.id,
                project_name="Four-storey school extension",
                client="Municipal client",
                value=Decimal("3100000"),
                currency=currency,
                year=today.year - 2,
                role="Main contractor",
            )
        )
        candidates += 1
    for name in _FREE_NAMES[len(subs) :]:
        session.add(
            BidderCandidate(project_id=project_id, package_id=main.id, free_name=name, source="market_sounding")
        )
        candidates += 1

    soundings = [
        MarketSounding(
            project_id=project_id,
            package_ids=[str(main.id)],
            trade="Structural works",
            held_on=(today - timedelta(days=30)).isoformat(),
            method="meeting",
            findings="Four regional contractors interested; two prefer a split into frame and finishes.",
            capacity_signal="adequate",
            price_signal="in_line",
        ),
        MarketSounding(
            project_id=project_id,
            package_ids=[
                str(a.id) for a, c in zip(awards, cps, strict=True) if c.kind in ("supply", "supply_and_install")
            ],
            trade="Steel and precast supply",
            held_on=(today - timedelta(days=21)).isoformat(),
            method="rfi",
            findings="Mill slots booked for nine months; prices rising.",
            capacity_signal="tight",
            price_signal="above_estimate",
            lead_time_signal_days=150,
            mitigation="Advance package to reserve the fabrication slot; framework call-off for reinforcement.",
        ),
        MarketSounding(
            project_id=project_id,
            package_ids=[],
            trade="Mechanical services",
            held_on=(today - timedelta(days=10)).isoformat(),
            method="survey",
            findings="Six installers responded, three with capacity from next spring.",
            capacity_signal="ample",
            price_signal="below_estimate",
        ),
    ]
    for s in soundings:
        session.add(s)
    await session.flush()
    return {"packages": len(awards), "candidates": candidates, "soundings": len(soundings)}
