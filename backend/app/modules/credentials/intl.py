# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Localized labels for the credentials registry vocabularies.

Pure, dependency-free label lookups for the credential-type and status code
sets, so the ``/meta`` endpoint can hand the UI pre-translated pickers. English
is the fallback for any locale or code not in the table - a missing translation
degrades to a readable English label, never a raw code. Mirrors the house style
of :mod:`app.modules.approval_routes.intl`.
"""

from __future__ import annotations

# Base language of a locale string ("de-AT" -> "de"). Kept tiny and pure.
_SUPPORTED = ("en", "de", "es", "ru")


def _normalize_locale(locale: str | None) -> str:
    if not locale:
        return "en"
    base = locale.replace("_", "-").split("-", 1)[0].lower()
    return base if base in _SUPPORTED else "en"


_TYPE_LABELS: dict[str, dict[str, str]] = {
    "professional_license": {
        "en": "Professional licence",
        "de": "Berufszulassung",
        "es": "Licencia profesional",
        "ru": "Профессиональная лицензия",
    },
    "certification": {
        "en": "Certification",
        "de": "Zertifizierung",
        "es": "Certificación",
        "ru": "Сертификация",
    },
    "statutory_membership": {
        "en": "Statutory membership",
        "de": "Gesetzliche Mitgliedschaft",
        "es": "Membresía obligatoria",
        "ru": "Обязательное членство",
    },
    "professional_indemnity": {
        "en": "Professional indemnity",
        "de": "Berufshaftpflicht",
        "es": "Seguro de responsabilidad profesional",
        "ru": "Профессиональная ответственность",
    },
    "registration": {
        "en": "Registration",
        "de": "Registrierung",
        "es": "Registro",
        "ru": "Регистрация",
    },
    "training": {
        "en": "Training record",
        "de": "Schulungsnachweis",
        "es": "Registro de formación",
        "ru": "Обучение",
    },
    "accreditation": {
        "en": "Accreditation",
        "de": "Akkreditierung",
        "es": "Acreditación",
        "ru": "Аккредитация",
    },
    "employment_contract": {
        "en": "Employment contract",
        "de": "Arbeitsvertrag",
        "es": "Contrato de trabajo",
        "ru": "Трудовой договор",
    },
    "work_permit": {
        "en": "Work permit",
        "de": "Arbeitserlaubnis",
        "es": "Permiso de trabajo",
        "ru": "Разрешение на работу",
    },
    "residence_permit": {
        "en": "Residence permit",
        "de": "Aufenthaltstitel",
        "es": "Permiso de residencia",
        "ru": "Вид на жительство",
    },
    "identity_document": {
        "en": "Passport or identity document",
        "de": "Reisepass oder Ausweis",
        "es": "Pasaporte o documento de identidad",
        "ru": "Паспорт или удостоверение личности",
    },
    "visa": {
        "en": "Visa",
        "de": "Visum",
        "es": "Visado",
        "ru": "Виза",
    },
    "occupational_health": {
        "en": "Occupational health certificate",
        "de": "Arbeitsmedizinische Bescheinigung",
        "es": "Certificado de salud laboral",
        "ru": "Справка медосмотра",
    },
    "right_to_work_check": {
        "en": "Right to work check",
        "de": "Prüfung der Arbeitsberechtigung",
        "es": "Verificación del derecho a trabajar",
        "ru": "Проверка права на работу",
    },
    "posting_certificate": {
        "en": "Posting certificate",
        "de": "Entsendebescheinigung",
        "es": "Certificado de desplazamiento",
        "ru": "Справка о командировании",
    },
    "other": {
        "en": "Other",
        "de": "Sonstige",
        "es": "Otro",
        "ru": "Другое",
    },
}

_STATUS_LABELS: dict[str, dict[str, str]] = {
    "active": {
        "en": "Active",
        "de": "Aktiv",
        "es": "Activa",
        "ru": "Действует",
    },
    "expiring_soon": {
        "en": "Expiring soon",
        "de": "Läuft bald ab",
        "es": "Vence pronto",
        "ru": "Скоро истекает",
    },
    "expired": {
        "en": "Expired",
        "de": "Abgelaufen",
        "es": "Vencida",
        "ru": "Истекла",
    },
    "suspended": {
        "en": "Suspended",
        "de": "Ausgesetzt",
        "es": "Suspendida",
        "ru": "Приостановлена",
    },
    "revoked": {
        "en": "Revoked",
        "de": "Widerrufen",
        "es": "Revocada",
        "ru": "Отозвана",
    },
}


def _label(code: str | None, locale: str | None, table: dict[str, dict[str, str]]) -> str:
    loc = _normalize_locale(locale)
    entry = table.get(code or "")
    if entry is None:
        # Unknown code: humanise it rather than leak the raw token.
        return (code or "").replace("_", " ").title()
    return entry.get(loc) or entry.get("en") or (code or "")


def describe_type(code: str | None, locale: str | None = None) -> str:
    """Localized label for a credential-type code."""
    return _label(code, locale, _TYPE_LABELS)


def describe_status(code: str | None, locale: str | None = None) -> str:
    """Localized label for a credential-status code."""
    return _label(code, locale, _STATUS_LABELS)


__all__ = ["describe_status", "describe_type"]
