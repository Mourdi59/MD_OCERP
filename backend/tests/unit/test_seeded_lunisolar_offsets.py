# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""A lunisolar festival sits a bounded distance from its own year's lunar new year.

``tests/unit/core/test_calendar.py`` already holds this invariant over the curated
``_CN_FESTIVALS`` table in ``app/core/calendar.py``. This file is the mirror for the
seeded JSON, which is the more exposed of the two: ``seed_data/work_calendars.json``
is what ``get_working_days`` subtracts, and that is published at ``router.py:232``.

The platform shipped exactly the defect this guards. The Chinese row for 2026 carried
``2026-05-31`` for Dragon Boat and ``2026-10-06`` for Mid-Autumn. Both are the correct
*2025* dates with the year bumped and the day and month left alone. Measured against
2026's own Spring Festival they come to 103 and 231 days, well outside the bands below;
measured against 2025's they are 122 and 250, dead centre. The row survived review
because it was half right - Spring Festival and Qingming were correct for 2026.

Why this needs no external source, which is what makes it worth having on hand-curated
data. Dragon Boat is lunar 5/5 and Mid-Autumn is lunar 8/15, so both sit a fixed number
of lunar months after lunar 1/1. Four months of 29 or 30 days puts Dragon Boat 120 to
124 days out. Seven puts Mid-Autumn near 220, unless a leap month falls between the two,
which adds a whole lunar month and pushes it near 250. It is arithmetic on the row's own
contents, so it stays true without anybody sourcing a date.

WHERE THE ARITHMETIC ANCHORS, which is easy to get wrong. The Chinese row lists the
*observed* holiday, so its Spring Festival block opens on New Year's Eve, the day BEFORE
lunar new year, and runs past it. Anchoring on the earliest date in the block therefore
measures from the wrong day and inflates every offset by one. Today that is survivable -
CN 2026 reads 123 and 221 instead of 122 and 220, both still inside the bands - but it
spends a day of margin that a row sitting on a band edge would not have. So the anchor
here is the row's stated lunar new year, found by name, and
``test_anchoring_on_the_block_start_would_shift_every_offset`` pins that reasoning.

TWO THINGS THIS CANNOT DO. Both are the reason to write them down: a guard whose blind
spots are undocumented gets trusted for what it never checked.

1. It cannot catch a table shifted uniformly in one direction, because every offset is
   relative to another date in the same row. Move the whole row a week and every offset
   is unchanged. Closing that needs a source for the absolute dates.
2. It does not prove Qingming. Qingming follows a solar term rather than a lunar month,
   so it has no offset to check. It gets only the narrow 4-6 April bound, which limits
   the damage rather than proving the date.

It is also blind to a MISSING festival: a row that simply omits Dragon Boat contributes
no offset and no offender. ``test_a_row_that_lost_its_anchor_is_an_offender`` closes the
half of that which is checkable - a rule-bearing festival with no anchor to measure from
is reported rather than skipped - but an absent festival is not detectable here at all.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
_SEED = _BACKEND / "app" / "modules" / "i18n_foundation" / "seed_data" / "work_calendars.json"

# The row's lunar new year, matched exactly so "Lunar New Year Eve" and "Lunar New Year
# Day 2" do not answer for "Lunar New Year". This is the anchor the offsets measure from.
_ANCHOR_NAMES = ("Chinese New Year Day 1", "Lunar New Year")

# Festival name -> the bands its offset from lunar 1/1 may fall in. The second band on
# the 8/15 festivals is the leap-month year, which inserts a whole lunar month between
# the two. Chuseok is the Korean name for the same lunar day as Mid-Autumn.
_OFFSET_RULES: dict[str, tuple[tuple[int, int], ...]] = {
    "Dragon Boat Festival": ((120, 124),),
    "Mid-Autumn Festival": ((219, 222), (249, 252)),
    "Chuseok": ((219, 222), (249, 252)),
}

# Qingming is a solar term, so it gets a calendar bound rather than an offset.
_SOLAR_TERM_BOUNDS = {"Qingming Festival": ((4, 4), (4, 6))}

# Rows known to violate the invariant and deliberately not repaired here, each with the
# reason. This is a ratchet, not an amnesty: ``test_every_exemption_is_still_needed``
# fails once an entry stops violating, so a fixed row cannot leave a stale exemption
# behind that would silently cover the next defect.
_EXEMPT: dict[tuple[str, str], str] = {
    ("KR", "Chuseok"): (
        "The Korean Chuseok block carries the same copy-forward defect as the Chinese row and is "
        "queued as its own change. Its three entries sit at 2026-10-04/05/06, all shifted together, "
        "where the row's own Lunar New Year puts the correct block at 2026-09-24/25/26."
    ),
}

