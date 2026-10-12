# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plan recurrence (rules 6, 7) and the mandate resolver (rules 11 to 15) as pure functions."""

from __future__ import annotations

from datetime import date

import pytest

from app.modules.stakeholders import mandates as md
from app.modules.stakeholders import recurrence as rc
from app.modules.stakeholders.catalogue import DEFAULT_FRAMEWORK_ID, FRAMEWORK_KIND, register_kind


@pytest.fixture(scope="module")
def fw():
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    return get_catalogue_kind(FRAMEWORK_KIND).get_shipped(DEFAULT_FRAMEWORK_ID)


# ── recurrence ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "FREQ=HOURLY",
        "FREQ=WEEKLY;BYHOUR=9",
        "FREQ=WEEKLY;COUNT=2;UNTIL=20261231",
        "INTERVAL=2",
        "FREQ=DAILY;UNTIL=20261231T000000Z",
        "nonsense",
    ],
)
def test_unsupported_rules_are_refused(bad: str) -> None:
    with pytest.raises(rc.RecurrenceError):
        rc.normalise(bad)


def test_normalise_is_canonical() -> None:
    assert rc.normalise("RRULE:freq=weekly;byday=mo;interval=2") == "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"
    assert rc.normalise(None) == "once"
    assert rc.normalise("once") == "once"


def test_weekly_next_due_and_advance() -> None:
    start = date(2026, 10, 5)  # Monday
    f = "FREQ=WEEKLY;BYDAY=MO"
    assert rc.next_due(frequency=f, trigger_kind=None, starts_on=start, ends_on=None, done=[]) == start
    assert rc.next_due(frequency=f, trigger_kind=None, starts_on=start, ends_on=None, done=[start]) == date(
        2026, 10, 12
    )


def test_two_events_for_one_occurrence_count_once() -> None:
    start = date(2026, 10, 5)
    f = "FREQ=WEEKLY;BYDAY=MO"
    one = rc.next_due(frequency=f, trigger_kind=None, starts_on=start, ends_on=None, done=[start])
    two = rc.next_due(frequency=f, trigger_kind=None, starts_on=start, ends_on=None, done=[start, start])
    assert one == two == date(2026, 10, 12)


def test_month_end_rule_lands_on_february_last_day() -> None:
    f = "FREQ=MONTHLY;BYMONTHDAY=-1"
    start = date(2027, 1, 31)
    assert rc.next_occurrence(f, start, None) == date(2027, 1, 31)
    assert rc.next_occurrence(f, start, date(2027, 1, 31)) == date(2027, 2, 28)
    assert rc.next_occurrence(f, date(2028, 1, 31), date(2028, 1, 31)) == date(2028, 2, 29)


def test_monthly_on_the_31st_skips_short_months_as_rfc5545_says() -> None:
    assert rc.next_occurrence("FREQ=MONTHLY", date(2027, 1, 31), date(2027, 1, 31)) == date(2027, 3, 31)


def test_first_monday_of_the_month() -> None:
    assert rc.next_occurrence("FREQ=MONTHLY;BYDAY=1MO", date(2026, 10, 1), date(2026, 10, 5)) == date(2026, 11, 2)


def test_dates_do_not_move_across_a_dst_change() -> None:
    # Europe switches on 2026-10-25 and the US on 2026-11-01; dates carry no clock, so nothing shifts.
    f = "FREQ=WEEKLY;BYDAY=SU"
    got = rc.occurrences_between(f, date(2026, 10, 18), date(2026, 10, 18), date(2026, 11, 8))
    assert got == [date(2026, 10, 18), date(2026, 10, 25), date(2026, 11, 1), date(2026, 11, 8)]


def test_ends_on_and_count_stop_the_series() -> None:
    f = "FREQ=WEEKLY;COUNT=2"
    start = date(2026, 10, 5)
    assert rc.next_occurrence(f, start, date(2026, 10, 12)) is None
    assert rc.next_occurrence("FREQ=WEEKLY", start, date(2026, 10, 5), ends_on=date(2026, 10, 10)) is None


def test_once_and_trigger_items() -> None:
    d = date(2026, 11, 3)
    assert rc.next_due(frequency="once", trigger_kind=None, starts_on=d, ends_on=None, done=[]) == d
    assert rc.next_due(frequency="once", trigger_kind=None, starts_on=d, ends_on=None, done=[d]) is None
    # gate trigger: not due before the gate moves to review
    assert rc.next_due(frequency=None, trigger_kind="gate", starts_on=None, ends_on=None, done=[]) is None
    fired = date(2026, 12, 1)
    assert (
        rc.next_due(frequency=None, trigger_kind="gate", starts_on=None, ends_on=None, done=[], triggered_on=fired)
        == fired
    )
    assert (
        rc.next_due(frequency=None, trigger_kind="gate", starts_on=None, ends_on=None, done=[fired], triggered_on=fired)
        is None
    )


# ── mandates ─────────────────────────────────────────────────────────────

TODAY = date(2026, 10, 12)
R = md.MandateRow


def test_one_decider_resolved_to_valid_holders() -> None:
    rows = [R("order_award", "role", "client", "D"), R("order_award", "role", "project_manager", "P")]
    holders = [
        md.Holder("client", user_id="u-old", valid_to=date(2026, 9, 30)),
        md.Holder("client", user_id="u-new", valid_from=date(2026, 10, 1)),
    ]
    res = md.who_decides(rows, "order_award", "", holders, [], TODAY)
    assert res.holder_code == "client"
    assert res.user_ids == ["u-new"]  # rule 14: an expired holder is not returned
    assert res.flags == []


