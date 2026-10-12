# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo logistics plan for a demo project, run from :func:`demo.seed_site_logistics_demo`.

The neutral example of SPEC section 11, country neutral and with no company or
person names: a 12 000 m2 site in two stages (earthworks, structure) whose area
balance closes; power for two tower cranes and the site offices against a
contracted connection with the reserve; a water connection still on request; a
concept with stock, kanban and direct-install flows; a heavy transformer
transport that is scheduled on a granted oversize permit (which also lifts the
gate's load limit for it) and a granted night-work permit for its night window;
a spoil run and a regular inbound delivery; an import
case under FCA with HS-coded lines and its document checklist; the neighbourhood
plan with quiet hours, two complaints and two coordination entries.

Everything goes through :class:`LogisticsPlanService`, so the rows obey the same
rules a user meets. Dates are anchored to the day the demo is seeded, and the
permit windows cover every weekday, so the plan is valid whatever day that is.
The site clock is set to UTC explicitly: a demo project states no location, and
the time rules do not run without a zone. A project that already has a stage is
skipped, so a re-run adds nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


DEMO_SITE_TIMEZONE = "UTC"
_EVERY_WEEKDAY = [0, 1, 2, 3, 4, 5, 6]


def _square(x0: int, y0: int, w: int, h: int) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h], [x0, y0]]]}


# (code, kind, geometry or declared m2, stage-1 kind and m2, stage-2 kind and m2)
_AREAS: tuple[tuple[str, str, dict[str, Any] | None, str | None, tuple[str, str], tuple[str, str]], ...] = (
    ("SITE", "site_total", _square(0, 0, 120, 100), None, ("site_total", "12000"), ("site_total", "12000")),
    (
        "A-BLD",
        "building_footprint",
        _square(20, 20, 90, 60),
        None,
        ("expansion_reserve", "5400"),
        ("building_footprint", "5400"),
    ),
    ("A-LAY", "laydown", _square(0, 0, 60, 20), None, ("laydown", "1200"), ("laydown", "1200")),
    ("A-LAY2", "laydown", None, "1800", ("laydown", "1800"), ("laydown", "600")),
    ("A-SET", "site_setup", None, "800", ("site_setup", "800"), ("site_setup", "800")),
    ("A-TRF", "traffic_route", None, "2200", ("traffic_route", "2200"), ("traffic_route", "1600")),
    ("A-RES", "expansion_reserve", None, "2400", ("expansion_reserve", "600"), ("expansion_reserve", "2400")),
)


