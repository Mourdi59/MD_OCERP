# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""site_logistics extension - the logistics plan of framework module 6.

Fifteen new project-scoped tables (stages, areas and allocations, utility
connections and demands, the logistics concept, transports and their permits,
customs cases with lines and documents, the neighbourhood plan, complaints and
the coordination log), all CASCADE with the project.

Three existing tables get NULLABLE columns only (no rename, no removal, no data
rewrite): ``oe_site_logistics_gate`` (access kind and load limits),
``oe_site_logistics_laydown_zone`` (``site_area_id``, FK SET NULL) and
``oe_site_logistics_delivery`` (``transport_id`` FK SET NULL, ``direction`` with a
server default, ``gross_weight_t``, soft ``plant_item_id`` / ``takt_location_id``).

The plant position table ``oe_site_logistics_plant_position`` belongs to the plant
register revision (module 5) and is not touched here.

Every constraint and index name is written out and matches the model. Every step
is inspector-guarded, so a database whose tables ``create_all`` already built
reaches this revision and only adds what is missing.

Revision ID: v78_site_logistics_ext
Revises: v68_project_governance
Create Date: 2026-10-12
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v78_site_logistics_ext"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"
_STAGE = "oe_site_logistics_stage.id"
_AREA = "oe_site_logistics_area.id"
_MEDIA = "oe_site_logistics_media.id"
_TRANSPORT = "oe_site_logistics_transport.id"
_PERMIT = "oe_site_logistics_transport_permit.id"
_CASE = "oe_site_logistics_customs_case.id"
_GATE = "oe_site_logistics_gate.id"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _project_fk(name: str) -> sa.Column:
    return sa.Column("project_id", GUID(), sa.ForeignKey(_PROJECT, ondelete="CASCADE", name=name), nullable=False)


def _fk(column: str, target: str, name: str, *, ondelete: str = "CASCADE", nullable: bool = False) -> sa.Column:
    return sa.Column(column, GUID(), sa.ForeignKey(target, ondelete=ondelete, name=name), nullable=nullable)


def _str(name: str, length: int, default: str | None = "") -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=False)
    return sa.Column(name, sa.String(length=length), nullable=False, server_default=default)


def _nstr(name: str, length: int) -> sa.Column:
    return sa.Column(name, sa.String(length=length), nullable=True)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=str(default))


def _num(name: str, precision: int, scale: int, nullable: bool = True, default: str | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Numeric(precision, scale), nullable=nullable)
    return sa.Column(name, sa.Numeric(precision, scale), nullable=nullable, server_default=default)


