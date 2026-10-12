# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo design management for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets what an owner's design manager would set up in the
first weeks: the numbering scheme its country resolves to, a small WBS (only
when the project has none), the design team as roles with originator codes,
approval points and a design schedule along the phases of the project's
pinned governance model (pinned here through module 1's own country default
when governance has not pinned one), drawings numbered by the generator with
revisions at different suitability, a distribution matrix, a draft release,
an internal review with comments, the expert reports the catalogue lists and
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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DESIGN_SPINE = ("concept", "design", "approval", "detail")


async def seed_design_management_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed every demo project in ``project_ids`` that has no design setup. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.design_management.models import DesignSetup
    from app.modules.projects.models import Project

    totals = {"projects": 0, "drawings": 0, "deliverables": 0, "reports": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (await session.execute(select(DesignSetup.id).where(DesignSetup.project_id == pid))).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("design_management demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _ensure_phase_model(session: AsyncSession, project) -> None:
    """Pin the governance model module 1 would pick for the country, only when none is pinned."""
    from app.modules.project_governance.catalogue import default_catalogue_id_for_country
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    if await GovernanceRepository(session).get_model(project.id) is not None:
        return
    await GovernanceService(session).set_model(
        project.id,
        source="shipped",
        catalogue_id=default_catalogue_id_for_country(project.country_code),
        version=None,
        four_eyes=True,
        actor_id=project.owner_id,
        tenant_id=None,
    )


def _phase_value(scheme_id: str, phase_code: str) -> str:
    m = re.fullmatch(r"lph(\d)", phase_code or "")
    return f"LPH{m.group(1)}" if m else "LPH5"


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.cde.models import DocumentContainer
    from app.modules.cde.schemas import RevisionCreate
    from app.modules.cde.service import CDEService
    from app.modules.design_management.service import DesignService
    from app.modules.projects.models import Project

    project = await session.get(Project, project_id)
    actor = project.owner_id
    await _ensure_phase_model(session, project)
    svc = DesignService(session)
    setup = await svc.set_setup(project_id, actor_id=actor, tenant_id=None)
    scheme = await svc.scheme(setup)
    phases = await svc.phases(project_id)
    design_phases = [p for p in phases if p["spine_key"] in _DESIGN_SPINE] or phases
    p_early = design_phases[0]["code"]
    p_mid = design_phases[min(1, len(design_phases) - 1)]["code"]
    p_late = design_phases[-1]["code"]

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

    de = scheme.id == "de_planschluessel"
    disc = {"arch": "AR" if de else "A", "struct": "TW" if de else "S", "mep": "HL" if de else "M"}
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
        ("DL-003", "Permit drawings", p_mid, "arch", 3),
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
    for title, role, dl, phase, form, spatial, sheet_type, suit in (
        ("Ground floor plan", "arch", "DL-001", p_early, "GR" if de else "DR", "EG" if de else "00", "1", "S3"),
        ("Section A-A", "arch", "DL-001", p_early, "SC" if de else "DR", "EG" if de else "ZZ", "3", "S4"),
        ("Foundation layout", "struct", "DL-002", p_early, "GR" if de else "DR", "UG" if de else "B1", "1", "S2"),
        ("Site plan for the permit", "arch", "DL-003", p_mid, "LP" if de else "DR", "EG" if de else "ZZ", "0", "A4"),
        ("Elevations for the permit", "arch", "DL-003", p_mid, "AN" if de else "DR", "EG" if de else "ZZ", "2", "S0"),
        ("Ventilation ground floor", "mep", "DL-004", p_late, "GR" if de else "DR", "EG" if de else "00", "1", "S0"),
    ):
        fields = {
            "project": (project.project_code or "DEMO").upper()[:6]
            if len(project.project_code or "DEMO") >= 2
            else "DEMO",
            "functional": "ZZ",
            "spatial": spatial,
            "form": form,
            "custom_sheet_type": sheet_type,
            "phase": _phase_value(scheme.id, phase),
        }
        fields["project"] = re.sub(r"[^A-Z0-9]", "", fields["project"]) or "DEMO"
        drawing, container = await svc.create_drawing(
            project_id,
            {
                "title": title,
                "role_id": roles[role].id,
                "deliverable_id": deliverables[dl].id,
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
        {"recipient_role_id": roles["owner"].id, "purpose": "for_information", "min_suitability": "S2"},
        actor_id=actor,
    )
    await svc.create_dist_rule(
        project_id,
        {"recipient_role_id": roles["struct"].id, "discipline_codes": [disc["arch"]], "purpose": "for_review"},
        actor_id=actor,
    )
    await svc.create_dist_rule(
        project_id,
        {"recipient_role_id": roles["mep"].id, "discipline_codes": [disc["arch"], disc["struct"]], "format": "native"},
        actor_id=actor,
    )
    shared = [r.id for _d, c, r in drawing_rows if c.cde_state != "wip"]
    await svc.create_release(
        project_id, {"code": "REL-001", "title": "Concept issue", "revision_ids": shared[:3]}, actor_id=actor
    )

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
        await svc.add_comment(
            project_id,
            review.id,
            {"text": text, "severity": severity, "revision_id": drawing_rows[idx][2].id},
            actor_id=actor,
        )

    count_reports = 0
    for code, kind, phase, status, author, checker in (
        ("RPT-001", "geotechnical", p_early, "accepted", "struct", None),
        ("RPT-002", "fire_safety_concept", p_mid, "in_progress", "fire", None),
        ("RPT-003", "structural_design", p_mid, "commissioned", "struct", None),
        ("RPT-004", "structural_proof_check", p_mid, "required", "struct", "checker"),
        ("RPT-005", "thermal_energy", p_mid, "required", "mep", None),
    ):
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
    return {"drawings": len(drawing_rows), "deliverables": len(deliverables), "reports": count_reports}
