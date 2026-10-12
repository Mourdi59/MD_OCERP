# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The delivery model matches nothing by a literal code: carrier, procurement gate, rule 6, overrides.

Every case shows the input that used to pass or be skipped. Where a governance
catalogue is needed, a small stand-in carries the tags as module 1 will
(``hosts`` on a document type, ``enables`` on a phase); the last test reads
the catalogues module 1 really ships.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.delivery_model import hosting, rules
from app.modules.delivery_model.catalogue import (
    CATALOGUE_DIR,
    DELIVERY_FORMS_KIND,
    DeliveryFormsCatalogue,
    effective_form,
    override_errors,
    register_kinds,
    validate_delivery_forms,
)
from app.modules.delivery_model.errors import DeliveryModelError
from app.modules.delivery_model.schemas import ModelPatch, OfiPatch, OptionPatch, PackagePatch
from app.modules.delivery_model.service import _weight, record_matches_bound_revision, snapshot_hash
from app.modules.project_governance.catalogue_kinds import get_catalogue_kind


@pytest.fixture(scope="module")
def cat() -> DeliveryFormsCatalogue:
    register_kinds()
    return get_catalogue_kind(DELIVERY_FORMS_KIND).get_shipped("neutral")


def _raw() -> dict:
    return json.loads((CATALOGUE_DIR / "neutral.json").read_text(encoding="utf-8"))


# ── carrier and procurement gate come from catalogue tags ──────────────────


@dataclass(frozen=True)
class _Doc:
    code: str
    area: str
    hosts: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Phase:
    code: str
    enables: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Gate:
    code: str
    to_phase: str


@dataclass(frozen=True)
class _Governance:
    document_types: tuple[_Doc, ...] = ()
    phases: tuple[_Phase, ...] = ()
    gates: tuple[_Gate, ...] = field(default=())


def test_the_carrier_is_the_tagged_document_whatever_it_is_called() -> None:
    model = _Governance(
        document_types=(
            _Doc("leistungsverzeichnisse", "vergabe"),
            _Doc("vergabestrategie", "vergabe", hosts=("delivery_model",)),
        )
    )
    assert hosting.carrier_document_types(model) == ("vergabestrategie",)


def test_an_untagged_model_has_no_carrier_and_no_other_document_stands_in() -> None:
    # The old resolver took the first document of the area here (a bill of quantities under one model).
    model = _Governance(document_types=(_Doc("bill_of_quantities", "procurement"), _Doc("x_frame", "procurement")))
    assert hosting.carrier_document_types(model) == ()


def test_a_document_without_the_attribute_is_not_a_carrier() -> None:
    class Bare:
        code = "frame"

    class Model:
        document_types = (Bare(),)

    assert hosting.carrier_document_types(Model()) == ()


def test_the_procurement_gate_is_the_gate_into_the_tagged_phase() -> None:
    model = _Governance(
        phases=(_Phase("design"), _Phase("tender", enables=("procurement",)), _Phase("build")),
        gates=(_Gate("g1", "design"), _Gate("g2", "tender"), _Gate("g3", "build")),
    )
    assert hosting.procurement_gate_codes(model) == ("g2",)
    assert hosting.procurement_gate_codes(_Governance(phases=(_Phase("tender"),), gates=(_Gate("g2", "tender"),))) == ()


def test_the_delivery_catalogue_no_longer_names_governance_codes() -> None:
    raw = _raw()
    assert "governance_areas" not in raw
    assert "procurement_release_gates" not in raw
    with pytest.raises(ValidationError):
        DeliveryFormsCatalogue.model_validate({**raw, "governance_areas": ["contracts"]})


def test_every_shipped_phase_model_names_one_carrier_and_a_procurement_phase() -> None:
    """Module 1 data: without the tags a project on that model can never approve a delivery decision."""
    from app.modules.project_governance.catalogue import list_catalogues

    missing = {
        c.id: (hosting.carrier_document_types(c), hosting.procurement_gate_codes(c))
        for c in list_catalogues()
        if len(hosting.carrier_document_types(c)) != 1 or not hosting.procurement_gate_codes(c)
    }
    assert missing == {}


# ── rule 6 reads attributes, never codes ────────────────────────────────────