# Floors. Two rather than one: a file that parsed but lost its festival names would clear
# a row count while contributing no offset to inspect, which is how a check like this goes
# quietly blind. Small numbers on purpose - only two seeded rows carry a lunar new year.
_MIN_ROWS_WITH_ANCHOR = 2
_MIN_OFFSETS_CHECKED = 3


def _seed_rows() -> list[dict[str, Any]]:
    """Read the shipped seed file, which is the thing under test."""
    return json.loads(_SEED.read_text(encoding="utf-8"))


def _as_date(text: str) -> date:
    year, month, day = (int(part) for part in text.split("-"))
    return date(year, month, day)


def _anchor_of(row: dict[str, Any]) -> date | None:
    """Return the row's stated lunar new year, or None when it declares none.

    Deliberately NOT the earliest date of the Spring Festival block: an observed block
    opens on New Year's Eve, one day earlier, and would inflate every offset by one.
    """
    for exception in row.get("exceptions", []):
        if exception.get("name", {}).get("en") in _ANCHOR_NAMES:
            return _as_date(exception["date"])
    return None


def _survey_offsets(rows: list[dict[str, Any]]) -> tuple[int, int, list[str]]:
    """Measure every rule-bearing festival against its own row's lunar new year.

    The single implementation the gate and the controls both call, so no control can
    pass by testing a re-implementation of the thing it guards.

    Returns:
        ``(rows carrying an anchor, offsets checked, offender lines)``.
    """
    anchored = 0
    checked = 0
    offenders: list[str] = []

    for row in rows:
        country = row.get("country_code", "??")
        anchor = _anchor_of(row)
        rule_bearing = [e for e in row.get("exceptions", []) if e.get("name", {}).get("en") in _OFFSET_RULES]

        if anchor is None:
            # Not every row is lunisolar. Only complain when one carries a festival that
            # needs an anchor, so a missing anchor is reported instead of silently skipped.
            for exception in rule_bearing:
                offenders.append(
                    f"{country} declares {exception['name']['en']} on {exception['date']} but states no "
                    f"lunar new year, so the offset cannot be measured. Expected one of {_ANCHOR_NAMES}."
                )
            continue

        anchored += 1
        for exception in rule_bearing:
            name = exception["name"]["en"]
            bands = _OFFSET_RULES[name]
            offset = (_as_date(exception["date"]) - anchor).days
            checked += 1
            if any(low <= offset <= high for low, high in bands):
                continue
            readable = " or ".join(f"{low}-{high}" for low, high in bands)
            offenders.append(
                f"{country} puts {name} on {exception['date']}, {offset} days after its own lunar new year "
                f"({anchor.isoformat()}). A lunisolar festival sits {readable} days out, so this date does "
                f"not belong to this row's year. Carrying last year's date forward and bumping only the "
                f"year lands exactly here."
            )

    return anchored, checked, offenders


def _unexempt(offenders: list[str]) -> list[str]:
    """Drop offender lines covered by a documented exemption."""
    return [
        line
        for line in offenders
        if not any(line.startswith(f"{country} ") and name in line for country, name in _EXEMPT)
    ]


@pytest.mark.unit
def test_every_seeded_lunisolar_festival_sits_in_its_own_years_band() -> None:
    """The wall: the shipped JSON itself, not the schema that guards the door.

    The Saudi weekday defect came in through the wall - ``seed.py`` builds the ORM object
    directly, so no write schema ever saw it. This is the same door and the same file.
    """
    _, _, offenders = _survey_offsets(_seed_rows())

    assert not _unexempt(offenders), "seeded lunisolar dates outside their own year's band:\n" + "\n".join(
        _unexempt(offenders)
    )


@pytest.mark.unit
def test_the_offset_survey_actually_surveyed_something() -> None:
    """A clean result means nothing if nothing was inspected."""
    anchored, checked, _ = _survey_offsets(_seed_rows())

    assert anchored >= _MIN_ROWS_WITH_ANCHOR, (
        f"only {anchored} rows declare a lunar new year, expected at least {_MIN_ROWS_WITH_ANCHOR}"
    )
    assert checked >= _MIN_OFFSETS_CHECKED, (
        f"only {checked} festival offsets were measured, expected at least {_MIN_OFFSETS_CHECKED}. "
        f"A shrinking population is how a check like this goes quietly blind."
    )


