# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""How a holiday answer was arrived at, not only what it was.

``_get_holidays`` used to collapse four situations into one ``frozenset``:
covered and complete, covered but outside a curated window, not covered at all,
and a computation that raised. The last was swallowed into an empty set by a
bare ``except Exception``, and since ``is_working_day`` turns the set into a
``bool``, a broken holiday computation made every weekday a working day with a
log line as the only trace. A log is not something a caller can branch on.

Three empty sets, three meanings. A jurisdiction with genuinely no holidays is
an answer. A jurisdiction nothing covers is a weaker answer, the international
default. A jurisdiction whose holidays could not be computed is not an answer at
all. The old code produced identical bytes for all three.

The two axes are asserted separately on purpose. China in a year past its
curated table is the case that matters: the country is fully covered and the
year is not, so a single flag keyed on the country would report it green. That
is why :func:`app.core.provenance.weakest` exists and why it is tested here.

Coverage answers whether rows are present, and does not absorb accuracy. A
holiday whose date is computed but whose length is a stand-in is a third axis,
not a hole in the first two, so it is a fallback on ``holiday_extent`` while
jurisdiction and year both stay declared. Bending ``partial`` to carry it would
have made one slot answer two questions resolved two different ways. See
``_EXTENT_STANDINS`` for why the axis and its tokens are named for the
mechanism: absence has to mean "no stand-in we know of" and never "verified",
because nothing in this module has been verified.

Mutation matrix, measured against this file:

    baseline                                       55 passed
    restore the swallow (except -> empty set)       4 failed, 51 passed
    raise but still cache an empty answer           2 failed, 53 passed
    treat a curated-window miss as complete         4 failed, 51 passed
    call every shared table a synonym (AT as DE)    1 failed, 54 passed
    forget the synonym table (GB falls back to UK)  1 failed, 54 passed
    call an uncovered country declared              3 failed, 52 passed
    drop one Gulf country from the span registry    3 failed, 52 passed
    call every uncomputed extent a computed one     8 failed, 47 passed
    restored                                       55 passed

Run together with ``test_calendar.py`` the baseline is 118 passed, and the
source was restored to a byte-identical sha256 after every mutation.

Two of these come in opposed pairs on purpose. A shared holiday function can be
wrongly called a synonym or wrongly called a fallback, and an empty set can be
wrongly called an answer or wrongly called nothing; a guard that is only hard in
one direction leaves the other as the way in.

The second mutation is the one a partial fix would produce: the first call
raises and every later one returns a plausible empty set from the cache. It is
caught only because the failure paths are asserted twice rather than once, at
both the resolver and the ``is_working_day`` level.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest

from app.core import calendar as cal
from app.core.calendar import (
    AXIS_EFFECTIVE_YEAR,
    AXIS_JURISDICTION,
    HolidayCalculationError,
    holiday_provenance,
    resolve_holidays,
)
from app.core.provenance import Provenance, Source, weakest

# Test-only codes. Real ones would tie these assertions to shipped data and make
# them fail for reasons that have nothing to do with provenance.
_EMPTY_CC = "ZZ"  # a jurisdiction with genuinely no holidays
_BROKEN_CC = "QQ"  # a jurisdiction whose computation raises


@pytest.fixture(autouse=True)
def _isolate_calendar_state() -> Iterator[None]:
    """Keep injected functions and memoised answers out of other tests.

    The cache is module-level, so a single poisoned entry would make unrelated
    tests order-dependent - which is exactly the failure the no-memoising rule
    below exists to prevent.
    """
    saved = dict(cal._HOLIDAY_FUNCS)
    cal._holiday_cache.clear()
    yield
    cal._HOLIDAY_FUNCS.clear()
    cal._HOLIDAY_FUNCS.update(saved)
    cal._holiday_cache.clear()


def _install_empty() -> None:
    cal._HOLIDAY_FUNCS[_EMPTY_CC] = lambda _y: set()


def _install_broken() -> None:
    def boom(_year: int) -> set[date]:
        raise ValueError("ephemeris unavailable")

    cal._HOLIDAY_FUNCS[_BROKEN_CC] = boom


# ── The three empty sets the old code could not tell apart ────────────────────


