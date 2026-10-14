# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Every finding the economics module can raise has a validation rule and a message in both languages."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from app.modules.economics import rules
from app.modules.economics.seed import PROFILES, round_up, split
from app.modules.economics.validators import ECONOMICS_RULE_SET, ECONOMICS_RULES

MESSAGES = Path(__file__).resolve().parents[2] / "app" / "modules" / "economics" / "messages"


def _load(lang: str) -> dict[str, str]:
    return json.loads((MESSAGES / f"{lang}.json").read_text(encoding="utf-8"))


def _placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", text))


def test_every_finding_code_has_exactly_one_rule() -> None:
    ids = sorted(r.rule_id for r in ECONOMICS_RULES)
    assert ids == sorted(f"economics.{code}" for code in rules.CODES)
    assert ECONOMICS_RULE_SET == "economics"


def test_every_rule_and_error_has_a_message_in_both_languages() -> None:
    en, de = _load("en"), _load("de")
    assert set(en) == set(de)
    for code in rules.CODES:
        for part in ("fail", "suggestion"):
            key = f"economics.rules.{code}.{part}"
            assert en.get(key), key
            assert de.get(key), key
            assert _placeholders(en[key]) == _placeholders(de[key]), key


def test_severity_follows_the_code_table() -> None:
    by_id = {r.rule_id: r for r in ECONOMICS_RULES}
    for code, severity in rules.CODES.items():
        assert by_id[f"economics.{code}"].severity.value == severity, code


def test_rounding_up_to_a_step_never_goes_below_the_amount() -> None:
    assert round_up(Decimal("1")) == Decimal("100000")
    assert round_up(Decimal("100000")) == Decimal("100000")
    assert round_up(Decimal("100000.01")) == Decimal("200000")
    assert round_up(Decimal("0")) == Decimal("0")


def test_a_split_adds_up_exactly_and_the_last_part_takes_the_remainder() -> None:
    parts = split(Decimal("100.00"), 3)
    assert parts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(split(Decimal("59200000.37"), 7), Decimal(0)) == Decimal("59200000.37")


def test_each_demo_profile_ends_with_the_exact_remainder_as_its_last_source() -> None:
    for demo_id, profile in PROFILES.items():
        assert profile.sources[-1].share is None, demo_id
        assert all(s.share is not None for s in profile.sources[:-1]), demo_id
        shares = sum(Decimal(s.share) for s in profile.sources[:-1] if s.share)
        assert Decimal(0) < shares < Decimal(1), demo_id
        assert all(s.due for s in profile.sources), demo_id