@pytest.mark.unit
def test_qingming_stays_within_its_narrow_calendar_bound() -> None:
    """Qingming is a solar term, so this bounds the damage rather than proving the date.

    Stated as its own test, and named as a weaker check, so nobody reads the file's clean
    result as evidence that Qingming was verified the way the lunisolar dates were.
    """
    checked = 0
    for row in _seed_rows():
        for exception in row.get("exceptions", []):
            bounds = _SOLAR_TERM_BOUNDS.get(exception.get("name", {}).get("en", ""))
            if not bounds:
                continue
            (month, _), (low, high) = bounds
            when = _as_date(exception["date"])
            checked += 1
            assert when.month == month and low <= when.day <= high, (
                f"{row['country_code']} puts {exception['name']['en']} on {exception['date']}, outside "
                f"{low}-{high} of month {month}"
            )
    assert checked >= 1, "no solar-term festival was inspected at all"


@pytest.mark.unit
def test_every_exemption_is_still_needed() -> None:
    """A ratchet: a repaired row must not leave a stale exemption behind.

    An exemption that outlives its defect is worse than none, because it silently covers
    the next one. This fails the moment an exempt row starts passing.
    """
    _, _, offenders = _survey_offsets(_seed_rows())

    for (country, name), reason in _EXEMPT.items():
        assert any(line.startswith(f"{country} ") and name in line for line in offenders), (
            f"the exemption for {country}/{name} no longer matches any offender, so it is stale and must "
            f"be deleted from _EXEMPT. It was recorded as: {reason}"
        )


# ── Controls: the survey above must be capable of going red ──────────────────


@pytest.mark.unit
def test_a_copy_forward_is_caught() -> None:
    """Plant the exact defect that shipped and prove the survey reports it."""
    rows = copy.deepcopy(_seed_rows())
    _, _, before = _survey_offsets(rows)
    assert not [line for line in _unexempt(before) if line.startswith("CN ")], (
        f"CN already offends, so planting a defect measures nothing: {before}"
    )

    china = next(row for row in rows if row["country_code"] == "CN")
    dragon = next(e for e in china["exceptions"] if e["name"]["en"] == "Dragon Boat Festival")
    dragon["date"] = "2026-05-31"  # the correct 2025 date, year bumped

    _, _, after = _survey_offsets(rows)
    planted = [line for line in _unexempt(after) if line.startswith("CN ") and "Dragon Boat" in line]
    assert len(planted) == 1, f"expected exactly the one planted offender, got: {planted}"
    assert len(_unexempt(after)) == len(_unexempt(before)) + 1, (
        f"planting one defect should add exactly one offender: {_unexempt(after)}"
    )
    assert "103 days after its own lunar new year" in planted[0], planted[0]


@pytest.mark.unit
def test_a_row_that_lost_its_anchor_is_an_offender() -> None:
    """A festival with nothing to measure from must be reported, never skipped.

    Silently skipping is the failure this whole file exists to prevent: the check reads
    clean because it stopped looking, not because the data is right.
    """
    rows = copy.deepcopy(_seed_rows())
    china = next(row for row in rows if row["country_code"] == "CN")
    china["exceptions"] = [e for e in china["exceptions"] if e["name"]["en"] != "Chinese New Year Day 1"]

    anchored, _, offenders = _survey_offsets(rows)
    complaints = [line for line in offenders if line.startswith("CN ") and "states no lunar new year" in line]

    assert complaints, f"a row with festivals but no anchor was skipped silently: {offenders}"
    assert anchored == _MIN_ROWS_WITH_ANCHOR - 1, anchored


@pytest.mark.unit
def test_anchoring_on_the_block_start_would_shift_every_offset() -> None:
    """Pins why the anchor is the stated lunar new year rather than the block's first date.

    The observed Spring Festival block opens on New Year's Eve, one day before lunar 1/1.
    Anchoring there inflates every offset by exactly one. CN 2026 happens to survive that
    (122 and 220 become 123 and 221, still inside the bands), which is precisely why it is
    worth a test: the error is invisible today and would only surface on a row sitting at a
    band edge, long after anybody remembered the anchor was chosen carelessly.
    """
    china = next(row for row in _seed_rows() if row["country_code"] == "CN")
    stated = _anchor_of(china)
    assert stated == date(2026, 2, 17)

    block = [e for e in china["exceptions"] if e["name"]["en"].startswith("Chinese New Year")]
    earliest = min(_as_date(e["date"]) for e in block)
    assert earliest == date(2026, 2, 16), "the observed block no longer opens on New Year's Eve"
    assert (stated - earliest).days == 1

    for name, expected_true in (("Dragon Boat Festival", 122), ("Mid-Autumn Festival", 220)):
        when = _as_date(next(e for e in china["exceptions"] if e["name"]["en"] == name)["date"])
        assert (when - stated).days == expected_true
        assert (when - earliest).days == expected_true + 1
