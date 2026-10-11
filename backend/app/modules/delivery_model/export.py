# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers of the delivery model (PDF and XLSX), SPEC rule 17.

Three documents on :mod:`app.core.register_export`: the decision record
(comparison with weighted totals and the decision), the risk allocation matrix
and the package plan. Every label comes from this module's message bundle.
The decision record is what a user files as a revision of the governance frame
document of the contracts area; governance binds that revision at the gate.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.delivery_model.messages import translate

KINDS = ("decision", "matrix", "packages")


def _t(key: str, locale: str) -> str:
    return translate(f"delivery_model.export.{key}", locale=locale)


def _label(key: str | None, locale: str, fallback: str = "") -> str:
    return translate(key, locale=locale) if key else fallback


def decision_document(
    cmp: dict[str, Any], decision: dict[str, Any] | None, *, project_name: str, locale: str
) -> RegisterDocument:
    options = cmp["options"]
    columns = [
        RegisterColumn(_t("col_criterion", locale), weight=2, wrap=True, xlsx_width=32),
        RegisterColumn(_t("col_weight", locale), kind="count"),
    ]
    for o in options:
        columns.append(RegisterColumn(_label((o.get("form") or {}).get("name_key"), locale, o["form_code"]), wrap=True))
    scores = {(s["option_id"], s["criterion_code"]): s["score"] for s in cmp["scores"]}
    rows: list[list[Any]] = []
    for c in cmp["criteria"]:
        rows.append(
            [
                _label(c.get("name_key"), locale, c["code"]),
                c["weight"],
                *[scores.get((o["id"], c["code"]), "") for o in options],
            ]
        )
    rows.append([_t("weighted_total", locale), cmp["weights_total"], *[o["weighted_total"] or "" for o in options]])
    details = [(_t("project", locale), project_name)]
    if decision:
        details += [
            (
                _t("chosen_form", locale),
                _label((decision.get("snapshot", {}).get("form") or {}).get("name_key"), locale, decision["form_code"]),
            ),
            (_t("status", locale), translate(f"delivery_model.decision_status.{decision['status']}", locale=locale)),
            (_t("rationale", locale), decision["rationale"]),
            (_t("proposed_at", locale), decision.get("proposed_at") or ""),
            (_t("approved_at", locale), decision.get("approved_at") or ""),
        ]
    return _doc(_t("decision_title", locale), columns, rows, details, locale)


def matrix_document(matrix: dict[str, Any], *, project_name: str, locale: str) -> RegisterDocument:
    parties = {p["code"]: p["name_key"] for p in matrix["parties"]}
    rows = []
    for item in matrix["items"]:
        a = item.get("allocation") or {}
        d = item.get("default") or {}
        party = a.get("party") or ""
        shares = ", ".join(f"{_label(parties.get(k), locale, k)} {v}%" for k, v in (a.get("shares") or {}).items())
        rows.append(
            [
                _label(item["name_key"], locale, item["category_code"]),
                item["register_category"],
                _t("not_applicable", locale) if a.get("not_applicable") else _label(parties.get(party), locale, party),
                shares,
                a.get("basis") or "",
                a.get("rationale") or "",
                _label(parties.get(d.get("party")), locale, d.get("party") or ""),
                translate(f"delivery_model.allocation_status.{a['status']}", locale=locale)
                if a
                else _t("default_only", locale),
                len(a.get("risk_item_ids") or []),
            ]
        )
    columns = [
        RegisterColumn(_t("col_category", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_register_category", locale)),
        RegisterColumn(_t("col_party", locale)),
        RegisterColumn(_t("col_shares", locale), wrap=True),
        RegisterColumn(_t("col_basis", locale)),
        RegisterColumn(_t("col_rationale", locale), weight=2.5, wrap=True, xlsx_width=40),
        RegisterColumn(_t("col_default", locale)),
        RegisterColumn(_t("col_status", locale)),
        RegisterColumn(_t("col_risks", locale), kind="count"),
    ]
    return _doc(_t("matrix_title", locale), columns, rows, [(_t("project", locale), project_name)], locale)


def packages_document(packages: list[dict[str, Any]], *, project_name: str, locale: str) -> RegisterDocument:
    def flags(p: dict[str, Any]) -> str:
        return "".join(
            letter for letter, key in (("D", "designs"), ("B", "builds"), ("S", "supplies"), ("M", "manages")) if p[key]
        )

    rows = [
        [
            p["code"],
            p["title"],
            translate(f"delivery_model.package_kind.{p['kind']}", locale=locale),
            flags(p),
            p["price_basis"] or "",
            p["standard_form"],
            translate(f"delivery_model.package_status.{p['effective_status']}", locale=locale),
            p["need_date"] or "",
        ]
        for p in packages
    ]
    columns = [
        RegisterColumn(_t("col_code", locale), nobreak=True),
        RegisterColumn(_t("col_title", locale), weight=2.5, wrap=True, xlsx_width=40),
        RegisterColumn(_t("col_kind", locale)),
        RegisterColumn(_t("col_flags", locale)),
        RegisterColumn(_t("col_price_basis", locale)),
        RegisterColumn(_t("col_standard_form", locale)),
        RegisterColumn(_t("col_status", locale)),
        RegisterColumn(_t("col_need_date", locale), kind="date"),
    ]
    return _doc(_t("packages_title", locale), columns, rows, [(_t("project", locale), project_name)], locale)


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
