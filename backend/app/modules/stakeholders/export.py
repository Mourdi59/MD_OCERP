# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The two frame documents of the module as printable registers (PDF and XLSX, rule 21).

* "Stakeholder and communication plan": three tables, one each for the
  stakeholders (names masked for a reader without
  ``stakeholders.read_personal``, rule 17), the communication plan and the
  commitments.
* "Project organisation and mandates": three tables, one each for the role
  holders, the governance bodies and the mandate matrix.

Every table has its own columns and a column means one thing in every row.
The workbook carries one sheet per table; the PDF is the tables one after
another, each starting on its own page under its own title.

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle (catalogue items through their ``name_key``).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from copy import copy
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.stakeholders.catalogue import StakeholderFramework
from app.modules.stakeholders.messages import DEFAULT_LOCALE, available_locales, translate


def written_locale(requested: str | None) -> str:
    """The language an export is actually written in for a requested locale.

    The message bundle answers a locale it does not ship in English, so that
    is what the response has to declare, not what the reader asked for.
    """
    return requested if requested and requested in available_locales() else DEFAULT_LOCALE


def _label(fw: StakeholderFramework, items: Sequence[Any], code: str | None, locale: str) -> str:
    if not code:
        return ""
    item = next((i for i in items if i.code == code), None)
    if item is None:
        return code
    if item.labels:
        return item.labels.get(locale) or item.labels.get("en") or code
    return translate(item.name_key, locale=locale) if item.name_key else code


def _classes(fw: StakeholderFramework) -> list[Any]:
    return [c for m in fw.analysis_methods for c in m.classes]


def _document(
    fw: StakeholderFramework,
    title: str,
    sheet: str,
    columns: list[RegisterColumn],
    rows: list[list[Any]],
    *,
    project_name: str,
    locale: str,
) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"stakeholders.export.{key}", locale=locale)

    return RegisterDocument(
        title=f"{title}: {sheet}",
        columns=columns,
        rows=rows,
        details=[(t("project"), project_name), (t("framework"), f"{fw.id} v{fw.version}")],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=sheet,
    )


