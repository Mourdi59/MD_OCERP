# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The three permit registers as printable documents (PDF and XLSX).

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle. These exports are what the governance frame documents
the governance model hosts permits in stores as CDE revisions at a gate (rule 18).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.permits.messages import translate

_COLUMNS: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "roadmap": [
        ("permit_type_code", "col_type", {"nobreak": True}),
        ("title", "col_title", {"weight": 2.0, "wrap": True, "xlsx_width": 36}),
        ("applicant_role", "col_applicant", {}),
        ("state", "col_state", {}),
        ("needed_by", "col_needed_by", {"kind": "date"}),
        ("latest_submit", "col_latest_submit", {"kind": "date"}),
        ("forecast_decision", "col_forecast", {"kind": "date"}),
        ("conflict_days", "col_conflict_days", {"kind": "count"}),
    ],
    "conditions": [
        ("number", "col_number", {"nobreak": True}),
        ("permit_reference", "col_permit", {}),
        ("text", "col_text", {"weight": 3.0, "wrap": True, "xlsx_width": 60}),
        ("kind", "col_kind", {}),
        ("trigger", "col_trigger", {}),
        ("topic", "col_topic", {}),
        ("due_date", "col_due", {"kind": "date"}),
        ("state", "col_state", {}),
        ("evidence_count", "col_evidence", {"kind": "count"}),
    ],
    "permits": [
        ("permit_type_code", "col_type", {"nobreak": True}),
        ("reference", "col_reference", {}),
        ("scope", "col_scope", {}),
        ("state", "col_state", {}),
        ("valid_until", "col_valid_until", {"kind": "date"}),
        ("start_notified_at", "col_started", {"kind": "date"}),
    ],
}
_ENUMS = {"state", "kind", "trigger", "topic", "scope", "applicant_role"}


def register_document(
    register: str, rows: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str
) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"permits.export.{key}", locale=locale)

    spec = _COLUMNS[register]
    out_rows = []
    for r in rows:
        line = []
        for field, _label, _kw in spec:
            value = r.get(field)
            if field in _ENUMS and value:
                value = translate(f"permits.enum.{field}.{value}", locale=locale)
            line.append("" if value is None else value)
        out_rows.append(line)
    return RegisterDocument(
        title=t(f"title_{register}"),
        columns=[RegisterColumn(t(label), **kw) for _f, label, kw in spec],
        rows=out_rows,
        details=[(t("project"), project_name), (t("as_of"), as_of)],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t(f"title_{register}"),
    )


def render(
    register: str, rows: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str, fmt: str
) -> bytes:
    doc = register_document(register, rows, project_name=project_name, locale=locale, as_of=as_of)
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
