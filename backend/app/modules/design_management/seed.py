# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo design management for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets what an owner's design manager would set up in the
first weeks: the numbering scheme its country resolves to, a small WBS (only
when the project has none), the design team as roles with originator codes,
approval points and a design schedule along the phases of the project's
pinned governance model (the governance seed runs first and is the only one
that pins; a project without a model is left alone). While the gate into construction is
undecided the seed describes that one moment: the phase the gate closes is done except a single
submitted report, nothing of the next phase has happened. Past that gate it tells a running
project. Drawings are numbered by the generator with
revisions at different suitability, a distribution matrix, the two approval
routes, a release a second person prepared and that waits for the demo user's
approval, a draft release, an internal review with comments, the expert reports the catalogue lists and
a permit package being assembled.

No names of real companies or people: roles are titled by function. Only
projects carrying the demo marker are touched; a project that already has a
design setup is skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DESIGN_SPINE = ("concept", "design", "approval", "detail")


async def seed_design_management_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed every demo project in ``project_ids`` that has no design setup. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.design_management.models import DesignSetup
    from app.modules.project_governance.public import project_catalogue
    from app.modules.projects.models import Project

    totals = {"projects": 0, "drawings": 0, "deliverables": 0, "reports": 0, "one_person_stories": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (await session.execute(select(DesignSetup.id).where(DesignSetup.project_id == pid))).scalar_one_or_none()
        if has is not None:
            continue
        if await project_catalogue(session, pid) is None:
            # Design phases are the phases of the pinned model; without one there is nothing to schedule along.
            logger.info("design_management demo seed: project %s has no phase model, left alone", pid)
            continue
        # No blanket except: a seed that cannot finish is a defect to see, not a project to skip
        # quietly. The savepoint keeps a half-seeded project out; the caller logs and reports.
        async with session.begin_nested():
            counts = await _seed_project(session, pid)
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _pre_construction(session: AsyncSession, project_id: uuid.UUID) -> tuple[str, str] | None:
    """``(phase the gate closes, phase it opens)`` while the gate into construction is undecided, else ``None``.

    Read from the project's own state through module 1's port: the gate whose
    target phase enables the start of construction exists and carries no
    decision. Never from a catalogue id, a name or the source of the pin.
    """
    from app.modules.project_governance.public import phases_enabling, project_gates

    enabling = set(await phases_enabling(session, project_id, "construction_start"))
    gate = next((g for g in await project_gates(session, project_id) if g.to_phase in enabling), None)
    if gate is None or gate.status == "decided":
        return None
    return gate.from_phase, gate.to_phase


async def _approve(session: AsyncSession, instance_id: uuid.UUID, approver: uuid.UUID) -> None:
    """Decide an approval instance through approval_routes, the way its own screen does."""
    from app.modules.approval_routes.models import Instance, Step
    from app.modules.approval_routes.schemas import DecisionSubmit
    from app.modules.approval_routes.service import ApprovalRouteService

    instance = await session.get(Instance, instance_id)
    step = (
        await session.execute(
            select(Step).where(Step.route_id == instance.route_id, Step.ordinal == instance.current_step_ordinal)
        )
    ).scalar_one()
    await ApprovalRouteService(session).submit_decision(
        instance_id, DecisionSubmit(step_id=step.id, decision="approved"), approver_id=approver
    )


def _example(scheme: Any, field: str, meaning: str) -> str | None:
    """The scheme's own illustrative value of a field; ``None`` when the scheme has no such field."""
    return scheme.examples.get(field, {}).get(meaning) if scheme.field(field) is not None else None


def _phase_value(scheme: Any, phase_code: str) -> str | None:
    """The scheme's code for a governance phase: the listed code of the same name, else its example."""
    field = scheme.field("phase")
    if field is None:
        return None
    by_name = {c.casefold(): c for c in field.codes() or ()}
    return by_name.get((phase_code or "").casefold()) or _example(scheme, "phase", "default")


async def _second_person(session: AsyncSession, owner_id: uuid.UUID) -> uuid.UUID | None:
    """The demo cast's second person of a four-eyes step, when the installation has one.

    Only the cast: any other account of the installation is somebody's real one, possibly another
    tenant's, and has no business on a seeded row.
    """
    from app.core.demo_cast import find_cast

    cost = (await find_cast(session)).get("cost")
    return cost if cost is not None and cost != owner_id else None


async def _routes(session: AsyncSession, project_id: uuid.UUID, owner: uuid.UUID, second: uuid.UUID) -> None:
    """One approval route per design target kind, each decided by the person who did not prepare."""
    from app.modules.approval_routes.schemas import RouteCreate, StepCreate
    from app.modules.approval_routes.service import ApprovalRouteService

    for kind, name, approver in (
        # The demo user submits approval points, so the second person decides them.
        ("design_approval_point", "Design approval point sign-off", second),
        # The second person prepares the release, so the demo user approves and issues it.
        ("design_release", "Design release sign-off", owner),
    ):
        await ApprovalRouteService(session).create_route(
            RouteCreate(
                project_id=project_id,
                name=name,
                target_kind=kind,
                steps=[StepCreate(ordinal=1, approver_user_id=approver, mode="any")],
            ),
            created_by=owner,
        )


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.cde.models import DocumentContainer
    from app.modules.cde.schemas import RevisionCreate
    from app.modules.cde.service import CDEService
    from app.modules.design_management.service import DesignService
    from app.modules.projects.models import Project

    project = await session.get(Project, project_id)
    actor = project.owner_id
    svc = DesignService(session)
    setup = await svc.set_setup(project_id, actor_id=actor, tenant_id=None)
    scheme = await svc.scheme(setup)
    phases = await svc.phases(project_id)
    design_phases = [p for p in phases if p["spine_key"] in _DESIGN_SPINE] or phases
    p_early = design_phases[0]["code"]
    p_mid = design_phases[min(1, len(design_phases) - 1)]["code"]
    p_late = design_phases[-1]["code"]
    # Before construction is released the story is one moment: everything of the phase the gate
    # closes is done except a single report, and nothing of the phase it opens has happened.
    pre = await _pre_construction(session, project_id)
    if pre is not None:
        p_mid, p_late = pre
        closes = next((p["order"] for p in phases if p["code"] == p_mid), None)
        earlier = [p for p in design_phases if closes is not None and p["order"] <= closes]
        p_early = earlier[0]["code"] if earlier else p_mid

    # WBS: only when the project has none (never touch a WBS someone built).
    wbs = await svc.wbs_rows(project_id)
    if not wbs:
        top = await svc.create_wbs(project_id, {"code": "1", "name": "Building", "kind": "location"}, actor_id=actor)
        for code, name, kind in (
            ("1.1", "Substructure", "system"),
            ("1.2", "Superstructure", "system"),
            ("1.3", "Envelope", "system"),
            ("1.4", "Building services", "system"),
        ):
            await svc.create_wbs(
                project_id, {"code": code, "name": name, "kind": kind, "parent_id": top.id}, actor_id=actor
            )
        await svc.create_wbs(project_id, {"code": "2", "name": "External works", "kind": "location"}, actor_id=actor)
        wbs = await svc.wbs_rows(project_id)
    wbs_leaf = next((w for w in wbs if not (w.metadata_ or {}).get("closed")), None)

    disc = {
        "arch": _example(scheme, "discipline", "architecture"),
        "struct": _example(scheme, "discipline", "structure"),
        "mep": _example(scheme, "discipline", "building_services"),
    }
    roles = {}
    for key, title, kind, orig in (
        ("owner", "Owner's design manager", "owner", None),
        ("arch", "Lead architect", "discipline_designer", "ARC"),
        ("struct", "Structural engineer", "discipline_designer", "STR"),
        ("mep", "Building services engineer", "discipline_designer", "MEP"),
        ("fire", "Fire safety specialist", "specialist", "FSE"),
        ("checker", "Independent structural checker", "checker", "CHK"),
    ):
        roles[key] = await svc.create_role(
            project_id,
            {
                "code": key.upper(),
                "title": title,
                "party_kind": kind,
                "discipline_code": disc.get(key),
                "originator_code": orig,
                "user_id": actor if key == "owner" else None,
            },
            actor_id=actor,
        )
        roles[key].status = "active"
    setup.lead_designer_role_id = roles["arch"].id

    for code, title, phase, kind in (
        ("AP-001", "Owner sign-off of the concept", p_early, "owner_approval"),
        ("AP-002", "Cost check before the permit application", p_mid, "cost_check"),
        ("AP-003", "User sign-off of room layouts", p_mid, "user_signoff"),
    ):
        await svc.create_approval_point(
            project_id,
            {"code": code, "title": title, "phase_code": phase, "kind": kind, "approver_role_id": roles["owner"].id},
            actor_id=actor,
        )

    deliverables = {}
    for code, title, phase, role, count in (
        ("DL-001", "Concept plans and sections", p_early, "arch", 2),
        ("DL-002", "Structural concept", p_early, "struct", 1),
        ("DL-003", "Permit drawings", p_mid, "arch", 2 if pre else 3),
        ("DL-004", "Building services layouts", p_late, "mep", 2),
    ):
        deliverables[code] = await svc.create_deliverable(
            project_id,
            {
                "code": code,
                "title": title,
                "phase_code": phase,
                "role_id": roles[role].id,
                "discipline_code": disc[role],
                "planned_count": count,
                "wbs_node_id": wbs_leaf.id if wbs_leaf else None,
            },
            actor_id=actor,
        )

    cde = CDEService(session)
    drawing_rows = []
    # Before construction: the drawings of the closing phase are published, so their schedule lines
    # are accepted; the one drawing of the next phase is work in progress and counts for no line yet.
    done = "A4" if pre else None
    for title, role, dl, phase, form, spatial, sheet_type, suit in (
        ("Ground floor plan", "arch", "DL-001", p_early, "plan", "ground", "plan", done or "S3"),
        ("Section A-A", "arch", "DL-001", p_early, "section", "whole", "section", done or "S4"),
        ("Foundation layout", "struct", "DL-002", p_early, "plan", "basement", "plan", done or "S2"),
        ("Site plan for the permit", "arch", "DL-003", p_mid, "site_plan", "whole", "general", "A4"),
        ("Elevations for the permit", "arch", "DL-003", p_mid, "elevation", "whole", "elevation", done or "S0"),
        ("Ventilation ground floor", "mep", None if pre else "DL-004", p_late, "plan", "ground", "plan", "S0"),
    ):
        project_code = re.sub(r"[^A-Z0-9]", "", (project.project_code or "").upper())[:6]
        values = {
            "project": project_code if len(project_code) >= 2 else "DEMO",
            "functional": _example(scheme, "functional", "whole"),
            "spatial": _example(scheme, "spatial", spatial),
            "form": _example(scheme, "form", form),
            "custom_sheet_type": _example(scheme, "custom_sheet_type", sheet_type),
            "phase": _phase_value(scheme, phase),
        }
        fields = {k: v for k, v in values.items() if v is not None}
        drawing, container = await svc.create_drawing(
            project_id,
            {
                "title": title,
                "role_id": roles[role].id,
                "deliverable_id": deliverables[dl].id if dl else None,
                "phase_code": phase,
                "fields": fields,
                "scale": "1:100",
                "sheet_size": "A1",
                "wbs_node_id": wbs_leaf.id if wbs_leaf else None,
            },
            actor_id=actor,
        )
        rev = await cde.create_revision(
            container.id,
            RevisionCreate(file_name=f"{container.container_code}.pdf", change_summary="first issue"),
            user_id=str(actor),
        )
        c = await session.get(DocumentContainer, container.id)
        c.current_revision_id = rev.id
        c.suitability_code = suit
        c.cde_state = "published" if suit.startswith("A") else ("wip" if suit == "S0" else "shared")
        drawing_rows.append((drawing, c, rev))
    await session.flush()
    for d in deliverables.values():
        await svc.refresh_deliverable(d)

    await svc.create_dist_rule(
        project_id,
        {"recipient_role_id": roles["owner"].id, "min_suitability": "S2"},
        actor_id=actor,
    )
    await svc.create_dist_rule(
        project_id,
        {"recipient_role_id": roles["struct"].id, "discipline_codes": [disc["arch"]]},
        actor_id=actor,
    )
    await svc.create_dist_rule(
        project_id,
        {"recipient_role_id": roles["mep"].id, "discipline_codes": [disc["arch"], disc["struct"]], "format": "native"},
        actor_id=actor,
    )
    shared = [r.id for _d, c, r in drawing_rows if c.cde_state != "wip"]
    second = await _second_person(session, actor)
    if second is not None:
        # Prepared and marked ready by the second person: the demo user approves it and issues it.
        await _routes(session, project_id, actor, second)
        concept = await svc.create_release(
            project_id, {"code": "REL-001", "title": "Concept issue", "revision_ids": shared[:3]}, actor_id=second
        )
        await svc.release_transition(project_id, concept.id, "ready", actor_id=second)
    else:
        # Nobody plays the second part here: four-eyes off, so the release can still be issued.
        logger.info("design_management demo seed: project %s has no second person, one-person story", project_id)
        setup.four_eyes_release = False
        concept = await svc.create_release(
            project_id, {"code": "REL-001", "title": "Concept issue", "revision_ids": shared[:3]}, actor_id=actor
        )
        await svc.release_transition(project_id, concept.id, "ready", actor_id=actor)
    preparer = (second or actor) if pre else actor
    permit_set = await svc.create_release(
        project_id, {"code": "REL-002", "title": "Permit drawings", "revision_ids": shared[3:]}, actor_id=preparer
    )
    if pre is not None:
        # Released before the gate: prepared by one person, approved on the route and issued by the other.
        ready = await svc.release_transition(project_id, permit_set.id, "ready", actor_id=preparer)
        if ready.approval_instance_id is not None:
            await _approve(session, ready.approval_instance_id, actor)
            await svc.catch_up_approvals(project_id)
        await svc.issue_release(project_id, permit_set.id, actor_id=actor)

    review = await svc.create_review(
        project_id,
        {
            "code": "REV-001",
            "title": "End of concept review",
            "phase_code": p_early,
            "deliverable_ids": [deliverables["DL-001"].id, deliverables["DL-002"].id],
            "reviewer_role_ids": [roles["owner"].id, roles["mep"].id],
        },
        actor_id=actor,
    )
    for text, severity, idx in (
        ("Plant room size does not match the ventilation concept", "major", 0),
        ("Stair width to be checked against the escape route", "minor", 1),
        ("Foundation level differs from the ground report", "minor", 2),
    ):
        comment = await svc.add_comment(
            project_id,
            review.id,
            {"text": text, "severity": severity, "revision_id": drawing_rows[idx][2].id},
            actor_id=actor,
        )
        if pre is not None and severity != "minor":
            # An open major comment blocks the phase; before the gate it has been answered and closed.
            await svc.comment_transition(
                project_id,
                comment.id,
                "answered",
                actor_id=actor,
                answer="Plant room enlarged to match the ventilation concept.",
                role_id=roles["arch"].id,
            )
            await svc.comment_transition(project_id, comment.id, "closed", actor_id=actor)

    count_reports = 0
    if pre is not None:
        # Exactly one report of the closing phase is not accepted yet, and it stands one step before it.
        report_plan = (
            ("RPT-001", "geotechnical", p_early, "accepted", "struct", None),
            ("RPT-002", "fire_safety_concept", p_mid, "accepted", "fire", None),
            ("RPT-003", "structural_design", p_mid, "accepted", "struct", None),
            ("RPT-004", "structural_proof_check", p_late, "required", "struct", "checker"),
            ("RPT-005", "thermal_energy", p_mid, "submitted", "mep", None),
        )
    else:
        report_plan = (
            ("RPT-001", "geotechnical", p_early, "accepted", "struct", None),
            ("RPT-002", "fire_safety_concept", p_mid, "in_progress", "fire", None),
            ("RPT-003", "structural_design", p_mid, "commissioned", "struct", None),
            ("RPT-004", "structural_proof_check", p_mid, "required", "struct", "checker"),
            ("RPT-005", "thermal_energy", p_mid, "required", "mep", None),
        )
    for code, kind, phase, status, author, checker in report_plan:
        report = await svc.create_report(
            project_id,
            {
                "code": code,
                "kind_code": kind,
                "title": kind.replace("_", " ").capitalize(),
                "phase_code": phase,
                "author_role_id": roles[author].id,
                "checker_role_id": roles[checker].id if checker else None,
                "from_catalogue": True,
            },
            actor_id=actor,
        )
        for step in {
            "accepted": ("commissioned", "in_progress", "submitted", "accepted"),
            "submitted": ("commissioned", "in_progress", "submitted"),
            "in_progress": ("commissioned", "in_progress"),
            "commissioned": ("commissioned",),
        }.get(status, ()):
            await svc.report_transition(project_id, report.id, step, actor_id=actor)
        count_reports += 1

    reports_cat = await svc.reports_catalogue(setup)
    country = (project.country_code or "").upper()
    profile = next((p.code for p in reports_cat.permit_steps if country in p.jurisdiction_countries), "neutral")
    permit = await svc.create_permit(
        project_id, {"code": "PP-001", "title": "Building permit application", "profile_code": profile}, actor_id=actor
    )
    for drawing, c, _rev in drawing_rows[3:5]:
        await svc.add_permit_item(
            project_id, permit.id, {"kind": "drawing", "title": drawing.title, "container_id": c.id}, actor_id=actor
        )
    await svc.add_permit_item(project_id, permit.id, {"kind": "form", "title": "Application form"}, actor_id=actor)
    await session.flush()
    return {
        "drawings": len(drawing_rows),
        "deliverables": len(deliverables),
        "reports": count_reports,
        "one_person_stories": 0 if second is not None else 1,
    }