def _renamed(cat: DeliveryFormsCatalogue) -> DeliveryFormsCatalogue:
    """The shipped catalogue with the codes rule 6 used to match renamed, as a tenant would."""
    text = json.dumps(cat.model_dump(mode="json"))
    for old, new in (
        ('"design_errors"', '"planungsfehler"'),
        ('"operation_availability"', '"verfuegbarkeit"'),
        ('"contractor"', '"unternehmer"'),
        ('"owner"', '"bauherr"'),
        ('"designer"', '"planer"'),
        ('"operator"', '"betreiber"'),
    ):
        text = text.replace(old, new)
    body = json.loads(text)
    # Renaming the codes also renamed attribute VALUES that happen to spell the same; put those back.
    for form in body["forms"]:
        for key in ("design_responsibility",):
            form[key] = {"unternehmer": "contractor", "bauherr": "owner"}.get(form[key], form[key])
    for party in body["parties"]:
        if party.get("side"):
            party["side"] = {"unternehmer": "contractor", "bauherr": "owner", "betreiber": "operator"}.get(
                party["side"], party["side"]
            )
        party["contract_party_role"] = {"unternehmer": "contractor"}.get(
            party["contract_party_role"], party["contract_party_role"]
        )
    for template in body["package_templates"]:
        for package in template["packages"]:
            package["contracting_party"] = {"bauherr": "owner"}.get(
                package["contracting_party"], package["contracting_party"]
            )
    return DeliveryFormsCatalogue.model_validate(body)


def _row(category: str, party: str) -> dict:
    return {
        "category_code": category,
        "party": party,
        "basis": "contract",
        "shares": None,
        "rationale": "we prefer it",
        "not_applicable": False,
    }


def test_rule6_survives_a_catalogue_that_renames_every_code(cat) -> None:
    renamed = _renamed(cat)
    assert validate_delivery_forms(renamed, "tenant") == []
    found = rules.allocation_findings(renamed, "design_build", [_row("planungsfehler", "bauherr")])
    assert ("allocation_inconsistent_with_form", "contractor_designs") in {
        (f.code, f.params.get("reason")) for f in found if f.ref == "planungsfehler"
    }
    found = rules.allocation_findings(renamed, "ppp_dbfom", [_row("verfuegbarkeit", "bauherr")])
    assert ("allocation_inconsistent_with_form", "operator_carries_availability") in {
        (f.code, f.params.get("reason")) for f in found if f.ref == "verfuegbarkeit"
    }


def test_a_catalogue_that_drops_the_attributes_rule6_reads_does_not_publish() -> None:
    raw = _raw()
    for c in raw["risk_categories"]:
        c.pop("concerns", None)
    errors = validate_delivery_forms(DeliveryFormsCatalogue.model_validate(raw), "shipped")
    assert "risk_concern_missing: design" in errors
    assert "risk_concern_missing: operation" in errors
    raw = _raw()
    for p in raw["parties"]:
        p.pop("side", None)
    errors = validate_delivery_forms(DeliveryFormsCatalogue.model_validate(raw), "shipped")
    assert {"party_side_missing: owner", "party_side_missing: contractor", "party_side_missing: operator"} <= set(
        errors
    )


def test_rule4_a_shared_risk_by_plain_contract_is_refused(cat) -> None:
    row = {**_row("price_escalation", "shared"), "shares": {"owner": "50", "contractor": "50"}}
    codes = {f.code for f in rules.allocation_findings(cat, "design_build", [row]) if f.ref == "price_escalation"}
    assert "shared_needs_basis" in codes
    ok = {**row, "basis": "shared_pain_gain"}
    codes = {f.code for f in rules.allocation_findings(cat, "design_build", [ok]) if f.ref == "price_escalation"}
    assert "shared_needs_basis" not in codes
    raw = _raw()
    shared = next(a for a in raw["default_allocations"] if a["party"] == "shared")
    shared["basis"] = "contract"
    errors = validate_delivery_forms(DeliveryFormsCatalogue.model_validate(raw), "shipped")
    assert any(e.startswith("allocation_shared_needs_basis") for e in errors)


# ── option overrides are validated and reach the rules ──────────────────────


def test_overrides_are_validated_against_the_form_attributes(cat) -> None:
    form = cat.form("design_build")
    assert override_errors(form, {}) == []
    assert override_errors(form, {"design_responsibility": "owner"}) == []
    assert override_errors(form, {"code": "other"}) == ["override_not_allowed: code"]
    assert override_errors(form, {"design_responsibility": "nobody"}) == ["override_invalid: design_responsibility"]
    assert override_errors(form, {"allowed_price_bases": ["barter"], "price_basis_at_award": "barter"}) != []
    assert override_errors(form, {"design_responsibility": "split_at_stage"}) == [
        "override_invalid: design_transfer_stage"
    ]


