"""What a caller may do, answered by the function that refuses the request.

The ``can`` flags of the API and the refusals of the service read the same
functions in ``capabilities``. These tests pin the answers and pin that the
service does not carry a second copy of a rule.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.quality_concept import capabilities as caps
from app.modules.quality_concept import schemas, seed, vocab

MODULE = Path(caps.__file__).parent
ALICE, BOB = uuid.uuid4(), uuid.uuid4()
EDITOR = caps.Caller(ALICE, edit=True)
MANAGER = caps.Caller(BOB, edit=True, manage=True, waive=True)
VIEWER = caps.Caller(uuid.uuid4())


def _proof(caller: caps.Caller, **facts) -> dict:
    base = {
        "concept_state": "draft",
        "decision": "none",
        "requested_by": None,
        "rationale": "",
        "delivery_state": "open",
        "evidence_authors": [],
        "four_eyes": True,
    }
    return caps.proof(caller, **{**base, **facts})


def test_a_waiver_is_decided_by_a_second_person_who_holds_the_permission() -> None:
    pending = {"requested_by": ALICE, "rationale": "Supplier tested"}
    # Nothing was asked for: neither approve nor reject is offered.
    assert _proof(MANAGER)["can_reason"]["decide_waiver"] == "waiver_not_requested"
    # The editor asked; the editor holds no waive permission.
    assert _proof(EDITOR, **pending)["can_reason"]["decide_waiver"] == "waive_required"
    assert _proof(MANAGER, **pending)["can"]["decide_waiver"] is True
    # Four eyes: the manager who asked cannot decide; without four eyes they can.
    own = {"requested_by": BOB, "rationale": "Not issued"}
    assert _proof(MANAGER, **own)["can_reason"]["decide_waiver"] == "approver_is_requester"
    assert _proof(MANAGER, **own, four_eyes=False)["can"]["decide_waiver"] is True
    # A decided proof has no request pending.
    assert _proof(MANAGER, **pending, decision="waived")["can_reason"]["decide_waiver"] == "invalid_transition"
    assert caps.waiver_decision_refusal("none", ALICE, "   ", BOB, True) == "waiver_not_requested"


def test_proof_flags_say_why_not_and_carry_no_reason_when_allowed() -> None:
    out = _proof(EDITOR)
    assert set(out) == {"can", "can_reason"}
    assert out["can"]["request_waiver"] is True and "request_waiver" not in out["can_reason"]
    assert out["can_reason"]["edit"] == "manage_required"
    assert out["can_reason"]["accept"] == "proof_not_delivered"
    assert out["can_reason"]["reopen"] == "invalid_transition"
    delivered = _proof(EDITOR, delivery_state="delivered", evidence_authors=[BOB])
    assert delivered["can"]["accept"] is True
    # Whoever attached the evidence does not also accept it.
    assert _proof(EDITOR, delivery_state="delivered", evidence_authors=[ALICE])["can_reason"]["accept"] == (
        "approver_added_evidence"
    )
    assert _proof(EDITOR, decision="accepted")["can"]["reopen"] is True
    assert set(_proof(VIEWER)["can"].values()) == {False}
    # The plan of a bound concept changes only through a change request.
    assert _proof(MANAGER, concept_state="binding")["can_reason"]["edit"] == "binding_requires_change_request"
    assert _proof(MANAGER, concept_state="in_review")["can_reason"]["delete"] == "concept_not_editable"
    assert _proof(MANAGER)["can"]["edit"] is True


def test_stage_flags_follow_the_state_machine_and_the_hold_gate() -> None:
    def flags(state: str, computed: str | None = None, gate: str | None = None, caller=EDITOR) -> dict:
        return caps.stage_progress(caller, state=state, computed_state=computed or state, gate_status=gate)

    # A blocked row whose preconditions are now met opens: opening a test refreshes the state first.
    assert flags("blocked", "ready")["can"]["open_test"] is True
    assert flags("blocked")["can_reason"]["open_test"] == "invalid_transition"
    assert flags("in_test")["can"]["record_pass"] is True and flags("in_test")["can"]["record_fail"] is True
    assert flags("ready")["can_reason"]["request_release"] == "stage_not_passed"
    assert flags("passed")["can"]["request_release"] is True
    assert flags("passed", gate="pending")["can_reason"]["request_release"] == "release_already_requested"
    assert flags("stale", gate="released")["can"]["request_release"] is True
    # Release itself is never offered here: the hold gate decides it in construction control.
    assert "release" not in flags("passed")["can"]
    assert flags("ready")["can_reason"]["not_applicable"] == "manage_required"
    assert flags("ready", caller=MANAGER)["can"]["not_applicable"] is True
    assert flags("not_applicable", caller=MANAGER)["can"]["reinstate"] is True
    assert flags("released", caller=MANAGER)["can_reason"]["reinstate"] == "invalid_transition"


def test_acceptance_flags_know_preconditions_dates_and_the_deemed_date() -> None:
    def flags(state: str, caller=MANAGER, **facts) -> dict:
        base = {"concept_state": "binding", "has_regime": True, "blocked": False, "deemed_due": False}
        return caps.acceptance_unit(caller, state=state, **{**base, **facts})

    assert flags("planned")["can"]["request"] is True
    assert flags("planned", blocked=True)["can_reason"]["request"] == "acceptance_preconditions_unmet"
    assert flags("planned", has_regime=False)["can_reason"]["request"] == "acceptance_regime_missing"
    assert flags("requested")["can_reason"]["request"] == "invalid_transition"
    assert flags("requested")["can_reason"]["confirm_deemed"] == "deemed_acceptance_not_due"
    assert flags("requested", deemed_due=True)["can"]["confirm_deemed"] is True
    assert flags("requested", EDITOR, deemed_due=True)["can_reason"]["confirm_deemed"] == "manage_required"
    assert flags("accepted")["can_reason"]["record_dates"] == "unit_dates_locked"
    assert flags("requested", EDITOR)["can"]["record_dates"] is True
    assert flags("requested")["can_reason"]["confirm_effect"] == "unit_not_accepted"
    assert flags("deemed_accepted")["can"]["confirm_effect"] is True
    # Accepting is the handover act's matter, never a button of this module.
    assert "accept" not in flags("requested")["can"]
    # The unit is part of the bound plan, but the act is linked afterwards.
    assert flags("planned")["can_reason"]["edit"] == "binding_requires_change_request"
    assert flags("planned")["can"]["link_handover"] is True


def test_survey_certification_and_credit_flags() -> None:
    planned = caps.survey(EDITOR, state="planned", phase="before", access_refused=False)
    assert planned["can"]["invite"] and planned["can"]["record_survey"] and planned["can"]["delete"]
    assert planned["can_reason"]["pair"] == "only_after_surveys_pair"
    assert planned["can_reason"]["close"] == "invalid_transition"
    done = caps.survey(EDITOR, state="surveyed", phase="after", access_refused=False)
    assert done["can"]["pair"] is True and done["can_reason"]["delete"] == "survey_recorded"
    assert caps.survey_action_refusal("planned", "refuse_access", True) == "refusal_is_final"
    assert set(caps.survey(VIEWER, state="planned", phase="after", access_refused=False)["can"].values()) == {False}

    cert = caps.certification(MANAGER, state="planned")
    assert cert["can"]["register"] is True and cert["can_reason"]["certify"] == "invalid_transition"
    assert caps.certification(EDITOR, state="planned")["can_reason"]["register"] == "manage_required"
    credit = caps.credit(EDITOR, state="targeted")
    assert credit["can"]["submit_evidence"] is True and credit["can_reason"]["achieve"] == "invalid_transition"
    assert credit["can_reason"]["delete"] == "manage_required"


def test_every_reason_has_a_message_in_both_languages_and_a_status() -> None:
    reasons: set[str] = set(caps._STATUS)
    for caller in (VIEWER, EDITOR, MANAGER):
        for state in (None, "draft", "in_review", "binding"):
            reasons |= set(_proof(caller, concept_state=state)["can_reason"].values())
            reasons |= set(caps.plan_row(caller, state)["can_reason"].values())
        for state in ("blocked", "passed", "released"):
            reasons |= set(
                caps.stage_progress(caller, state=state, computed_state=state, gate_status="pending")[
                    "can_reason"
                ].values()
            )
        for state in ("planned", "accepted"):
            reasons |= set(
                caps.acceptance_unit(
                    caller, concept_state="draft", state=state, has_regime=False, blocked=True, deemed_due=False
                )["can_reason"].values()
            )
            reasons |= set(caps.survey(caller, state=state, phase="before", access_refused=True)["can_reason"].values())
        reasons |= set(caps.certification(caller, state="certified")["can_reason"].values())
        reasons |= set(caps.credit(caller, state="achieved")["can_reason"].values())
    for locale in ("en", "de"):
        messages = json.loads((MODULE / "messages" / f"{locale}.json").read_text(encoding="utf-8"))
        missing = sorted(r for r in reasons if f"quality_concept.errors.{r}" not in messages)
        assert missing == [], (locale, missing)
    assert caps.status_of("approver_is_requester") == 403
    assert caps.status_of("waiver_not_requested") == 422
    assert caps.status_of("release_already_requested") == 409


@pytest.mark.parametrize(
    "code",
    [
        "approver_is_requester",
        "approver_added_evidence",
        "waiver_not_requested",
        "stage_not_passed",
        "release_already_requested",
        "unit_dates_locked",
        "unit_not_accepted",
        "survey_recorded",
        "only_after_surveys_pair",
        "refusal_is_final",
        "binding_requires_change_request",
        "concept_not_editable",
    ],
)
def test_the_service_keeps_no_second_copy_of_a_rule(code: str) -> None:
    """A rule written twice drifts: the flag would say yes where the request says no."""
    service = (MODULE / "service.py").read_text(encoding="utf-8")
    assert f'"{code}"' not in service, code


def test_expert_report_trigger_and_frequency_are_vocabulary() -> None:
    ok = schemas.ExpertReportIn(subject="Fire inspection", trigger="before_concealment", frequency="per_floor")
    assert (ok.trigger, ok.frequency) == ("before_concealment", "per_floor")
    # Not stated is allowed; free text is not.
    assert schemas.ExpertReportIn(subject="x").trigger == ""
    with pytest.raises(ValidationError):
        schemas.ExpertReportIn(subject="x", trigger="Before the ceilings are closed")
    with pytest.raises(ValidationError):
        schemas.ExpertReportIn(subject="x", frequency="per floor")
    with pytest.raises(ValidationError):
        schemas.ExpertReportPatch(frequency="every now and then")
    assert schemas.ExpertReportPatch(trigger="on_defect").trigger == "on_defect"
    for _subject, trigger, frequency, _offsets, _state in seed._EXPERT_REPORTS:
        assert trigger in vocab.EXPERT_REPORT_TRIGGERS
        assert frequency in vocab.EXPERT_REPORT_FREQUENCIES


def test_a_pack_catalogue_can_be_named_in_a_pin() -> None:
    fields = schemas.CataloguePin.model_fields["catalogue_source"]
    assert set(fields.annotation.__args__) == {"shipped", "tenant", "pack"}
