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

Logistics plan (framework module 6, extension of 2026-10-12): expansion stages
with an area balance per stage, gate load limits, utility connections with a
demand-versus-capacity balance, the logistics concept aligned to takt, inbound
and outbound transports with their permits and time windows, customs data
(incoterm, HS codes, documents) and the neighbourhood (noise limits, quiet
hours, complaints, coordination). Its approved state is the governance frame
document tagged for logistics in the project's governance catalogue; national
figures are catalogue data (kind site_logistics).
"""


async def on_startup() -> None:
    """Module startup hook - register permissions, rules, the catalogue kind, gate evidence and the daily sweep."""
    from app.modules.site_logistics.catalogue import register_kind
    from app.modules.site_logistics.evidence import register_gate_evidence
    from app.modules.site_logistics.permissions import (
        register_site_logistics_permissions,
    )
    from app.modules.site_logistics.sweep import register_sweep_process
    from app.modules.site_logistics.validators import (
        register_site_logistics_validation_rules,
    )

    register_site_logistics_permissions()
    register_site_logistics_validation_rules()
    register_kind()
    register_gate_evidence()
    register_sweep_process()
