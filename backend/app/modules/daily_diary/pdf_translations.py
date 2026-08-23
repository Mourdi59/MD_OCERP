# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""String catalog and locale resolution for the daily-diary PDF export.

The diary PDF used to be hardcoded English and printed the raw
``weather_summary`` dictionary keys (``temp_c: 20 · conditions: clear``).
This module gives the renderer a self-contained translations table -
English (source of truth) plus German - and the small helpers the router
and the renderer need to pick and apply a locale.

* **Self-contained per-package bundle**, like
  :mod:`app.core.validation.messages`: strings live next to the code that
  renders them, and no global i18n catalog is touched.
* **Shared resolution**, from :mod:`app.core.document_locale`: an explicit
  ``?locale=`` query parameter wins, otherwise the first
  ``Accept-Language`` tag whose primary subtag this table has, otherwise
  ``"en"``. The middleware's context locale is deliberately not reused
  here, so the PDF language depends only on what this table can render.

The strings are local; the rule that picks between them is not. It used to
be, copied verbatim into the e-invoice bundle, which is how the two drifted
into being separately maintained copies of the same three functions.

Because this table is narrower than the interface's locale list, a reader
can ask for a language it does not hold. The route serving the PDF must
then declare the language it actually rendered in ``Content-Language`` -
see :mod:`app.core.document_locale`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.document_locale import (
    normalize_document_locale,
    resolve_document_locale,
    translate,
)

__all__ = [
    "DEFAULT_PDF_LOCALE",
    "SUPPORTED_PDF_LOCALES",
    "diary_pdf_filename",
    "entry_type_label",
    "fmt_number",
    "format_iso_date",
    "normalize_pdf_locale",
    "resolve_pdf_locale",
    "status_label",
    "tr",
    "weather_summary_text",
]

DEFAULT_PDF_LOCALE = "en"

#: Languages the diary PDF can actually render. Extend the tables below
#: when adding a language; anything else falls back to English.
SUPPORTED_PDF_LOCALES: tuple[str, ...] = ("en", "de")

# ── Catalog ──────────────────────────────────────────────────────────────
# The English values are byte-for-byte the literals the renderer shipped
# with, so an English export stays identical to the pre-i18n output.

_STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "doc_title": "Daily Site Diary",
        "overview": "Overview",
        "site_supervisor": "Site supervisor",
        "not_recorded": "Not recorded",
        "labour_on_site": "Labour on site",
        "equipment_on_site": "Equipment on site",
        "completeness": "Completeness",
        "weather": "Weather",
        "weather_time": "Time",
        "weather_source": "Source",
        "weather_temp": "Temp (C)",
        "weather_wind": "Wind (km/h)",
        "weather_precip": "Precip (mm)",
        "weather_conditions": "Conditions",
        "weather_empty": "No weather recorded for this day.",
        "site_record": "Site record",
        "entries_empty": "No entries recorded for this diary.",
        "notes": "Notes",
        "notes_empty": "No additional notes.",
        "footer_supervisor": "Supervisor: {name}",
        "footer_supervisor_missing": "Site supervisor: not recorded",
        "footer_generated": "Generated: {timestamp}",
        "footer_page": "Page {page}",
        "filename_prefix": "diary",
        "date_format": "%Y-%m-%d",
        "datetime_format": "%Y-%m-%d %H:%M UTC",
        "summary_wind": "wind {value} km/h",
        "summary_precipitation": "precipitation {value} mm",
        "summary_humidity": "humidity {value} %",
    },
    "de": {
        "doc_title": "Bautagebuch",
        "overview": "Übersicht",
        "site_supervisor": "Bauleiter",
        "not_recorded": "Nicht erfasst",
        "labour_on_site": "Arbeitskräfte vor Ort",
        "equipment_on_site": "Geräte vor Ort",
        "completeness": "Vollständigkeit",
        "weather": "Wetter",
        "weather_time": "Uhrzeit",
        "weather_source": "Quelle",
        "weather_temp": "Temp (°C)",
        "weather_wind": "Wind (km/h)",
        "weather_precip": "Niederschlag (mm)",
        "weather_conditions": "Bedingungen",
        "weather_empty": "Für diesen Tag wurde kein Wetter erfasst.",
        "site_record": "Tagesprotokoll",
        "entries_empty": "Für dieses Bautagebuch wurden keine Einträge erfasst.",
        "notes": "Notizen",
        "notes_empty": "Keine weiteren Notizen.",
        "footer_supervisor": "Bauleiter: {name}",
        "footer_supervisor_missing": "Bauleiter: nicht erfasst",
        "footer_generated": "Erstellt: {timestamp}",
        "footer_page": "Seite {page}",
        "filename_prefix": "bautagebuch",
        "date_format": "%d.%m.%Y",
        "datetime_format": "%d.%m.%Y %H:%M UTC",
        "summary_wind": "Wind {value} km/h",
        "summary_precipitation": "Niederschlag {value} mm",
        "summary_humidity": "Luftfeuchte {value} %",
    },
}

