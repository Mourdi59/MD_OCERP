# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The funding findings say the same thing in every locale the bundle ships.

A missing message does not raise. ``translate`` falls back to English and then
to the raw key, so a hole shows up as an English sentence inside a German
report, or as ``funding.own_share_is_covered.fail`` printed to a funding
officer. Neither is visible to any other gate we own, because there is no
value to compare against.

The keys are read out of the rule source rather than listed here, so a rule
that starts emitting a sixth message is covered the day it is written instead
of the day somebody remembers to extend this file.
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

import pytest

from app.core.validation import messages as message_bundle
from app.core.validation.messages import is_key_present, translate
from app.modules.funding import validators as funding_validators

# Both are found through the modules themselves rather than through a relative
# path, so the tests pass wherever pytest was started from.
MESSAGES_DIR = pathlib.Path(str(message_bundle.__file__)).parent
VALIDATORS = pathlib.Path(str(funding_validators.__file__))

#: The locales the self-contained validation bundle ships. This is a different
#: and much smaller set than the front end's locales, on purpose: these are
#: rule messages, not interface strings.
SHIPPED_LOCALES = ["en", "de", "es", "ru"]

#: Substituted into the one message key the rules build at runtime.
FAULTS = ["before", "after", "spans"]


def message_keys() -> set[str]:
    """Every ``funding.`` message key the rule source can ask for.

    Walks the syntax tree rather than grepping, because a call spread over
    four lines is invisible to a single-line pattern and that is exactly how
    these calls are formatted. The one key assembled from an f-string is
    expanded over the three values its branch can produce.
    """
    tree = ast.parse(VALIDATORS.read_text("utf-8"))

    # The literal halves of an f-string are Constant nodes in their own right,
    # so walking the tree would otherwise collect the bare prefix alongside the
    # three keys that prefix actually produces, and then report the prefix as a
    # missing translation in every locale.
    literal_halves = {
        id(part)
        for node in ast.walk(tree)
        if isinstance(node, ast.JoinedStr)
        for part in ast.walk(node)
        if isinstance(part, ast.Constant)
    }

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            prefix = "".join(
                part.value for part in node.values if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if prefix.startswith("funding."):
                found.update(prefix + fault for fault in FAULTS)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in literal_halves:
            if node.value.startswith("funding."):
                found.add(node.value)
    # ``funding`` on its own is the rule set name, and the rule ids are not
    # message keys. Both are three segments short of a message.
    return {key for key in found if key.count(".") >= 2}


def test_the_source_really_yields_the_keys_this_file_then_checks() -> None:
    """A scanner that quietly finds nothing would make every test below vacuous."""
    keys = message_keys()
    assert len(keys) >= 15, sorted(keys)
    assert "funding.measure_starts_after_application.fail" in keys
    assert "funding.own_share_is_covered.suggestion" in keys
    # The runtime-assembled key, expanded.
    for fault in FAULTS:
        assert f"funding.costs_fall_in_the_award_period.{fault}" in keys


@pytest.mark.parametrize("locale", SHIPPED_LOCALES)
def test_every_message_the_rules_can_ask_for_exists_in_every_shipped_locale(locale: str) -> None:
    missing = sorted(key for key in message_keys() if not is_key_present(key, locale))
    assert missing == [], f"{locale} answers none of these: {missing}"


def test_the_four_bundles_carry_exactly_the_same_funding_keys() -> None:
    """One locale gaining a key alone is how a translation silently drifts."""
    bundles = {}
    for locale in SHIPPED_LOCALES:
        data = json.loads((MESSAGES_DIR / f"{locale}.json").read_text("utf-8"))
        funding = data.get("funding") or {}
        bundles[locale] = {f"{group}.{leaf}" for group, leaves in funding.items() for leaf in leaves}

    reference = bundles["en"]
    assert reference, "en.json carries no funding messages at all"
    for locale in SHIPPED_LOCALES[1:]:
        assert bundles[locale] == reference, f"{locale} differs by {bundles[locale] ^ reference}"


@pytest.mark.parametrize("locale", SHIPPED_LOCALES)
def test_no_funding_message_is_left_as_its_english_placeholder(locale: str) -> None:
    """Every message is a real sentence, not a key and not an empty string."""
    for key in sorted(message_keys()):
        rendered = translate(key, locale=locale)
        assert rendered != key, f"{locale} falls through on {key}"
        assert rendered.strip(), f"{locale} answers {key} with whitespace"


def test_the_translated_messages_keep_the_placeholders_the_rules_fill() -> None:
    """A dropped placeholder loses the date or amount that makes a finding actionable."""
    for key in sorted(message_keys()):
        expected = set(re.findall(r"{(\w+)}", translate(key, locale="en")))
        for locale in SHIPPED_LOCALES[1:]:
            actual = set(re.findall(r"{(\w+)}", translate(key, locale=locale)))
            assert actual == expected, f"{locale} on {key}: expected {sorted(expected)}, got {sorted(actual)}"


def test_the_german_wording_uses_the_domains_own_terms() -> None:
    """German funding administration has settled words, and a literal translation is wrong.

    These are the terms a Zuwendungsempfaenger reads on the notice itself. A
    finding that invents its own vocabulary reads as a software message rather
    than as something the authority would recognise, and the reader cannot map
    it onto the paperwork in front of them.
    """
    german = " ".join(translate(key, locale="de") for key in sorted(message_keys()))
    for term in ["Bewilligungszeitraum", "Eigenanteil", "Verwendungsnachweis", "Beihilfeintensit"]:
        assert term in german, f"the German bundle never says {term}"
