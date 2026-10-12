# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pins for the independent review of the commitment release module (pure, no database)."""

from __future__ import annotations

from fastapi.routing import APIRoute

from app.modules.commitment_release.router import router

CLIENT_DATE_PARAMS = {"today", "as_of"}


def _routes() -> list[APIRoute]:
    return [r for r in router.routes if isinstance(r, APIRoute)]


def test_no_write_route_takes_a_date_from_the_caller() -> None:
    """The FX date and the validity of an assignment are the server's; only a GET may ask for a day."""
    offenders = []
    for route in _routes():
        if route.methods == {"GET"}:
            continue
        taken = {p.name for p in route.dependant.query_params} & CLIENT_DATE_PARAMS
        if taken:
            offenders.append((sorted(route.methods), route.path, sorted(taken)))
    assert offenders == []


def test_read_routes_still_offer_a_day() -> None:
    by_path = {r.path: r for r in _routes() if r.methods == {"GET"}}
    assert "today" in {p.name for p in by_path["/projects/{project_id}/items"].dependant.query_params}
    assert "as_of" in {p.name for p in by_path["/projects/{project_id}/exposure"].dependant.query_params}


def _flat(node: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for key, value in node.items():
        out |= _flat(value, f"{prefix}{key}.") if isinstance(value, dict) else {f"{prefix}{key}"}
    return out


def test_every_refusal_code_has_a_message_in_every_language_the_module_ships() -> None:
    """A refused action answers a code; a code without a message shows the raw key to the user."""
    import json
    import re
    from pathlib import Path

    import app.modules.commitment_release as module

    root = Path(module.__file__).parent
    codes: set[str] = set()
    for source in root.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        codes |= set(re.findall(r"(?:CommitmentError|conflict|forbidden|not_found)\(\s*\"([a-z_0-9]+)\"", text))
        codes |= set(re.findall(r"rationale=\"([a-z_0-9]+)\"", text))
    codes |= {"four_eyes_no_approver", "four_eyes_requester_is_approver", "commitment_guard_unavailable"}
    codes |= {"not_item_owner", "manage_required", "not_requester", "not_entitled_decider", "four_eyes_violation"}
    codes |= {"release_pending", "invalid_transition", "no_pending_release", "item_closed"}
    assert len(codes) > 60
    files = sorted((root / "messages").glob("*.json"))
    assert [f.name for f in files] == ["de.json", "en.json"]
    for file in files:
        keys = _flat(json.loads(file.read_text(encoding="utf-8")))
        missing = sorted(c for c in codes if f"commitment.errors.{c}" not in keys)
        assert missing == [], (file.name, missing)