@pytest.mark.unit
def test_holiday_free_and_uncovered_and_failed_are_three_different_things() -> None:
    """All three produced an empty frozenset before, which is why none was safe.

    This asserts they are now distinguishable at all, which is the whole point
    of the change. The finer assertions live in the tests below; this one is the
    statement of the defect.
    """
    _install_empty()
    _install_broken()

    free = resolve_holidays(_EMPTY_CC, 2026)
    uncovered = resolve_holidays("XX", 2026)

    assert free["dates"] == uncovered["dates"] == frozenset()
    # Same dates, different provenance. That is the entire fix.
    assert free[AXIS_JURISDICTION].source is not uncovered[AXIS_JURISDICTION].source

    with pytest.raises(HolidayCalculationError):
        resolve_holidays(_BROKEN_CC, 2026)


@pytest.mark.unit
def test_a_holiday_free_jurisdiction_is_declared_rather_than_a_fallback() -> None:
    """Zero holidays is an answer found on the country's own terms."""
    _install_empty()
    prov = resolve_holidays(_EMPTY_CC, 2026)[AXIS_JURISDICTION]
    assert prov.source is Source.DECLARED
    assert prov.answered is True
    assert prov.usable is True


@pytest.mark.unit
def test_an_uncovered_country_falls_back_to_the_international_default() -> None:
    """Not covered is a weaker answer, not the absence of one.

    It stays usable: an uncovered jurisdiction runs on a working week with no
    public holidays and says so, rather than refusing to schedule anything.
    """
    prov = resolve_holidays("XX", 2026)[AXIS_JURISDICTION]
    assert prov.source is Source.FALLBACK
    assert prov.requested == "XX"
    assert prov.used == cal.NO_PUBLIC_HOLIDAYS
    assert prov.answered is False
    assert prov.usable is True


@pytest.mark.unit
def test_a_failed_computation_raises_and_carries_unavailable_provenance() -> None:
    """The defect surfaces as a defect, and brings the vocabulary with it.

    A caller that catches this should not have to rebuild the provenance by
    hand, because rebuilding it by hand is how it ends up recorded as a
    fallback - which would say an answer was found.
    """
    _install_broken()
    with pytest.raises(HolidayCalculationError) as excinfo:
        resolve_holidays(_BROKEN_CC, 2026)

    exc = excinfo.value
    assert exc.country_code == _BROKEN_CC
    assert exc.year == 2026
    assert isinstance(exc.__cause__, ValueError)
    assert exc.provenance.source is Source.UNAVAILABLE
    assert exc.provenance.usable is False
    assert exc.provenance.used == "", "nothing answered, so nothing was used"


@pytest.mark.unit
def test_a_failure_is_never_memoised() -> None:
    """A cached failure would raise once and then answer emptily forever after.

    Asserting the failure twice is what separates this from a partial fix. One
    call cannot tell a raise-and-do-not-cache from a raise-and-cache.
    """
    _install_broken()
    for _ in range(2):
        with pytest.raises(HolidayCalculationError):
            resolve_holidays(_BROKEN_CC, 2026)
    assert (_BROKEN_CC, 2026) not in cal._holiday_cache


@pytest.mark.unit
def test_is_working_day_propagates_a_failed_computation() -> None:
    """The bool-returning caller must not invent a working year out of a failure.

    Called twice on purpose. A fix that raises but still memoises the empty set
    would satisfy the first call and hand the second a year in which every
    weekday is a working day, which is the original defect wearing a raise.
    """
    _install_broken()
    _install_empty()
    for _ in range(2):
        with pytest.raises(HolidayCalculationError):
            cal.is_working_day(date(2026, 6, 3), _BROKEN_CC)
    # Control: a country with no holidays still answers normally, so the raise
    # above is about the failure and not about having an empty set.
    assert cal.is_working_day(date(2026, 6, 3), _EMPTY_CC) is True


# ── Curated windows: the second axis ──────────────────────────────────────────


@pytest.mark.unit
def test_the_curated_tables_are_populated() -> None:
    """Population floor: the window tests below pass vacuously over empty tables."""
    assert cal._CURATED_TABLES
    for code, (table, omitted) in cal._CURATED_TABLES.items():
        assert table, f"{code} curated table is empty"
        assert omitted, f"{code} names nothing it omits"


