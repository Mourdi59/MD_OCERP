# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Locale-scoped message bundle for the project handbook module (same pattern as the engineering brief)."""

from __future__ import annotations

from pathlib import Path

from app.core.validation.messages import MessageBundle

DEFAULT_LOCALE = "en"
_MESSAGES_DIR = Path(__file__).parent
_bundle = MessageBundle(messages_dir=_MESSAGES_DIR)


def translate(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """Resolve a project handbook message key for ``locale`` with ``str.format`` params."""
    return _bundle.translate(key, locale=locale, **params)


def is_key_present(key: str, locale: str = DEFAULT_LOCALE) -> bool:
    """Return ``True`` if ``key`` exists in ``locale`` without any fallback."""
    return _bundle.is_key_present(key, locale=locale)


def available_locales() -> list[str]:
    """List locales currently loaded into the bundle."""
    return _bundle.available_locales()


def reload_bundle() -> None:
    """Force a cache refresh (test helper)."""
    _bundle.reload()


__all__ = ["available_locales", "is_key_present", "reload_bundle", "translate"]