def test_an_override_changes_what_rule6_and_rule7_say(cat) -> None:
    bare = cat.form("design_build")
    customised = effective_form(bare, {"design_responsibility": "owner"})
    assert customised is not None and customised.design_responsibility == "owner"
    assert effective_form(bare, {}) is bare
    row = [_row("design_errors", "owner")]
    plain = rules.allocation_findings(cat, "design_build", row)
    assert "allocation_inconsistent_with_form" in {f.code for f in plain if f.ref == "design_errors"}
    with_override = rules.allocation_findings(cat, "design_build", row, form=customised)
    assert "allocation_inconsistent_with_form" not in {f.code for f in with_override if f.ref == "design_errors"}
    package = {"id": "1", "code": "DB", "kind": "design_and_construction", "designs": True, "builds": True}
    assert "owner_designs_no_design_and_build" in {
        f.params.get("reason") for f in rules.package_findings(customised, [package])
    }
    assert "owner_designs_no_design_and_build" not in {
        f.params.get("reason") for f in rules.package_findings(bare, [package])
    }


# ── packages: parent cycles ─────────────────────────────────────────────────


def test_a_parent_cycle_is_found_at_any_length() -> None:
    assert rules.parent_cycle("a", {"a": "b", "b": "a"}) is True
    assert rules.parent_cycle("a", {"a": "b", "b": "c", "c": "a"}) is True
    assert rules.parent_cycle("a", {"a": "b", "b": None}) is False
    # A cycle that does not pass through the start must end the walk, not hang it.
    assert rules.parent_cycle("a", {"a": "b", "b": "c", "c": "b"}) is False


def test_rule7_reports_packages_that_parent_each_other(cat) -> None:
    packages = [
        {"id": "1", "code": "A", "kind": "construction", "builds": True, "parent_id": "2"},
        {"id": "2", "code": "B", "kind": "construction", "builds": True, "parent_id": "1"},
    ]
    reasons = {
        (f.ref, f.params.get("reason")) for f in rules.package_findings(cat.form("design_bid_build_split"), packages)
    }
    assert {("A", "parent_cycle"), ("B", "parent_cycle")} <= reasons


# ── numbers and nulls ───────────────────────────────────────────────────────


def test_a_weight_with_more_decimals_than_the_column_keeps_is_refused() -> None:
    assert _weight("33.3333") == Decimal("33.3333")
    assert _weight("12.5") == Decimal("12.5")
    with pytest.raises(DeliveryModelError) as exc:
        _weight("33.33333")
    assert exc.value.code == "weight_invalid" and exc.value.status_code == 422
    for bad in ("-1", "100.0001", "abc", "NaN"):
        with pytest.raises(DeliveryModelError):
            _weight(bad)


def test_the_snapshot_hash_ignores_key_order_and_sees_content() -> None:
    a = snapshot_hash({"form": {"code": "x"}, "packages": [1, 2]})
    assert a == snapshot_hash({"packages": [1, 2], "form": {"code": "x"}})
    assert a != snapshot_hash({"form": {"code": "x"}, "packages": [2, 1]})
    assert len(a) == 64


@pytest.mark.parametrize(
    ("schema", "body"),
    [
        (PackagePatch, {"title": None}),
        (PackagePatch, {"kind": None}),
        (PackagePatch, {"party": None}),
        (PackagePatch, {"sort_order": None}),
        (OfiPatch, {"description": None}),
        (OfiPatch, {"install_by": None}),
        (OptionPatch, {"notes": None}),
        (OptionPatch, {"overrides": None}),
        (ModelPatch, {"underground_risk_sharing": None}),
    ],
)
def test_an_explicit_null_on_a_field_that_cannot_be_cleared_is_refused(schema, body) -> None:
    with pytest.raises(ValidationError):
        schema.model_validate(body)


@pytest.mark.parametrize(
    ("schema", "field_name"),
    [
        (PackagePatch, "parent_id"),
        (PackagePatch, "price_basis"),
        (PackagePatch, "need_date"),
        (OfiPatch, "package_id"),
        (OfiPatch, "need_by_date"),
        (OfiPatch, "schedule_activity_id"),
        (OfiPatch, "lead_time_days"),
    ],
)
def test_an_explicit_null_on_a_nullable_field_reaches_the_service(schema, field_name) -> None:
    # The service used to skip every None, so a package could never be detached from its parent.
    assert schema.model_validate({field_name: None}).model_dump(exclude_unset=True) == {field_name: None}
    assert schema.model_validate({}).model_dump(exclude_unset=True) == {}


# ── exports ─────────────────────────────────────────────────────────────────


