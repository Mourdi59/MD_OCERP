# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Tests for the country coverage manifest.

These test the instrument, not the coverage. A country having no payment regime
is a finding for the register and not a failure here; the manifest reporting it
as covered, or reporting a broken probe as a gap, is a failure here.

The one property everything else rests on: **UNRESOLVED must never present as
MISSING.** An instrument that turns "I could not measure this" into "there is
nothing there" hands back a finished-looking answer to an unasked question, and
every count downstream of it is wrong in the comfortable direction.
"""

from __future__ import annotations

import sys

import pytest

from app.core import country_coverage as cc
from app.modules.payment_clock import data as payment_clock_data

# Countries with enough spread to exercise the verdicts: a large market with
# broad coverage, one known to be partly covered, one Gulf state, two Asian.
_SWEEP = ("US", "CA", "DE", "GB", "AE", "CN", "IN", "BR", "SA", "NL", "JP", "MX")

# The register's working cohort plus the rest of the large markets. Wider than
# _SWEEP on purpose: a probe that answers for one country and goes quiet for its
# neighbour is the failure this file exists to catch, and a narrow list hides it.
_COHORT = (
    "US", "CA", "DE", "BG", "RU", "CN", "IN", "BR", "NG", "GB", "FR", "ES",
    "IT", "NL", "PL", "JP", "KR", "AU", "MX", "SA", "AE", "ZA", "TR",
)  # fmt: skip

_SCHEDULE_SERVICE = "app.modules.schedule.service"


def test_the_manifest_has_probes_and_they_all_have_distinct_names():
    """Floor plus uniqueness: a suite over an empty registry passes vacuously."""
    names = cc.dimensions()
    assert len(names) >= 8, f"only {len(names)} dimensions; the manifest has lost probes"
    assert len(set(names)) == len(names), "two probes share a dimension name, so one report overwrites the other"


def test_every_probe_returns_one_of_the_declared_verdicts():
    known = {*cc.ANSWERED, cc.UNRESOLVED}
    report = cc.country_coverage("CA")
    assert len(report.dimensions) == len(cc.dimensions())
    for d in report.dimensions:
        assert d.verdict in known, f"{d.dimension} invented the verdict {d.verdict!r}"
        assert d.detail, f"{d.dimension} returned {d.verdict} with no explanation"


# --------------------------------------------------------------------------- #
# The load-bearing property
# --------------------------------------------------------------------------- #


def test_a_probe_that_raises_is_unresolved_and_never_missing():
    def broken(_country: str) -> cc.DimensionReport:
        raise RuntimeError("registry moved")

    got = cc._run("demo.broken", broken, "CA")
    assert got.verdict == cc.UNRESOLVED
    assert got.verdict != cc.MISSING
    assert "registry moved" in got.detail, "the reason was swallowed, so nobody can fix the probe"


def test_a_raising_probe_stays_unresolved_through_the_public_entry_point(monkeypatch):
    """The wrapper is only worth anything if the registry actually goes through it."""

    def broken(_country: str) -> cc.DimensionReport:
        raise LookupError("symbol gone")

    monkeypatch.setattr(cc, "_PROBES", [*cc._PROBES, ("demo.broken", broken)])
    report = cc.country_coverage("CA")
    assert report.counts[cc.UNRESOLVED] >= 1
    assert [d.dimension for d in report.by_verdict(cc.UNRESOLVED)].count("demo.broken") == 1
    assert "demo.broken" not in [d.dimension for d in report.by_verdict(cc.MISSING)]


def test_an_empty_population_is_unresolved_rather_than_everyone_missing():
    """A registry that resolved and came back empty has lost its shape, not its rows."""
    got = cc._keyed("demo.empty", "nowhere", set(), "CA")
    assert got.verdict == cc.UNRESOLVED
    assert got.verdict != cc.MISSING


def test_a_populated_registry_without_this_country_is_missing_not_unresolved():
    """The other side of the same control, so the check above is not passing on everything."""
    got = cc._keyed("demo.populated", "nowhere", {"US", "DE"}, "CA")
    assert got.verdict == cc.MISSING
    assert got.population == ("DE", "US")


def test_unresolved_is_kept_out_of_the_answered_arithmetic():
    assert cc.UNRESOLVED not in cc.ANSWERED
    unresolved = cc._keyed("demo.empty", "nowhere", set(), "CA")
    assert not unresolved.answered
    assert cc._keyed("demo.populated", "nowhere", {"CA"}, "CA").answered


# --------------------------------------------------------------------------- #
# Each verdict has to be reachable, or it is decoration
# --------------------------------------------------------------------------- #


def _sweep() -> list[cc.DimensionReport]:
    out: list[cc.DimensionReport] = []
    for code in _SWEEP:
        out.extend(cc.country_coverage(code).dimensions)
    return out


def test_the_schedule_resolver_answers_through_the_import_it_has_here():
    """The probe takes the import path when the import is available, as it is here.

    This test used to say that the probe declines to guess on a laptop with no
    cluster, and it was the whole trouble: that was true, the probe reported
    UNRESOLVED for every country off a database, and this test could never see
    it because pytest boots one. It now asserts the narrower thing it is
    actually able to observe - that where the import works, the import is what
    answered. The case it could not reach is staged explicitly further down.
    """
    got = _one("CA", "calendar.schedule_regions")
    assert got.verdict != cc.UNRESOLVED, f"the resolver was not importable even under the test harness: {got.detail}"
    assert got.method == "import", f"a cluster is up, so the import path should have answered, not {got.method!r}"


@pytest.mark.parametrize("verdict", [cc.COVERED, cc.FALLBACK, cc.MISSING, cc.NOT_KEYED, cc.ABSENT])
def test_each_verdict_actually_occurs_somewhere_in_the_sweep(verdict):
    """A vocabulary nothing ever returns describes an imaginary product."""
    results = _sweep()
    assert len(results) >= len(_SWEEP) * 8, "the sweep collapsed; the floor below would pass on anything"
    assert any(d.verdict == verdict for d in results), f"no dimension in {len(_SWEEP)} countries returned {verdict}"


def test_covered_and_missing_land_on_different_countries_in_the_same_dimension():
    """Proof the manifest discriminates rather than reporting one verdict per dimension."""
    dimension = "payment.prompt_payment_regime"
    verdicts = {c: _one(c, dimension).verdict for c in _SWEEP}
    resolved = {c: v for c, v in verdicts.items() if v != cc.UNRESOLVED}
    assert len(resolved) >= 6, f"too few resolved to compare: {verdicts}"
    assert len(set(resolved.values())) > 1, f"{dimension} gave every country the same answer: {resolved}"


def test_a_missing_payment_regime_carries_a_reason_when_one_is_on_record(monkeypatch):
    """The deliverable: a reader queries three MISSING countries and gets three
    different stories, not the same generic sentence three times.

    BR has a recorded NO_REGIME_DIFFERENT_SHAPE reason, JP is simply
    unresearched, which is the default state for most of the world, and the
    held case is staged rather than named. It used to name CN, which was held
    at the time; CN then earned a row of its own and this test failed for a
    reason that had nothing to do with what it was testing. Membership of
    NO_REGIME_HELD is meant to change - that is what the set is for - so the
    held branch is exercised on a country the test puts there itself, and the
    assertion survives the table being right about the world on any given day.

    JP is read twice on purpose, once staged as held and once in its natural
    unresearched state, and the two produce different sentences: the held
    branch's own wording against _keyed's generic one. That is what keeps the
    three-distinct-stories assertion meaningful with two real countries.

    This is the assertion that would fail if the detail enrichment in
    _payment_regimes were ever deleted and the probe fell back to _keyed's
    generic MISSING sentence for all three alike.
    """
    dimension = "payment.prompt_payment_regime"
    monkeypatch.setattr(payment_clock_data, "NO_REGIME_HELD", frozenset({"JP"}))
    held = _one("JP", dimension)
    monkeypatch.undo()

    br = _one("BR", dimension)
    jp = _one("JP", dimension)
    assert br.verdict == cc.MISSING
    assert held.verdict == cc.MISSING
    assert jp.verdict == cc.MISSING
    assert "different_shape" in br.detail
    assert "held" in held.detail
    details = {br.detail, held.detail, jp.detail}
    assert len(details) == 3, f"expected three distinct stories, got {details}"


@pytest.mark.parametrize("country", ["RU", "CN"])
def test_the_researched_countries_have_a_payment_regime_of_their_own(country):
    """Fails on the tree before the rows were added, which is the point.

    RU and CN sat in NO_REGIME_HELD, so this dimension came back MISSING for
    both. Holding was the honest state while the search had not been run
    against the right instrument; it stops being honest once it has. A country
    that regresses to MISSING here has lost its row, not merely its research.
    """
    got = _one(country, "payment.prompt_payment_regime")
    assert got.verdict == cc.COVERED, f"{country}: {got.detail}"


def _one(country: str, dimension: str) -> cc.DimensionReport:
    report = cc.country_coverage(country)
    found = [d for d in report.dimensions if d.dimension == dimension]
    assert len(found) == 1, f"{dimension} is not in the manifest"
    return found[0]


# --------------------------------------------------------------------------- #
# Calendars are four registries and the manifest must keep them four
# --------------------------------------------------------------------------- #


def test_the_calendar_registries_are_probed_separately_and_from_separate_sources():
    """They were written independently and have disagreed; one row would hide that."""
    cal = [d for d in cc.country_coverage("CA").dimensions if d.dimension.startswith("calendar.")]
    assert len(cal) >= 4, f"expected four calendar registries, found {[d.dimension for d in cal]}"
    sources = [d.source for d in cal]
    assert len(set(sources)) == len(sources), f"two calendar probes read the same source: {sources}"


def test_the_calendar_registries_do_not_all_agree_about_every_country():
    """Records that coverage is uneven across the four.

    If this ever fails because every country resolves the same way in all four,
    that is not a regression: it means the calendars have been unified and this
    manifest should collapse them into one dimension. Read the failure that way.
    """
    disagreements = []
    for code in _SWEEP:
        cal = [d for d in cc.country_coverage(code).dimensions if d.dimension.startswith("calendar.")]
        answered = {d.verdict for d in cal if d.verdict != cc.UNRESOLVED}
        if len(answered) > 1:
            disagreements.append(code)
    assert disagreements, "the four calendar registries agreed everywhere; consider collapsing the dimension"


# --------------------------------------------------------------------------- #
# Reading a registry without executing its module
# --------------------------------------------------------------------------- #


def test_a_renamed_registry_is_unresolved_rather_than_read_from_stale_source():
    with pytest.raises(LookupError, match="not defined at module level"):
        cc._module_level_node("app.modules.boq.service", "_AACE_CLASSES_RENAMED_BY_THIS_TEST")


def test_the_source_reader_refuses_modules_outside_the_app_package():
    with pytest.raises(LookupError, match="outside the app package"):
        cc._source_of("os.path")


def test_the_report_says_which_method_answered():
    """A source parse is weaker evidence than an import and has to be labelled."""
    for d in cc.country_coverage("CA").dimensions:
        assert d.method, f"{d.dimension} did not say how it resolved"


def test_the_country_code_is_normalised():
    assert cc.country_coverage("ca").country_code == "CA"
    assert cc.country_coverage(" us ").country_code == "US"


# --------------------------------------------------------------------------- #
# A shared row is a limit, and a limit nobody counts is one that gets
# rediscovered rather than remembered
# --------------------------------------------------------------------------- #


def test_the_shared_row_census_is_taken_over_the_axis_and_not_over_the_cohort():
    """The figure must not move when the list of countries somebody asks about does.

    Drawn from _COHORT this same fact would read as 2, because the cohort holds
    DE and SA and none of the other six countries on a shared row. The register
    would then print a number that grows whenever the cohort does, which is the
    failure mode the module's own prose warns about two paragraphs further up.
    The assertion that catches it is the one on AT, BH, CH, KW, OM and QA: they
    are on the axis, they are on a shared row, and they are in no cohort here.
    """
    census = cc.shared_calendar_rows()
    assert census.on_axis == 18, f"the axis moved: {census.on_axis}"
    assert len(census.on_shared_row) == 8, f"expected 8 on a shared row, got {census.on_shared_row}"
    assert set(census.shared) == {"DACH", "GULF"}, f"the shared rows moved: {sorted(census.shared)}"
    off_cohort = set(census.on_shared_row) - set(_COHORT)
    assert off_cohort == {"AT", "BH", "CH", "KW", "OM", "QA"}, (
        f"the census looks drawn from the cohort rather than from the registry: {off_cohort}"
    )
    assert "8 of 18" in census.summary(), census.summary()


def test_the_two_registry_figures_are_separate_measurements_of_the_same_axis():
    """Sixteen of eighteen and eight of eighteen are different facts, and both are quoted.

    Sixteen is how many countries on the axis are not keys of the table at all,
    which is why the probe is forbidden from reading the table. Eight is how
    many share their row, which is the limit the register prints. They
    decompose exactly: eight are only spelled differently, eight actually share.
    Swapping one number for the other in a sentence would leave every other
    check in this file green, so the arithmetic is asserted rather than trusted.
    """
    calendars, _resolve, axis, _method = cc._schedule_registry()
    not_a_key = {code for code in axis if code not in calendars}
    shared = set(cc.shared_calendar_rows().on_shared_row)
    assert len(not_a_key) == 16, f"countries missing from the table keys moved: {sorted(not_a_key)}"
    assert len(shared) == 8, f"countries on a shared row moved: {sorted(shared)}"
    assert shared < not_a_key, "a country on a shared row was also a table key; the decomposition changed"
    assert len(not_a_key - shared) == 8, f"the 8 + 8 = 16 decomposition broke: {sorted(not_a_key - shared)}"


def test_a_shared_row_is_named_on_the_country_report_and_counted_in_its_summary():
    """Named where one country is read, counted where the country is summarised."""
    de = _one("DE", "calendar.schedule_regions")
    assert de.verdict == cc.COVERED, f"DACH is a real regional week, not a stand-in: {de.detail}"
    assert de.shares_row_with == ("AT", "CH"), de.shares_row_with
    assert cc.SHARED_ROW in de.detail, de.detail

    sa = _one("SA", "calendar.schedule_regions")
    assert sa.shares_row_with == ("BH", "KW", "OM", "QA"), sa.shares_row_with

    us = _one("US", "calendar.schedule_regions")
    assert us.verdict == cc.COVERED, us.detail
    assert us.shares_row_with == (), f"US has the US row to itself: {us.shares_row_with}"
    assert cc.SHARED_ROW not in us.detail, us.detail

    assert "1 on a shared row" in cc.country_coverage("DE").summary()
    assert "0 on a shared row" in cc.country_coverage("US").summary()


def test_the_census_reads_the_same_registry_when_the_import_is_gone(monkeypatch):
    """The registry figure survives the same missing database the probe does."""
    live = cc.shared_calendar_rows()
    assert live.method == "import"

    monkeypatch.setitem(sys.modules, _SCHEDULE_SERVICE, None)
    off = cc.shared_calendar_rows()
    assert off.method.startswith("source"), f"an isolated read must not be labelled {off.method!r}"
    assert off.shared == live.shared, f"{off.shared} != {live.shared}"
    assert off.on_own_row == live.on_own_row, f"{off.on_own_row} != {live.on_own_row}"


# --------------------------------------------------------------------------- #
# A probe that goes quiet has stopped measuring, and says so in a way that reads
# like a small denominator rather than like a hole
# --------------------------------------------------------------------------- #


def test_no_dimension_is_unresolved_anywhere_in_the_cohort():
    """No dimension fails to read its registry, for any country in the cohort.

    This is a floor, not the guard. It passes on a tree where the schedule probe
    is broken, because pytest boots a database and the probe's import therefore
    succeeds here and nowhere else. Read a failure of this test as "some probe
    lost its registry"; read the test below as the one that checks the probe
    still answers when the import is the thing that went away.
    """
    silent: dict[str, list[str]] = {}
    for code in _COHORT:
        for d in cc.country_coverage(code).by_verdict(cc.UNRESOLVED):
            silent.setdefault(d.dimension, []).append(f"{code}: {d.detail}")
    assert not silent, f"dimensions that could not read their registry: {silent}"


def test_the_schedule_probe_still_answers_when_its_module_will_not_import(monkeypatch):
    """The probe answers off a cluster, where its module cannot be imported.

    Importing app.modules.schedule.service reaches app.database, which builds an
    engine at import time and raises without a PostgreSQL URL. That is the
    ordinary state of a developer machine with nothing running, and it is the
    state the probe was silent in for every country while the suite stayed green.

    Putting None in sys.modules makes the import raise ModuleNotFoundError, which
    is the same shape of failure and does not need the database taken away from
    the rest of the session.
    """
    monkeypatch.setitem(sys.modules, _SCHEDULE_SERVICE, None)
    got = _one("DE", "calendar.schedule_regions")
    assert got.verdict != cc.UNRESOLVED, f"the probe went silent without its import: {got.detail}"
    assert got.method.startswith("source"), f"a read of the file on disk must not be labelled {got.method!r}"
    assert got.population, "the probe answered without naming the regions it read"


def test_the_isolated_read_and_the_import_agree_about_every_country(monkeypatch):
    """The fallback path returns what the import path returns, country by country.

    This is the test that makes the fix honest rather than convenient. An edit
    that widens a probe until it answers can be told from one that reads the
    registry correctly by exactly this: the answers off the cluster have to be
    the answers the live module gives, including the ones that are not COVERED.
    """
    live = {code: _one(code, "calendar.schedule_regions") for code in _COHORT}
    assert {d.method for d in live.values()} == {"import"}, "this test needs the import path to be the live one"
    assert len({d.verdict for d in live.values()}) > 1, "one verdict everywhere; this proves nothing about agreement"

    monkeypatch.setitem(sys.modules, _SCHEDULE_SERVICE, None)
    disagreed = {
        code: (live[code].verdict, off.verdict)
        for code in _COHORT
        if (off := _one(code, "calendar.schedule_regions")).verdict != live[code].verdict
    }
    assert not disagreed, f"the isolated read answered differently from the import: {disagreed}"


def test_the_schedule_probe_is_unresolved_when_the_registry_itself_is_renamed(monkeypatch):
    """A renamed registry is a finding about the tree, not something to route around.

    The probe has two ways to reach the calendars and must not use the second to
    paper over a symbol the first proved is gone. Here the import succeeds and
    the name does not exist, so the answer has to be UNRESOLVED rather than a
    confident one assembled from the file on disk.
    """
    import app.modules.schedule.service as svc

    monkeypatch.delattr(svc, "WORK_CALENDARS", raising=True)
    got = _one("DE", "calendar.schedule_regions")
    assert got.verdict == cc.UNRESOLVED, f"a missing registry was answered anyway: {got.verdict} / {got.detail}"
