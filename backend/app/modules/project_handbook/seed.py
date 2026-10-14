# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo project handbook for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets a handbook that reads like one a project team would keep: every chapter of the
catalogue carries German text about that project, owners are the people of the project, and the chapters
stand at different points of their life: most approved (the main one in two versions), two in review, the
rest still in draft. Everything goes through the service, so catalogue pins, versions, four-eyes and the
audit trail are the real ones; the approver is the project's decider, never the person who submitted.

The data room is materialised from the phase model the project pinned, and the documents the demo
register already holds are filed into its folders by category. Only projects carrying the demo marker are
touched; a project that already has a handbook is skipped, so a re-run never duplicates. The text is
German because the demo projects are German.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PROFILES: dict[str, dict[str, str]] = {
    "residential-regensburg": {
        # The site runs: the handbook is in its second edition.
        "edition": "Ausgabe 2, Ausführungsphase",
        "name": "Wohnquartier Regensburg Donaupark",
        "kind": "ein Wohnquartier mit vier Mehrfamilienhäusern",
        "size": "rund 120 Wohnungen und einer Tiefgarage mit 110 Stellplätzen",
        "standard": "KfW-Effizienzhaus 40",
        "supply": "Fernwärme und Photovoltaik auf allen Dächern",
        "client": "die Donaupark Wohnbau GmbH",
        "authority": "die Stadt Regensburg",
        "law": "der Bayerischen Bauordnung",
        "site": "Die Baustelle liegt in einem bewohnten Quartier. Zufahrt und Anlieferung laufen über die Donaustraße, "
        "die Nachbarn werden vor lärmintensiven Arbeiten informiert.",
        "hse": "Tiefgaragenbau mit Verbau und Wasserhaltung, Kranarbeiten über bewohnten Nachbargrundstücken",
        "structure": "Stahlbeton-Skelett mit vorgefertigten Balkonen",
        "period": "Bezug der ersten Wohnungen zwölf Monate nach Baubeginn des ersten Hauses",
    },
    "school-ludwigsburg": {
        "edition": "Ausgabe 1, Entwicklungsphase",
        "name": "Schulzentrum Ludwigsburg",
        "kind": "ein vierzügiges Gymnasium mit Mensa und Sporthalle",
        "size": "16 Klassenräumen, Fachräumen, Mensa und einer Dreifeldhalle auf rund 10.500 m² Brutto-Grundfläche",
        "standard": "dem Schulbauprogramm der Stadt",
        "supply": "Luft-Wasser-Wärmepumpe mit Flächenheizung und Photovoltaik",
        "client": "die Stadt Ludwigsburg",
        "authority": "das Baurechtsamt der Stadt Ludwigsburg",
        "law": "der Landesbauordnung Baden-Württemberg",
        "site": "Der Schulbetrieb der Nachbarschule läuft während der Bauzeit weiter. Baustellenzufahrt und Schulweg "
        "sind getrennt, Lärmspitzen werden mit der Schulleitung abgestimmt.",
        "hse": "Arbeiten neben dem laufenden Schulbetrieb, Fassadenmontage an der Schulstraße, Hallendach in Stahl-Holz-Bauweise",
        "structure": "Stahlbeton-Skelett mit Holzrahmenbau-Fassaden, Sporthalle in Stahl-Holz-Bauweise",
        "period": "Bezug zum Schuljahresbeginn, Einregulierung der Lüftung in den Sommerferien",
    },
}
_FALLBACK = "residential-regensburg"

# Chapter code -> how far the chapter has come: approved | revised | review | draft.
_PLAN: dict[str, str] = {
    "principles": "revised",
    "organisation": "approved",
    "communication": "approved",
    "phase_model": "review",
    "data_room": "review",
    "contracts": "approved",
    "engineering": "approved",
    "equipment": "draft",
    "personnel": "approved",
    "logistics": "draft",
    "design": "draft",
    "procurement": "draft",
    "commercial": "draft",
    "quality": "draft",
    "hse": "draft",
}
# Chapters owned by the cost login; the rest belong to the project owner.
_COST_AREAS = frozenset({"m08_procurement", "m09_commercial"})

# Where an existing demo document is filed: its category -> folder code in the data room.
_CATEGORY_FOLDER: dict[str, str] = {
    "drawing": "m07_design_management/dev_design_concept",
    "contract": "m02_contract_management/dev_contract_requirements",
    "specification": "m03_engineering_scheduling/dev_technical_requirements",
    "correspondence": "m01_project_management/exec_correspondence",
    "other": "m01_project_management/dev_project_handbook",
}


