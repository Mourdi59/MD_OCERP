"""Unit tests for :mod:`app.modules.property_dev.tax_engine`.

Pure-function coverage — no DB, no HTTP. Each test pins one of the
edge cases enumerated in the task brief: UK SDLT bands + first-home +
additional-property, DE state-specific Grunderwerbsteuer, UAE DLD
transfer fee, IN GST + state stamp duty, RU state-duty,
SG BSD + ABSD, AU state stamp duty, late-interest accrual,
rate-effective-date behaviour, and unsupported-jurisdiction handling.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from app.modules.property_dev.tax_engine import (
    MissingRegionSubcodeError,
    NoVatBlockError,
    RateNotInForceError,
    TaxEngineError,
    UnknownRateClassError,
    UnsupportedJurisdictionError,
    compute_absd,
    compute_late_interest,
    compute_registration_fee,
    compute_stamp_duty,
    compute_total_taxes_for_contract,
    compute_transfer_fee,
    compute_vat,
    gross_from_net,
    net_from_gross,
    supported_jurisdictions,
)

# ── 0. Smoke ────────────────────────────────────────────────────────────


def test_supported_jurisdictions_includes_core_set() -> None:
    codes = supported_jurisdictions()
    # All jurisdictions listed in the task brief must be loaded.
    for code in ("GB", "DE", "AE", "IN", "RU", "BR", "SG", "US", "AU"):
        assert code in codes, f"Missing jurisdiction {code} in tax table"


# ── 1. UK SDLT — bands, first-home, additional-property ─────────────────


def test_uk_sdlt_zero_band_400k_standard() -> None:
    # 0 % up to 250k + 5 % on 250k-400k = 7500.
    assert compute_stamp_duty(Decimal("400000"), "GB") == Decimal("7500.00")


def test_uk_sdlt_first_home_under_425k_zero() -> None:
    # First-time-buyer relief: 0 % up to £425k.
    assert compute_stamp_duty(Decimal("400000"), "GB", is_first_home=True) == Decimal("0.00")


def test_uk_sdlt_first_home_500k_partial_relief() -> None:
    # First-time-buyer: 0 % up to 425k + 5 % on 425k-500k = 3750.
    assert compute_stamp_duty(Decimal("500000"), "GB", is_first_home=True) == Decimal("3750.00")


def test_uk_sdlt_first_home_above_625k_falls_back_to_standard() -> None:
    # Above £625k the relief disappears entirely.
    # 0 (250k) + 5% × 675k (33750) + 10% × 75k (7500) = 41250.
    assert compute_stamp_duty(Decimal("1000000"), "GB", is_first_home=True) == compute_stamp_duty(
        Decimal("1000000"), "GB"
    )


def test_uk_sdlt_additional_property_3pct_surcharge() -> None:
    # Standard 400k = 7500; +3 % × 400k = 12000 → 19500.
    assert compute_stamp_duty(Decimal("400000"), "GB", is_additional_property=True) == Decimal("19500.00")


def test_uk_sdlt_top_band_above_1_5m() -> None:
    # Bands: 0 (250k) + 33750 (5% × 675k) + 57500 (10% × 575k)
    #       + 12000 (12% × 100k) = 103250.
    assert compute_stamp_duty(Decimal("1600000"), "GB") == Decimal("103250.00")


def test_uk_sdlt_zero_at_or_below_250k() -> None:
    assert compute_stamp_duty(Decimal("250000"), "GB") == Decimal("0.00")
    assert compute_stamp_duty(Decimal("100000"), "GB") == Decimal("0.00")


# ── 2. DE Grunderwerbsteuer — state-specific ────────────────────────────


def test_de_grunderwerbsteuer_bw_5pct() -> None:
    # Baden-Württemberg = 5 %.
    assert compute_stamp_duty(Decimal("500000"), "DE", region_subcode="BW") == Decimal("25000.00")


def test_de_grunderwerbsteuer_by_lowest() -> None:
    # Bayern = 3.5 % — lowest in DE.
    assert compute_stamp_duty(Decimal("500000"), "DE", region_subcode="BY") == Decimal("17500.00")


def test_de_grunderwerbsteuer_nw_6_5pct() -> None:
    # NRW = 6.5 % — common DE state.
    assert compute_stamp_duty(Decimal("500000"), "DE", region_subcode="NW") == Decimal("32500.00")


def test_de_missing_state_raises() -> None:
    with pytest.raises(MissingRegionSubcodeError) as exc:
        compute_stamp_duty(Decimal("500000"), "DE")
    assert exc.value.jurisdiction == "DE"
    assert "BE" in exc.value.supported  # Berlin must be listed.


def test_de_unknown_state_raises() -> None:
    with pytest.raises(MissingRegionSubcodeError):
        compute_stamp_duty(Decimal("500000"), "DE", region_subcode="XX")


# ── 3. UAE — transfer fee + zero-rated VAT ──────────────────────────────


def test_ae_dubai_transfer_fee_4pct() -> None:
    assert compute_transfer_fee(Decimal("1000000"), "AE", emirate="dubai") == Decimal("40000.00")


def test_ae_abu_dhabi_transfer_fee_2pct() -> None:
    assert compute_transfer_fee(Decimal("1000000"), "AE", emirate="abu_dhabi") == Decimal("20000.00")


def test_ae_first_residential_sale_zero_rated_vat() -> None:
    # Zero-rated VAT class returns 0 even on a 5M purchase.
    assert compute_vat(Decimal("5000000"), "AE", rate_class="zero_rated") == Decimal("0.00")


def test_ae_standard_vat_5pct() -> None:
    assert compute_vat(Decimal("1000000"), "AE") == Decimal("50000.00")


def test_ae_unknown_emirate_raises() -> None:
    with pytest.raises(MissingRegionSubcodeError):
        compute_transfer_fee(Decimal("1000000"), "AE", emirate="atlantis")


# ── 4. IN — affordable vs premium vs commercial GST ─────────────────────


def test_in_affordable_gst_1pct() -> None:
    # 50 Lakh × 1 % = 50,000.
    assert compute_vat(Decimal("5000000"), "IN", rate_class="affordable") == Decimal("50000.00")


def test_in_premium_gst_5pct() -> None:
    # 1 Cr × 5 % = 5,00,000.
    assert compute_vat(Decimal("10000000"), "IN", rate_class="premium") == Decimal("500000.00")


def test_in_commercial_gst_12pct() -> None:
    assert compute_vat(Decimal("10000000"), "IN", rate_class="commercial") == Decimal("1200000.00")


def test_in_state_stamp_duty_maharashtra_6pct() -> None:
    assert compute_stamp_duty(Decimal("10000000"), "IN", region_subcode="MH") == Decimal("600000.00")


def test_in_state_stamp_duty_karnataka_5pct() -> None:
    assert compute_stamp_duty(Decimal("10000000"), "IN", region_subcode="KA") == Decimal("500000.00")


def test_in_registration_fee_1pct() -> None:
    assert compute_registration_fee(Decimal("10000000"), "IN") == Decimal("100000.00")


# ── 5. RU — escrow flag + flat state duty ───────────────────────────────


def test_ru_state_duty_flat_2000_rub() -> None:
    # Stamp_duty path falls through to ``state_duty``.
    assert compute_stamp_duty(Decimal("10000000"), "RU") == Decimal("2000.00")


def test_ru_escrow_flag_exposed_in_metadata() -> None:
    from app.modules.property_dev.tax_engine import jurisdiction_metadata

    meta = jurisdiction_metadata("RU")
    assert meta.get("escrow_required") is True


def test_ru_vat_standard_20pct() -> None:
    assert compute_vat(Decimal("1000000"), "RU") == Decimal("200000.00")


# ── 6. SG — BSD progressive bands + ABSD ────────────────────────────────


def test_sg_bsd_2m_progressive() -> None:
    # 1%×180k (1800) + 2%×180k (3600) + 3%×640k (19200)
    # + 4%×500k (20000) + 5%×500k (25000) = 69,600.
    assert compute_stamp_duty(Decimal("2000000"), "SG") == Decimal("69600.00")


def test_sg_bsd_180k_first_band_only() -> None:
    assert compute_stamp_duty(Decimal("180000"), "SG") == Decimal("1800.00")


def test_sg_absd_foreign_buyer_60pct() -> None:
    assert compute_absd(Decimal("1000000"), "SG", buyer_profile="foreigner") == Decimal("600000.00")


def test_sg_absd_sc_second_20pct() -> None:
    assert compute_absd(Decimal("1000000"), "SG", buyer_profile="sc_second") == Decimal("200000.00")


def test_sg_absd_sc_first_zero() -> None:
    assert compute_absd(Decimal("1000000"), "SG", buyer_profile="sc_first") == Decimal("0.00")


def test_sg_absd_unknown_profile_raises() -> None:
    with pytest.raises(UnknownRateClassError):
        compute_absd(Decimal("1000000"), "SG", buyer_profile="alien")


# ── 7. Late interest ────────────────────────────────────────────────────


def test_uk_late_interest_30d_100k_at_7_5_pct() -> None:
    # 100,000 × 0.075 × 30/365 = 616.4383... → 616.44.
    assert compute_late_interest(Decimal("100000"), "GB", days_overdue=30) == Decimal("616.44")


def test_de_late_interest_30d_100k_at_6_12pct() -> None:
    # 100,000 × 0.0612 × 30/365 = 503.0136... → 503.01.
    assert compute_late_interest(Decimal("100000"), "DE", days_overdue=30) == Decimal("503.01")


def test_late_interest_zero_when_not_overdue() -> None:
    assert compute_late_interest(Decimal("100000"), "GB", days_overdue=0) == Decimal("0.00")
    assert compute_late_interest(Decimal("100000"), "GB", days_overdue=-5) == Decimal("0.00")


def test_late_interest_from_dates() -> None:
    # Same answer via due_date + paid_date as via days_overdue.
    via_days = compute_late_interest(Decimal("50000"), "DE", days_overdue=60)
    via_dates = compute_late_interest(
        Decimal("50000"),
        "DE",
        due_date=date(2026, 1, 1),
        paid_date=date(2026, 3, 2),
    )
    assert via_days == via_dates


# ── 8. Rate-effective-date behaviour ────────────────────────────────────


def test_vat_effective_from_before_band_change_refuses_rather_than_returning_zero() -> None:
    """A date the table cannot price is refused, not answered with zero.

    This test previously asserted the opposite, with the comment "should
    return 0 (no band yet in force)". The case it covers is right and is kept
    verbatim; only the expectation is inverted. GB standard VAT carries
    effective_from 2011-01-04, and on 2010-12-31 the rate actually in force
    was 17.5 per cent, so zero was not a lenient answer, it was a wrong one
    that a quote then presented as the whole bill.
    """
    with pytest.raises(RateNotInForceError) as exc:
        compute_vat(Decimal("100000"), "GB", effective_on=date(2010, 12, 31))
    # The caller has to be able to act on this: either ask about a date inside
    # the band, or add the historical band to the YAML. Both need the dates.
    assert exc.value.jurisdiction == "GB"
    assert exc.value.rate_class == "standard"
    assert exc.value.effective_on == date(2010, 12, 31)
    assert exc.value.effective_from == date(2011, 1, 4)


def test_a_genuinely_zero_rated_supply_still_returns_zero_and_does_not_raise() -> None:
    """The control in the other direction: not everything may raise.

    Without this, the change above could be "passed" by refusing every zero,
    which would break every zero-rated jurisdiction in the table and still
    show a green suite for the case that motivated the work.
    """
    assert compute_vat(Decimal("5000000"), "AE", rate_class="zero_rated") == Decimal("0.00")
    assert net_from_gross(Decimal("1000.00"), "AE", rate_class="zero_rated") == Decimal("1000.00")


# ── 8b. The class axis: no block is not the same as an unknown class ────

# Jurisdictions whose stamp duty needs a subcode. Supplied so that nothing can
# refuse on an unrelated axis before the call under test is reached; the first
# version of this measurement used US without one and read MissingRegionSubcodeError
# from compute_stamp_duty as though it were the answer.
_SUBCODE = {"US": "TX", "IN": "MH", "DE": "BE", "AU": "NSW"}


def _quote_outcome(jurisdiction: str, rate_class: str, price_field: str) -> tuple[str, object]:
    """What the summariser does, in a form two call shapes can be compared by."""
    try:
        compute_total_taxes_for_contract(
            {price_field: Decimal("100000"), "currency": "USD"},
            jurisdiction,
            vat_rate_class=rate_class,
            region_subcode=_SUBCODE.get(jurisdiction),
        )
        return ("quoted", None)
    except TaxEngineError as exc:
        return ("raised", type(exc).__name__)


def test_no_vat_block_is_a_different_event_from_an_unknown_rate_class() -> None:
    """Two situations that raised the same error and meant different things.

    US has no vat or gst block at all. RU has one holding exempt and standard,
    and the caller asked for reduced. The first is a fact about what the table
    holds, the second is a caller naming something that does not exist.
    """
    with pytest.raises(NoVatBlockError) as no_block:
        compute_vat(Decimal("100000"), "US")
    assert no_block.value.jurisdiction == "US"

    with pytest.raises(UnknownRateClassError):
        compute_vat(Decimal("100000"), "RU", rate_class="reduced")

    # The split has to be real rather than nominal. If either were a subclass of
    # the other, every existing `except` on the parent would still swallow the
    # child and nothing about the old behaviour would have changed.
    assert not issubclass(NoVatBlockError, UnknownRateClassError)
    assert not issubclass(UnknownRateClassError, NoVatBlockError)


@pytest.mark.parametrize(
    ("jurisdiction", "rate_class", "expected"),
    [
        ("US", "standard", "quoted"),
        ("BR", "standard", "quoted"),
        ("RU", "reduced", "raised"),
        ("GB", "standard", "quoted"),
    ],
    ids=["us-no-block", "br-no-block", "ru-unknown-class", "gb-control"],
)
def test_a_quote_answers_alike_whichever_price_field_carries_it(
    jurisdiction: str, rate_class: str, expected: str
) -> None:
    """The same contract must not get two different answers by field name.

    ``net`` and ``total_value`` are two ways of stating the same contract's
    price. Before this, the summariser guarded its compute_vat call and left its
    net_from_gross call bare, so a jurisdiction with no rate class answered 200
    with a silent zero through one field and 422 through the other. The
    difference was not in the question.
    """
    by_net = _quote_outcome(jurisdiction, rate_class, "net")
    by_gross = _quote_outcome(jurisdiction, rate_class, "total_value")

    assert by_net == by_gross, f"{jurisdiction}/{rate_class} answers {by_net} by net and {by_gross} by total_value"
    # Asserted against the expected kind as well, because equality alone is
    # satisfied by refusing everything or by quoting everything, and each of
    # those breaks one of the four rows here while leaving the other three.
    assert by_net[0] == expected, f"{jurisdiction}/{rate_class} was expected to be {expected}, got {by_net}"


def _outcome(call: Callable[[], Decimal]) -> tuple[str, object]:
    """What a call did, in a form two calls can be compared by."""
    try:
        return ("returned", call())
    except TaxEngineError as exc:
        return ("raised", type(exc).__name__)


@pytest.mark.parametrize(
    ("fn", "zero_rated", "no_rate_yet"),
    [
        (
            compute_vat,
            lambda f: f(Decimal("100000"), "AE", rate_class="zero_rated"),
            lambda f: f(Decimal("100000"), "GB", effective_on=date(2010, 12, 31)),
        ),
        (
            net_from_gross,
            lambda f: f(Decimal("100000"), "AE", rate_class="zero_rated"),
            lambda f: f(Decimal("100000"), "GB", effective_on=date(2010, 12, 31)),
        ),
    ],
    ids=["compute_vat", "net_from_gross"],
)
def test_a_zero_rated_supply_and_an_unpriceable_date_cannot_come_back_alike(
    fn: Callable[..., Decimal],
    zero_rated: Callable[[Callable[..., Decimal]], Decimal],
    no_rate_yet: Callable[[Callable[..., Decimal]], Decimal],
) -> None:
    """The invariant, asserted on the pair rather than on a number.

    A test that pins a particular return value is blind to the thing that was
    wrong here, because the wrong answer was a perfectly ordinary zero. What
    must hold is that these two branches cannot produce the same output: they
    were once identical down to as_tuple(), so no caller could separate a
    tax-free sale from one the engine could not price.

    Asserted in both directions, because "they differ" is satisfied by any
    change that breaks one of them, including making everything raise.
    """
    a = _outcome(lambda: zero_rated(fn))
    b = _outcome(lambda: no_rate_yet(fn))

    assert a[0] == "returned", f"a zero-rated supply must still be priced, got {a}"
    assert b[0] == "raised", f"a date with no rate in force must be refused, got {b}"
    assert a != b


def test_vat_effective_from_on_or_after_uses_current_rate() -> None:
    # On the effective date itself the rate is active.
    assert compute_vat(
        Decimal("100000"),
        "GB",
        effective_on=date(2011, 1, 4),
    ) == Decimal("20000.00")
    assert compute_vat(
        Decimal("100000"),
        "GB",
        effective_on=date(2025, 6, 1),
    ) == Decimal("20000.00")


# ── 9. Unsupported jurisdiction handling ────────────────────────────────


def test_unsupported_jurisdiction_raises_with_supported_list() -> None:
    with pytest.raises(UnsupportedJurisdictionError) as exc:
        compute_vat(Decimal("100"), "XX")
    assert exc.value.jurisdiction == "XX"
    # The error must enumerate supported codes so the UI can guide the user.
    assert "GB" in exc.value.supported
    assert "DE" in exc.value.supported


def test_unsupported_jurisdiction_lowercase_is_normalised() -> None:
    # Mixed case must still be looked up.
    assert compute_vat(Decimal("100"), "gb") == Decimal("20.00")


def test_unknown_rate_class_raises() -> None:
    with pytest.raises(UnknownRateClassError):
        compute_vat(Decimal("100"), "RU", rate_class="reduced")


# ── 10. Gross/net round-trip ────────────────────────────────────────────


def test_gross_from_net_roundtrip_with_uk_20pct() -> None:
    net = Decimal("1000.00")
    gross = gross_from_net(net, "GB")
    assert gross == Decimal("1200.00")


def test_net_from_gross_roundtrip_with_de_19pct() -> None:
    gross = Decimal("1190.00")
    net = net_from_gross(gross, "DE")
    assert net == Decimal("1000.00")


def test_net_from_gross_zero_rate_class_returns_gross() -> None:
    # Zero-rated → no VAT subtracted.
    assert net_from_gross(Decimal("1000.00"), "AE", rate_class="zero_rated") == Decimal("1000.00")


# ── 11. AU state-specific bands ─────────────────────────────────────────


def test_au_nsw_stamp_duty_300k() -> None:
    # NSW bands: 1.25%×17k (212.5) + 1.5%×19k (285) + 1.75%×61k (1067.5)
    # + 3.5%×203k (7105) = 8670.
    result = compute_stamp_duty(Decimal("300000"), "AU", region_subcode="NSW")
    assert result == Decimal("8670.00")


def test_au_vic_stamp_duty_500k() -> None:
    # VIC bands: 1.4%×25k (350) + 2.4%×105k (2520) + 5.5%×370k (20350) = 23220.
    result = compute_stamp_duty(Decimal("500000"), "AU", region_subcode="VIC")
    assert result == Decimal("23220.00")


def test_au_missing_state_raises() -> None:
    with pytest.raises(MissingRegionSubcodeError):
        compute_stamp_duty(Decimal("500000"), "AU")


# ── 12. US state-specific transfer tax ──────────────────────────────────


def test_us_ny_transfer_tax_0_4pct() -> None:
    assert compute_stamp_duty(Decimal("1000000"), "US", region_subcode="NY") == Decimal("4000.00")


def test_us_texas_no_transfer_tax() -> None:
    assert compute_stamp_duty(Decimal("1000000"), "US", region_subcode="TX") == Decimal("0.00")


# ── 13. compute_total_taxes_for_contract — high-level integration ───────


def test_total_taxes_uk_first_time_buyer() -> None:
    quote = compute_total_taxes_for_contract(
        {"net": Decimal("400000"), "currency": "GBP"},
        "GB",
        is_first_home=True,
    )
    # No SDLT under £425k for first-time buyer.
    assert quote["stamp_duty"] == Decimal("0.00")
    # GB VAT 20 % on residential new-build is technically zero-rated
    # but our default 'standard' class returns 20 %; verify roll-up
    # math regardless of policy.
    assert quote["vat"] == Decimal("80000.00")
    # Grand total = 400k + 80k VAT + 0 SDLT.
    assert quote["grand_total"] == Decimal("480000.00")
    # Breakdown must include the net line.
    assert any(line["line"] == "Net price" for line in quote["breakdown"])


def test_total_taxes_de_berlin_full_chain() -> None:
    quote = compute_total_taxes_for_contract(
        {"net": Decimal("500000"), "currency": "EUR"},
        "DE",
        region_subcode="BE",
    )
    assert quote["vat"] == Decimal("95000.00")  # 19 % VAT
    # Berlin Grunderwerbsteuer = 6 % on net price (500k × 6%).
    assert quote["stamp_duty"] == Decimal("30000.00")
    # 7500 notary (1.5 %) — registration fallback.
    assert quote["registration_fee"] == Decimal("7500.00")
    # Grand total = 500k + 95k + 30k + 7.5k = 632,500.
    assert quote["grand_total"] == Decimal("632500.00")


def test_total_taxes_unsupported_jurisdiction_raises() -> None:
    with pytest.raises(UnsupportedJurisdictionError):
        compute_total_taxes_for_contract(
            {"net": Decimal("100000"), "currency": "USD"},
            "ZZ",
        )


def test_total_taxes_with_overdue_instalments_accrues_late_interest() -> None:
    overdue = [
        {
            "sequence": 1,
            "amount": "100000",
            "days_overdue": 60,
        }
    ]
    quote = compute_total_taxes_for_contract(
        {"net": Decimal("500000"), "currency": "EUR"},
        "DE",
        region_subcode="BE",
        overdue_instalments=overdue,
    )
    # 100k × 6.12 % × 60/365 = 1006.0274 → 1006.03.
    assert quote["late_interest"] == Decimal("1006.03")
    assert any("Late interest" in line["line"] for line in quote["breakdown"])


def test_total_taxes_currency_passthrough() -> None:
    quote = compute_total_taxes_for_contract(
        {"net": Decimal("100000"), "currency": "AED"},
        "AE",
        vat_rate_class="standard",
        emirate="dubai",
    )
    assert quote["currency"] == "AED"
    assert quote["jurisdiction"] == "AE"
    assert quote["transfer_fee"] == Decimal("4000.00")
