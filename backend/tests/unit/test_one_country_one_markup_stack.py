# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One country, one markup stack, whichever engine you ask.

The platform has two markup engines with two different jobs.
:func:`app.modules.boq.service._calculate_markup_amounts` prices a bill's own
markup lines; :func:`app.modules.methodology.cascade.compute_cascade` prices a
company or project methodology. Two engines with different jobs is the intended
arrangement. Two engines that answer the same question differently is not, and
that is what this file exists to prevent.

It was not hypothetical. On a million of American direct cost the bill engine
returned 1,308,150 and the methodology engine returned 1,210,000, a gap of 7.5
percent, because the methodology catalogue shipped a three-step flat method
under the name "United States" while the regional table stated the seven-line
stack an American estimator would recognise. The fix was to derive one from the
other. This file is the part that keeps it derived: it recomputes every covered
country through both paths and fails on any disagreement the two rounding
conventions do not fully explain.

Two assertions, and they catch different regressions:

* Line for line. Same count, same order, same category, same rate, same base,
  and the base is checked against the translation rule stated independently
  here rather than against whatever the producer emitted. This is the assertion
  that makes a silent divergence structurally impossible: a rate edited on one
  side alone cannot survive it.
* Total against total, within a tolerance derived from the rounding conventions
  and asserted to be orders of magnitude below the defect it must catch.

These tests touch ``BOQMarkup`` and therefore SQLAlchemy, so they live here and
not under ``tests/unit/methodology/``, which is the standalone Python 3.11 lane.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.boq.markup_templates import (
    DEFAULT_MARKUP_TEMPLATES,
    NON_SINGLE_TAX_REGIONS,
    REGION_BY_COUNTRY,
    region_lines_for_country,
)
from app.modules.boq.models import BOQMarkup
from app.modules.boq.service import _calculate_markup_amounts
from app.modules.methodology.cascade import compute_cascade
from app.modules.methodology.templates import (
    NEUTRAL_METHOD_NOTE,
    TEMPLATES,
    build_cascade_spec_from_template,
)

# A million of direct cost split across the four leaf bases the flat mapping
# declares. The split is arbitrary; only the sum matters, because every step in
# every regional stack applies to the direct composite or to a running total,
# never to one resource type. A round million is used because it makes the
# American pair legible: 1,308,150 against 1,210,000.
_BASES: dict[str, Decimal] = {
    "labor": Decimal("400000"),
    "materials": Decimal("400000"),
    "equipment": Decimal("150000"),
    "subcontract": Decimal("50000"),
}
_DIRECT_COST = sum(_BASES.values(), Decimal("0"))

#: The seven-line American stack on a million, computed by hand from the
#: regional table: 8 + 7 + 5 + 1 percent of direct cost is 210,000; the bond at
#: 1.5 percent of 1,210,000 is 18,150; 5 + 3 percent of direct cost is 80,000.
#: This is the number the bill engine has always produced and the number the
#: methodology now has to agree with.
_US_TOTAL = Decimal("1308150")

#: What the "United States" methodology produced before the derivation: three
#: flat steps, 10 percent overhead then 10 percent profit, no general
#: conditions, no insurance, no bond, no contingency. Pinned so the size of the
#: defect stays on the record next to the tolerance that has to stay under it.
_US_TOTAL_BEFORE = Decimal("1210000")


def _derived_templates() -> list[dict[str, object]]:
    """Every catalogue template whose steps come from the regional table."""
    return [tpl for tpl in TEMPLATES if tpl.get("derived_from_region")]


def _template_for(country_code: str) -> dict[str, object]:
    """The derived template for a country. Exactly one, or the test is wrong."""
    matches = [tpl for tpl in _derived_templates() if tpl.get("country_code") == country_code]
    assert len(matches) == 1, f"expected one derived template for {country_code}, got {[t['slug'] for t in matches]}"
    return matches[0]


