# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers of the quality concept (PDF and XLSX).

Five registers, one per area: proofs, stage progress, acceptance units,
preservation surveys and certification targets, each a flat projection of rows
the API already serves. Two matrices on top: packages by evidence type and
systems by stage, the cell being the state. The acceptance plan carries the
legal effects of each unit's regime and where each one is sourced. Headers
come from ``quality_concept.export.*``.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.quality_concept import evaluator as ev
from app.modules.quality_concept.messages import DEFAULT_LOCALE, is_key_present, translate
from app.modules.quality_concept.models import (
    AcceptanceUnit,
    CertificationTarget,
    CommissioningStageDef,
    PreservationSurvey,
    ProofRequirement,
    StageProgress,
)

# register -> (model, [(field, column kind)])
_LAYOUT: dict[str, tuple[type, list[tuple[str, str]]]] = {
    "proofs": (
        ProofRequirement,
        [
            ("title", "text"),
            ("package_ref", "text"),
            ("evidence_type", "text"),
            ("deliverer_role", "text"),
            ("state", "text"),
        ],
    ),
    "stages": (
        StageProgress,
        [("system_id", "text"), ("stage_code", "text"), ("state", "text"), ("released_at", "text")],
    ),
    "acceptance": (
        AcceptanceUnit,
        [
            ("code", "text"),
            ("title", "text"),
            ("kind", "text"),
            ("regime_code", "text"),
            ("state", "text"),
            ("planned_date", "date"),
            ("accepted_on", "date"),
        ],
    ),
    "preservation": (
        PreservationSurvey,
        [
            ("subject_ref", "text"),
            ("phase", "text"),
            ("state", "text"),
            ("planned_date", "date"),
            ("survey_date", "date"),
        ],
    ),
    "certification": (
        CertificationTarget,
        [
            ("scheme_code", "text"),
            ("scope", "text"),
            ("target_level", "text"),
            ("achieved_level", "text"),
            ("state", "text"),
        ],
    ),
}


MATRICES = ("proof_matrix", "stage_matrix")


def pivot(cells: Iterable[tuple[str, str, str]], columns: Sequence[str], rows: Sequence[str] = ()) -> list[list[str]]:
    """``(row, column, value)`` triples as a table: one line per row label, one cell per column.

    Row labels keep the order of ``rows`` and then of first appearance; several values in
    one cell are joined; a column nobody wrote to stays empty. A triple naming a column that
    is not in ``columns`` is an error, never dropped.
    """
    index = {c: i for i, c in enumerate(columns)}
    table: dict[str, list[list[str]]] = {r: [[] for _ in columns] for r in rows}
    for row, column, value in cells:
        table.setdefault(row, [[] for _ in columns])[index[column]].append(value)
    return [[row, *(", ".join(values) for values in line)] for row, line in table.items()]


def _text(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    return "" if value is None else value


def rendered_language(locale: str) -> str:
    """The language the export's own texts come out in for a reader who asked for ``locale``.

    The module ships fewer languages than the interface offers. A regional code falls back to
    its base language and anything else to English, which is what ``translate`` does; this says
    which of the three happened, so the response can declare it.
    """
    probe = "quality_concept.export.empty"
    base = locale.replace("_", "-").split("-")[0]
    for candidate in (locale, base):
        if candidate and is_key_present(probe, locale=candidate):
            return candidate
    return DEFAULT_LOCALE


async def render(svc: Any, project_id: uuid.UUID, *, what: str, fmt: str, locale: str) -> bytes:
    """Build the ``what`` register of the project as ``fmt`` (pdf or xlsx)."""
    if what in MATRICES:
        return _build(await _matrix(svc, project_id, what, locale), fmt)
    model, fields = _LAYOUT[what]
    rows = await svc.repo.list(model, project_id)
    if what == "proofs":
        delivery = await svc.proof_delivery(project_id, rows)
        derived = {p.id: ev.proof_state(delivery[p.id].state if p.id in delivery else "open", p.decision) for p in rows}
    else:
        derived = {}

    def t(key: str) -> str:
        return translate(f"quality_concept.export.{key}", locale=locale)

    def cell(row: Any, field: str) -> Any:
        if field == "state" and row.id in derived:
            return derived[row.id]
        value = getattr(row, field, None)
        return value.isoformat() if isinstance(value, datetime) else _text(value)

    table = [[cell(r, f) for f, _k in fields] for r in rows]
    columns = [RegisterColumn(t(f"col.{f}"), kind=k) for f, k in fields]
    if what == "acceptance":
        # The acceptance plan names the legal effects of each act and the source of each one.
        cat = await svc.catalogue_for(await svc.require_concept(project_id))
        columns += [RegisterColumn(t("col_effects")), RegisterColumn(t("col_sources"))]
        for unit, line in zip(rows, table, strict=True):
            regime = cat.regime(unit.regime_code)
            effects = list(regime.effects) if regime else []
            line.append(", ".join(e.effect for e in effects))
            line.append(", ".join(sorted({e.source_url for e in effects if e.source_url})))
    doc = RegisterDocument(
        title=t(f"{what}.title"),
        columns=columns,
        rows=table,
        locale=locale,
        empty_text=t("empty"),
        sheet_title=t(f"{what}.title")[:31],
    )
    return _build(doc, fmt)


async def _matrix(svc: Any, project_id: uuid.UUID, what: str, locale: str) -> RegisterDocument:
    """Packages by evidence type, or systems by stage; the cell is the state."""

    def t(key: str) -> str:
        return translate(f"quality_concept.export.{key}", locale=locale)

    if what == "proof_matrix":
        proofs = await svc.repo.list(ProofRequirement, project_id)
        delivery = await svc.proof_delivery(project_id, proofs)
        concept = await svc.require_concept(project_id)
        packages = [p["ref"] for p in await svc.applicable_packages(concept)]
        columns = sorted({p.evidence_type for p in proofs})
        cells = [
            (p.package_ref or "", p.evidence_type, ev.proof_state(delivery[p.id].state, p.decision)) for p in proofs
        ]
        first = t("col.package_ref")
        table = pivot(cells, columns, packages)
    else:
        from sqlalchemy import select

        from app.modules.commissioning.models import CxSystem

        stages = await svc.repo.list(CommissioningStageDef, project_id, CommissioningStageDef.order)
        names = {s.code: s.name_override or s.code for s in stages}
        systems = {
            x.id: " ".join(part for part in (x.tag, x.name) if part)
            for x in (await svc.session.execute(select(CxSystem).where(CxSystem.project_id == project_id))).scalars()
        }
        columns = [names[s.code] for s in stages]
        cells = [
            (systems.get(r.system_id, str(r.system_id)), names[r.stage_code], r.state)
            for r in await svc.repo.list(StageProgress, project_id)
            if r.stage_code in names
        ]
        first = t("col.system_id")
        table = pivot(cells, columns)
    return RegisterDocument(
        title=t(f"{what}.title"),
        columns=[RegisterColumn(first), *(RegisterColumn(c) for c in columns)],
        rows=table,
        locale=locale,
        empty_text=t("empty"),
        sheet_title=t(f"{what}.title")[:31],
    )


def _build(doc: RegisterDocument, fmt: str) -> bytes:
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
