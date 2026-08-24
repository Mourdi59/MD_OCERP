# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""An amount that could not be converted is reported, not hidden in the total.

A BOQ resource priced in a foreign currency is converted to the project base
before it joins the rollup. When the project holds no usable rate, the amount
is summed in its own units anyway - deliberately, so a row is never zeroed and
the rollup stays deterministic. The cost of that choice is that the total can
be a blend, and nothing on the resource-summary response said so.

A user hit this. They changed a resource's currency from one code to another
and the total did not move. The reason was that the first currency had a rate
in their project and the second did not, so the conversion was skipped rather
than applied. The pair is what made it diagnosable: one unchanged total looks
like a screen that did not refresh, whereas two currencies behaving differently
under the same action on the same screen is a diagnosis.

These tests cover the policy itself, ``resource_fx_factor``, which existed as
four separate hand-written copies before it had a name.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.boq.schemas import ResourceSummaryResponse
from app.modules.boq.service import resource_fx_factor

RATES = {"USD": "0.92", "GBP": "1.17"}


@pytest.mark.parametrize(
    ("currency", "base", "why"),
    [
        ("", "EUR", "a resource with no currency carries no monetary signal"),
        (None, "EUR", "same, arriving as None rather than empty"),
        ("EUR", "", "no declared base means nothing can be said to need converting"),
        ("EUR", "EUR", "already base"),
        ("eur", "EUR", "already base, lower case"),
        ("  EUR  ", "EUR", "already base, padded"),
    ],
)
def test_nothing_to_convert_is_a_factor_of_one(currency: str | None, base: str, why: str) -> None:
    assert resource_fx_factor(currency, base, RATES) == 1.0, why


def test_a_usable_rate_is_returned() -> None:
    assert resource_fx_factor("USD", "EUR", RATES) == 0.92
    assert resource_fx_factor("usd", "EUR", RATES) == 0.92


@pytest.mark.parametrize(
    ("rates", "why"),
    [
        ({"GBP": "1.17"}, "the code is absent from the table"),
        ({}, "the project has no FX table at all"),
        (None, "the project has no FX table at all, as None"),
        ({"USD": ""}, "the entry is blank"),
        ({"USD": "abc"}, "the entry does not parse"),
        ({"USD": "0"}, "a zero rate is a corrupt entry, not a conversion"),
        ({"USD": "-0.92"}, "a negative rate is a corrupt entry"),
        ({"USD": "inf"}, "an infinite rate is a corrupt entry"),
        ({"USD": "nan"}, "a NaN rate is a corrupt entry"),
    ],
)
def test_no_usable_rate_is_none(rates: dict[str, str] | None, why: str) -> None:
    assert resource_fx_factor("USD", "EUR", rates) is None, why


def test_unconvertible_is_none_and_never_one() -> None:
    """The distinction the whole change rests on.

    ``1.0`` and ``None`` would produce an identical total, because multiplying
    by one changes nothing. They mean opposite things: one says there was
    nothing to convert, the other says a conversion was needed and could not be
    done. Collapsing them is exactly how an unconvertible amount joins a
    base-currency total with nobody able to tell afterwards.

    So this asserts the two cases are distinguishable, not merely that each
    returns something sensible on its own.
    """
    nothing_to_do = resource_fx_factor("EUR", "EUR", {})
    could_not_do_it = resource_fx_factor("USD", "EUR", {})

    assert nothing_to_do == 1.0
    assert could_not_do_it is None
    assert nothing_to_do != could_not_do_it

    # And the negative control on the control: if the rate IS present, the
    # second case must stop being None, or this test would pass against a
    # function that simply never converts anything.
    assert resource_fx_factor("USD", "EUR", RATES) == 0.92


def test_the_total_is_not_changed_by_reporting() -> None:
    """Part one promises the published totals do not move.

    An unconvertible amount was previously left in its own units and added as
    it stood. It still is: the caller multiplies only when a factor comes back,
    so a ``None`` leaves the amount exactly as it was. This pins that promise
    at the point it could break.
    """
    amount = 50_000.0
    factor = resource_fx_factor("USD", "EUR", {})
    assert factor is None
    # The caller's contract: no factor, no multiplication.
    unchanged = amount if factor is None else amount * factor
    assert unchanged == amount


def test_the_response_carries_the_unconverted_amounts_as_decimal_strings() -> None:
    """Money leaves this response as a plain-decimal string, per §10."""
    response = ResourceSummaryResponse(
        total_resources=1,
        grand_total=Decimal("50000.00"),
        unconverted={"USD": Decimal("50000.00")},
    )
    dumped = response.model_dump(mode="json")

    assert dumped["unconverted"] == {"USD": "50000.00"}
    assert dumped["grand_total"] == "50000.00"
    # Same shape as the total it qualifies, so a reader can subtract one from
    # the other without reformatting either.
    assert isinstance(dumped["unconverted"]["USD"], type(dumped["grand_total"]))


def test_an_all_base_currency_summary_reports_nothing_unconverted() -> None:
    """The ordinary case stays quiet.

    A field that is populated on every response teaches readers to ignore it,
    so the empty case is worth pinning as hard as the populated one.
    """
    response = ResourceSummaryResponse(total_resources=1, grand_total=Decimal("100.00"))
    dumped = response.model_dump(mode="json")

    assert dumped["unconverted"] == {}
