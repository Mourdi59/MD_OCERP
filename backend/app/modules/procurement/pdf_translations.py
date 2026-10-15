# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""String catalogue for the printed purchase order and goods receipt.

The fixed strings of the two procurement record forms live here, next to the
renderer, the way :mod:`app.modules.changeorders.pdf_translations` keeps the
change order's. The page furniture (footer, signature captions, "Total") is
the shared one in :data:`app.core.register_export.FURNITURE`, with
:data:`app.core.register_export.FORM_FURNITURE` for German and Russian.

English, German and Russian are in the catalogue; any other request renders
in English and the route says so in ``Content-Language``. The Russian strings
avoid past tense verbs, which would force a grammatical gender onto whoever
ordered or received the goods.
"""

from __future__ import annotations

from typing import Any

from app.core.register_export import FORM_FURNITURE, DocumentCatalogue, export_filename

__all__ = [
    "CATALOGUE",
    "DEFAULT_PDF_LOCALE",
    "SUPPORTED_PDF_LOCALES",
    "goods_receipt_pdf_filename",
    "normalize_pdf_locale",
    "purchase_order_pdf_filename",
    "resolve_pdf_locale",
    "tr",
]

DEFAULT_PDF_LOCALE = "en"

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "po_title": "Purchase Order",
        "gr_title": "Goods Receipt",
        "supplier": "Supplier",
        "po_type": "Order type",
        "issue_date": "Issue date",
        "delivery_date": "Delivery date",
        "created_by": "Prepared by",
        "order_total": "Order total",
        "line_items": "Line items",
        "col_no": "No.",
        "col_description": "Description",
        "col_quantity": "Qty",
        "col_unit": "Unit",
        "col_unit_rate": "Unit rate",
        "col_amount": "Amount",
        "no_line_items": "No line items.",
        "totals": "Totals",
        "subtotal": "Net amount",
        "tax": "Tax",
        "total_gross": "Total incl. tax",
        "terms": "Terms",
        "payment_terms": "Payment terms",
        "retention": "Retention",
        "retention_at": "Retention withheld at",
        "retention_at_receipt": "Goods receipt",
        "retention_at_invoice": "Invoice",
        "invoice_tolerance": "Invoice tolerance",
        "supplier_confirmation": "Supplier confirmation",
        "supplier_reference": "Supplier reference",
        "confirmed_delivery": "Confirmed delivery date",
        "acknowledged_on": "Acknowledged on",
        "not_confirmed": "Not confirmed by the supplier yet.",
        "notes": "Notes",
        "no_notes": "No notes recorded.",
        "sig_ordered_by": "Ordered by",
        "purchase_order": "Purchase order",
        "receipt_date": "Receipt date",
        "received_by": "Received by",
        "delivery_note": "Delivery note",
        "col_ordered": "Ordered",
        "col_received": "Received",
        "col_rejected": "Rejected",
        "col_batch": "Batch / lot",
        "rejections": "Rejections",
        "col_reason": "Reason",
        "no_rejections": "Nothing was rejected.",
        "sig_delivered_by": "Delivered by",
    },
    "de": {
        "po_title": "Bestellung",
        "gr_title": "Wareneingang",
        "supplier": "Lieferant",
        "po_type": "Bestellart",
        "issue_date": "Bestelldatum",
        "delivery_date": "Liefertermin",
        "created_by": "Erstellt von",
        "order_total": "Bestellsumme",
        "line_items": "Positionen",
        "col_no": "Pos.",
        "col_description": "Beschreibung",
        "col_quantity": "Menge",
        "col_unit": "Einheit",
        "col_unit_rate": "Einheitspreis",
        "col_amount": "Betrag",
        "no_line_items": "Keine Positionen.",
        "totals": "Summen",
        "subtotal": "Nettobetrag",
        "tax": "Steuer",
        "total_gross": "Gesamtbetrag inkl. Steuer",
        "terms": "Konditionen",
        "payment_terms": "Zahlungsbedingungen",
        "retention": "Einbehalt",
        "retention_at": "Einbehalt bei",
        "retention_at_receipt": "Wareneingang",
        "retention_at_invoice": "Rechnung",
        "invoice_tolerance": "Rechnungstoleranz",
        "supplier_confirmation": "Auftragsbestätigung",
        "supplier_reference": "Referenz des Lieferanten",
        "confirmed_delivery": "Bestätigter Liefertermin",
        "acknowledged_on": "Bestätigt am",
        "not_confirmed": "Vom Lieferanten noch nicht bestätigt.",
        "notes": "Bemerkungen",
        "no_notes": "Keine Bemerkungen.",
        "sig_ordered_by": "Besteller",
        "purchase_order": "Bestellung",
        "receipt_date": "Eingangsdatum",
        "received_by": "Angenommen von",
        "delivery_note": "Lieferschein",
        "col_ordered": "Bestellt",
        "col_received": "Erhalten",
        "col_rejected": "Abgelehnt",
        "col_batch": "Charge",
        "rejections": "Beanstandungen",
        "col_reason": "Grund",
        "no_rejections": "Nichts beanstandet.",
        "sig_delivered_by": "Übergeben von",
    },
    "ru": {
        "po_title": "Заказ на поставку",
        "gr_title": "Приёмка поставки",
        "supplier": "Поставщик",
        "po_type": "Тип заказа",
        "issue_date": "Дата выдачи",
        "delivery_date": "Срок поставки",
        "created_by": "Составитель",
        "order_total": "Сумма заказа",
        "line_items": "Позиции",
        "col_no": "№",
        "col_description": "Наименование",
        "col_quantity": "Кол-во",
        "col_unit": "Ед. изм.",
        "col_unit_rate": "Цена за ед.",
        "col_amount": "Сумма",
        "no_line_items": "Позиций нет.",
        "totals": "Итоги",
        "subtotal": "Сумма без налога",
        "tax": "Налог",
        "total_gross": "Всего с налогом",
        "terms": "Условия",
        "payment_terms": "Условия оплаты",
        "retention": "Удержание",
        "retention_at": "Момент удержания",
        "retention_at_receipt": "Приёмка",
        "retention_at_invoice": "Счёт",
        "invoice_tolerance": "Допуск по счёту",
        "supplier_confirmation": "Подтверждение поставщика",
        "supplier_reference": "Номер у поставщика",
        "confirmed_delivery": "Подтверждённый срок",
        "acknowledged_on": "Дата подтверждения",
        "not_confirmed": "Поставщик ещё не подтвердил заказ.",
        "notes": "Примечания",
        "no_notes": "Примечаний нет.",
        "sig_ordered_by": "Заказчик",
        "purchase_order": "Заказ на поставку",
        "receipt_date": "Дата приёмки",
        "received_by": "Приёмщик",
        "delivery_note": "Накладная",
        "col_ordered": "Заказано",
        "col_received": "Принято",
        "col_rejected": "Отклонено",
        "col_batch": "Партия",
        "rejections": "Отклонения",
        "col_reason": "Причина",
        "no_rejections": "Отклонений нет.",
        "sig_delivered_by": "Сдающая сторона",
    },
}

_LABELS: dict[str, dict[str, dict[str, str]]] = {
    "po_status": {
        "en": {
            "draft": "Draft",
            "approved": "Approved",
            "issued": "Issued",
            "partially_received": "Partially received",
            "completed": "Completed",
            "cancelled": "Cancelled",
        },
        "de": {
            "draft": "Entwurf",
            "approved": "Freigegeben",
            "issued": "Bestellt",
            "partially_received": "Teilweise geliefert",
            "completed": "Abgeschlossen",
            "cancelled": "Storniert",
        },
        "ru": {
            "draft": "Черновик",
            "approved": "Утверждён",
            "issued": "Выдан",
            "partially_received": "Получен частично",
            "completed": "Выполнен",
            "cancelled": "Отменён",
        },
    },
    "gr_status": {
        "en": {"draft": "Draft", "confirmed": "Confirmed"},
        "de": {"draft": "Entwurf", "confirmed": "Bestätigt"},
        "ru": {"draft": "Черновик", "confirmed": "Подтверждена"},
    },
    "po_type": {
        "en": {"standard": "Standard", "blanket": "Blanket order", "service": "Services"},
        "de": {"standard": "Standard", "blanket": "Rahmenbestellung", "service": "Dienstleistung"},
        "ru": {"standard": "Стандартный", "blanket": "Рамочный", "service": "Услуги"},
    },
}

CATALOGUE = DocumentCatalogue(_STRINGS, _LABELS, default=DEFAULT_PDF_LOCALE, furniture=FORM_FURNITURE)

#: Languages the procurement documents can render; anything else is English.
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


def purchase_order_pdf_filename(number: str | None) -> str:
    """Download filename for one purchase order, e.g. ``PO-0001.pdf``."""
    return export_filename(number, "purchase-order", "pdf")


def goods_receipt_pdf_filename(po_number: str | None, delivery_note: str | None) -> str:
    """Download filename for one goods receipt, e.g. ``GR_PO-0001_DN-77.pdf``."""
    stem = "_".join(part for part in ("GR", po_number, delivery_note) if part)
    return export_filename(stem, "goods-receipt", "pdf")
