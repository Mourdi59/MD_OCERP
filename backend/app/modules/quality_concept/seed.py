# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo quality concept for the demo estate.

Each demo project gets a draft concept on the neutral catalogue with every
register filled: applied standards and requirements, certification targets with
credits, the proof plan of two packages with evidence linked from records the
other seeders wrote, the catalogue commissioning stages with owners and a
system walked part of the way, acceptance units, expert reports and the
before-and-after survey of a neighbouring building.

Everything goes through the service, so the demo obeys the same rules as user
input: a stage is released by its hold gate, evidence is accepted by someone
other than the person who linked it, and where the estate has only one account
those steps are left open rather than faked.

The staged commissioning model is applied to the systems whose commissioning
has not finished its tests. A system the commissioning demo already shows as
tested or commissioned keeps working exactly as before.

A project is skipped when it is not a demo project or already has a concept,
so a customer's live project is never written to and a re-run adds nothing.
Dates are counted back from the day the seed runs: recorded facts lie in the
past, planned ones in the future.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_concept import schemas as s
from app.modules.quality_concept.errors import QualityConceptError
from app.modules.quality_concept.models import QualityConcept

logger = logging.getLogger(__name__)

_REGIME = "fidic_taking_over"
# Lifecycle states of a commissioning system whose tests are still open.
_OPEN_LIFECYCLES = ("not_started", "in_progress")
_PACKAGES = (
    ("PKG-STR", "Structure and envelope"),
    ("PKG-MEP", "Building services"),
)
_STANDARDS = (
    ("EN 206", "Concrete: specification, performance, production and conformity", "concrete", "structure", 0),
    ("EN 1090-2", "Execution of steel structures", "steel", "structure", 0),
    ("EN 12599", "Ventilation for buildings: test procedures for handing over", None, "mep", 1),
)
_REQUIREMENTS = (
    ("quality.material", "Structural concrete", "strength class", "C30/37", "", "Structural specification 3.2"),
    ("quality.availability", "Cooling plant", "availability", "99.5", "%", "Employer's requirements 7.1"),
    ("quality.acoustics", "Office floors", "airborne sound insulation", "52", "dB", "Employer's requirements 5.4"),
    ("quality.fm_data", "Maintainable assets", "asset data set", "complete at handover", "", "Information needs 2.3"),
)
_EXPERT_REPORTS = (
    ("Independent check of the structural analysis", "before_concreting", "once", (-240,), "completed"),
    (
        "Fire protection inspection of the services",
        "before_concealment",
        "per_floor",
        (-20, 25),
        "reporting",
    ),
    ("Acoustic measurement of the finished floors", "after_installation", "per_floor", (60, 110), "planned"),
)
_TOTALS = (
    "projects",
    "standards",
    "requirements",
    "certifications",
    "credits",
    "stages",
    "stage_rows",
    "units",
    "proofs",
    "links",
    "expert_reports",
    "surveys",
)


