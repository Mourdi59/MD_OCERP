# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Printable registers of the procurement concept (PDF and XLSX, SPEC rule 17).

Built on :mod:`app.core.register_export`; every label comes from this
module's message bundle. ``concept`` is the record the governance frame
document that hosts procurement stores as a CDE revision at the gate.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.register_export import RegisterColumn, RegisterDocument, build_register_pdf, build_register_xlsx
from app.modules.procurement_concept.messages import translate


def _dec(value: Any) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


async def build_document(
    svc: Any, project_id: uuid.UUID, *, part: str, package_id: uuid.UUID | None, project_name: str, locale: str
) -> RegisterDocument:
    def t(key: str) -> str:
        return translate(f"procurement_concept.export.{key}", locale=locale)

    def lbl(prefix: str, value: str | None) -> str:
        return translate(f"procurement_concept.{prefix}.{value}", locale=locale) if value else ""

    concept = await svc.get_concept(project_id)
    state = await svc.effective_state(concept)
    details = [
        (t("project"), project_name),
        (t("jurisdiction"), lbl("jurisdiction", concept.jurisdiction)),
        (t("client_type"), lbl("client_type", concept.client_type)),
        (t("state"), lbl("concept_state", state)),
        (t("catalogue"), f"{concept.catalogue_id} v{concept.catalogue_version}"),
    ]
    common = {
        "locale": locale,
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "empty_text": t("empty"),
        "details": details,
    }
    if part in ("concept", "packages"):
        rows = []
        for v in await svc.package_views(project_id):
            cp, a, th = v["contract_package"], v["award"] or {}, v["threshold"] or {}
            rows.append(
                [
                    cp["code"],
                    cp["title"],
                    lbl("package_kind", v["package_kind"]),
                    lbl("split_basis", a.get("split_basis")),
                    t("yes") if a.get("is_advance") else "",
                    a.get("currency") or "",
                    _dec(a.get("estimated_value")),
                    _dec(a.get("aggregated_value")),
                    lbl("threshold_status", th.get("status")),
                    lbl("procedure", a.get("procedure_code")),
                    lbl("tender_basis", a.get("tender_basis")),
                    lbl("package_state", a.get("state")),
                    (cp.get("execution_link") or {}).get("kind") or "",
                ]
            )
        title = t("title_concept" if part == "concept" else "title_packages")
        return RegisterDocument(
            title=title,
            columns=[
                RegisterColumn(t("col_code"), nobreak=True),
                RegisterColumn(t("col_title"), weight=2.5, wrap=True, xlsx_width=40),
                RegisterColumn(t("col_kind")),
                RegisterColumn(t("col_split")),
                RegisterColumn(t("col_advance")),
                RegisterColumn(t("col_currency"), kind="currency"),
                RegisterColumn(t("col_estimate"), kind="money"),
                RegisterColumn(t("col_aggregated"), kind="money"),
                RegisterColumn(t("col_threshold")),
                RegisterColumn(t("col_procedure"), weight=1.5, wrap=True),
                RegisterColumn(t("col_tender_basis")),
                RegisterColumn(t("col_state")),
                RegisterColumn(t("col_execution")),
            ],
            rows=rows,
            sheet_title=title,
            **common,
        )
    if part == "shortlist":
        if package_id is None:
            from app.modules.procurement_concept.errors import ProcurementError

            raise ProcurementError("package_id_required", 422)
        data = await svc.candidate_views(project_id, package_id)
        rows = [
            [
                c["name"],
                lbl("candidate_list", c["list"]),
                lbl("candidate_source", c["source"]),
                _dec(c["total_score"]),
                t("yes") if c["passed_all"] else t("no"),
                c["decision_rationale"],
            ]
            for c in data["items"]
        ]
        return RegisterDocument(
            title=t("title_shortlist"),
            columns=[
                RegisterColumn(t("col_company"), weight=2, wrap=True),
                RegisterColumn(t("col_list")),
                RegisterColumn(t("col_source")),
                RegisterColumn(t("col_score"), kind="money"),
                RegisterColumn(t("col_passed")),
                RegisterColumn(t("col_rationale"), weight=2.5, wrap=True, xlsx_width=50),
            ],
            rows=rows,
            sheet_title=t("title_shortlist"),
            **common,
        )
    data = await svc.schedule_view(project_id)
    rows = [
        [
            r["code"],
            r["title"],
            lbl("procedure", r["procedure_code"]),
            r["need_date"] or "",
            r["lead_time_days"],
            r["procedure_days"],
            r["proposed_start_date"] or "",
            r["proposed_award_date"] or "",
            ", ".join(f["code"] for f in r["findings"]),
        ]
        for r in data["items"]
    ]
    return RegisterDocument(
        title=t("title_schedule"),
        columns=[
            RegisterColumn(t("col_code"), nobreak=True),
            RegisterColumn(t("col_title"), weight=2, wrap=True),
            RegisterColumn(t("col_procedure")),
            RegisterColumn(t("col_need_date"), kind="date"),
            RegisterColumn(t("col_lead_time"), kind="count"),
            RegisterColumn(t("col_procedure_days"), kind="count"),
            RegisterColumn(t("col_start"), kind="date"),
            RegisterColumn(t("col_award"), kind="date"),
            RegisterColumn(t("col_findings"), weight=1.5, wrap=True),
        ],
        rows=rows,
        sheet_title=t("title_schedule"),
        **common,
    )


async def render(
    svc: Any,
    project_id: uuid.UUID,
    *,
    part: str,
    package_id: uuid.UUID | None,
    project_name: str,
    locale: str,
    fmt: str,
) -> bytes:
    """PDF or XLSX bytes of one part of the concept."""
    doc = await build_document(
        svc, project_id, part=part, package_id=package_id, project_name=project_name, locale=locale
    )
    if fmt == "xlsx":
        buf: io.BytesIO = build_register_xlsx(doc)
        return buf.getvalue()
    return build_register_pdf(doc)
