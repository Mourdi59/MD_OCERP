"""The read port other modules use: listings as small frozen read models."""

from __future__ import annotations

import dataclasses
import uuid
from types import SimpleNamespace

import pytest

from app.modules.project_governance import catalogue as cat
from app.modules.project_governance import public


def _id(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


def _gate(n: int, code: str, order: int, status: str = "not_started", outcome: str = "") -> SimpleNamespace:
    c = cat.get_catalogue("neutral").gate(code)
    return SimpleNamespace(
        id=_id(n),
        code=code,
        sort_order=order,
        status=status,
        from_phase=c.from_phase,
        to_phase=c.to_phase,
        last_outcome=outcome,
    )


def _area(n: int, code: str, order: int, **kw) -> SimpleNamespace:
    base = {"name_override": "", "applicable": True, "owner_user_id": None, "deputy_user_id": None}
    return SimpleNamespace(id=_id(n), code=code, sort_order=order, **{**base, **kw})


def _doc(n: int, doc_type: str, area: int, **kw) -> SimpleNamespace:
    base = {"status": "draft", "required_at_gates": [], "read_only": False}
    return SimpleNamespace(id=_id(n), doc_type=doc_type, area_id=_id(area), **{**base, **kw})


def test_gate_views_are_ordered_and_labelled() -> None:
    neutral = cat.get_catalogue("neutral")
    rows = [_gate(2, "brief_to_concept", 2), _gate(1, "strategy_to_brief", 1, "decided", "go")]
    views = public.gate_views(neutral, rows)
    assert [(v.code, v.order, v.status, v.last_outcome) for v in views] == [
        ("strategy_to_brief", 1, "decided", "go"),
        ("brief_to_concept", 2, "not_started", ""),
    ]
    assert (views[0].from_phase, views[0].to_phase) == ("strategy", "brief")
    assert views[0].label == {"key": "governance.catalogue.neutral.gate.strategy_to_brief", "text": None}
    assert views[0].id == _id(1)


def test_area_views_carry_owner_and_applicability() -> None:
    neutral = cat.get_catalogue("neutral")
    rows = [
        _area(2, "scope", 2, applicable=False),
        _area(1, "integration", 1, owner_user_id=_id(7), name_override="Steering"),
    ]
    views = public.area_views(neutral, rows)
    assert [(v.code, v.order, v.status) for v in views] == [
        ("integration", 1, "applicable"),
        ("scope", 2, "not_applicable"),
    ]
    assert (views[0].owner_user_id, views[0].deputy_user_id, views[0].name_override) == (_id(7), None, "Steering")
    assert views[1].label["key"] == "governance.catalogue.neutral.area.scope"


def test_document_views_follow_area_order_and_drop_documents_of_retired_areas() -> None:
    neutral = cat.get_catalogue("neutral")
    areas = public.area_views(neutral, [_area(1, "integration", 1), _area(2, "scope", 2)])
    rows = [
        _doc(11, "scope_statement", 2, status="binding", required_at_gates=["design_to_approval"], read_only=True),
        _doc(12, "requirements_brief", 2),
        _doc(13, "project_handbook", 1),
        _doc(14, "risk_register", 99),
    ]
    views = public.document_views(neutral, rows, areas)
    assert [(v.code, v.area_code, v.order) for v in views] == [
        ("project_handbook", "integration", 1),
        ("requirements_brief", "scope", 2),
        ("scope_statement", "scope", 3),
    ]
    last = views[-1]
    assert (last.status, last.required_at_gates, last.read_only) == ("binding", ("design_to_approval",), True)
    assert last.label["key"] == "governance.catalogue.neutral.doc.scope_statement"


def test_a_code_the_catalogue_does_not_know_has_an_empty_label() -> None:
    views = public.area_views(cat.get_catalogue("neutral"), [_area(1, "left_over", 1)])
    assert views[0].label == {"key": None, "text": None}


@pytest.mark.parametrize("view", [public.GateView, public.AreaView, public.DocumentView, public.Host])
def test_read_models_are_frozen(view: type) -> None:
    assert dataclasses.is_dataclass(view) and view.__dataclass_params__.frozen


@pytest.mark.parametrize("view", [public.GateView, public.AreaView, public.DocumentView])
def test_every_listing_model_has_the_common_fields(view: type) -> None:
    names = {f.name for f in dataclasses.fields(view)}
    assert {"id", "code", "label", "order", "status"} <= names


def test_the_port_exports_its_listing_calls() -> None:
    assert {"project_gates", "project_areas", "project_documents"} <= set(public.__all__)
