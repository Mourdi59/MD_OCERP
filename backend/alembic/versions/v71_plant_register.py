# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""plant register - main components, long-lead items, slots, papers, limits, spares, IT; site plant positions.

Nine new tables, nothing existing altered. Eight belong to the plant register
(``oe_plant_*``), are project-scoped and CASCADE with the project; one extends
site logistics with the positions of site plant and cranes on the site plan
(``oe_site_logistics_plant_position``). Soft references into other modules carry
no foreign key.

Every constraint and index name is written out and matches the models. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v71_plant_register
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v71_plant_register"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"
_ITEM = "oe_plant_item.id"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _project_fk(name: str) -> sa.Column:
    return sa.Column("project_id", GUID(), sa.ForeignKey(_PROJECT, ondelete="CASCADE", name=name), nullable=False)


def _item_fk(name: str) -> sa.Column:
    return sa.Column("plant_item_id", GUID(), sa.ForeignKey(_ITEM, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool | None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Boolean(), nullable=True)
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=False)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def _num(name: str, precision: int, scale: int, nullable: bool = True, default: str | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Numeric(precision, scale), nullable=nullable)
    return sa.Column(name, sa.Numeric(precision, scale), nullable=nullable, server_default=default)


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _day(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=nullable)


_Index = tuple[str, list[str], dict]

