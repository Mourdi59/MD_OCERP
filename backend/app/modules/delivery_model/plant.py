# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The plant item an owner-furnished item may also be.

An owner-furnished item can be a thing the plant register holds too. Then the
register owns its enquiry date, its lead time and its latest order date, and
this module shows those instead of its own columns. The item's own columns are
for a thing the register does not hold.

The link is a soft id, checked against the project through the register's read
port and never through its tables. The register is an optional module: without
it nothing can be linked and every item keeps its own figures.

This is the only file of the module that reads the plant register.
"""

from __future__ import annotations

import importlib
import uuid
from datetime import date
from typing import Any

# What ``dates_source`` of an item view says.
OWN = "own"
REGISTER = "plant_register"


# Routes of the register under which a plant item has an owner-furnished item here (its ``needs_ofi``),
# and the item states in which the register still lets a route change. Both are the register's words; a
# test compares them with the register when it is installed.
OFI_ROUTES = ("owner_furnished_contractor_installed", "owner_furnished_owner_installed", "owner_procured_novated")
ROUTE_OPEN_STATES = ("identified", "specified", "enquired", "route_set")
CONTRACTOR_INSTALLS = "owner_furnished_contractor_installed"
OWNER_INSTALLS = "owner_furnished_owner_installed"


def keeps_owner_furnished_item(dates: Any | None) -> bool:
    """Does the register say this plant item is supplied by the owner?"""
    return dates is not None and dates.procurement_route in OFI_ROUTES


def route_open(dates: Any | None) -> bool:
    """May the route of this plant item still be changed in the register?"""
    return dates is not None and dates.status in ROUTE_OPEN_STATES


def item_code(register_code: str | None, plant_item_id: uuid.UUID, taken: set[str]) -> str:
    """The code of the owner-furnished item the register asks for: its own code, made unique here."""
    stem = "".join(c if c.isalnum() or c in "_.-" else "-" for c in (register_code or plant_item_id.hex[:8]))
    base = f"OFI-{stem}"[:56]
    code, n = base, 1
    while code in taken:
        n += 1
        code = f"{base}-{n}"
    return code


async def set_owner_furnished_route(
    session: Any,
    project_id: uuid.UUID,
    plant_item_id: uuid.UUID,
    *,
    installer_package_id: uuid.UUID | None,
    actor_id: uuid.UUID,
) -> str | None:
    """Have the register record that the owner supplies this plant item; ``None`` when done, else its refusal code.

    The register's own write: it asks this module's package plan provider for
    the owner-furnished item, checks the route against the plan and stores the
    link on its side. Nothing is written here when it refuses.
    """
    try:
        service = importlib.import_module("app.modules.plant_register.service")
        errors = importlib.import_module("app.modules.plant_register.errors")
    except ImportError:
        return "plant_register_unavailable"
    route = CONTRACTOR_INSTALLS if installer_package_id is not None else OWNER_INSTALLS
    try:
        async with session.begin_nested():
            await service.PlantService(session).set_route(
                project_id, plant_item_id, route=route, contract_package_id=installer_package_id, actor_id=actor_id
            )
    except errors.PlantError as exc:
        return exc.code
    return None


def _reads() -> Any | None:
    """The register's read port, or ``None`` when the module is not installed."""
    # By its full name, so a register that is not installed is an ImportError and nothing else is touched.
    try:
        return importlib.import_module("app.modules.plant_register.reads")
    except ImportError:
        return None


def installed() -> bool:
    return _reads() is not None


async def plant_item_dates(
    session: Any, project_id: uuid.UUID, plant_item_id: uuid.UUID, *, today: date | None = None
) -> Any | None:
    """The register's dates of one plant item of this project.

    ``None`` when the register is not installed, and when it knows no such item
    in this project (an item of another project reads exactly like a missing one).
    """
    reads = _reads()
    if reads is None:
        return None
    return await reads.plant_item_dates(session, project_id, plant_item_id, today=today)


async def plant_item_id_by_code(session: Any, project_id: uuid.UUID, code: str) -> uuid.UUID | None:
    """The plant item of this project with that register code, if the register has one."""
    lookup = getattr(_reads(), "plant_item_id_by_code", None)
    if lookup is None:
        return None
    return await lookup(session, project_id, code)


def _iso(day: date | None) -> str | None:
    return day.isoformat() if day is not None else None


def with_dates(view: dict[str, Any], dates: Any | None) -> dict[str, Any]:
    """The item view with the figures that are in force and where they come from.

    Unlinked: the item's own figures. Linked and held by the register: the
    register's enquiry date, lead time and latest order date, also where the
    register has none (an item it holds is not described twice). Linked and not
    answered by the register: the item's own figures, and ``missing`` says so.
    """
    linked = view.get("plant_item_id") is not None
    out = dict(view)
    if not linked:
        out.update(plant_item=None, dates_source=OWN, latest_order_date=None)
        return out
    if dates is None:
        out.update(plant_item={"code": None, "missing": True}, dates_source=OWN, latest_order_date=None)
        return out
    out.update(
        plant_item={"code": dates.code, "missing": False},
        dates_source=REGISTER,
        enquiry_date=_iso(dates.enquiry_date),
        lead_time_days=dates.lead_time_days,
        latest_order_date=_iso(dates.latest_order_date),
    )
    return out
