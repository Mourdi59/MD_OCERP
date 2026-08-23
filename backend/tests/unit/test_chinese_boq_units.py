# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unit vocabulary for Chinese bills of quantities.

A GB/T 50500 bill writes its units as words. ``app.modules.boq.units`` keeps
non-Latin units verbatim rather than folding them to Latin, so those words
reach the validation rules exactly as an estimator typed them - and an
unrecognised unit is skipped, never flagged. A Chinese bill therefore used to
produce no findings rather than wrong ones, which is safe and useless.

These tests pin the three things that were decided when the vocabulary was
extended, because none of them is self-evident from the code:

1. Chinese metric words are in the metric set.
2. Chinese count words are in ``_COUNT_UNITS`` and in NEITHER measurement
   system set. A count of discrete items has no dimension, so it cannot be
   the wrong measurement system; both system sets are only ever read as the
   *wrong* set, and a count unit listed in one would make every count row on
   a project of the other system report a mismatch.
3. The CJK compatibility glyphs are rejected before storage, which is why
   they are deliberately absent from the vocabulary.
"""

from __future__ import annotations

import pytest

from app.core.validation.rules import _IMPERIAL_BOQ_UNITS, _METRIC_BOQ_UNITS
from app.modules.bim_hub.service import _COUNT_UNITS, normalize_unit_token
from app.modules.boq.units import normalise_unit

# Metric units as a Chinese bill writes them. Both readings are listed
# because both are written: the colloquial forms sit beside the SI-derived
# ones and a real bill mixes them.
CHINESE_METRIC_UNITS = (
    "米",
    "平方米",
    "立方米",
    "吨",
    "千克",
    "公斤",
    "毫米",
    "厘米",
    "千米",
    "公里",
    "升",
    "公顷",
)

# Count units. Every one of these is dimensionless.
CHINESE_COUNT_UNITS = (
    "项",
    "台",
    "套",
    "樘",
    "个",
    "块",
    "根",
    "组",
    "座",
    "只",
    "片",
)

# Produced by a Chinese IME left in full-width mode. ``str.lower()`` folds
# full-width capitals to full-width lowercase but never to ASCII, and nothing
# on the write path applies NFKC, so these arrive exactly as typed.
FULLWIDTH_METRIC_UNITS = ("ｍ", "ｍ２", "ｍ３")

# CJK compatibility glyphs. Common in real Chinese documents and rejected by
# the write path, which is the reason they are not in the vocabulary.
CJK_COMPATIBILITY_GLYPHS = ("㎡", "㎥", "㎏", "㎜")


@pytest.mark.parametrize("unit", CHINESE_METRIC_UNITS + FULLWIDTH_METRIC_UNITS)
def test_chinese_metric_units_are_recognised_as_metric(unit: str) -> None:
    assert unit in _METRIC_BOQ_UNITS
    assert unit not in _IMPERIAL_BOQ_UNITS


@pytest.mark.parametrize("unit", CHINESE_COUNT_UNITS)
def test_chinese_count_units_are_counts(unit: str) -> None:
    assert unit in _COUNT_UNITS


@pytest.mark.parametrize("unit", CHINESE_COUNT_UNITS)
def test_chinese_count_units_reach_the_count_branch(unit: str) -> None:
    """Membership in the set is not the same as reaching the branch that reads it.

    ``bim_hub`` never tests the raw unit: it folds the token through
    ``normalize_unit_token`` first, which lower-cases, strips trailing
    periods and folds superscripts. None of those touch CJK today, so the
    word arrives at the ``_COUNT_UNITS`` test unchanged - but that is a
    property of the folding function, not of the set, and this asserts the
    path rather than assuming it. If the folding ever starts transliterating
    CJK, the set entries become the wrong spelling and the guard against
    overwriting a hand-entered piece count goes quiet.
    """
    assert normalize_unit_token(unit) in _COUNT_UNITS


@pytest.mark.parametrize("unit", CHINESE_COUNT_UNITS)
def test_chinese_count_units_belong_to_no_measurement_system(unit: str) -> None:
    """A count unit in either system set would misfire on every count row.

    ``BOQUnitSystemConsistencyRule`` reads the set for the system the project
    is NOT in. Putting 个 in the metric set would flag every 个 row on an
    imperial project as a metric mismatch, and vice versa. This is the
    assertion that stops a future contributor from tidying the count units in
    beside the metric words: nothing else would fail if they did, because an
    unrecognised unit is skipped rather than flagged.
    """
    assert unit not in _METRIC_BOQ_UNITS
    assert unit not in _IMPERIAL_BOQ_UNITS


@pytest.mark.parametrize("unit", CHINESE_METRIC_UNITS + CHINESE_COUNT_UNITS + FULLWIDTH_METRIC_UNITS)
def test_chinese_units_survive_the_write_path(unit: str) -> None:
    """Every unit in the vocabulary must be one the write path can store.

    A token the write path rejects would be decoration: it could never reach
    the rule that reads it. This is the load-bearing property, and it holds
    whatever ``normalise_unit`` chooses to return.
    """
    assert normalise_unit(unit) is not None


@pytest.mark.parametrize("unit", CHINESE_METRIC_UNITS + CHINESE_COUNT_UNITS + FULLWIDTH_METRIC_UNITS)
def test_chinese_units_are_not_aliased_to_latin(unit: str) -> None:
    """Pin on a policy, not on a fact: local spellings are kept as typed.

    ``boq/units.py`` deliberately carries no CJK, Cyrillic or accented
    entries in ``_UNIT_ALIASES`` - the bill shows what the estimator wrote,
    and the vocabulary in the rules is what makes that readable to the
    engine. Adding an alias such as 平方米 -> m2 would fail this test.

    That failure is a decision point, not a defect. Aliasing is a coherent
    alternative design, but it moves the vocabulary out of the rules and
    into the write path for every market at once, so it should be taken
    deliberately and this test should be deleted in the same change - not
    loosened to make a surprise pass.
    """
    assert normalise_unit(unit) == unit


@pytest.mark.parametrize("glyph", CJK_COMPATIBILITY_GLYPHS)
def test_cjk_compatibility_glyphs_are_still_rejected(glyph: str) -> None:
    """Guard on the reason these are absent from the vocabulary.

    ``_is_safe_unit_shape`` requires the first character to be a letter, a
    digit or '%'. These glyphs are category So, so ``normalise_unit`` returns
    None and ``PositionCreate`` raises: a bill row measured in ㎡ cannot be
    stored at all. That is a real import gap for the Chinese market - NFKC
    would fold ㎡ to m2 in one line - but it is a change to a write path every
    market shares, so it was left alone.

    When someone does fix it, this test fails, and that failure is the signal
    to add the compatibility glyphs to ``_METRIC_BOQ_UNITS``.
    """
    assert normalise_unit(glyph) is None
    assert glyph not in _METRIC_BOQ_UNITS
