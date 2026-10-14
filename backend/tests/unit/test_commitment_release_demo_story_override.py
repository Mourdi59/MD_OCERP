"""Demo story override of the commitment release seeder: pure validation and the shipped Ludwigsburg file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.commitment_release import seed

REPO = Path(__file__).resolve().parents[3]
DEMO = REPO / "packs/eleven-areas-framework/src/openconstructionerp_eleven_areas_framework/demo"
STORY_FILE = DEMO / "school-ludwigsburg-commitment_release.json"


@pytest.fixture(scope="module")
def shipped() -> dict:
    return json.loads(STORY_FILE.read_text(encoding="utf-8"))


def test_no_story_changes_nothing() -> None:
    assert seed.resolve_story(None) == {}
    assert seed.resolve_story({}) == {}


def test_valid_keys_pass_and_bad_ones_are_dropped() -> None:
    story = {
        "works": {"title": "Lot 1", "amount": "100", "lead_time_days": 3, "bogus": "x"},
        "slot": {"amount": "0", "order_signed_pct": "1.5", "title": {"en": "T", "de": "U"}},
        "design": "not a section",
        "contingency": {"amount": "NaN", "title": "  "},
    }
    out = seed.resolve_story(story, "de")
    assert out["works"] == {"title": "Lot 1", "amount": "100", "lead_time_days": 3}
    assert out["slot"] == {"title": "U"}
    assert "design" not in out
    assert out["contingency"] == {}


def test_int_keys_refuse_bool_and_negative() -> None:
    out = seed.resolve_story(
        {"slot": {"order_signed_days": True, "manufacturing_started_days": -2, "lead_time_days": 9}}
    )
    assert out["slot"] == {"lead_time_days": 9}


def test_shipped_story_is_complete_and_valid(shipped: dict) -> None:
    for locale in ("en", "de"):
        out = seed.resolve_story(shipped, locale)
        for section, spec in seed._SECTIONS.items():
            kept = set(out.get(section, {}))
            given = set(shipped.get(section, {}))
            assert kept == given, f"{section}: dropped {given - kept}"
            assert given <= set(spec), f"{section}: unknown keys {given - set(spec)}"


def test_slot_story_agrees_with_plant_register_story(shipped: dict) -> None:
    register = json.loads((DEMO / "school-ludwigsburg-plant_register.json").read_text(encoding="utf-8"))
    items = {i["code"]: i for i in register["items"]}
    slot = shipped["slot"]
    # The commitment links to a plant item that exists in the register story and holds a free slot.
    linked = items[slot["plant_item"]]
    assert linked.get("slot") == "held"
    assert seed.DEMO_PLANT_LINKS[seed.DEMO_SLOT_ITEM_CODE] == "PL-001"
    held = register["slots"]["held"]
    assert slot["order_signed_days"] == held["convert_by_days"]
    assert slot["manufacturing_started_days"] == held["slot_from_days"]
    assert "heat pump" in slot["title"].lower() and linked["class"] == "heat_pump"


def test_shipped_story_text_hygiene() -> None:
    text = STORY_FILE.read_text(encoding="utf-8")
    assert "\u2014" not in text and "\u2013" not in text
