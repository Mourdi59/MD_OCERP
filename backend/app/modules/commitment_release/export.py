# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The commitment matrix as a printable register (PDF and XLSX).

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle. This export is also what the governance frame document
``dev_commitment_matrix`` stores as a CDE revision at a gate, so the binding
version is the snapshot and the live matrix keeps moving.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.commitment_release.messages import translate


def _dec(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def matrix_document(views: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str) -> RegisterDocument:
    """The register document for one project's matrix (rows as ``CommitmentService.item_views`` returns them)."""

    def t(key: str) -> str:
        return translate(f"commitment.export.{key}", locale=locale)

    rows = []
    for v in views:
        e = v.get("exposure") or {}
        rows.append(
            [
                v["code"],
                v["title"],
                translate(f"commitment.type.{v['commitment_type']}", locale=locale),
                translate(f"commitment.status.{v['status']}", locale=locale),
                v["schedule_currency"],
                _dec(v.get("planned_in_schedule_currency")),
                _dec(v.get("released")),
                _dec(v.get("committed")),
                v.get("required_tier_for_planned") or "",
                v.get("latest_decision_date") or "",
                t("overdue") if v.get("decision_overdue") else "",
                v.get("open_preconditions", 0),
                _dec(e.get("residual_loss")),
            ]
        )
    return RegisterDocument(
        title=t("title"),
        columns=[
            RegisterColumn(t("col_code"), nobreak=True),
            RegisterColumn(t("col_title"), weight=2.5, wrap=True, xlsx_width=40),
            RegisterColumn(t("col_type")),
            RegisterColumn(t("col_status")),
            RegisterColumn(t("col_currency"), kind="currency"),
            RegisterColumn(t("col_planned"), kind="money"),
            RegisterColumn(t("col_released"), kind="money"),
            RegisterColumn(t("col_committed"), kind="money"),
            RegisterColumn(t("col_tier")),
            RegisterColumn(t("col_decision_date"), kind="date"),
            RegisterColumn(t("col_overdue")),
            RegisterColumn(t("col_open_preconditions"), kind="count"),
            RegisterColumn(t("col_residual_loss"), kind="money"),
        ],
        rows=rows,
        details=[(t("project"), project_name), (t("as_of"), as_of)],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t("title"),
    )


def render(views: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str, fmt: str) -> bytes:
    """PDF or XLSX bytes of the matrix."""
    doc = matrix_document(views, project_name=project_name, locale=locale, as_of=as_of)
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
