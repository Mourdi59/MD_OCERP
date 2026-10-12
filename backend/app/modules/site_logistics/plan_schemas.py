# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request bodies of the logistics plan API (``/projects/{project_id}/...``).

Create and patch bodies share one model per entity; the router sends
``model_dump(exclude_unset=True)`` so a patch only touches the keys it carries.
Quantities and money arrive as Decimal (a JSON number or string); a float is
never stored because Pydantic parses the decimal from the JSON text. Catalogue
codes (area kind, media kind, permit kind ...) are checked by the service
against the project's pinned catalogue, not here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
_CODE = r"^[a-z0-9][a-z0-9_]*$"


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TransitionIn(_In):
    target: str = Field(min_length=1, max_length=30)


class CataloguePinIn(_In):
    source: Literal["shipped", "tenant"] = "shipped"
    catalogue_id: str = Field(min_length=1, max_length=64)
    version: int | None = Field(default=None, ge=1)


class StageIn(_In):
    code: str | None = Field(default=None, pattern=_CODE, max_length=40)
    title: str | None = Field(default=None, max_length=255)
    ordinal: int | None = Field(default=None, ge=0, le=999)
    from_activity_id: uuid.UUID | None = None
    to_activity_id: uuid.UUID | None = None
    from_date: date | None = None
    to_date: date | None = None


class AreaIn(_In):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=255)
    area_kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    geometry: dict[str, Any] | None = None
    frame: Literal["local", "wgs84"] | None = None
    area_m2_declared: Decimal | None = Field(default=None, ge=0)
    geo_overlay_id: uuid.UUID | None = None
    takt_location_id: uuid.UUID | None = None
    owner_party: str | None = Field(default=None, max_length=255)


class AllocationItem(_In):
    stage_id: uuid.UUID
    area_kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    allocated_m2: Decimal | None = Field(default=None, ge=0)
    use_note: str | None = Field(default=None, max_length=2000)


class AllocationsPut(_In):
    items: list[AllocationItem] = Field(default_factory=list, max_length=100)


class MediaIn(_In):
    media_kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    phase: Literal["construction", "operation", "both"] | None = None
    provider_name: str | None = Field(default=None, max_length=255)
    provider_vendor_id: uuid.UUID | None = None
    connection_point: str | None = Field(default=None, max_length=2000)
    connection_point_geometry: dict[str, Any] | None = None
    capacity_unit: str | None = Field(default=None, max_length=20)
    available_capacity: Decimal | None = Field(default=None, ge=0)
    contracted_capacity: Decimal | None = Field(default=None, ge=0)
    application_ref: str | None = Field(default=None, max_length=120)
    applied_on: date | None = None
    promised_on: date | None = None
    connected_on: date | None = None
    document_ref: str | None = Field(default=None, max_length=120)


class DemandIn(_In):
    media_connection_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    consumer: str | None = Field(default=None, max_length=255)
    plant_item_id: uuid.UUID | None = None
    peak_demand: Decimal | None = Field(default=None, ge=0)
    simultaneity_factor: Decimal | None = Field(default=None, ge=0, le=1)


class PlantDemandIn(_In):
    """Rule 9 hook: the plant position save path sends its power demand here."""

    site_plant_position_id: uuid.UUID
    power_demand_kva: Decimal | None = Field(default=None, ge=0)
    stage_id: uuid.UUID | None = None
    consumer: str = Field(default="", max_length=255)


class FlowIn(_In):
    flow_code: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=2000)
    mode: Literal["stock", "just_in_time", "kanban", "direct_install"] = "stock"
    storage_area_id: uuid.UUID | None = None
    takt_schedule_id: uuid.UUID | None = None
    buffer_days: int = Field(default=0, ge=0, le=365)


class ConceptIn(_In):
    strategy: list[FlowIn] | None = Field(default=None, max_length=200)
    delivery_open: str | None = Field(default=None, pattern=_HHMM)
    delivery_close: str | None = Field(default=None, pattern=_HHMM)
    max_deliveries_per_hour: int | None = Field(default=None, ge=1, le=500)
    rules_text: str | None = Field(default=None, max_length=20000)
    document_ref: str | None = Field(default=None, max_length=120)


