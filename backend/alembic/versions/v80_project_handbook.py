# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""project_handbook - handbook chapters with versions, and the document folder tree of the data room.

Four new tables, all project-scoped and CASCADE with the project: the handbook, its chapters, the
approved chapter versions, and the folders of the documents module (``oe_documents_folder``). One column
is added to an existing table: ``oe_documents_document.folder_id``, nullable with an index and no foreign
key, because a folder that goes away unfiles its documents and never deletes them.

Every constraint and index name is written out and matches the models. Every step is inspector-guarded,
so a database whose tables ``create_all`` already built reaches this revision and does nothing.

Revision ID: v80_project_handbook
Revises: v79_hse_frame
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v80_project_handbook"
down_revision: str | Sequence[str] | None = "v79_delivery_contract_items"
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


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=str(default))


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_handbook_handbook",
        lambda: [
            _project_fk("fk_oe_hb_handbook_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, "neutral"),
            _int("catalogue_version", 1),
            _str("title", 255),
            _str("edition", 120),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_hb_handbook_project"),
        ],
        [],
    ),
    (
        "oe_handbook_chapter",
        lambda: [
            _project_fk("fk_oe_hb_chapter_project"),
            _fk("handbook_id", "oe_handbook_handbook.id", "fk_oe_hb_chapter_handbook"),
            _str("code", 64, None),
            _str("area_code", 64),
            _str("folder_code", 120),
            _int("sort_order", 0),
            _str("title", 255),
            _guid("owner_id"),
            _text("content"),
            _str("status", 20, "draft"),
            _int("draft_version", 1),
            _int("approved_version", nullable=True),
            _guid("submitted_by"),
            _ts("submitted_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _int("row_version", 1),
            sa.UniqueConstraint("handbook_id", "code", name="uq_oe_hb_chapter_code"),
        ],
        [("ix_oe_hb_chapter_project", ["project_id"])],
    ),
    (
        "oe_handbook_chapter_version",
        lambda: [
            _project_fk("fk_oe_hb_version_project"),
            _fk("chapter_id", "oe_handbook_chapter.id", "fk_oe_hb_version_chapter"),
            _int("version"),
            _str("title", 255),
            _text("content"),
            _guid("owner_id"),
            _guid("submitted_by"),
            _ts("submitted_at"),
            sa.Column("approved_by", GUID(), nullable=False),
            _ts("approved_at", nullable=False),
            sa.UniqueConstraint("chapter_id", "version", name="uq_oe_hb_version_number"),
        ],
        [("ix_oe_hb_version_project", ["project_id"])],
    ),
    (
        "oe_documents_folder",
        lambda: [
            _project_fk("fk_oe_documents_folder_project"),
            _str("code", 120, None),
            _guid("parent_id"),
            _str("name", 255),
            _str("name_key", 255),
            _str("area_code", 64),
            _str("phase_code", 64),
            _str("source", 20, "manual"),
            _int("sort_order", 0),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_documents_folder_code"),
        ],
        [("ix_oe_documents_folder_project_id", ["project_id"])],
    ),
]

_DOC_TABLE = "oe_documents_document"
_DOC_INDEX = "ix_oe_documents_document_folder_id"


def upgrade() -> None:
    """Create the four tables and their indexes, then the folder column; each only when missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)
    if _DOC_TABLE in sa.inspect(bind).get_table_names():
        if "folder_id" not in {c["name"] for c in sa.inspect(bind).get_columns(_DOC_TABLE)}:
            op.add_column(_DOC_TABLE, sa.Column("folder_id", GUID(), nullable=True))
        if _DOC_INDEX not in {ix["name"] for ix in sa.inspect(bind).get_indexes(_DOC_TABLE)}:
            op.create_index(_DOC_INDEX, _DOC_TABLE, ["folder_id"])


def downgrade() -> None:
    """Drop the folder column, then the tables, children before the parents they reference."""
    bind = op.get_bind()
    if _DOC_TABLE in sa.inspect(bind).get_table_names():
        if _DOC_INDEX in {ix["name"] for ix in sa.inspect(bind).get_indexes(_DOC_TABLE)}:
            op.drop_index(_DOC_INDEX, table_name=_DOC_TABLE)
        if "folder_id" in {c["name"] for c in sa.inspect(bind).get_columns(_DOC_TABLE)}:
            with op.batch_alter_table(_DOC_TABLE) as batch:
                batch.drop_column("folder_id")
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
