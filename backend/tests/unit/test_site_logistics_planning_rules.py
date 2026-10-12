"""Pure rules of the site-logistics plan (framework module 11): no database."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.site_logistics import planning as pl
from app.modules.site_logistics.catalogue import (
    INCOTERM_CODES_2020,
    SiteLogisticsCatalogue,
    default_catalogue_id,
    has_figure,
    resolved_shipped,
    shipped_catalogues,
    validate_site_logistics_catalogue,
)
from app.modules.site_logistics.geometry import GeometryError, polygon_area_m2, polygons_overlap, validate_polygon

D = Decimal


def _square(x: float, y: float, side: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [[[x, y], [x + side, y], [x + side, y + side], [x, y + side], [x, y]]],
    }


# ── State machines ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fsm", "current", "target", "allowed"),
    [
        (pl.STAGE_FSM, "planned", "active", True),
        (pl.STAGE_FSM, "planned", "closed", False),
        (pl.STAGE_FSM, "closed", "active", False),
        (pl.TRANSPORT_FSM, "planned", "scheduled", True),
        (pl.TRANSPORT_FSM, "planned", "in_transit", False),
        (pl.TRANSPORT_FSM, "in_transit", "cancelled", False),
        (pl.TRANSPORT_FSM, "arrived", "closed", True),
        (pl.PERMIT_FSM, "draft", "granted", False),
        (pl.PERMIT_FSM, "applied", "granted", True),
        (pl.PERMIT_FSM, "refused", "applied", False),
        (pl.CUSTOMS_FSM, "open", "declared", False),
        (pl.CUSTOMS_FSM, "held", "cleared", True),
        (pl.MEDIA_FSM, "offered", "contracted", True),
        (pl.MEDIA_FSM, "identified", "connected", False),
        (pl.COMPLAINT_FSM, "received", "closed", False),
        (pl.COMPLAINT_FSM, "acknowledged", "closed", True),
        (pl.CUSTOMS_DOCUMENT_FSM, "missing", "verified", False),
    ],
)
def test_state_machines(fsm, current, target, allowed) -> None:
    assert pl.can_move(fsm, current, target) is allowed


def test_terminal_states_have_no_exit() -> None:
    for fsm, terminal in (
        (pl.TRANSPORT_FSM, ("closed", "cancelled")),
        (pl.PERMIT_FSM, ("refused", "expired")),
        (pl.CUSTOMS_FSM, ("closed",)),
        (pl.COMPLAINT_FSM, ("closed",)),
    ):
        for state in terminal:
            assert fsm[state] == ()


def test_unknown_state_is_refused() -> None:
    assert pl.can_move(pl.TRANSPORT_FSM, "nonsense", "scheduled") is False


# ── Area balance ───────────────────────────────────────────────────────────


class _Kind:
    def __init__(self, group: str, counts: bool = True) -> None:
        self.balance_group = group
        self.counts_in_balance = counts


KINDS = {
    "building": _Kind("built"),
    "storage": _Kind("logistics"),
    "reserve": _Kind("reserve"),
    "public_road": _Kind("external", counts=False),
}


def _alloc(kind: str, m2: str, area_id: str | None = None, **kw) -> pl.AllocationFact:
    return pl.AllocationFact(area_id or kind, kind, D(m2), **kw)


def test_balance_closes_exactly() -> None:
    bal = pl.area_balance(
        [_alloc("site_total", "10000"), _alloc("building", "6000"), _alloc("storage", "4000")], KINDS, D("2")
    )
    assert bal.closed is True
    assert bal.difference_m2 == 0
    assert bal.by_group == {"built": D("6000"), "logistics": D("4000")}


@pytest.mark.parametrize(("counted", "closed"), [("9800", True), ("10200", True), ("9799", False), ("10201", False)])
def test_balance_tolerance_edge(counted: str, closed: bool) -> None:
    building = D(counted) - D("1000")
    bal = pl.area_balance(
        [_alloc("site_total", "10000"), _alloc("building", str(building)), _alloc("storage", "1000")], KINDS, D("2")
    )
    assert bal.closed is closed


def test_balance_ignores_kinds_that_do_not_count() -> None:
    bal = pl.area_balance(
        [_alloc("site_total", "100"), _alloc("building", "100"), _alloc("public_road", "500")], KINDS, D("0")
    )
    assert bal.closed is True
    assert bal.by_kind["public_road"] == D("500")


def test_balance_without_site_total_uses_fallback_then_reports() -> None:
    fallback = pl.area_balance([_alloc("building", "100")], KINDS, D("0"), site_total_fallback_m2=D("100"))
    assert fallback.closed is True
    missing = pl.area_balance([_alloc("building", "100")], KINDS, D("0"))
    assert (missing.closed, missing.reason) == (False, "no_site_total")


def test_balance_as_dict_is_json_safe() -> None:
    bal = pl.area_balance([_alloc("site_total", "10"), _alloc("building", "9.5")], KINDS, D("10"))
    json.dumps(bal.as_dict())


def test_allocation_exceeds_area() -> None:
    assert pl.allocation_exceeds_area(D("101"), D("100")) is True
    assert pl.allocation_exceeds_area(D("100"), D("100")) is False
    assert pl.allocation_exceeds_area(D("1e6"), None) is False


def test_stage_gaps() -> None:
    assert pl.stage_gaps(["laydown", "site_setup"]) == []
    assert pl.stage_gaps(["building"]) == ["stage_without_storage", "stage_without_site_setup"]


# ── Geometry and overlap ───────────────────────────────────────────────────


def test_polygon_area_local_and_wgs84() -> None:
    assert polygon_area_m2(_square(0, 0, 50)) == D("2500.00")
    # 0.001 degree square at the equator is about 111.2 m on each side.
    area = polygon_area_m2(_square(0, 0, 0.001), frame="wgs84")
    assert D("12300") < area < D("12400")


@pytest.mark.parametrize(
    ("b", "overlap"),
    [
        (_square(5, 5, 10), True),  # edges cross
        (_square(2, 2, 2), True),  # fully inside
        (_square(10, 0, 10), False),  # shares an edge only
        (_square(20, 20, 5), False),  # apart
    ],
)
def test_polygons_overlap(b: dict, overlap: bool) -> None:
    assert polygons_overlap(_square(0, 0, 10), b) is overlap


def test_identical_polygons_overlap() -> None:
    assert polygons_overlap(_square(0, 0, 10), _square(0, 0, 10)) is True


def test_overlapping_pairs_skip_same_kind_and_site_total() -> None:
    rows = [
        _alloc("building", "1", "a", geometry=_square(0, 0, 10)),
        _alloc("storage", "1", "b", geometry=_square(5, 5, 10)),
        _alloc("storage", "1", "c", geometry=_square(6, 6, 10)),
        _alloc("site_total", "1", "t", geometry=_square(0, 0, 100)),
    ]
    assert pl.overlapping_pairs(rows) == [("a", "b"), ("a", "c")]


@pytest.mark.parametrize(
    "geometry",
    [{"type": "Point", "coordinates": [0, 0]}, {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}, {}],
)
def test_validate_polygon_rejects(geometry: dict) -> None:
    with pytest.raises(GeometryError):
        validate_polygon(geometry)


# ── Heavy loads and permits ────────────────────────────────────────────────

GATE = {"max_axle_load_t": D("11.5"), "max_gross_t": D("40"), "max_height_m": D("4"), "max_width_m": D("2.55")}


def test_exceeded_limits_and_is_heavy() -> None:
    truck = {"axle_load_t": "10", "gross_weight_t": "38", "height_m": "3.9"}
    assert pl.exceeded_limits(truck, GATE) == []
    assert pl.is_heavy(truck, [GATE]) is False
    over = {**truck, "gross_weight_t": "84", "width_m": "3.4"}
    assert pl.exceeded_limits(over, GATE) == ["gross_weight_t", "width_m"]
    assert pl.is_heavy(over, [GATE]) is True
    assert pl.is_heavy(truck, [GATE], always_heavy=True) is True


def test_unset_values_and_limits_are_not_exceeded() -> None:
    assert pl.exceeded_limits({"gross_weight_t": "99"}, {}) == []
    assert pl.limits_unknown({}) is True
    assert pl.limits_unknown(GATE) is False


def test_limits_from_class() -> None:
    class Cls:
        axle_load_t = D("11.5")
        gross_weight_t = D("40")
        max_height_m = D("4")
        max_width_m = None
        max_length_m = None
        turning_radius_m = None

    limits = pl.limits_from_class(Cls())
    assert limits["max_gross_t"] == D("40")
    assert pl.exceeded_limits({"axle_load_t": "12"}, limits) == ["axle_load_t"]


TZ = timezone(timedelta(hours=1))


def _dt(day: int, h: int, m: int = 0) -> datetime:
    return datetime(2026, 10, day, h, m, tzinfo=TZ)


NIGHT = [{"weekdays": [0, 1, 2, 3, 4], "from": "22:00", "to": "06:00"}]


def test_overnight_window_contains_a_run_across_midnight() -> None:
    # 2026-10-12 is a Monday.
    assert pl.window_in_allowed(NIGHT, _dt(12, 23), _dt(13, 4)) is True
    assert pl.window_in_allowed(NIGHT, _dt(13, 1), _dt(13, 5)) is True  # started Monday night
    assert pl.window_in_allowed(NIGHT, _dt(12, 21), _dt(12, 23)) is False
    assert pl.window_in_allowed(NIGHT, _dt(13, 5), _dt(13, 7)) is False


def test_overnight_window_respects_weekday_of_start() -> None:
    # Saturday 2026-10-17 night is not allowed; neither is the Sunday morning after it.
    assert pl.window_in_allowed(NIGHT, _dt(17, 23), _dt(18, 2)) is False
    assert pl.window_in_allowed(NIGHT, _dt(18, 1), _dt(18, 2)) is False


def test_no_windows_means_no_time_restriction() -> None:
    assert pl.window_in_allowed(None, _dt(12, 12), _dt(12, 13)) is True


def _permit(state: str = "granted", **kw) -> dict:
    return {
        "permit_kind": "oversize",
        "state": state,
        "valid_from": date(2026, 10, 1),
        "valid_to": date(2026, 10, 31),
        "allowed_windows": NIGHT,
        **kw,
    }


def test_heavy_permit_finding() -> None:
    start, end = _dt(12, 23), _dt(13, 3)
    assert pl.heavy_permit_finding([], start, end, ["oversize"]) == "heavy_without_permit"
    assert pl.heavy_permit_finding([_permit("applied")], start, end, ["oversize"]) == "heavy_without_permit"
    assert pl.heavy_permit_finding([_permit()], start, end, ["night_work"]) == "heavy_without_permit"
    assert pl.heavy_permit_finding([_permit()], start, end, ["oversize"]) is None
    assert pl.heavy_permit_finding([_permit()], _dt(12, 10), _dt(12, 12), ["oversize"]) == "window_outside_permit"
    assert pl.heavy_permit_finding([_permit()], None, None, ["oversize"]) == "window_outside_permit"


def test_permit_validity_bounds() -> None:
    late = datetime(2026, 11, 2, 23, tzinfo=TZ)
    assert pl.permit_covers(_permit(), late, late + timedelta(hours=2)) is False


def test_permit_expiry() -> None:
    today = date(2026, 10, 12)
    assert pl.permit_expiry(None, today, 14) == "ok"
    assert pl.permit_expiry(date(2026, 10, 11), today, 14) == "expired"
    assert pl.permit_expiry(date(2026, 10, 12), today, 14) == "expiring"
    assert pl.permit_expiry(date(2026, 10, 26), today, 14) == "expiring"
    assert pl.permit_expiry(date(2026, 10, 27), today, 14) == "ok"


def test_narrower_hours() -> None:
    assert pl.narrower_hours(("06:00", "20:00"), ("07:00", "22:00")) == ("07:00", "20:00")
    assert pl.narrower_hours(("06:00", "20:00"), None) == ("06:00", "20:00")
    assert pl.narrower_hours((None, None), ("07:00", "18:00")) == ("07:00", "18:00")
    assert pl.narrower_hours(("06:00", "20:00"), ("bad", "18:00")) == ("06:00", "20:00")


@pytest.mark.parametrize(
    ("value", "minutes"), [("00:00", 0), ("23:59", 1439), ("24:00", None), ("7", None), (None, None)]
)
def test_hhmm(value, minutes) -> None:
    assert pl.hhmm(value) == minutes


# ── Media ──────────────────────────────────────────────────────────────────


def test_media_required_and_short() -> None:
    required = pl.media_required([(D("100"), D("0.8")), (D("60"), D("1"))], D("10"))
    assert required == D("154.000")
    assert pl.media_short(required, D("154")) is False
    assert pl.media_short(required, D("140.8")) is True
    assert pl.media_short(D("1"), None) is True
    assert pl.media_short(D("0"), None) is False


def test_media_late() -> None:
    today = date(2026, 10, 12)
    stage = date(2026, 11, 1)
    assert pl.media_late("requested", date(2026, 11, 2), stage, today) is True
    assert pl.media_late("requested", date(2026, 10, 30), stage, today) is False
    assert pl.media_late("contracted", date(2026, 12, 1), stage, today) is False
    assert pl.media_late("requested", None, stage, today) is False
    assert pl.media_late("requested", None, date(2026, 10, 1), today) is True
    assert pl.media_late("requested", None, None, today) is False


# ── Just in time and quiet hours ───────────────────────────────────────────


def test_jit_finding() -> None:
    takt = date(2026, 10, 20)
    assert pl.jit_finding(date(2026, 10, 18), takt, 2) is None
    assert pl.jit_finding(date(2026, 10, 20), takt, 2) is None
    assert pl.jit_finding(date(2026, 10, 17), takt, 2) == "jit_too_early"
    assert pl.jit_finding(date(2026, 10, 21), takt, 2) == "jit_late"
    assert pl.jit_finding(date(2026, 10, 1), None, 2) is None


def test_quiet_hours_across_midnight() -> None:
    quiet = ("20:00", "07:00")
    assert pl.quiet_hours_conflict(quiet, _dt(12, 8), _dt(12, 19)) is False
    assert pl.quiet_hours_conflict(quiet, _dt(12, 19), _dt(12, 21)) is True
    assert pl.quiet_hours_conflict(quiet, _dt(13, 6), _dt(13, 8)) is True
    assert pl.quiet_hours_conflict(quiet, _dt(12, 7), _dt(12, 20)) is False  # touches both edges only
    assert pl.quiet_hours_conflict(None, _dt(12, 1), _dt(12, 2)) is False


# ── Customs ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "ok"), [("853720", True), ("8537200000", True), ("85372", False), ("8537.20", False), ("", False)]
)
def test_hs_code_valid(code: str, ok: bool) -> None:
    assert pl.hs_code_valid(code, 6) is ok


# Independent of the shipped catalogue: who clears export and import under each
# Incoterms 2020 rule (A7/B7), and which rules are for sea and inland waterway only.
ICC_2020 = {
    "EXW": ("buyer", "buyer", False),
    "FCA": ("seller", "buyer", False),
    "CPT": ("seller", "buyer", False),
    "CIP": ("seller", "buyer", False),
    "DAP": ("seller", "buyer", False),
    "DPU": ("seller", "buyer", False),
    "DDP": ("seller", "seller", False),
    "FAS": ("seller", "buyer", True),
    "FOB": ("seller", "buyer", True),
    "CFR": ("seller", "buyer", True),
    "CIF": ("seller", "buyer", True),
}


@pytest.fixture(scope="module")
def neutral() -> SiteLogisticsCatalogue:
    return resolved_shipped("neutral")


def test_shipped_incoterms_match_icc(neutral: SiteLogisticsCatalogue) -> None:
    assert set(ICC_2020) == set(INCOTERM_CODES_2020) == neutral.codes("incoterms")
    for code, (export_by, import_by, sea_only) in ICC_2020.items():
        term = neutral.entry("incoterms", code)
        assert (term.export_clearance_by, term.import_clearance_by, term.sea_only) == (export_by, import_by, sea_only)


@pytest.mark.parametrize("code", sorted(ICC_2020))
@pytest.mark.parametrize("direction", ["import", "export"])
def test_document_template_per_incoterm(neutral, code: str, direction: str) -> None:
    export_by, import_by, _ = ICC_2020[code]
    docs = pl.required_documents(direction, neutral.entry("incoterms", code), "road")
    assert docs[:2] == ["commercial_invoice", "packing_list"]
    assert "cmr" in docs
    if direction == "import":
        assert "certificate_of_origin" in docs
        assert ("import_declaration" in docs) is (import_by == "buyer")
        assert "export_declaration" not in docs
    else:
        assert ("export_declaration" in docs) is (export_by == "seller")
        assert "import_declaration" not in docs


def test_document_template_mode_and_preference(neutral) -> None:
    fob = neutral.entry("incoterms", "FOB")
    assert "bill_of_lading" in pl.required_documents("import", fob, "sea")
    assert "air_waybill" in pl.required_documents("import", fob, "air")
    assert "preferential_origin_statement" in pl.required_documents("import", fob, None, preferential=True)


def test_sea_only_and_declarant(neutral) -> None:
    fob, fca, ddp = (neutral.entry("incoterms", c) for c in ("FOB", "FCA", "DDP"))
    assert pl.sea_only_mismatch(fob, "road") is True
    assert pl.sea_only_mismatch(fob, "sea") is False
    assert pl.sea_only_mismatch(fca, "road") is False
    assert pl.declarant_matches("import", fca, "buyer") is True
    assert pl.declarant_matches("import", ddp, "buyer") is False
    assert pl.declarant_matches("export", ddp, "buyer") is True
    assert pl.declarant_matches("import", None, "buyer") is True


def test_missing_required() -> None:
    docs = [
        {"kind": "commercial_invoice", "required": True, "state": "missing"},
        {"kind": "packing_list", "required": True, "state": "received"},
        {"kind": "insurance", "required": False, "state": "missing"},
    ]
    assert pl.missing_required(docs) == ["commercial_invoice"]


def test_complaint_overdue() -> None:
    today = date(2026, 10, 12)
    assert pl.complaint_overdue("received", date(2026, 10, 11), today) is True
    assert pl.complaint_overdue("received", today, today) is False
    assert pl.complaint_overdue("acknowledged", date(2026, 10, 1), today) is False
    assert pl.complaint_overdue("received", None, today) is False


# ── Catalogues ─────────────────────────────────────────────────────────────


def test_shipped_catalogues_validate_and_merge() -> None:
    shipped = shipped_catalogues()
    assert {"neutral", "de", "uk", "us"} <= set(shipped)
    for cat_id, cat in shipped.items():
        assert validate_site_logistics_catalogue(cat, "shipped") == [], cat_id
        merged = resolved_shipped(cat_id)
        assert merged.codes("incoterms") == set(INCOTERM_CODES_2020)
        assert {"site_total", "storage", "laydown", "site_setup"} <= merged.codes("area_kinds")


def test_national_figures_are_sourced_and_unconfirmed() -> None:
    for cat_id in ("de", "uk", "us"):
        cat = shipped_catalogues()[cat_id]
        for group in ("load_classes", "permit_kinds", "noise_limits"):
            for entry in getattr(cat, group):
                ref = f"{cat_id}:{group}:{entry.code}"
                # An entry without a figure (a method, "project enters its own value") needs no source.
                if has_figure(entry):
                    assert entry.source_url, ref
                if entry.review_status is not None:
                    assert entry.review_status.value == "unconfirmed", ref
                if getattr(entry, "project_value_required", False):
                    assert entry.day_dba is None and entry.night_dba is None, ref


def test_validator_flags_figure_without_source() -> None:
    body = resolved_shipped("neutral").model_dump()
    body["id"] = "probe"
    body["load_classes"] = [{"code": "probe", "gross_weight_t": "40"}]
    errors = validate_site_logistics_catalogue(SiteLogisticsCatalogue.model_validate(body), "tenant")
    assert "statutory_figure_without_source: load_classes:probe" in errors


def test_validator_flags_incomplete_incoterms() -> None:
    body = resolved_shipped("neutral").model_dump()
    body["id"] = "probe"
    body["extends"] = None
    body["incoterms"] = body["incoterms"][:3]
    errors = validate_site_logistics_catalogue(SiteLogisticsCatalogue.model_validate(body), "tenant")
    assert "incoterms_2020_incomplete" in errors


@pytest.mark.parametrize(
    ("country", "expected"), [("DE", "de"), ("GB", "uk"), ("us", "us"), ("FR", "neutral"), (None, "neutral")]
)
def test_default_catalogue_id(country, expected) -> None:
    assert default_catalogue_id(country) == expected


# ── JSON columns ───────────────────────────────────────────────────────────


def test_json_safe_dumps() -> None:
    value = {
        "when": datetime(2026, 10, 12, 8, tzinfo=UTC),
        "day": date(2026, 10, 12),
        "amount": D("12.50"),
        "id": uuid.UUID(int=1),
        "pair": ("a", D("1")),
        "nested": [{"x": {D("1")}}],
    }
    safe = pl.json_safe(value)
    text = json.dumps(safe)
    assert safe["amount"] == "12.50"
    assert safe["day"] == "2026-10-12"
    assert "Decimal" not in text
