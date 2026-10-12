# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers (PDF and XLSX) of design management, rule 25.

Four registers: the drawing register, the distribution matrix, the reports
list and a permit package. Built on :mod:`app.core.register_export`; every
label comes from this module's message bundle. The same bytes are what a
frame document stores as a CDE revision (rule 23).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.design_management.messages import translate

REGISTERS = ("register", "matrix", "reports", "permit")

_COLUMNS: dict[str, tuple[tuple[str, dict[str, Any]], ...]] = {
    "register": (
        ("col_number", {"nobreak": True}),
        ("col_title", {"weight": 2.5, "wrap": True, "xlsx_width": 40}),
        ("col_revision", {}),
        ("col_status", {}),
        ("col_state", {}),
        ("col_phase", {}),
        ("col_discipline", {}),
        ("col_last_issue", {"kind": "date"}),
        ("col_recipients", {"wrap": True}),
    ),
    "matrix": (
        ("col_recipient", {"weight": 2, "wrap": True}),
        ("col_disciplines", {}),
        ("col_forms", {}),
        ("col_phases", {}),
        ("col_min_status", {}),
        ("col_purpose", {}),
        ("col_format", {}),
        ("col_copies", {"kind": "count"}),
    ),
    "reports": (
        ("col_code", {"nobreak": True}),
        ("col_kind", {"weight": 2, "wrap": True}),
        ("col_title", {"weight": 2, "wrap": True}),
        ("col_phase", {}),
        ("col_check", {}),
        ("col_state", {}),
    ),
    "permit": (
        ("col_kind", {}),
        ("col_title", {"weight": 2.5, "wrap": True}),
        ("col_required", {}),
        ("col_present", {}),
        ("col_pinned_revision", {}),
    ),
}


def document(register: str, rows: Sequence[Sequence[Any]], *, project_name: str, locale: str) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"design.export.{key}", locale=locale)

    return RegisterDocument(
        title=t(f"title_{register}"),
        columns=[RegisterColumn(t(key), **kw) for key, kw in _COLUMNS[register]],
        rows=[list(r) for r in rows],
        details=[(t("project"), project_name)],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t(f"title_{register}"),
    )


def render(register: str, rows: Sequence[Sequence[Any]], *, project_name: str, locale: str, fmt: str) -> bytes:
    """PDF or XLSX bytes of one register."""
    doc = document(register, rows, project_name=project_name, locale=locale)
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