# Section labels for the grouped diary-entry types declared in schemas.py.
# English mirrors the original hardcoded set; unknown types are humanised
# by :func:`entry_type_label` instead of leaking a snake_case token.
_ENTRY_TYPE_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "visitor": "Visitors",
        "event": "Events",
        "delivery": "Materials delivered",
        "completion": "Work performed",
        "incident_summary": "Safety and incidents",
        "inspection_summary": "Inspections",
        "photo_note": "Photo notes",
        "general": "General notes",
    },
    "de": {
        "visitor": "Besucher",
        "event": "Ereignisse",
        "delivery": "Materiallieferungen",
        "completion": "Ausgeführte Arbeiten",
        "incident_summary": "Sicherheit und Vorfälle",
        "inspection_summary": "Prüfungen",
        "photo_note": "Fotonotizen",
        "general": "Allgemeine Notizen",
    },
}

# Status chip labels for the DIARY_STATUSES lifecycle (open -> closed ->
# signed -> archived). The renderer upper-cases them, so the English set
# reproduces the previous ``status.upper()`` output exactly. German uses
# the "unterzeichnen" family per the module's settled vocabulary.
_STATUS_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "open": "Open",
        "closed": "Closed",
        "signed": "Signed",
        "archived": "Archived",
    },
    "de": {
        "open": "Offen",
        "closed": "Geschlossen",
        "signed": "Unterzeichnet",
        "archived": "Archiviert",
    },
}