def register_documents(
    fw: StakeholderFramework,
    *,
    stakeholders: Sequence[dict[str, Any]],
    plan_items: Sequence[dict[str, Any]],
    commitments: Sequence[dict[str, Any]],
    project_name: str,
    locale: str,
) -> list[RegisterDocument]:
    """Stakeholders, communication plan and commitments, one table each."""

    def t(key: str) -> str:
        return translate(f"stakeholders.export.{key}", locale=locale)

    names = {s["id"]: s for s in stakeholders}

    def who(s: dict[str, Any]) -> str:
        if s.get("anonymised"):
            return t("anonymised")
        if s.get("masked"):
            return t("masked")
        return s.get("name") or ""

    def audience(ids: Sequence[str]) -> str:
        return ", ".join(n for n in (who(names[i]) for i in ids if i in names) if n)

    stakeholder_rows: list[list[Any]] = []
    for s in stakeholders:
        if s.get("status") == "archived":
            continue
        cls = s.get("classification")
        stakeholder_rows.append(
            [
                s["code"],
                who(s),
                _label(fw, fw.stakeholder_categories, s.get("category"), locale),
                t("not_assessed") if cls == "not_assessed" else _label(fw, _classes(fw), cls, locale),
                " / ".join(
                    _label(fw, fw.engagement_levels, s.get(k), locale)
                    for k in ("engagement_current", "engagement_desired")
                ).strip(" /"),
                t("yes") if s.get("review_due") else "",
                s.get("open_commitments", 0),
            ]
        )
    plan_rows: list[list[Any]] = []
    for p in plan_items:
        groups = [_label(fw, fw.stakeholder_categories, c, locale) for c in p.get("audience_categories", [])]
        plan_rows.append(
            [
                p.get("title", ""),
                ", ".join(a for a in [audience(p.get("audience_stakeholder_ids", [])), *groups] if a),
                " / ".join(x for x in (p.get("purpose") or "", p.get("key_message") or "") if x),
                _label(fw, fw.participation_levels, p.get("participation_level"), locale),
                _label(fw, fw.channels, p.get("channel"), locale),
                p.get("frequency") or p.get("trigger_kind") or "",
                p.get("next_due") or "",
                translate(f"stakeholders.plan_status.{p.get('status')}", locale=locale),
            ]
        )
    commitment_rows: list[list[Any]] = []
    for c in commitments:
        commitment_rows.append(
            [
                c["code"],
                c.get("text", ""),
                audience(c.get("stakeholder_ids", [])),
                translate(f"stakeholders.commitment_category.{c.get('category')}", locale=locale),
                c.get("source_snapshot", {}).get("title") or "",
                c.get("due_date") or "",
                translate(f"stakeholders.commitment_status.{c.get('status')}", locale=locale),
            ]
        )
    title = t("register_title")
    common = {"project_name": project_name, "locale": locale}
    return [
        _document(
            fw,
            title,
            t("sheet_stakeholders"),
            [
                RegisterColumn(t("col_code"), nobreak=True),
                RegisterColumn(t("col_name"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_category"), weight=1.5, wrap=True, xlsx_width=24),
                RegisterColumn(t("col_classification"), wrap=True),
                RegisterColumn(t("col_engagement"), wrap=True, xlsx_width=24),
                RegisterColumn(t("col_review_due")),
                RegisterColumn(t("col_open_commitments"), kind="count"),
            ],
            stakeholder_rows,
            **common,
        ),
        _document(
            fw,
            title,
            t("sheet_plan"),
            [
                RegisterColumn(t("col_title"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_audience"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_purpose"), weight=2.5, wrap=True, xlsx_width=40),
                RegisterColumn(t("col_level"), wrap=True),
                RegisterColumn(t("col_channel"), wrap=True),
                RegisterColumn(t("col_frequency"), wrap=True),
                RegisterColumn(t("col_next_due"), nobreak=True),
                RegisterColumn(t("col_status")),
            ],
            plan_rows,
            **common,
        ),
        _document(
            fw,
            title,
            t("sheet_commitments"),
            [
                RegisterColumn(t("col_code"), nobreak=True),
                RegisterColumn(t("col_text"), weight=3.0, wrap=True, xlsx_width=48),
                RegisterColumn(t("col_audience"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_commitment_category"), wrap=True),
                RegisterColumn(t("col_source"), weight=1.5, wrap=True, xlsx_width=24),
                RegisterColumn(t("col_due"), nobreak=True),
                RegisterColumn(t("col_status")),
            ],
            commitment_rows,
            **common,
        ),
    ]


def organisation_documents(
    fw: StakeholderFramework,
    *,
    roles: dict[str, Any],
    bodies: Sequence[dict[str, Any]],
    matrix: dict[str, Any],
    project_name: str,
    locale: str,
) -> list[RegisterDocument]:
    """Role holders, governance bodies and the mandate matrix, one table each."""

    def t(key: str) -> str:
        return translate(f"stakeholders.export.{key}", locale=locale)

    def role_name(code: str) -> str:
        return _label(fw, fw.roles, code, locale)

    role_rows: list[list[Any]] = []
    held = {h["role_code"] for h in roles.get("holders", [])}
    for h in roles.get("holders", []):
        role_rows.append(
            [
                role_name(h["role_code"]) or h.get("custom_label") or "",
                h.get("holder_name") or "",
                h.get("valid_from") or "",
                h.get("valid_to") or "",
            ]
        )
    for code in roles.get("vacant", []):
        if code not in held:
            role_rows.append([role_name(code), t("vacant"), "", ""])
    body_rows: list[list[Any]] = []
    for b in bodies:
        members = ", ".join(
            role_name(m["role_code"]) if m.get("role_code") else t("member_person")
            for m in b.get("members", [])
            if m.get("valid_today")
        )
        body_rows.append([b["name"], members, b["quorum_needed"], b["quorum_present"]])
    body_names = {b["code"]: b["name"] for b in bodies}
    mandate_rows: list[list[Any]] = []
    for r in matrix.get("rows", []):
        holder = (
            role_name(r["holder_code"])
            if r["holder_kind"] == "role"
            else body_names.get(r["holder_code"], r["holder_code"])
        )
        mandate_rows.append(
            [
                _label(fw, fw.decision_types, r["decision_type"], locale),
                holder,
                r["letter"],
                r.get("scope") or "",
                r.get("scope_note") or "",
            ]
        )
    title = t("organisation_title")
    common = {"project_name": project_name, "locale": locale}
    return [
        _document(
            fw,
            title,
            t("sheet_roles"),
            [
                RegisterColumn(t("col_role_name"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_holder_name"), weight=2.5, wrap=True, xlsx_width=40),
                RegisterColumn(t("col_valid_from"), nobreak=True),
                RegisterColumn(t("col_valid_to"), nobreak=True),
            ],
            role_rows,
            **common,
        ),
        _document(
            fw,
            title,
            t("sheet_bodies"),
            [
                RegisterColumn(t("col_body"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_members"), weight=3.0, wrap=True, xlsx_width=48),
                RegisterColumn(t("col_quorum_needed"), kind="count"),
                RegisterColumn(t("col_quorum_present"), kind="count"),
            ],
            body_rows,
            **common,
        ),
        _document(
            fw,
            title,
            t("sheet_mandates"),
            [
                RegisterColumn(t("col_decision_type"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_role"), weight=2.0, wrap=True, xlsx_width=30),
                RegisterColumn(t("col_letter"), nobreak=True),
                RegisterColumn(t("col_scope"), wrap=True),
                RegisterColumn(t("col_note"), weight=2.0, wrap=True, xlsx_width=40),
            ],
            mandate_rows,
            **common,
        ),
    ]


def _merge_workbooks(buffers: Sequence[io.BytesIO], titles: Sequence[str]) -> bytes:
    """One workbook with one sheet per table, each sheet as the register builder laid it out."""
    from openpyxl import Workbook, load_workbook

    out = Workbook()
    out.remove(out.active)
    for buf, title in zip(buffers, titles, strict=True):
        src = load_workbook(buf).active
        dst = out.create_sheet(title=title[:31] or None)
        for row in src.iter_rows():
            for cell in row:
                new = dst.cell(row=cell.row, column=cell.column, value=cell.value)
                if cell.has_style:
                    new.font = copy(cell.font)
                    new.fill = copy(cell.fill)
                    new.border = copy(cell.border)
                    new.alignment = copy(cell.alignment)
                    new.number_format = cell.number_format
        for key, dim in src.column_dimensions.items():
            dst.column_dimensions[key].width = dim.width
        for key, dim in src.row_dimensions.items():
            dst.row_dimensions[key].height = dim.height
        for merged in src.merged_cells.ranges:
            dst.merge_cells(str(merged))
        dst.freeze_panes = src.freeze_panes
        dst.page_setup.orientation = src.page_setup.orientation
        dst.page_setup.fitToWidth = src.page_setup.fitToWidth
        dst.page_setup.fitToHeight = src.page_setup.fitToHeight
        dst.sheet_properties.pageSetUpPr = copy(src.sheet_properties.pageSetUpPr)
        dst.print_title_rows = src.print_title_rows
    done = io.BytesIO()
    out.save(done)
    return done.getvalue()


def _merge_pdfs(parts: Sequence[bytes]) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for part in parts:
        writer.append(io.BytesIO(part))
    done = io.BytesIO()
    writer.write(done)
    return done.getvalue()


def render(docs: Sequence[RegisterDocument], fmt: str) -> bytes:
    """PDF or XLSX bytes of the tables of one frame document."""
    if fmt == "xlsx":
        return _merge_workbooks([build_register_xlsx(d) for d in docs], [d.sheet_title for d in docs])
    return _merge_pdfs([build_register_pdf(d) for d in docs])
