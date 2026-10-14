# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo engineering brief for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the brief its country's catalogue asks for: structured requirements across the
catalogue categories (with a verification method on every must), a technical concept that decides every
required topic and answers the must requirements, the area and quantity programme, and the framework
schedule: the catalogue's chain dated backwards from the operating proof, plus one milestone for every
gate of the project's phase model. Everything goes through the service, so catalogue pins, codes, audit
rows and the checks are the real ones.

The brief is submitted when the service finds nothing blocking, so the governance gate reads it as in
review. Approval goes through the gate, never through a seeder. Only projects carrying the demo marker
are touched; a project that already has a brief is skipped, so a re-run never duplicates. The text is
German because the demo projects are German.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# (category, entity, attribute, constraint_type, value, unit, priority, verification, originator, role, source)
_REQ = tuple[str, str, str, str, str, str, str, str, str, str, str]

_COMMON: tuple[_REQ, ...] = (
    (
        "performance",
        "Gebäude",
        "Brutto-Grundfläche",
        "max",
        "{bgf}",
        "m2",
        "must",
        "analysis",
        "Bauherr",
        "client",
        "Raumprogramm",
    ),
    (
        "performance",
        "Tragwerk",
        "Nutzlast Regelgeschoss",
        "min",
        "{live}",
        "kN/m2",
        "must",
        "analysis",
        "Tragwerksplanung",
        "designer",
        "DIN EN 1991-1-1",
    ),
    (
        "standards",
        "Brandschutz",
        "Gebäudeklasse",
        "equals",
        "{gk}",
        "",
        "must",
        "inspection",
        "Brandschutzgutachter",
        "authority",
        "{lbo}",
    ),
    (
        "standards",
        "Barrierefreiheit",
        "Anforderung",
        "equals",
        "DIN 18040",
        "",
        "must",
        "inspection",
        "Bauherr",
        "client",
        "{lbo}",
    ),
    (
        "energy_efficiency",
        "Gebäudehuelle",
        "Energiestandard",
        "equals",
        "{energy}",
        "",
        "must",
        "analysis",
        "Bauherr",
        "client",
        "GEG 2024",
    ),
    (
        "energy_efficiency",
        "Wärmeversorgung",
        "Erneuerbarer Anteil",
        "min",
        "65",
        "%",
        "must",
        "analysis",
        "Energieplanung",
        "designer",
        "GEG 2024",
    ),
    (
        "availability",
        "Aufzüge",
        "Verfügbarkeit",
        "min",
        "98",
        "%",
        "should",
        "demonstration",
        "Betreiber",
        "client",
        "Betriebskonzept",
    ),
    (
        "site_conditions",
        "Baugrund",
        "Gründungsempfehlung",
        "equals",
        "Bodenplatte mit Teilunterkellerung",
        "",
        "should",
        "inspection",
        "Baugrundgutachter",
        "designer",
        "Baugrundgutachten",
    ),
    (
        "operation_maintenance",
        "Technik",
        "Wartungszugang je Anlage",
        "exists",
        "",
        "",
        "should",
        "inspection",
        "Facility Management",
        "client",
        "Betriebskonzept",
    ),
    (
        "safety_security",
        "Außenanlagen",
        "Beleuchtung Zugänge",
        "min",
        "10",
        "lx",
        "could",
        "test",
        "Bauherr",
        "client",
        "DIN EN 12464-2",
    ),
)