def _texts(p: dict[str, str]) -> dict[str, str]:
    """The German chapter texts of one project. Plain text with blank-line paragraphs."""
    return {
        "principles": (
            f"Dieses Handbuch gilt für das Projekt {p['name']}: {p['kind']} mit {p['size']}. "
            f"Bauherr ist {p['client']}; das Projekt wird nach {p['standard']} geplant und gebaut.\n\n"
            "Ziele in dieser Reihenfolge: Kosten- und Terminsicherheit vor Ausstattungswünschen, eine "
            "nachvollziehbare Entscheidung an jedem Gate, und eine Bauakte, die beim Betreiber ohne Rückfragen "
            "weiterverwendet werden kann.\n\n"
            "Grundsätze: Entscheidungen werden schriftlich getroffen und im System abgelegt. Jedes Kapitel dieses "
            "Handbuchs hat einen Verantwortlichen und eine freigegebene Fassung; geändert wird nur über eine neue "
            "Fassung mit Vier-Augen-Freigabe."
        ),
        "organisation": (
            f"Die Projektorganisation bildet Bauherr, Projektsteuerung, Planer und ausführende Firmen für {p['name']} ab. "
            "Die Beteiligten und Stellen stehen unten live aus den Modulen Stakeholder und Personal; sie werden hier "
            "nicht abgeschrieben, damit dieses Kapitel nie von der Wirklichkeit abweicht.\n\n"
            "Entscheidungsebenen: Der Lenkungskreis tagt monatlich und entscheidet über Budget, Termine und Gates. "
            "Das Projektteam trifft sich wöchentlich. Der Projektleiter des Bauherrn ist Eskalationsstufe eins, "
            "der Projektdirektor Stufe zwei.\n\n"
            "Vertretungen sind für jede Schlüsselrolle benannt; fehlt eine Besetzung, steht sie im Personalplan "
            "als offene Stelle mit Eintrittsdatum."
        ),
        "communication": (
            "Kommunikationsregeln des Projekts:\n\n"
            "1. Verbindliche Anweisungen, Freigaben und Änderungen ergehen schriftlich über das Projektsystem, nicht per Zuruf "
            "oder Telefonnotiz.\n"
            "2. Pläne und Unterlagen werden ausschließlich über den Datenraum ausgetauscht. Jede Datei liegt im Ordner "
            "ihres Bereichs; Versandwege per E-Mail sind keine Quelle.\n"
            "3. Besprechungen haben eine Tagesordnung vorab und ein Protokoll innerhalb von zwei Arbeitstagen.\n"
            "4. Antworten auf Anfragen der Beteiligten kommen innerhalb von fünf Arbeitstagen, bei Terminrelevanz innerhalb von zwei.\n"
            "5. Nach außen (Presse, Nachbarn, Behörden) spricht nur der Projektleiter des Bauherrn oder wen er benennt.\n\n"
            f"{p['site']}"
        ),
        "phase_model": (
            "Das Projekt läuft in zwei Phasen, Entwicklung und Ausführung, mit einem Gate dazwischen. "
            "Am Gate entscheidet der Lenkungskreis über den Beginn der Ausführung; Grundlage sind die Rahmendokumente "
            "der elf Bereiche und der Nachweis, dass die Pflichtkapitel dieses Handbuchs freigegeben sind.\n\n"
            "Die Gates, die Bereiche und ihre Verantwortlichen stehen unten live aus dem Modul Projektsteuerung. "
            "Eine Entscheidung mit Auflagen ist möglich; Auflagen haben einen Verantwortlichen und eine Frist."
        ),
        "data_room": (
            "Der Datenraum ist die einzige Ablage der Projektunterlagen. Seine Ordnerstruktur folgt den elf Bereichen "
            "des Phasenmodells: je Bereich ein Hauptordner, darunter die Arbeitsordner der Entwicklungs- und der "
            "Ausführungsphase.\n\n"
            "Ablageregel: Ein Dokument liegt in genau einem Ordner, und zwar im Ordner des Bereichs, der den "
            "Inhalt verantwortet. Pläne gehen in die Planungsverwaltung, Verträge in die Vertragsverwaltung, "
            "Schriftverkehr in den Ordner Korrespondenz. Die Übersicht unten zeigt, wie viele Ordner und Dokumente "
            "je Bereich im Datenraum liegen."
        ),
        "contracts": (
            f"Vertragsmanagement: Die Verträge mit Planern und ausführenden Firmen schließt {p['client']} ab. "
            "Grundlage sind VOB/B für Bauleistungen und die HOAI für Planerleistungen. Jeder Vertrag hat einen "
            "Vertragsverantwortlichen und wird im Datenraum im Ordner Vertragsanforderungen abgelegt.\n\n"
            f"Genehmigungen: Das Genehmigungsverfahren läuft bei {p['authority']} nach {p['law']}. "
            "Auflagen aus dem Bescheid werden im Genehmigungsmodul geführt und vor Baubeginn der betroffenen Gewerke geschlossen."
        ),
        "engineering": (
            f"Technik und Terminplanung: Das technische Konzept sieht {p['structure']} vor, "
            f"die Versorgung erfolgt über {p['supply']}.\n\n"
            "Der Rahmenterminplan ist rückwärts vom Betriebsnachweis geplant und an die Gates gebunden. "
            f"Die Meilensteine stehen unten live aus dem Modul Lastenheft und Terminplanung. Vorgabe: {p['period']}."
        ),
        "equipment": (
            "Anlagen und Ausrüstung: Für die technische Gebäudeausrüstung wird ein Anlagenverzeichnis geführt. "
            f"Langläufer (Wärmeerzeugung, Aufzüge, Schaltanlagen) werden früh bestellt, damit der Einbau mit dem Rohbau "
            f"zusammenpasst. Die Versorgung über {p['supply']} bestimmt die Hauptanlagen.\n\n"
            "Zuständig für das Verzeichnis ist der Projektleiter Technik; Lieferzeiten werden quartalsweise mit den Herstellern abgeglichen."
        ),
        "personnel": (
            "Personal und Besetzung: Der Personalplan des Projekts unterscheidet Entwicklungs- und Ausführungsphase. "
            "Schlüsselrollen sind Projektleiter, Bauleiter, Sicherheits- und Gesundheitsschutzkoordinator sowie Dokumentenkontrolle. "
            "Die Stellen stehen unten live aus dem Modul Personal.\n\n"
            "Für die Ausführungsphase werden Bauleiter und Fachbauleiter bis zum Gate benannt; eine offene Schlüsselrolle "
            "wird am Gate als Risiko ausgewiesen."
        ),
        "logistics": (
            "Logistik: Das Baustellenlogistikkonzept regelt Zufahrt, Kranstandorte, Lagerflächen und Anlieferzeiten.\n\n"
            f"{p['site']}\n\n"
            "Anlieferungen werden vorab über ein Zeitfenstersystem gebucht. Schwertransporte werden mit der Straßenverkehrsbehörde abgestimmt."
        ),
        "design": (
            "Planungsmanagement: Planungsleistungen werden nach Leistungsphasen der HOAI vergeben und überwacht. "
            "Der Planungsterminplan enthält Planlieferungen, Prüfstatik und Freigaben. Pläne werden nach dem "
            "Projektnummernsystem benannt und über den Datenraum verteilt; ein Plan gilt erst mit Freigabevermerk als Ausführungsunterlage.\n\n"
            "Planungsstände werden im Wochentakt mit den Fachplanern abgeglichen, offene Planungsfragen laufen als Anfragen mit Fristen."
        ),
        "procurement": (
            "Beschaffung und Vergabe: Bauleistungen werden nach Gewerken ausgeschrieben, Lose und Termine stehen im "
            "Vergabekonzept. Wertgrenzen: bis zur Schwelle des Projektleiters entscheidet dieser, darüber der Lenkungskreis. "
            "Vergaben erfolgen nach Preisspiegel und Eignungsprüfung, jede Zuschlagsentscheidung wird begründet abgelegt.\n\n"
            "Der Vergabeterminplan ist an den Bestelltermin der Langläufer gebunden: kein Los wird später vergeben, als die Lieferzeit erlaubt."
        ),
        "commercial": (
            "Kaufmännisches Management: Das Budget ist nach DIN 276 gegliedert und wird monatlich mit Obligo und Prognose fortgeschrieben. "
            "Verpflichtungen werden nur freigegeben, wenn sie im Budget gedeckt sind; Nachträge laufen über das Änderungsverfahren "
            "mit Vier-Augen-Freigabe.\n\n"
            "Zahlungen erfolgen nach Prüfung durch Bauleitung und Projektsteuerung. Skonto und Sicherheitseinbehalte "
            "werden je Vertrag geführt."
        ),
        "quality": (
            "Qualitätsmanagement: Qualitätsanforderungen stammen aus Leistungsverzeichnis, Normen und den Zielen des Bauherrn "
            f"({p['standard']}). Für jedes Gewerk gibt es einen Prüfplan mit Hold Points; ohne Freigabe am Hold Point wird nicht weitergebaut.\n\n"
            "Mängel werden zentral erfasst, mit Frist und Verantwortlichem versehen und vor der Abnahme geschlossen. "
            "Die Dokumentation für den Betreiber wird von Beginn an mitgeführt."
        ),
        "hse": (
            f"Arbeitsschutz, Gesundheit und Umwelt: Besondere Gefährdungen auf dieser Baustelle sind {p['hse']}.\n\n"
            "Der SiGeKo wird vor Planungsabschluss bestellt, der SiGe-Plan liegt vor Baubeginn vor. Jede Firma weist ihre "
            "Unterweisungen nach; Erlaubnisscheine für Arbeiten mit erhöhtem Risiko gibt die Bauleitung aus. "
            "Unfälle und Beinaheunfälle werden am selben Tag gemeldet."
        ),
    }