@pytest.mark.unit
def test_the_curated_set_names_every_year_keyed_table_in_the_module() -> None:
    """Ratchet: a new lunisolar table added and not registered would lie.

    A table left out of ``_CURATED_TABLES`` reports every year complete,
    including years it does not cover, which is the defect this file exists to
    prevent. Counting the module's year-keyed tables is a property of the module
    rather than a restatement of the list being checked.
    """
    year_keyed = {
        name
        for name, value in vars(cal).items()
        if name.isupper() and isinstance(value, dict) and value and all(isinstance(k, int) for k in value)
    }
    registered = {id(table) for table, _ in cal._CURATED_TABLES.values()}
    unregistered = {name for name in year_keyed if id(vars(cal)[name]) not in registered}
    assert not unregistered, f"year-keyed tables not registered in _CURATED_TABLES: {sorted(unregistered)}"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("country", "expected_omission"),
    [("CN", "Spring Festival"), ("IN", "Diwali")],
)
def test_a_year_outside_a_curated_table_falls_back_on_the_year_axis_alone(
    country: str,
    expected_omission: str,
) -> None:
    """The country is covered and the year is not. One flag would miss this.

    ``_holidays_cn`` already knew exactly what it was dropping and said so in a
    warning. Only the channel was missing.
    """
    far_future = 2099
    assert far_future not in cal._CURATED_TABLES[country][0], "pick a year the table really does not cover"

    result = resolve_holidays(country, far_future)
    assert result[AXIS_JURISDICTION].source is Source.DECLARED, "the country itself is fully covered"
    assert result[AXIS_EFFECTIVE_YEAR].source is Source.FALLBACK
    assert result[AXIS_EFFECTIVE_YEAR].used == cal.GREGORIAN_ONLY
    assert expected_omission in result["omitted"]
    assert expected_omission in result[AXIS_EFFECTIVE_YEAR].detail
    assert result["dates"], "the fixed Gregorian days are still returned"


@pytest.mark.unit
@pytest.mark.parametrize("country", ["CN", "IN"])
def test_a_year_inside_the_curated_table_is_declared_on_both_axes(country: str) -> None:
    """Control for the partial case: inside the window nothing is omitted."""
    covered_year = max(cal._CURATED_TABLES[country][0])
    result = resolve_holidays(country, covered_year)
    assert result[AXIS_JURISDICTION].source is Source.DECLARED
    assert result[AXIS_EFFECTIVE_YEAR].source is Source.DECLARED
    assert result["omitted"] == ()


@pytest.mark.unit
def test_the_weaker_axis_is_the_verdict() -> None:
    """A fully covered country in an uncovered year is not a covered answer.

    This is the case a single jurisdiction-keyed flag paints green, so it is
    asserted through the helper a caller would actually reach for.
    """
    verdict = holiday_provenance("CN", 2099)
    assert verdict.source is Source.FALLBACK
    assert verdict.axis == AXIS_EFFECTIVE_YEAR

    inside = holiday_provenance("CN", max(cal._CURATED_TABLES["CN"][0]))
    assert inside.source is Source.DECLARED


# ── Which country actually answered ───────────────────────────────────────────


@pytest.mark.unit
def test_at_least_one_shipped_code_is_served_by_another_countrys_function() -> None:
    """Population floor for the alias test: without an alias it proves nothing."""
    by_func: dict[Any, list[str]] = {}
    for code, func in cal._HOLIDAY_FUNCS.items():
        by_func.setdefault(func, []).append(code)
    assert any(len(codes) > 1 for codes in by_func.values())


@pytest.mark.unit
def test_a_country_served_by_another_countrys_table_reports_a_fallback() -> None:
    """Austria is not Germany, and a caller is entitled to know which answered.

    The table's own comment calls Austrian holidays a close mirror of Germany's.
    A close mirror is an approximation, so it is a fallback and says so.
    """
    prov = resolve_holidays("AT", 2026)[AXIS_JURISDICTION]
    assert prov.source is Source.FALLBACK
    assert prov.requested == "AT"
    assert prov.used == "DE"
    assert prov.answered is False


@pytest.mark.unit
@pytest.mark.parametrize("code", ["GB", "UK"])
def test_two_spellings_of_one_state_are_not_a_fallback(code: str) -> None:
    """GB and UK share a function because they are the same country.

    The counterpart to the Austria test, and the reason the two cannot be told
    apart by "do these share a function". Reporting Britain as falling back to
    itself would be a false alarm, and false alarms are how a provenance field
    stops being read.
    """
    prov = resolve_holidays(code, 2026)[AXIS_JURISDICTION]
    assert prov.source is Source.DECLARED
    assert prov.answered is True


@pytest.mark.unit
@pytest.mark.parametrize("code", ["DE", "CA", "US", "CH"])
def test_a_country_answered_by_its_own_table_is_declared(code: str) -> None:
    """Controls, including CH whose function is a lambda naming no country."""
    prov = resolve_holidays(code, 2026)[AXIS_JURISDICTION]
    assert prov.source is Source.DECLARED
    assert prov.requested == prov.used == code


