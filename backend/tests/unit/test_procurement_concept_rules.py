# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure rules of the procurement concept: thresholds, lots, consistency, shortlist, schedule, frameworks.

Each test names the SPEC rule it pins and contains the case that would pass if
the rule were missing (a breach that must be reported, or a boundary that must
flip).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.procurement_concept import evaluator as ev
from app.modules.procurement_concept.catalogue import (
    CONTRACT_PACKAGE_KIND_MAP,
    PROCUREMENT_KIND,
    ProcurementCatalogue,
    register_kind,
)
from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

D2026 = date(2026, 6, 1)
D2025 = date(2025, 6, 1)


def _cat(cid: str) -> ProcurementCatalogue:
    register_kind()
    return get_catalogue_kind(PROCUREMENT_KIND).get_shipped(cid)


EU = ev.ConceptFacts(jurisdiction="eu", client_type="sub_central", public_client=True)
PRIVATE = ev.ConceptFacts(jurisdiction="none", client_type="private", public_client=False)


def pkg(code: str = "W1", kind: str = "construction", value: str | None = "1000000", **kw) -> ev.PackageFacts:
    return ev.PackageFacts(
        id=kw.pop("id", code),
        code=code,
        cp_kind=kind,
        estimated_value=None if value is None else Decimal(value),
        currency=kw.pop("currency", "EUR"),
        **kw,
    )


def codes(findings) -> list[str]:
    return [f["code"] for f in findings]


# ── Threshold resolver (rules 2, 4, 5) ──────────────────────────────────


@pytest.mark.parametrize(
    ("facts", "kind", "value", "day", "status"),
    [
        (EU, "construction", "5403999.99", D2026, "below"),
        (EU, "construction", "5404000", D2026, "above"),  # equal to the threshold is above
        (EU, "supply", "215999", D2026, "below"),
        (EU, "supply", "216000", D2026, "above"),
        # Central government has the lower figure for the same value.
        (ev.ConceptFacts("eu", "central", True), "supply", "150000", D2026, "above"),
        # Design is services, never works (rule 7): 300k design is above, 300k works is below.
        (EU, "design", "300000", D2026, "above"),
        (EU, "construction", "300000", D2026, "below"),
        (PRIVATE, "construction", "90000000", D2026, "not_applicable"),
    ],
)
def test_threshold_table(facts, kind, value, day, status) -> None:
    p = pkg(kind=kind, value=value)
    assert ev.threshold_view(_cat("eu"), facts, p, [p], day).status == status


def test_threshold_valid_on_the_planned_start_date_not_today() -> None:
    """2024-2025 works threshold was 5,538,000 (unconfirmed); 5,450,000 is above in 2026, below in 2025."""
    p = pkg(value="5450000")
    in_2026 = ev.threshold_view(_cat("eu"), EU, p, [p], D2026)
    in_2025 = ev.threshold_view(_cat("eu"), EU, p, [p], D2025)
    assert in_2026.status == "above"
    assert in_2026.thresholds[0]["amount"] == "5404000"
    assert in_2025.thresholds[0]["amount"] == "5538000"
    assert in_2025.status == "unconfirmed"


def test_expired_threshold_version_is_not_applied() -> None:
    p = pkg(value="5450000")
    view = ev.threshold_view(_cat("eu"), EU, p, [p], date(2028, 3, 1))
    assert view.status == "not_applicable"


def test_vat_basis_gross_converts_a_net_value() -> None:
    """UK figures include VAT: 4,400,000 net at 20% = 5,280,000 gross, above 5,193,000."""
    uk = ev.ConceptFacts("uk", "central", True, vat_rate_pct=Decimal("20"))
    p = pkg(value="4400000", currency="GBP")
    view = ev.threshold_view(_cat("uk"), uk, p, [p], D2026)
    assert view.thresholds[0]["compared_value"] == "5280000.00"
    no_vat = ev.threshold_view(_cat("uk"), ev.ConceptFacts("uk", "central", True), p, [p], D2026)
    assert no_vat.thresholds[0]["compared_value"] == "4400000.00"


def test_foreign_currency_without_rate_is_unresolved_and_blocks_public_approval() -> None:
    p = pkg(value="100", currency="USD")
    view = ev.threshold_view(_cat("eu"), EU, p, [p], D2026)
    assert view.status == "unresolved"
    f = next(f for f in view.findings if f["code"] == "threshold_currency_unresolved")
    assert f["severity"] == "warning"
    assert f["blocks_approval"] is True


def test_unconfirmed_threshold_only_warns() -> None:
    """UK thresholds ship unconfirmed: a direct award at 50m is a warning, never an error (rule 5)."""
    uk = ev.ConceptFacts("uk", "central", True)
    p = pkg(value="50000000", currency="GBP", procedure_code="direct_award")
    fs = ev.procedure_findings(_cat("uk"), uk, p, [p], D2026)
    assert "procedure_not_allowed_above_threshold" in codes(fs)
    assert {f["severity"] for f in fs} == {"warning"}