async def _actors(session: AsyncSession, owner_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """``(engineer, authority)``: who records and who signs off. The owner stands in for a missing side."""
    from app.modules.users.models import User

    by_role: dict[str, uuid.UUID] = {}
    for uid, role in (await session.execute(select(User.id, User.role).order_by(User.email))).all():
        by_role.setdefault(str(role or ""), uid)
    engineer = by_role.get("editor") or owner_id
    authority = by_role.get("manager") or by_role.get("admin") or owner_id
    return engineer, authority


async def _seed_plan(svc: Any, pid: uuid.UUID, actor: uuid.UUID, today: date, totals: dict[str, int]) -> list[str]:
    """Packages, standards, requirements, certification targets and expert reports. Returns the package refs."""
    await svc.patch_concept(
        pid, s.ConceptPatch(packages=[s.PackageScopeIn(ref=ref, code=ref, title=title) for ref, title in _PACKAGES])
    )
    concept = await svc.require_concept(pid)
    refs = [p["ref"] for p in await svc.applicable_packages(concept)][:2]
    for code, title, family, discipline, package in _STANDARDS:
        await svc.create_standard(
            pid,
            s.StandardIn(
                code=code,
                title=title,
                family_code=family,
                discipline=discipline,
                package_refs=refs[package : package + 1],
            ),
        )
        totals["standards"] += 1
    for category, entity, attribute, value, unit, source in _REQUIREMENTS:
        await svc.add_requirement(
            pid,
            s.QualityRequirementIn(
                category=category,
                entity=entity,
                attribute=attribute,
                constraint_value=value,
                unit=unit,
                source_ref=source,
            ),
            actor,
        )
        totals["requirements"] += 1

    # One target per scope the catalogue offers a graded scheme for. The scheme is catalogue data.
    cat = await svc.catalogue_for(concept)
    seen: set[str] = set()
    for scheme in cat.certification_schemes:
        if scheme.scope in seen or len(scheme.levels) < 2 or not scheme.credit_categories:
            continue
        seen.add(scheme.scope)
        first = len(seen) == 1
        target = await svc.create_certification(
            pid,
            s.CertificationIn(
                scheme_code=scheme.code,
                scheme_version=scheme.versions[0] if scheme.versions else "",
                scope=scheme.scope,
                target_level=scheme.levels[-2].code,
                points_available=Decimal("100"),
            ),
        )
        totals["certifications"] += 1
        categories = scheme.credit_categories[: 5 if first else 3]
        credits = await svc.add_credits(
            pid,
            target.id,
            [
                s.CreditIn(
                    credit_code=f"{category.upper()[:3]}-{n + 1:02d}",
                    category=category,
                    points_targeted=Decimal(18 - 2 * n),
                    owner_user_id=actor,
                )
                for n, category in enumerate(categories)
            ],
        )
        totals["credits"] += len(credits)
        if first:
            await svc.transition_certification(
                pid, target.id, s.CertificationTransition(action="register", on=today - timedelta(days=180))
            )
            await svc.patch_credit(pid, credits[0].id, s.CreditPatch(action="submit_evidence"))
            await svc.patch_credit(pid, credits[0].id, s.CreditPatch(action="achieve", points_achieved=Decimal("17")))
            await svc.patch_credit(pid, credits[1].id, s.CreditPatch(action="submit_evidence"))

    for subject, trigger, frequency, offsets, state in _EXPERT_REPORTS:
        await svc.create_expert_report(
            pid,
            s.ExpertReportIn(
                subject=subject,
                trigger=trigger,
                frequency=frequency,
                due_dates=[today + timedelta(days=d) for d in offsets],
                state=state,
            ),
        )
        totals["expert_reports"] += 1
    return refs


async def _seed_stages(
    svc: Any, pid: uuid.UUID, engineer: uuid.UUID, authority: uuid.UUID, totals: dict[str, int]
) -> None:
    """The catalogue stages with owners, scoped to the systems still in testing, and one system under way."""
    from app.modules.commissioning.models import CxSystem
    from app.modules.construction_control.gating_service import GatingService
    from app.modules.construction_control.schemas import HoldGateReleaseIn

    session = svc.session
    systems = list(
        (await session.execute(select(CxSystem).where(CxSystem.project_id == pid).order_by(CxSystem.tag))).scalars()
    )
    staged = [x for x in systems if x.status in _OPEN_LIFECYCLES]
    scope: dict[str, Any] = {"mode": "all"}
    if len(staged) != len(systems):
        scope = {"mode": "systems", "values": [str(x.id) for x in staged]}
    stages = await svc.apply_catalogue_stages(pid)
    for stage in stages:
        await svc.patch_stage(pid, stage.id, s.StageDefPatch(owner_user_id=engineer, applies_to=scope))
    totals["stages"] += len(stages)
    rows = await svc.sync_progress(pid)
    totals["stage_rows"] += len(rows)
    if not staged or not stages:
        return

    def row_of(system: Any, stage: Any) -> Any:
        return next(r for r in rows if r.system_id == system.id and r.stage_code == stage.code)

    first = stages[0]
    # System one: the first stage tested, passed and released by its hold gate; the next one in test.
    # System two: tested and passed, release requested and waiting for the releasing party.
    for index, system in enumerate(staged[:2]):
        row = row_of(system, first)
        if row.state != "ready":
            continue
        await svc.open_test(pid, row.id, engineer)
        await svc.record_result(pid, row.id, s.StageResultIn(result="pass"), engineer)
        gate = await svc.request_release(pid, row.id, engineer)
        if index or authority == engineer:
            continue
        await GatingService(session).release_gate(
            gate.id, HoldGateReleaseIn(party_role=first.release_party_role), str(authority), signature_ip=None
        )
        await svc.apply_gate_released(gate.id)
        if len(stages) > 1:
            await svc.refresh_ready(pid)
            following = row_of(system, stages[1])
            if following.state == "ready":
                await svc.open_test(pid, following.id, engineer)


async def _seed_units(svc: Any, pid: uuid.UUID, refs: list[str], today: date, totals: dict[str, int]) -> None:
    for code, title, kind, days, packages in (
        ("AU-01", "Structure, building section A", "partial_section", 45, refs[:1]),
        ("AU-02", "Building services", "partial_package", 120, refs[1:2]),
        ("AU-03", "Whole works", "total", 150, []),
        ("AU-04", "Handover to operation", "handover_to_operation", 165, []),
    ):
        if kind.startswith("partial_") and not packages:
            continue
        await svc.create_unit(
            pid,
            s.AcceptanceUnitIn(
                code=code,
                title=title,
                kind=kind,
                regime_code=_REGIME,
                package_refs=packages,
                section_ref="A" if kind == "partial_section" else "",
                planned_date=today + timedelta(days=days),
            ),
        )
        totals["units"] += 1


async def _seed_proofs(
    svc: Any, pid: uuid.UUID, refs: list[str], engineer: uuid.UUID, authority: uuid.UUID, totals: dict[str, int]
) -> None:
    """The catalogue proof plan of each package, evidence from the project's own records, and decisions."""
    concept = await svc.require_concept(pid)
    cat = await svc.catalogue_for(concept)
    proofs: list[Any] = []
    for position, ref in enumerate(refs):
        preview = (await svc.generate_proofs(pid, s.ProofGenerateIn(package_ref=ref)))["preview"]
        wanted = [r["evidence_type"] for r in preview]
        # The second package carries the documentation proofs only, so the two columns differ.
        chosen = wanted if position == 0 else wanted[-3:]
        proofs += (await svc.generate_proofs(pid, s.ProofGenerateIn(package_ref=ref, confirm=chosen)))["created"]
    totals["proofs"] += len(proofs)

    passing: dict[str, list[str]] = {}
    delivered: list[Any] = []
    for proof in proofs:
        if proof.quantity_rule:
            # A counted proof needs the placed quantity to say how many tests are due.
            rule = s.QuantityRuleIn(**{**proof.quantity_rule, "placed_quantity": Decimal("300")})
            await svc.patch_proof(pid, proof.id, s.ProofPatch(quantity_rule=rule))
        evidence_type = cat.evidence_type(proof.evidence_type)
        for kind in evidence_type.fulfilled_by if evidence_type else ():
            if kind not in passing:
                passing[kind] = [
                    c["id"] for c in await svc.candidates(pid, kind, limit=20) if c.get("outcome") == "pass"
                ]
            if not passing[kind]:
                continue
            await svc.add_link(
                pid,
                s.EvidenceLinkIn(owner_kind="proof", owner_id=proof.id, link_kind=kind, link_id=passing[kind][0]),
                engineer,
            )
            totals["links"] += 1
            if (await svc.proof_delivery(pid, [proof]))[proof.id].state == "delivered":
                delivered.append(proof)
            break
    # Four eyes: accepted by the authority, never by the engineer who linked the evidence.
    if authority != engineer:
        for proof in delivered[:2]:
            await svc.accept_proof(pid, proof.id, authority)
    open_proofs = [p for p in proofs if p not in delivered]
    if open_proofs:
        await svc.request_waiver(
            pid,
            open_proofs[-1].id,
            "Covered by the manufacturer's system warranty; a separate certificate is not issued for this package.",
            engineer,
        )


async def _seed_surveys(svc: Any, pid: uuid.UUID, actor: uuid.UUID, today: date, totals: dict[str, int]) -> None:
    before = await svc.create_survey(
        pid,
        s.PreservationIn(
            subject_kind="neighbour_building",
            subject_ref="NB-01",
            address="Adjacent building, north boundary",
            influence_triggers=["excavation"],
            methods=["photo", "crack_mapping"],
            planned_date=today - timedelta(days=300),
        ),
    )
    await svc.survey_action(
        pid, before.id, s.PreservationAction(action="invite", on=today - timedelta(days=320)), actor
    )
    await svc.survey_action(
        pid,
        before.id,
        s.PreservationAction(action="record_survey", on=today - timedelta(days=300), owner_acknowledged=True),
        actor,
    )
    await svc.survey_action(
        pid, before.id, s.PreservationAction(action="issue_report", on=today - timedelta(days=290)), actor
    )
    await svc.create_survey(
        pid,
        s.PreservationIn(
            subject_kind="neighbour_building",
            subject_ref="NB-01",
            address="Adjacent building, north boundary",
            influence_triggers=["excavation"],
            methods=["photo", "crack_mapping"],
            phase="after",
            paired_with_id=before.id,
            planned_date=today + timedelta(days=120),
        ),
    )
    await svc.create_survey(
        pid,
        s.PreservationIn(
            subject_kind="public_road",
            subject_ref="RD-01",
            address="Access road, east side",
            influence_triggers=["vibration"],
            methods=["photo"],
            planned_date=today + timedelta(days=10),
        ),
    )
    totals["surveys"] += 3


async def seed_quality_concept_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed a filled quality concept into every demo project that has none.

    Args:
        session: Async DB session. The caller commits.
        project_ids: Projects to consider.

    Returns:
        Dict with per-entity insert counts.
    """
    from app.modules.projects.models import Project
    from app.modules.quality_concept.service import QualityConceptService

    totals = dict.fromkeys(_TOTALS, 0)
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (
        await session.execute(select(Project.id, Project.owner_id, Project.metadata_).where(Project.id.in_(ids)))
    ).all()
    seeded = set(
        (await session.execute(select(QualityConcept.project_id).where(QualityConcept.project_id.in_(ids)))).scalars()
    )
    today = datetime.now(UTC).date()
    svc = QualityConceptService(session)
    for pid, owner, meta in rows:
        if pid in seeded or not (isinstance(meta, dict) and str(meta.get("demo_id") or "").strip()):
            continue
        engineer, authority = await _actors(session, owner)
        counts = dict.fromkeys(_TOTALS, 0)
        try:
            # One project is one unit of work: a refused step leaves that project without a
            # concept and the others untouched.
            async with session.begin_nested():
                await svc.ensure_concept(pid, engineer)
                refs = await _seed_plan(svc, pid, engineer, today, counts)
                await _seed_stages(svc, pid, engineer, authority, counts)
                await _seed_units(svc, pid, refs, today, counts)
                await _seed_proofs(svc, pid, refs, engineer, authority, counts)
                await _seed_surveys(svc, pid, engineer, today, counts)
        except (QualityConceptError, HTTPException) as exc:
            logger.warning("quality_concept demo seed refused for project %s: %s", pid, exc)
            continue
        counts["projects"] = 1
        for key, value in counts.items():
            totals[key] += value
    logger.info("quality_concept demo seed: %s", totals)
    return totals
