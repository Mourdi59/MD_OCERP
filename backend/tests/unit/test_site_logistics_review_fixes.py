"""Site logistics plan: the wiring the review of 2026-10-12 found missing or wrong, pinned without a database."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi.routing import APIRoute

from app.modules.site_logistics import hosting, links, plan_schemas, plan_service, router, validators
from app.modules.site_logistics.messages import translate

MODULE = Path(router.__file__).parent
SITE = ZoneInfo("Asia/Kolkata")  # UTC+05:30, no daylight saving: far enough from UTC to tell the clocks apart


def _run(coro):
    return asyncio.run(coro)


# ── finding 6: the plan rules actually execute ─────────────────────────────


def _payload(findings: list[dict]) -> dict:
    return {"findings": findings, "deliveries": [], "gates": {}, "concept_hours": None, "site_timezone": None}


def _validate(monkeypatch: pytest.MonkeyPatch, payload: dict) -> dict:
    validators.register_site_logistics_validation_rules()

    async def fake_payload(self, project_id, today=None):
        return payload

    monkeypatch.setattr(plan_service.LogisticsPlanService, "validation_payload", fake_payload)
    return _run(plan_service.LogisticsPlanService(None).validate(uuid.uuid4(), locale="en"))


def test_validate_runs_every_plan_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _validate(monkeypatch, _payload([]))
    expected = {f"site_logistics.{r.key}" for r in validators.PLAN_RULES}
    assert len(expected) == 22
    # Fails when the payload does not reach the rules: a plan rule without ``findings`` returns nothing.
    assert expected <= set(report["rules_run"])
    assert report["counts"]["errors"] == 0
    assert report["counts"]["passed"] >= len(expected)


def test_validate_reports_a_finding_through_its_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    finding = {
        "rule": "site_timezone_set",
        "code": "site_timezone_missing",
        "severity": "error",
        "ref": None,
        "params": {},
    }
    report = _validate(monkeypatch, _payload([finding]))
    failed = [r for r in report["results"] if not r["passed"]]
    assert [r["rule_id"] for r in failed] == ["site_logistics.site_timezone_set"]
    assert failed[0]["message"] == translate("site_logistics.findings.site_timezone_missing.fail", locale="en")
    assert report["status"] != "passed"


def test_an_empty_payload_would_run_no_plan_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    """The defect itself: the rule set used to be handed a payload without ``findings``."""
    report = _validate(monkeypatch, {})
    assert not {f"site_logistics.{r.key}" for r in validators.PLAN_RULES} & set(report["rules_run"])


def test_validation_payload_carries_what_the_rules_read() -> None:
    import inspect

    source = inspect.getsource(plan_service.LogisticsPlanService.validation_payload)
    for key in ("findings", "site_timezone", "concept_hours", "gates", "deliveries"):
        assert f'"{key}"' in source, key


def test_validate_route_exists_and_reads_only() -> None:
    routes = {(sorted(r.methods)[0], r.path): r for r in router.router.routes if isinstance(r, APIRoute)}
    route = routes[("POST", "/projects/{project_id}/validate")]
    perms = {p for d in route.dependant.dependencies if (p := getattr(d.call, "permission", None))}
    assert perms == {"site_logistics.read"}


# ── finding 1: one site clock ──────────────────────────────────────────────


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 10, 12, h, m, tzinfo=UTC)


def test_gate_hours_are_read_on_the_site_clock() -> None:
    # 02:00 UTC is 07:30 on site: inside 07:00 to 18:00, though the UTC clock reads 02:00.
    assert validators.delivery_within_gate_hours("07:00", "18:00", _at(2), _at(3), SITE) == (True, None)
    # 08:00 UTC is 13:30 on site; 13:00 UTC is 18:30: after closing, though the UTC clock reads 13:00.
    ok, reason = validators.delivery_within_gate_hours("07:00", "18:00", _at(8), _at(13), SITE)
    assert ok is False and "closes" in str(reason)
    # 00:00 UTC is 05:30 on site: before opening.
    ok, reason = validators.delivery_within_gate_hours("07:00", "18:00", _at(0), _at(3), SITE)
    assert ok is False and "opens" in str(reason)
    # 18:00 to 19:00 UTC is one UTC day and crosses the site's midnight.
    ok, reason = validators.delivery_within_gate_hours("00:00", "23:59", _at(18), _at(19), SITE)
    assert ok is False and "same day" in str(reason)


def test_gate_hours_without_a_zone_do_not_guess() -> None:
    ok, reason = validators.delivery_within_gate_hours("07:00", "18:00", _at(8), _at(9))
    assert ok is False
    assert str(reason).startswith("site_timezone_missing")


def test_a_gate_without_hours_needs_no_zone() -> None:
    assert validators.delivery_within_gate_hours(None, None, _at(8), _at(9)) == (True, None)


def _gate_context(tz: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "site_timezone": tz,
            "concept_hours": None,
            "gates": {"g": {"name": "North", "open_time": "07:00", "close_time": "18:00"}},
            "deliveries": [
                {"id": "a", "gate_id": "g", "window_start": _at(2).isoformat(), "window_end": _at(3).isoformat()},
                {"id": "b", "gate_id": "g", "window_start": _at(13).isoformat(), "window_end": _at(14).isoformat()},
            ],
        },
        metadata={},
    )


def test_gate_hours_rule_uses_the_zone_of_the_payload() -> None:
    results = _run(validators.SiteLogisticsGateHoursRule().validate(_gate_context("Asia/Kolkata")))
    assert {r.element_ref: r.passed for r in results} == {"a": True, "b": False}


def test_gate_hours_rule_reports_the_missing_zone_once() -> None:
    results = _run(validators.SiteLogisticsGateHoursRule().validate(_gate_context(None)))
    assert len(results) == 1
    assert results[0].passed is False
    assert results[0].message.startswith("site_timezone_missing")


# ── FIX_BRIEF: no client date on a write route ─────────────────────────────


def test_sweep_takes_no_date_from_the_client() -> None:
    assert plan_schemas.SweepIn.model_fields == {}
    with pytest.raises(ValueError, match="today"):
        plan_schemas.SweepIn.model_validate({"today": "2020-01-01"})


def test_no_plan_request_schema_carries_today() -> None:
    for name in dir(plan_schemas):
        model = getattr(plan_schemas, name)
        if isinstance(model, type) and issubclass(model, plan_schemas._In):
            assert "today" not in model.model_fields, name


def test_state_changes_take_no_date_argument() -> None:
    import inspect

    svc = plan_service.LogisticsPlanService
    for name in (
        "transition_transport",
        "transition_permit",
        "transition_customs",
        "transition_complaint",
        "transition_media",
        "transition_stage",
        "sweep_permit",
        "sweep_permits",
        "sweep_complaint",
        "sweep_complaints",
        "sync_arrivals",
    ):
        assert "today" not in inspect.signature(getattr(svc, name)).parameters, name


# ── neutrality: no governance code in the module ───────────────────────────


def test_module_names_no_governance_area_gate_or_document() -> None:
    from app.modules.project_governance.catalogue import list_catalogues

    codes: set[str] = set()
    for cat in list_catalogues():
        codes |= {a.code for a in cat.areas if "logistics" in a.code}
        codes |= {d.code for d in cat.document_types if "logistics" in d.code}
        codes |= {g.code for g in cat.gates}
    codes = {c for c in codes if len(c) > 3}
    assert codes, "the governance catalogues ship areas and gates"
    for path in MODULE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        used = {c for c in codes if re.search(rf"\b{re.escape(c)}\b", text)}
        assert not used, (path.name, used)


def test_hosting_resolves_logistics_from_tags_in_every_tagged_catalogue() -> None:
    from app.modules.project_governance.catalogue import list_catalogues

    tagged = {}
    for cat in list_catalogues():
        target = hosting.target_of(cat)
        if target.area_code is not None:
            tagged[cat.id] = target
            assert target.area_code in {a.code for a in cat.areas}
    # Three shipped models place logistics, each under a different code.
    assert len(tagged) >= 3
    assert len({t.area_code for t in tagged.values()}) == len(tagged)
    resolved = [t for t in tagged.values() if t.reason is None]
    assert resolved, "at least one shipped model gives logistics a gate"
    for target in resolved:
        assert target.gate_codes


def test_an_untagged_catalogue_resolves_to_a_named_reason() -> None:
    cat = SimpleNamespace(
        areas=[SimpleNamespace(code="x")],
        document_types=[SimpleNamespace(code="doc")],
        phases=[SimpleNamespace(code="p")],
        gates=[SimpleNamespace(code="g", to_phase="p")],
    )
    target = hosting.target_of(cat)
    assert (target.area_code, target.frame_doc_type, target.gate_codes) == (None, None, ())
    assert target.reason == "no_area_hosts_logistics"
    assert hosting.GovernanceTarget(has_model=False).reason == "no_governance_model"
    assert hosting.GovernanceTarget(has_model=True, area_code="x").reason == "no_gate_for_logistics"


def test_gates_fall_back_to_the_phase_that_enables_construction() -> None:
    cat = SimpleNamespace(
        areas=[SimpleNamespace(code="log", hosts=("logistics",))],
        document_types=[],
        phases=[SimpleNamespace(code="plan"), SimpleNamespace(code="build", enables=("construction_start",))],
        gates=[SimpleNamespace(code="g1", to_phase="plan"), SimpleNamespace(code="g2", to_phase="build")],
    )
    target = hosting.target_of(cat)
    assert target.gate_codes == ("g2",)
    assert target.frame_doc_type is None
    assert target.reason is None


def test_evidence_provider_is_registered_for_every_area_and_blocking() -> None:
    from app.modules.project_governance.evidence import ANY_AREA, evidence_providers
    from app.modules.site_logistics.evidence import PROVIDER, register_gate_evidence

    register_gate_evidence()
    [reg] = [p for p in evidence_providers() if p.name == PROVIDER]
    assert reg.key == ANY_AREA
    assert reg.blocking is True


# ── the link port for modules that are not merged yet ──────────────────────


def test_link_resolver_registry() -> None:
    async def owner(session, row_id):
        return None

    assert links.resolver("plant_item") is None or callable(links.resolver("plant_item"))
    links.register_link_resolver("plant_item", owner)
    try:
        assert links.resolver("plant_item") is owner
    finally:
        links.unregister_link_resolver("plant_item")
    assert links.resolver("plant_item") is None
    with pytest.raises(ValueError, match="unknown link kind"):
        links.register_link_resolver("purchase_order", owner)


class _NoSession:
    """A session that fails the test if the port touches the database."""

    def __getattr__(self, name: str):
        raise AssertionError(f"unexpected session use: {name}")


def test_port_refuses_a_link_nobody_can_check() -> None:
    from app.modules.site_logistics.errors import LogisticsError

    svc = plan_service.LogisticsPlanService(_NoSession())
    project = uuid.uuid4()
    links.unregister_link_resolver("plant_item")
    with pytest.raises(LogisticsError) as exc:
        _run(svc._port("plant_item", uuid.uuid4(), project))
    assert (exc.value.code, exc.value.status_code) == ("link_target_unavailable", 422)
    # Nothing to check: no value, or the value already stored.
    _run(svc._port("plant_item", None, project))
    same = uuid.uuid4()
    _run(svc._port("plant_item", str(same), project, same))


def test_port_accepts_only_a_row_of_the_same_project() -> None:
    from app.modules.site_logistics.errors import LogisticsError

    project, other, row = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    owners = {row: project}

    async def owner(session, row_id):
        return owners.get(row_id)

    svc = plan_service.LogisticsPlanService(_NoSession())
    links.register_link_resolver("plant_position", owner)
    try:
        _run(svc._port("plant_position", row, project))
        for foreign_project, foreign_row in ((other, row), (project, uuid.uuid4())):
            with pytest.raises(LogisticsError) as exc:
                _run(svc._port("plant_position", foreign_row, foreign_project))
            assert (exc.value.code, exc.value.status_code) == ("plant_position_not_found", 404)
    finally:
        links.unregister_link_resolver("plant_position")


# ── the periodic sweep ─────────────────────────────────────────────────────


def test_sweep_is_a_registered_platform_process() -> None:
    from app.core.processes import process_registry
    from app.modules.site_logistics.sweep import PROCESS_ID, register_sweep_process

    register_sweep_process()
    assert PROCESS_ID in process_registry.ids()


# ── permission, not a raw role ─────────────────────────────────────────────


def test_customs_values_follow_the_permission_of_the_token() -> None:
    from app.modules.site_logistics.permissions import register_site_logistics_permissions

    register_site_logistics_permissions()
    assert router._sees_values({"role": "viewer", "permissions": ["site_logistics.customs"]}) is True
    assert router._sees_values({"role": "viewer", "permissions": []}) is False
    assert router._sees_values({"role": "manager"}) is True
    assert router._sees_values({}) is False


# ── values, never clamped ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("current", "new", "same"),
    [
        (None, None, True),
        (None, "x", False),
        ("x", None, False),
        (uuid.UUID(int=7), str(uuid.UUID(int=7)), True),
        (uuid.UUID(int=7), str(uuid.UUID(int=8)), False),
        (datetime(2026, 10, 12, 8, tzinfo=UTC), datetime(2026, 10, 12, 13, 30, tzinfo=SITE), True),
        (datetime(2026, 10, 12, 8, tzinfo=UTC), datetime(2026, 10, 12, 8, tzinfo=SITE), False),
        (plan_service.Decimal("62.00"), "62", True),
        (plan_service.Decimal("62.00"), "62.5", False),
        ("oversize_permit", "oversize_permit", True),
    ],
)
def test_same_compares_what_a_request_sends_with_what_is_stored(current, new, same: bool) -> None:
    assert plan_service._same(current, new) is same
