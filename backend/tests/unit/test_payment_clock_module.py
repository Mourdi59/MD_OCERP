"""Unit + service tests for the Payment Clock module.

Four layers:
  * The statutory arithmetic - no DB. Worked examples with the dates written
    out, because a date engine that is only tested against itself proves that
    it is consistent, not that it is right.
  * The shipped catalogue - no DB. Every regime is checked against the model's
    own vocabularies and against the rules that will judge it. The one that
    matters most is that the final date falls after the due date in every
    regime shipped, since a shipped regime that fails the product's own ERROR
    rule would make that rule unsatisfiable rather than strict.
  * Service layer against the shared PostgreSQL unit DB with per-test
    transaction isolation (same fixture style as ``test_cases_module.py``).
  * The validation rules, one test per rule, including the one the module
    exists for: silence past the payment notice deadline makes the sum applied
    for the notified sum.

This file lives in ``tests/unit`` and has to be named in
``.github/workflows/ci-postgres.yml`` to run in a blocking lane.
``tests/integration`` runs in no blocking lane, so a guard placed there would
pass review and gate nothing.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal
from typing import get_args

import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payment_clock import clock, schemas, service
from app.modules.payment_clock import data as payment_clock_data
from app.modules.payment_clock.data import (
    NO_REGIME_DIFFERENT_SHAPE,
    NO_REGIME_HELD,
    NO_REGIME_NO_STATUTE,
    NO_REGIME_NOT_MODELLED,
    NO_REGIME_REASONS,
    NO_REGIME_VALUES,
    PAYMENT_REGIMES,
    REGIME_CODES,
    no_regime_reason,
    regime_by_code,
    seed_payment_regimes,
)
from app.modules.payment_clock.models import (
    APPLICATION_STATUSES,
    DATE_BASES,
    DAY_BASES,
    EVENT_TYPES,
    INTEREST_BASES,
    NO_NOTICE_EFFECTS,
    NOTICE_TYPES,
    SOURCE_TYPES,
    PaymentClockEvent,
    PaymentNotice,
    PaymentRegime,
    StatutoryPaymentApplication,
)
from app.modules.payment_clock.permissions import register_payment_clock_permissions
from app.modules.payment_clock.validators import (
    RULE_EVENT_TYPES,
    blocking_findings,
    evaluate_clock,
    register_payment_clock_rules,
)
from app.modules.projects.models import Project
from app.modules.users.models import User
from tests._pg import transactional_session


@pytest.fixture(autouse=True)
def _rules_registered() -> None:
    """The rules only exist once somebody registers them.

    In the running application that is the module ``on_startup`` hook. A rule
    set that was never registered validates nothing and reports a clean bill of
    health, so registering here is what stops every rule test below passing
    vacuously.
    """
    register_payment_clock_rules()


# ── The statutory arithmetic (no DB) ─────────────────────────────────────────


class TestDayCounting:
    def test_business_days_step_over_the_weekend(self):
        # 2026-03-06 is a Friday.
        assert clock.add_days(date(2026, 3, 6), 1, "business") == date(2026, 3, 9)

    def test_business_days_step_over_a_supplied_holiday(self):
        # No public holiday calendar ships with the module, so a deployment
        # hands one in. Monday 9 March off means one business day lands Tuesday.
        assert clock.add_days(date(2026, 3, 6), 1, "business", [date(2026, 3, 9)]) == date(2026, 3, 10)

    def test_zero_days_is_the_same_day_even_on_a_saturday(self):
        # A statute that makes the sum due on the day the claim is served means
        # that day. Four of the shipped regimes say exactly that.
        saturday = date(2026, 3, 7)
        assert clock.add_days(saturday, 0, "business") == saturday
        assert clock.add_days(saturday, 0, "calendar") == saturday

    def test_negative_days_count_backwards(self):
        # "Not later than seven days before the final date" is counted this way.
        assert clock.add_days(date(2026, 4, 24), -7, "calendar") == date(2026, 4, 17)
        # Monday minus one business day is the Friday before.
        assert clock.add_days(date(2026, 3, 9), -1, "business") == date(2026, 3, 6)

    def test_an_unknown_basis_is_refused_rather_than_guessed(self):
        with pytest.raises(ValueError, match="day basis"):
            clock.add_days(date(2026, 3, 6), 1, "working")

    def test_days_between_is_calendar_and_signed(self):
        assert clock.days_between(date(2026, 3, 1), date(2026, 3, 12)) == 11
        assert clock.days_between(date(2026, 3, 12), date(2026, 3, 1)) == -11


class TestWorkedExamples:
    """Dates written out by hand from the statutes, not from the code."""

    def test_uk_scheme_sequence(self):
        # A March valuation applied for on the last day of the period.
        schedule = clock.compute_schedule(
            regime_by_code("uk_hgcra"),
            application_date=date(2026, 3, 31),
            period_end=date(2026, 3, 31),
        )
        assert schedule.due_date == date(2026, 4, 7)  # period end + 7 days
        assert schedule.payment_notice_deadline == date(2026, 4, 12)  # due + 5 days
        assert schedule.final_date == date(2026, 4, 24)  # due + 17 days
        assert schedule.pay_less_deadline == date(2026, 4, 17)  # final - 7 days

    def test_new_south_wales_counts_business_days(self):
        # 2026-03-02 is a Monday, so every step below lands on a weekday.
        schedule = clock.compute_schedule(
            regime_by_code("au_nsw_sopa"),
            application_date=date(2026, 3, 2),
        )
        assert schedule.due_date == date(2026, 3, 2)  # payable from service
        assert schedule.payment_notice_deadline == date(2026, 3, 16)  # 10 business days
        assert schedule.final_date == date(2026, 3, 23)  # 15 business days
        # The Act provides no pay-less notice; the payment schedule is the whole
        # response, so a null here is the statute being silent.
        assert schedule.pay_less_deadline is None

    def test_a_holiday_calendar_moves_the_business_day_deadlines(self):
        holidays = [date(2026, 3, 9), date(2026, 3, 10)]
        schedule = clock.compute_schedule(
            regime_by_code("au_nsw_sopa"),
            application_date=date(2026, 3, 2),
            holidays=holidays,
        )
        assert schedule.payment_notice_deadline == date(2026, 3, 18)
        assert schedule.final_date == date(2026, 3, 25)

    def test_a_silent_regime_leaves_the_date_null(self):
        # The EU Directive has no notice sequence at all.
        eu = clock.compute_schedule(regime_by_code("eu_late_payment"), application_date=date(2026, 3, 2))
        assert eu.payment_notice_deadline is None
        assert eu.final_date == date(2026, 4, 1)  # 30 calendar days

        # Malaysia leaves the payment period to the contract.
        my = clock.compute_schedule(regime_by_code("my_cipaa"), application_date=date(2026, 3, 2))
        assert my.final_date is None
        assert my.pay_less_deadline is None
        assert my.payment_notice_deadline is not None

    def test_the_derivation_names_the_statute_and_the_dates(self):
        schedule = clock.compute_schedule(
            regime_by_code("uk_hgcra"),
            application_date=date(2026, 3, 31),
            period_end=date(2026, 3, 31),
        )
        joined = " ".join(schedule.derivation)
        assert "Housing Grants, Construction and Regeneration Act 1996" in joined
        assert "2026-04-07" in joined
        assert "7 days after the end of the period claimed" in joined
        # Four dates computed, four lines. This text is what gets quoted in a
        # dispute, so it is not allowed to go quiet on one of them.
        assert len(schedule.derivation) == 4

    def test_a_zero_offset_reads_as_on_rather_than_zero_days_after(self):
        schedule = clock.compute_schedule(regime_by_code("au_nsw_sopa"), application_date=date(2026, 3, 2))
        assert "on the application date 2026-03-02" in schedule.derivation[0]
        assert "0 days" not in " ".join(schedule.derivation)


class TestNoticeDeadlinesAndInterest:
    def test_each_notice_type_is_measured_against_its_own_deadline(self):
        schedule = clock.ClockSchedule(
            due_date=date(2026, 4, 7),
            payment_notice_deadline=date(2026, 4, 12),
            pay_less_deadline=date(2026, 4, 17),
            final_date=date(2026, 4, 24),
        )
        assert clock.deadline_for_notice("payment_notice", schedule)[0] == date(2026, 4, 12)
        assert clock.deadline_for_notice("pay_less_notice", schedule)[0] == date(2026, 4, 17)

    def test_a_default_payment_notice_has_no_deadline_and_is_never_late(self):
        # It is the payee's own notice and it exists *because* the payer missed
        # a deadline, so measuring it against one would be backwards.
        schedule = clock.ClockSchedule(payment_notice_deadline=date(2026, 4, 12))
        assert clock.deadline_for_notice("default_payment_notice", schedule)[0] is None

    def test_interest_is_described_not_invented(self):
        text = clock.interest_description(regime_by_code("uk_hgcra"))
        assert "Bank of England base rate plus 8 percent" in text
        assert "Late Payment of Commercial Debts (Interest) Act 1998" in text

    def test_a_prescribed_rate_says_so_instead_of_naming_a_number(self):
        text = clock.interest_description(regime_by_code("au_nsw_sopa"))
        assert "prescribed" in text.lower()

    def test_money_formatting_never_produces_scientific_notation(self):
        assert clock.format_money(Decimal("1240000.00"), "GBP") == "1240000.00 GBP"
        assert clock.format_money(None) == "an unstated amount"


# ── The shipped catalogue (no DB) ────────────────────────────────────────────


class TestRegimeCatalogue:
    def test_the_briefed_jurisdictions_are_all_shipped(self):
        assert set(REGIME_CODES) >= {
            "uk_hgcra",
            "ie_cca_2013",
            "au_nsw_sopa",
            "au_qld_bif",
            "nz_cca_2002",
            "sg_sopa",
            "eu_late_payment",
            "de_vob_b_abschlag",
            "de_vob_b_schluss",
            "de_bgb_632a",
        }

    def test_codes_are_unique(self):
        assert len(set(REGIME_CODES)) == len(REGIME_CODES)

    def test_every_entry_matches_the_table_exactly(self):
        # A key the table does not have would be dropped silently by the seeder
        # and a column the entry omits would seed as a default nobody chose.
        columns = {c.name for c in PaymentRegime.__table__.columns} - {"id", "created_at", "updated_at"}
        for entry in PAYMENT_REGIMES:
            assert set(entry) == columns, entry["code"]

    def test_every_entry_uses_the_declared_vocabularies(self):
        for entry in PAYMENT_REGIMES:
            assert entry["due_date_basis"] in DATE_BASES
            assert entry["payment_notice_basis"] in DATE_BASES
            assert entry["final_date_basis"] in DATE_BASES
            assert entry["due_date_day_basis"] in DAY_BASES
            assert entry["payment_notice_day_basis"] in DAY_BASES
            assert entry["final_date_day_basis"] in DAY_BASES
            assert entry["pay_less_day_basis"] in DAY_BASES
            assert entry["no_notice_effect"] in NO_NOTICE_EFFECTS
            assert entry["interest_basis"] in INTEREST_BASES

    def test_percentages_are_decimal_and_never_float(self):
        for entry in PAYMENT_REGIMES:
            for key in ("interest_margin_percent", "interest_fixed_percent"):
                assert entry[key] is None or isinstance(entry[key], Decimal), entry["code"]

    def test_every_shipped_regime_satisfies_the_products_own_error_rule(self):
        # ``payment_clock.final_date_after_due_date`` is an ERROR. A shipped
        # regime that produced final == due would make that rule fire on the
        # product's own data, which turns a strict rule into an unsatisfiable
        # one. Checked on a Monday and on a Saturday, since the business-day
        # regimes behave differently when the count starts on a weekend.
        for start in (date(2026, 3, 2), date(2026, 3, 7)):
            for entry in PAYMENT_REGIMES:
                schedule = clock.compute_schedule(entry, application_date=start, period_end=start)
                if schedule.due_date is None or schedule.final_date is None:
                    continue
                assert schedule.final_date > schedule.due_date, f"{entry['code']} on {start}"

    def test_a_pay_less_deadline_never_precedes_the_notice_deadline(self):
        # If it did, the payer would have to decide what to withhold before it
        # had to say what was due, and the sequence would read backwards.
        for entry in PAYMENT_REGIMES:
            schedule = clock.compute_schedule(
                entry,
                application_date=date(2026, 3, 2),
                period_end=date(2026, 3, 2),
            )
            if schedule.pay_less_deadline is None or schedule.payment_notice_deadline is None:
                continue
            assert schedule.pay_less_deadline >= schedule.payment_notice_deadline, entry["code"]

    def test_every_statute_is_named_and_referenced(self):
        for entry in PAYMENT_REGIMES:
            assert entry["statute"].strip(), entry["code"]
            assert entry["statute_reference"].strip(), entry["code"]

    def test_regime_by_code_returns_none_for_an_unknown_code(self):
        assert regime_by_code("zz_nowhere") is None


class TestNoRegimeReasons:
    def test_the_shipped_reasons_are_all_within_the_closed_set(self):
        for code, reason in NO_REGIME_REASONS.items():
            assert reason in NO_REGIME_VALUES, code

    def test_held_and_reasons_and_covered_are_disjoint_on_the_shipped_data(self):
        covered = {str(r.get("country_code")) for r in PAYMENT_REGIMES if r.get("country_code")}
        assert not (set(NO_REGIME_REASONS) & covered)
        assert not (NO_REGIME_HELD & covered)
        assert not (set(NO_REGIME_REASONS) & NO_REGIME_HELD)

    def test_the_validator_refuses_a_value_outside_the_closed_set(self, monkeypatch):
        monkeypatch.setattr(payment_clock_data, "NO_REGIME_REASONS", {"ZZ": "guessed"})
        with pytest.raises(ValueError, match="not one of"):
            payment_clock_data._validate_no_regime_reasons()

    def test_the_validator_refuses_a_country_that_has_both_a_row_and_a_reason(self, monkeypatch):
        # GB has a row (uk_hgcra); declaring a reason for it too is the same
        # contradiction tax_engine._validate_vat_absence refuses.
        monkeypatch.setattr(payment_clock_data, "NO_REGIME_REASONS", {"GB": NO_REGIME_NOT_MODELLED})
        with pytest.raises(ValueError, match="have a row in PAYMENT_REGIMES"):
            payment_clock_data._validate_no_regime_reasons()

    def test_the_validator_refuses_a_held_country_that_also_has_a_row(self, monkeypatch):
        # The bug this test exists to catch: a naive validator that only walks
        # NO_REGIME_REASONS never looks at NO_REGIME_HELD at all, so a held
        # country that later gains a real row would pass silently and the
        # probe would go on reporting it as held forever.
        monkeypatch.setattr(payment_clock_data, "NO_REGIME_HELD", frozenset({"GB"}))
        with pytest.raises(ValueError, match="have a row in PAYMENT_REGIMES"):
            payment_clock_data._validate_no_regime_reasons()

    def test_the_validator_refuses_a_country_in_both_reasons_and_held(self, monkeypatch):
        monkeypatch.setattr(payment_clock_data, "NO_REGIME_REASONS", {"ZZ": NO_REGIME_NO_STATUTE})
        monkeypatch.setattr(payment_clock_data, "NO_REGIME_HELD", frozenset({"ZZ"}))
        with pytest.raises(ValueError, match="both resolved and held"):
            payment_clock_data._validate_no_regime_reasons()

    def test_no_regime_reason_raises_for_a_country_with_a_row(self):
        with pytest.raises(ValueError, match="not something to explain"):
            no_regime_reason("GB")

    def test_no_regime_reason_returns_the_declared_value_for_brazil(self):
        assert no_regime_reason("BR") == NO_REGIME_DIFFERENT_SHAPE

    def test_no_regime_reason_returns_none_for_an_unresearched_country(self):
        assert no_regime_reason("JP") is None

    def test_no_regime_reason_normalises_case_and_whitespace(self):
        assert no_regime_reason(" br ") == NO_REGIME_DIFFERENT_SHAPE


class TestGermanRegimes:
    """The § 16 VOB/B and § 632a BGB deadlines, worked out by hand.

    The numbers come from the provisions themselves: an Abschlagsrechnung falls
    due within 21 calendar days of the client receiving the Aufstellung
    (§ 16 Abs. 1 Nr. 3 VOB/B), the Schlussrechnung at the latest within 30
    calendar days of its receipt (§ 16 Abs. 3 Nr. 1 VOB/B), and under a plain
    BGB contract the client is in default at the latest 30 days after receiving
    the invoice (§ 286 Abs. 3 BGB). All three run on calendar days and none of
    them has a statutory notice sequence.
    """

    def test_an_abschlagsrechnung_runs_twenty_one_calendar_days(self):
        schedule = clock.compute_schedule(
            regime_by_code("de_vob_b_abschlag"),
            application_date=date(2026, 3, 2),  # the day the Aufstellung arrived
        )
        assert schedule.due_date == date(2026, 3, 2)
        assert schedule.final_date == date(2026, 3, 23)  # 21 calendar days
        # No statutory payment or pay-less notice under the VOB/B.
        assert schedule.payment_notice_deadline is None
        assert schedule.pay_less_deadline is None

    def test_the_schlussrechnung_runs_thirty_calendar_days(self):
        schedule = clock.compute_schedule(
            regime_by_code("de_vob_b_schluss"),
            application_date=date(2026, 3, 2),  # the day the Schlussrechnung arrived
        )
        assert schedule.final_date == date(2026, 4, 1)  # 30 calendar days
        assert schedule.payment_notice_deadline is None

    def test_the_bgb_default_limit_runs_thirty_calendar_days(self):
        schedule = clock.compute_schedule(
            regime_by_code("de_bgb_632a"),
            application_date=date(2026, 3, 2),
        )
        assert schedule.final_date == date(2026, 4, 1)
        assert schedule.payment_notice_deadline is None

    def test_the_calendar_count_does_not_skip_weekends(self):
        # 21 calendar days from a Friday still lands 21 days later, weekend or
        # not - "binnen 21 Tagen" counts every day.
        schedule = clock.compute_schedule(
            regime_by_code("de_vob_b_abschlag"),
            application_date=date(2026, 3, 6),  # a Friday
        )
        assert schedule.final_date == date(2026, 3, 27)

    def test_the_statutory_references_are_exact(self):
        abschlag = regime_by_code("de_vob_b_abschlag")
        assert "§ 16 Abs. 1 Nr. 3 VOB/B" in abschlag["statute_reference"]
        assert "§ 16 Abs. 5 Nr. 3 VOB/B" in abschlag["statute_reference"]

        schluss = regime_by_code("de_vob_b_schluss")
        assert "§ 16 Abs. 3 Nr. 1 VOB/B" in schluss["statute_reference"]
        # The 60-day extension and the 28-day Vorbehalt live in the notes: the
        # model has no column for either, and the notes are where a reader is
        # told what the clock does not compute.
        assert "60 days" in schluss["notes"]
        assert "expressly agreed" in schluss["notes"]
        assert "28 calendar days" in schluss["notes"]

        bgb = regime_by_code("de_bgb_632a")
        assert "§ 632a Abs. 1 BGB" in bgb["statute_reference"]
        assert "§ 286 Abs. 3 BGB" in bgb["statute_reference"]

    def test_german_interest_is_nine_points_over_the_base_rate(self):
        # § 288 Abs. 2 BGB: nine percentage points over the Basiszinssatz for
        # commercial debts. Nine, not the Directive's eight - the German
        # transposition went above the minimum.
        for code in ("de_vob_b_abschlag", "de_vob_b_schluss", "de_bgb_632a"):
            regime = regime_by_code(code)
            assert regime["interest_margin_percent"] == Decimal("9.000"), code
            text = clock.interest_description(regime)
            assert "plus 9 percent" in text, code
            assert "§ 288 Abs. 2 BGB" in text, code

    def test_the_derivation_names_the_german_provision(self):
        schedule = clock.compute_schedule(
            regime_by_code("de_vob_b_abschlag"),
            application_date=date(2026, 3, 2),
        )
        joined = " ".join(schedule.derivation)
        assert "VOB/B § 16 Abs. 1 (Abschlagszahlungen)" in joined
        assert "21 days after the application date 2026-03-02" in joined


# ── Schemas (no DB) ──────────────────────────────────────────────────────────


class TestSchemaVocabularyParity:
    """Each Literal is pinned to the tuple the data and the arithmetic use.

    The tuple is what the seeded rows and the date engine are written against;
    the Literal is what the API rejects on. A drift between them lets a value
    through the door that the clock has no arithmetic for.
    """

    def test_notice_types(self):
        assert set(get_args(schemas.NoticeTypeLiteral)) == set(NOTICE_TYPES)

    def test_source_types(self):
        assert set(get_args(schemas.SourceTypeLiteral)) == set(SOURCE_TYPES)

    def test_application_statuses(self):
        assert set(get_args(schemas.ApplicationStatusLiteral)) == set(APPLICATION_STATUSES)

    def test_event_types(self):
        assert set(get_args(schemas.EventTypeLiteral)) == set(EVENT_TYPES)

    def test_no_notice_effects(self):
        assert set(get_args(schemas.NoNoticeEffectLiteral)) == set(NO_NOTICE_EFFECTS)

    def test_interest_bases(self):
        assert set(get_args(schemas.InterestBasisLiteral)) == set(INTEREST_BASES)

    def test_day_and_date_bases(self):
        assert set(get_args(schemas.DayBasisLiteral)) == set(DAY_BASES)
        assert set(get_args(schemas.DateBasisLiteral)) == set(DATE_BASES)

    def test_every_event_type_is_produced_by_exactly_one_rule(self):
        # The register and the findings have to be the same statements twice,
        # not two implementations of the same law.
        assert set(RULE_EVENT_TYPES.values()) == set(EVENT_TYPES)
        assert len(set(RULE_EVENT_TYPES)) == len(RULE_EVENT_TYPES)


class TestApplicationSchema:
    def _body(self, **overrides) -> dict:
        body = {
            "project_id": uuid.uuid4(),
            "regime_code": "uk_hgcra",
            "application_date": date(2026, 3, 31),
            "period_end": date(2026, 3, 31),
            "applied_amount": Decimal("124000.00"),
            "currency": "GBP",
        }
        body.update(overrides)
        return body

    def test_currency_is_upper_cased_and_checked(self):
        assert schemas.ApplicationCreate(**self._body(currency="gbp")).currency == "GBP"
        with pytest.raises(ValueError):
            schemas.ApplicationCreate(**self._body(currency="12X"))

    def test_currency_is_required_because_an_implied_one_is_a_bug(self):
        with pytest.raises(ValueError):
            schemas.ApplicationCreate(**self._body(currency=""))

    def test_a_negative_application_is_refused(self):
        with pytest.raises(ValueError):
            schemas.ApplicationCreate(**self._body(applied_amount=Decimal("-1.00")))

    def test_a_period_that_ends_before_it_starts_is_refused(self):
        with pytest.raises(ValueError):
            schemas.ApplicationCreate(**self._body(period_start=date(2026, 4, 1), period_end=date(2026, 3, 1)))

    def test_the_holiday_calendar_has_a_ceiling(self):
        with pytest.raises(ValueError):
            schemas.ApplicationCreate(
                **self._body(holidays=[date(2026, 1, 1)] * (schemas.MAX_HOLIDAYS + 1)),
            )

    def test_money_leaves_as_a_string_never_as_a_json_number(self):
        payload = schemas.ApplicationCreate(**self._body()).model_dump(mode="json")
        assert payload["applied_amount"] == "124000.00"
        assert isinstance(payload["applied_amount"], str)


# ── Service layer (PostgreSQL) ───────────────────────────────────────────────


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with transactional_session() as s:
        yield s


async def _project(session: AsyncSession, name: str = "Payment clock project") -> Project:
    owner = User(email=f"{uuid.uuid4().hex[:12]}@example.com", hashed_password="x", full_name="Owner")
    session.add(owner)
    await session.flush()
    project = Project(name=name, owner_id=owner.id)
    session.add(project)
    await session.flush()
    return project


async def _regime(session: AsyncSession, code: str = "uk_hgcra") -> PaymentRegime:
    await service.ensure_regimes(session)
    regime = await service.get_regime_by_code(session, code=code)
    assert regime is not None
    return regime


async def _application(
    session: AsyncSession,
    *,
    code: str = "uk_hgcra",
    **overrides,
) -> tuple[StatutoryPaymentApplication, PaymentRegime]:
    project = await _project(session)
    regime = await _regime(session, code)
    body = {
        "project_id": project.id,
        "regime_code": code,
        "reference": "AFP-014",
        "application_date": date(2026, 3, 31),
        "period_end": date(2026, 3, 31),
        "applied_amount": Decimal("124000.00"),
        "currency": "GBP",
    }
    body.update(overrides)
    application = await service.create_application(
        session,
        body=schemas.ApplicationCreate(**body),
        regime=regime,
    )
    return application, regime


@pytest.mark.asyncio
class TestSeeding:
    async def test_the_catalogue_seeds_once_and_stays_put(self, session):
        first = await service.ensure_regimes(session)
        assert first["created"] == len(PAYMENT_REGIMES)

        second = await service.ensure_regimes(session)
        assert second["created"] == 0

        total = await session.scalar(select(func.count()).select_from(PaymentRegime))
        assert total == len(PAYMENT_REGIMES)

    async def test_a_refresh_rewrites_the_shipped_rows_in_place(self, session):
        await service.ensure_regimes(session)
        regime = await service.get_regime_by_code(session, code="uk_hgcra")
        regime_id = regime.id
        regime.payment_notice_days = 99
        await session.flush()

        result = await service.ensure_regimes(session, refresh=True)
        assert result["updated"] == len(PAYMENT_REGIMES)

        again = await service.get_regime_by_code(session, code="uk_hgcra")
        assert again.payment_notice_days == 5
        # The same row, so every application still points at its own regime.
        assert again.id == regime_id

    async def test_a_bad_value_in_the_shipped_catalogue_is_refused_at_load(self, session, monkeypatch):
        """The seeder validates against the schema, not just against itself.

        seed_payment_regimes used to build PaymentRegime(**entry) straight
        from the dict, so a typo in data.py would have seeded silently and
        only surfaced downstream, in whichever rule happened to read the bad
        value. This builds a row exactly the way an editor of data.py could,
        one letter off a real no_notice_effect value, and checks the load
        path refuses it rather than absorbing it, and that nothing from the
        attempt reaches the table.
        """
        bad_entry = dict(PAYMENT_REGIMES[0])
        bad_entry["code"] = "test_bad_regime"
        bad_entry["no_notice_effect"] = "applied_sum_becomes_notifed_sum"  # missing an "i"
        monkeypatch.setattr(payment_clock_data, "PAYMENT_REGIMES", (bad_entry,))

        with pytest.raises(ValueError, match="no_notice_effect"):
            await payment_clock_data.seed_payment_regimes(session)

        total = await session.scalar(select(func.count()).select_from(PaymentRegime))
        assert total == 0


@pytest.mark.asyncio
class TestGermanDemoSeeding:
    """The demo clocks the German demo projects install.

    Anchored to a supplied ``today`` rather than the machine clock, because the
    thing being asserted is the *relationship* between the seeded dates and the
    installation day: one invoice paid in time, one overdue with interest
    running, one still inside its 21 days. A seed anchored to a constant would
    hold that shape for three weeks and then rot.
    """

    async def test_the_demo_clocks_land_in_the_three_states_the_screen_shows(self, session):
        from app.modules.payment_clock.demo import DEMO_REGIME_CODE, seed_demo_payment_clocks

        project = await _project(session, name="Bürogebäude Frankfurt Europaviertel")
        today = date(2026, 8, 12)
        count = await seed_demo_payment_clocks(session, project_id=project.id, today=today)
        assert count == 3

        rows = await service.list_applications(session, project_id=project.id)
        by_ref = {row.reference: row for row in rows}
        assert set(by_ref) == {"AZ-02", "AZ-03", "AZ-04"}

        regime = await service.get_regime(session, regime_id=rows[0].regime_id)
        assert regime is not None
        assert regime.code == DEMO_REGIME_CODE
        assert {row.regime_id for row in rows} == {regime.id}
        assert all(row.currency == "EUR" for row in rows)
        # Round demo money reads as a placeholder; a valuation never is.
        assert all(row.applied_amount % 1 != 0 for row in rows)
        # The dates came from the regime arithmetic, not from the seed data.
        assert all(row.dates_overridden is False for row in rows)
        assert all(row.final_date == row.application_date + timedelta(days=21) for row in rows)

        paid = by_ref["AZ-02"]
        assert paid.status == "paid"
        assert paid.paid_amount == paid.applied_amount
        assert paid.paid_at is not None
        assert paid.paid_at <= paid.final_date  # paid inside the 21 days

        overdue = by_ref["AZ-03"]
        assert overdue.status == "open"
        assert overdue.final_date < today  # § 16 Abs. 1 Nr. 3 deadline missed

        ticking = by_ref["AZ-04"]
        assert ticking.status == "open"
        assert ticking.final_date > today  # the clock the demo watches run

        # The overdue filter picks out exactly the invoice somebody is owed
        # money on - the paid one is settled and the ticking one is not yet due.
        overdue_rows = await service.list_applications(session, project_id=project.id, overdue_as_of=today)
        assert [row.id for row in overdue_rows] == [overdue.id]

    async def test_the_overdue_invoice_reports_german_interest_on_read(self, session):
        from app.modules.payment_clock.demo import seed_demo_payment_clocks

        project = await _project(session)
        today = date(2026, 8, 12)
        await seed_demo_payment_clocks(session, project_id=project.id, today=today)
        rows = await service.list_applications(session, project_id=project.id)
        overdue = next(row for row in rows if row.reference == "AZ-03")
        regime = await service.get_regime(session, regime_id=overdue.regime_id)

        findings = await _findings(session, overdue, regime, as_of=today)
        assert "payment_clock.notified_sum" not in findings  # no notice sequence to breach
        finding = findings["payment_clock.statutory_interest"][0]
        assert "941618.45 EUR" in finding.message
        assert "plus 9 percent" in finding.message
        assert finding.details["days_overdue"] == 13  # served 34 days ago, 21-day limit

    async def test_installing_a_german_demo_project_opens_the_clocks(self, session):
        """The wiring, not the seeder: the installer's DE gate has to fire.

        The seeder tests above call ``seed_demo_payment_clocks`` directly, so
        they would stay green if the call in ``_seed_module_data`` were deleted
        or its country gate mistyped. This installs a real German demo project
        and reads the clocks back off it.
        """
        import app.core.demo_packs  # noqa: F401 - registers the pack templates
        from app.core.demo_projects import install_demo_project

        result = await install_demo_project(session, "office-frankfurt")
        project_id = uuid.UUID(str(result["project_id"]))

        rows = await service.list_applications(session, project_id=project_id)
        assert {row.reference for row in rows} == {"AZ-02", "AZ-03", "AZ-04"}
        assert all(row.currency == "EUR" for row in rows)
        regime = await service.get_regime(session, regime_id=rows[0].regime_id)
        assert regime is not None
        assert regime.code == "de_vob_b_abschlag"


@pytest.mark.asyncio
class TestOpeningAClock:
    async def test_the_statutory_dates_are_computed_and_stored(self, session):
        application, _ = await _application(session)
        assert application.due_date == date(2026, 4, 7)
        assert application.payment_notice_deadline == date(2026, 4, 12)
        assert application.pay_less_deadline == date(2026, 4, 17)
        assert application.final_date == date(2026, 4, 24)
        assert application.dates_overridden is False

    async def test_dates_stated_by_the_caller_win_and_mark_the_row(self, session):
        application, _ = await _application(session, final_date=date(2026, 5, 29))
        assert application.final_date == date(2026, 5, 29)
        # The rest still come from the regime.
        assert application.due_date == date(2026, 4, 7)
        assert application.dates_overridden is True

    async def test_recompute_will_not_silently_replace_hand_set_dates(self, session):
        application, regime = await _application(session, final_date=date(2026, 5, 29))

        _, written = await service.recompute_schedule(session, application=application, regime=regime)
        assert written is False
        assert application.final_date == date(2026, 5, 29)

        _, forced = await service.recompute_schedule(session, application=application, regime=regime, force=True)
        assert forced is True
        assert application.final_date == date(2026, 4, 24)
        assert application.dates_overridden is False

    async def test_money_is_stored_as_an_exact_decimal(self, session):
        application, _ = await _application(session, applied_amount=Decimal("124000.10"))
        assert application.applied_amount == Decimal("124000.10")
        assert isinstance(application.applied_amount, Decimal)


# ── The rule the module exists for ───────────────────────────────────────────


async def _findings(
    session: AsyncSession,
    application: StatutoryPaymentApplication,
    regime: PaymentRegime,
    *,
    as_of: date,
) -> dict[str, list]:
    notices = await service.list_notices(session, application_id=application.id)
    snapshot = service.clock_snapshot(application, regime, notices, as_of=as_of)
    results = await evaluate_clock(snapshot, application_id=str(application.id))
    grouped: dict[str, list] = {}
    for result in results:
        grouped.setdefault(result.rule_id, []).append(result)
    return grouped


@pytest.mark.asyncio
class TestNotifiedSum:
    async def test_silence_past_the_deadline_makes_the_applied_sum_payable(self, session):
        application, regime = await _application(session)
        # One day after the payment notice deadline of 2026-04-12.
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 13))

        assert "payment_clock.notified_sum" in findings
        finding = findings["payment_clock.notified_sum"][0]
        assert str(finding.severity) == "error"
        # The finding has to name the amount. A rule that says "a notice was
        # missed" without saying what it now costs is a reminder, not a finding.
        assert "124000.00 GBP" in finding.message
        assert finding.details["applied_amount"] == "124000.00"
        assert "the sum applied for becomes the notified sum" in finding.message

        summary = service.notified_sum(application, regime, [], as_of=date(2026, 4, 13))
        assert summary["source"] == "application"
        assert summary["amount"] == Decimal("124000.00")
        # The sentence is assembled here, in English, because it can only be
        # assembled in one language. The code and its parameters are how a
        # screen says the same thing in the reader's - so every value the
        # sentence interpolates has to travel with it.
        assert summary["reason"] == "application"
        assert set(summary["params"]) == {"deadline", "statute", "amount"}
        for value in summary["params"].values():
            assert value and value in summary["explanation"]

    async def test_a_payment_notice_served_in_time_settles_the_sum(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="payment_notice",
                issued_at=date(2026, 4, 10),
                notified_amount=Decimal("118500.00"),
                basis_of_calculation="Measured work to 31 March less retention at 3 percent.",
                reference="PN-014",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 13))
        assert "payment_clock.notified_sum" not in findings

        notices = await service.list_notices(session, application_id=application.id)
        summary = service.notified_sum(application, regime, notices, as_of=date(2026, 4, 13))
        assert summary["source"] == "payment_notice"
        assert summary["amount"] == Decimal("118500.00")
        assert summary["reason"] == "payment_notice"
        assert set(summary["params"]) == {"issued", "amount"}
        for value in summary["params"].values():
            assert value and value in summary["explanation"]

    async def test_the_window_being_open_is_not_a_breach(self, session):
        application, regime = await _application(session)
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 11))
        assert "payment_clock.notified_sum" not in findings

        summary = service.notified_sum(application, regime, [], as_of=date(2026, 4, 11))
        assert summary["source"] == "undetermined"
        assert summary["amount"] is None

    async def test_a_pay_less_notice_does_not_displace_the_notified_sum(self, session):
        # The mistake that loses the adjudication: a pay-less notice reduces
        # what has to be paid, it does not change what the notified sum is.
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="pay_less_notice",
                issued_at=date(2026, 4, 16),
                notified_amount=Decimal("60000.00"),
                basis_of_calculation="Defective blockwork to grid C, rectification quoted at 64000.",
                reference="PLN-014",
            ),
        )
        notices = await service.list_notices(session, application_id=application.id)
        summary = service.notified_sum(application, regime, notices, as_of=date(2026, 4, 20))
        assert summary["source"] == "application"
        assert summary["amount"] == Decimal("124000.00")

        findings = await _findings(session, application, regime, as_of=date(2026, 4, 20))
        message = findings["payment_clock.notified_sum"][0].message
        assert "does not displace the notified sum" in message

    async def test_a_regime_with_a_different_consequence_says_so(self, session):
        # Singapore bars the unstated reason rather than conceding the claim.
        application, regime = await _application(session, code="sg_sopa", currency="SGD")
        findings = await _findings(session, application, regime, as_of=date(2026, 5, 30))
        finding = findings["payment_clock.notified_sum"][0]
        assert "may not rely at adjudication" in finding.message
        assert "sum applied for becomes the notified sum" not in finding.message

        summary = service.notified_sum(application, regime, [], as_of=date(2026, 5, 30))
        assert summary["source"] == "undetermined"

    async def test_a_regime_with_no_notice_sequence_raises_nothing(self, session):
        application, regime = await _application(session, code="eu_late_payment", currency="EUR")
        findings = await _findings(session, application, regime, as_of=date(2026, 6, 30))
        assert "payment_clock.notified_sum" not in findings

    async def test_a_default_payment_notice_supplies_the_sum(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="default_payment_notice",
                issued_at=date(2026, 4, 14),
                notified_amount=Decimal("124000.00"),
                basis_of_calculation="Application 14 in full; no payment notice was served.",
                reference="DPN-014",
            ),
        )
        notices = await service.list_notices(session, application_id=application.id)
        summary = service.notified_sum(application, regime, notices, as_of=date(2026, 4, 15))
        assert summary["source"] == "default_payment_notice"
        assert summary["amount"] == Decimal("124000.00")
        # And it is not itself reported as late.
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 15))
        assert "payment_clock.notice_in_time" not in findings


@pytest.mark.asyncio
class TestGermanClock:
    """A German application through the service layer, end to end.

    The German regimes have no notice sequence, so the rule the module exists
    for must stay quiet on them forever, while the date arithmetic and the
    interest rule still work - a deadline under § 16 VOB/B is missed just as
    hard as one under the UK Act.
    """

    async def test_the_vob_b_dates_are_computed_and_stored(self, session):
        application, _ = await _application(
            session,
            code="de_vob_b_abschlag",
            currency="EUR",
            reference="AZ-03",
            application_date=date(2026, 3, 2),
            period_end=date(2026, 2, 27),
            period_start=date(2026, 2, 1),
            applied_amount=Decimal("941618.45"),
        )
        assert application.due_date == date(2026, 3, 2)
        assert application.final_date == date(2026, 3, 23)
        assert application.payment_notice_deadline is None
        assert application.pay_less_deadline is None

    async def test_silence_is_never_a_breach_under_a_german_regime(self, session):
        application, regime = await _application(
            session,
            code="de_vob_b_abschlag",
            currency="EUR",
            application_date=date(2026, 3, 2),
            period_end=date(2026, 2, 27),
        )
        # Long past every date the regime sets, still no notified-sum finding:
        # there was never a notice whose absence could have a consequence.
        findings = await _findings(session, application, regime, as_of=date(2026, 6, 30))
        assert "payment_clock.notified_sum" not in findings

    async def test_the_notified_sum_says_the_regime_has_no_notice_sequence(self, session):
        application, regime = await _application(
            session,
            code="de_vob_b_abschlag",
            currency="EUR",
            application_date=date(2026, 3, 2),
            period_end=date(2026, 2, 27),
        )
        summary = service.notified_sum(application, regime, [], as_of=date(2026, 6, 30))
        assert summary["source"] == "undetermined"
        assert summary["amount"] is None
        # Not "the window is still open": there is no window, and promising one
        # would tell a German reader to wait for a settling event that never
        # arrives under the VOB/B.
        assert "no payment notice sequence" in summary["explanation"]
        assert "window" not in summary["explanation"]

    async def test_unpaid_past_the_vob_b_final_date_accrues_german_interest(self, session):
        application, regime = await _application(
            session,
            code="de_vob_b_abschlag",
            currency="EUR",
            application_date=date(2026, 3, 2),
            period_end=date(2026, 2, 27),
            applied_amount=Decimal("941618.45"),
        )
        # Thirteen days past the final date of 2026-03-23.
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 5))
        finding = findings["payment_clock.statutory_interest"][0]
        assert str(finding.severity) == "warning"
        assert "941618.45 EUR" in finding.message
        assert finding.details["days_overdue"] == 13
        assert "plus 9 percent" in finding.message
        assert "§ 288 Abs. 2 BGB" in finding.message


# ── The remaining rules ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestNoticeRules:
    async def test_a_late_notice_names_the_deadline_and_the_days(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="payment_notice",
                issued_at=date(2026, 4, 15),  # deadline was 2026-04-12
                notified_amount=Decimal("118500.00"),
                basis_of_calculation="Measured work to 31 March.",
                reference="PN-014",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 20))
        finding = findings["payment_clock.notice_in_time"][0]
        assert str(finding.severity) == "error"
        assert "the payment notice deadline" in finding.message
        assert "2026-04-12" in finding.message
        assert "3 calendar day(s)" in finding.message
        assert finding.details["days_late"] == 3

        # A notice served out of time is not a notice, so the notified sum rule
        # fires as well. Both findings are the point.
        assert "payment_clock.notified_sum" in findings

    async def test_a_pay_less_notice_without_a_basis_is_invalid(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="pay_less_notice",
                issued_at=date(2026, 4, 16),
                notified_amount=Decimal("60000.00"),
                basis_of_calculation="",
                reference="PLN-014",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 20))
        finding = findings["payment_clock.pay_less_basis"][0]
        assert str(finding.severity) == "error"
        assert "the basis on which it is calculated" in finding.message
        assert finding.details["missing"] == ["the basis on which it is calculated"]

    async def test_a_pay_less_notice_without_a_sum_is_invalid_too(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="pay_less_notice",
                issued_at=date(2026, 4, 16),
                basis_of_calculation="Defective blockwork to grid C.",
                reference="PLN-015",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 20))
        assert findings["payment_clock.pay_less_basis"][0].details["missing"] == ["the sum considered due"]

    async def test_a_complete_pay_less_notice_raises_nothing(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="pay_less_notice",
                issued_at=date(2026, 4, 16),
                notified_amount=Decimal("60000.00"),
                basis_of_calculation="Defective blockwork to grid C, rectification quoted at 64000.",
                reference="PLN-016",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 20))
        assert "payment_clock.pay_less_basis" not in findings

    async def test_a_notice_in_another_currency_is_flagged_but_not_a_breach(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="payment_notice",
                issued_at=date(2026, 4, 10),
                notified_amount=Decimal("118500.00"),
                currency="EUR",
                basis_of_calculation="Measured work to 31 March.",
                reference="PN-EUR",
            ),
        )
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 13))
        finding = findings["payment_clock.notice_currency"][0]
        assert str(finding.severity) == "warning"
        assert finding.rule_id not in RULE_EVENT_TYPES  # shown, not filed


@pytest.mark.asyncio
class TestDateAndInterestRules:
    async def test_a_final_date_that_does_not_follow_the_due_date_is_an_error(self, session):
        application, regime = await _application(session, final_date=date(2026, 4, 7))
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 8))
        finding = findings["payment_clock.final_date_after_due_date"][0]
        assert str(finding.severity) == "error"
        assert "2026-04-07" in finding.message
        assert finding.details["days_between"] == 0

    async def test_a_healthy_sequence_raises_no_date_error(self, session):
        application, regime = await _application(session)
        findings = await _findings(session, application, regime, as_of=date(2026, 4, 8))
        assert "payment_clock.final_date_after_due_date" not in findings

    async def test_unpaid_past_the_final_date_accrues_interest_at_a_named_rate(self, session):
        application, regime = await _application(session)
        findings = await _findings(session, application, regime, as_of=date(2026, 5, 4))
        finding = findings["payment_clock.statutory_interest"][0]
        assert str(finding.severity) == "warning"
        assert "Bank of England base rate plus 8 percent" in finding.message
        assert finding.details["days_overdue"] == 10
        assert finding.details["outstanding_amount"] == "124000.00"

    async def test_a_part_payment_leaves_the_shortfall_running(self, session):
        application, regime = await _application(session)
        application.paid_at = date(2026, 4, 24)
        application.paid_amount = Decimal("100000.00")
        application.status = "paid"
        await session.flush()

        findings = await _findings(session, application, regime, as_of=date(2026, 5, 4))
        finding = findings["payment_clock.statutory_interest"][0]
        assert finding.details["outstanding_amount"] == "24000.00"

    async def test_paid_in_full_stops_the_interest(self, session):
        application, regime = await _application(session)
        application.paid_at = date(2026, 4, 24)
        application.paid_amount = Decimal("124000.00")
        application.status = "paid"
        await session.flush()

        findings = await _findings(session, application, regime, as_of=date(2026, 5, 4))
        assert "payment_clock.statutory_interest" not in findings

    async def test_a_paid_status_with_no_payment_date_is_not_evidence_of_payment(self, session):
        # A workflow tick somebody clicked is not the money arriving.
        application, regime = await _application(session)
        application.status = "paid"
        await session.flush()

        findings = await _findings(session, application, regime, as_of=date(2026, 5, 4))
        assert "payment_clock.statutory_interest" in findings


# ── The breach register ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBreachRegister:
    async def _record(
        self,
        session: AsyncSession,
        application: StatutoryPaymentApplication,
        regime: PaymentRegime,
        *,
        as_of: date,
    ) -> list[PaymentClockEvent]:
        notices = await service.list_notices(session, application_id=application.id)
        snapshot = service.clock_snapshot(application, regime, notices, as_of=as_of)
        findings = await evaluate_clock(snapshot, application_id=str(application.id))
        return await service.record_clock_events(session, application=application, findings=findings)

    async def test_a_breach_is_filed_with_its_consequence_in_words(self, session):
        application, regime = await _application(session)
        await self._record(session, application, regime, as_of=date(2026, 4, 13))

        events = await service.list_events(session, application_id=application.id)
        missed = [event for event in events if event.event_type == "payment_notice_missed"]
        assert len(missed) == 1
        assert missed[0].rule_id == "payment_clock.notified_sum"
        assert missed[0].deadline_date == date(2026, 4, 12)
        assert missed[0].amount == Decimal("124000.00")
        assert missed[0].currency == "GBP"
        assert "notified sum" in missed[0].consequence

    async def test_reading_the_clock_twice_does_not_file_the_breach_twice(self, session):
        application, regime = await _application(session)
        await self._record(session, application, regime, as_of=date(2026, 4, 13))
        first = await service.list_events(session, application_id=application.id)
        first_detected = {event.event_type: event.detected_at for event in first}

        await self._record(session, application, regime, as_of=date(2026, 4, 14))
        second = await service.list_events(session, application_id=application.id)

        assert len(second) == len(first)
        # ``detected_at`` keeps saying when the breach was first seen, which is
        # the date interest and time bars get argued from.
        assert {event.event_type: event.detected_at for event in second} == first_detected

    async def test_a_correction_removes_the_entry_it_invalidates(self, session):
        application, regime = await _application(session)
        await self._record(session, application, regime, as_of=date(2026, 4, 13))
        assert any(
            event.event_type == "payment_notice_missed"
            for event in await service.list_events(session, application_id=application.id)
        )

        # The notice was served all along and reached the system late.
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="payment_notice",
                issued_at=date(2026, 4, 10),
                notified_amount=Decimal("118500.00"),
                basis_of_calculation="Measured work to 31 March.",
                reference="PN-014",
            ),
        )
        await self._record(session, application, regime, as_of=date(2026, 4, 13))
        assert not any(
            event.event_type == "payment_notice_missed"
            for event in await service.list_events(session, application_id=application.id)
        )

    async def test_two_bad_notices_file_two_entries_not_one(self, session):
        application, regime = await _application(session)
        for reference in ("PLN-A", "PLN-B"):
            await service.create_notice(
                session,
                application=application,
                body=schemas.NoticeCreate(
                    notice_type="pay_less_notice",
                    issued_at=date(2026, 4, 16),
                    notified_amount=Decimal("60000.00"),
                    basis_of_calculation="",
                    reference=reference,
                ),
            )
        await self._record(session, application, regime, as_of=date(2026, 4, 20))
        events = await service.list_events(session, application_id=application.id)
        filed = [event for event in events if event.event_type == "pay_less_notice_without_basis"]
        assert len(filed) == 2
        assert {event.detail["element_ref"] for event in filed} == {"PLN-A", "PLN-B"}

    async def test_the_register_reads_by_project(self, session):
        application, regime = await _application(session)
        await self._record(session, application, regime, as_of=date(2026, 4, 13))
        by_project = await service.list_events(session, project_id=application.project_id)
        assert by_project
        assert {event.application_id for event in by_project} == {application.id}

    async def test_deleting_a_clock_takes_its_notices_and_events_with_it(self, session):
        application, regime = await _application(session)
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="pay_less_notice",
                issued_at=date(2026, 4, 16),
                basis_of_calculation="",
                reference="PLN-C",
            ),
        )
        await self._record(session, application, regime, as_of=date(2026, 4, 20))
        application_id = application.id

        await service.delete_application(session, application=application)

        notices = await session.scalar(
            select(func.count()).select_from(PaymentNotice).where(PaymentNotice.application_id == application_id)
        )
        events = await session.scalar(
            select(func.count())
            .select_from(PaymentClockEvent)
            .where(PaymentClockEvent.application_id == application_id)
        )
        assert notices == 0
        assert events == 0


@pytest.mark.asyncio
class TestBlockingFindings:
    async def test_errors_are_separated_from_the_notes(self, session):
        application, regime = await _application(session)
        notices = await service.list_notices(session, application_id=application.id)
        snapshot = service.clock_snapshot(application, regime, notices, as_of=date(2026, 5, 4))
        results = await evaluate_clock(snapshot, application_id=str(application.id))

        blocking = blocking_findings(results)
        assert {result.rule_id for result in blocking} == {"payment_clock.notified_sum"}
        # The interest warning is real and is not an error: it reports a
        # consequence, it does not accuse anybody of a procedural failure.
        assert "payment_clock.statutory_interest" in {result.rule_id for result in results}


@pytest.mark.asyncio
class TestListing:
    async def test_overdue_only_narrows_to_what_is_actually_owed(self, session):
        application, _ = await _application(session)
        project_id = application.project_id

        everything = await service.list_applications(session, project_id=project_id)
        assert len(everything) == 1

        open_window = await service.list_applications(session, project_id=project_id, overdue_as_of=date(2026, 4, 20))
        assert open_window == []

        overdue = await service.list_applications(session, project_id=project_id, overdue_as_of=date(2026, 5, 4))
        assert [row.id for row in overdue] == [application.id]

        application.status = "paid"
        await session.flush()
        assert await service.list_applications(session, project_id=project_id, overdue_as_of=date(2026, 5, 4)) == []


# ── The wire form ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestTheWireForm:
    """The response the API actually sends, assembled from real rows.

    Every other test in this file reads the ORM side. Nothing there exercises
    the response models, so a field the ORM does not supply, or a key
    ``NotifiedSum`` does not declare, would surface as a 500 from a route no
    test calls rather than as a failure here.

    Note what the string assertions below do *not* prove: Pydantic v2 already
    renders ``Decimal`` as a string in JSON mode, so they would pass with no
    serialiser at all. What ``_money_string`` adds is tested separately, in
    ``test_money_is_plain_decimal_not_however_python_prints_it``.
    """

    async def test_the_whole_clock_serialises_and_money_stays_a_string(self, session):
        from app.modules.payment_clock.router import _application_response, _findings

        application, regime = await _application(session, applied_amount=Decimal("124000.10"))
        # Served three days after the 2026-04-12 deadline, so it is a notice
        # that exists and is out of time: notices, findings and the register all
        # carry money in the same response.
        await service.create_notice(
            session,
            application=application,
            body=schemas.NoticeCreate(
                notice_type="payment_notice",
                issued_at=date(2026, 4, 15),
                notified_amount=Decimal("118500.00"),
                currency="GBP",
                basis_of_calculation="Measured work to 31 March.",
            ),
        )
        reading_date = date(2026, 5, 4)
        notices = await service.list_notices(session, application_id=application.id)
        snapshot = service.clock_snapshot(application, regime, notices, as_of=reading_date)
        findings = await evaluate_clock(snapshot, application_id=str(application.id))
        await service.record_clock_events(session, application=application, findings=findings)
        events = await service.list_events(session, application_id=application.id)
        summary = service.notified_sum(application, regime, notices, as_of=reading_date)
        schedule = service.build_schedule(
            regime,
            application_date=application.application_date,
            period_end=application.period_end,
        )
        payload = schemas.ApplicationClock(
            application=_application_response(application, regime),
            notices=[schemas.NoticeResponse.model_validate(notice) for notice in notices],
            events=[schemas.EventResponse.model_validate(event) for event in events],
            findings=_findings(findings),
            notified_sum=schemas.NotifiedSum(**summary),
            derivation=schedule.derivation,
            interest_description=service.regime_summary(regime),
        )

        wire = payload.model_dump(mode="json")

        assert wire["application"]["applied_amount"] == "124000.10"
        assert wire["notices"][0]["notified_amount"] == "118500.00"
        # A late notice is not a notice, so the sum applied for stands.
        assert wire["notified_sum"]["source"] == "application"
        assert wire["notified_sum"]["amount"] == "124000.10"
        filed = {event["event_type"]: event for event in wire["events"]}
        assert "payment_notice_missed" in filed
        assert filed["payment_notice_missed"]["amount"] == "124000.10"
        assert filed["notice_out_of_time"]["days_late"] == 3

        # And the whole object survives the encoder FastAPI will hand it to.
        assert "124000.10" in payload.model_dump_json()

    async def test_money_is_plain_decimal_not_however_python_prints_it(self, session):
        # Pydantic's own Decimal handling passes ``str(value)`` through, which
        # keeps whatever exponent form the Decimal happens to carry. A sum that
        # reaches a screen as "1E+3" is not a sum anybody can read. That is what
        # the serialiser is for, and it is invisible in the test above because a
        # value that came back from a NUMERIC column is already in plain form.
        assert schemas.NotifiedSum(amount=Decimal("1E+3")).model_dump(mode="json")["amount"] == "1000"
        assert schemas.NotifiedSum(amount=None).model_dump(mode="json")["amount"] is None
        # Trailing zeros are significant in money and are not trimmed.
        assert schemas.NotifiedSum(amount=Decimal("124000.10")).model_dump(mode="json")["amount"] == "124000.10"

        # Non-finite money is refused at the door rather than rendered. The
        # ``is_finite`` branch inside ``_money_string`` is therefore unreachable
        # through any of these models, which is the better outcome: NaN never
        # becomes a plausible-looking "0" that somebody then pays against.
        with pytest.raises(ValidationError):
            schemas.NotifiedSum(amount=Decimal("NaN"))
        assert schemas._money_string(Decimal("NaN")) == "0"

    async def test_the_regime_response_carries_the_interest_clause(self, session):
        from app.modules.payment_clock.router import _regime_response

        regime = await _regime(session)
        wire = _regime_response(regime).model_dump(mode="json")

        assert wire["code"] == "uk_hgcra"
        assert "Bank of England base rate plus 8 percent" in wire["interest_description"]
        # The clause is composed on the way out. Reading it off the column would
        # have shown the basis word, not a sentence anybody can act on.
        assert regime.interest_basis == "reference_rate_plus_margin"


# ── Permissions ──────────────────────────────────────────────────────────────


class TestPaymentClockPermissions:
    """Every permission the router names has to exist in the registry.

    ``RequirePermission`` denies an unregistered key rather than waving it
    through, so a module that forgets its ``permissions.py`` ships endpoints
    only an admin can reach, and no test that calls them as an admin notices.
    """

    @staticmethod
    def _router_permissions() -> set[str]:
        from app.modules.payment_clock.router import router

        found: set[str] = set()
        for route in router.routes:
            for dependency in getattr(route, "dependencies", []) or []:
                call = getattr(dependency, "dependency", None)
                key = getattr(call, "permission", None)
                if isinstance(key, str):
                    found.add(key)
        return found

    def test_every_permission_the_router_asks_for_is_registered(self):
        from app.core.permissions import permission_registry

        register_payment_clock_permissions()
        asked = self._router_permissions()
        assert asked, "no route declared a permission; the guard would be vacuous"
        registered = set(permission_registry.list_all())
        assert asked <= registered, f"unregistered: {sorted(asked - registered)}"

    def test_every_route_declares_one(self):
        from app.modules.payment_clock.router import router

        unguarded = [
            getattr(route, "path", "?")
            for route in router.routes
            if not any(
                isinstance(getattr(getattr(dep, "dependency", None), "permission", None), str)
                for dep in (getattr(route, "dependencies", []) or [])
            )
        ]
        assert unguarded == []

    def test_the_roles_split_where_the_consequences_do(self):
        from app.core.permissions import Role, permission_registry

        register_payment_clock_permissions()
        assert permission_registry.role_has_permission(Role.VIEWER, "payment_clock.read") is True
        assert permission_registry.role_has_permission(Role.VIEWER, "payment_clock.write") is False
        assert permission_registry.role_has_permission(Role.EDITOR, "payment_clock.write") is True
        # Overriding a statutory date silences the arithmetic the module exists
        # for, so it sits with the role that answers for the contract.
        assert permission_registry.role_has_permission(Role.EDITOR, "payment_clock.manage") is False
        assert permission_registry.role_has_permission(Role.MANAGER, "payment_clock.manage") is True


def test_tables_are_named_by_convention():
    assert PaymentRegime.__tablename__ == "oe_payment_clock_regime"
    assert StatutoryPaymentApplication.__tablename__ == "oe_payment_clock_application"
    assert PaymentNotice.__tablename__ == "oe_payment_clock_notice"
    assert PaymentClockEvent.__tablename__ == "oe_payment_clock_event"


def test_the_seeder_is_exported_for_the_module_loader():
    # Imported by name in the service; a rename here would only show up at
    # runtime on a fresh deployment, which is the worst place to find it.
    assert callable(seed_payment_regimes)
