# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""String catalog and locale resolution for the single-RFI PDF export.

The RFI document is the printable form of one request for information: the
page a site team hands to the design team, files with the contract or
prints for a coordination meeting. Its fixed strings live here, next to the
renderer, the way :mod:`app.modules.daily_diary.pdf_translations` keeps the
diary's, and the rule that picks a language is the shared one in
:mod:`app.core.document_locale`.

The catalogue covers English, German and Russian, the same three languages
:mod:`app.modules.rfi.intl` already labels statuses and disciplines in, so a
document never mixes a translated heading with an untranslated status word.
Any other request falls back to English, and the route serving the PDF
declares the language it actually rendered in ``Content-Language``.

The terms are the ones a construction reader expects on the form rather than
word-for-word copies of the interface labels: German says "Gestellt von" for
raised by and "Nachtrag" for a variation, and the Russian strings avoid past
tense verbs, which would force a grammatical gender onto whoever raised or
answered the RFI.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.core.document_locale import (
    normalize_document_locale,
    resolve_document_locale,
    translate,
)

__all__ = [
    "DEFAULT_PDF_LOCALE",
    "SUPPORTED_PDF_LOCALES",
    "days_text",
    "format_date",
    "normalize_pdf_locale",
    "priority_label",
    "resolve_pdf_locale",
    "rfi_pdf_filename",
    "tr",
]

DEFAULT_PDF_LOCALE = "en"

#: Languages the RFI PDF can render. Extend every table below together when
#: adding one; anything else falls back to English.
SUPPORTED_PDF_LOCALES: tuple[str, ...] = ("en", "de", "ru")

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "doc_title": "Request for Information",
        "project": "Project",
        "raised_by": "Raised by",
        "assigned_to": "Assigned to",
        "ball_in_court": "Ball in court",
        "date_raised": "Date raised",
        "response_due": "Response due",
        "date_required": "Date required",
        "priority": "Priority",
        "discipline": "Discipline",
        "question": "Question",
        "references": "Referenced documents",
        "references_unavailable": "Linked documents no longer available: {count}",
        "attachments": "Attached files",
        "impact": "Impact",
        "cost_impact": "Cost impact",
        "schedule_impact": "Schedule impact",
        "yes": "Yes",
        "yes_with": "Yes, {detail}",
        "no": "No",
        "response": "Official response",
        "no_response": "No response recorded yet.",
        "answered_by": "Answered by",
        "answer_date": "Answer date",
        "variation": "Linked variation",
        "signatures": "Signatures",
        "name": "Name",
        "signature": "Signature",
        "date": "Date",
        "footer_generated": "Generated {timestamp}",
        "footer_page": "Page {page}",
        "date_format": "%Y-%m-%d",
        "datetime_format": "%Y-%m-%d %H:%M UTC",
    },
    "de": {
        "doc_title": "Technische Anfrage (RFI)",
        "project": "Projekt",
        "raised_by": "Gestellt von",
        "assigned_to": "Gerichtet an",
        "ball_in_court": "Zuständig",
        "date_raised": "Gestellt am",
        "response_due": "Antwort fällig am",
        "date_required": "Benötigt bis",
        "priority": "Priorität",
        "discipline": "Fachbereich",
        "question": "Frage",
        "references": "Bezugsdokumente",
        "references_unavailable": "Nicht mehr verfügbare verknüpfte Dokumente: {count}",
        "attachments": "Angehängte Dateien",
        "impact": "Auswirkungen",
        "cost_impact": "Kostenauswirkung",
        "schedule_impact": "Terminauswirkung",
        "yes": "Ja",
        "yes_with": "Ja, {detail}",
        "no": "Nein",
        "response": "Offizielle Antwort",
        "no_response": "Noch keine Antwort erfasst.",
        "answered_by": "Beantwortet von",
        "answer_date": "Antwortdatum",
        "variation": "Verknüpfter Nachtrag",
        "signatures": "Unterschriften",
        "name": "Name",
        "signature": "Unterschrift",
        "date": "Datum",
        "footer_generated": "Erstellt {timestamp}",
        "footer_page": "Seite {page}",
        "date_format": "%d.%m.%Y",
        "datetime_format": "%d.%m.%Y %H:%M UTC",
    },
    "ru": {
        "doc_title": "Запрос информации (RFI)",
        "project": "Проект",
        "raised_by": "Автор запроса",
        "assigned_to": "Адресат",
        "ball_in_court": "Ответственный",
        "date_raised": "Дата запроса",
        "response_due": "Срок ответа",
        "date_required": "Требуется к",
        "priority": "Приоритет",
        "discipline": "Раздел",
        "question": "Вопрос",
        "references": "Связанные документы",
        "references_unavailable": "Связанные документы больше недоступны: {count}",
        "attachments": "Приложенные файлы",
        "impact": "Влияние",
        "cost_impact": "Влияние на стоимость",
        "schedule_impact": "Влияние на сроки",
        "yes": "Да",
        "yes_with": "Да, {detail}",
        "no": "Нет",
        "response": "Официальный ответ",
        "no_response": "Ответ пока не получен.",
        "answered_by": "Автор ответа",
        "answer_date": "Дата ответа",
        "variation": "Связанное изменение",
        "signatures": "Подписи",
        "name": "ФИО",
        "signature": "Подпись",
        "date": "Дата",
        "footer_generated": "Сформировано {timestamp}",
        "footer_page": "Стр. {page}",
        "date_format": "%d.%m.%Y",
        "datetime_format": "%d.%m.%Y %H:%M UTC",
    },
}

