# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The shipped Regensburg story files resolve through the same pure merge functions as the module override tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.modules.commitment_release import seed as commitment_seed
from app.modules.delivery_model import seed as delivery_seed
from app.modules.design_management import seed as design_seed
from app.modules.permits import seed as permits_seed
from app.modules.plant_register import seed as plant_seed
from app.modules.plant_register.catalogue import shipped_default
from app.modules.procurement_concept import seed as procurement_seed
from app.modules.quality_concept import seed as quality_seed
from app.modules.site_logistics import demo as site_demo
from app.modules.site_logistics import demo_plan
from app.modules.staffing import seed as staffing_seed
from app.modules.stakeholders import seed as stakeholder_seed
from app.modules.transmittals import seed as transmittal_seed

_ROOT = Path(__file__).resolve().parents[3]
_DEMO = _ROOT / "packs/eleven-areas-framework/src/openconstructionerp_eleven_areas_framework/demo"
_MODULES = (
    "stakeholders",
    "staffing",
    "permits",
    "plant_register",
    "delivery_model",
    "procurement_concept",
    "quality_concept",
    "design_management",
    "commitment_release",
    "site_logistics",
    "transmittals",
)
_CATALOGUES = [
    _ROOT / "backend/app/modules/permits/catalogues/permit_type/de.json",
    _ROOT / "backend/app/modules/permits/catalogues/permit_type/de_by.json",
    _ROOT
    / "packs/eleven-areas-framework/src/openconstructionerp_eleven_areas_framework/catalogues/permit_type"
    / "eleven_areas_framework_de_by.json",
]
# Free-text keys whose plain strings are data (codes, references, numbers), not screen text.
_DATA_KEYS = {
    "code",
    "kind",
    "class",
    "key",
    "unit",
    "reach",
    "slot",
    "role",
    "from",
    "to",
    "phase",
    "status",
    "method",
    "topic",
    "ref",
    "body",
    "mode",
    "flow_code",
    "storage_area",
    "package",
    "packages",
    "discipline",
    "family",
    "mandate",
    "trigger",
    "frequency",
    "state",
    "regime",
    "regime_before_construction",
    "client_type",
    "purpose_code",
    "plant_item",
    "item_kind",
    "public_procedure",
    "private_procedure",
    "category",
    "open",
    "close",
    "delivery_open",
    "delivery_close",
    "noise_zone_type",
    "price_signal",
    "capacity_signal",
    "source",
    "quantity",
    "redundancy",
    "weight",
    "scores",
    "recommendation",
    "author",
    "$note",
    "x",
    "y",
    "reach_m",
    "max_load_t",
    "value",
    "amount",
    "salvage_value",
    "reservation_fee",
    "first_amount",
    "second_amount",
    "loss_estimate",
    "supplier_name_code",
    "triggers",
    "methods",
    "forms",
    "risks",
    "free_names",
    "vehicles",
    "filled",
    "package_kinds",
    "funding_source",
    "company_name",
    "address_code",
    "reference",
    "preliminary_reference",
    "building_reference",
    "early_reference",
    "source_procedure_ref_code",
}


def _load(module: str) -> dict[str, Any]:
    return json.loads((_DEMO / f"residential-regensburg-{module}.json").read_text(encoding="utf-8"))


def _walk(node: Any, path: tuple[str, ...] = ()):
    """Yield every language map as ``(path, map)``."""
    if isinstance(node, dict):
        if set(node) == {"en", "de"}:
            yield path, node
            return
        for key, value in node.items():
            yield from _walk(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, (*path, str(index)))


