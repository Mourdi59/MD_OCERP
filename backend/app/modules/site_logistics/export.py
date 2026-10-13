# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The logistics plan as printable registers (PDF and XLSX), rule 21.

Built on :mod:`app.core.register_export`; every label comes from this module's
message bundle. The ``frame`` register is what the governance frame document
for logistics stores as a CDE revision at the gate into construction.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.site_logistics.messages import translate

REGISTERS = ("balance", "media", "transports", "customs", "neighbourhood", "frame")

_COLUMNS: dict[str, list[tuple[str, str, dict[str, Any]]]] = {
    "balance": [
        ("stage", "col_stage", {"nobreak": True}),
        ("group", "col_group", {}),
        ("area_kind", "col_area_kind", {}),
        ("m2", "col_m2", {"kind": "count"}),
        ("pct", "col_pct", {}),
        ("closed", "col_closed", {}),
    ],
    "media": [
        ("stage", "col_stage", {"nobreak": True}),
        ("media_kind", "col_media_kind", {}),
        ("capacity_unit", "col_unit", {}),
        ("required", "col_required", {}),
        ("contracted", "col_contracted", {}),
        ("short", "col_short", {}),
    ],
    "transports": [
        ("title", "col_title", {"weight": 2.0, "wrap": True, "xlsx_width": 36}),
        ("direction", "col_direction", {}),
        ("transport_kind", "col_transport_kind", {}),
        ("planned_window_start", "col_window", {}),
        ("is_heavy", "col_heavy", {}),
        ("state", "col_state", {}),
        ("permits", "col_permits", {"wrap": True}),
    ],
    "customs": [
        ("title", "col_title", {"weight": 2.0, "wrap": True, "xlsx_width": 36}),
        ("direction", "col_direction", {}),
        ("incoterm", "col_incoterm", {"nobreak": True}),
        ("named_place", "col_named_place", {}),
        ("hs_codes", "col_hs_codes", {"wrap": True}),
        ("documents", "col_documents", {"wrap": True}),
        ("state", "col_state", {}),
    ],
    "neighbourhood": [
        ("date", "col_date", {"kind": "date"}),
        ("type", "col_type", {}),
        ("topic", "col_topic", {"weight": 2.0, "wrap": True, "xlsx_width": 40}),
        ("state", "col_state", {}),
        ("due", "col_due", {"kind": "date"}),
    ],
    "frame": [
        ("section", "col_section", {"nobreak": True}),
        ("item", "col_item", {"weight": 2.0, "wrap": True, "xlsx_width": 40}),
        ("value", "col_value", {"wrap": True}),
    ],
}
_ENUMS = {"direction", "state", "group", "closed", "short", "is_heavy", "type", "section"}


def register_document(
    register: str, rows: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str
) -> RegisterDocument:
    """A register as the shared PDF/XLSX document model."""

    def t(key: str) -> str:
        return translate(f"site_logistics.export.{key}", locale=locale)

    spec = _COLUMNS[register]
    out_rows = []
    for r in rows:
        line = []
        for field, _label, _kw in spec:
            value = r.get(field)
            if field in _ENUMS and value is not None and value != "":
                value = translate(f"site_logistics.enum.{field}.{str(value).lower()}", locale=locale)
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


def written_locale(requested: str | None) -> str:
    """The language a register is actually written in for a requested locale.

    The message bundle answers a locale it does not ship in English, so that is
    what the response has to declare, not what the reader asked for.
    """
    from app.modules.site_logistics.messages import available_locales

    return requested if requested and requested in available_locales() else "en"


def render(
    register: str, rows: Sequence[dict[str, Any]], *, project_name: str, locale: str, as_of: str, fmt: str
) -> bytes:
    """PDF or XLSX bytes of one register."""
    doc = register_document(register, rows, project_name=project_name, locale=locale, as_of=as_of)
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)


def register_rows(register: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the service read models into register rows."""
    if register == "balance":
        rows = []
        for item in data["balance"]:
            total = item["area"]["site_total_m2"]
            for kind, m2 in sorted(item["area"]["by_kind"].items()):
                rows.append(
                    {
                        "stage": item["stage"]["code"],
                        "group": data["groups"].get(kind, ""),
                        "area_kind": kind,
                        "m2": m2,
                        "pct": _pct(m2, total),
                        "closed": "",
                    }
                )
            rows.append(
                {
                    "stage": item["stage"]["code"],
                    "group": "",
                    "area_kind": "site_total",
                    "m2": total,
                    "pct": item["area"]["difference_pct"] or "",
                    "closed": "yes" if item["area"]["closed"] else "no",
                }
            )
        return rows
    if register == "media":
        return [
            {
                "stage": item["stage"]["code"],
                "media_kind": m["media_kind"],
                "capacity_unit": m["capacity_unit"],
                "required": m["required"],
                "contracted": m["contracted"],
                "short": "yes" if m["short"] else "no",
            }
            for item in data["balance"]
            for m in item["media"]
        ]
    if register == "transports":
        return [
            {
                **t,
                "is_heavy": "yes" if t["is_heavy"] else "no",
                "permits": ", ".join(f"{p['permit_kind']} ({p['state']})" for p in t["permits"]),
            }
            for t in data["transports"]
        ]
    if register == "customs":
        return data["customs"]
    if register == "neighbourhood":
        rows = [
            {
                "date": c["reported_on"],
                "type": "complaint",
                "topic": c["kind"],
                "state": c["state"],
                "due": c["response_due"],
            }
            for c in data["complaints"]
        ]
        rows += [
            {
                "date": e["entry_date"],
                "type": "coordination",
                "topic": e["topic"],
                "state": e["body"],
                "due": e["next_action_due"],
            }
            for e in data["coordination"]
        ]
        return sorted(rows, key=lambda r: str(r["date"] or ""))
    if register == "frame":
        rows = [{"section": "readiness", "item": i["code"], "value": i["state"]} for i in data["readiness"]["items"]]
        for item in data["balance"]:
            rows.append(
                {
                    "section": "balance",
                    "item": item["stage"]["code"],
                    "value": f"{item['area']['counted_m2']} / {item['area']['site_total_m2']} m2",
                }
            )
        concept = data.get("concept") or {}
        for flow in concept.get("strategy") or []:
            rows.append({"section": "concept", "item": flow["flow_code"], "value": flow["mode"]})
        hood = data.get("neighbourhood") or {}
        if hood:
            rows.append(
                {
                    "section": "neighbourhood",
                    "item": hood.get("noise_limit_source") or "",
                    "value": " - ".join(hood.get("quiet_hours") or []),
                }
            )
        return rows
    raise KeyError(register)


def _pct(part: str, total: str) -> str:
    from decimal import Decimal

    t = Decimal(str(total or "0"))
    if t == 0:
        return ""
    return str((Decimal(str(part)) * 100 / t).quantize(Decimal("0.1")))
