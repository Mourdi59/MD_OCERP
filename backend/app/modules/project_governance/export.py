# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The governance decision trail as a printable register (PDF and XLSX).

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle, so the sheet is in the reader's language wherever a locale
file exists and falls back to English otherwise.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.project_governance.evaluator import trail_rows
from app.modules.project_governance.messages import DEFAULT_LOCALE, available_locales, translate


def written_locale(requested: str | None) -> str:
    """The language the export is actually written in for a requested locale.

    The message bundle answers a locale it does not ship in English, so that
    is what the response has to declare, not what the reader asked for.
    """
    return requested if requested and requested in available_locales() else DEFAULT_LOCALE


def trail_document(trail: Sequence[dict[str, Any]], *, project_name: str, locale: str) -> RegisterDocument:
    """The register document for one project's decision trail."""

    def t(key: str) -> str:
        return translate(f"governance.export.{key}", locale=locale)

    rows = [
        [
            r["gate_code"],
            r["attempt_no"],
            translate(r["outcome_key"], locale=locale),
            r["decided_by"],
            r["decided_at"],
            r["rationale"],
            r["conditions"],
            r["proceed_at_risk_areas"],
        ]
        for r in trail_rows(trail)
    ]
    return RegisterDocument(
        title=t("title"),
        columns=[
            RegisterColumn(t("col_gate"), nobreak=True),
            RegisterColumn(t("col_attempt"), kind="count"),
            RegisterColumn(t("col_outcome")),
            RegisterColumn(t("col_decided_by"), pdf=False),
            RegisterColumn(t("col_decided_at"), kind="date"),
            RegisterColumn(t("col_rationale"), weight=3.0, wrap=True, xlsx_width=60),
            RegisterColumn(t("col_conditions"), kind="count"),
            RegisterColumn(t("col_at_risk")),
        ],
        rows=rows,
        details=[(t("project"), project_name)],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t("title"),
    )


def render(trail: Sequence[dict[str, Any]], *, project_name: str, locale: str, fmt: str) -> bytes:
    """PDF or XLSX bytes of the trail."""
    doc = trail_document(trail, project_name=project_name, locale=locale)
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
