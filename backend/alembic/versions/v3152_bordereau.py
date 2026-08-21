"""Bordereau de prix — shareable deduplicated price schedule.

Three new tables:
    oe_bordereau_bordereau  — the price schedule entity
    oe_bordereau_line       — deduplicated price line
    oe_bordereau_component  — assembly decomposition

Two additive nullable FK columns on existing BOQ tables:
    oe_boq_boq.bordereau_id        — attach a BOQ to a bordereau
    oe_boq_position.bordereau_line_id — link a position to a bordereau line

Idempotent: guarded by inspector so re-running after SQLite
``Base.metadata.create_all`` (dev) is a no-op.

Revision ID: v3152_bordereau
Revises: v3300_formwork_system_choice
Created: 2026-05-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v3152_bordereau"
down_revision: Union[str, Sequence[str], None] = "v3300_formwork_system_choice"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BOQ_TABLE = "oe_boq_boq"
_POS_TABLE = "oe_boq_position"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ── New tables ──────────────────────────────────────────────────────
    if "oe_bordereau_bordereau" not in existing_tables:
        op.create_table(
            "oe_bordereau_bordereau",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("project_id", GUID(), sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("currency", sa.String(10), nullable=False, server_default=""),
            sa.Column("status", sa.String(50), nullable=False, server_default="draft", index=True),
            sa.Column("is_locked", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    if "oe_bordereau_line" not in existing_tables:
        op.create_table(
            "oe_bordereau_line",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("bordereau_id", GUID(), sa.ForeignKey("oe_bordereau_bordereau.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("reference_code", sa.String(64), nullable=True, index=True),
            sa.Column("designation", sa.Text, nullable=False, server_default=""),
            sa.Column("designation_norm", sa.String(255), nullable=False, server_default="", index=True),
            sa.Column("unit", sa.String(20), nullable=False, server_default=""),
            sa.Column("unit_rate", sa.String(50), nullable=False, server_default="0"),
            sa.Column("is_assembly", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
            sa.Column("version", sa.Integer, nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_bordereau_line_dedup",
            "oe_bordereau_line",
            ["bordereau_id", "designation_norm", "unit"],
        )
        op.create_index(
            "ix_bordereau_line_bordereau_ref",
            "oe_bordereau_line",
            ["bordereau_id", "reference_code"],
        )

    if "oe_bordereau_component" not in existing_tables:
        op.create_table(
            "oe_bordereau_component",
            sa.Column("id", GUID(), primary_key=True),
            sa.Column("line_id", GUID(), sa.ForeignKey("oe_bordereau_line.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("cost_item_id", GUID(), sa.ForeignKey("oe_costs_item.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("description", sa.String(500), nullable=False, server_default=""),
            sa.Column("resource_type", sa.String(20), nullable=True),
            sa.Column("factor", sa.String(50), nullable=False, server_default="1.0"),
            sa.Column("quantity", sa.String(50), nullable=False, server_default="1.0"),
            sa.Column("unit", sa.String(20), nullable=False, server_default=""),
            sa.Column("unit_cost", sa.String(50), nullable=False, server_default="0"),
            sa.Column("total", sa.String(50), nullable=False, server_default="0"),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # ── Additive nullable FK columns on existing tables ─────────────────
    boq_cols = {c["name"] for c in inspector.get_columns(_BOQ_TABLE)}
    boq_indexes = {i["name"] for i in inspector.get_indexes(_BOQ_TABLE)}

    if "bordereau_id" not in boq_cols:
        op.add_column(
            _BOQ_TABLE,
            sa.Column("bordereau_id", GUID(), nullable=True),
        )
    if "ix_oe_boq_boq_bordereau_id" not in boq_indexes:
        op.create_index(
            "ix_oe_boq_boq_bordereau_id",
            _BOQ_TABLE,
            ["bordereau_id"],
        )

    pos_cols = {c["name"] for c in inspector.get_columns(_POS_TABLE)}
    pos_indexes = {i["name"] for i in inspector.get_indexes(_POS_TABLE)}

    if "bordereau_line_id" not in pos_cols:
        op.add_column(
            _POS_TABLE,
            sa.Column("bordereau_line_id", GUID(), nullable=True),
        )
    if "ix_oe_boq_position_bordereau_line_id" not in pos_indexes:
        op.create_index(
            "ix_oe_boq_position_bordereau_line_id",
            _POS_TABLE,
            ["bordereau_line_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Drop additive columns + indexes
    pos_cols = {c["name"] for c in inspector.get_columns(_POS_TABLE)} if _POS_TABLE in existing_tables else set()
    pos_indexes = {i["name"] for i in inspector.get_indexes(_POS_TABLE)} if _POS_TABLE in existing_tables else set()

    if "ix_oe_boq_position_bordereau_line_id" in pos_indexes:
        op.drop_index("ix_oe_boq_position_bordereau_line_id", table_name=_POS_TABLE)
    if "bordereau_line_id" in pos_cols:
        op.drop_column(_POS_TABLE, "bordereau_line_id")

    boq_cols = {c["name"] for c in inspector.get_columns(_BOQ_TABLE)} if _BOQ_TABLE in existing_tables else set()
    boq_indexes = {i["name"] for i in inspector.get_indexes(_BOQ_TABLE)} if _BOQ_TABLE in existing_tables else set()

    if "ix_oe_boq_boq_bordereau_id" in boq_indexes:
        op.drop_index("ix_oe_boq_boq_bordereau_id", table_name=_BOQ_TABLE)
    if "bordereau_id" in boq_cols:
        op.drop_column(_BOQ_TABLE, "bordereau_id")

    # Drop new tables (reverse order of creation)
    if "oe_bordereau_component" in existing_tables:
        op.drop_table("oe_bordereau_component")
    if "oe_bordereau_line" in existing_tables:
        op.drop_table("oe_bordereau_line")
    if "oe_bordereau_bordereau" in existing_tables:
        op.drop_table("oe_bordereau_bordereau")