_PRIORITY_LABELS: dict[str, dict[str, str]] = {
    "en": {"low": "Low", "normal": "Normal", "high": "High", "critical": "Critical"},
    "de": {"low": "Niedrig", "normal": "Normal", "high": "Hoch", "critical": "Kritisch"},
    "ru": {"low": "Низкий", "normal": "Обычный", "high": "Высокий", "critical": "Критический"},
}


def normalize_pdf_locale(value: str | None) -> str:
    """Reduce a locale-ish value to a supported primary subtag.

    Args:
        value: A locale code such as ``"de"``, ``"de-DE"`` or ``"DE"``.
            ``None`` and unsupported values normalise to ``"en"``.

    Returns:
        A member of :data:`SUPPORTED_PDF_LOCALES`.
    """
    return normalize_document_locale(value, SUPPORTED_PDF_LOCALES, DEFAULT_PDF_LOCALE)


def resolve_pdf_locale(locale_param: str | None, accept_language: str | None) -> str:
    """Pick the PDF language for an HTTP request.

    See :func:`app.core.document_locale.resolve_document_locale` for the rule.
    When this returns ``"en"`` for a reader who asked for something else, the
    route must declare ``Content-Language: en`` so the fallback is visible.

    Args:
        locale_param: Explicit ``?locale=`` query value, if any.
        accept_language: Raw ``Accept-Language`` header value, if any.

    Returns:
        A member of :data:`SUPPORTED_PDF_LOCALES`.
    """
    return resolve_document_locale(locale_param, accept_language, SUPPORTED_PDF_LOCALES, DEFAULT_PDF_LOCALE)


def tr(locale: str, key: str, **params: Any) -> str:
    """Resolve ``key`` for ``locale``, falling back to English, then the key.

    Args:
        locale: A PDF locale code; unknown codes read the English table.
        key: Catalog key, e.g. ``"question"``.
        **params: ``str.format`` interpolation values.

    Returns:
        The resolved, formatted string.
    """
    return translate(_STRINGS, locale, key, DEFAULT_PDF_LOCALE, **params)


def priority_label(priority: str | None, locale: str) -> str:
    """Priority label in the document language; an unknown value passes through."""
    key = (priority or "").strip().lower()
    table = _PRIORITY_LABELS.get(locale) or _PRIORITY_LABELS[DEFAULT_PDF_LOCALE]
    return table.get(key) or _PRIORITY_LABELS[DEFAULT_PDF_LOCALE].get(key) or (priority or "")


def days_text(count: int, locale: str) -> str:
    """A number of days with the noun in the form the language needs.

    Russian picks between three forms by the last digits (1 день, 3 дня,
    5 дней, 11 дней, 21 день), so the count cannot be glued to one word the
    way English and German allow.

    Args:
        count: The number of days.
        locale: A supported PDF locale.

    Returns:
        The count followed by the noun, e.g. ``"3 days"`` or ``"3 дня"``.
    """
    if locale == "ru":
        tail = abs(count) % 100
        if tail % 10 == 1 and tail != 11:
            noun = "день"
        elif 2 <= tail % 10 <= 4 and not 12 <= tail <= 14:
            noun = "дня"
        else:
            noun = "дней"
    elif locale == "de":
        noun = "Tag" if abs(count) == 1 else "Tage"
    else:
        noun = "day" if abs(count) == 1 else "days"
    return f"{count} {noun}"


def format_date(value: date | datetime | str | None, locale: str) -> str:
    """Render a stored date in the locale's format, or a dash when absent.

    The RFI keeps its dates in three shapes: ``created_at`` is a timestamp,
    ``date_required`` a ``YYYY-MM-DD`` string, and ``responded_at`` /
    ``response_due_date`` either of the two, depending on which code path
    wrote them. Only the calendar date is printed. A value that parses as
    neither is returned as stored, so a malformed row still renders.

    Args:
        value: The stored value.
        locale: A supported PDF locale.

    Returns:
        The formatted date, the raw value when unparseable, or ``"-"``.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return "-"
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text).date()
        except ValueError:
            try:
                parsed = date.fromisoformat(text[:10])
            except ValueError:
                return text
    return parsed.strftime(tr(locale, "date_format"))


def rfi_pdf_filename(rfi_number: str | None) -> str:
    """Download filename for one RFI, e.g. ``RFI-007.pdf``.

    Everything outside letters, digits, dot, dash and underscore becomes an
    underscore, so a number typed with a slash or a space still gives a name
    every operating system accepts.
    """
    stem = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in (rfi_number or "").strip())
    return f"{stem or 'rfi'}.pdf"
