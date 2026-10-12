# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers (PDF and XLSX) of the plant register, on :mod:`app.core.register_export`.

Five documents: the long-lead register, the delivery-limit matrix, the spares
list, one decision paper and the frame summary. Every label comes from this
module's message bundle, so the sheet is in the reader's language wherever a
locale file exists and English otherwise.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.plant_register.messages import translate

KINDS = ("register", "limits", "spares", "paper", "frame")


def _d(value: Any) -> str:
    return value.isoformat() if isinstance(value, date) else ("" if value is None else str(value))


def _doc(
    kind: str, columns: list[RegisterColumn], rows: list[list[Any]], *, project_name: str, locale: str
) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"plant.export.{key}", locale=locale)

    return RegisterDocument(
        title=t(f"{kind}_title"),
        columns=columns,
        rows=rows,
        details=[(t("project"), project_name)],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t(f"{kind}_title"),
    )


def register_document(views: Sequence[dict[str, Any]], *, project_name: str, locale: str) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"plant.export.{key}", locale=locale)

    rows = [
        [
            v["code"],
            v["item"].title,
            translate(f"plant.catalogue.class.{v['item'].component_class_code}", locale=locale),
            t("yes") if v["critical"] else "",
            v["effective_lead_weeks"],
            translate(f"plant.catalogue.source.{v['lead_source']}", locale=locale),
            _d(v["basis_enquiry_date"]),
            _d(v["need_date"]),
            _d(v["latest_order_date"]),
            v["float_days"],
            translate(f"plant.catalogue.route.{v['item'].procurement_route}", locale=locale)
            if v["item"].procurement_route
            else "",
            translate(f"plant.state.{v['item'].status}", locale=locale),
        ]
        for v in views
    ]
    cols = [
        RegisterColumn(t("col_code"), nobreak=True),
        RegisterColumn(t("col_title"), weight=2.0, wrap=True, xlsx_width=36),
        RegisterColumn(t("col_class")),
        RegisterColumn(t("col_critical")),
        RegisterColumn(t("col_lead_weeks"), kind="count"),
        RegisterColumn(t("col_lead_source")),
        RegisterColumn(t("col_enquiry_date"), kind="date"),
        RegisterColumn(t("col_need_date"), kind="date"),
        RegisterColumn(t("col_latest_order"), kind="date"),
        RegisterColumn(t("col_float"), kind="count"),
        RegisterColumn(t("col_route")),
        RegisterColumn(t("col_state")),
    ]
    return _doc("register", cols, rows, project_name=project_name, locale=locale)


def limits_document(
    views: Sequence[dict[str, Any]],
    limits: dict[Any, dict[str, str]],
    steps: Sequence[str],
    *,
    project_name: str,
    locale: str,
) -> RegisterDocument:
    cols = [RegisterColumn(translate("plant.export.col_code", locale=locale), nobreak=True)] + [
        RegisterColumn(translate(f"plant.catalogue.step.{s}", locale=locale)) for s in steps
    ]
    rows = [[v["code"], *[_party(limits.get(v["id"], {}).get(s, ""), locale) for s in steps]] for v in views]
    return _doc("limits", cols, rows, project_name=project_name, locale=locale)


def _party(value: str, locale: str) -> str:
    if not value:
        return ""
    key = f"plant.catalogue.party.{value}"
    text = translate(key, locale=locale)
    return value if text == key else text


def spares_document(rows_in: Sequence[dict[str, Any]], *, project_name: str, locale: str) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"plant.export.{key}", locale=locale)

    rows = [
        [
            r["item_code"],
            translate(f"plant.catalogue.spare.{r['category']}", locale=locale),
            r["description"],
            r["quantity"],
            r["unit"],
            _party(r["supply_by"], locale),
            translate(f"plant.spare_state.{r['status']}", locale=locale),
        ]
        for r in rows_in
    ]
    cols = [
        RegisterColumn(t("col_code"), nobreak=True),
        RegisterColumn(t("col_category")),
        RegisterColumn(t("col_description"), weight=2.0, wrap=True, xlsx_width=40),
        RegisterColumn(t("col_quantity"), kind="count"),
        RegisterColumn(t("col_unit")),
        RegisterColumn(t("col_supply_by")),
        RegisterColumn(t("col_state")),
    ]
    return _doc("spares", cols, rows, project_name=project_name, locale=locale)


def paper_document(
    paper: Any, scores: dict[str, Any], item_code: str, *, project_name: str, locale: str
) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"plant.export.{key}", locale=locale)

    rows = [
        [
            o.get("code", ""),
            o.get("title", ""),
            o.get("lead_weeks", ""),
            o.get("cost", ""),
            str(scores.get(str(o.get("code")), "")),
            t("yes") if o.get("code") == paper.recommendation else "",
        ]
        for o in paper.options
    ]
    cols = [
        RegisterColumn(t("col_option"), nobreak=True),
        RegisterColumn(t("col_title"), weight=2.0, wrap=True, xlsx_width=36),
        RegisterColumn(t("col_lead_weeks")),
        RegisterColumn(t("col_cost")),
        RegisterColumn(t("col_score")),
        RegisterColumn(t("col_recommended")),
    ]
    doc = _doc("paper", cols, rows, project_name=project_name, locale=locale)
    doc.details.extend(
        [
            (t("col_code"), item_code),
            (t("question"), paper.question),
            (t("rationale"), paper.rationale),
            (t("col_state"), translate(f"plant.paper_state.{paper.status}", locale=locale)),
        ]
    )
    return doc


def frame_document(summary: dict[str, Any], *, project_name: str, locale: str) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"plant.export.{key}", locale=locale)

    rows: list[list[Any]] = [
        [t("section_long_lead"), r["code"], r["title"], _d(r["latest_order_date"]), r["float_days"]]
        for r in summary["long_lead"]
    ]
    rows += [
        [
            t("section_site_plant"),
            translate(f"plant.catalogue.site_plant.{p['kind']}", locale=locale),
            p["name"],
            _d(p["from_date"]),
            _d(p["to_date"]),
        ]
        for p in summary["site_plant"]
    ]
    rows += [
        [
            t("section_it"),
            translate(f"plant.catalogue.it_service.{s['kind']}", locale=locale),
            _party(s["responsible_party"], locale),
            "",
            "",
        ]
        for s in summary["it_services"]
    ]
    cols = [
        RegisterColumn(t("col_section")),
        RegisterColumn(t("col_code")),
        RegisterColumn(t("col_title"), weight=2.0, wrap=True, xlsx_width=36),
        RegisterColumn(t("col_from"), kind="date"),
        RegisterColumn(t("col_to")),
    ]
    doc = _doc("frame", cols, rows, project_name=project_name, locale=locale)
    doc.details.extend(
        [
            (t("item_count"), str(summary["item_count"])),
            (t("critical_count"), str(summary["critical_count"])),
            (t("long_lead_count"), str(summary["long_lead_count"])),
            (t("overdue_count"), str(summary["overdue_count"])),
            (t("catalogue"), summary["catalogue"]),
        ]
    )
    return doc


def render(doc: RegisterDocument, fmt: str) -> bytes:
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