def _comparison() -> dict:
    return {
        "options": [
            {"id": "o1", "form_code": "design_build", "form": {"name_key": None}, "weighted_total": "3.53"},
            {"id": "o2", "form_code": "cm_at_risk", "form": {"name_key": None}, "weighted_total": None},
        ],
        "criteria": [
            {"code": "cost", "weight": "12.5000", "name_key": None},
            {"code": "time", "weight": "87.5000", "name_key": None},
        ],
        "scores": [{"option_id": "o1", "criterion_code": "cost", "score": 4}],
        "weights_total": "100.0000",
    }


def test_the_decision_export_prints_weights_as_numbers_a_person_wrote() -> None:
    from app.modules.delivery_model import export as ex

    decision = {
        "form_code": "design_build",
        "status": "rejected",
        "rationale": "One point of responsibility.",
        "snapshot": {},
        "proposed_at": "2026-10-01T10:00:00+00:00",
        "approved_at": None,
    }
    doc = ex.decision_document(_comparison(), decision, project_name="Demo", locale="en")
    assert [row[1] for row in doc.rows] == ["12.5", "87.5", "100"]
    for fmt in ("pdf", "xlsx"):
        assert len(ex.render(doc, fmt)) > 500
    assert len(ex.render(ex.decision_document(_comparison(), None, project_name="Demo", locale="de"), "pdf")) > 500


def test_the_package_plan_export_renders_in_both_formats() -> None:
    from app.modules.delivery_model import export as ex

    packages = [
        {
            "id": "1",
            "code": "DB-01",
            "title": "Design and construction",
            "kind": "design_and_construction",
            "designs": True,
            "builds": True,
            "supplies": False,
            "manages": False,
            "party": "contractor",
            "contracting_party": "owner",
            "price_basis": "lump_sum",
            "standard_form": "",
            "parent_id": None,
            "need_date": "2027-03-01",
            "status": "planned",
            "effective_status": "awarded",
            "link": {"kind": "contract", "id": "c1", "status": "active", "missing": False},
        }
    ]
    doc = ex.packages_document(packages, project_name="Demo", locale="en")
    assert len(doc.rows) == 1
    for fmt in ("pdf", "xlsx"):
        assert len(ex.render(doc, fmt)) > 500


async def test_the_subscribers_are_wired_to_the_bus_once_and_reach_the_handlers(monkeypatch) -> None:
    from app.core.events import EventBus
    from app.modules.delivery_model import events

    bus = EventBus()
    seen: list[tuple[str, dict]] = []

    async def frame(data: dict, **kw) -> bool:
        seen.append(("frame", data))
        return True

    async def risk(data: dict, **kw) -> int:
        seen.append(("risk", data))
        return 1

    monkeypatch.setattr(events, "event_bus", bus)
    monkeypatch.setattr(events, "handle_frame_document", frame)
    monkeypatch.setattr(events, "handle_risk_deleted", risk)
    events.register_delivery_model_subscribers()
    events.register_delivery_model_subscribers()
    await bus.publish("project_governance.frame_document.state_changed", {"document_id": "d", "status": "binding"})
    await bus.publish("risk.risk.deleted", {"risk_id": "r"})
    assert seen == [("frame", {"document_id": "d", "status": "binding"}), ("risk", {"risk_id": "r"})]


async def test_without_an_isolated_postgres_session_the_handlers_stand_down(monkeypatch) -> None:
    """On SQLite a second writer would deadlock the request; the catch-up on read covers it instead."""
    import uuid as _uuid

    from app.modules.delivery_model import events

    async def no() -> bool:
        return False

    def never():
        raise AssertionError("a session was opened")

    monkeypatch.setattr(events, "_can_open_isolated_session", no)
    monkeypatch.setattr(events, "async_session_factory", never)
    ids = {"project_id": str(_uuid.uuid4()), "document_id": str(_uuid.uuid4())}
    assert await events.handle_frame_document({**ids, "status": "binding"}) is False
    assert await events.handle_frame_document({**ids, "status": "approved"}, session_factory=never) is False
    assert await events.handle_risk_deleted({**ids, "risk_id": "r"}) == 0


def test_the_record_is_compared_with_the_bound_revision_only_when_both_hashes_exist() -> None:
    record = snapshot_hash({"form": {"code": "design_build"}})
    assert record_matches_bound_revision(record, record) is True
    assert record_matches_bound_revision(record, "0" * 64) is False
    assert record_matches_bound_revision(record, None) is None
    assert record_matches_bound_revision(None, record) is None
    assert record_matches_bound_revision("", "") is None
