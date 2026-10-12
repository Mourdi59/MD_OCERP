# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Locale-scoped message bundle for the plant register.

Same pattern as the funding module: one JSON file per interface language,
resolved through the shared :class:`~app.core.validation.messages.MessageBundle`
so a regional code such as ``pt-BR`` falls back through its base language and
finally to English.
"""

from __future__ import annotations

from pathlib import Path

from app.core.validation.messages import MessageBundle

DEFAULT_LOCALE = "en"
_MESSAGES_DIR = Path(__file__).parent
_bundle = MessageBundle(messages_dir=_MESSAGES_DIR)


def translate(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """Resolve a plant register message key for ``locale`` with ``str.format`` params."""
    return _bundle.translate(key, locale=locale, **params)


def is_key_present(key: str, locale: str = DEFAULT_LOCALE) -> bool:
    """Return ``True`` if ``key`` exists in ``locale`` without any fallback."""
    return _bundle.is_key_present(key, locale=locale)


def available_locales() -> list[str]:
    """List locales currently loaded into the plant register bundle."""
    return _bundle.available_locales()


def written_locale(locale: str | None) -> str:
    """The language a document rendered for ``locale`` is actually written in."""
    have = set(available_locales())
    for candidate in (locale or "", (locale or "").replace("_", "-").split("-")[0]):
        if candidate in have:
            return candidate
    return DEFAULT_LOCALE


def reload_bundle() -> None:
    """Force a cache refresh (test helper)."""
    _bundle.reload()


__all__ = ["available_locales", "is_key_present", "reload_bundle", "translate"]
