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

Eligibility is gated on the project's country and not on the contract's
currency: ``is_aia_eligible`` resolves US, CA or AU from the project, while the
currency is a free ISO code the contract carries. A US project may therefore
run a contract denominated in something other than dollars, so how many digits
an amount keeps is asked of ``app.core.money`` rather than assumed to be two.
"""

# Copyright 2024-2026 OpenEstimate Contributors
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import html
import io
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.money import minor_units, money_quantum
from app.core.pdf_fonts import (
    BODY_FONT,
    BOLD_FONT,
    pdf_style_for_text,
    pdf_table_paragraph_rows,
    register_pdf_fonts,
)

register_pdf_fonts()

PLACEHOLDER = "-"


def _amount(value: Any, currency: str = "") -> str:
    """Format a money value as ``1,234,567.89``, in its currency's own units.

    How many digits follow the separator is a question about the currency, not
    about the form, and :func:`app.core.money.minor_units` is the one place
    that knows. The continuation sheet calls this directly because its columns
    are too narrow to repeat the code on every row, and its figures still have
    to agree with the face that does carry it. A blank or unregistered code
    takes the registry's own two-decimal default rather than a guess made here.
    """
    try:
        d = Decimal(str(value)) if value not in (None, "") else Decimal("0")
        if not d.is_finite():
            d = Decimal("0")
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal("0")
    code = (currency or "").strip().upper()
    return f"{d.quantize(money_quantum(code), rounding=ROUND_HALF_UP):,.{minor_units(code)}f}"


def _money(value: Any, currency: str = "") -> str:
    """The same figure with its currency code in front, for the G702 face."""
    body = _amount(value, currency)
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

    Every table in this document is built from Paragraphs, so this is the only
    kind of cell here and a table command naming a font, a size, a colour or an
    alignment would not be obeyed by any of them.
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
    # The continuation sheet's header row sits on a near black fill, so its
    # cells carry the white the table's TEXTCOLOR command used to ask for and
    # could not deliver.
    head_l = ParagraphStyle("AIAHeadL", parent=cell_l, fontName=BOLD_FONT, textColor=colors.white)
    head_r = ParagraphStyle("AIAHeadR", parent=cell_r, fontName=BOLD_FONT, textColor=colors.white)
    foot_l = ParagraphStyle("AIAFootL", parent=cell_l, fontName=BOLD_FONT)
    foot_r = ParagraphStyle("AIAFootR", parent=cell_r, fontName=BOLD_FONT)
    # The G702 tables above. A bold label column, a right aligned money column
    # and a bold total row were table commands until these cells became
    # Paragraphs, which no table command can reach.
    label = ParagraphStyle("AIALabel", parent=body, fontName=BOLD_FONT)
    value = ParagraphStyle("AIAValue", parent=body)
    money = ParagraphStyle("AIAMoney", parent=body, alignment=TA_RIGHT)
    money_total = ParagraphStyle("AIAMoneyTotal", parent=money, fontName=BOLD_FONT)

    def _label_columns(*columns: int):
        """Draw the named columns as bold labels and everything else as values."""

        def choose(_row_index: int, col_index: int):
            return label if col_index in columns else None

        return choose

    def _summary_face(row_index: int, col_index: int):
        """Row 7 is the payment due line, which the form prints in bold."""
        if row_index == 7:
            return money_total if col_index == 1 else label
        return money if col_index == 1 else None

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
    # Paragraph cells rather than bare strings. A bare cell is drawn through
    # canvas.drawString, which neither wraps nor shapes: a period or a currency
    # longer than its column was printed straight over the column beside it,
    # and a Thai or Devanagari value was mis-arranged whatever face it was
    # given. A Paragraph does both, and carries its own face, size and colour,
    # which is why the font commands this table used to append are gone.
    header_rows = pdf_table_paragraph_rows(header_rows, value, style_for=_label_columns(0, 2))
    header_tbl = Table(header_rows, colWidths=[40 * mm, 70 * mm, 40 * mm, 70 * mm])
    header_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
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
    # Paragraph cells for the reason given at the header table above. The
    # right alignment of the money column and the bold payment due row were
    # table commands and are now paragraph styles, which is the only place a
    # flowable cell reads them from.
    summary_rows = pdf_table_paragraph_rows(summary_rows, value, style_for=_summary_face)
    summary_tbl = Table(summary_rows, colWidths=[150 * mm, 70 * mm])
    summary_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 7), (-1, 7), colors.whitesmoke),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(summary_tbl)
    story.append(Spacer(1, 5 * mm))

    # ── Certification block ────────────────────────────────────────────
    story.append(Paragraph("Certification", h2))
    cert_rows = [
        ["Architect certified", _txt(cert.get("architect_certified_by")), _txt(cert.get("architect_certified_at"))],
        ["Owner certified", _txt(cert.get("owner_certified_by")), _txt(cert.get("owner_certified_at"))],
        ["Amount certified", _money(cert.get("certified_amount"), currency), ""],
    ]
    # Paragraph cells for the reason given at the header table above. The
    # certifier names in these rows are typed by a person, and a practice name
    # that runs past 90mm used to be printed over the date beside it.
    cert_rows = pdf_table_paragraph_rows(cert_rows, value, style_for=_label_columns(0))
    cert_tbl = Table(cert_rows, colWidths=[50 * mm, 90 * mm, 80 * mm])
    cert_tbl.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(cert_tbl)
    story.append(Spacer(1, 8 * mm))

    # ── G703 continuation sheet ────────────────────────────────────────
    story.append(Paragraph("Continuation Sheet - AIA Document G703 (functional equivalent)", h2))
    story.append(Spacer(1, 2 * mm))

    head = [
        _safe_para("A\nItem", head_l),
        _safe_para("B\nDescription of work", head_l),
        _safe_para("C\nScheduled value", head_r),
        _safe_para("D\nFrom previous", head_r),
        _safe_para("E\nThis period", head_r),
        _safe_para("F\nStored", head_r),
        _safe_para("G\nTotal completed", head_r),
        _safe_para("%\n(G/C)", head_r),
        _safe_para("H\nBalance to finish", head_r),
        _safe_para("I\nRetainage", head_r),
    ]
    data: list[list[Any]] = [head]
    for ln in lines:
        data.append(
            [
                _safe_para(ln.get("item_number"), cell_l),
                _safe_para(ln.get("description"), cell_l),
                Paragraph(_amount(ln.get("scheduled_value"), currency), cell_r),
                Paragraph(_amount(ln.get("previous_value"), currency), cell_r),
                Paragraph(_amount(ln.get("this_period_value"), currency), cell_r),
                Paragraph(_amount(ln.get("materials_stored"), currency), cell_r),
                Paragraph(_amount(ln.get("total_completed_stored"), currency), cell_r),
                Paragraph(_pct(ln.get("percent_complete")), cell_r),
                Paragraph(_amount(ln.get("balance_to_finish"), currency), cell_r),
                Paragraph(_amount(ln.get("retainage"), currency), cell_r),
            ]
        )

    # Totals row from the summary.
    data.append(
        [
            Paragraph("", foot_l),
            _safe_para("Grand total", foot_l),
            Paragraph(_amount(summary.get("contract_sum_to_date"), currency), foot_r),
            Paragraph("", foot_r),
            Paragraph("", foot_r),
            Paragraph("", foot_r),
            Paragraph(_amount(summary.get("total_completed_stored"), currency), foot_r),
            Paragraph("", foot_r),
            Paragraph(_amount(summary.get("balance_to_finish"), currency), foot_r),
            Paragraph(_amount(summary.get("retainage"), currency), foot_r),
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
    # Every cell here is already a Paragraph, so the shaping and font command
    # helpers this table used to call had nothing to act on and were removed.
    # The TEXTCOLOR and FONTNAME commands that used to sit here had nothing to
    # act on either, which is the part that was not harmless: the header row
    # asked for white bold text on a #1f2937 fill and got black regular,
    # because a table command cannot reach a flowable. The white and the weight
    # now live on head_l and head_r, and the totals row's weight on foot_l and
    # foot_r, where a Paragraph reads them.
    g703_tbl = Table(data, colWidths=col_widths, repeatRows=1)
    g703_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(g703_tbl)

    doc.build(story)
    return buf.getvalue()


__all__ = ["render_aia_application_pdf"]