# ── The type is doing work, not just carrying strings ─────────────────────────


@pytest.mark.unit
def test_the_shape_of_this_defect_cannot_be_written_down() -> None:
    """An unavailable that claims something answered is refused by the type.

    This is the shape the old swallow would have had to take to be recorded:
    nothing answered, yet a country named as having answered. Asserting it here
    keeps the guarantee visible from the module that needed it.
    """
    with pytest.raises(ValueError, match="nothing answered"):
        Provenance(axis=AXIS_JURISDICTION, source=Source.UNAVAILABLE, requested="DE", used="DE")


@pytest.mark.unit
def test_weakest_of_the_two_axes_prefers_the_worse_one() -> None:
    """Guards the ordering the verdict depends on."""
    strong = resolve_holidays("DE", 2026)[AXIS_JURISDICTION]
    weak = resolve_holidays("XX", 2026)[AXIS_JURISDICTION]
    assert weakest(strong, weak) is weak
    assert weakest(weak, strong) is weak


# ── Present rows, uncomputed extent ───────────────────────────────────────────


@pytest.mark.unit
def test_the_placeholder_span_registry_is_populated() -> None:
    """Population floor: the tests below pass vacuously over an empty registry."""
    assert cal._PLACEHOLDER_SPANS
    for code, names in cal._PLACEHOLDER_SPANS.items():
        assert names, f"{code} is registered as having a placeholder span but names none"


