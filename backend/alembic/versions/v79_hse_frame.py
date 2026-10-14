# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""hse_frame - the HSE frame, its register, roles and links.

Four new tables, all project-scoped and CASCADE with the project: the frame,
the register items, the roles and the links from items to records of other
modules. No existing table is touched. HSE catalogues a company builds itself
live in the governance catalogue tables under ``kind = hse_frame``; no table
here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v79_hse_frame
Revises: v78_site_logistics_ext
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v79_hse_frame"
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


def _fk(column: str, target: str, name: str) -> sa.Column:
    return sa.Column(column, GUID(), sa.ForeignKey(target, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool = False) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
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
        "oe_hsef_frame",
        lambda: [
            _project_fk("fk_oe_hsef_frame_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, "neutral"),
            _int("catalogue_version", 1),
            _str("state", 20, "draft"),
            _guid("governance_doc_id"),
            _day("planned_start"),
            _int("duration_working_days", nullable=True),
            _int("peak_workers", nullable=True),
            _int("person_days", nullable=True),
            _int("employers_count", nullable=True),
            _json("hazardous_work_codes"),
            _bool("hazardous_works_assessed"),
            _day("advance_notice_sent_on"),
            _str("advance_notice_reference", 120),
            _str("plan_status", 20, "not_started"),
            _day("plan_issued_on"),
            _guid("plan_document_id"),
            _str("later_works_status", 20, "not_started"),
            _text("notes"),
            _guid("submitted_by"),
            _ts("submitted_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_hsef_frame_project"),
        ],
        [],
    ),
    (
        "oe_hsef_item",
        lambda: [
            _project_fk("fk_oe_hsef_item_project"),
            _fk("frame_id", "oe_hsef_frame.id", "fk_oe_hsef_item_frame"),
            _str("topic", 64, None),
            _str("template_code", 64, None, nullable=True),
            _str("title", 500, None),
            _text("description"),
            _json("audience"),
            _str("obligation", 20, "mandatory"),
            _str("legal_basis", 255),
            _str("status", 20, "open"),
            _guid("responsible_user_id"),
            _str("responsible_party", 255),
            _day("due_date"),
            _day("met_on"),
            _str("target_text", 255),
            _text("evidence_note"),
            _text("waive_reason"),
            _guid("waived_by"),
            _bool("in_tender_documents"),
            _str("source", 20, "manual"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("frame_id", "template_code", name="uq_oe_hsef_item_template"),
        ],
        [("ix_oe_hsef_item_project_topic", ["project_id", "topic"])],
    ),
    (
        "oe_hsef_role",
        lambda: [
            _project_fk("fk_oe_hsef_role_project"),
            _fk("frame_id", "oe_hsef_frame.id", "fk_oe_hsef_role_frame"),
            _str("role_code", 64, None),
            _guid("person_user_id"),
            _guid("contact_id"),
            _str("person_name", 255),
            _str("organisation", 255),
            _str("status", 20, "proposed"),
            _day("appointed_on"),
            _day("ends_on"),
            _str("qualification", 255),
            _day("qualification_valid_until"),
            _guid("appointment_document_id"),
            _text("note"),
            _guid("created_by"),
        ],
        [("ix_oe_hsef_role_project_code", ["project_id", "role_code"])],
    ),
    (
        "oe_hsef_link",
        lambda: [
            _project_fk("fk_oe_hsef_link_project"),
            _fk("item_id", "oe_hsef_item.id", "fk_oe_hsef_link_item"),
            _str("link_kind", 30, None),
            _str("link_id", 64, None),
            _str("note", 500),
            _guid("created_by"),
            sa.UniqueConstraint("item_id", "link_kind", "link_id", name="uq_oe_hsef_link_target"),
        ],
        [("ix_oe_hsef_link_project", ["project_id"])],
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