def test_no_decider_is_mandate_missing() -> None:
    res = md.who_decides([R("order_award", "role", "client", "P")], "order_award", "", [], [], TODAY)
    assert res.flags == ["mandate_missing"]


def test_vacant_role_is_flagged() -> None:
    res = md.who_decides(
        [R("x", "role", "client", "D")], "x", "", [md.Holder("client", "u", valid_to=date(2026, 1, 1))], [], TODAY
    )
    assert res.flags == ["role_vacant"]
    assert res.user_ids == []


def test_scope_falls_back_to_the_project_row() -> None:
    rows = [
        R("design_decision", "role", "client_pm", "D"),
        R("design_decision", "role", "lead_designer", "D", "facade"),
    ]
    holders = [md.Holder("client_pm", "pm"), md.Holder("lead_designer", "ld")]
    assert md.who_decides(rows, "design_decision", "facade", holders, [], TODAY).user_ids == ["ld"]
    assert md.who_decides(rows, "design_decision", "roof", holders, [], TODAY).user_ids == ["pm"]


def test_decider_counts_find_two_deciders() -> None:
    rows = [R("x", "role", "a", "D"), R("x", "role", "b", "D"), R("x", "role", "c", "D", "lot1")]
    assert md.decider_counts(rows) == {("x", ""): 2, ("x", "lot1"): 1}


def test_missing_deciders_only_for_required_types(fw) -> None:
    missing = md.missing_deciders(fw, [R("order_award", "role", "client", "D")])
    required = {d.code for d in fw.decision_types if d.required}
    assert "order_award" not in missing
    assert set(missing) == required - {"order_award"}
    assert "user_change" not in missing  # not required


def test_body_members_and_quorum() -> None:
    body = md.Body(
        "steering_committee",
        "majority",
        members=(
            md.Member(role_code="client", voting=True),
            md.Member(user_id="u2", voting=True),
            md.Member(user_id="u3", voting=True, valid_to=date(2026, 9, 1)),
            md.Member(user_id="guest", voting=False),
        ),
    )
    holders = [md.Holder("client", "u1")]
    res = md.who_decides(
        [R("gate_decision", "body", "steering_committee", "D")], "gate_decision", "", holders, [body], TODAY
    )
    assert res.user_ids == ["guest", "u1", "u2"]
    assert (res.quorum_needed, res.quorum_present) == (2, 2)
    assert "body_inquorate" not in res.flags


def test_body_inquorate_when_seats_expire() -> None:
    body = md.Body(
        "board",
        "unanimous",
        members=(md.Member(user_id="u1"), md.Member(user_id="u2", valid_to=date(2026, 10, 1))),
    )
    res = md.who_decides([R("x", "body", "board", "D")], "x", "", [], [body], TODAY)
    assert res.flags == ["body_inquorate"]
    mm = md.Body("board", "min_members", quorum_min=3, members=(md.Member(user_id="u1"), md.Member(user_id="u2")))
    assert md.who_decides([R("x", "body", "board", "D")], "x", "", [], [mm], TODAY).flags == ["body_inquorate"]


def test_vacant_roles(fw) -> None:
    holders = [md.Holder("client", contact_id="c1"), md.Holder("project_manager", "u")]
    assert md.vacant_roles(fw, holders, TODAY, required_only=True) == ["client_pm"]


def test_self_approval_conflict_severity_follows_the_framework(fw) -> None:
    rows = [
        R("order_award", "role", "project_manager", "P"),
        R("order_award", "role", "client", "D"),
        R("design_decision", "role", "lead_designer", "P"),
        R("design_decision", "role", "client_pm", "D"),
    ]
    holders = [
        md.Holder("project_manager", "same"),
        md.Holder("client", "same"),
        md.Holder("lead_designer", "u2"),
        md.Holder("client_pm", "u2"),
    ]
    found = {c.decision_type: c for c in md.conflicts(fw, rows, holders, [], TODAY)}
    assert found["order_award"].severity == "error"  # forbid_self_approval
    assert found["order_award"].letters == ("P", "D")
    assert found["design_decision"].severity == "warning"
    assert not found["design_decision"].acknowledged


def test_conflict_acknowledged_by_rationale_on_the_role_assignment(fw) -> None:
    rows = [R("design_decision", "role", "lead_designer", "P"), R("design_decision", "role", "client_pm", "D")]
    holders = [
        md.Holder("lead_designer", "u2"),
        md.Holder("client_pm", "u2", conflict_rationale="Small project, one lead"),
    ]
    (c,) = md.conflicts(fw, rows, holders, [], TODAY)
    assert c.acknowledged


def test_no_conflict_for_different_people_or_expired_holder(fw) -> None:
    rows = [R("order_award", "role", "project_manager", "P"), R("order_award", "role", "client", "D")]
    assert md.conflicts(fw, rows, [md.Holder("project_manager", "a"), md.Holder("client", "b")], [], TODAY) == []
    expired = [md.Holder("project_manager", "a", valid_to=date(2026, 1, 1)), md.Holder("client", "a")]
    assert md.conflicts(fw, rows, expired, [], TODAY) == []


def test_decide_and_approve_conflict_through_a_body(fw) -> None:
    rows = [R("scope_change", "body", "steering_committee", "D"), R("scope_change", "role", "client", "A")]
    body = md.Body("steering_committee", members=(md.Member(role_code="client"),))
    (c,) = md.conflicts(fw, rows, [md.Holder("client", "u1")], [body], TODAY)
    assert c.letters == ("D", "A")
    assert c.severity == "error"
