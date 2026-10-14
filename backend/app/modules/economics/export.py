# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable economics (PDF and XLSX): the cost frame, the business case and the financing plan.

Three project documents on :mod:`app.core.register_export`. They print the views the screens read, so
a figure on paper is the figure on screen. Amounts are parsed from the views' decimal strings, never
from floats; a key figure that cannot be computed prints as words and is never zero.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.economics.messages import translate

KINDS = ("frame", "case", "financing")
ZERO = Decimal("0")


def _t(key: str, locale: str) -> str:
    return translate(f"economics.export.{key}", locale=locale)


def _d(value: Any) -> Decimal:
    return Decimal(str(value)) if value not in (None, "") else ZERO


def _doc(
    title: str,
    columns: list[RegisterColumn],
    rows: list[list[Any]],
    details: list[tuple[str, Any]],
    locale: str,
    currency: str,
    *,
    totals: bool = False,
) -> RegisterDocument:
    return RegisterDocument(
        title=title,
        columns=columns,
        rows=rows,
        details=[(k, str(v)) for k, v in details],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=_t("empty", locale),
        sheet_title=title[:31],
        currency=currency,
        totals_label=_t("total", locale) if totals else "",
    )


def frame_document(view: dict[str, Any], *, project_name: str, locale: str) -> RegisterDocument:
    totals = view["totals"]
    rows: list[list[Any]] = [
        [
            r["code"],
            r["title"],
            _d(r["amount"]),
            _d(r["estimate"]),
            None if r["committed"] is None else _d(r["committed"]),
        ]
        for r in view["lines"]
    ]
    if rows:
        rows.append(["", _t("allowance", locale), _d(totals["markup_allowance"]), _d(totals["markups"]), None])
        if _d(totals["estimate_unassigned"]) != 0:
            rows.append(["", _t("unassigned", locale), ZERO, _d(totals["estimate_unassigned"]), None])
    columns = [
        RegisterColumn(_t("col_code", locale), nobreak=True),
        RegisterColumn(_t("col_group", locale), weight=3, wrap=True, xlsx_width=40),
        RegisterColumn(_t("col_budget", locale), kind="money", total=True),
        RegisterColumn(_t("col_estimate", locale), kind="money", total=True),
        RegisterColumn(_t("col_committed", locale), kind="money"),
    ]
    details = [
        (_t("project", locale), project_name),
        (_t("currency", locale), view["currency"]),
    ]
    return _doc(_t("frame_title", locale), columns, rows, details, locale, view["currency"], totals=True)


def _figure(value: Any, locale: str) -> str:
    return _t("unknown", locale) if value is None else format(Decimal(str(value)), "f")


def case_document(view: dict[str, Any], *, project_name: str, locale: str) -> RegisterDocument:
    k = view["key_figures"]
    rows = [
        [
            _t(f"flow_{line['kind']}", locale),
            line["label"],
            _d(line["amount"]),
            f"{line['year_from']} - {line['year_to']}",
            format(_d(line["escalation_pct"]).normalize(), "f"),
        ]
        for line in view["lines"]
    ]
    columns = [
        RegisterColumn(_t("col_kind", locale), wrap=True),
        RegisterColumn(_t("col_line", locale), weight=3, wrap=True, xlsx_width=40),
        RegisterColumn(_t("col_amount", locale), kind="money"),
        RegisterColumn(_t("col_years", locale), nobreak=True),
        RegisterColumn(_t("col_escalation", locale), nobreak=True),
    ]
    details = [
        (_t("project", locale), project_name),
        (_t("currency", locale), view["currency"]),
        (_t("discount_rate", locale), _figure(view["discount_rate_pct"], locale)),
        (_t("horizon", locale), view["horizon_years"]),
        (_t("total_investment", locale), _figure(k["total_investment"], locale)),
        (_t("npv", locale), _figure(k["npv"], locale)),
        (_t("irr", locale), _figure(k["irr_pct"], locale)),
        (_t("payback", locale), _figure(k["payback_year"], locale)),
        (_t("bcr", locale), _figure(k["benefit_cost_ratio"], locale)),
        (_t("yield", locale), _figure(k["yield_on_cost_pct"], locale)),
    ]
    return _doc(_t("case_title", locale), columns, rows, details, locale, view["currency"])


def financing_document(view: dict[str, Any], *, project_name: str, locale: str) -> RegisterDocument:
    cov = view["coverage"]
    rows = [
        [
            source["name"],
            _t(f"source_{source['kind']}", locale),
            tranche["due_on"],
            _d(tranche["amount"]),
            _t(f"tranche_{tranche['status']}", locale),
            tranche["condition"],
        ]
        for source in view["sources"]
        for tranche in source["tranches"]
    ]
    columns = [
        RegisterColumn(_t("col_source", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_kind", locale), wrap=True),
        RegisterColumn(_t("col_due", locale), kind="date"),
        RegisterColumn(_t("col_amount", locale), kind="money", total=True),
        RegisterColumn(_t("col_status", locale)),
        RegisterColumn(_t("col_condition", locale), weight=2, wrap=True, xlsx_width=30),
    ]
    details = [
        (_t("project", locale), project_name),
        (_t("currency", locale), view["currency"]),
        (_t("requirement", locale), _figure(view["requirement"], locale)),
        (_t("sources_total", locale), _figure(cov["sources_total"], locale)),
        (_t("shortfall", locale), _figure(cov["shortfall"], locale)),
        (_t("surplus", locale), _figure(cov["surplus"], locale)),
    ]
    return _doc(_t("financing_title", locale), columns, rows, details, locale, view["currency"], totals=True)


def render(doc: RegisterDocument, fmt: str) -> bytes:
    """PDF or XLSX bytes of one document."""
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