class TransportIn(_In):
    direction: Literal["inbound", "outbound"] | None = None
    transport_kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    title: str | None = Field(default=None, max_length=255)
    carrier_name: str | None = Field(default=None, max_length=255)
    origin: str | None = Field(default=None, max_length=255)
    destination: str | None = Field(default=None, max_length=255)
    gate_id: uuid.UUID | None = None
    planned_window_start: datetime | None = None
    planned_window_end: datetime | None = None
    po_id: uuid.UUID | None = None
    plant_item_id: uuid.UUID | None = None
    waste_record_ref: str | None = Field(default=None, max_length=120)
    customs_case_id: uuid.UUID | None = None
    axle_load_t: Decimal | None = Field(default=None, ge=0)
    gross_weight_t: Decimal | None = Field(default=None, ge=0)
    height_m: Decimal | None = Field(default=None, ge=0)
    width_m: Decimal | None = Field(default=None, ge=0)
    length_m: Decimal | None = Field(default=None, ge=0)
    turning_radius_m: Decimal | None = Field(default=None, ge=0)
    route_geojson: dict[str, Any] | None = None
    route_notes: str | None = Field(default=None, max_length=5000)
    escort_required: bool | None = None


class WindowIn(_In):
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), max_length=7)
    from_: str = Field(alias="from", pattern=_HHMM)
    to: str = Field(pattern=_HHMM)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PermitIn(_In):
    transport_id: uuid.UUID | None = None
    covers_transport_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)
    permit_kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    authority: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=120)
    applied_on: date | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    allowed_windows: list[WindowIn] | None = Field(default=None, max_length=50)
    conditions: str | None = Field(default=None, max_length=10000)
    route_geojson: dict[str, Any] | None = None
    document_ref: str | None = Field(default=None, max_length=120)
    authority_permit_id: uuid.UUID | None = None

    def payload(self) -> dict[str, Any]:
        data = self.model_dump(exclude_unset=True)
        if self.allowed_windows is not None:
            data["allowed_windows"] = [w.model_dump(by_alias=True) for w in self.allowed_windows]
        return data


class CustomsIn(_In):
    direction: Literal["import", "export"] | None = None
    title: str | None = Field(default=None, max_length=255)
    incoterm: str | None = Field(default=None, min_length=3, max_length=3)
    named_place: str | None = Field(default=None, max_length=255)
    transport_mode: str | None = Field(default=None, max_length=20)
    country_of_origin: str | None = Field(default=None, min_length=2, max_length=2)
    country_of_destination: str | None = Field(default=None, min_length=2, max_length=2)
    declarant_party: Literal["buyer", "seller"] | None = None
    broker_name: str | None = Field(default=None, max_length=255)
    customs_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    declaration_ref: str | None = Field(default=None, max_length=120)
    cleared_on: date | None = None
    po_id: uuid.UUID | None = None


class LineIn(_In):
    description: str | None = Field(default=None, max_length=2000)
    hs_code: str | None = Field(default=None, min_length=2, max_length=14)
    commodity_code_id: uuid.UUID | None = None
    quantity: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=20)
    net_mass_kg: Decimal | None = Field(default=None, ge=0)
    value: Decimal | None = Field(default=None, ge=0)
    origin_country: str | None = Field(default=None, min_length=2, max_length=2)
    preferential_origin: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class DocumentIn(_In):
    document_ref: str | None = Field(default=None, max_length=120)
    state: Literal["missing", "received", "verified"] | None = None


class DocumentAddIn(_In):
    kind: str = Field(pattern=_CODE, max_length=40)


class NeighbourhoodIn(_In):
    zone_type: Literal["residential", "mixed", "industrial"] | None = None
    noise_limit_source: str | None = Field(default=None, max_length=64)
    day_dba: Decimal | None = Field(default=None, ge=0, le=200)
    night_dba: Decimal | None = Field(default=None, ge=0, le=200)
    quiet_hours: list[str] | None = Field(default=None, min_length=2, max_length=2)
    site_traffic_routes: dict[str, Any] | None = None
    parking_note: str | None = Field(default=None, max_length=5000)
    municipality_contact: str | None = Field(default=None, max_length=255)
    correspondence_thread_id: uuid.UUID | None = None


class ComplaintIn(_In):
    kind: str | None = Field(default=None, pattern=_CODE, max_length=40)
    reported_on: date | None = None
    reporter: str | None = Field(default=None, max_length=255)
    location: dict[str, Any] | None = None
    description: str | None = Field(default=None, max_length=10000)
    transport_id: uuid.UUID | None = None
    delivery_id: uuid.UUID | None = None
    response: str | None = Field(default=None, max_length=10000)
    response_due: date | None = None
    owner_user_id: uuid.UUID | None = None


class CoordinationIn(_In):
    entry_date: date | None = None
    body: Literal["municipality", "utility", "police", "neighbours", "authority", "other"] | None = None
    topic: str | None = Field(default=None, max_length=255)
    outcome: str | None = Field(default=None, max_length=10000)
    next_action_due: date | None = None
    correspondence_id: uuid.UUID | None = None


class SweepIn(_In):
    """No fields: the sweep runs on the server's date."""
