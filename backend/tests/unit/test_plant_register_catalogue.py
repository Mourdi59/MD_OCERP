# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``plant_register``, the message bundle and the one-list grep tests (rules 1, 12, 20)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.modules.plant_register.catalogue import (
    CATALOGUE_DIR,
    PLANT_KIND,
    PlantCatalogue,
    register_plant_kind,
    validate_plant_catalogue,
)

MODULES = Path(__file__).resolve().parents[2] / "app" / "modules"
SPEC_CLASSES = {
    "power_transformer", "distribution_transformer", "mv_switchgear", "lv_switchboard", "generator", "ups",
    "battery_storage", "chiller", "cooling_tower", "boiler", "heat_pump", "ahu", "lift", "escalator",
    "sprinkler_pump", "bms_controls", "facade_unit", "structural_steel_package", "process_unit",
    "crane_permanent", "kitchen_equipment", "medical_equipment", "it_core_network",
}  # fmt: skip


def _raw() -> dict:
    return json.loads((CATALOGUE_DIR / "neutral.json").read_text(encoding="utf-8"))


def test_shipped_catalogue_loads_through_the_governance_registry() -> None:
    from app.modules.project_governance.catalogue_kinds import catalogue_kinds, get_catalogue_kind

    register_plant_kind()
    assert PLANT_KIND in catalogue_kinds()
    cat = get_catalogue_kind(PLANT_KIND).get_shipped("neutral")
    assert isinstance(cat, PlantCatalogue)
    assert {c.code for c in cat.component_classes} == SPEC_CLASSES
    assert cat.step_codes()[0] == "supply" and cat.step_codes()[-1] == "document"


def test_every_shipped_lead_time_is_unconfirmed_with_an_as_of_date() -> None:
    for c in _raw()["component_classes"]:
        lw = c["typical_lead_weeks"]
        assert lw["review_status"] == "unconfirmed", c["code"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", lw["as_of"]), c["code"]


def test_a_verified_lead_time_in_a_shipped_file_is_rejected() -> None:
    body = _raw()
    body["component_classes"][0]["typical_lead_weeks"]["review_status"] = "verified"
    errors = validate_plant_catalogue(PlantCatalogue.model_validate(body), "shipped")
    assert any("shipped lead time must be unconfirmed" in e for e in errors)


def test_verified_without_source_url_is_rejected_and_routes_carry_sources() -> None:
    body = _raw()
    for r in body["procurement_routes"]:
        if r["review_status"] == "verified":
            assert r["source_url"].startswith("https://"), r["code"]
    body["procurement_routes"][0]["source_url"] = None
    errors = validate_plant_catalogue(PlantCatalogue.model_validate(body), "shipped")
    assert any("verified without source_url" in e for e in errors)


def test_every_owner_furnished_route_has_a_country_alias() -> None:
    body = _raw()
    for r in body["procurement_routes"]:
        if r["code"].startswith("owner_furnished"):
            assert r["aliases"], r["code"]


def test_duplicate_codes_and_inverted_ranges_are_rejected() -> None:
    body = _raw()
    body["component_classes"].append(dict(body["component_classes"][0]))
    body["component_classes"][1]["typical_lead_weeks"] = {
        **body["component_classes"][1]["typical_lead_weeks"],
        "min": 99,
        "max": 3,
    }
    errors = validate_plant_catalogue(PlantCatalogue.model_validate(body), "shipped")
    assert any("duplicate code power_transformer" in e for e in errors)
    assert any("min > max" in e for e in errors)


def test_expert_estimate_is_not_market_evidence() -> None:
    sources = {s["code"]: s for s in _raw()["lead_time_sources"]}
    assert sources["expert_estimate"]["market_evidence"] is False
    assert all(s["market_evidence"] for k, s in sources.items() if k != "expert_estimate")
    assert sources["supplier_quote"]["evidence_rank"] == 1


@pytest.mark.parametrize("locale", ["en", "de"])
def test_every_catalogue_label_and_error_code_has_a_message(locale: str) -> None:
    from app.modules.plant_register.messages import is_key_present

    keys = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("name_key", "description_key") and v:
                    keys.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(_raw())
    src = "\n".join(p.read_text(encoding="utf-8") for p in (MODULES / "plant_register").glob("*.py"))
    codes = set(re.findall(r'(?:PlantError|conflict|forbidden|not_found)\(\s*"([a-z_]+)"', src))
    codes |= set(re.findall(r'(?:blocked\(\[|out\.append\(|errors\.append\()\s*"([a-z_]+)"', src))
    codes |= {"lead_time_without_enquiry_date", "enquiry_date_in_future", "response_before_enquiry"}
    codes |= {"route_inconsistent_with_package_plan", "decision_paper_needs_two_options", "transition_blocked"}
    keys += [f"plant.errors.{c}" for c in codes]
    missing = [k for k in keys if not is_key_present(k, locale=locale)]
    assert not missing, missing


def _model_columns(pattern: str) -> list[str]:
    hits = []
    rx = re.compile(rf"^\s+({pattern})\s*:\s*Mapped", re.MULTILINE)
    for path in MODULES.glob("*/models.py"):
        for m in rx.finditer(path.read_text(encoding="utf-8")):
            hits.append(f"{path.parent.name}.{m.group(1)}")
    return sorted(hits)


def test_rule_1_no_new_module_adds_a_long_lead_column() -> None:
    """The plant register is the only long-lead list; submittals keep theirs for contractor items."""
    assert _model_columns(r"long_lead\w*") == [
        "plant_register.long_lead_override",
        "plant_register.long_lead_override_reason",
        "submittals.long_lead",
    ]


def test_rule_12_no_module_keeps_its_own_lead_time_copy() -> None:
    """``commitment_lead_time_duplicated``: lead time lives on the quote; others read it through ``reads``."""
    allowed = {
        "procurement.lead_time_days",  # requisition call-off at execution time
        "supplier_catalogs.lead_time_days",  # catalogue entry, a quote source of rank supplier_catalogue
        "submittals.lead_time_weeks",  # contractor submittals, read-only when linked to a plant item
        "property_dev.lead_time_days",  # sales lead-to-contract time, not procurement
    }
    assert set(_model_columns(r"lead_time\w*|enquiry_date")) - allowed == {"plant_register.enquiry_date"}
