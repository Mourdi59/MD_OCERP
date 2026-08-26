# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""AIA G702/G703 payment-application PDF (US/CA/AU only).

Renders a two-part document mirroring the layout of the AIA standard forms:

* G702 - Application and Certificate for Payment (the summary face with the
  contract-sum-to-date math and the architect/owner certification block), and
* G703 - Continuation Sheet (one row per schedule-of-values line with the
  previous / this-period / stored / total / balance / retainage columns).

These are the official AIA copyrighted layouts only in spirit: this is a
clean-room functional equivalent that carries the same figures, suitable for
internal review and submission alongside the executed AIA forms. The PDF is
Unicode-safe via :mod:`app.core.pdf_fonts` (DejaVu Sans), so currency symbols
and accented names render rather than showing empty boxes.

The render function takes the dict produced by
``ContractsService.build_aia_application`` so all arithmetic stays in the pure,
unit-tested builders and the PDF layer only formats.
"""

# Copyright 2024-2026 OpenEstimate Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import html
import io
from decimal import Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.pdf_fonts import (
    BODY_FONT,
    BOLD_FONT,
    pdf_style_for_text,
    pdf_table_font_commands,
    pdf_table_shaped_rows,
    register_pdf_fonts,
)

register_pdf_fonts()

PLACEHOLDER = "-"


def _money(value: Any, currency: str = "") -> str:
    """Format a Decimal money value as ``1,234,567.89`` with optional code."""
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal("0")
        if not d.is_finite():
            d = Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    body = f"{d.quantize(Decimal('0.01')):,.2f}"
    return f"{currency} {body}".strip() if currency else body


def _pct(value: Any) -> str:
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    return f"{d.quantize(Decimal('0.01'))}%"


def _txt(value: Any) -> str:
    """Format a value for a plain string table cell.

    Deliberately does not escape, and the difference from :func:`_safe_para`
    below is the kind of cell rather than the caller. A plain string in a table
    cell is drawn straight to the canvas and never parsed as markup, so escaping
    here does not protect anything, it puts the entity on the page: a party
    named ``R&D Tower`` printed as ``R&amp;D Tower`` on the certificate. A
    Paragraph is parsed, which is why the helper that builds one does escape.
    """
    if value in (None, ""):
        return PLACEHOLDER
    return str(value)


def _safe_para(text: Any, style: ParagraphStyle) -> Paragraph:
    """Build a Paragraph cell, escaped and faced for the text it carries.

    The face is chosen from the raw string rather than the escaped one. Escaping
    only ever adds ASCII, so the two cannot disagree about which face is needed,
    and asking the raw string keeps the question about what a party wrote.

    This reaches the schedule-of-values cells and nothing above them. The four
    summary tables are plain strings drawn under their own ``FONTNAME``, which a
    paragraph style cannot reach at all, so they are faced separately.
    """
    raw = "" if text is None else str(text)
    return Paragraph(html.escape(raw), pdf_style_for_text(style, raw))


def render_aia_application_pdf(app: dict[str, Any]) -> bytes:
    """Render the AIA G702 + G703 application dict to PDF bytes.

    ``app`` is the structure returned by ``ContractsService.build_aia_application``.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="AIA G702/G703 Application for Payment",
    )

    base = getSampleStyleSheet()
    h1 = ParagraphStyle("AIAH1", parent=base["Heading1"], fontName=BOLD_FONT, fontSize=14, alignment=TA_CENTER)
    h2 = ParagraphStyle("AIAH2", parent=base["Heading2"], fontName=BOLD_FONT, fontSize=10)
    body = ParagraphStyle("AIABody", parent=base["Normal"], fontName=BODY_FONT, fontSize=8)
    cell = ParagraphStyle("AIACell", parent=body, fontSize=7, leading=9)
    cell_r = ParagraphStyle("AIACellR", parent=cell, alignment=TA_RIGHT)
    cell_l = ParagraphStyle("AIACellL", parent=cell, alignment=TA_LEFT)

    currency = str(app.get("currency") or "")
    summary = app.get("summary", {}) or {}
    cert = app.get("certification", {}) or {}
    lines = app.get("lines", []) or []

    story: list[Any] = []
    story.append(Paragraph("Application and Certificate for Payment", h1))
    story.append(Paragraph("AIA Document G702 (functional equivalent)", body))
    story.append(Spacer(1, 6 * mm))

    # ── G702 header facts ──────────────────────────────────────────────
    header_rows = [
        ["Application No.", _txt(app.get("application_number")), "Period to", _txt(app.get("period_end"))],
        ["Application date", _txt(app.get("claim_date")), "Currency", _txt(currency or PLACEHOLDER)],
    ]
    # Shaped before the table is built. These are bare cells, and reportlab
    # draws a bare cell through canvas.drawString, which cannot shape, so a
    # face alone leaves Thai and Devanagari mis-arranged. Same arguments as
    # the font commands below, so both resolve the same face per cell.
    header_rows = pdf_table_shaped_rows(header_rows, base=BODY_FONT)
    header_tbl = Table(header_rows, colWidths=[40 * mm, 70 * mm, 40 * mm, 70 * mm])
    header_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("FONTNAME", (2, 0), (2, -1), BOLD_FONT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    # Plain string cells are drawn under the table's own FONTNAME, so the
    # per-paragraph facing cannot reach them. This adds a command for exactly
    # the cells whose face cannot draw them and none at all for the rest, so a
    # Latin table keeps both its bytes and its column widths.
    #
    # A second setStyle rather than an edit to the first: reportlab applies
    # commands in order and a later one wins for the cells it covers, so every
    # command above survives. Measured rather than taken from the docs, against
    # the certification table's bold first column, which keeps its weight.
    #
    # The base is the body face for the whole table even though some cells here
    # are drawn in the bold one. pdf_table_font_commands offers header_rows for
    # that, but these tables carry bold COLUMNS rather than bold header rows,
    # which the parameter cannot express. Passing one base is safe because the
    # two faces have identical coverage: compared across 0x20 to 0x2E7F, 11744
    # codepoints, they agree on every one. So weight cannot change the
    # escalation decision, and the only commands emitted are escalations to a
    # CJK face that carries one weight anyway. This reasoning expires if those
    # two faces ever diverge in coverage.
    header_tbl.setStyle(TableStyle(pdf_table_font_commands(header_rows, base=BODY_FONT)))
    story.append(header_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── G702 summary lines (1..9) ──────────────────────────────────────
    summary_rows = [
        ["1. Original contract sum", _money(summary.get("original_contract_sum"), currency)],
        ["2. Net change by change orders", _money(summary.get("change_orders_net"), currency)],
        ["3. Contract sum to date (1 + 2)", _money(summary.get("contract_sum_to_date"), currency)],
        ["4. Total completed and stored to date", _money(summary.get("total_completed_stored"), currency)],
        ["5. Retainage", _money(summary.get("retainage"), currency)],
        ["6. Total earned less retainage (4 - 5)", _money(summary.get("total_earned_less_retainage"), currency)],
        ["7. Less previous certificates for payment", _money(summary.get("previous_certificates_total"), currency)],
        ["8. Current payment due", _money(summary.get("current_payment_due"), currency)],
        ["9. Balance to finish including retainage", _money(summary.get("balance_to_finish"), currency)],
    ]
    # Shaped for the reason given at the header table above.
    summary_rows = pdf_table_shaped_rows(summary_rows, base=BODY_FONT)
    summary_tbl = Table(summary_rows, colWidths=[150 * mm, 70 * mm])
    summary_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 7), (-1, 7), BOLD_FONT),
                ("BACKGROUND", (0, 7), (-1, 7), colors.whitesmoke),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    # Faced per cell, for the reasons given at the header table above.
    summary_tbl.setStyle(TableStyle(pdf_table_font_commands(summary_rows, base=BODY_FONT)))
    story.append(summary_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── Certification block ────────────────────────────────────────────
    story.append(Paragraph("Certification", h2))
    cert_rows = [
        ["Architect certified", _txt(cert.get("architect_certified_by")), _txt(cert.get("architect_certified_at"))],
        ["Owner certified", _txt(cert.get("owner_certified_by")), _txt(cert.get("owner_certified_at"))],
        ["Amount certified", _money(cert.get("certified_amount"), currency), ""],
    ]
    # Shaped for the reason given at the header table above. The certifier
    # names in these rows are typed by a person.
    cert_rows = pdf_table_shaped_rows(cert_rows, base=BODY_FONT)
    cert_tbl = Table(cert_rows, colWidths=[50 * mm, 90 * mm, 80 * mm])
    cert_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), BOLD_FONT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    # Faced per cell, for the reasons given at the header table above.
    cert_tbl.setStyle(TableStyle(pdf_table_font_commands(cert_rows, base=BODY_FONT)))
    story.append(cert_tbl)
    story.append(Spacer(1, 8 * mm))

    # ── G703 continuation sheet ────────────────────────────────────────
    story.append(Paragraph("Continuation Sheet - AIA Document G703 (functional equivalent)", h2))
    story.append(Spacer(1, 2 * mm))

    head = [
        _safe_para("A\nItem", cell_l),
        _safe_para("B\nDescription of work", cell_l),
        _safe_para("C\nScheduled value", cell_r),
        _safe_para("D\nFrom previous", cell_r),
        _safe_para("E\nThis period", cell_r),
        _safe_para("F\nStored", cell_r),
        _safe_para("G\nTotal completed", cell_r),
        _safe_para("%\n(G/C)", cell_r),
        _safe_para("H\nBalance to finish", cell_r),
        _safe_para("I\nRetainage", cell_r),
    ]
    data: list[list[Any]] = [head]
    for ln in lines:
        data.append(
            [
                _safe_para(ln.get("item_number"), cell_l),
                _safe_para(ln.get("description"), cell_l),
                Paragraph(_money(ln.get("scheduled_value")), cell_r),
                Paragraph(_money(ln.get("previous_value")), cell_r),
                Paragraph(_money(ln.get("this_period_value")), cell_r),
                Paragraph(_money(ln.get("materials_stored")), cell_r),
                Paragraph(_money(ln.get("total_completed_stored")), cell_r),
                Paragraph(_pct(ln.get("percent_complete")), cell_r),
                Paragraph(_money(ln.get("balance_to_finish")), cell_r),
                Paragraph(_money(ln.get("retainage")), cell_r),
            ]
        )

    # Totals row from the summary.
    data.append(
        [
            Paragraph("", cell_l),
            _safe_para("Grand total", cell_l),
            Paragraph(_money(summary.get("contract_sum_to_date")), cell_r),
            Paragraph("", cell_r),
            Paragraph("", cell_r),
            Paragraph("", cell_r),
            Paragraph(_money(summary.get("total_completed_stored")), cell_r),
            Paragraph("", cell_r),
            Paragraph(_money(summary.get("balance_to_finish")), cell_r),
            Paragraph(_money(summary.get("retainage")), cell_r),
        ]
    )

    col_widths = [
        16 * mm,
        58 * mm,
        28 * mm,
        28 * mm,
        26 * mm,
        22 * mm,
        30 * mm,
        16 * mm,
        28 * mm,
        26 * mm,
    ]
    # Paired with the font commands below for consistency. These cells are
    # Paragraphs, which shape themselves, so this returns the rows untouched;
    # it is here so the pairing holds if a plain string is ever added.
    data = pdf_table_shaped_rows(data, base=BODY_FONT)
    g703_tbl = Table(data, colWidths=col_widths, repeatRows=1)
    g703_tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), BODY_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), BOLD_FONT),
                ("FONTNAME", (0, -1), (-1, -1), BOLD_FONT),
                ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    # Faced per cell, for the reasons given at the header table above.
    g703_tbl.setStyle(TableStyle(pdf_table_font_commands(data, base=BODY_FONT)))
    story.append(g703_tbl)

    doc.build(story)
    return buf.getvalue()


__all__ = ["render_aia_application_pdf"]
