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

import pytest

from app.core import country_coverage as cc

# Countries with enough spread to exercise the verdicts: a large market with
# broad coverage, one known to be partly covered, one Gulf state, two Asian.
_SWEEP = ("US", "CA", "DE", "GB", "AE", "CN", "IN", "BR", "SA", "NL", "JP", "MX")


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


def test_the_schedule_resolver_answers_when_the_app_is_importable():
    """On a laptop with no cluster this probe declines to guess; here it must not.

    Without this, the FALLBACK path would never be exercised by anything: the
    probe would report UNRESOLVED in every environment and the suite would go
    green over a verdict that had never once been produced.
    """
    got = _one("CA", "calendar.schedule_regions")
    assert got.verdict != cc.UNRESOLVED, f"the resolver was not importable even under the test harness: {got.detail}"


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


def test_a_missing_payment_regime_carries_a_reason_when_one_is_on_record():
    """The deliverable: a reader queries three MISSING countries and gets three
    different stories, not the same generic sentence three times.

    BR has a recorded NO_REGIME_DIFFERENT_SHAPE reason, CN is held pending
    research, and JP is simply unresearched, which is the default state for
    most of the world. This is the assertion that would fail if the detail
    enrichment in _payment_regimes were ever deleted and the probe fell back
    to _keyed's generic MISSING sentence for all three alike.
    """
    dimension = "payment.prompt_payment_regime"
    br = _one("BR", dimension)
    cn = _one("CN", dimension)
    jp = _one("JP", dimension)
    assert br.verdict == cc.MISSING
    assert cn.verdict == cc.MISSING
    assert jp.verdict == cc.MISSING
    assert "different_shape" in br.detail
    assert "held" in cn.detail
    details = {br.detail, cn.detail, jp.detail}
    assert len(details) == 3, f"expected three distinct stories, got {details}"


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