async def _seed_project(session: AsyncSession, project_id: uuid.UUID, demo_id: str) -> dict[str, int]:
    from app.core.demo_cast import find_cast
    from app.modules.project_handbook import data_room
    from app.modules.project_handbook.service import Actor, ProjectHandbookService
    from app.modules.projects.models import Project

    project = await session.get(Project, project_id)
    owner = project.owner_id
    profile = _PROFILES.get(demo_id, _PROFILES[_FALLBACK])
    texts = _texts(profile)
    cast = await find_cast(session)
    cost = cast.get("cost") or owner
    decider = cast.get("decider")
    svc = ProjectHandbookService(session)
    counts = {"chapters": 0, "approved": 0, "in_review": 0, "versions": 0, "folders": 0, "filed": 0}

    await svc.create_handbook(
        project_id,
        actor_id=owner,
        tenant_id=None,
        title=f"Projekthandbuch {project.name}",
        edition=profile["edition"],
        default_owner_id=owner,
    )
    for row in await svc._chapters(project_id):
        who = cost if row.area_code in _COST_AREAS else owner
        text = texts.get(row.code, "")
        plan = _PLAN.get(row.code, "draft")
        author = Actor(who, edit=True)
        approver = Actor(decider, manage=True, edit=True) if decider is not None else None
        draft = text
        if plan == "revised":
            # The first approved version is the short one; the revision adds the full text.
            draft = text.split("\n\n")[0]
        await svc.patch_chapter(project_id, row.code, {"content": draft, "owner_id": who}, author)
        counts["chapters"] += 1
        if plan == "draft":
            continue
        await svc.submit(project_id, row.code, author)
        if plan == "review" or approver is None:
            counts["in_review"] += 1
            continue
        await svc.approve(project_id, row.code, approver)
        counts["approved"] += 1
        counts["versions"] += 1
        if plan == "revised":
            await svc.patch_chapter(project_id, row.code, {"content": text}, author)
            await svc.submit(project_id, row.code, author)
            await svc.approve(project_id, row.code, approver)
            counts["versions"] += 1

    try:
        async with session.begin_nested():
            result = await data_room.materialise(session, project_id)
        counts["folders"] = result["folders"]
    except Exception:
        logger.info("data room not materialised for %s: no phase model", project_id)
        return counts
    counts["filed"] = await _file_documents(session, project_id)
    return counts


