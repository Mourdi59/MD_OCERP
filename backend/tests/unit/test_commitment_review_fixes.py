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
