# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers of the quality concept (PDF and XLSX).

Five registers, one per area: proofs, stage progress, acceptance units,
preservation surveys and certification targets. Each is a flat projection of
rows the API already serves; headers come from ``quality_concept.export.*``.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.quality_concept import evaluator as ev
from app.modules.quality_concept.messages import translate
from app.modules.quality_concept.models import (
    AcceptanceUnit,
    CertificationTarget,
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


def _text(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    return "" if value is None else value


async def render(svc: Any, project_id: uuid.UUID, *, what: str, fmt: str, locale: str) -> bytes:
    """Build the ``what`` register of the project as ``fmt`` (pdf or xlsx)."""
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
    doc = RegisterDocument(
        title=t(f"{what}.title"),
        columns=[RegisterColumn(t(f"col.{f}"), kind=k) for f, k in fields],
        rows=table,
        locale=locale,
        empty_text=t("empty"),
        sheet_title=t(f"{what}.title")[:31],
    )
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
