# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable staffing registers (PDF and XLSX), SPEC rule 20.

Three project documents on :mod:`app.core.register_export`: the staffing plan
(names, roles, FTE, dates and status only), the organisation chart, and the
compliance matrix (role x document kind, status only, no number, no date of a
health check). Personnel files are not exportable in bulk; one person's own
file is exportable to that person (GDPR Art. 15 and 20) via ``own_file_document``.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.staffing.catalogue import label_of
from app.modules.staffing.messages import translate

KINDS = ("plan", "org_chart", "compliance")


def _t(key: str, locale: str) -> str:
    return translate(f"staffing.export.{key}", locale=locale)


def _label(catalogue: Any, group: str, code: str, locale: str) -> str:
    """The catalogue's own text for ``code``; a tenant entry prints its label, a shipped one its translation."""
    entry = next((e for e in getattr(catalogue, group, ()) if e.code == code), None)
    return label_of(entry, locale, code)


def _role(catalogue: Any, code: str, custom: str, locale: str) -> str:
    return custom if code == "custom" else _label(catalogue, "roles", code, locale)


def plan_document(
    positions: list[dict[str, Any]], *, catalogue: Any, project_name: str, locale: str
) -> RegisterDocument:
    rows = [
        [
            _role(catalogue, p["role_code"], p["custom_label"], locale),
            _label(catalogue, "organisations", p["organisation"], locale),
            translate(f"staffing.phase.{p['phase']}", locale=locale),
            p["fte"],
            p["headcount"],
            p["entry_date"] or "",
            p["exit_date"] or "",
            translate(f"staffing.position_status.{p['status']}", locale=locale),
            ", ".join(f["name"] or "" for f in p["fills"] if f["status"] != "ended"),
        ]
        for p in positions
    ]
    columns = [
        RegisterColumn(_t("col_role", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_organisation", locale), wrap=True),
        RegisterColumn(_t("col_phase", locale)),
        RegisterColumn(_t("col_fte", locale)),
        RegisterColumn(_t("col_headcount", locale), kind="count"),
        RegisterColumn(_t("col_entry", locale), kind="date"),
        RegisterColumn(_t("col_exit", locale), kind="date"),
        RegisterColumn(_t("col_status", locale)),
        RegisterColumn(_t("col_people", locale), weight=2, wrap=True, xlsx_width=36),
    ]
    return _doc(_t("plan_title", locale), columns, rows, [(_t("project", locale), project_name)], locale)


def org_chart_document(chart: dict[str, Any], *, catalogue: Any, project_name: str, locale: str) -> RegisterDocument:
    rows = []
    for ph in chart["phases"]:
        for org in ph["organisations"]:
            for p in org["positions"]:
                rows.append(
                    [
                        translate(f"staffing.phase.{ph['phase']}", locale=locale),
                        _label(catalogue, "organisations", org["organisation"], locale),
                        _role(catalogue, p["role_code"], p["custom_label"], locale),
                        ", ".join(x["name"] or "" for x in p["people"]) or _t("vacant", locale),
                    ]
                )
    columns = [
        RegisterColumn(_t("col_phase", locale)),
        RegisterColumn(_t("col_organisation", locale), wrap=True),
        RegisterColumn(_t("col_role", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_people", locale), weight=2, wrap=True, xlsx_width=36),
    ]
    return _doc(_t("org_chart_title", locale), columns, rows, [(_t("project", locale), project_name)], locale)


def compliance_document(matrix: dict[str, Any], *, catalogue: Any, project_name: str, locale: str) -> RegisterDocument:
    kinds = matrix["document_kinds"]
    columns = [
        RegisterColumn(_t("col_person", locale), weight=2, wrap=True, xlsx_width=28),
        RegisterColumn(_t("col_cleared", locale)),
        *[RegisterColumn(_label(catalogue, "document_kinds", k, locale), wrap=True) for k in kinds],
    ]
    rows = [
        [
            r["name"] or "",
            _t("yes" if r["cleared_to_work"] else "no", locale),
            # A person whose file the reader may not open has no cells: the column stays empty.
            *[
                translate(f"staffing.cell.{r['cells'][k]['state'] if k in r['cells'] else 'restricted'}", locale=locale)
                for k in kinds
            ],
        ]
        for r in matrix["items"]
    ]
    return _doc(_t("compliance_title", locale), columns, rows, [(_t("project", locale), project_name)], locale)


def own_file_document(view: dict[str, Any], *, catalogue: Any, locale: str) -> RegisterDocument:
    """One person's own file, everything the platform holds about them (GDPR Art. 15).

    Header: employer, employment basis, legal basis of the processing, status and
    the date the data is kept until. Rows: documents with validity and, for the
    health certificate, the fitness flag; accommodation; travel; leave.
    """

    def status(group: str, value: str | None) -> str:
        return translate(f"staffing.{group}.{value}", locale=locale) if value else ""

    rows: list[list[Any]] = []
    for d in view["documents"]:
        item = _label(catalogue, "document_kinds", d["document_kind"], locale)
        if d.get("fit_for_role"):
            item = f"{item} ({_t('fit_for_role', locale)}: {status('fit', d['fit_for_role'])})"
        rows.append(
            [_t("section_document", locale), item, d.get("valid_until") or "", status("document_status", d["status"])]
        )
    for b in view.get("accommodation", []):
        rows.append(
            [
                _t("section_accommodation", locale),
                f"{b.get('accommodation') or ''} {b.get('room') or ''}".strip(),
                b.get("check_in") or "",
                status("record_status", b.get("status")),
            ]
        )
    for t in view["travel"]:
        rows.append(
            [
                _t("section_travel", locale),
                status("travel_kind", t["kind"]),
                t["depart_date"],
                status("record_status", t["status"]),
            ]
        )
    for lv in view["leave"]:
        rows.append(
            [
                _t("section_leave", locale),
                _label(catalogue, "leave_types", lv["leave_type"], locale),
                lv["from_date"],
                status("record_status", lv["status"]),
            ]
        )
    columns = [
        RegisterColumn(_t("col_section", locale)),
        RegisterColumn(_t("col_item", locale), weight=2, wrap=True, xlsx_width=30),
        RegisterColumn(_t("col_date", locale), kind="date"),
        RegisterColumn(_t("col_status", locale)),
    ]
    details = [
        (_t("col_person", locale), view["name"] or ""),
        (_t("col_status", locale), status("file_status", view["status"])),
        (_t("employer", locale), view.get("employer_organisation") or ""),
        (_t("employment_basis", locale), status("employment_basis", view.get("employment_basis"))),
        (_t("lawful_basis", locale), status("lawful_basis", view.get("lawful_basis"))),
        (_t("retention_due", locale), view.get("retention_due_at") or ""),
    ]
    return _doc(_t("own_file_title", locale), columns, rows, details, locale)


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