def _expected_bases(lines: list[dict[str, object]]) -> list[list[str]]:
    """The base each step must carry, stated from the markup rule directly.

    Deliberately not imported from the producer. ``direct_cost`` prices the
    direct cost alone; ``cumulative`` and its alias ``subtotal`` price the
    direct cost plus every line already added, which written out as explicit
    tokens is the direct composite followed by every preceding step key.
    """
    keys = [f"s{index + 1}_{line['category']}" for index, line in enumerate(lines)]
    bases: list[list[str]] = []
    for index, line in enumerate(lines):
        if str(line.get("apply_to", "direct_cost")).lower() in ("cumulative", "subtotal"):
            bases.append(["direct", *keys[:index]])
        else:
            bases.append(["direct"])
    return bases


def _boq_total(lines: list[dict[str, object]]) -> Decimal:
    """Price the same lines through the bill engine, as a seeded bill would."""
    markups = [
        BOQMarkup(
            name=str(line["name"]),
            markup_type=str(line.get("markup_type", "percentage")),
            category=str(line["category"]),
            percentage=str(line["percentage"]),
            fixed_amount=str(line.get("fixed_amount", "0")),
            apply_to=str(line.get("apply_to", "direct_cost")),
            sort_order=int(line["sort_order"]),  # type: ignore[arg-type]
            is_active=True,
        )
        for line in lines
    ]
    return _DIRECT_COST + sum((amount for _, amount in _calculate_markup_amounts(_DIRECT_COST, markups)), Decimal("0"))


def _tolerance(steps: int, decimals: int) -> Decimal:
    """The most the two rounding conventions can make the totals differ by.

    The cascade quantizes every step immediately and feeds the rounded amount
    forward; the bill engine carries full precision and quantizes once at the
    rollup. Each step can therefore differ by up to half a unit in the last
    place, and a later cumulative step applies its own rate to that difference,
    growing it by at most ``1 + rate`` per step. No rate in the regional table
    exceeds 30 percent, so ``steps * (quantum / 2) * 1.3 ** steps`` bounds it.
    """
    quantum = Decimal(1).scaleb(-decimals)
    return steps * (quantum / 2) * Decimal("1.3") ** steps


@pytest.mark.parametrize("region", sorted(DEFAULT_MARKUP_TEMPLATES))
def test_a_region_carries_one_tax_line_or_says_why_not(region: str) -> None:
    """One tax line per region, so one country VAT rate is a complete swap.

    That swap is how a single DACH stack serves Germany at 19, Austria at 20 and
    Switzerland at 8.1, and how the per-project override works on the bill side.
    A region with two tax lines cannot be served that way and a region with none
    has nothing to swap, so both have to be declared with a reason before they
    can ship. Otherwise a fifteenth region quietly takes one country's rate
    twice and the two engines start disagreeing again through the back door.
    """
    tax_lines = [line for line in DEFAULT_MARKUP_TEMPLATES[region] if line.get("category") == "tax"]
    if region in NON_SINGLE_TAX_REGIONS:
        assert len(tax_lines) != 1, f"{region} states a reason for not having one tax line, but it has one"
        assert NON_SINGLE_TAX_REGIONS[region].strip(), f"{region} needs a reason, not an empty string"
        return
    assert len(tax_lines) == 1, (
        f"{region} has {len(tax_lines)} tax lines. A country VAT rate can only stand in for one. "
        f"Add {region} to NON_SINGLE_TAX_REGIONS with the reason, or give it a single tax line."
    )


def test_every_mapped_country_is_a_country_the_catalogue_ships() -> None:
    """``REGION_BY_COUNTRY`` is falsifiable: no entry without a template.

    An unused mapping is not harmless. It reads as coverage the product does not
    have, and it makes the parity test below silently smaller than it looks.
    """
    derived = {tpl.get("country_code") for tpl in _derived_templates()}
    assert derived == set(REGION_BY_COUNTRY), (
        f"mapped but not derived: {sorted(set(REGION_BY_COUNTRY) - derived)}; "
        f"derived but not mapped: {sorted(derived - set(REGION_BY_COUNTRY))}"
    )


