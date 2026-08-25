# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""CCDC is recognised as a standard and reports that it has no periods yet.

Two shipped Canadian demo packs declare CCDC 2 (2020) as their contract form.
The normaliser did not recognise it, so it became UNKNOWN, and an unknown
standard falls through to the standard-neutral fallback windows. The result was
not a visible gap: a Canadian variation was given a 28 calendar-day claim
deadline and a countdown, sourced from nothing.

Recognising the form on its own would replace a fabricated number with a
silently missing one. So CCDC is recognised *and* registered as held: no
periods are invented, and the clock says so instead of counting.

This mirrors the convention the payment-clock registry already uses for a
country deliberately carried without a value.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.change_intelligence.time_bar import (
    GENERIC_PERIODS,
    NOTICE_ASSESSMENT,
    NOTICE_CLAIM,
    NOTICE_EOT,
    NOTICE_PERIODS,
    NOTICE_PERIODS_HELD,
    NOTICE_QUOTATION,
    NOTICE_RESPONSE,
    STANDARD_CCDC,
    STANDARD_FIDIC,
    STANDARD_UNKNOWN,
    STATUS_UNKNOWN,
    ClockInput,
    build_clock,
    normalize_standard,
    period_bases_are_complete,
    period_for,
)

ALL_NOTICE_TYPES = (
    NOTICE_CLAIM,
    NOTICE_EOT,
    NOTICE_QUOTATION,
    NOTICE_ASSESSMENT,
    NOTICE_RESPONSE,
)

# ── 1. The form is recognised ────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        # Exactly the two strings the shipped Canadian demo packs declare.
        "CCDC 2 (2020) - stipulated price",
        "CCDC 2 (2020) - contrat à forfait",
        # Other members of the same family, and casing/spacing variants.
        "CCDC 5B (2010)",
        "ccdc 14",
        "  CCDC-2  ",
    ],
)
def test_a_ccdc_contract_form_is_recognised(raw: str) -> None:
    assert normalize_standard(raw) == STANDARD_CCDC


def test_recognising_ccdc_does_not_disturb_the_other_standards() -> None:
    assert normalize_standard("FIDIC Red Book 2017") == STANDARD_FIDIC
    assert normalize_standard("totally made up form") == STANDARD_UNKNOWN
    assert normalize_standard(None) == STANDARD_UNKNOWN
    assert normalize_standard("") == STANDARD_UNKNOWN


# ── 2. It reports no period rather than computing a fictitious one ───────


@pytest.mark.parametrize("notice_type", ALL_NOTICE_TYPES)
def test_a_held_standard_reports_no_period_instead_of_the_generic_one(notice_type: str) -> None:
    """This is the assertion the whole change exists for.

    Before the change this returned the generic window - 28, 28, 28, 21, 14 -
    for a standard nobody had entered a single period for.
    """
    assert period_for(STANDARD_CCDC, notice_type) is None


def test_no_ccdc_period_was_invented() -> None:
    """The registry must stay empty for CCDC until a period is sourced."""
    assert STANDARD_CCDC not in NOTICE_PERIODS
    assert STANDARD_CCDC in NOTICE_PERIODS_HELD


def test_a_genuinely_unknown_standard_still_gets_the_generic_fallback() -> None:
    """Held is not the same as unknown, and only held refuses.

    A record with no recognisable contract form keeps the standard-neutral
    window it has always had; this change narrows nothing except CCDC.
    """
    for notice_type in ALL_NOTICE_TYPES:
        assert period_for(STANDARD_UNKNOWN, notice_type) == GENERIC_PERIODS[notice_type]


def test_every_registered_period_still_states_its_basis() -> None:
    """CCDC carries no day counts, so the density gate is untouched by it.

    The gate returns the names of periods missing a basis, so an empty list is
    the passing answer.
    """
    assert period_bases_are_complete() == []


# ── 3. The refusal is visible, and it does not disarm the risk flag ──────


def _ccdc_clock(*, proof_on_file: bool) -> object:
    standard = normalize_standard("CCDC 2 (2020) - stipulated price")
    return build_clock(
        ClockInput(
            source_kind="variation",
            source_id="1",
            source_ref="VO-001",
            title="Toronto condo variation",
            standard=standard,
            notice_type=NOTICE_CLAIM,
            clause_ref="",
            trigger_date=datetime(2026, 8, 1, tzinfo=UTC),
            period_days=period_for(standard, NOTICE_CLAIM),
            explicit_due=None,
            satisfied_at=None,
            requires_notice=True,
            proof_on_file=proof_on_file,
            is_open=True,
        ),
        now=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_a_ccdc_clock_is_returned_and_says_unknown_rather_than_vanishing() -> None:
    """The honest path has to stay on screen to be honest.

    A refusal that dropped the clock from the register would trade a wrong
    answer for no answer, which is the failure this change is avoiding.
    """
    clock = _ccdc_clock(proof_on_file=False)
    assert clock.standard == STANDARD_CCDC
    assert clock.period_days is None
    assert clock.deadline is None
    assert clock.days_remaining is None
    assert clock.status == STATUS_UNKNOWN


def test_a_held_period_still_flags_the_entitlement_as_at_risk() -> None:
    """Not knowing the window is not evidence the notice is safe."""
    assert _ccdc_clock(proof_on_file=False).entitlement_at_risk is True


def test_a_ccdc_clock_no_longer_shows_a_countdown_from_nowhere() -> None:
    """Names the exact wrong behaviour, so a regression is unambiguous.

    On the tree before this change the same input produced period_days=28, a
    deadline of 2026-08-29 and status "due_soon" - a live countdown to a legal
    deadline that no contract text supports.
    """
    clock = _ccdc_clock(proof_on_file=True)
    assert clock.period_days != 28
    assert clock.deadline != datetime(2026, 8, 29, tzinfo=UTC)
