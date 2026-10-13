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

A project whose gate into the phase that starts construction exists and is not
decided yet tells the story before construction: the same plan as a draft,
nothing delivered, nothing tested, every survey and expert report still ahead.
The project is recognised by that state, read through the governance port,
never by a catalogue, a name or a code.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.quality_concept import schemas as s
from app.modules.quality_concept.models import QualityConcept

logger = logging.getLogger(__name__)

_REGIME = "fidic_taking_over"
# Before construction the demo is told under the German standard form of the catalogue.
_REGIME_BEFORE_CONSTRUCTION = "de_vob_b"
# Days from the seed day to the start of construction in the story before construction.
_START = 190
# Due dates of the expert reports in that story, all after the start.
_REPORTS_AFTER_START = ((_START + 30,), (_START + 110, _START + 170), (_START + 290, _START + 330))
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


async def _before_construction(session: AsyncSession, pid: uuid.UUID) -> bool:
    """Whether the gate into the phase that starts construction exists and is still undecided."""
    from app.modules.project_governance import public
    from app.modules.quality_concept.hosting import CONSTRUCTION_START

    starts = set(await public.phases_enabling(session, pid, CONSTRUCTION_START))
    if not starts:
        return False
    gates = [g for g in await public.project_gates(session, pid) if g.to_phase in starts]
    return bool(gates) and all(g.status != "decided" for g in gates)


async def _named(session: AsyncSession, pid: uuid.UUID, user_id: uuid.UUID, owner_id: uuid.UUID) -> uuid.UUID:
    """Who a record names as responsible: the user when they can open the project, else its owner."""
    from app.modules.project_governance import public

    return user_id if await public.user_can_access_project(session, pid, user_id) else owner_id


async def _team_members(session: AsyncSession, pid: uuid.UUID) -> list[uuid.UUID]:
    """The users on a team of this project, longest standing first."""
    from app.modules.teams.models import Team, TeamMembership

    stmt = (
        select(TeamMembership.user_id)
        .join(Team, Team.id == TeamMembership.team_id)
        .where(Team.project_id == pid)
        .order_by(TeamMembership.created_at)
    )
    return list((await session.execute(stmt)).scalars())


async def _actors(session: AsyncSession, pid: uuid.UUID, owner_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """``(recorder, second person)``: who records and who signs off.

    The recorder is the project's owner. The second person is the demo cast's cost owner, else
    its decider, else a member of one of the project's teams, and in every case somebody who can
    open this project. Nobody else is eligible: an account that merely exists in the installation
    may be a real person, of another tenant, and is never made the author of demo records. With
    nobody but the owner both sides are the owner and the two-person steps are left out.
    """
    from app.core import demo_cast
    from app.modules.project_governance import public

    cast = await demo_cast.find_cast(session)
    for uid in (cast.get("cost"), cast.get("decider"), *await _team_members(session, pid)):
        if uid is not None and uid != owner_id and await public.user_can_access_project(session, pid, uid):
            return owner_id, uid
    return owner_id, owner_id


async def _seed_plan(
    svc: Any, pid: uuid.UUID, actor: uuid.UUID, named: uuid.UUID, today: date, totals: dict[str, int], before: bool
) -> list[str]:
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
                    owner_user_id=named,
                )
                for n, category in enumerate(categories)
            ],
        )
        totals["credits"] += len(credits)
        if first and not before:
            await svc.transition_certification(
                pid, target.id, s.CertificationTransition(action="register", on=today - timedelta(days=180))
            )
            await svc.patch_credit(pid, credits[0].id, s.CreditPatch(action="submit_evidence"))
            await svc.patch_credit(pid, credits[0].id, s.CreditPatch(action="achieve", points_achieved=Decimal("17")))
            await svc.patch_credit(pid, credits[1].id, s.CreditPatch(action="submit_evidence"))

    for index, (subject, trigger, frequency, offsets, state) in enumerate(_EXPERT_REPORTS):
        if before:
            # Nothing is built yet: every report is still planned and falls due after the start.
            offsets, state = _REPORTS_AFTER_START[index % len(_REPORTS_AFTER_START)], "planned"
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
    svc: Any,
    pid: uuid.UUID,
    engineer: uuid.UUID,
    authority: uuid.UUID,
    named: uuid.UUID,
    totals: dict[str, int],
    before: bool,
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
        await svc.patch_stage(pid, stage.id, s.StageDefPatch(owner_user_id=named, applies_to=scope))
    totals["stages"] += len(stages)
    rows = await svc.sync_progress(pid)
    totals["stage_rows"] += len(rows)
    if not staged or not stages or before:
        # Before construction the stage model stands with its owners and no system has been tested.
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
        if index:
            continue
        if authority == engineer:
            # Not a fault of the installation: a project with nobody but its owner shows the request only.
            logger.info("quality_concept demo seed: project %s has no second person to release a stage", pid)
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


