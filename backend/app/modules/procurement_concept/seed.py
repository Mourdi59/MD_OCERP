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
  currency, a procedure the threshold check allows, supply lead times, and need
  dates that let each procedure start after the gate that releases procurement; the design package with a fee, already awarded (the
  designers were appointed before the works were planned);
* one long-lead supply as an advance package, but only when something of the
  project's demo data already releases it: a released commitment with a lead
  time (the reserved fabrication slot, answered by the commitment matrix when
  it is connected), else a cleared condition of a gate. With neither the
  package stays an ordinary one. The seed never writes a commitment, a
  governance decision or a condition of its own;
* a prequalification profile with five criteria; candidates on the main works
  package from the demo subcontractor register (in a fixed order), topped up
  with named candidates still to be registered;
* three market soundings held one to four months before the seed day, one with
  a tight capacity signal and its mitigation;
* one framework agreement of the project owner's company, called off by a
  supply package.

The concept is left as a draft with no blocking finding, so it can be
submitted and taken through the governance gate. Company names are generic
trade descriptions, never real firms. A project that already has a concept is
skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

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


_SOUNDING_METHODS = ("survey", "meeting", "rfi", "notice")
_CAPACITY_SIGNALS = ("ample", "adequate", "tight", "insufficient")
_PRICE_SIGNALS = ("below_estimate", "in_line", "above_estimate", "unknown")


def _story_str(value: Any, locale: str, *, limit: int = 500) -> str | None:
    """A non-empty story text in the project's locale, else ``None`` (the default stays)."""
    from app.modules.project_governance.public import story_text

    if not isinstance(value, (str, dict)):
        return None
    text = story_text(value, locale)
    return text.strip()[:limit] if isinstance(text, str) and text.strip() else None


def _story_int(value: Any, low: int, high: int) -> int | None:
    """An integer of the story within ``[low, high]``; ``None`` for anything else (bool included)."""
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        return None
    return value


