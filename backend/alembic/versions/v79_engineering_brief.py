# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""engineering_brief - requirements brief, technical concept, programme and framework schedule.

Four new tables, all project-scoped and CASCADE with the project: the brief (one per project), the
concept items, the programme lines and the framework milestones. The requirements are rows of the
existing ``oe_requirements_item`` in the requirement set the brief points at; no table here.

Engineering brief catalogues a company builds itself live in the governance catalogue tables of v68
under ``kind = engineering_brief_model``; no table here either.

Every constraint and index name is written out and matches the model. Every step is inspector-guarded,
so a database whose tables ``create_all`` already built reaches this revision and does nothing.

Revision ID: v79_engineering_brief
Revises: v78_site_logistics_ext
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v79_engineering_brief"
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


def _brief_fk(name: str) -> sa.Column:
    return sa.Column(
        "brief_id", GUID(), sa.ForeignKey("oe_engbrief_brief.id", ondelete="CASCADE", name=name), nullable=False
    )


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _int(name: str, default: int | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=False)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _day(name: str) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=True)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_engbrief_brief",
        lambda: [
            _project_fk("fk_oe_eb_brief_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("status", 20, "draft"),
            _str("title", 255),
            _text("summary"),
            sa.Column(
                "requirement_set_id",
                GUID(),
                sa.ForeignKey("oe_requirements_set.id", ondelete="SET NULL", name="fk_oe_eb_brief_req_set"),
                nullable=True,
            ),
            sa.Column(
                "schedule_id",
                GUID(),
                sa.ForeignKey("oe_schedule_schedule.id", ondelete="SET NULL", name="fk_oe_eb_brief_schedule"),
                nullable=True,
            ),
            _day("operation_proof_date"),
            sa.Column(
                "governance_document_id",
                GUID(),
                sa.ForeignKey("oe_governance_document.id", ondelete="SET NULL", name="fk_oe_eb_brief_gov_document"),
                nullable=True,
            ),
            _guid("submitted_by"),
            _ts("submitted_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _str("approval_source", 20),
            _guid("bound_revision_id"),
            _json("bound_snapshot"),
            _str("bound_requirements_hash", 64, None, nullable=True),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_eb_brief_project"),
        ],
        [],
    ),
    (
        "oe_engbrief_concept",
        lambda: [
            _project_fk("fk_oe_eb_concept_project"),
            _brief_fk("fk_oe_eb_concept_brief"),
            _str("code", 40, None),
            _str("topic_code", 64, None),
            _str("title", 255, None),
            _text("description"),
            _text("decision"),
            _str("status", 20, "open"),
            _json("requirement_ids"),
            _int("sort_order", 0),
            sa.UniqueConstraint("brief_id", "code", name="uq_oe_eb_concept_code"),
        ],
        [("ix_oe_eb_concept_project", ["project_id"])],
    ),
    (
        "oe_engbrief_programme",
        lambda: [
            _project_fk("fk_oe_eb_programme_project"),
            _brief_fk("fk_oe_eb_programme_brief"),
            _str("code", 40, None),
            _str("kind_code", 64, None),
            _str("label", 255, None),
            _str("unit", 20, None),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
            _text("basis"),
            _int("sort_order", 0),
            sa.UniqueConstraint("brief_id", "code", name="uq_oe_eb_programme_code"),
        ],
        [("ix_oe_eb_programme_project", ["project_id"])],
    ),
    (
        "oe_engbrief_milestone",
        lambda: [
            _project_fk("fk_oe_eb_milestone_project"),
            _brief_fk("fk_oe_eb_milestone_brief"),
            _str("code", 40, None),
            _str("kind_code", 64, None),
            _str("name", 255, None),
            _day("planned_date"),
            _int("lead_days", 0),
            sa.Column(
                "successor_id",
                GUID(),
                sa.ForeignKey("oe_engbrief_milestone.id", ondelete="SET NULL", name="fk_oe_eb_milestone_successor"),
                nullable=True,
            ),
            _str("gate_code", 64, None, nullable=True),
            _guid("permit_requirement_id"),
            _guid("activity_id"),
            _text("notes"),
            _int("sort_order", 0),
            sa.UniqueConstraint("brief_id", "code", name="uq_oe_eb_milestone_code"),
        ],
        [("ix_oe_eb_milestone_project", ["project_id"])],
    ),
]


def upgrade() -> None:
    """Create the four tables and their indexes, each only when missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)


def downgrade() -> None:
    """Drop the four tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