# Human labels for the weather condition codes stored in
# ``weather_summary["conditions"]``. Covers the full code set from
# ``daily_diary.intl._WEATHER_CONDITION_LABELS`` plus the shorthand codes
# the demo data uses ("rain", "cloudy", "snow"). Lower-case where the
# label sits mid-sentence ("20 °C, clear"); German nouns keep their
# capital as German requires.
_CONDITION_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "clear": "clear",
        "mainly_clear": "mainly clear",
        "partly_cloudy": "partly cloudy",
        "cloudy": "cloudy",
        "overcast": "overcast",
        "fog": "fog",
        "fog_rime": "freezing fog",
        "drizzle_light": "light drizzle",
        "drizzle_moderate": "moderate drizzle",
        "drizzle_dense": "heavy drizzle",
        "rain": "rain",
        "rain_light": "light rain",
        "rain_moderate": "moderate rain",
        "rain_heavy": "heavy rain",
        "freezing_rain_light": "light freezing rain",
        "freezing_rain_heavy": "heavy freezing rain",
        "snow": "snow",
        "snow_light": "light snow",
        "snow_moderate": "moderate snow",
        "snow_heavy": "heavy snow",
        "rain_showers_light": "light rain showers",
        "rain_showers_moderate": "moderate rain showers",
        "rain_showers_violent": "violent rain showers",
        "snow_showers_light": "light snow showers",
        "snow_showers_heavy": "heavy snow showers",
        "thunderstorm": "thunderstorm",
        "thunderstorm_hail_light": "thunderstorm with light hail",
        "thunderstorm_hail_heavy": "thunderstorm with heavy hail",
    },
    "de": {
        "clear": "klar",
        "mainly_clear": "überwiegend klar",
        "partly_cloudy": "wechselnd bewölkt",
        "cloudy": "bewölkt",
        "overcast": "bedeckt",
        "fog": "Nebel",
        "fog_rime": "gefrierender Nebel",
        "drizzle_light": "leichter Nieselregen",
        "drizzle_moderate": "mäßiger Nieselregen",
        "drizzle_dense": "starker Nieselregen",
        "rain": "Regen",
        "rain_light": "leichter Regen",
        "rain_moderate": "mäßiger Regen",
        "rain_heavy": "starker Regen",
        "freezing_rain_light": "leichter gefrierender Regen",
        "freezing_rain_heavy": "starker gefrierender Regen",
        "snow": "Schnee",
        "snow_light": "leichter Schneefall",
        "snow_moderate": "mäßiger Schneefall",
        "snow_heavy": "starker Schneefall",
        "rain_showers_light": "leichte Regenschauer",
        "rain_showers_moderate": "mäßige Regenschauer",
        "rain_showers_violent": "heftige Regenschauer",
        "snow_showers_light": "leichte Schneeschauer",
        "snow_showers_heavy": "starke Schneeschauer",
        "thunderstorm": "Gewitter",
        "thunderstorm_hail_light": "Gewitter mit leichtem Hagel",
        "thunderstorm_hail_heavy": "Gewitter mit starkem Hagel",
    },
}