async def _file_documents(session: AsyncSession, project_id: uuid.UUID) -> int:
    """File the project's unfiled documents into the folder their category names."""
    from app.modules.documents.models import Document, DocumentFolder

    folders = {
        f.code: f.id
        for f in (
            await session.execute(select(DocumentFolder).where(DocumentFolder.project_id == project_id))
        ).scalars()
    }
    filed = 0
    docs = (
        await session.execute(select(Document).where(Document.project_id == project_id, Document.folder_id.is_(None)))
    ).scalars()
    for doc in docs:
        target = folders.get(_CATEGORY_FOLDER.get(doc.category or "other", ""))
        if target is not None:
            doc.folder_id = target
            filed += 1
    await session.flush()
    return filed


async def seed_project_handbook_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the handbook of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.project_handbook.models import Handbook
    from app.modules.projects.models import Project

    totals = {"projects": 0, "chapters": 0, "approved": 0, "in_review": 0, "versions": 0, "folders": 0, "filed": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid, meta in rows:
        demo_id = demo_id_of(meta)
        if not demo_id:
            continue
        has = (await session.execute(select(Handbook.id).where(Handbook.project_id == pid))).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts: Any = await _seed_project(session, pid, demo_id)
        except Exception:
            # One project that cannot be seeded must not take the rest of the demo estate with it.
            logger.warning("project handbook demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals
