# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""economics - business case, cost frame and financing plan of a project.

Six new tables, nothing existing touched, all project-scoped and CASCADE with
the project: the plan (status, currency, classification standard, discount
rate, horizon), the lines of the business case, the lines of the cost frame,
the sources of finance with their tranches, and the approvals with the frozen
snapshot they were judged on.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v79_economics
Revises: v78_site_logistics_ext
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v79_economics"
down_revision: str | Sequence[str] | None = "v78_site_logistics_ext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _project_fk(name: str) -> sa.Column:
    return sa.Column("project_id", GUID(), sa.ForeignKey(_PROJECT, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=str(default))


def _money(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, MoneyType(18, 4), nullable=nullable)


def _rate(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, MoneyType(9, 4), nullable=nullable)


def _guid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, GUID(), nullable=nullable)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_economics_plan",
        lambda: [
            _project_fk("fk_oe_eco_plan_project"),
            _str("status", 20, "draft"),
            _str("currency", 3, ""),
            _str("classification_standard", 50, ""),
            _rate("discount_rate_pct", nullable=True),
            _int("horizon_years", 20),
            _guid("boq_id"),
            _money("markup_allowance"),
            _guid("current_approval_id"),
            _guid("change_request_id"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_eco_plan_project"),
        ],
        [],
    ),
    (
        "oe_economics_flow_line",
        lambda: [
            _project_fk("fk_oe_eco_flow_project"),
            _str("kind", 20, None),
            _str("label", 255, ""),
            _str("mode", 10, "total"),
            _str("source", 12, "manual"),
            _money("amount"),
            _int("year_from", 0),
            _int("year_to", 0),
            _rate("escalation_pct"),
            _int("sort_order", 0),
            _text("notes"),
        ],
        [("ix_oe_eco_flow_project", ["project_id", "sort_order"])],
    ),
    (
        "oe_economics_frame_line",
        lambda: [
            _project_fk("fk_oe_eco_frame_project"),
            _str("code", 80, None),
            _str("title", 255, ""),
            _money("amount"),
            _text("basis"),
            _int("sort_order", 0),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_eco_frame_project_code"),
        ],
        [("ix_oe_eco_frame_project", ["project_id", "sort_order"])],
    ),
    (
        "oe_economics_funding_source",
        lambda: [
            _project_fk("fk_oe_eco_source_project"),
            _str("kind", 30, None),
            _str("name", 255, ""),
            _money("amount"),
            _rate("interest_rate_pct", nullable=True),
            _guid("funding_application_id"),
            _int("sort_order", 0),
            _text("notes"),
        ],
        [("ix_oe_eco_source_project", ["project_id", "sort_order"])],
    ),
    (
        "oe_economics_tranche",
        lambda: [
            _project_fk("fk_oe_eco_tranche_project"),
            sa.Column(
                "source_id",
                GUID(),
                sa.ForeignKey("oe_economics_funding_source.id", ondelete="CASCADE", name="fk_oe_eco_tranche_source"),
                nullable=False,
            ),
            _str("due_on", 40, ""),
            _money("amount"),
            _str("status", 12, "planned"),
            _text("condition"),
            _str("drawn_on", 40, None, nullable=True),
        ],
        [("ix_oe_eco_tranche_source", ["source_id", "due_on"])],
    ),
    (
        "oe_economics_approval",
        lambda: [
            _project_fk("fk_oe_eco_approval_project"),
            _int("number"),
            _str("status", 12, "proposed"),
            _text("rationale"),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            _str("snapshot_hash", 64, ""),
            _guid("proposed_by"),
            _ts("proposed_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _str("approval_source", 20, None, nullable=True),
            _guid("governance_ref_id"),
            sa.Column(
                "governance_document_id",
                GUID(),
                sa.ForeignKey("oe_governance_document.id", ondelete="SET NULL", name="fk_oe_eco_approval_gov_document"),
                nullable=True,
            ),
            sa.Column("four_eyes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            _str("approval_blocked_reason", 64, ""),
            sa.UniqueConstraint("project_id", "number", name="uq_oe_eco_approval_number"),
        ],
        [("ix_oe_eco_approval_project", ["project_id", "number"])],
    ),
]


def upgrade() -> None:
    """Create the six tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)


def downgrade() -> None:
    """Drop the six tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
