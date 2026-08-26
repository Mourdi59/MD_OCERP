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

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from app.core import country_coverage as cc
from app.core import country_registries as registries
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
# The distinction is only closed if it reaches the page a human reads
# --------------------------------------------------------------------------- #


def _reporter():
    """The command-line reporter, loaded by path because scripts/ is not a package."""
    path = Path(cc.__file__).resolve().parents[2] / "scripts" / "country_coverage.py"
    spec = importlib.util.spec_from_file_location("country_coverage_reporter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_page_says_how_the_verdicts_were_read_in_both_directions():
    """Provenance is stated in words, never implied by the absence of a mark.

    The per-verdict marks are printed only for a read of the file on disk, so a
    fully imported run carries none at all and is indistinguishable, on the
    page, from a run by a tool that never tracked provenance. That fully
    imported run is what a machine with a cluster produces, which is the exact
    environment this instrument's own defect survived in.
    """
    reporter = _reporter()

    clean = reporter._provenance({"import": 253})
    assert len(clean) == 1, clean
    assert "all 253 verdicts came from importing the live module" in clean[0]

    # A table parsed on purpose is not a degraded import and must not be called one.
    parsed = reporter._provenance({"import": 252, "source": 1})
    assert any("252 from importing the live module" in line for line in parsed), parsed
    assert not any("weaker evidence" in line for line in parsed), (
        f"a deliberate structural parse was reported as weaker evidence: {parsed}"
    )

    fell_back = reporter._provenance({"import": 230, "source (RuntimeError on import)": 23})
    assert any("230 from importing the live module" in line for line in fell_back), fell_back
    assert any("23 of those name an exception" in line for line in fell_back), fell_back
    assert any("weaker evidence" in line for line in fell_back), fell_back

    # A verdict that read nothing must not be totalled as one that read the module.
    nothing = reporter._provenance({"import": 90, "declared (no registry exists)": 9, "(none)": 2})
    assert any("90 from importing the live module" in line for line in nothing), nothing
    assert any("9 declared (no registry exists)" in line for line in nothing), nothing
    assert any("2 from nothing at all" in line for line in nothing), nothing
    assert not any("weaker evidence" in line for line in nothing), nothing

    # Two reasons to declare something get two clauses. One clause covering both
    # would still read as true, which is why this is asserted rather than left to
    # a reading of the code: the failure is a sentence that stays grammatical
    # while becoming false, and nothing about the output would look wrong.
    two = reporter._provenance(
        {
            "import": 90,
            "declared (no registry exists)": 9,
            "declared (the registry is a service we do not call)": 4,
        }
    )
    assert any("9 declared (no registry exists)" in line for line in two), two
    assert any("4 declared (the registry is a service we do not call)" in line for line in two), two
    assert not any("13 declared" in line for line in two), (
        f"two reasons were merged into one clause and one of them is now described wrongly: {two}"
    )


def test_the_printed_census_names_its_provenance_on_the_import_path_too(monkeypatch, capsys):
    """End to end, on the path that used to print nothing about how it read.

    Asserted against the reporter's real output rather than against the field,
    because a method string that only a test ever reads closes nothing: the
    failure this instrument exists to prevent is a human being unable to tell a
    gap in the product from a gap in the instrument.
    """
    reporter = _reporter()
    # --ignore-unprobed because this test is about how the page labels its
    # provenance, and the registry census below it now fails the run on purpose.
    # Without the flag the assertions here would be riding on an exit code that
    # belongs to a different property.
    monkeypatch.setattr(sys, "argv", ["country_coverage.py", "DE", "--ignore-unprobed"])
    assert reporter.main() == 0

    out = capsys.readouterr().out
    assert "registry limits:" in out, out
    assert "[read by import]" in out, "the census line went unlabelled on the import path"
    assert "provenance:" in out, "the page never said how the verdicts were read"
    assert "from importing the live module" in out, out
    assert "declared (no registry exists)" in out, out


def test_the_page_names_the_interpreter_that_produced_it(monkeypatch, capsys):
    """The same tree prints a different page under a different interpreter.

    Nine countries came back with eighteen verdicts read from source under one
    interpreter and eighteen read from nothing at all under another, because a
    dependency was installed in one and missing in the other. Provenance that
    names the method but not the interpreter stops one level above the thing
    that actually decided the page, so this line is printed on every run.
    """
    reporter = _reporter()
    monkeypatch.setattr(sys, "argv", ["country_coverage.py", "DE", "--ignore-unprobed"])
    reporter.main()

    out = capsys.readouterr().out
    assert "interpreter:" in out, "the page never said which interpreter produced it"
    assert sys.executable in out, out
    # Healthy runs too. A line printed only when something is wrong makes its
    # absence carry meaning, which is the defect this whole lane started from.
    assert "instrument healthy" in out, "expected a healthy run here; the assertion above is now untested"


def test_the_unhealthy_exit_names_the_package_and_not_only_the_exception():
    """A reader should not have to decode ModuleNotFoundError into an action."""
    reporter = _reporter()

    details = [
        "probe raised ModuleNotFoundError: No module named 'hijridate'",
        "probe raised ModuleNotFoundError: No module named 'hijridate'",
        "probe raised RuntimeError: no cluster",
    ]
    assert reporter._missing_packages(details) == ["hijridate"], "one missing package, named once"

    # A submodule failure names the distribution somebody would install, not the
    # dotted path, which is not a thing that can be installed.
    assert reporter._missing_packages(["No module named 'lxml.etree'"]) == ["lxml"]
    assert reporter._missing_packages(["probe raised RuntimeError: no cluster"]) == []


def test_a_probe_that_read_nothing_does_not_report_that_it_imported():
    """The method default is "import", so silence there is a claim, not an absence.

    security_of_payment has no registry to import and is declared from a reading
    of the tree, and a probe that raised read nothing at all. Both used to
    inherit the default and be counted on the printed page among the verdicts
    taken from the live module, which is the same small untruth the schedule
    probe carried on its failure path.
    """
    absent = _one("DE", "security_of_payment.deadlines")
    assert absent.verdict == cc.ABSENT
    assert absent.method.startswith("declared"), f"a probe with nothing to import reported {absent.method!r}"
    # The reason has to be on the verdict, because the reporter groups on this
    # string and prints it verbatim rather than supplying a reason of its own.
    assert absent.method != "declared", "a declared verdict must say why it was declared"

    raised = cc._run("probe.that.raises", _raise_on_purpose, "DE")
    assert raised.verdict == cc.UNRESOLVED
    assert raised.method == "(none)", f"a probe that raised reported {raised.method!r}"


def _raise_on_purpose(country: str):
    raise RuntimeError("staged failure")


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


# --------------------------------------------------------------------------- #
# The denominator
#
# The defect these close: a coverage figure whose divisor is the set of probes
# somebody already wrote is a measurement of the instrument. A registry nobody
# probed was absent from the divisor as well as the dividend, so the percentage
# stayed flattering and moved only when a probe was added. The divisor is now
# walked out of the tree, and these gate that it stays walked.
# --------------------------------------------------------------------------- #


def test_the_denominator_moves_when_the_tree_gains_a_registry(monkeypatch):
    """The property the whole change exists for.

    A registry appearing in the product has to move the figure with nobody
    editing a list. Staged by handing the census one extra discovered registry,
    which is what the walk would return the day somebody adds one.
    """
    before = cc.registry_census()
    invented = registries.DiscoveredRegistry(
        symbol="app.modules.invented.thing.SOME_REGISTRY",
        codes=("DE", "FR", "NL"),
        entries=3,
        kind="literal",
        path="app/modules/invented/thing.py",
        iso_hits=3,
    )
    monkeypatch.setattr(cc, "discover_registries", lambda: (*before.discovered, invented))

    after = cc.registry_census()
    assert after.denominator == before.denominator + 1, (
        f"a new registry did not move the denominator: {before.denominator} -> {after.denominator}"
    )
    assert invented in after.unprobed, "a registry nobody probes was not reported as unprobed"


def test_a_registry_no_probe_reads_is_named_rather_than_skipped():
    """Skipping is the failure. Being named is the fix.

    An unprobed registry reported as neither covered nor missing is the shape of
    defect this file exists to prevent, one level up: it is not a country that
    went unanswered but a whole axis that was never asked about.
    """
    census = cc.registry_census()
    assert census.unprobed, "nothing is unprobed, which would mean the walk found less than the probes read"
    assert all(r.symbol not in census.covered for r in census.unprobed)
    assert census.probed + len(census.unprobed) == census.denominator, census.summary()


def test_the_denominator_is_the_union_and_not_the_walk_alone():
    """Four probes read registries the walk structurally cannot see.

    NOTICE_PERIODS is keyed by contract standard, CREDENTIAL_TYPES is a closed
    vocabulary, _AACE_CLASSES is a ladder of integers and LaborRateTemplate is a
    model column. None holds a country-shaped token, so counting only what the
    walk found would drop those four out of the universe and make the ratio a
    fact about the walk instead of about the product.
    """
    census = cc.registry_census()
    walked = {r.symbol for r in census.discovered}
    invisible = census.covered - walked
    assert invisible, "every covered symbol is discoverable; this test no longer guards anything"
    assert census.denominator == len(walked | census.covered)
    assert census.denominator > len(walked), "the union is no larger than the walk, so the probes were dropped"


def test_every_symbol_a_probe_claims_to_cover_is_really_there():
    """A probe naming a registry that has moved is how a rename goes quiet.

    The census subtracts on these strings, so a stale one silently inflates the
    probed count: the registry is still discovered under its new name and lands
    in unprobed, while the old name keeps being counted as covered.
    """
    root = Path(cc.__file__).resolve().parents[2]
    missing = []
    for symbol in sorted(cc.covered_symbols()):
        if "/" in symbol:
            if not (root / symbol).is_file():
                missing.append(symbol)
            continue
        dotted, _, name = symbol.rpartition(".")
        try:
            cc._module_level_node(dotted, name)
            continue
        except Exception:  # noqa: BLE001 - the parse is only the first of two ways to look
            pass
        try:
            module = importlib.import_module(dotted)
        except Exception:  # noqa: BLE001 - a module that will not import cannot vouch for the name
            missing.append(symbol)
            continue
        if not hasattr(module, name):
            missing.append(symbol)
    assert not missing, f"probes name registries that are not in the tree: {missing}"


def test_discovery_reads_the_shape_of_the_value_and_not_the_name_of_the_field():
    """The wrong-key trap, gated.

    The field name axis in this tree is at least six wide - country_code,
    country_iso, iso_code, country, jurisdiction, code. A first pass at this
    inventory keyed on ``country_code`` and read countries.json, the largest
    country registry in the product, as ZERO countries, because that file spells
    it ``iso_code``; the same pass missed CWICR_V3_CATALOGUES entirely, because
    that one spells it ``country_iso``. Both are asserted here by their awkward
    spelling, so a pass that goes back to looking for a name fails.
    """
    found = {r.symbol: r for r in registries.discover_registries()}

    seeded = found.get("app/modules/i18n_foundation/seed_data/countries.json")
    assert seeded is not None, "the 198-row country list was not discovered; the pass is keying on a field name"
    assert seeded.country_count > 150, seeded.country_count

    catalogue = found.get("app.modules.costs.cwicr_v3_catalogue.CWICR_V3_CATALOGUES")
    assert catalogue is not None, "the catalogue registry spells its field country_iso and was not discovered"
    assert catalogue.country_count > 30, catalogue.country_count


def test_the_walk_finds_the_registry_an_iso_filter_would_have_lost():
    """Why there is no country filter on the discovery pass, recorded as a number.

    WORK_CALENDARS has exactly three country-shaped keys among its thirteen -
    RU, UK and US - and "UK" is not a country code, so intersecting the pass with
    the product's own country list leaves two and drops the table below the
    threshold. The filter would lose the very registry the schedule probe exists
    to read, which is the measured reason this pass favours recall and states its
    noise instead of suppressing it.
    """
    found = {r.symbol: r for r in registries.discover_registries()}
    calendars = found.get("app.modules.schedule.service.WORK_CALENDARS")
    assert calendars is not None, "the work calendars fell out of the walk"
    assert calendars.country_count == registries.MIN_CODES, (
        f"WORK_CALENDARS now has {calendars.country_count} country-shaped keys, not {registries.MIN_CODES}; "
        "the margin this threshold was chosen for has moved and the choice needs remaking"
    )


def test_the_five_claimed_axes_are_probed():
    """Units, regional packs, cost classification, the second tax table, e-invoicing.

    Each is an axis the product claims per-country support on, and each was
    reachable from the tree while no dimension asked it anything.
    """
    named = set(cc.dimensions())
    for dimension in (
        "units.measurement_system",
        "packs.regional_coverage",
        "cost_classification.catalogue_standard",
        "tax.vat_rate_table",
        "einvoice.clearance_regime",
    ):
        assert dimension in named, f"{dimension} is not in the manifest"


def test_the_two_tax_registries_are_probed_separately_and_disagree():
    """Collapsing them would hide the drift their own comment warns about.

    tax_configurations.json carries forty-one countries and core/tax._RAW
    twenty-three. They are two hand-kept tables of different scope, so a country
    covered by one and not the other is the finding, and one merged "tax"
    dimension could not report it.
    """
    seeded = {c: _one(c, "tax.rates").verdict for c in _COHORT}
    table = {c: _one(c, "tax.vat_rate_table").verdict for c in _COHORT}
    assert cc.UNRESOLVED not in set(seeded.values()) | set(table.values())
    disagree = {c for c in _COHORT if seeded[c] != table[c]}
    assert disagree, (
        "the two tax registries agreed about every country. Either one of them is not being read, or "
        "somebody has genuinely reconciled the two tables - and that is a fix, not a regression. If it "
        "is the second, delete this test; do not put drift back to make it pass."
    )


def test_the_units_probe_asks_the_resolver_rather_than_pack_membership():
    """Membership of a pack's country list is not the question a caller asks.

    resolve_measurement_system returns None both when no pack claims a country
    and when several claim it and disagree, and the difference decides whether
    anybody has work to do. A country the packs do claim must therefore never
    come back MISSING, which is what reading the lists alone would report.
    """
    claimed = cc._pack_countries()
    assert claimed, "no pack claims any country; this test proves nothing"
    for code in sorted(claimed):
        got = _one(code, "units.measurement_system")
        assert got.verdict in (cc.COVERED, cc.FALLBACK), (
            f"{code} is claimed by a pack and the units probe called it {got.verdict}: {got.detail}"
        )


def test_the_reporter_fails_on_a_registry_nobody_probes(monkeypatch, capsys):
    """Loud, not skipped - and the flag that says so is the only way past it."""
    reporter = _reporter()

    monkeypatch.setattr(sys, "argv", ["country_coverage.py", "DE"])
    assert reporter.main() == 3, "an unprobed registry did not get its own exit code"
    out = capsys.readouterr().out
    assert "INSTRUMENT INCOMPLETE" in out, out
    assert "NO PROBE" in out, "the unprobed registries were counted but never named"
    assert "registries:" in out, "the page never printed the derived denominator"

    monkeypatch.setattr(sys, "argv", ["country_coverage.py", "DE", "--ignore-unprobed"])
    assert reporter.main() == 0, "the escape hatch did not let the rest of the page through"


def test_every_report_site_states_how_it_was_read():
    """A field recording how something was learned must never guess.

    ``method`` defaults to "import", the strongest value it can take, and that
    default has already produced a false claim on this page once: report sites
    inherited it while importing nothing, and the provenance line then said
    seventy-two of ninety-nine verdicts came from the live module when the true
    figure was sixty-three. Adding probes multiplies report sites, so the
    default gets more chances to be wrong with every dimension added.

    The default is left alone deliberately. Changing it would move the
    reporter's bucket arithmetic, which prints on every run of a blocking lane,
    to buy what this test buys for nothing: a site that forgets is caught here,
    at the point somebody can still fix it, rather than relabelled at runtime.
    """
    source = Path(cc.__file__).read_text(encoding="utf-8")
    silent = [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "DimensionReport"
        and "method" not in {kw.arg for kw in node.keywords}
    ]
    assert not silent, (
        f'DimensionReport built without method= at line(s) {silent}. It will inherit "import" and be '
        "counted on the page as evidence taken from the live module. Say how the verdict was really read."
    )


def test_the_near_miss_flag_describes_and_never_subtracts():
    """The suppression list, refused again in the one place it could sneak back.

    Two uppercase letters is also a US state, a data unit and a schedule
    relationship type, so the walk catches things that are not country
    registries. Naming them on the page is the answer; dropping them is not.
    The moment a near miss stops being counted, the divisor is once more a
    hand-kept list of what somebody decided was interesting, which is the whole
    defect this census exists to end.
    """
    census = cc.registry_census()
    near = [r for r in census.discovered if r.is_near_miss]
    assert near, "nothing is a near miss; either the tree changed or the annotation is not being computed"
    assert all(r.symbol in {d.symbol for d in census.discovered} for r in near)
    assert census.denominator == len({r.symbol for r in census.discovered} | census.covered), (
        "the denominator no longer counts every discovered registry, so something is being skipped"
    )
    counted = {r.symbol for r in census.discovered}
    assert all(r.symbol in counted for r in near), "a near miss fell out of the count it is supposed to stay in"


def test_the_walk_caught_a_list_of_us_states_and_the_page_says_so():
    """The measured example that made the annotation necessary.

    us_pack's config carries FL, NY, TX and WA beside its country list, so the
    shape rule reads six country-shaped tokens where the product means two. It
    is worth pinning because a probe already covers this registry: it never
    reaches the NO PROBE list, so before the near-miss section nothing on the
    page mentioned it at all, and a reader had no way to learn that four of
    those six were states. An unannotated pass would have carried the error
    silently, which is the failure mode the whole task is about.
    """
    found = {r.symbol: r for r in registries.discover_registries()}
    pack = found.get("app.modules.us_pack.config.PACK_CONFIG")
    assert pack is not None, "the us pack config fell out of the walk"
    assert {"FL", "NY", "TX", "WA"}.issubset(set(pack.non_iso)), pack.non_iso
    assert pack.is_near_miss, f"{pack.iso_purity:.0%} ISO and not flagged; the reader is never told about the states"
    assert pack.symbol in cc.covered_symbols(), (
        "this registry is probed, which is what makes the annotation the only way to see it"
    )


def test_a_registry_names_the_file_it_was_found_in():
    """A red lane nobody can act on gets silenced instead of fixed."""
    root = Path(cc.__file__).resolve().parents[2]
    for registry in registries.discover_registries():
        assert registry.path, f"{registry.symbol} was discovered without a path"
        assert (root / registry.path).is_file(), f"{registry.symbol} names {registry.path}, which is not a file"


def test_the_reference_country_list_refuses_to_arrive_nearly_empty():
    """A count from a reader with a fallback is a fact about the reader.

    If the shipped list moved or its field names changed, an empty reference
    set would quietly mark every registry in the tree a near miss and the page
    would read as though the product had no countries at all.
    """
    assert len(registries.iso_codes()) >= registries._MIN_ISO_CODES
    assert "DE" in registries.iso_codes() and "US" in registries.iso_codes()
    assert "UK" not in registries.iso_codes(), "UK is not an ISO alpha-2 code and must not be in the reference set"


def test_the_pack_list_is_the_products_own_and_not_a_copy_of_it():
    """Two hand-kept mirrors of one registry always drift, and this pair did.

    The covers list for the pack probes was written out by hand and named
    twelve modules. A thirteenth was added to the product's own
    PACK_CONFIG_MODULES while this file still said twelve, so the product would
    have loaded a pack, that pack would have claimed countries on the coverage
    page, and the census would still have counted its config as a registry
    nobody probes. A numerator kept as a copy has exactly the defect the
    denominator was rebuilt to remove, one column to the left.

    Asserted as set equality against the product rather than against a number,
    because a count would pass the day one module was swapped for another.
    """
    from app.core.regional_packs import PACK_CONFIG_MODULES

    assert set(cc._PACK_CONFIGS) == {f"{module}.PACK_CONFIG" for module in PACK_CONFIG_MODULES}, (
        "the pack probes name a different set of configs than the product loads; derive this list, do not copy it"
    )
    assert set(cc._PACK_CONFIGS) <= cc.covered_symbols()