@pytest.mark.parametrize("country", sorted(REGION_BY_COUNTRY))
def test_the_derived_stack_matches_the_regional_table_line_for_line(country: str) -> None:
    """Same lines, same order, same rates, same bases. No tolerance here."""
    template = _template_for(country)
    lines = region_lines_for_country(country, vat_rate=template.get("vat_rate"))
    assert lines is not None
    steps = list(template["cascade_steps"])  # type: ignore[call-overload]

    assert len(steps) == len(lines), f"{country}: {len(steps)} steps against {len(lines)} regional lines"
    for step, line, expected_base in zip(steps, lines, _expected_bases(lines), strict=True):
        assert step["label"] == str(line["name"]), f"{country}: label drift on {step['key']}"
        assert step["category"] == str(line["category"]), f"{country}: category drift on {step['key']}"
        assert step["kind"] == "percentage"
        assert Decimal(str(step["rate"])) == Decimal(str(line["percentage"])), (
            f"{country}: rate drift on {step['key']}, "
            f"methodology says {step['rate']} and the regional table says {line['percentage']}"
        )
        assert step["base"] == expected_base, f"{country}: base drift on {step['key']}"


@pytest.mark.parametrize("country", sorted(REGION_BY_COUNTRY))
def test_both_engines_price_the_same_country_the_same(country: str) -> None:
    """The finish line: one country, two engines, one number."""
    template = _template_for(country)
    lines = region_lines_for_country(country, vat_rate=template.get("vat_rate"))
    assert lines is not None

    spec = build_cascade_spec_from_template(str(template["slug"]))
    cascade_total = compute_cascade(spec, _BASES).grand_total
    bill_total = _boq_total(lines)

    tolerance = _tolerance(len(lines), int(template["decimals"]))  # type: ignore[call-overload]
    assert abs(cascade_total - bill_total) <= tolerance, (
        f"{country}: the methodology says {cascade_total} and a bill says {bill_total} "
        f"on {_DIRECT_COST} of direct cost, which is more than rounding can explain"
    )


def test_the_american_gap_that_started_this_is_closed() -> None:
    """The named case, pinned with both numbers so the size stays on record."""
    spec = build_cascade_spec_from_template("united_states")
    cascade_total = compute_cascade(spec, _BASES).grand_total

    assert cascade_total == _US_TOTAL
    assert cascade_total != _US_TOTAL_BEFORE
    # The tolerance the parity test allows itself has to be negligible against
    # the defect it exists to catch, or a green run would prove nothing.
    assert _tolerance(7, 2) * 100 < _US_TOTAL - _US_TOTAL_BEFORE


def test_a_country_without_a_national_stack_does_not_claim_one() -> None:
    """The other half of the ruling: say in the code what these actually are.

    Thirty of the flat country templates describe markets the regional table has
    no convention for. They still ship, because the local currency and the local
    consumption-tax rate are real and useful. What they must not do is present
    three steps as a national cost-planning method, so every one of them carries
    the note and the derived ones carry none.
    """
    flat = [tpl for tpl in TEMPLATES if tpl.get("country_code") and not tpl.get("derived_from_region")]
    neutral = [tpl for tpl in flat if NEUTRAL_METHOD_NOTE in str(tpl.get("description", ""))]
    own_cascade = [tpl for tpl in flat if tpl not in neutral]

    assert neutral, "no neutral-method country templates found; the catalogue or this test moved"
    for tpl in own_cascade:
        steps = tuple(str(step.get("key")) for step in tpl["cascade_steps"])  # type: ignore[union-attr]
        assert steps != ("overhead", "profit", "vat"), (
            f"{tpl['slug']} ships the flat method under a country name without saying so. "
            f"Either derive it from the regional table or let the note be appended."
        )
    for tpl in _derived_templates():
        assert NEUTRAL_METHOD_NOTE not in str(tpl.get("description", "")), (
            f"{tpl['slug']} is derived from the regional table and must not also disclaim being national"
        )
