# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The staffing demo seed applies a per-project story on top of its defaults, key by key."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.modules.staffing import seed

_STORY = (
    Path(__file__).resolve().parents[3]
    / "packs/eleven-areas-framework/src/openconstructionerp_eleven_areas_framework/demo"
    / "school-ludwigsburg-staffing.json"
)
_DE = Path(seed.__file__).parent / "catalogues" / "de.json"


def test_no_story_keeps_defaults() -> None:
    d = seed.POSITIONS_BEFORE_CONSTRUCTION
    assert seed.story_positions({}, d) == d
    assert seed.story_handovers({}, "en", seed.HANDOVERS) == seed.HANDOVERS


def test_bad_rows_are_dropped_quietly(caplog) -> None:
    story = {
        "positions": [{"role": "x", "phase": "nope", "entry": 1}, {"role": "y", "phase": "execution", "entry": "1"}],
        "handovers": [{"from": "a", "to": "b", "overlap_days": 0, "scope": "s"}, 3],
        "expiring": [{"role": "a"}, "x"],
    }
    with caplog.at_level(logging.INFO):
        d = seed.POSITIONS_BEFORE_CONSTRUCTION
        assert seed.story_positions(story, d) == d
        assert seed.story_handovers(story, "en", seed.HANDOVERS) == seed.HANDOVERS
        assert seed.story_pairs(story, "expiring") == []
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_valid_rows_replace() -> None:
    story = {"positions": [{"role": "site_manager", "phase": "execution", "entry": 5, "exit": None}]}
    assert seed.story_positions(story, ()) == (("site_manager", "execution", 5, None, "open"),)


def test_shipped_school_story_uses_real_catalogue_codes() -> None:
    story = json.loads(_STORY.read_text(encoding="utf-8"))
    cat = json.loads(_DE.read_text(encoding="utf-8"))
    roles = {r["code"] for r in cat["roles"]}
    kinds = {k["code"] for k in cat["document_kinds"]}
    rows = seed.story_positions(story, ())
    assert len(rows) == len(story["positions"])
    assert {r[0] for r in rows} <= roles
    assert set(story["filled"]) <= {r[0] for r in rows}
    for key in ("expiring", "missing", "waived"):
        pairs = seed.story_pairs(story, key)
        assert len(pairs) == len(story[key])
        assert {r for r, _, _ in pairs} <= {r[0] for r in rows}
        assert {k for _, k, _ in pairs} <= kinds
    handovers = seed.story_handovers(story, "en", ())
    assert len(handovers) == len(story["handovers"])
    assert {h[0] for h in handovers} <= set(story["filled"])
    assert {h[1] for h in handovers} <= {r[0] for r in rows}
    assert "\u2014" not in _STORY.read_text(encoding="utf-8")
