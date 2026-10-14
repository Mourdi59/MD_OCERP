# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable engineering brief registers (PDF and XLSX).

Four project documents on :mod:`app.core.register_export`: the requirements brief, the technical concept,
the area and quantity programme and the framework schedule. The labels of catalogue entries come from the
pinned catalogue in the language of the document.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.engineering_brief.catalogue import label_of
from app.modules.engineering_brief.messages import translate

KINDS = ("requirements", "concept", "programme", "schedule")


def _t(key: str, locale: str) -> str:
    return translate(f"engineering_brief.export.{key}", locale=locale)


def _label(catalogue: Any, finder: str, code: str, locale: str) -> str:
    """The catalogue's own text for ``code``; a tenant entry prints its label, a shipped one its translation."""
    return label_of(getattr(catalogue, finder)(code), locale, code)


def requirements_document(
    rows: list[dict[str, Any]], *, catalogue: Any, project_name: str, locale: str
) -> RegisterDocument:
    body = [
        [
            _label(catalogue, "category", r["category"], locale),
            f"{r['entity']} / {r['attribute']}",
            " ".join(
                x
                for x in (
                    translate(f"engineering_brief.constraint.{r['constraint_type']}", locale=locale),
                    r["constraint_value"],
                    r["unit"],
                )
                if x
            ),
            translate(f"engineering_brief.priority.{r['priority']}", locale=locale),
            translate(f"engineering_brief.verification.{r['verification_method']}", locale=locale)
            if r["verification_method"]
            else "",
            r["originator"] or r["source_ref"],
            ", ".join(r.get("answered_by") or []),
        ]
        for r in rows
    ]
    columns = [
        RegisterColumn(_t("col_category", locale), wrap=True),
        RegisterColumn(_t("col_requirement", locale), weight=2, wrap=True, xlsx_width=34),
        RegisterColumn(_t("col_constraint", locale), wrap=True, xlsx_width=22),
        RegisterColumn(_t("col_priority", locale)),
        RegisterColumn(_t("col_verification", locale), wrap=True),
        RegisterColumn(_t("col_origin", locale), wrap=True, xlsx_width=24),
        RegisterColumn(_t("col_answered_by", locale), nobreak=True),
    ]
    return _doc(_t("requirements_title", locale), columns, body, [(_t("project", locale), project_name)], locale)


def concept_document(rows: list[dict[str, Any]], *, catalogue: Any, project_name: str, locale: str) -> RegisterDocument:
    body = [
        [
            c["code"],
            _label(catalogue, "topic", c["topic_code"], locale),
            c["title"],
            c["decision"],
            translate(f"engineering_brief.concept_status.{c['status']}", locale=locale),
        ]
        for c in rows
    ]
    columns = [
        RegisterColumn(_t("col_code", locale), nobreak=True),
        RegisterColumn(_t("col_topic", locale), wrap=True),
        RegisterColumn(_t("col_title", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_decision", locale), weight=3, wrap=True, xlsx_width=50),
        RegisterColumn(_t("col_status", locale)),
    ]
    return _doc(_t("concept_title", locale), columns, body, [(_t("project", locale), project_name)], locale)


def programme_document(
    rows: list[dict[str, Any]], *, catalogue: Any, project_name: str, locale: str
) -> RegisterDocument:
    body = [
        [
            p["code"],
            _label(catalogue, "programme_kind", p["kind_code"], locale),
            p["label"],
            format(Decimal(str(p["quantity"])).normalize(), "f"),
            p["unit"],
            p["basis"],
        ]
        for p in rows
    ]
    columns = [
        RegisterColumn(_t("col_code", locale), nobreak=True),
        RegisterColumn(_t("col_kind", locale), wrap=True),
        RegisterColumn(_t("col_title", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_quantity", locale), nobreak=True),
        RegisterColumn(_t("col_unit", locale), nobreak=True),
        RegisterColumn(_t("col_basis", locale), weight=2, wrap=True, xlsx_width=40),
    ]
    return _doc(_t("programme_title", locale), columns, body, [(_t("project", locale), project_name)], locale)


def schedule_document(
    rows: list[dict[str, Any]], *, catalogue: Any, project_name: str, locale: str
) -> RegisterDocument:
    by_id = {m["id"]: m for m in rows}
    body = [
        [
            m["code"],
            m["name"],
            _label(catalogue, "milestone_kind", m["kind_code"], locale),
            m["planned_date"] or "",
            m["lead_days"],
            by_id[m["successor_id"]]["code"] if m["successor_id"] in by_id else "",
            m["gate_code"] or "",
        ]
        for m in rows
    ]
    columns = [
        RegisterColumn(_t("col_code", locale), nobreak=True),
        RegisterColumn(_t("col_title", locale), weight=2, wrap=True, xlsx_width=34),
        RegisterColumn(_t("col_kind", locale), wrap=True),
        RegisterColumn(_t("col_date", locale), kind="date"),
        RegisterColumn(_t("col_lead_days", locale), kind="count"),
        RegisterColumn(_t("col_successor", locale), nobreak=True),
        RegisterColumn(_t("col_gate", locale), wrap=True),
    ]
    return _doc(_t("schedule_title", locale), columns, body, [(_t("project", locale), project_name)], locale)


def _doc(
    title: str, columns: list[RegisterColumn], rows: list[list[Any]], details: list[tuple[str, Any]], locale: str
) -> RegisterDocument:
    return RegisterDocument(
        title=title,
        columns=columns,
        rows=rows,
        details=details,
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=_t("empty", locale),
        sheet_title=title[:31],
    )


def render(doc: RegisterDocument, fmt: str) -> bytes:
    """PDF or XLSX bytes of one register."""
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
