"""Combined tax rates: does the shipped data say how two rates add up?

These tests read ``seed_data/tax_configurations.json`` directly rather than a
database, because the seed file is what a new installation gets and it is the
thing that has to be right. They exist to stop one specific bug.

Canada levies a federal rate and, in most provinces, a provincial one, and the
two combine in two opposite ways. A harmonised rate REPLACES the federal rate,
so Ontario is 13 % and not 5 + 13. A separate provincial rate STACKS on it, so
British Columbia is 5 + 7. Before the ``combination`` column, nothing in a row
said which, and the obvious implementation - federal plus my province - gives
the right answer in British Columbia and an 18 % invoice in Ontario. A bug that
is correct in the province you happened to test in is a bug that ships.

The rule that decides replace-versus-stack is therefore read out of the data,
never written here. ``_combined_rate`` below branches on ``combination`` and on
nothing else; it does not know that HST is harmonised, and if every row were
mislabelled it would happily return the wrong numbers. That is deliberate:
these tests are a check on the data, so the data has to be able to fail them.
``test_marking_ontario_as_stacking_breaks_the_published_figure`` proves it can.

One honest weakness. There is no jurisdiction column - the province lives in
``tax_code`` as a naming convention - so ``_jurisdiction`` parses it, and the
convention is not even uniform between countries. That is recorded in the
helper rather than papered over.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.modules.i18n_foundation.models import TAX_COMBINATIONS

_SEED = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "modules"
    / "i18n_foundation"
    / "seed_data"
    / "tax_configurations.json"
)

# Published combined rates a quantity surveyor would recognise, by province.
# Sources are the CRA GST/HST rate tables, Revenu Quebec, and the provincial
# finance ministries; the working is in docs/strategy. Alberta appears because
# a province with no provincial tax is the case a "federal plus provincial"
# implementation gets right by accident, so it proves nothing on its own and
# is here to keep the federal row honest.
_CANADA_PUBLISHED = {
    "ON": Decimal("13"),
    "NS": Decimal("14"),
    "NB": Decimal("15"),
    "NL": Decimal("15"),
    "PE": Decimal("15"),
    "QC": Decimal("14.975"),
    "BC": Decimal("12"),
    "SK": Decimal("11"),
    "MB": Decimal("12"),
    "AB": Decimal("5"),
}


def _rows() -> list[dict]:
    return json.loads(_SEED.read_text(encoding="utf-8"))


def _active(rows: list[dict], country: str, on_date: str) -> list[dict]:
    """Rows of ``country`` whose effective window contains ``on_date``.

    Dates are ISO strings and compare lexicographically, which is how the
    repository selects them too.
    """
    out = []
    for row in rows:
        if row["country_code"] != country:
            continue
        start, end = row["effective_from"], row["effective_to"]
        if start is not None and start > on_date:
            continue
        if end is not None and end < on_date:
            continue
        out.append(row)
    return out


def _jurisdiction(row: dict) -> str | None:
    """The sub-national code a row belongs to, or None for a country-wide row.

    This is the weak point and it is worth naming. The table has no
    jurisdiction column, so the only place a province has ever been recorded
    is inside ``tax_code``, by convention - and the convention differs by
    country. Canada writes the tax first (``HST_ON``, ``PST_BC``), the United
    States writes the state first (``CA_SALES``). Neither is enforced.
    """
    code = row["tax_code"] or ""
    if row["combination"] in ("national", "federal"):
        return None
    if row["country_code"] == "CA":
        return code.rsplit("_", 1)[-1]
    if row["country_code"] == "US":
        return code.split("_", 1)[0]
    raise AssertionError(f"no jurisdiction convention for country {row['country_code']!r}")


def _combined_rate(rows: list[dict], country: str, jurisdiction: str, on_date: str) -> Decimal:
    """Total rate payable in one jurisdiction, decided only by ``combination``."""
    active = _active(rows, country, on_date)

    federal = [r for r in active if r["combination"] == "federal"]
    local = [
        r
        for r in active
        if r["combination"] in ("replaces_federal", "stacks_on_federal") and _jurisdiction(r) == jurisdiction
    ]

    replacing = [r for r in local if r["combination"] == "replaces_federal"]
    if replacing:
        assert len(replacing) == 1, f"{country}/{jurisdiction} has {len(replacing)} replacing rates on {on_date}"
        return Decimal(replacing[0]["rate_pct"])

    total = sum((Decimal(r["rate_pct"]) for r in federal), Decimal("0"))
    return total + sum((Decimal(r["rate_pct"]) for r in local), Decimal("0"))


# ── The field exists and every row states it ────────────────────────────────


def test_every_row_states_how_it_combines() -> None:
    """No row is allowed to stay silent; silence is the defect being fixed."""
    rows = _rows()

    missing = [r for r in rows if not r.get("combination")]

    assert missing == [], f"{len(missing)} rows carry no combination"


def test_no_row_invents_a_combination_the_model_does_not_know() -> None:
    rows = _rows()

    unknown = sorted({r["combination"] for r in rows} - set(TAX_COMBINATIONS))

    assert unknown == []


def test_a_country_has_at_most_one_federal_rate() -> None:
    """Two federal rows would make the stacking arithmetic ambiguous."""
    counts: dict[str, int] = {}
    for row in _rows():
        if row["combination"] == "federal" and row["effective_to"] is None:
            counts[row["country_code"]] = counts.get(row["country_code"], 0) + 1

    assert [cc for cc, n in counts.items() if n > 1] == []


def test_a_stacking_or_replacing_row_has_a_federal_row_to_refer_to() -> None:
    """``stacks_on_federal`` in a country with no federal row means nothing."""
    rows = _rows()
    federal_countries = {r["country_code"] for r in rows if r["combination"] == "federal"}

    orphans = sorted(
        {
            f"{r['country_code']}/{r['tax_code']}"
            for r in rows
            if r["combination"] in ("replaces_federal", "stacks_on_federal")
            and r["country_code"] not in federal_countries
        }
    )

    assert orphans == []


def test_no_row_that_names_a_subdivision_calls_itself_country_wide() -> None:
    """Row eighty is the risk this cannot fully close, so it closes what it can.

    The 79 shipped rows are explicit, but ``TaxConfigCreate.combination``
    defaults to ``national`` and so does the column, which means a Canadian
    provincial row created through the API without the field inherits it. A
    ``national`` HST row falls out of ``_combined_rate``'s ``local`` list
    entirely and Ontario would compute as the federal 5 % alone - a third
    wrong answer, and a quieter one than 18 %.

    That default is deliberate: a new single-tier country genuinely is
    ``national``, and making the field required would break every existing
    client of an endpoint that has never had it. What this test does is stop
    the same mistake reaching the seed file, where it would be permanent and
    would ship to every new installation.

    The rule is the naming convention itself: in Canada and the United
    States, an underscore in ``tax_code`` is how a subdivision has always
    been written. Elsewhere it means a rate tier (``VAT_RED``), so the check
    is scoped to the two countries where the structure exists.
    """
    offenders = sorted(
        f"{r['country_code']}/{r['tax_code']}"
        for r in _rows()
        if r["country_code"] in ("CA", "US") and "_" in (r["tax_code"] or "") and r["combination"] == "national"
    )

    assert offenders == [], (
        f"{offenders} name a subdivision but claim to be country-wide. A row like that "
        f"is invisible to the combined-rate arithmetic rather than wrong in it."
    )


# ── The arithmetic, against published figures ───────────────────────────────


@pytest.mark.parametrize(("province", "published"), sorted(_CANADA_PUBLISHED.items()))
def test_the_combined_canadian_rate_matches_the_published_figure(province: str, published: Decimal) -> None:
    """Ontario 13, British Columbia 12, Quebec 14.975, Alberta 5."""
    combined = _combined_rate(_rows(), "CA", province, "2026-08-23")

    assert combined == published, f"{province}: computed {combined}, published {published}"


def test_nova_scotia_reads_the_rate_that_was_correct_before_the_cut() -> None:
    """The closed period is load-bearing: 15 % until 2025-03-31, 14 % after."""
    rows = _rows()

    assert _combined_rate(rows, "CA", "NS", "2025-03-31") == Decimal("15")
    assert _combined_rate(rows, "CA", "NS", "2025-04-01") == Decimal("14")


def test_the_california_combined_rate_adds_to_a_zero_federal_layer() -> None:
    """The United States has a federal row of 0 %, which is what a state adds to."""
    combined = _combined_rate(_rows(), "US", "CA", "2026-08-23")

    assert combined == Decimal("7.25")


# ── The control: prove the data can fail these tests ────────────────────────


def test_marking_ontario_as_stacking_breaks_the_published_figure() -> None:
    """Mutate the field and the arithmetic must convict.

    If this passes with Ontario marked as stacking, then ``combination`` is
    decorative and the tests above are only re-reading numbers somebody typed.
    18 % is the exact wrong answer the field exists to prevent, so it is
    asserted rather than merely being asserted as "not 13".
    """
    rows = _rows()
    ontario = [r for r in rows if r["tax_code"] == "HST_ON"]
    assert len(ontario) == 1
    ontario[0]["combination"] = "stacks_on_federal"

    combined = _combined_rate(rows, "CA", "ON", "2026-08-23")

    assert combined == Decimal("18")
    assert combined != _CANADA_PUBLISHED["ON"]


def test_dropping_the_federal_row_breaks_every_stacking_province() -> None:
    """The other half of the control: replacing provinces must not move."""
    rows = [r for r in _rows() if r["combination"] != "federal"]

    assert _combined_rate(rows, "CA", "BC", "2026-08-23") == Decimal("7")
    assert _combined_rate(rows, "CA", "ON", "2026-08-23") == Decimal("13")