def _texts(node: Any, path: tuple[str, ...] = ()):
    """Yield every plain string leaf as ``(path, string)``; a language map is not descended into."""
    if isinstance(node, dict):
        if set(node) == {"en", "de"}:
            return
        for key, value in node.items():
            yield from _texts(value, (*path, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _texts(value, (*path, str(index)))
    elif isinstance(node, str):
        yield path, node


def test_every_module_has_a_file_registered_in_the_demo_project() -> None:
    demo = json.loads((_DEMO / "demo_project.json").read_text(encoding="utf-8"))
    entry = next(p for p in demo["projects"] if p["project"]["demo_template_id"] == "residential-regensburg")
    assert set(entry["module_files"]) == set(_MODULES)
    for module, relative in entry["module_files"].items():
        assert relative == f"demo/residential-regensburg-{module}.json"
        assert (_DEMO.parent / relative).is_file()


@pytest.mark.parametrize("module", _MODULES)
def test_files_are_clean_and_every_language_map_is_complete(module: str) -> None:
    raw = (_DEMO / f"residential-regensburg-{module}.json").read_text(encoding="utf-8")
    assert "–" not in raw and "—" not in raw
    assert not re.search(r"\bAI\b|Claude", raw)
    maps = list(_walk(_load(module)))
    assert maps, "the file carries no German text"
    for path, value in maps:
        assert value["en"].strip() and value["de"].strip(), path
    # No plain English string stays on a screen: a plain string is a code, a reference or a data value.
    for path, text in _texts(_load(module)):
        if path[-1] in _DATA_KEYS or path[0] == "$note" or len(text) < 25:
            continue
        pytest.fail(f"{module}: plain text {'/'.join(path)!r} has no German")


def test_stakeholders() -> None:
    story = _load("stakeholders")
    for locale in ("en", "de"):
        merged = stakeholder_seed.merge_register(stakeholder_seed._STAKEHOLDERS, story, locale)
        assert [r[0] for r in merged] == [r[0] for r in stakeholder_seed._STAKEHOLDERS]
        assert all(m[1] != d[1] for m, d in zip(merged, stakeholder_seed._STAKEHOLDERS, strict=True))
        assert all(m[2:4] == d[2:4] for m, d in zip(merged, stakeholder_seed._STAKEHOLDERS, strict=True))
        commitments = stakeholder_seed.merge_commitments(story, locale)
        assert len(commitments) == len(stakeholder_seed._COMMITMENTS)
        assert all(c[0] != d[0] for c, d in zip(commitments, stakeholder_seed._COMMITMENTS, strict=True))
        # The beat stays in code: the third commitment fell due three days ago.
        assert commitments[2][3] == stakeholder_seed._COMMITMENTS[2][3] == -3
        for section, defaults in stakeholder_seed._TEXT_DEFAULTS.items():
            got = stakeholder_seed.merge_texts(story, section, locale)
            assert set(story[section]) <= set(got)
            if locale == "de":
                assert all(got[k] != v for k, v in defaults.items() if k in story[section])
    de = stakeholder_seed.merge_register(stakeholder_seed._STAKEHOLDERS, story, "de")
    en = stakeholder_seed.merge_register(stakeholder_seed._STAKEHOLDERS, story, "en")
    assert de[1][1] != en[1][1]


def test_staffing() -> None:
    story = _load("staffing")
    cat = json.loads((Path(staffing_seed.__file__).parent / "catalogues" / "de.json").read_text(encoding="utf-8"))
    roles = {r["code"] for r in cat["roles"]}
    kinds = {k["code"] for k in cat["document_kinds"]}
    rows = staffing_seed.story_positions(story, ())
    assert len(rows) == len(story["positions"])
    assert {r[0] for r in rows} <= roles
    assert set(story["filled"]) <= {r[0] for r in rows}
    for key in ("expiring", "missing", "waived"):
        pairs = staffing_seed.story_pairs(story, key)
        assert len(pairs) == len(story[key])
        assert {r for r, _, _ in pairs} <= {r[0] for r in rows}
        assert {k for _, k, _ in pairs} <= kinds
    handovers = staffing_seed.story_handovers(story, "de", ())
    assert len(handovers) == len(story["handovers"])
    assert handovers != staffing_seed.story_handovers(story, "en", ())
    assert {h[0] for h in handovers} <= set(story["filled"])


def test_permits() -> None:
    story = _load("permits")
    types: dict[str, SimpleNamespace] = {}
    for path in _CATALOGUES:
        for t in json.loads(path.read_text(encoding="utf-8"))["permit_types"]:
            types[t["code"]] = SimpleNamespace(
                code=t["code"],
                scope=t["scope"],
                category=t["category"],
                triggered_by_route=t.get("triggered_by_route", []),
                requires=[SimpleNamespace(code=r if isinstance(r, str) else r["code"]) for r in t.get("requires", [])],
            )
    out = permits_seed.resolve_permit_content(story, "en")
    de = permits_seed.resolve_permit_content(story, "de")
    assert set(out["codes"]) == set(permits_seed._CODE_KEYS)
    assert all(code in types for code in out["codes"].values())
    assert types[out["codes"]["preliminary"]].scope == "preliminary"
    building = types[out["codes"]["building"]]
    assert building.scope == "full" and "full_permit" in building.triggered_by_route
    early = types[out["codes"]["early_start"]]
    assert early.scope == "early_start" and building.code in {r.code for r in early.requires}
    assert types[out["codes"]["road"]].category == "traffic_road"
    assert types[out["codes"]["occupancy"]].category == "occupancy"
    for key, default in permits_seed._TEXT_DEFAULTS.items():
        assert key in story and out[key] != default
    assert set(out["conditions"]) == {"1", "2", "3", "4", "5"}
    assert set(out["early_conditions"]) == {"1", "2"}
    assert out["conditions"]["3"]["topic"] == "ecology" and out["conditions"]["4"]["topic"] == "fire"
    assert de["building_title"] != out["building_title"]
    assert de["conditions"]["1"]["text"] != out["conditions"]["1"]["text"]


def test_plant_register() -> None:
    story = _load("plant_register")
    codes = plant_seed._catalogue_codes()
    for locale in ("en", "de"):
        out = plant_seed.resolve_story(story, codes, locale)
        for key in ("items", "limits", "paper", "slots", "it_services", "site_plant"):
            assert key in out, f"{key} of the shipped story is malformed or missing"
    out = plant_seed.resolve_story(story, codes)
    items = {i["code"]: i for i in out["items"]}
    assert len(items) == len(story["items"])
    assert items["PL-001"]["class"] == "power_transformer" and items["PL-001"].get("slot") == "held"
    assert items["PL-002"].get("paper")
    assert {i.get("slot") for i in items.values()} >= {"held", "requested"}
    assert "cancelled" in {i["reach"] for i in items.values()}
    assert sum(1 for i in out["items"] if i.get("paper")) == 1
    paper = out["paper"]
    assert max(o["lead_weeks"] for o in paper["options"]) >= max(q[5] for q in items["PL-002"]["quotes"])
    assert out["slots"]["held"]["convert_by_days"] == 45
    catalogue = shipped_default()
    assert all(catalogue.component_class(i["class"]) is not None for i in out["items"])
    de = plant_seed.resolve_story(story, codes, "de")
    assert de["items"][0]["title"] != out["items"][0]["title"]


def test_delivery_model() -> None:
    story = _load("delivery_model")
    catalogue = json.loads(
        (_ROOT / "backend/app/modules/delivery_model/catalogues/neutral.json").read_text(encoding="utf-8")
    )
    forms = {f["code"] for f in catalogue["forms"]}
    risks = {r["code"] for r in catalogue["risk_categories"]}
    for locale in ("en", "de"):
        out = delivery_seed.resolve_story(story, locale)
        for key in ("forms", "rationales", "owner_capability", "risks", "ground_rationale", "ofi_first", "ofi_second"):
            assert key in out, key
    assert set(story["forms"]) <= forms and set(story["rationales"]) == set(story["forms"])
    assert set(story["risks"]) <= risks
    de = delivery_seed.resolve_story(story, "de")
    en = delivery_seed.resolve_story(story, "en")
    assert de["ground_rationale"] != en["ground_rationale"]
    register = _load("plant_register")
    item = {i["code"]: i for i in register["items"]}[story["plant_item"]]
    assert item["reach"] in {"identified", "specified", "enquired", "route_set"}


def test_procurement_concept() -> None:
    story = _load("procurement_concept")
    catalogue = json.loads(
        (_ROOT / "backend/app/modules/procurement_concept/catalogues/de_national.json").read_text(encoding="utf-8")
    )
    procedures = {p["code"] for p in catalogue["procedures"]}
    jurisdiction = next(j for j in catalogue["jurisdictions"] if j["code"] == "de_national")
    assert story["client_type"] in jurisdiction["client_types"]
    assert set(story["kinds"]) <= set(procurement_seed._DEFAULTS)
    for locale in ("en", "de"):
        for kind, entry in story["kinds"].items():
            merged = procurement_seed.merge_package_story(procurement_seed._DEFAULTS[kind], entry, procedures, locale)
            assert merged["value"] == str(entry["value"]) and merged["notes"], kind
            for key in ("public_procedure", "private_procedure"):
                assert entry.get(key, "open") in procedures
        assert len(procurement_seed.merge_names(procurement_seed._FREE_NAMES, story["free_names"], locale)) == 7
        assert procurement_seed.merge_prequal(story["prequal"], locale)["weights"] == ["40", "25", "35"]
        assert procurement_seed.merge_framework(story["framework"], locale)["code"] == "FW-WOHN-01"
        assert procurement_seed.merge_reference(story["reference"], locale)["value"] == "18500000"
        rows = procurement_seed.merge_soundings(story["soundings"], locale)
        assert rows is not None and len(rows) == len(story["soundings"])
    notes = story["kinds"]["construction"]["notes"]
    assert procurement_seed._story_str(notes, "de") != procurement_seed._story_str(notes, "en")


def test_quality_concept() -> None:
    story = _load("quality_concept")
    catalogue = json.loads(
        (_ROOT / "backend/app/modules/quality_concept/catalogues/neutral.json").read_text(encoding="utf-8")
    )
    codes = {
        "families": {f["code"] for f in catalogue["standard_families"]},
        "categories": {c["code"] for c in catalogue["requirement_categories"]},
        "regimes": {r["code"] for r in catalogue["acceptance_regimes"]},
    }
    plan = quality_seed.resolve_story(story, "en", **codes)
    de = quality_seed.resolve_story(story, "de", **codes)
    assert plan["regime"] == "de_vob_b"
    assert len(plan["packages"]) == 2
    assert len(plan["standards"]) == len(story["standards"])
    assert len(plan["requirements"]) == len(story["requirements"])
    assert len(plan["expert_reports"]) == len(story["expert_reports"])
    assert len(plan["units"]) == len(story["units"])
    assert plan["neighbour"]["triggers"] == ["excavation", "vibration"]
    assert all(i in (0, 1) for u in plan["units"] for i in u[4])
    assert any(u[2] == "total" for u in plan["units"])
    assert any(u[2] == "handover_to_operation" for u in plan["units"])
    assert plan["expert_reports"][0][0] != de["expert_reports"][0][0]


def test_design_management() -> None:
    story = _load("design_management")
    kinds = {
        k["code"]
        for k in json.loads(
            (_ROOT / "backend/app/modules/design_management/catalogues/design_reports/default.json").read_text(
                encoding="utf-8"
            )
        )["report_kinds"]
    }
    plan = design_seed.resolve_story(story, "en", report_kinds=kinds)
    de = design_seed.resolve_story(story, "de", report_kinds=kinds)
    default = design_seed.default_plan()
    assert len(plan["wbs_children"]) == len(story["wbs"]["children"])
    assert len(plan["wbs_extra"]) == len(story["wbs"]["extra"])
    assert plan["roles"]["checker"][1] == "CHK" and plan["roles"]["owner"][1] is None
    assert len(plan["drawings"]) == len(default["drawings"])
    assert all(v != default["deliverables"][k] for k, v in plan["deliverables"].items())
    assert len(plan["extra_reports"]) == len(story["reports"]["extra"])
    assert set(plan["reports"]) == {"RPT-001", "RPT-002", "RPT-003", "RPT-004", "RPT-005"}
    # The open reports the governance story expects stay in the file.
    assert {e["status"] for e in plan["extra_reports"]} >= {"accepted", "required", "in_progress", "commissioned"}
    assert de["approval_points"]["AP-001"] != plan["approval_points"]["AP-001"]
    assert de["wbs_top"] != plan["wbs_top"]


def test_commitment_release() -> None:
    story = _load("commitment_release")
    for locale in ("en", "de"):
        out = commitment_seed.resolve_story(story, locale)
        assert set(out) == set(commitment_seed._SECTIONS)
        for section, keys in out.items():
            assert set(keys) == set(story[section]), f"{section}: a key of the file was dropped"
    # The supply order agrees with the held slot of the plant register story.
    held = _load("plant_register")["slots"]["held"]
    slot = story["slot"]
    assert slot["order_signed_days"] == held["convert_by_days"]
    assert slot["manufacturing_started_days"] == held["slot_from_days"]
    assert slot["plant_item"] == "PL-001"
    assert (
        commitment_seed.resolve_story(story, "de")["slot"]["title"]
        != commitment_seed.resolve_story(story, "en")["slot"]["title"]
    )


def test_site_logistics() -> None:
    story = _load("site_logistics")
    gates, zones, vehicles = site_demo.resolve_site_content(story, "en")
    assert gates != site_demo._GATES and zones != site_demo._ZONES and len(vehicles) == 2
    assert site_demo.resolve_site_content(story, "de")[0] != gates
    out = demo_plan.resolve_plan_content(story, "en")
    out_de = demo_plan.resolve_plan_content(story, "de")
    for key, default in demo_plan._PLAN_TEXT_DEFAULTS.items():
        assert key in story and out_de[key] != default
    assert out["strategy"] != demo_plan._DEFAULT_STRATEGY and out["coordination"] != demo_plan._DEFAULT_COORDINATION
    assert set(out["area_names"]) == {a[0] for a in demo_plan._AREAS}
    assert demo_plan.resolve_plan_content(story, "de")["rules_text"] != out["rules_text"]


def test_transmittals() -> None:
    story = _load("transmittals")
    out = transmittal_seed.parse_transmittals_story(story, "en")
    assert len(out) == len(story["transmittals"]) >= 4
    assert any(e["issued"] is None for e in out)
    assert any(r["resp"] is not None for e in out for r in e["recipients"])
    assert transmittal_seed.parse_transmittals_story(story, "de")[0]["subject"] != out[0]["subject"]