def _money(name: str) -> sa.Column:
    return sa.Column(name, MoneyType(18, 2), nullable=True)


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _date(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str, nullable: bool = False, default: str | None = "[]") -> sa.Column:
    if nullable:
        return sa.Column(name, sa.JSON(), nullable=True)
    return sa.Column(name, sa.JSON(), nullable=False, server_default=default)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_site_logistics_stage",
        lambda: [
            _project_fk("fk_oe_site_stage_project"),
            _str("code", 40, None),
            _str("title", 255),
            _int("ordinal", 0),
            _guid("from_activity_id"),
            _guid("to_activity_id"),
            _date("from_date"),
            _date("to_date"),
            _str("state", 20, "planned"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_site_stage_code"),
        ],
        [("ix_oe_site_stage_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_area",
        lambda: [
            _project_fk("fk_oe_site_area_project"),
            _str("code", 40, None),
            _str("name", 255),
            _str("area_kind", 40, None),
            _json("geometry", nullable=True),
            _str("frame", 10, "local"),
            _num("area_m2", 14, 2),
            _num("area_m2_declared", 14, 2),
            _guid("geo_overlay_id"),
            _guid("takt_location_id"),
            _str("owner_party", 255),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_site_area_code"),
        ],
        [("ix_oe_site_area_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_area_allocation",
        lambda: [
            _project_fk("fk_oe_site_alloc_project"),
            _fk("site_area_id", _AREA, "fk_oe_site_alloc_area"),
            _fk("stage_id", _STAGE, "fk_oe_site_alloc_stage"),
            _str("area_kind", 40, None),
            _num("allocated_m2", 14, 2, nullable=False, default="0"),
            _text("use_note"),
            sa.UniqueConstraint("site_area_id", "stage_id", name="uq_oe_site_alloc_area_stage"),
        ],
        [("ix_oe_site_alloc_project_stage", ["project_id", "stage_id"])],
    ),
    (
        "oe_site_logistics_media",
        lambda: [
            _project_fk("fk_oe_site_media_project"),
            _str("media_kind", 40, None),
            _str("phase", 20, "construction"),
            _str("provider_name", 255),
            _guid("provider_vendor_id"),
            _text("connection_point"),
            _json("connection_point_geometry", nullable=True),
            _str("capacity_unit", 20),
            _num("available_capacity", 14, 3),
            _num("contracted_capacity", 14, 3),
            _str("application_ref", 120),
            _date("applied_on"),
            _date("promised_on"),
            _date("connected_on"),
            _nstr("document_ref", 120),
            _str("state", 20, "identified"),
        ],
        [("ix_oe_site_media_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_media_demand",
        lambda: [
            _project_fk("fk_oe_site_demand_project"),
            _fk("media_connection_id", _MEDIA, "fk_oe_site_demand_media", ondelete="SET NULL", nullable=True),
            _str("media_kind", 40, None),
            _fk("stage_id", _STAGE, "fk_oe_site_demand_stage"),
            _str("consumer", 255),
            _guid("site_plant_position_id"),
            _guid("plant_item_id"),
            _num("peak_demand", 14, 3, nullable=False, default="0"),
            _num("simultaneity_factor", 4, 3, nullable=False, default="1"),
        ],
        [
            ("ix_oe_site_demand_media", ["media_connection_id"]),
            ("ix_oe_site_demand_project_stage", ["project_id", "stage_id"]),
            ("ix_oe_site_demand_plant_position", ["site_plant_position_id"]),
        ],
    ),
    (
        "oe_site_logistics_concept",
        lambda: [
            _project_fk("fk_oe_site_concept_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, "neutral"),
            _int("catalogue_version", 1),
            _json("strategy"),
            _nstr("delivery_open", 5),
            _nstr("delivery_close", 5),
            _int("max_deliveries_per_hour", nullable=True),
            _text("rules_text"),
            _nstr("document_ref", 120),
            _guid("saved_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_site_concept_project"),
        ],
        [],
    ),
    (
        "oe_site_logistics_transport",
        lambda: [
            _project_fk("fk_oe_site_transport_project"),
            _str("direction", 10, "inbound"),
            _str("transport_kind", 40, None),
            _str("title", 255),
            _str("carrier_name", 255),
            _str("origin", 255),
            _str("destination", 255),
            _fk("gate_id", _GATE, "fk_oe_site_transport_gate", ondelete="SET NULL", nullable=True),
            _ts("planned_window_start"),
            _ts("planned_window_end"),
            _guid("po_id"),
            _guid("plant_item_id"),
            _nstr("waste_record_ref", 120),
            _guid("customs_case_id"),
            _num("axle_load_t", 10, 2),
            _num("gross_weight_t", 10, 2),
            _num("height_m", 8, 2),
            _num("width_m", 8, 2),
            _num("length_m", 8, 2),
            _num("turning_radius_m", 8, 2),
            _json("route_geojson", nullable=True),
            _text("route_notes"),
            _bool("escort_required", False),
            _str("state", 20, "planned"),
            _date("arrived_on"),
        ],
        [("ix_oe_site_transport_window", ["project_id", "planned_window_start"])],
    ),
    (
        "oe_site_logistics_transport_permit",
        lambda: [
            _project_fk("fk_oe_site_tpermit_project"),
            _fk("transport_id", _TRANSPORT, "fk_oe_site_tpermit_transport", ondelete="SET NULL", nullable=True),
            _str("permit_kind", 40, None),
            _str("authority", 255),
            _str("reference", 120),
            _date("applied_on"),
            _date("valid_from"),
            _date("valid_to"),
            _json("allowed_windows"),
            _text("conditions"),
            _json("route_geojson", nullable=True),
            _nstr("document_ref", 120),
            _guid("authority_permit_id"),
            _str("state", 20, "draft"),
            _date("expiry_notified_on"),
        ],
        [("ix_oe_site_tpermit_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_permit_transport",
        lambda: [
            _project_fk("fk_oe_site_ptlink_project"),
            _fk("permit_id", _PERMIT, "fk_oe_site_ptlink_permit"),
            _fk("transport_id", _TRANSPORT, "fk_oe_site_ptlink_transport"),
            sa.UniqueConstraint("permit_id", "transport_id", name="uq_oe_site_permit_transport"),
        ],
        [("ix_oe_site_ptlink_transport", ["transport_id"])],
    ),
    (
        "oe_site_logistics_customs_case",
        lambda: [
            _project_fk("fk_oe_site_customs_project"),
            _str("direction", 10, "import"),
            _str("title", 255),
            _str("incoterm", 3, None),
            _str("incoterm_version", 10, "2020"),
            _str("named_place", 255),
            _nstr("transport_mode", 20),
            _nstr("country_of_origin", 2),
            _nstr("country_of_destination", 2),
            _nstr("declarant_party", 10),
            _str("broker_name", 255),
            _money("customs_value"),
            _nstr("currency", 3),
            _str("declaration_ref", 120),
            _date("cleared_on"),
            _guid("po_id"),
            _str("state", 20, "open"),
        ],
        [("ix_oe_site_customs_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_customs_line",
        lambda: [
            _project_fk("fk_oe_site_cline_project"),
            _fk("customs_case_id", _CASE, "fk_oe_site_cline_case"),
            _text("description"),
            _str("hs_code", 10, None),
            _guid("commodity_code_id"),
            _num("quantity", 18, 4),
            _str("unit", 20),
            _num("net_mass_kg", 14, 3),
            _money("value"),
            _nstr("origin_country", 2),
            _bool("preferential_origin", False),
            _int("sort_order", 0),
        ],
        [("ix_oe_site_cline_case", ["customs_case_id"])],
    ),
    (
        "oe_site_logistics_customs_document",
        lambda: [
            _project_fk("fk_oe_site_cdoc_project"),
            _fk("customs_case_id", _CASE, "fk_oe_site_cdoc_case"),
            _str("kind", 40, None),
            _bool("required", False),
            _nstr("document_ref", 120),
            _str("state", 20, "missing"),
            sa.UniqueConstraint("customs_case_id", "kind", name="uq_oe_site_cdoc_case_kind"),
        ],
        [("ix_oe_site_cdoc_case", ["customs_case_id"])],
    ),
    (
        "oe_site_logistics_neighbourhood",
        lambda: [
            _project_fk("fk_oe_site_neighbourhood_project"),
            _str("zone_type", 20, "mixed"),
            _str("noise_limit_source", 64),
            _num("day_dba", 5, 1),
            _num("night_dba", 5, 1),
            _json("quiet_hours"),
            _json("site_traffic_routes", nullable=True),
            _text("parking_note"),
            _str("municipality_contact", 255),
            _guid("correspondence_thread_id"),
            sa.UniqueConstraint("project_id", name="uq_oe_site_neighbourhood_project"),
        ],
        [],
    ),
    (
        "oe_site_logistics_neighbour_complaint",
        lambda: [
            _project_fk("fk_oe_site_complaint_project"),
            _str("kind", 40, None),
            _date("reported_on", nullable=False),
            _str("reporter", 255),
            _json("location", nullable=True),
            _text("description"),
            _guid("transport_id"),
            _guid("delivery_id"),
            _text("response"),
            _date("response_due"),
            _str("state", 20, "received"),
            _date("overdue_notified_on"),
        ],
        [("ix_oe_site_complaint_project", ["project_id"])],
    ),
    (
        "oe_site_logistics_coordination",
        lambda: [
            _project_fk("fk_oe_site_coord_project"),
            _date("entry_date", nullable=False),
            _str("body", 30, "municipality"),
            _str("topic", 255),
            _text("outcome"),
            _date("next_action_due"),
            _guid("correspondence_id"),
        ],
        [("ix_oe_site_coord_project", ["project_id", "entry_date"])],
    ),
]

# New nullable columns on the three existing tables: (table, column factory, fk, index).
_EXTEND: list[tuple[str, Callable[[], sa.Column], tuple[str, str, str] | None, str | None]] = [
    ("oe_site_logistics_gate", lambda: _nstr("access_kind", 40), None, None),
    ("oe_site_logistics_gate", lambda: _num("max_axle_load_t", 10, 2), None, None),
    ("oe_site_logistics_gate", lambda: _num("max_gross_t", 10, 2), None, None),
    ("oe_site_logistics_gate", lambda: _num("max_height_m", 8, 2), None, None),
    ("oe_site_logistics_gate", lambda: _num("max_width_m", 8, 2), None, None),
    ("oe_site_logistics_gate", lambda: _num("max_length_m", 8, 2), None, None),
    ("oe_site_logistics_gate", lambda: _num("turning_radius_m", 8, 2), None, None),
    (
        "oe_site_logistics_laydown_zone",
        lambda: _guid("site_area_id"),
        ("fk_oe_site_zone_area", "oe_site_logistics_area", "SET NULL"),
        "ix_oe_site_logistics_laydown_zone_site_area_id",
    ),
    (
        "oe_site_logistics_delivery",
        lambda: _guid("transport_id"),
        ("fk_oe_site_delivery_transport", "oe_site_logistics_transport", "SET NULL"),
        "ix_oe_site_logistics_delivery_transport_id",
    ),
    ("oe_site_logistics_delivery", lambda: _str("direction", 10, "inbound"), None, None),
    ("oe_site_logistics_delivery", lambda: _num("gross_weight_t", 10, 2), None, None),
    ("oe_site_logistics_delivery", lambda: _guid("plant_item_id"), None, None),
    ("oe_site_logistics_delivery", lambda: _guid("takt_location_id"), None, None),
]


def upgrade() -> None:
    """Create the new tables, then add the nullable columns, each only when missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)
    for table, column, fk, index in _EXTEND:
        inspector = sa.inspect(bind)
        if table not in inspector.get_table_names():
            continue
        col = column()
        if col.name not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, col)
        if fk is not None:
            name, target, ondelete = fk
            if name not in {f.get("name") for f in sa.inspect(bind).get_foreign_keys(table)}:
                op.create_foreign_key(name, table, target, [col.name], ["id"], ondelete=ondelete)
        if index is not None and index not in {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}:
            op.create_index(index, table, [col.name])


def downgrade() -> None:
    """Drop the added columns, then the new tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, column, fk, index in reversed(_EXTEND):
        inspector = sa.inspect(bind)
        if table not in inspector.get_table_names():
            continue
        name = column().name
        if index is not None and index in {ix["name"] for ix in inspector.get_indexes(table)}:
            op.drop_index(index, table_name=table)
        if fk is not None and fk[0] in {f.get("name") for f in sa.inspect(bind).get_foreign_keys(table)}:
            op.drop_constraint(fk[0], table, type_="foreignkey")
        if name in {c["name"] for c in sa.inspect(bind).get_columns(table)}:
            op.drop_column(table, name)
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