async def seed_logistics_plan_demo(session: AsyncSession, project_ids: list[uuid.UUID]) -> dict[str, int]:
    """Seed the logistics plan of every project in ``project_ids`` that has no stage yet. The caller commits."""
    from app.modules.site_logistics.models import ExpansionStage

    totals = {"projects": 0, "transports": 0}
    for pid in project_ids:
        has = (
            await session.execute(select(ExpansionStage.id).where(ExpansionStage.project_id == pid).limit(1))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                written = await _seed_project(session, pid)
        except Exception:
            logger.warning("site_logistics plan demo skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        totals["transports"] += written
    return totals


async def _seed_project(session: AsyncSession, pid: uuid.UUID) -> int:
    from app.modules.site_logistics.models import Gate, LaydownZone
    from app.modules.site_logistics.plan_service import LogisticsPlanService

    svc = LogisticsPlanService(session)
    cat = await svc.catalogue(pid)
    today = datetime.now(UTC).date()
    actor = None

    # The site clock first: every window below is checked on it.
    await svc.put_concept(pid, {"site_timezone": DEMO_SITE_TIMEZONE}, actor)

    # Stages: earthworks now, structure from week 8. The first write above created the initial stage.
    stage1 = (await svc.stages(pid))[0]
    await svc.update_stage(
        pid,
        stage1.id,
        {
            "code": "stage_1",
            "title": "Earthworks",
            "ordinal": 1,
            "from_date": today - timedelta(days=14),
            "to_date": today + timedelta(days=42),
        },
        actor,
    )
    await svc.transition_stage(pid, stage1.id, "active", actor)
    stage2 = await svc.create_stage(
        pid,
        {
            "code": "stage_2",
            "title": "Structure",
            "ordinal": 2,
            "from_date": today + timedelta(days=43),
            "to_date": today + timedelta(days=300),
        },
        actor,
    )

    # Areas and their allocation per stage: both balances close at 12 000 m2.
    areas = {}
    for code, kind, geometry, declared, s1, s2 in _AREAS:
        data: dict[str, Any] = {"code": code, "name": code, "area_kind": kind}
        if geometry is not None:
            data["geometry"] = geometry
        else:
            data["area_m2_declared"] = Decimal(declared or "0")
        area = await svc.create_area(pid, data, actor)
        areas[code] = area
        await svc.put_allocations(
            pid,
            area.id,
            [
                {"stage_id": stage1.id, "area_kind": s1[0], "allocated_m2": Decimal(s1[1])},
                {"stage_id": stage2.id, "area_kind": s2[0], "allocated_m2": Decimal(s2[1])},
            ],
            actor,
        )

    # Gates get load limits; laydown zones map onto the planned laydown area.
    gates = list((await session.execute(select(Gate).where(Gate.project_id == pid).order_by(Gate.name))).scalars())
    limits = (("road_gate", "44", "4.00", "3.50"), ("road_gate", "18", "4.00", "3.00"))
    for gate, (kind, gross, height, width) in zip(gates, limits, strict=False):
        if gate.max_gross_t is None:
            gate.access_kind = kind
            gate.max_gross_t = Decimal(gross)
            gate.max_axle_load_t = Decimal("11.5")
            gate.max_height_m = Decimal(height)
            gate.max_width_m = Decimal(width)
    zones = list((await session.execute(select(LaydownZone).where(LaydownZone.project_id == pid))).scalars())
    for zone in zones[:1]:
        zone.site_area_id = areas["A-LAY"].id
    await session.flush()

    # Media: power contracted at 160 kVA covers 2 x 60 + 40 kVA at 0.8 plus 10 % (140.8 kVA).
    power = await svc.create_media(
        pid,
        {
            "media_kind": "power",
            "phase": "construction",
            "provider_name": "Local grid operator",
            "connection_point": "Transformer kiosk at the north gate",
            "available_capacity": Decimal("250"),
            "contracted_capacity": Decimal("160"),
            "application_ref": "PWR-001",
            "applied_on": today - timedelta(days=60),
            "promised_on": today - timedelta(days=20),
        },
        actor,
    )
    for target in ("requested", "offered", "contracted", "connected"):
        await svc.transition_media(pid, power.id, target, actor)
    for consumer, kva in (("Tower crane 1", "60"), ("Tower crane 2", "60"), ("Site offices and welfare", "40")):
        await svc.create_demand(
            pid,
            power.id,
            {
                "stage_id": stage2.id,
                "consumer": consumer,
                "peak_demand": Decimal(kva),
                "simultaneity_factor": Decimal("0.8"),
            },
            actor,
        )
    await svc.create_demand(
        pid,
        power.id,
        {
            "stage_id": stage1.id,
            "consumer": "Site offices and welfare",
            "peak_demand": Decimal("40"),
            "simultaneity_factor": Decimal("0.8"),
        },
        actor,
    )
    water = await svc.create_media(
        pid,
        {
            "media_kind": "water",
            "provider_name": "Municipal water utility",
            "connection_point": "Hydrant south road",
            "application_ref": "WAT-014",
            "applied_on": today - timedelta(days=10),
            "promised_on": today + timedelta(days=30),
        },
        actor,
    )
    await svc.transition_media(pid, water.id, "requested", actor)
    await svc.create_demand(
        pid,
        water.id,
        {"stage_id": stage2.id, "consumer": "Concrete curing and wheel wash", "peak_demand": Decimal("6")},
        actor,
    )

    # Concept: delivery hours narrower than the gates, three flows.
    await svc.put_concept(
        pid,
        {
            "strategy": [
                {
                    "flow_code": "rebar",
                    "description": "Reinforcement, cut and bent",
                    "mode": "stock",
                    "storage_area_id": areas["A-LAY"].id,
                    "buffer_days": 5,
                },
                {
                    "flow_code": "drywall",
                    "description": "Drywall boards by floor",
                    "mode": "kanban",
                    "storage_area_id": areas["A-LAY2"].id,
                    "buffer_days": 2,
                },
                {
                    "flow_code": "precast",
                    "description": "Precast stair cores, set from the truck",
                    "mode": "direct_install",
                    "buffer_days": 0,
                },
            ],
            "delivery_open": "07:00",
            "delivery_close": "17:00",
            "max_deliveries_per_hour": 4,
            "rules_text": "Book every delivery 48 hours ahead. No waiting on the public road. Wheel wash on exit.",
        },
        actor,
    )

    # Neighbourhood: the catalogue's mixed-zone limit where the country has one, else a project value.
    limit = next((n for n in cat.noise_limits if n.zone_type == "mixed" and not n.project_value_required), None)
    hood: dict[str, Any] = {
        "zone_type": "mixed",
        "municipality_contact": "Municipal building department",
        "parking_note": "Site staff park on the leased lot east of the site.",
    }
    if limit is not None:
        hood["noise_limit_source"] = limit.code
    else:
        hood.update(
            {
                "noise_limit_source": "project",
                "day_dba": Decimal("60"),
                "night_dba": Decimal("45"),
                "quiet_hours": ["20:00", "07:00"],
            }
        )
    await svc.put_neighbourhood(pid, hood, actor)

    # Transports.
    gate = gates[0] if gates else None
    day = today + timedelta(days=21)
    heavy = await svc.create_transport(
        pid,
        {
            "direction": "inbound",
            "transport_kind": "heavy_oversize",
            "title": "Main transformer 62 t",
            "carrier_name": "Heavy haulage carrier",
            "origin": "Manufacturer works",
            "destination": "Site, north gate",
            "gate_id": gate.id if gate else None,
            "planned_window_start": datetime.combine(day, time(22, 0), tzinfo=UTC),
            "planned_window_end": datetime.combine(day + timedelta(days=1), time(4, 0), tzinfo=UTC),
            "gross_weight_t": Decimal("62"),
            "width_m": Decimal("3.20"),
            "height_m": Decimal("4.30"),
            "length_m": Decimal("22.00"),
            "escort_required": True,
            "route_notes": "Ring road, then the industrial road.",
        },
        actor,
    )
    await svc.transition_transport(pid, heavy.id, "permit_pending", actor)
    oversize = await svc.create_permit(
        pid,
        {
            "transport_id": heavy.id,
            "permit_kind": "oversize_permit",
            "authority": "Road traffic authority",
            "reference": "OS-2026-118",
            "valid_from": day - timedelta(days=3),
            "valid_to": day + timedelta(days=10),
            "allowed_windows": [{"weekdays": _EVERY_WEEKDAY, "from": "22:00", "to": "05:00"}],
        },
        actor,
    )
    night = await svc.create_permit(
        pid,
        {
            "transport_id": heavy.id,
            "permit_kind": "night_work",
            "authority": "Environmental authority",
            "reference": "NW-2026-031",
            "valid_from": day,
            "valid_to": day + timedelta(days=1),
        },
        actor,
    )
    for permit in (oversize, night):
        await svc.transition_permit(pid, permit.id, "applied", actor)
        await svc.transition_permit(pid, permit.id, "granted", actor)
    # 62 t through a 44 t gate: the granted oversize permit covers this transport and
    # this window, so the gate limit is lifted for it and it can hold its slot.
    await svc.transition_transport(pid, heavy.id, "scheduled", actor)
    await svc.create_transport(
        pid,
        {
            "direction": "outbound",
            "transport_kind": "outbound_spoil",
            "title": "Excavated soil to the licensed tip",
            "carrier_name": "Earthworks haulier",
            "origin": "Site",
            "destination": "Licensed soil tip",
            "gate_id": gate.id if gate else None,
            "planned_window_start": datetime.combine(today + timedelta(days=2), time(8, 0), tzinfo=UTC),
            "planned_window_end": datetime.combine(today + timedelta(days=2), time(15, 0), tzinfo=UTC),
            "gross_weight_t": Decimal("32"),
        },
        actor,
    )
    rebar = await svc.create_transport(
        pid,
        {
            "direction": "inbound",
            "transport_kind": "inbound_delivery",
            "title": "Reinforcement, first floor slab",
            "carrier_name": "Steel supplier transport",
            "origin": "Rebar yard",
            "destination": "Laydown A",
            "gate_id": gate.id if gate else None,
            "planned_window_start": datetime.combine(today + timedelta(days=4), time(9, 0), tzinfo=UTC),
            "planned_window_end": datetime.combine(today + timedelta(days=4), time(10, 0), tzinfo=UTC),
            "gross_weight_t": Decimal("24"),
        },
        actor,
    )
    await svc.transition_transport(pid, rebar.id, "scheduled", actor)

    # Customs: imported switchgear under FCA, the buyer (us) clears import. Values are
    # in the project's currency; a project without one gets the case without values.
    from app.modules.projects.models import Project

    currency = (await session.execute(select(Project.currency).where(Project.id == pid))).scalar_one_or_none() or None
    case = await svc.create_customs(
        pid,
        {
            "direction": "import",
            "title": "Medium voltage switchgear",
            "incoterm": "FCA",
            "named_place": "Manufacturer works, loading dock",
            "transport_mode": "road",
            "country_of_origin": "CH",
            "declarant_party": "buyer",
            "broker_name": "Customs broker",
            **({"customs_value": Decimal("184500.00"), "currency": currency} if currency else {}),
        },
        actor,
        can_see_values=True,
    )
    for desc, hs, qty, value in (
        ("Switchgear panels, 24 kV", "853720", "6", "171000.00"),
        ("Control cabinets", "853710", "2", "13500.00"),
    ):
        await svc.create_line(
            pid,
            case.id,
            {
                "description": desc,
                "hs_code": hs,
                "quantity": Decimal(qty),
                "unit": "pcs",
                **({"value": Decimal(value), "currency": currency} if currency else {}),
                "origin_country": "CH",
            },
            actor,
            can_see_values=True,
        )
    for doc in await svc.documents(pid, case.id):
        if doc.kind in ("commercial_invoice", "packing_list"):
            await svc.update_document(pid, doc.id, {"document_ref": f"CDE-{doc.kind}", "state": "received"}, actor)

    # Complaints and coordination.
    dust = await svc.create_complaint(
        pid,
        {
            "kind": "dust",
            "reported_on": today - timedelta(days=6),
            "reporter": "Neighbour, anonymous",
            "description": "Dust on parked cars on the east side after excavation.",
        },
        actor,
    )
    await svc.transition_complaint(pid, dust.id, "acknowledged", actor)
    await svc.update_complaint(
        pid, dust.id, {"response": "Water spraying twice a day; wheel wash moved to the exit."}, actor
    )
    await svc.transition_complaint(pid, dust.id, "action_taken", actor)
    await svc.create_complaint(
        pid,
        {
            "kind": "noise",
            "reported_on": today - timedelta(days=1),
            "description": "Reversing alarms before 07:00 at the north gate.",
        },
        actor,
    )
    await svc.create_coordination(
        pid,
        {
            "entry_date": today - timedelta(days=9),
            "body": "municipality",
            "topic": "Road occupancy for the crane base",
            "outcome": "Agreed in principle; written application to follow.",
            "next_action_due": today + timedelta(days=5),
        },
        actor,
    )
    await svc.create_coordination(
        pid,
        {
            "entry_date": today - timedelta(days=2),
            "body": "utility",
            "topic": "Water connection date",
            "outcome": "Utility confirmed the connection in four weeks.",
        },
        actor,
    )
    await session.flush()
    return 3