# ── Locale resolution ────────────────────────────────────────────────────


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

    See :func:`app.core.document_locale.resolve_document_locale` for the
    rule. When this returns ``"en"`` for a reader who asked for something
    else, the route must declare ``Content-Language: en`` so the fallback
    is visible rather than silent.

    Args:
        locale_param: Explicit ``?locale=`` query value, if any.
        accept_language: Raw ``Accept-Language`` header value, if any.

    Returns:
        A member of :data:`SUPPORTED_PDF_LOCALES`.
    """
    return resolve_document_locale(locale_param, accept_language, SUPPORTED_PDF_LOCALES, DEFAULT_PDF_LOCALE)


# ── Catalog lookups ──────────────────────────────────────────────────────


def tr(locale: str, key: str, **params: Any) -> str:
    """Resolve ``key`` for ``locale`` with English fallback.

    Same fallback chain as the validation-messages bundle: requested
    locale -> ``en`` -> the key itself (a bug, but never a crash).

    Args:
        locale: A PDF locale code; unknown codes read the English table.
        key: Catalog key, e.g. ``"overview"``.
        **params: ``str.format`` interpolation values.

    Returns:
        The resolved, formatted string.
    """
    return translate(_STRINGS, locale, key, DEFAULT_PDF_LOCALE, **params)


def entry_type_label(entry_type: str, locale: str) -> str:
    """Section label for a diary entry type, never a raw snake_case token."""
    table = _ENTRY_TYPE_LABELS.get(locale) or {}
    label = table.get(entry_type) or _ENTRY_TYPE_LABELS[DEFAULT_PDF_LOCALE].get(entry_type)
    return label or entry_type.replace("_", " ").title()


def status_label(status: str | None, locale: str) -> str:
    """Status chip label; unknown statuses pass through as stored."""
    normalized = (status or "open").strip().lower()
    table = _STATUS_LABELS.get(locale) or {}
    label = table.get(normalized) or _STATUS_LABELS[DEFAULT_PDF_LOCALE].get(normalized)
    return label or (status or "open")


def diary_pdf_filename(stem: str, locale: str) -> str:
    """Download filename for a diary export, e.g. ``bautagebuch-2026-04-10.pdf``."""
    return f"{tr(normalize_pdf_locale(locale), 'filename_prefix')}-{stem}.pdf"


# ── Value formatting ─────────────────────────────────────────────────────


def fmt_number(value: Any, decimals: int = 1) -> str:
    """Format a numeric value (int / float / Decimal) for display.

    Args:
        value: The value to format. ``None`` renders as a dash.
        decimals: Number of decimal places to keep.

    Returns:
        A formatted string, or ``"-"`` when the value is missing or not
        numeric.
    """
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number == int(number):
        return str(int(number))
    return f"{number:.{decimals}f}"


def format_iso_date(value: str, locale: str) -> str:
    """Render an ISO ``YYYY-MM-DD`` string in the locale's date format.

    The English format is ISO itself, so English output is unchanged.
    Non-ISO input is returned as-is - the diary stores dates as ISO
    strings, but the renderer must never crash on a malformed row.

    Args:
        value: The stored date string.
        locale: A supported PDF locale.

    Returns:
        The formatted date, or ``value`` unchanged when unparseable.
    """
    try:
        parsed = date.fromisoformat((value or "").strip())
    except ValueError:
        return value
    return parsed.strftime(tr(locale, "date_format"))


# ── Weather summary ──────────────────────────────────────────────────────

_TEMP_KEYS = ("temp_c", "temperature_c")
_CONDITION_KEYS = ("conditions", "condition")
_WIND_KEYS = ("wind_kmh", "wind_speed_kmh")
_PRECIP_KEYS = ("precipitation_mm", "precip_mm")
_HUMIDITY_KEYS = ("humidity_pct", "humidity")


def _first_present(summary: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-empty value among ``keys``, else ``None``."""
    for key in keys:
        value = summary.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def weather_summary_text(summary: dict[str, Any], locale: str) -> str:
    """Render a ``weather_summary`` snapshot as a human sentence fragment.

    ``{"temp_c": 20, "conditions": "clear"}`` becomes ``"20 °C, clear"``
    (``"20 °C, klar"`` in German). Known keys render in a fixed order;
    anything else is appended as a humanised ``label: value`` pair, so a
    raw ``snake_case`` key never reaches the document.

    Args:
        summary: The diary's ``weather_summary`` JSON snapshot.
        locale: A supported PDF locale.

    Returns:
        The joined fragment, or ``""`` when nothing is renderable.
    """
    parts: list[str] = []
    consumed: set[str] = set()

    temp = _first_present(summary, _TEMP_KEYS)
    if temp is not None:
        text = fmt_number(temp)
        if text != "-":
            parts.append(f"{text} °C")
            consumed.update(_TEMP_KEYS)

    condition = _first_present(summary, _CONDITION_KEYS)
    if condition is not None:
        code = str(condition).strip()
        table = _CONDITION_LABELS.get(locale) or {}
        label = table.get(code.lower()) or _CONDITION_LABELS[DEFAULT_PDF_LOCALE].get(code.lower())
        # Free-text conditions ("Partly cloudy, mild") pass through as
        # written; coded ones only lose their underscores.
        parts.append(label or code.replace("_", " "))
        consumed.update(_CONDITION_KEYS)

    for keys, template_key in (
        (_WIND_KEYS, "summary_wind"),
        (_PRECIP_KEYS, "summary_precipitation"),
        (_HUMIDITY_KEYS, "summary_humidity"),
    ):
        value = _first_present(summary, keys)
        if value is not None:
            text = fmt_number(value)
            if text != "-":
                parts.append(tr(locale, template_key, value=text))
                consumed.update(keys)

    for key, value in summary.items():
        if key in consumed or value is None or str(value).strip() == "":
            continue
        label = str(key).replace("_", " ").strip()
        parts.append(f"{label}: {value}")

    return ", ".join(parts)
