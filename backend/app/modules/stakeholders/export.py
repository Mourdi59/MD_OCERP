# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The two frame documents of the module as printable registers (PDF and XLSX, rule 21).

* "Stakeholder and communication plan": stakeholders (names masked for a
  reader without ``stakeholders.read_personal``, rule 17), plan items and
  commitments, one row each with a kind column.
* "Project organisation and mandates": role holders, governance bodies with
  their members, and the mandate matrix.

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle (catalogue items through their ``name_key``).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.stakeholders.catalogue import StakeholderFramework
from app.modules.stakeholders.messages import translate


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


def register_document(
    fw: StakeholderFramework,
    *,
    stakeholders: Sequence[dict[str, Any]],
    plan_items: Sequence[dict[str, Any]],
    commitments: Sequence[dict[str, Any]],
    project_name: str,
    locale: str,
) -> RegisterDocument:
    """Stakeholders, plan items and commitments as one register."""

    def t(key: str) -> str:
        return translate(f"stakeholders.export.{key}", locale=locale)

    names = {s["id"]: s for s in stakeholders}

    def who(s: dict[str, Any]) -> str:
        if s.get("anonymised"):
            return t("anonymised")
        if s.get("masked"):
            return t("masked")
        return s.get("name") or ""

    rows: list[list[Any]] = []
    for s in stakeholders:
        if s.get("status") == "archived":
            continue
        cls = s.get("classification")
        rows.append(
            [
                t("kind_stakeholder"),
                s["code"],
                who(s),
                _label(fw, fw.stakeholder_categories, s.get("category"), locale),
                t("not_assessed") if cls == "not_assessed" else _label(fw, _classes(fw), cls, locale),
                " / ".join(
                    _label(fw, fw.engagement_levels, s.get(k), locale)
                    for k in ("engagement_current", "engagement_desired")
                ).strip(" /"),
                "",
                t("yes") if s.get("review_due") else "",
                s.get("open_commitments", 0),
            ]
        )
    for p in plan_items:
        audience = [who(names[i]) for i in p.get("audience_stakeholder_ids", []) if i in names]
        audience += [_label(fw, fw.stakeholder_categories, c, locale) for c in p.get("audience_categories", [])]
        rows.append(
            [
                t("kind_plan"),
                p.get("title", ""),
                ", ".join(a for a in audience if a),
                _label(fw, fw.participation_levels, p.get("participation_level"), locale),
                _label(fw, fw.channels, p.get("channel"), locale),
                p.get("frequency") or p.get("trigger_kind") or "",
                p.get("next_due") or "",
                translate(f"stakeholders.plan_status.{p.get('status')}", locale=locale),
                "",
            ]
        )
    for c in commitments:
        rows.append(
            [
                t("kind_commitment"),
                c["code"],
                ", ".join(who(names[i]) for i in c.get("stakeholder_ids", []) if i in names),
                c.get("text", ""),
                translate(f"stakeholders.commitment_category.{c.get('category')}", locale=locale),
                c.get("source_snapshot", {}).get("title") or "",
                c.get("due_date") or "",
                translate(f"stakeholders.commitment_status.{c.get('status')}", locale=locale),
                "",
            ]
        )
    return RegisterDocument(
        title=t("register_title"),
        columns=[
            RegisterColumn(t("col_kind"), nobreak=True),
            RegisterColumn(t("col_code"), nobreak=True),
            RegisterColumn(t("col_name"), weight=2.0, wrap=True, xlsx_width=30),
            RegisterColumn(t("col_category"), weight=2.0, wrap=True, xlsx_width=30),
            RegisterColumn(t("col_classification"), wrap=True),
            RegisterColumn(t("col_engagement"), wrap=True),
            RegisterColumn(t("col_next_due")),
            RegisterColumn(t("col_status")),
            RegisterColumn(t("col_open_commitments"), kind="count"),
        ],
        rows=rows,
        details=[(t("project"), project_name), (t("framework"), f"{fw.id} v{fw.version}")],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t("register_title"),
    )


def organisation_document(
    fw: StakeholderFramework,
    *,
    roles: dict[str, Any],
    bodies: Sequence[dict[str, Any]],
    matrix: dict[str, Any],
    project_name: str,
    locale: str,
) -> RegisterDocument:
    """Role holders, bodies and mandates as one register."""

    def t(key: str) -> str:
        return translate(f"stakeholders.export.{key}", locale=locale)

    def role_name(code: str) -> str:
        return _label(fw, fw.roles, code, locale)

    rows: list[list[Any]] = []
    held = {h["role_code"] for h in roles.get("holders", [])}
    for h in roles.get("holders", []):
        valid = f"{h.get('valid_from') or ''} - {h.get('valid_to') or ''}".strip(" -")
        rows.append(
            [
                t("kind_role"),
                role_name(h["role_code"]) or h.get("custom_label"),
                h.get("holder_name") or "",
                "",
                valid,
                "",
            ]
        )
    for code in roles.get("vacant", []):
        if code not in held:
            rows.append([t("kind_role"), role_name(code), t("vacant"), "", "", ""])
    for b in bodies:
        members = ", ".join(
            role_name(m["role_code"]) if m.get("role_code") else (m.get("user_id") or m.get("contact_id") or "")
            for m in b.get("members", [])
            if m.get("valid_today")
        )
        rows.append([t("kind_body"), b["name"], members, "", f"{b['quorum_present']}/{b['quorum_needed']}", ""])
    for r in matrix.get("rows", []):
        holder = role_name(r["holder_code"]) if r["holder_kind"] == "role" else r["holder_code"]
        rows.append(
            [
                t("kind_mandate"),
                holder,
                _label(fw, fw.decision_types, r["decision_type"], locale),
                r["letter"],
                r.get("scope") or "",
                r.get("scope_note") or "",
            ]
        )
    return RegisterDocument(
        title=t("organisation_title"),
        columns=[
            RegisterColumn(t("col_kind"), nobreak=True),
            RegisterColumn(t("col_role"), weight=2.0, wrap=True, xlsx_width=28),
            RegisterColumn(t("col_holder"), weight=2.5, wrap=True, xlsx_width=40),
            RegisterColumn(t("col_letter"), nobreak=True),
            RegisterColumn(t("col_valid")),
            RegisterColumn(t("col_scope"), wrap=True),
        ],
        rows=rows,
        details=[(t("project"), project_name), (t("framework"), f"{fw.id} v{fw.version}")],
        locale=locale,
        generated=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        empty_text=t("empty"),
        sheet_title=t("organisation_title"),
    )


def render(doc: RegisterDocument, fmt: str) -> bytes:
    """PDF or XLSX bytes of a register document."""
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