def merge_package_story(
    base: tuple[str, str, str, int],
    entry: Any,
    procedures: set[str],
    locale: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Defaults of one package with a story entry applied key by key.

    Args:
        base: ``(base estimate, public procedure, private procedure, lead days)``.
        entry: Story object for a kind or a package code; anything else is ignored.
        procedures: Procedure codes of the catalogue; an unknown one keeps the default.
        locale: Locale for ``{"en", "de"}`` texts.
        previous: Result of an earlier merge (the kind entry) to build on instead of ``base``.

    Returns:
        Dict with ``value``, ``public``, ``private``, ``lead``, ``offset`` (days after the planning start, or
        ``None``) and ``notes``.
    """
    out: dict[str, Any] = dict(
        previous
        or {
            "value": base[0],
            "public": base[1],
            "private": base[2],
            "lead": base[3],
            "offset": None,
            "notes": "",
            "award_ago": None,
        }
    )
    if not isinstance(entry, dict):
        return out
    raw = entry.get("value")
    if isinstance(raw, (str, int)) and not isinstance(raw, bool):
        try:
            if Decimal(str(raw)) > 0:
                out["value"] = str(raw)
        except InvalidOperation:
            logger.info("procurement_concept demo story: value %r ignored", raw)
    for key, field in (("public_procedure", "public"), ("private_procedure", "private")):
        code = entry.get(key)
        if code is None:
            continue
        if isinstance(code, str) and code in procedures:
            out[field] = code
        else:
            logger.info("procurement_concept demo story: procedure %r ignored", code)
    lead = _story_int(entry.get("lead_days"), 0, 730)
    if lead is not None:
        out["lead"] = lead
    offset = _story_int(entry.get("start_offset_days"), 0, 720)
    if offset is not None:
        out["offset"] = offset
    ago = _story_int(entry.get("award_days_ago"), 1, 720)
    if ago is not None:
        out["award_ago"] = ago
    notes = _story_str(entry.get("notes"), locale, limit=2000)
    if notes:
        out["notes"] = notes
    return out


def merge_names(default: tuple[str, ...], value: Any, locale: str) -> tuple[str, ...]:
    """The story's list of texts, or ``default`` when it is not a non-empty list of texts."""
    if not isinstance(value, list):
        return default
    names = tuple(t for t in (_story_str(v, locale, limit=255) for v in value) if t)
    return names or default


def merge_soundings(value: Any, locale: str) -> list[dict[str, Any]] | None:
    """Valid sounding rows of the story, or ``None`` when the story gives none (the default three stay).

    A row needs a trade, a ``days_ago`` and findings; an invalid vocabulary value falls back to its default.
    ``package_kinds`` lists the package kinds covered; ``main`` adds the main works package.
    """
    if not isinstance(value, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        trade = _story_str(item.get("trade"), locale, limit=120)
        findings = _story_str(item.get("findings"), locale, limit=2000)
        days = _story_int(item.get("days_ago"), 1, 720)
        if not (trade and findings and days):
            logger.info("procurement_concept demo story: incomplete sounding ignored")
            continue
        kinds = item.get("package_kinds")
        method, capacity, price = item.get("method"), item.get("capacity_signal"), item.get("price_signal")
        rows.append(
            {
                "trade": trade,
                "findings": findings,
                "days_ago": days,
                "main": item.get("main") is True,
                "package_kinds": [k for k in kinds if isinstance(k, str)] if isinstance(kinds, list) else [],
                "method": method if method in _SOUNDING_METHODS else "meeting",
                "capacity_signal": capacity if capacity in _CAPACITY_SIGNALS else "adequate",
                "price_signal": price if price in _PRICE_SIGNALS else "unknown",
                "lead_time_signal_days": _story_int(item.get("lead_time_signal_days"), 1, 1500),
                "mitigation": _story_str(item.get("mitigation"), locale, limit=2000) or "",
            }
        )
    return rows or None


def merge_framework(value: Any, locale: str) -> dict[str, Any]:
    """The framework agreement fields, the story's on top of the default supply framework."""
    out: dict[str, Any] = {
        "code": "FW-SUPPLY-01",
        "title": "Reinforcement and precast supply framework",
        "supplier_name": "Precast concrete supplier",
        "scope": "Reinforcement steel, precast elements and delivery to site",
        "package_kinds": ["supply", "supply_and_install"],
        "lots": [{"code": "L1", "title": "Reinforcement"}, {"code": "L2", "title": "Precast"}],
        "source_procedure_ref": "Open procedure, framework award 2025",
    }
    if not isinstance(value, dict):
        return out
    code = value.get("code")
    if isinstance(code, str) and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{1,31}", code):
        out["code"] = code
    for key, limit in (("title", 255), ("supplier_name", 255), ("scope", 2000), ("source_procedure_ref", 255)):
        text = _story_str(value.get(key), locale, limit=limit)
        if text:
            out[key] = text
    kinds = value.get("package_kinds")
    if isinstance(kinds, list) and kinds and all(k in _DEFAULTS for k in kinds):
        out["package_kinds"] = list(kinds)
    lots = value.get("lots")
    if isinstance(lots, list):
        parsed = [
            {"code": str(lot["code"])[:20], "title": t}
            for lot in lots
            if isinstance(lot, dict) and lot.get("code") and (t := _story_str(lot.get("title"), locale, limit=120))
        ]
        if parsed:
            out["lots"] = parsed
    return out


def merge_prequal(value: Any, locale: str) -> dict[str, Any]:
    """Name, pass mark and the three scored weights (they must add up to 100) of the default profile."""
    out: dict[str, Any] = {"name": "Standard works prequalification", "pass_mark": "60", "weights": ["40", "35", "25"]}
    if not isinstance(value, dict):
        return out
    name = _story_str(value.get("name"), locale, limit=255)
    if name:
        out["name"] = name
    mark = _story_int(value.get("pass_mark"), 1, 100)
    if mark is not None:
        out["pass_mark"] = str(mark)
    weights = value.get("weights")
    if (
        isinstance(weights, list)
        and len(weights) == 3
        and all(isinstance(w, int) and not isinstance(w, bool) and w > 0 for w in weights)
        and sum(weights) == 100
    ):
        out["weights"] = [str(w) for w in weights]
    elif weights is not None:
        logger.info("procurement_concept demo story: prequal weights ignored")
    return out


def merge_reference(value: Any, locale: str) -> dict[str, str]:
    """The reference project shown on every candidate, and the reason an excluded candidate gets."""
    out = {
        "project_name": "Four-storey school extension",
        "client": "Municipal client",
        "role": "Main contractor",
        "value": "3100000",
        "excluded_rationale": "Below the pass mark on similar projects and current workload",
    }
    if not isinstance(value, dict):
        return out
    for key in ("project_name", "client", "role", "excluded_rationale"):
        text = _story_str(value.get(key), locale, limit=255)
        if text:
            out[key] = text
    amount = value.get("value")
    if isinstance(amount, (int, str)) and not isinstance(amount, bool) and str(amount).isdigit() and int(amount) > 0:
        out["value"] = str(amount)
    return out


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
    from app.core.demo_marker import demo_id_of
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
    from app.modules.project_governance.public import demo_module_story
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
    # The story of the active pack (if it names one for this project) is applied key by key on the defaults.
    story = demo_module_story(demo_id_of(project.metadata_), "procurement_concept")
    locale = getattr(project, "locale", None) or "en"
    scale = _story_int(story.get("magnitude"), 1, 1_000_000) or _MAGNITUDE.get(currency, 1)
    _form, mod3_public = await plan.delivery_form(session, project_id)
    regime = _regime_for(getattr(project, "country_code", None), currency) if mod3_public else None
    public = regime is not None
    catalogue, jurisdiction, client_type = regime or _neutral_regime()
    story_type = story.get("client_type")
    if public and isinstance(story_type, str):
        juris = next((j for j in catalogue.jurisdictions if j.code == jurisdiction), None)
        if juris is not None and story_type in juris.client_types:
            client_type = story_type
        else:
            logger.info("procurement_concept demo story: client type %r ignored", story_type)
    procedures = {p.code for p in catalogue.procedures}
    by_kind = story.get("kinds") if isinstance(story.get("kinds"), dict) else {}
    by_code = story.get("packages") if isinstance(story.get("packages"), dict) else {}
    free_names = merge_names(_FREE_NAMES, story.get("free_names"), locale)
    today = datetime.now(UTC).date()
    release = await _advance_release(session, project_id)
    concept = ProcurementConcept(
        project_id=project_id,
        catalogue_source="shipped",
        catalogue_id=catalogue.id,
        catalogue_version=catalogue.version,
        jurisdiction=jurisdiction,
        client_type=client_type,
        public_client=public,
        vat_rate_pct=Decimal("0"),
        # A cleared condition names the gate that released procurement in the demo story; a released
        # commitment names none, and the gate the phase model tags stays the release gate.
        release_gate_code=release[2] if release is not None else "",
        state="draft",
        created_by=getattr(project, "owner_id", None),
    )
    session.add(concept)
    await session.flush()

    tenant = str(getattr(project, "owner_id", "") or "")
    fw = merge_framework(story.get("framework"), locale)
    framework = None
    if tenant:
        framework = (
            (
                await session.execute(
                    select(FrameworkAgreement).where(
                        FrameworkAgreement.tenant_id == tenant, FrameworkAgreement.code == fw["code"]
                    )
                )
            )
            .scalars()
            .first()
        )
        if framework is None:
            framework = FrameworkAgreement(
                tenant_id=tenant,
                code=fw["code"],
                title=fw["title"],
                supplier_name=fw["supplier_name"],
                scope=fw["scope"],
                package_kinds=fw["package_kinds"],
                lots=fw["lots"],
                max_value=Decimal("2500000") * scale,
                currency=currency,
                start_date=(today - timedelta(days=200)).isoformat(),
                end_date=(today + timedelta(days=900)).isoformat(),
                call_off_mode="direct",
                source_procedure_ref=fw["source_procedure_ref"],
                state="active",
            )
            session.add(framework)
            await session.flush()

    # Planning dates follow from the gate that releases procurement: a procedure that starts before its
    # release date is a blocking finding (rule 11), so every ordinary package starts after it.
    from app.modules.procurement_concept.service import ProcurementConceptService

    svc = ProcurementConceptService(session)
    release_date = await svc._release_date(project_id, await svc.release_gate(project_id, concept))
    plan_from = max(today, release_date) if release_date is not None else today
    if not await svc.advance_applies(project_id, concept):
        # No gate holds procurement back in this project's phase model, so there is no advance package to seed.
        release = None
    awards: list[AwardPackage] = []
    advance_done = False
    framework_used = False
    for i, cp in enumerate(cps):
        merged = merge_package_story(_DEFAULTS[cp.kind], by_kind.get(cp.kind), procedures, locale)
        if cp.code in by_code:
            # A package code names one package of the plan and wins over the kind it belongs to.
            merged = merge_package_story(_DEFAULTS[cp.kind], by_code[cp.code], procedures, locale, previous=merged)
        value, pub_proc, priv_proc, lead = merged["value"], merged["public"], merged["private"], merged["lead"]
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
            notes=merged["notes"],
            lead_time_days=lead or None,
            # The designers were appointed before the works were planned: that award is a fact of the past.
            # Everything else is a plan with a procedure chosen, waiting for the gate.
            state="awarded" if cp.kind == "design" else "procedure_set",
        )
        if cp.kind == "supply" and framework is not None and not framework_used:
            row.framework_agreement_id = framework.id
            row.procedure_code = "framework_call_off"
            framework_used = True
        elif cp.kind in ("supply", "supply_and_install") and not advance_done and release is not None:
            # Only with something that releases it already: an advance package nothing released would block
            # the demo concept.
            row.is_advance = True
            row.advance_reason = (
                _story_str(story.get("advance_reason"), locale, limit=2000)
                or "Long lead item: fabrication slot must be reserved before the main tender"
            )
            row.advance_release_kind, row.advance_release_id = release[0], release[1]
            advance_done = True
        # Need date = start + procedure + lead time. A released advance package is the one that may start
        # before the release date; the others start a month or more after it, staggered.
        steps = catalogue.lead_time(row.procedure_code)
        offset = merged["offset"] if merged["offset"] is not None else 30 + 45 * i
        start = today + timedelta(days=10) if row.is_advance else plan_from + timedelta(days=offset)
        row.need_date = (start + timedelta(days=(steps.total_days() if steps else 0) + lead)).isoformat()
        if cp.kind == "design" and merged["award_ago"] is not None:
            # An awarded package was awarded in the past: the award date is the need date less the lead time.
            row.need_date = (today - timedelta(days=merged["award_ago"]) + timedelta(days=lead)).isoformat()
        session.add(row)
        awards.append(row)
    await session.flush()

    prequal = merge_prequal(story.get("prequal"), locale)
    profile = PrequalProfile(
        project_id=project_id,
        name=prequal["name"],
        criteria=[
            {"code": "exclusion_grounds", "kind": "pass_fail", "weight": "0"},
            {"code": "insurance_cover", "kind": "pass_fail", "weight": "0"},
            {"code": "similar_projects", "kind": "scored", "weight": prequal["weights"][0]},
            {"code": "technical_capacity", "kind": "scored", "weight": prequal["weights"][1]},
            {"code": "hse_record", "kind": "scored", "weight": prequal["weights"][2]},
        ],
        pass_mark=Decimal(prequal["pass_mark"]),
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
    reference = merge_reference(story.get("reference"), locale)
    scores = [("88", "82", "75"), ("74", "70", "80"), ("65", "72", "68"), ("55", "50", "45")]
    for n, sub in enumerate(subs):
        lst = "short" if n < 3 else "excluded"
        c = BidderCandidate(
            project_id=project_id,
            package_id=main.id,
            subcontractor_id=sub.id,
            source="own_list" if n % 2 == 0 else "market_sounding",
            list_kind=lst,
            decision_rationale="" if lst == "short" else reference["excluded_rationale"],
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
                project_name=reference["project_name"],
                client=reference["client"],
                value=Decimal(reference["value"]) * scale,
                currency=currency,
                year=today.year - 2,
                role=reference["role"],
            )
        )
        candidates += 1
    for name in free_names[len(subs) :]:
        session.add(
            BidderCandidate(project_id=project_id, package_id=main.id, free_name=name, source="market_sounding")
        )
        candidates += 1

    supply_ids = [str(a.id) for a, c in zip(awards, cps, strict=True) if c.kind in ("supply", "supply_and_install")]
    story_soundings = merge_soundings(story.get("soundings"), locale)
    if story_soundings is None:
        soundings = [
            MarketSounding(
                project_id=project_id,
                package_ids=[str(main.id)],
                trade="Structural works",
                held_on=(today - timedelta(days=110)).isoformat(),
                method="meeting",
                findings="Four regional contractors interested; two prefer a split into frame and finishes.",
                capacity_signal="adequate",
                price_signal="in_line",
            ),
            MarketSounding(
                project_id=project_id,
                package_ids=supply_ids,
                trade="Steel and precast supply",
                held_on=(today - timedelta(days=70)).isoformat(),
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
                held_on=(today - timedelta(days=30)).isoformat(),
                method="survey",
                findings="Six installers responded, three with capacity from next spring.",
                capacity_signal="ample",
                price_signal="below_estimate",
            ),
        ]
    else:
        soundings = []
        for row in story_soundings:
            covered = [str(main.id)] if row["main"] else []
            covered += [str(a.id) for a, c in zip(awards, cps, strict=True) if c.kind in row["package_kinds"]]
            soundings.append(
                MarketSounding(
                    project_id=project_id,
                    package_ids=list(dict.fromkeys(covered)),
                    trade=row["trade"],
                    held_on=(today - timedelta(days=row["days_ago"])).isoformat(),
                    method=row["method"],
                    findings=row["findings"],
                    capacity_signal=row["capacity_signal"],
                    price_signal=row["price_signal"],
                    lead_time_signal_days=row["lead_time_signal_days"],
                    mitigation=row["mitigation"],
                )
            )
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


async def _advance_release(session: AsyncSession, project_id: uuid.UUID) -> tuple[str, uuid.UUID, str] | None:
    """What releases the demo advance package: ``(kind, id, gate code)``, or ``None``. Nothing is written.

    A released commitment that carries a lead time comes first (the long lead reservation of the commitment
    matrix); the longest lead time wins and the code makes the pick repeatable. Else a cleared gate condition.
    """
    from app.modules.procurement_concept import commitments

    lister = commitments.commitment_lister()
    if lister is not None and commitments.commitment_checker() is not None:
        long_lead = [o for o in await lister(session, project_id) if o.released and o.lead_time_days]
        if long_lead:
            pick = min(long_lead, key=lambda o: (-o.lead_time_days, o.code))
            return commitments.KIND, pick.id, ""
    condition = await _cleared_release(session, project_id)
    return ("condition", condition.id, condition.gate_code) if condition is not None else None


async def _cleared_release(session: AsyncSession, project_id: uuid.UUID):
    """A cleared gate condition of the project's governance demo data, or ``None``. Nothing is written."""
    from app.modules.project_governance.public import project_conditions

    cleared = [c for c in await project_conditions(session, project_id) if c.status == "cleared"]
    # Conditions cleared without a timestamp sort last; the id makes the pick repeatable.
    cleared.sort(key=lambda c: (c.cleared_at is None, c.cleared_at.isoformat() if c.cleared_at else "", str(c.id)))
    return cleared[0] if cleared else None
