# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""String catalogue for the printed invoice and the printed payment record.

The fixed strings of the two finance record forms live here, next to the
renderer, the way :mod:`app.modules.changeorders.pdf_translations` keeps the
change order's. The page furniture (footer, signature captions, "Total") is
the shared one in :data:`app.core.register_export.FURNITURE`, with
:data:`app.core.register_export.FORM_FURNITURE` for German and Russian.

English, German and Russian are in the catalogue; any other request renders
in English and the route says so in ``Content-Language``. The Brazilian RPS
layout in :mod:`app.modules.finance.br_invoice_pdf` is a separate document
with its own fixed language and is not affected.
"""

from __future__ import annotations

from typing import Any

from app.core.register_export import FORM_FURNITURE, DocumentCatalogue, export_filename

__all__ = [
    "CATALOGUE",
    "DEFAULT_PDF_LOCALE",
    "SUPPORTED_PDF_LOCALES",
    "invoice_pdf_filename",
    "normalize_pdf_locale",
    "payment_pdf_filename",
    "resolve_pdf_locale",
    "tr",
]

DEFAULT_PDF_LOCALE = "en"

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "invoice_title": "Invoice",
        "payment_title": "Payment",
        "direction": "Direction",
        "supplier": "Supplier",
        "client": "Client",
        "invoice_date": "Invoice date",
        "due_date": "Due date",
        "payment_terms": "Payment terms",
        "purchase_order": "Purchase order",
        "invoice_total": "Invoice total",
        "line_items": "Line items",
        "col_no": "No.",
        "col_description": "Description",
        "col_quantity": "Qty",
        "col_unit": "Unit",
        "col_unit_rate": "Unit rate",
        "col_vat": "VAT",
        "col_amount": "Amount",
        "no_line_items": "No line items.",
        "totals": "Totals",
        "subtotal": "Net amount",
        "tax": "Tax",
        "total_gross": "Total incl. tax",
        "retention": "Retention",
        "amount_due": "Payable after retention",
        "payments": "Payments",
        "col_date": "Date",
        "col_reference": "Reference",
        "col_paid": "Paid",
        "col_withheld": "Withheld",
        "refund": "Refund",
        "no_payments": "No payments recorded.",
        "notes": "Notes",
        "no_notes": "No notes recorded.",
        "invoice": "Invoice",
        "invoice_number": "Invoice no.",
        "payment_date": "Payment date",
        "reference": "Reference",
        "amount_paid": "Amount paid",
        "exchange_rate": "Exchange rate",
        "kind": "Type",
        "kind_payment": "Payment",
        "kind_refund": "Refund",
        "withholding": "Retention withheld",
        "withheld_amount": "Amount withheld",
        "release_date": "Release date",
        "gross_settled": "Gross amount settled",
        "no_withholding": "Nothing was withheld from this payment.",
    },
    "de": {
        "invoice_title": "Rechnung",
        "payment_title": "Zahlung",
        "direction": "Rechnungsart",
        "supplier": "Lieferant",
        "client": "Kunde",
        "invoice_date": "Rechnungsdatum",
        "due_date": "Fällig am",
        "payment_terms": "Zahlungsziel",
        "purchase_order": "Bestellung",
        "invoice_total": "Rechnungsbetrag",
        "line_items": "Positionen",
        "col_no": "Pos.",
        "col_description": "Beschreibung",
        "col_quantity": "Menge",
        "col_unit": "Einheit",
        "col_unit_rate": "Einheitspreis",
        "col_vat": "USt.",
        "col_amount": "Betrag",
        "no_line_items": "Keine Positionen.",
        "totals": "Summen",
        "subtotal": "Nettobetrag",
        "tax": "Steuer",
        "total_gross": "Gesamtbetrag inkl. Steuer",
        "retention": "Einbehalt",
        "amount_due": "Zahlbetrag nach Einbehalt",
        "payments": "Zahlungen",
        "col_date": "Datum",
        "col_reference": "Referenz",
        "col_paid": "Gezahlt",
        "col_withheld": "Einbehalten",
        "refund": "Erstattung",
        "no_payments": "Keine Zahlungen erfasst.",
        "notes": "Bemerkungen",
        "no_notes": "Keine Bemerkungen.",
        "invoice": "Rechnung",
        "invoice_number": "Rechnungs-Nr.",
        "payment_date": "Zahlungsdatum",
        "reference": "Referenz",
        "amount_paid": "Gezahlter Betrag",
        "exchange_rate": "Wechselkurs",
        "kind": "Art",
        "kind_payment": "Zahlung",
        "kind_refund": "Erstattung",
        "withholding": "Einbehalt",
        "withheld_amount": "Einbehaltener Betrag",
        "release_date": "Freigabe am",
        "gross_settled": "Abgerechneter Bruttobetrag",
        "no_withholding": "Von dieser Zahlung wurde nichts einbehalten.",
    },
    "ru": {
        "invoice_title": "Счёт",
        "payment_title": "Платёж",
        "direction": "Тип счёта",
        "supplier": "Поставщик",
        "client": "Заказчик",
        "invoice_date": "Дата счёта",
        "due_date": "Срок оплаты",
        "payment_terms": "Условия оплаты",
        "purchase_order": "Заказ на поставку",
        "invoice_total": "Сумма счёта",
        "line_items": "Позиции",
        "col_no": "№",
        "col_description": "Наименование",
        "col_quantity": "Кол-во",
        "col_unit": "Ед. изм.",
        "col_unit_rate": "Цена за ед.",
        "col_vat": "НДС",
        "col_amount": "Сумма",
        "no_line_items": "Позиций нет.",
        "totals": "Итоги",
        "subtotal": "Сумма без налога",
        "tax": "Налог",
        "total_gross": "Всего с налогом",
        "retention": "Удержание",
        "amount_due": "К оплате за вычетом удержания",
        "payments": "Платежи",
        "col_date": "Дата",
        "col_reference": "Основание",
        "col_paid": "Оплачено",
        "col_withheld": "Удержано",
        "refund": "Возврат",
        "no_payments": "Платежей нет.",
        "notes": "Примечания",
        "no_notes": "Примечаний нет.",
        "invoice": "Счёт",
        "invoice_number": "№ счёта",
        "payment_date": "Дата платежа",
        "reference": "Основание",
        "amount_paid": "Сумма платежа",
        "exchange_rate": "Курс",
        "kind": "Вид",
        "kind_payment": "Оплата",
        "kind_refund": "Возврат",
        "withholding": "Удержание",
        "withheld_amount": "Сумма удержания",
        "release_date": "Дата возврата удержания",
        "gross_settled": "Погашено всего",
        "no_withholding": "Удержаний по этому платежу нет.",
    },
}

_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "invoice_status": {
        "en": {
            "draft": "Draft",
            "pending": "Pending approval",
            "approved": "Approved",
            "sent": "Sent",
            "paid": "Paid",
            "cancelled": "Cancelled",
            "credit_note_issued": "Credit note issued",
        },
        "de": {
            "draft": "Entwurf",
            "pending": "Zur Freigabe",
            "approved": "Freigegeben",
            "sent": "Versendet",
            "paid": "Bezahlt",
            "cancelled": "Storniert",
            "credit_note_issued": "Gutschrift erstellt",
        },
        "ru": {
            "draft": "Черновик",
            "pending": "На согласовании",
            "approved": "Утверждён",
            "sent": "Отправлен",
            "paid": "Оплачен",
            "cancelled": "Отменён",
            "credit_note_issued": "Выставлена кредит-нота",
        },
    },
    "direction": {
        "en": {"payable": "Payable (supplier invoice)", "receivable": "Receivable (client invoice)"},
        "de": {"payable": "Eingangsrechnung", "receivable": "Ausgangsrechnung"},
        "ru": {"payable": "Входящий счёт", "receivable": "Исходящий счёт"},
    },
    "payment_status": {
        "en": {"completed": "Completed", "refunded": "Refunded"},
        "de": {"completed": "Ausgeführt", "refunded": "Erstattet"},
        "ru": {"completed": "Проведён", "refunded": "Возвращён"},
    },
}

CATALOGUE = DocumentCatalogue(_STRINGS, _LABELS, default=DEFAULT_PDF_LOCALE, furniture=FORM_FURNITURE)

#: Languages the finance documents can render; anything else is English.
SUPPORTED_PDF_LOCALES: tuple[str, ...] = CATALOGUE.supported


def normalize_pdf_locale(value: str | None) -> str:
    """Reduce a locale-ish value to a member of :data:`SUPPORTED_PDF_LOCALES`."""
    return CATALOGUE.normalize(value)


def resolve_pdf_locale(locale_param: str | None, accept_language: str | None) -> str:
    """Pick the document language: ``?locale=``, then ``Accept-Language``, then English."""
    return CATALOGUE.resolve(locale_param, accept_language)


def tr(locale: str, key: str, **params: Any) -> str:
    """Resolve ``key`` for ``locale``, falling back to English, then the key."""
    return CATALOGUE.tr(locale, key, **params)


def invoice_pdf_filename(number: str | None) -> str:
    """Download filename for one invoice, e.g. ``INV-0042.pdf``."""
    return export_filename(number, "invoice", "pdf")


def payment_pdf_filename(invoice_number: str | None, payment_date: str | None) -> str:
    """Download filename for one payment, e.g. ``Payment_INV-0042_2026-10-01.pdf``."""
    stem = "_".join(part for part in ("Payment", invoice_number, (payment_date or "")[:10]) if part)
    return export_filename(stem, "payment", "pdf")
