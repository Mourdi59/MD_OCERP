# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo plant register for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the register an owner's engineer would actually keep
before letting the packages: eight items across electrical, mechanical,
conveying, user and operating equipment, each with dated lead time quotes
(enquiry date, who answered, from what basis), need dates, delivery limits for
the main components, a spares concept, a held capacity slot for the
transformer, a decision paper in draft for the switchgear and the
construction-phase IT services. Supplier names are generic descriptions, never
company names. Dates are relative to today so float and overdue chips mean
something whenever the demo is recorded.

Procurement routes are left unset: a route is only accepted against the
project's package plan (rule 10), and the demo does not invent one.

Only projects carrying the demo marker are touched; a project that already has
plant items is skipped, so a re-run never duplicates.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# code, title, class, quantity, redundancy, critical override, need offset days,
# quotes [(source, source_name, enquiry offset, response offset, min, max, basis)]
_ITEMS: list[dict[str, Any]] = [
    {
        "code": "PL-001",
        "title": "Main power transformer 20/0.4 kV, 2500 kVA",
        "class": "power_transformer",
        "quantity": "2",
        "redundancy": "N+1",
        "need_days": 760,
        "performance": [
            {"key": "rated_power", "value": "2500", "unit": "kVA"},
            {"key": "voltage_ratio", "value": "20/0.4", "unit": "kV"},
            {"key": "losses_class", "value": "Ecodesign tier 2", "unit": ""},
        ],
        "quotes": [
            ("market_sounding", "Market sounding, three transformer manufacturers", -120, -105, 90, 128, "from_order"),
            ("supplier_quote", "Transformer manufacturer A (budget quote)", -40, -26, 96, 110, "from_order"),
        ],
        "slot": True,
        "spares": [("strategic_spares", "Spare bushing set and tap changer contacts", "1", "set")],
    },
    {
        "code": "PL-002",
        "title": "Medium voltage switchgear, 12 panels",
        "class": "mv_switchgear",
        "quantity": "1",
        "redundancy": "",
        "need_days": 700,
        "performance": [
            {"key": "rated_voltage", "value": "24", "unit": "kV"},
            {"key": "short_circuit_rating", "value": "20", "unit": "kA 1s"},
        ],
        "quotes": [
            ("supplier_quote", "Switchgear manufacturer A", -60, -46, 52, 60, "from_order"),
            ("supplier_quote", "Switchgear manufacturer B", -55, -38, 40, 44, "from_approved_drawings"),
        ],
        "paper": True,
        "spares": [
            ("strategic_spares", "Spare circuit breaker truck", "1", "pcs"),
            ("special_tools", "Racking and earthing tools", "1", "set"),
        ],
    },
    {
        "code": "PL-003",
        "title": "Standby diesel generator set 1250 kVA",
        "class": "generator",
        "quantity": "2",
        "redundancy": "N+1",
        "need_days": 520,
        "performance": [{"key": "prime_power", "value": "1250", "unit": "kVA"}],
        "quotes": [("supplier_quote", "Generator packager (budget quote)", -30, -18, 40, 48, "from_order")],
        "spares": [("operating_consumables", "Filters and belts for first two services", "2", "set")],
    },
    {
        "code": "PL-004",
        "title": "Water-cooled chiller 1.2 MW",
        "class": "chiller",
        "quantity": "3",
        "redundancy": "N+1",
        "need_days": 430,
        "performance": [{"key": "cooling_capacity", "value": "1200", "unit": "kW"}],
        "quotes": [("expert_estimate", "Owner's engineer estimate", -15, None, 26, 34, "from_order")],
        "spares": [],
    },
    {
        "code": "PL-005",
        "title": "Passenger lifts, 1600 kg, 8 stops",
        "class": "lift",
        "quantity": "4",
        "redundancy": "",
        "need_days": 330,
        "performance": [{"key": "rated_load", "value": "1600", "unit": "kg"}],
        "quotes": [
            ("historic_order", "Previous order on a comparable building", -200, -200, 28, 36, "from_approved_drawings")
        ],
        "spares": [("commissioning_spares", "Door operator spares", "1", "set")],
    },
    {
        "code": "PL-006",
        "title": "UPS system 2 x 800 kVA",
        "class": "ups",
        "quantity": "2",
        "redundancy": "2N",
        "need_days": 150,
        "performance": [{"key": "autonomy", "value": "10", "unit": "min"}],
        "quotes": [("supplier_quote", "UPS manufacturer (firm quote)", -70, -60, 20, 24, "from_order")],
        "spares": [("strategic_spares", "Spare power module", "1", "pcs")],
    },
    {
        "code": "PL-007",
        "title": "Commercial kitchen equipment, staff restaurant",
        "class": "kitchen_equipment",
        "quantity": "1",
        "redundancy": "",
        "need_days": 600,
        "performance": [{"key": "covers_per_day", "value": "450", "unit": ""}],
        "quotes": [],
        "spares": [],
    },
    {
        "code": "PL-008",
        "title": "Core network switches and fibre backbone",
        "class": "it_core_network",
        "quantity": "2",
        "redundancy": "N+1",
        "need_days": 480,
        "performance": [{"key": "uplink", "value": "100", "unit": "Gbit/s"}],
        "quotes": [("market_sounding", "Distributor price list", -10, -10, 10, 14, "from_order")],
        "spares": [("strategic_spares", "Spare line card and optics", "1", "set")],
    },
]