_PROFILES: dict[str, dict[str, Any]] = {
    "residential-regensburg": {
        "title": "Anforderungsheft Wohnquartier Regensburg Donaupark",
        "summary": (
            "Lastenheft für vier Mehrfamilienhäuser mit rund 120 Wohnungen, Tiefgarage mit 110 Stellplätzen, "
            "KfW-Effizienzhaus 40, Fernwärme und Photovoltaik."
        ),
        "fmt": {"bgf": "16000", "live": "2,0", "gk": "4", "lbo": "BayBO", "energy": "KfW-Effizienzhaus 40"},
        "extra": (
            (
                "performance",
                "Wohnungen",
                "Anzahl Wohneinheiten",
                "equals",
                "120",
                "",
                "must",
                "inspection",
                "Bauherr",
                "client",
                "Raumprogramm",
            ),
            (
                "performance",
                "Tiefgarage",
                "Stellplätze",
                "min",
                "110",
                "",
                "must",
                "inspection",
                "Stadt Regensburg",
                "authority",
                "Stellplatzsatzung",
            ),
            (
                "energy_efficiency",
                "Dach",
                "Photovoltaik Nennleistung",
                "min",
                "250",
                "kWp",
                "should",
                "test",
                "Energieplanung",
                "designer",
                "Energiekonzept",
            ),
        ),
        "programme": (
            ("gross_floor_area", "Brutto-Grundfläche oberirdisch", "m2", "16000", "Flächenberechnung Entwurf"),
            ("net_usable_area", "Wohnfläche", "m2", "10800", "WoFlV, 120 Wohnungen"),
            ("units", "Wohneinheiten", "Stk", "120", "Wohnungsmix 2 bis 4 Zimmer"),
            ("parking_spaces", "Tiefgaragenstellplätze", "Stk", "110", "Stellplatzsatzung"),
        ),
        "topics": {
            "supply": "Fernwärme mit Hausübergabestation je Haus, zentrale Photovoltaik mit Mieterstrom.",
            "building_structure": "Stahlbeton-Massivbau mit Flachdecken, Treppenhäuser als Aussteifung.",
            "construction_method": "Konventionelle Ortbetonbauweise, Tiefgarage zuerst, Häuser taktweise.",
            "commissioning_sequence": "Haus für Haus, Abnahme je Haus, Mieterbezug nach Fertigstellung Außenanlagen.",
            "site_analysis": "Hochwasserbereich Donau geprüft, Baugrube mit Verbau, Grundwasser im Baufeld.",
        },
    },
    "school-ludwigsburg": {
        "title": "Anforderungsheft Grundschule Ludwigsburg Neckarweihingen",
        "summary": (
            "Lastenheft für eine vierzügige Ganztagsgrundschule mit Mensa und Einfeld-Sporthalle, "
            "Wärmepumpe, Photovoltaik und Lüftung mit Wärmerueckgewinnung."
        ),
        "fmt": {
            "bgf": "10500",
            "live": "3,0",
            "gk": "3",
            "lbo": "LBO BW",
            "energy": "Effizienzhaus 40 (Nichtwohngebäude)",
        },
        "extra": (
            (
                "performance",
                "Klassenräume",
                "Anzahl Klassenräume",
                "equals",
                "16",
                "",
                "must",
                "inspection",
                "Stadt Ludwigsburg",
                "client",
                "Schulbauprogramm",
            ),
            (
                "performance",
                "Unterrichtsräume",
                "Nachhallzeit",
                "max",
                "0,6",
                "s",
                "must",
                "test",
                "Bauakustik",
                "designer",
                "DIN 18041",
            ),
            (
                "operation_maintenance",
                "Lüftung",
                "CO2-Konzentration Klassenraum",
                "max",
                "1000",
                "ppm",
                "should",
                "test",
                "Stadt Ludwigsburg",
                "client",
                "Schulbauprogramm",
            ),
        ),
        "programme": (
            (
                "gross_floor_area",
                "Brutto-Grundfläche Schulgebäude, Mensa, Sporthalle",
                "m2",
                "10500",
                "Raumprogramm Stadt Ludwigsburg",
            ),
            ("plot_area", "Grundstück", "m2", "22000", "Liegenschaftskataster"),
            ("units", "Klassenräume", "Stk", "16", "Vierzügigkeit, Ganztag"),
        ),
        "topics": {
            "supply": "Luft-Wasser-Wärmepumpe mit Flächenheizung, Photovoltaik auf allen Dächern.",
            "building_structure": "Stahlbeton-Skelett mit Holzrahmenbau-Fassaden, Sporthalle in Stahl-Holz-Bauweise.",
            "construction_method": "Skelettbau in Ortbeton, Fassadenelemente vorgefertigt, Sporthalle parallel.",
            "commissioning_sequence": "Einregulierung der Lüftung in den Sommerferien, Bezug zum Schuljahresbeginn.",
            "site_analysis": "Schulbetrieb der Nachbarschule bleibt während der Bauzeit bestehen, getrennte Zufahrt.",
        },
    },
}

_FALLBACK = "residential-regensburg"