def test_verified_threshold_breach_is_an_error() -> None:
    p = pkg(value="6000000", procedure_code="direct_award")
    fs = ev.procedure_findings(_cat("eu"), EU, p, [p], D2026)
    f = next(f for f in fs if f["code"] == "procedure_not_allowed_above_threshold")
    assert f["severity"] == "error"
    below = pkg(value="100000", procedure_code="direct_award")
    assert ev.procedure_findings(_cat("eu"), EU, below, [below], D2026) == []


def test_private_procedure_refused_for_public_client_above_threshold_only() -> None:
    above = pkg(value="6000000", procedure_code="two_stage_negotiated")
    below = pkg(value="100000", procedure_code="two_stage_negotiated")
    assert "procedure_not_allowed_above_threshold" in codes(
        ev.procedure_findings(_cat("eu"), EU, above, [above], D2026)
    )
    assert ev.procedure_findings(_cat("eu"), EU, below, [below], D2026) == []


def test_private_client_cannot_use_a_public_only_procedure() -> None:
    p = pkg(value="100", procedure_code="competitive_dialogue")
    assert codes(ev.procedure_findings(_cat("neutral"), PRIVATE, p, [p], D2026)) == ["procedure_not_allowed_for_client"]


def test_procedure_picker_filters_with_reason() -> None:
    p = pkg(value="6000000")
    rows = {r["code"]: r for r in ev.allowed_procedures(_cat("eu"), EU, p, [p], D2026)}
    assert rows["open"]["allowed"] is True
    assert rows["direct_award"] == {**rows["direct_award"], "allowed": False, "reason": "not_allowed_at_value"}
    assert rows["sealed_bid"]["allowed"] is False


# ── Lot aggregation (rule 3) ────────────────────────────────────────────


def test_three_works_lots_are_aggregated_above_the_threshold() -> None:
    """Three 2m lots: each below, together 6m above; a direct award is splitting."""
    lots = [pkg(f"W{i}", value="2000000", procedure_code="direct_award") for i in (1, 2, 3)]
    view = ev.threshold_view(_cat("eu"), EU, lots[0], lots, D2026)
    assert view.aggregated_value == Decimal("6000000")
    assert view.status == "above"
    assert "lot_splitting_avoids_threshold" in codes(ev.procedure_findings(_cat("eu"), EU, lots[0], lots, D2026))
    open_lots = [pkg(f"W{i}", value="2000000", procedure_code="open") for i in (1, 2, 3)]
    assert ev.procedure_findings(_cat("eu"), EU, open_lots[0], open_lots, D2026) == []


def test_supplies_aggregate_per_lot_group_only() -> None:
    a = pkg("S1", "supply", "150000", lot_group="steel")
    b = pkg("S2", "supply", "150000", lot_group="steel")
    c = pkg("S3", "supply", "150000", lot_group="glass")
    agg = ev.aggregated_values(_cat("eu"), [a, b, c])
    assert agg == {"S1": Decimal("300000"), "S2": Decimal("300000"), "S3": Decimal("150000")}


def test_cancelled_lots_do_not_count() -> None:
    a = pkg("W1", value="3000000")
    b = pkg("W2", value="3000000", state="cancelled")
    assert ev.aggregated_values(_cat("eu"), [a, b])["W1"] == Decimal("3000000")


def test_small_lot_exemption_within_cap_allows_direct_award() -> None:
    big = pkg("W1", value="5500000", procedure_code="open")
    small = pkg("W2", value="900000", procedure_code="direct_award", small_lot_exemption=True)
    view = ev.threshold_view(_cat("eu"), EU, small, [big, small], D2026)
    assert view.small_lot_exempt is True
    assert view.status == "unconfirmed"  # the exemption rule itself is unconfirmed, so warnings only
    # Above the lot cap the exemption is refused.
    too_big = pkg("W2", value="1200000", procedure_code="direct_award", small_lot_exemption=True)
    v2 = ev.threshold_view(_cat("eu"), EU, too_big, [big, too_big], D2026)
    assert v2.small_lot_exempt is False
    assert "lot_splitting_avoids_threshold" in codes(v2.findings)


def test_small_lot_exemption_where_the_catalogue_has_no_rule_is_an_error() -> None:
    uk = ev.ConceptFacts("uk", "central", True)
    p = pkg("W1", value="100", currency="GBP", small_lot_exemption=True)
    f = next(
        f
        for f in ev.threshold_view(_cat("uk"), uk, p, [p], D2026).findings
        if f["code"] == "lot_splitting_avoids_threshold"
    )
    assert f["severity"] == "error"