_LIMITS_MAIN = {
    "supply": "supplier",
    "deliver_to_site": "supplier",
    "offload": "contractor",
    "set_in_place": "contractor",
    "connect": "contractor",
    "test": "supplier",
    "commission": "supplier",
    "accept": "owner",
    "train": "supplier",
    "document": "supplier",
}


async def seed_plant_register_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the register of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.plant_register.models import PlantItem
    from app.modules.projects.models import Project

    totals = {"projects": 0, "items": 0, "quotes": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (
        await session.execute(select(Project.id, Project.metadata_, Project.owner_id).where(Project.id.in_(ids)))
    ).all()
    for pid, meta, owner in rows:
        if not demo_id_of(meta):
            continue
        has = (
            await session.execute(select(PlantItem.id).where(PlantItem.project_id == pid).limit(1))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid, owner)
        except Exception:
            logger.warning("plant_register demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _seed_project(session: AsyncSession, project_id: uuid.UUID, owner: uuid.UUID | None) -> dict[str, int]:
    from app.modules.plant_register.service import PlantService

    svc = PlantService(session)
    today = datetime.now(UTC).date()
    actor = owner or uuid.UUID(int=0)
    counts = {"items": 0, "quotes": 0}
    for spec in _ITEMS:
        item = await svc.create_item(
            project_id,
            {
                "code": spec["code"],
                "title": spec["title"],
                "component_class_code": spec["class"],
                "quantity": Decimal(spec["quantity"]),
                "unit": "pcs",
                "redundancy_scheme": spec["redundancy"],
                "performance": spec["performance"],
                "need_date_fixed": today + timedelta(days=spec["need_days"]),
                "owner_user_id": owner,
            },
            actor_id=actor,
        )
        counts["items"] += 1
        for source, name, enq, resp, lo, hi, basis in spec["quotes"]:
            await svc.add_quote(
                project_id,
                item.id,
                {
                    "source": source,
                    "source_name": name,
                    "enquiry_date": today + timedelta(days=enq),
                    "response_date": today + timedelta(days=resp) if resp is not None else None,
                    "lead_weeks_min": lo,
                    "lead_weeks_max": hi,
                    "lead_basis": basis,
                    "set_basis": True,
                },
                actor_id=actor,
                today=today,
            )
            counts["quotes"] += 1
        if item.item_class == "main_component" and spec["code"] in ("PL-001", "PL-002", "PL-003"):
            await svc.put_limits(
                project_id, item.id, [{"step": k, "party": v} for k, v in _LIMITS_MAIN.items()], actor_id=actor
            )
        for category, text, qty, unit in spec["spares"]:
            await svc.create_spare(
                project_id,
                item.id,
                {
                    "category": category,
                    "description": text,
                    "quantity": Decimal(qty),
                    "unit": unit,
                    "supply_by": "supplier",
                },
                actor_id=actor,
            )
        if spec["spares"] or spec["quotes"]:
            await svc.transition_item(project_id, item.id, "specified", actor_id=actor, today=today)
        if spec["quotes"]:
            await svc.transition_item(project_id, item.id, "enquired", actor_id=actor, today=today)
        if spec.get("slot"):
            await svc.create_slot(
                project_id,
                item.id,
                {
                    "vendor_name": "Transformer manufacturer A",
                    "slot_from": today + timedelta(days=300),
                    "slot_to": today + timedelta(days=360),
                    "reservation_fee": Decimal("25000.00"),
                    "currency": "EUR",
                    "fee_refundable": "none",
                    "fee_credited_to_order": True,
                    "convert_by_date": today + timedelta(days=45),
                    "terms": "Fee non-refundable, credited in full to the order if signed by the conversion date.",
                },
                actor_id=actor,
            )
        if spec.get("paper"):
            await svc.create_paper(
                project_id,
                item.id,
                {
                    "question": "Which switchgear offer secures the energisation date at acceptable risk?",
                    "criteria": [
                        {"code": "lead_time", "title": "Lead time", "weight": "4"},
                        {"code": "cost", "title": "Cost", "weight": "3"},
                        {"code": "service", "title": "Local service", "weight": "2"},
                    ],
                    "options": [
                        {
                            "code": "a",
                            "title": "Manufacturer A, from order",
                            "lead_weeks": 60,
                            "scores": {"lead_time": "2", "cost": "4", "service": "4"},
                        },
                        {
                            "code": "b",
                            "title": "Manufacturer B, from approved drawings",
                            "lead_weeks": 44,
                            "scores": {"lead_time": "4", "cost": "3", "service": "3"},
                        },
                    ],
                    "recommendation": "b",
                    "rationale": "Option B gains about four months on the energisation path; the drawing review is planned.",
                },
                actor_id=actor,
            )
    for kind, desc, start in (
        ("cde_access", "Common data environment access for all design and site parties", -30),
        ("site_network", "Site office network and wireless coverage", 60),
        ("access_control", "Turnstiles and badge system at the site gates", 60),
        ("drone_survey", "Monthly drone survey of earthworks and structure", 90),
    ):
        await svc.create_it_service(
            project_id,
            {"kind": kind, "description": desc, "needed_from": today + timedelta(days=start)},
            actor_id=actor,
        )
    await _seed_site_plant(session, project_id, today)
    return counts


async def _seed_site_plant(session: AsyncSession, project_id: uuid.UUID, today: date) -> None:
    from app.modules.site_logistics.models import SitePlantPosition

    has = (
        await session.execute(select(SitePlantPosition.id).where(SitePlantPosition.project_id == project_id).limit(1))
    ).scalar_one_or_none()
    if has is not None:
        return
    for kind, name, x, y, reach, load in (
        ("tower_crane", "Tower crane 1", "42.0", "28.5", "60.00", "8.00"),
        ("mobile_crane_pad", "Crane pad for transformer delivery", "12.0", "64.0", "35.00", "120.00"),
        ("site_office", "Site office and meeting containers", "5.0", "5.0", None, None),
        ("temporary_power", "Temporary power distribution", "8.0", "12.0", None, None),
    ):
        session.add(
            SitePlantPosition(
                project_id=project_id,
                kind=kind,
                name=name,
                x=Decimal(x),
                y=Decimal(y),
                reach_m=Decimal(reach) if reach else None,
                max_load_t=Decimal(load) if load else None,
                from_date=today,
                to_date=today + timedelta(days=720),
                note="",
            )
        )
    await session.flush()
