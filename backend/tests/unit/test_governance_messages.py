"""Governance backend messages: every shipped locale answers every English key with the same placeholders."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.modules.project_governance import messages

_DIR = Path(messages.__file__).resolve().parent
_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def _flat(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out |= _flat(value, f"{path}.")
        else:
            out[path] = value
    return out


def _load(locale: str) -> dict[str, str]:
    return _flat(json.loads((_DIR / f"{locale}.json").read_text(encoding="utf-8")))


_LOCALES = sorted(p.stem for p in _DIR.glob("*.json") if p.stem != "en")


def test_german_is_shipped() -> None:
    assert "de" in _LOCALES


@pytest.mark.parametrize("locale", _LOCALES)
def test_locale_has_exactly_the_english_keys(locale: str) -> None:
    en, other = _load("en"), _load(locale)
    assert sorted(set(en) - set(other)) == []
    assert sorted(set(other) - set(en)) == []


@pytest.mark.parametrize("locale", _LOCALES)
def test_locale_keeps_placeholders_and_translates(locale: str) -> None:
    en, other = _load("en"), _load(locale)
    for key, text in en.items():
        assert sorted(_PLACEHOLDER.findall(other[key])) == sorted(_PLACEHOLDER.findall(text)), key
        assert other[key].strip(), key