_TABLES: list[tuple[str, Callable[[], list], list[_Index]]] = [
    (
        "oe_plant_settings",
        lambda: [
            _project_fk("fk_oe_plant_settings_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, "neutral"),
            _int("catalogue_version", 1),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_plant_settings_project"),
        ],
        [],
    ),
    (
        "oe_plant_item",
        lambda: [
            _project_fk("fk_oe_plant_item_project"),
            _str("code", 64, None),
            _str("title", 255, None),
            _text("description"),
            _str("component_class_code", 64, None),
            _str("item_class", 40, None),
            _num("quantity", 18, 3, nullable=False, default="1"),
            _str("unit", 20, "pcs"),
            _str("tag", 64),
            _guid("wbs_id"),
            _guid("boq_position_id"),
            _json("bim_element_ids"),
            _guid("cx_system_id"),
            _str("space_ref", 255),
            _json("performance"),
            _str("redundancy_scheme", 16),
            _json("maintainability"),
            _str("vendor_policy", 20, "neutral"),
            _str("vendor_bound_reason", 40),
            _guid("vendor_id"),
            _bool("critical_override", None),
            _text("critical_reason"),
            _guid("need_activity_id"),
            _day("need_date_fixed"),
            _json("order_buffers"),
            _str("procurement_route", 64, None, nullable=True),
            _guid("contract_package_id"),
            _guid("owner_furnished_item_id"),
            _guid("purchase_order_id"),
            _guid("submittal_id"),
            _str("maintenance_strategy", 40),
            _text("no_strategic_spare_reason"),
            _bool("long_lead_override", None),
            _text("long_lead_override_reason"),
            _guid("owner_user_id"),
            _str("status", 20, "identified"),
            _guid("service_asset_id"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_plant_item_code"),
        ],
        [("ix_oe_plr_item_status", ["project_id", "status"], {})],
    ),
    (
        "oe_plant_lead_time_quote",
        lambda: [
            _project_fk("fk_oe_plant_quote_project"),
            _item_fk("fk_oe_plant_quote_item"),
            _str("source", 40, None),
            _guid("vendor_id"),
            _str("source_name", 255),
            _day("enquiry_date", nullable=False),
            _day("response_date"),
            _int("lead_weeks_min"),
            _int("lead_weeks_max"),
            _str("lead_basis", 40, "from_order"),
            _day("valid_until"),
            _str("document_ref", 255),
            _guid("catalogue_entry_id"),
            _bool("is_basis", False),
            _guid("superseded_by"),
            _text("note"),
            _guid("created_by"),
        ],
        [
            ("ix_oe_plr_quote_item", ["plant_item_id"], {}),
            (
                "uq_oe_plant_quote_basis",
                ["plant_item_id"],
                {"unique": True, "postgresql_where": sa.text("is_basis"), "sqlite_where": sa.text("is_basis")},
            ),
        ],
    ),
    (
        "oe_plant_slot_reservation",
        lambda: [
            _project_fk("fk_oe_plant_slot_project"),
            _item_fk("fk_oe_plant_slot_item"),
            _guid("vendor_id"),
            _str("vendor_name", 255),
            _day("slot_from"),
            _day("slot_to"),
            _num("reservation_fee", 18, 2),
            _str("currency", 3),
            _str("fee_refundable", 20),
            _bool("fee_credited_to_order", False),
            _day("convert_by_date"),
            _text("terms"),
            _guid("commitment_item_id"),
            _str("document_ref", 255),
            _str("status", 30, "requested"),
            _guid("created_by"),
        ],
        [("ix_oe_plr_slot_item", ["plant_item_id"], {})],
    ),
    (
        "oe_plant_decision_paper",
        lambda: [
            _project_fk("fk_oe_plant_paper_project"),
            _item_fk("fk_oe_plant_paper_item"),
            _text("question"),
            _json("options"),
            _json("criteria"),
            _str("recommendation", 64),
            _text("rationale"),
            _guid("approval_instance_id"),
            _str("status", 20, "draft"),
            _json("snapshot", nullable=True),
            _guid("supersedes_id"),
            _guid("submitted_by"),
            _ts("decided_at"),
            _guid("created_by"),
        ],
        [("ix_oe_plr_paper_item", ["plant_item_id"], {})],
    ),
    (
        "oe_plant_delivery_limit",
        lambda: [
            _project_fk("fk_oe_plant_limit_project"),
            _item_fk("fk_oe_plant_limit_item"),
            _str("step", 40, None),
            _str("party", 40),
            _guid("contract_package_id"),
            _text("note"),
            sa.UniqueConstraint("plant_item_id", "step", name="uq_oe_plant_limit_step"),
        ],
        [],
    ),
    (
        "oe_plant_spare_part",
        lambda: [
            _project_fk("fk_oe_plant_spare_project"),
            _item_fk("fk_oe_plant_spare_item"),
            _str("category", 40, None),
            _text("description"),
            _num("quantity", 18, 3, nullable=False, default="1"),
            _str("unit", 20, "pcs"),
            _str("supply_by", 40),
            _guid("supply_package_id"),
            _str("handover_target", 255),
            _text("waiver_reason"),
            _str("status", 20, "required"),
        ],
        [("ix_oe_plr_spare_item", ["plant_item_id"], {})],
    ),
    (
        "oe_plant_it_service",
        lambda: [
            _project_fk("fk_oe_plant_it_project"),
            _str("kind", 40, None),
            _text("description"),
            _str("responsible_party", 40),
            _day("needed_from"),
            _day("needed_until"),
            _guid("needed_from_activity_id"),
            _json("access_roles"),
            _guid("cde_container_id"),
            _str("status", 20, "planned"),
        ],
        [("ix_oe_plr_it_project", ["project_id"], {})],
    ),
    (
        "oe_site_logistics_plant_position",
        lambda: [
            _project_fk("fk_oe_site_plant_position_project"),
            _str("kind", 40, None),
            _str("name", 255),
            _num("x", 12, 3),
            _num("y", 12, 3),
            _num("reach_m", 8, 2),
            _num("max_load_t", 10, 2),
            _day("from_date"),
            _day("to_date"),
            _guid("equipment_id"),
            _guid("laydown_zone_id"),
            _text("note"),
        ],
        [("ix_oe_site_plantpos_project", ["project_id"], {})],
    ),
]


def upgrade() -> None:
    """Create the nine tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols, kw in indexes:
            if name not in existing:
                op.create_index(name, table, cols, **kw)


def downgrade() -> None:
    """Drop the nine tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