# ── Plan and consistency (rules 1, 6, 7, 12) ────────────────────────────


def test_contract_package_kind_mapping_is_total() -> None:
    mod3_kinds = {
        "design",
        "construction",
        "design_and_construction",
        "supply",
        "supply_and_install",
        "management_services",
        "operation",
        "project_agreement",
    }
    assert set(CONTRACT_PACKAGE_KIND_MAP) == mod3_kinds
    kinds = {k.code for k in _cat("neutral").package_kinds}
    assert {v for v in CONTRACT_PACKAGE_KIND_MAP.values() if v} <= kinds


def test_every_contract_package_needs_an_award_package_except_the_project_agreement() -> None:
    cps = [
        {"id": "a", "code": "A", "kind": "construction"},
        {"id": "b", "code": "B", "kind": "project_agreement"},
        {"id": "c", "code": "C", "kind": "supply"},
    ]
    assert [f["ref"] for f in ev.plan_findings(cps, {"a"})] == ["C"]


def test_design_package_needs_a_fee_and_services_rules() -> None:
    assert "design_fee_estimate_missing" in codes(
        ev.package_findings(_cat("eu"), pkg("D1", "design", None, procedure_code="open"))
    )
    assert ev.package_findings(_cat("eu"), pkg("D1", "design", "200000", procedure_code="open")) == []


def test_advance_package_needs_reason_and_release() -> None:
    no_reason = pkg(is_advance=True, procedure_code="open")
    assert {"advance_without_reason", "advance_package_not_released"} <= set(
        codes(ev.package_findings(_cat("eu"), no_reason))
    )
    ok = pkg(is_advance=True, advance_reason="Piling before permit", advance_released=True, procedure_code="open")
    assert ev.package_findings(_cat("eu"), ok) == []


def test_design_build_package_needs_functional_tender_basis() -> None:
    db = pkg("DB", "design_and_construction", procedure_code="open", tender_basis="detailed")
    assert codes(ev.consistency_findings(_cat("eu"), "design_build", [db])) == [
        "procedure_inconsistent_with_delivery_form"
    ]
    fn = pkg("DB", "design_and_construction", procedure_code="open", tender_basis="functional")
    assert ev.consistency_findings(_cat("eu"), "design_build", [fn]) == []
    assert ev.consistency_findings(_cat("eu"), "design_bid_build_single", [db]) == []


def test_cm_at_risk_main_package_needs_two_stages() -> None:
    main = pkg("GMP", "construction", procedure_code="open")
    trade = pkg("T1", "construction", procedure_code="open", parent_id="GMP")
    assert [f["ref"] for f in ev.consistency_findings(_cat("eu"), "cm_at_risk", [main, trade])] == ["GMP"]
    two = pkg("GMP", "construction", procedure_code="restricted")
    assert ev.consistency_findings(_cat("eu"), "cm_at_risk", [two, trade]) == []


def test_split_form_with_one_works_package_warns() -> None:
    f = ev.consistency_findings(_cat("eu"), "design_bid_build_split", [pkg("W1")])
    assert [(x["code"], x["severity"]) for x in f] == [("split_form_without_trade_packages", "warning")]


# ── Prequalification (rules 8, 10) ──────────────────────────────────────

CRIT = [
    {"code": "exclusion_grounds", "kind": "pass_fail", "weight": "0"},
    {"code": "similar_projects", "kind": "scored", "weight": "60"},
    {"code": "technical_capacity", "kind": "scored", "weight": "40"},
]


def cand(i: int, lst: str = "short", s1: str = "80", s2: str = "70", passed: bool = True, **kw):
    return {
        "id": f"c{i}",
        "list": lst,
        "registered": kw.pop("registered", True),
        "rationale": kw.pop("rationale", ""),
        "scores": {
            "exclusion_grounds": {"passed": passed},
            "similar_projects": {"score": s1},
            "technical_capacity": {"score": s2},
        },
    }


def test_scoring_is_decimal_weighted() -> None:
    sc = ev.candidate_score(CRIT, cand(1, s1="85.5", s2="72.25")["scores"])
    # 85.5 * 0.6 + 72.25 * 0.4 = 51.3 + 28.9 = 80.2
    assert sc["total"] == Decimal("80.20")
    assert sc["passed_all"] is True


def test_weights_must_sum_to_100() -> None:
    assert ev.weights_findings(CRIT, "p") == []
    assert codes(ev.weights_findings([*CRIT[:2], {"code": "x", "kind": "scored", "weight": "39.99"}], "p")) == [
        "prequal_weights_not_100"
    ]


