# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo procurement concept for the demo estate, run by ``app.core.demo_enrichment``.

Reads the package plan module 3's demo seeder wrote (``ContractPackage``), so
it must run after it; a demo project without a package plan is skipped, never
given an invented plan, and so is a project without a currency.

Per project:

* the concept. A public client whose country has a shipped catalogue in the
  project's own currency gets that catalogue and a public client type. Every
  other project is planned under the neutral catalogue as a private client:
  there is no threshold regime this seed could honestly apply to it;
* award packages for every package, with estimates sized to the project
  currency, a procedure the threshold check allows, need dates a few months out
  and supply lead times; one design package with a fee;
* one long-lead supply as an advance package, but only when the project's
  governance demo data holds a cleared gate condition to release it. The seed
  never writes a governance decision or condition of its own;
* a prequalification profile with five criteria; candidates on the main works
  package from the demo subcontractor register (in a fixed order), topped up
  with named candidates still to be registered;
* three market soundings, one with a tight capacity signal and its mitigation;
* one framework agreement of the project owner's company, called off by a
  supply package.

The concept is left as a draft with no blocking finding, so it can be
submitted and taken through the governance gate. Company names are generic
trade descriptions, never real firms. A project that already has a concept is
skipped, so a re-run never duplicates.
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

# Demo subcontractors are the ones the subcontractors demo seeder wrote: they alone sit on this reserved
# documentation domain. A company a user registered is never put on a demo short list.
_DEMO_SUBCONTRACTOR_SITE = "https://contractor-%.example.com"
# Rough size of one unit of the base estimates in each currency, so a demo project in yen or rupees shows
# plausible figures. Orders of magnitude for demo data, not exchange rates; unlisted currencies use 1.
_MAGNITUDE: dict[str, int] = {
    "JPY": 150,
    "INR": 90,
    "RUB": 100,
    "NGN": 1500,
    "HUF": 400,
    "CZK": 25,
    "TRY": 40,
    "CNY": 8,
    "BRL": 6,
    "SEK": 11,
    "NOK": 11,
    "DKK": 7,
    "PLN": 4,
    "AED": 4,
    "SAR": 4,
    "BGN": 2,
}
_PUBLIC_CLIENT_TYPES = ("sub_central", "central")

# (mod3 kind) -> (base estimate, procedure for a public client, procedure for a private one, lead days)
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
    currency = (getattr(project, "currency", "") or "").upper()
    if not currency:
        # No currency is ever assumed for an amount.
        return None
    scale = _MAGNITUDE.get(currency, 1)
    _form, mod3_public = await plan.delivery_form(session, project_id)
    regime = _regime_for(getattr(project, "country_code", None), currency) if mod3_public else None
    public = regime is not None
    catalogue, jurisdiction, client_type = regime or _neutral_regime()
    today = datetime.now(UTC).date()
    release = await _cleared_release(session, project_id)
    concept = ProcurementConcept(
        project_id=project_id,
        catalogue_source="shipped",
        catalogue_id=catalogue.id,
        catalogue_version=catalogue.version,
        jurisdiction=jurisdiction,
        client_type=client_type,
        public_client=public,
        vat_rate_pct=Decimal("0"),
        # The gate the cleared condition belongs to released procurement in the demo story.
        release_gate_code=release.gate_code if release is not None else "",
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
                max_value=Decimal("2500000") * scale,
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
            estimated_value=Decimal(value) * scale,
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
        elif cp.kind in ("supply", "supply_and_install") and not advance_done and release is not None:
            # Only with a cleared condition to release it: an advance package that can never be released
            # would block the demo concept for good.
            row.is_advance = True
            row.advance_reason = "Long lead item: fabrication slot must be reserved before the main tender"
            row.advance_release_kind = "condition"
            row.advance_release_id = release.id
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
    subs = (
        (
            await session.execute(
                select(Subcontractor)
                .where(Subcontractor.website.like(_DEMO_SUBCONTRACTOR_SITE), Subcontractor.is_active.is_(True))
                .order_by(Subcontractor.tax_id, Subcontractor.legal_name)
                .limit(4)
            )
        )
        .scalars()
        .all()
    )
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
                value=Decimal("3100000") * scale,
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


def _shipped_catalogues() -> list:
    from app.modules.procurement_concept.catalogue import PROCUREMENT_KIND, register_kind
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    kind = get_catalogue_kind(PROCUREMENT_KIND)
    return sorted(kind.shipped(), key=lambda c: c.id)


def _neutral_regime() -> tuple:
    """``(catalogue, jurisdiction, client type)`` of a client under no threshold regime."""
    from app.modules.procurement_concept.catalogue import DEFAULT_CATALOGUE_ID

    neutral = next(c for c in _shipped_catalogues() if c.id == DEFAULT_CATALOGUE_ID)
    juris = neutral.jurisdictions[0]
    return neutral, juris.code, juris.private_client_type


def _regime_for(country: str | None, currency: str) -> tuple | None:
    """The shipped regime of a public client in ``country`` whose thresholds are in ``currency``.

    ``None`` when no shipped catalogue covers the country in that currency:
    its thresholds could not be compared with the project's amounts.
    """
    code = (country or "").upper()
    if not code:
        return None
    for catalogue in _shipped_catalogues():
        if code not in {c.upper() for c in catalogue.jurisdiction_countries}:
            continue
        for juris in catalogue.jurisdictions:
            currencies = {t.currency.upper() for t in juris.thresholds}
            client_type = next((ct for ct in _PUBLIC_CLIENT_TYPES if ct in juris.client_types), None)
            if currencies == {currency} and client_type is not None:
                return catalogue, juris.code, client_type
    return None


async def _cleared_release(session: AsyncSession, project_id: uuid.UUID):
    """A cleared gate condition of the project's governance demo data, or ``None``. Nothing is written."""
    from app.modules.project_governance.models import GovernanceCondition

    return (
        (
            await session.execute(
                select(GovernanceCondition)
                .where(GovernanceCondition.project_id == project_id, GovernanceCondition.status == "cleared")
                .order_by(GovernanceCondition.cleared_at, GovernanceCondition.id)
            )
        )
        .scalars()
        .first()
    )
