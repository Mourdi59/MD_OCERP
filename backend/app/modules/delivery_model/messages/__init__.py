# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Locale-scoped message bundle for the delivery model.

Same pattern as the funding module: one JSON file per interface language,
resolved through the shared :class:`~app.core.validation.messages.MessageBundle`
so a regional code such as ``pt-BR`` falls back through its base language and
finally to English.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.validation.messages import MessageBundle

DEFAULT_LOCALE = "en"
_MESSAGES_DIR = Path(__file__).parent
_bundle = MessageBundle(messages_dir=_MESSAGES_DIR)


def translate(key: str, locale: str = DEFAULT_LOCALE, **params: object) -> str:
    """Resolve a delivery model message key for ``locale`` with ``str.format`` params."""
    return _bundle.translate(key, locale=locale, **params)


def label_texts(key: str | None, labels: dict[str, str] | None, locale: str = DEFAULT_LOCALE) -> dict[str, str] | None:
    """The ``text`` of a ``{key, text}`` catalogue label for ``locale``; see ``MessageBundle.label_texts``."""
    return _bundle.label_texts(key, labels, locale=locale)


def is_key_present(key: str, locale: str = DEFAULT_LOCALE) -> bool:
    """Return ``True`` if ``key`` exists in ``locale`` without any fallback."""
    return _bundle.is_key_present(key, locale=locale)


def available_locales() -> list[str]:
    """List locales currently loaded into the delivery model bundle."""
    return _bundle.available_locales()


def reload_bundle() -> None:
    """Force a cache refresh (test helper)."""
    _bundle.reload()


__all__ = ["available_locales", "is_key_present", "reload_bundle", "translate"]


def with_label_texts(node: Any, locale: str = DEFAULT_LOCALE) -> Any:
    """A catalogue body with every shipped ``name_key`` item given the ``labels`` text for ``locale``.

    Items that already carry ``labels`` (tenant catalogues) are left as they are, and so is an item
    whose key this bundle does not know: the screen then resolves the key itself.
    """
    if isinstance(node, list):
        return [with_label_texts(v, locale) for v in node]
    if not isinstance(node, dict):
        return node
    out = {k: with_label_texts(v, locale) for k, v in node.items()}
    key = out.get("name_key")
    if isinstance(key, str) and key and "labels" in out and not out["labels"]:
        out["labels"] = label_texts(key, None, locale)
    return out