def test_shortlist_rules() -> None:
    p = pkg(procedure_code="competitive_negotiated")  # min 3
    two = [cand(1), cand(2)]
    assert "shortlist_below_min_bidders" in codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("60"), two))
    three = [cand(1), cand(2), cand(3), cand(4, "excluded")]
    assert codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("60"), three)) == [
        "excluded_candidate_without_rationale"
    ]
    failing = [cand(1), cand(2), cand(3, passed=False)]
    assert codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("60"), failing)) == [
        "shortlisted_candidate_fails_prequal"
    ]
    low = [cand(1), cand(2), cand(3, s1="10", s2="10")]
    assert codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("60"), low)) == [
        "shortlisted_candidate_fails_prequal"
    ]
    free = [cand(1), cand(2), cand(3, registered=False)]
    assert codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("60"), free)) == ["candidate_not_registered"]


def test_restricted_procedure_needs_its_own_minimum_of_five() -> None:
    p = pkg(procedure_code="restricted")
    four = [cand(i) for i in range(4)]
    assert "shortlist_below_min_bidders" in codes(ev.shortlist_findings(_cat("eu"), p, CRIT, Decimal("0"), four))


def test_evidence_expiring_before_award_warns() -> None:
    ev_rows = [{"ref": "cert:1", "expires": date(2026, 5, 1)}, {"ref": "cert:2", "expires": date(2027, 1, 1)}]
    f = ev.evidence_findings("c1", ev_rows, date(2026, 6, 1))
    assert [(x["code"], x["severity"], x["evidence"]) for x in f] == [
        ("prequal_evidence_expires_before_award", "warning", "cert:1")
    ]


# ── Market sounding (rule 9) ────────────────────────────────────────────


def test_tight_capacity_needs_mitigation_or_resplit() -> None:
    rows = [
        {"id": "a", "capacity_signal": "tight", "mitigation": ""},
        {"id": "b", "capacity_signal": "insufficient", "mitigation": "Split into two lots"},
        {"id": "c", "capacity_signal": "insufficient", "mitigation": "", "resplit": True},
        {"id": "d", "capacity_signal": "ample", "mitigation": ""},
    ]
    assert [f["ref"] for f in ev.capacity_findings(rows)] == ["a"]


# ── Award schedule (rule 11) ────────────────────────────────────────────


def test_backward_pass() -> None:
    p = pkg(procedure_code="open", need_date=date(2027, 6, 30), lead_time_days=60)
    bp = ev.backward_pass(_cat("eu"), p)
    assert bp is not None
    assert bp.award_date == date(2027, 5, 1)
    assert bp.procedure_days == 115
    assert bp.start_date == date(2027, 1, 6)


def test_start_in_the_past_or_before_release_is_infeasible_unless_released_advance() -> None:
    p = pkg(procedure_code="open", need_date=date(2027, 3, 1), lead_time_days=0)
    today = date(2026, 10, 11)
    assert codes(ev.schedule_findings(_cat("eu"), p, today=today, release_date=None)) == []
    late_gate = ev.schedule_findings(_cat("eu"), p, today=today, release_date=date(2026, 12, 1))
    assert [(f["code"], f["severity"], f["reason"]) for f in late_gate] == [
        ("award_schedule_infeasible", "error", "start_before_release_gate")
    ]
    past = ev.schedule_findings(_cat("eu"), p, today=date(2027, 1, 1), release_date=None)
    assert past[0]["reason"] == "start_in_past"
    adv = pkg(
        procedure_code="open",
        need_date=date(2027, 3, 1),
        is_advance=True,
        advance_reason="Long lead",
        advance_released=True,
    )
    assert (
        ev.schedule_findings(_cat("eu"), adv, today=today, release_date=date(2026, 12, 1))[0]["severity"] == "warning"
    )


# ── Frameworks (rule 13) ────────────────────────────────────────────────


def test_framework_call_off_checks() -> None:
    p = pkg("S1", "supply", "100000", procedure_code="framework_call_off", framework_agreement_id="f1")
    fw = {"state": "active", "package_kinds": ["supply"], "end_date": date(2027, 12, 31)}
    assert ev.framework_findings(p, fw, award_date=date(2027, 1, 1), remaining=Decimal("100000")) == []
    assert codes(ev.framework_findings(p, fw, award_date=date(2027, 1, 1), remaining=Decimal("99999.99"))) == [
        "framework_exhausted"
    ]
    assert codes(ev.framework_findings(p, fw, award_date=date(2028, 1, 1), remaining=None)) == ["framework_expired"]
    assert codes(ev.framework_findings(p, {**fw, "package_kinds": ["works"]}, award_date=None, remaining=None)) == [
        "framework_scope_mismatch"
    ]
    assert codes(ev.framework_findings(p, {**fw, "state": "draft"}, award_date=None, remaining=None)) == [
        "framework_not_active"
    ]