def _fill(row: _REQ, fmt: dict[str, str]) -> _REQ:
    return tuple(c.format(**fmt) if "{" in c else c for c in row)  # type: ignore[return-value]


async def _seed_project(session: AsyncSession, project_id: uuid.UUID, demo_id: str) -> dict[str, int]:
    from app.modules.engineering_brief.service import EngineeringBriefService
    from app.modules.projects.models import Project

    profile = _PROFILES.get(demo_id, _PROFILES[_FALLBACK])
    project = await session.get(Project, project_id)
    actor = project.owner_id
    svc = EngineeringBriefService(session)
    counts = {"requirements": 0, "concepts": 0, "programme": 0, "milestones": 0, "submitted": 0, "gates_bound": 0}

    await svc.set_brief(
        project_id,
        actor_id=actor,
        tenant_id=None,
        title=profile["title"],
        summary=profile["summary"],
        operation_proof_date=date.today() + timedelta(days=760),
    )

    created: list[Any] = []
    for row in (*_COMMON, *profile["extra"]):
        cat, entity, attr, ctype, value, unit, prio, verif, orig, role, src = _fill(row, profile["fmt"])
        data = {
            "category": cat,
            "entity": entity,
            "attribute": attr,
            "constraint_type": ctype,
            "constraint_value": value,
            "unit": unit,
            "priority": prio,
            "verification_method": verif,
            "originator": orig,
            "originator_role": role,
            "source_ref": src,
        }
        created.append((prio, await svc.create_requirement(project_id, data, actor)))
        counts["requirements"] += 1
    musts = [r.id for prio, r in created if prio == "must"]

    # The concept: one decided item for every topic of the profile, the first carrying the musts it answers.
    brief = await svc.require_brief(project_id)
    catalogue = await svc.catalogue_for(brief)
    titles = {t.code: t for t in catalogue.concept_topics}
    first = True
    for code, decision in profile["topics"].items():
        if code not in titles:
            continue
        await svc.create_concept(
            project_id,
            {
                "topic_code": code,
                "title": decision.split(",")[0].split(".")[0][:120],
                "description": "",
                "decision": decision,
                "requirement_ids": musts if first else [],
            },
            actor,
        )
        first = False
        counts["concepts"] += 1

    for kind, label, unit, qty, basis in profile["programme"]:
        await svc.create_programme(
            project_id, {"kind_code": kind, "label": label, "unit": unit, "quantity": qty, "basis": basis}, actor
        )
        counts["programme"] += 1

    made = await svc.milestones_from_catalogue(project_id, None, actor)
    counts["milestones"] += len(made)
    if catalogue.gate_kind is not None:
        gates = await svc.milestones_from_gates(project_id, actor)
        counts["milestones"] += len(gates)

    # The schedule module takes the milestones and owns the date of every undecided gate. A decided gate
    # keeps what it was decided with; nothing may be refused here, or the demo would show an unbound gate.
    published = await svc.publish_schedule(project_id, actor)
    if published["gates_skipped"]:
        logger.warning("engineering brief demo: gates not bound for %s: %s", project_id, published["gates_skipped"])
    counts["gates_bound"] = len(published["gates_bound"])

    # Submit only what the checks accept; a brief with a blocking finding stays the draft somebody is on.
    blocking = [f for f in await svc.submission_findings(project_id) if f.severity == "error"]
    if not blocking:
        try:
            async with session.begin_nested():
                await svc.submit(project_id, actor)
            counts["submitted"] = 1
        except Exception:
            logger.info("engineering brief demo left as draft for %s", project_id, exc_info=True)
    return counts


async def seed_engineering_brief_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the brief of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.engineering_brief.models import EngineeringBrief
    from app.modules.projects.models import Project

    totals = {
        "projects": 0,
        "requirements": 0,
        "concepts": 0,
        "programme": 0,
        "milestones": 0,
        "submitted": 0,
        "gates_bound": 0,
    }
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid, meta in rows:
        demo_id = demo_id_of(meta)
        if not demo_id:
            continue
        has = (
            await session.execute(select(EngineeringBrief.id).where(EngineeringBrief.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid, demo_id)
        except Exception:
            # One project that cannot be seeded must not take the rest of the demo estate with it.
            logger.warning("engineering brief demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals
