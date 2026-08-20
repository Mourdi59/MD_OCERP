# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics & Delivery module.

Plan and control what arrives on site:
    - Access gates with daily operating hours and per-slot capacity
    - Material laydown / storage zones
    - Delivery booking board with approve/reject scheduling
    - Delivery lines pointing at the BOQ positions the load delivers

Delivery windows are validated against gate hours, and two approved deliveries
on one gate can never overlap.

The bill is the source of truth for what is being delivered: a booking carries
lines that reference BOQ positions rather than re-describing the work, so the
board can show, per estimate line, what is booked, what has arrived and what is
still outstanding.
"""


async def on_startup() -> None:
    """Module startup hook - register permissions and validation rules."""
    from app.modules.site_logistics.permissions import (
        register_site_logistics_permissions,
    )
    from app.modules.site_logistics.validators import (
        register_site_logistics_validation_rules,
    )

    register_site_logistics_permissions()
    register_site_logistics_validation_rules()
