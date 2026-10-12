# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site Logistics event topics.

Events are published best-effort via ``event_bus.publish_detached`` from the
service layer so other modules (notifications, dashboards, field team) can react
to delivery activity without importing the site-logistics ORM.

    site_logistics.delivery.booked    - a new delivery was booked
    site_logistics.delivery.approved  - a delivery was approved and holds its slot
    site_logistics.delivery.rejected  - a delivery was declined

Logistics plan topics, published after commit (``publish_after_commit``):

    site_logistics.area_balance.changed      - allocations of a stage changed
    site_logistics.media.short               - a stage needs more than is contracted
    site_logistics.transport.state_changed   - a transport moved in its lifecycle
    site_logistics.permit.expiring           - a permit runs out while transports remain
    site_logistics.permit.expired            - a permit ran out
    site_logistics.customs.cleared           - a customs case was cleared
    site_logistics.customs.held              - a customs case is held
    site_logistics.neighbour_issue.overdue   - a complaint passed its response date unanswered
"""

from __future__ import annotations

DELIVERY_BOOKED = "site_logistics.delivery.booked"
DELIVERY_APPROVED = "site_logistics.delivery.approved"
DELIVERY_REJECTED = "site_logistics.delivery.rejected"

AREA_BALANCE_CHANGED = "site_logistics.area_balance.changed"
MEDIA_SHORT = "site_logistics.media.short"
TRANSPORT_STATE_CHANGED = "site_logistics.transport.state_changed"
PERMIT_EXPIRING = "site_logistics.permit.expiring"
PERMIT_EXPIRED = "site_logistics.permit.expired"
CUSTOMS_CLEARED = "site_logistics.customs.cleared"
CUSTOMS_HELD = "site_logistics.customs.held"
NEIGHBOUR_ISSUE_OVERDUE = "site_logistics.neighbour_issue.overdue"