@pytest.mark.unit
def test_every_country_served_by_the_shared_eid_spans_is_registered() -> None:
    """Ratchet: derived from the source, not from the list being checked.

    ``_gcc_eids`` is where the placeholder lives, so the countries affected are
    the ones whose function calls it. A seventh Gulf country added without a
    registry entry would silently claim a computed span, which is the whole
    thing this field exists to prevent.
    """
    served = {
        code
        for code, func in cal._HOLIDAY_FUNCS.items()
        if getattr(func, "__name__", "").startswith("_holidays_") and "_gcc_eids(" in inspect.getsource(func)
    }
    assert served, "no function calls _gcc_eids; this test is checking nothing"
    assert served <= set(cal._PLACEHOLDER_SPANS), (
        f"served by the shared Eid spans but not registered: {sorted(served - set(cal._PLACEHOLDER_SPANS))}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("country", ["AE", "SA", "QA", "KW", "BH", "OM"])
def test_a_placeholder_span_is_reported_without_downgrading_coverage(country: str) -> None:
    """The rows are present, so coverage is complete, and that is a true sentence.

    Coverage answers presence and does not absorb accuracy. The country and the
    year both answered on their own terms; what did not happen is the length
    being worked out, and that is the third axis rather than a hole in the
    first two.
    """
    result = resolve_holidays(country, 2026)
    assert result[AXIS_JURISDICTION].source is Source.DECLARED
    assert result[AXIS_EFFECTIVE_YEAR].source is Source.DECLARED
    assert result["omitted"] == (), "nothing is missing; the extent is the issue"
    assert result["placeholder_spans"] == cal._GCC_PLACEHOLDER_SPANS


@pytest.mark.unit
@pytest.mark.parametrize(
    ("country", "token"),
    [
        ("AE", cal.SHARED_GCC_EID_SPAN),
        ("SA", cal.SHARED_GCC_EID_SPAN),
        ("QA", cal.SHARED_GCC_EID_SPAN),
        ("KW", cal.SHARED_GCC_EID_SPAN),
        ("BH", cal.SHARED_GCC_EID_SPAN),
        ("OM", cal.SHARED_GCC_EID_SPAN),
        ("CH", cal.THREE_FIXED_DAYS),
    ],
)
def test_an_uncomputed_extent_is_a_fallback_naming_what_stood_in(country: str, token: str) -> None:
    """A stand-in is an answer, so it is a fallback and it names itself.

    Switzerland is here beside the Gulf because a hardcoded three-date roster is
    as uncomputed as a hardcoded span. Marking one and not the other would make
    the absence of the mark mean less than it should.
    """
    prov = resolve_holidays(country, 2026)[cal.AXIS_HOLIDAY_EXTENT]
    assert prov.source is Source.FALLBACK
    assert prov.requested == country
    assert prov.used == token
    assert prov.usable is True, "the dates are still an answer and can be computed with"
    assert prov.detail, "a stand-in has to be able to explain itself to a human"


@pytest.mark.unit
@pytest.mark.parametrize("country", ["DE", "US", "CN", "IN", "JP", "NG", "BG"])
def test_a_country_with_no_known_stand_in_is_declared_on_the_extent_axis(country: str) -> None:
    """Absence means no stand-in we know of, not an extent anybody verified.

    Nobody has checked the German roster. The whole reason the axis is named for
    the mechanism is so that this row can be silent without claiming otherwise.
    """
    assert resolve_holidays(country, 2026)[cal.AXIS_HOLIDAY_EXTENT].source is Source.DECLARED


@pytest.mark.unit
def test_the_verdict_goes_amber_for_a_country_whose_span_was_never_computed() -> None:
    """The live consequence, asserted where a consumer would actually hit it.

    Nothing publishes as jurisdiction specific while a dimension it uses falls
    back, and that rule reads the verdict. Before the third axis Saudi Arabia
    answered fully covered on a span its own source says runs short, so the rule
    read the answer and never saw the caveat.
    """
    verdict = holiday_provenance("SA", 2026)
    assert verdict.source is Source.FALLBACK
    assert verdict.axis == cal.AXIS_HOLIDAY_EXTENT
    assert verdict.answered is False

    # Control: a country with none of the three weaknesses still reads clean.
    assert holiday_provenance("DE", 2026).source is Source.DECLARED


@pytest.mark.unit
def test_every_country_with_a_placeholder_span_also_declares_a_stand_in() -> None:
    """The two registries cannot drift apart without this going red.

    ``placeholder_spans`` is the data and ``holiday_extent`` is the provenance.
    A country in the first and not the second would carry the names of holidays
    nobody computed while reporting the axis clean, which is the worse half of
    the pair to lose.
    """
    assert set(cal._PLACEHOLDER_SPANS) <= set(cal._EXTENT_STANDINS), (
        f"has placeholder spans but no stand-in on the extent axis: "
        f"{sorted(set(cal._PLACEHOLDER_SPANS) - set(cal._EXTENT_STANDINS))}"
    )
    for token in cal._EXTENT_STANDINS.values():
        assert token in cal._EXTENT_DETAIL, f"{token} has no detail text"


@pytest.mark.unit
@pytest.mark.parametrize("country", ["DE", "US", "CA", "CN", "JP"])
def test_a_country_with_no_known_placeholder_reports_none(country: str) -> None:
    """Absence means no placeholder we know of, not a span anybody verified.

    The field is named for the mechanism for exactly this reason. Nothing here
    asserts that Germany's holiday lengths were checked, because they were not,
    and a field called "approximate" would have made every quiet country claim
    they had been.
    """
    assert resolve_holidays(country, 2026)["placeholder_spans"] == ()


@pytest.mark.unit
def test_an_omitted_holiday_and_a_placeholder_span_are_independent() -> None:
    """Two different facts in two slots, which is the point of the second slot.

    China past its curated table has omissions and no placeholder spans. Saudi
    Arabia has the reverse. One field carrying both would have had to call these
    the same thing.
    """
    china = resolve_holidays("CN", 2099)
    saudi = resolve_holidays("SA", 2026)

    assert china["omitted"] and not china["placeholder_spans"]
    assert saudi["placeholder_spans"] and not saudi["omitted"]


# ── The accessor keeps its shape ──────────────────────────────────────────────


@pytest.mark.unit
def test_get_holidays_still_returns_a_frozenset_of_dates() -> None:
    """Guards a trap: ``assert _get_holidays(cc, y)`` is a live assertion elsewhere.

    ``tests/unit/core/test_calendar.py`` asserts truthiness of this return to
    prove Bahrain and Oman have holidays at all. Had the accessor started
    returning the provenance mapping, that assertion would have passed on a
    non-empty dict while the dates inside it were empty.
    """
    holidays = cal._get_holidays("DE", 2026)
    assert isinstance(holidays, frozenset)
    assert all(isinstance(d, date) for d in holidays)
    assert holidays == resolve_holidays("DE", 2026)["dates"]


@pytest.mark.unit
def test_a_lower_case_code_resolves_the_same_as_upper() -> None:
    """The code is normalised once, in the resolver, rather than at each caller."""
    assert resolve_holidays("de", 2026)["dates"] == resolve_holidays("DE", 2026)["dates"]
    assert resolve_holidays("de", 2026)[AXIS_JURISDICTION].requested == "DE"