async def _seed_units(
    svc: Any, pid: uuid.UUID, refs: list[str], today: date, totals: dict[str, int], before: bool
) -> None:
    # Before construction the acceptances lie after commissioning, a year and a half ahead.
    shift = _START + 250 if before else 0
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
                regime_code=_REGIME_BEFORE_CONSTRUCTION if before else _REGIME,
                package_refs=packages,
                section_ref="A" if kind == "partial_section" else "",
                planned_date=today + timedelta(days=days + shift),
            ),
        )
        totals["units"] += 1


async def _seed_proofs(
    svc: Any,
    pid: uuid.UUID,
    refs: list[str],
    engineer: uuid.UUID,
    authority: uuid.UUID,
    totals: dict[str, int],
    before: bool,
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
    if before:
        # The proof plan is the deliverable of this phase; no record of the works exists to prove anything.
        return

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
    elif delivered:
        logger.info("quality_concept demo seed: project %s has no second person to accept a proof", pid)
    open_proofs = [p for p in proofs if p not in delivered]
    if open_proofs:
        await svc.request_waiver(
            pid,
            open_proofs[-1].id,
            "Covered by the manufacturer's system warranty; a separate certificate is not issued for this package.",
            engineer,
        )


async def _seed_surveys_ahead(svc: Any, pid: uuid.UUID, today: date, totals: dict[str, int]) -> None:
    """Before construction: the condition surveys are planned shortly before the start, none is carried out."""
    for kind, ref, address, methods, days in (
        ("neighbour_building", "NB-01", "Adjacent building, north boundary", ["photo", "crack_mapping"], 20),
        ("public_road", "RD-01", "Access road, east side", ["photo"], 10),
    ):
        await svc.create_survey(
            pid,
            s.PreservationIn(
                subject_kind=kind,
                subject_ref=ref,
                address=address,
                influence_triggers=["excavation"],
                methods=methods,
                planned_date=today + timedelta(days=_START - days),
            ),
        )
        totals["surveys"] += 1


async def _seed_course(svc: Any, pid: uuid.UUID, engineer: uuid.UUID, today: date) -> None:
    """Works under way: a documentation set chosen, one acceptance on its way, the concept in review.

    Each step is asked of the service first and left out when it would be refused, so a demo
    estate that lacks the records for it still gets its concept.
    """
    from app.modules.quality_concept import evaluator as ev
    from app.modules.quality_concept.models import AcceptanceUnit

    concept = await svc.require_concept(pid)
    cat = await svc.catalogue_for(concept)
    if cat.documentation_sets:
        await svc.patch_concept(pid, s.ConceptPatch(documentation_set_code=cat.documentation_sets[0].code))
    units = await svc.repo.list(AcceptanceUnit, pid)
    if units:
        # The contractor gave notice of completion for the first section: the deemed date starts to count.
        unit = min(units, key=lambda u: u.planned_date or "")
        await svc.record_dates(pid, unit.id, s.AcceptanceRecordIn(completion_notice_at=today - timedelta(days=4)))
        regime = cat.regime(unit.regime_code)
        unmet = await svc.unmet_preconditions(pid, unit)
        blocking, _reserved = ev.acceptance_request_check(
            unmet, reservable=regime.reservable if regime else (), with_reservations=True
        )
        if regime is not None and not blocking:
            await svc.request_acceptance(pid, unit.id, s.AcceptanceRequestIn(with_reservations=True), engineer)
    # Submitting freezes the first revision. It is the last step: a concept in review is closed to edits.
    concept = await svc.require_concept(pid)
    errors = [f for f in await svc.completeness(concept) if f.severity == ev.ERROR]
    if svc.submit_refusal(concept, errors) is None:
        await svc.submit(pid, engineer)


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
            influence_triggers=["excavation"],
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
        engineer, authority = await _actors(session, pid, owner)
        counts = dict.fromkeys(_TOTALS, 0)
        # One project is one unit of work. A refusal is not caught: it rolls this project back
        # and reaches the caller with its code, so a seed that no longer fits the rules is seen.
        # Steps that need a second person are left out above, with a warning, when there is none.
        async with session.begin_nested():
            before = await _before_construction(session, pid)
            named = await _named(session, pid, engineer, owner)
            await svc.ensure_concept(pid, engineer)
            refs = await _seed_plan(svc, pid, engineer, named, today, counts, before)
            await _seed_stages(svc, pid, engineer, authority, named, counts, before)
            await _seed_units(svc, pid, refs, today, counts, before)
            await _seed_proofs(svc, pid, refs, engineer, authority, counts, before)
            if before:
                await _seed_surveys_ahead(svc, pid, today, counts)
            else:
                await _seed_surveys(svc, pid, engineer, today, counts)
                await _seed_course(svc, pid, engineer, today)
        counts["projects"] = 1
        for key, value in counts.items():
            totals[key] += value
    logger.info("quality_concept demo seed: %s", totals)
    return totals
