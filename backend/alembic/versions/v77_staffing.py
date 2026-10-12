# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""staffing - staffing plan, fills, handovers and personnel files.

Eight new tables, all project-scoped and CASCADE with the project: the plan,
positions, fills, handovers, personnel files, personnel documents, travel and
leave. One existing table is touched: ``oe_accommodation_booking`` gains a
nullable ``roster_member_id`` so a booking can be attributed to a person.

Staffing catalogues a company builds itself live in the governance catalogue
tables of v68 under ``kind = staffing_model``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v77_staffing
Revises: v68_project_governance
Create Date: 2026-10-12
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v77_staffing"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"
_BOOKING = "oe_accommodation_booking"
_BOOKING_IX = "ix_oe_accommodation_booking_roster_member_id"


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


def _int(name: str, default: int | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=False)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _day(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _num(name: str, precision: int, scale: int, default: str | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Numeric(precision, scale), nullable=True)
    return sa.Column(name, sa.Numeric(precision, scale), nullable=False, server_default=default)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_staffing_plan",
        lambda: [
            _project_fk("fk_oe_staff_plan_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("status", 20, "draft"),
            _bool("requires_accommodation"),
            _day("commissioning_date"),
            sa.Column(
                "governance_document_id",
                GUID(),
                sa.ForeignKey("oe_governance_document.id", ondelete="SET NULL", name="fk_oe_staff_plan_gov_document"),
                nullable=True,
            ),
            _guid("submitted_by"),
            _ts("submitted_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _str("approval_source", 20),
            _guid("bound_revision_id"),
            _json("bound_snapshot"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_staff_plan_project"),
        ],
        [],
    ),
    (
        "oe_staffing_position",
        lambda: [
            _project_fk("fk_oe_staff_position_project"),
            _fk("plan_id", "oe_staffing_plan.id", "fk_oe_staff_position_plan"),
            _str("role_code", 64, None),
            _str("custom_label", 255),
            _str("organisation", 40, None),
            _str("phase", 20, None),
            _str("title", 255),
            _num("fte", 5, 2, "1"),
            _int("headcount", 1),
            _day("entry_date"),
            _day("exit_date"),
            _str("required_before", 64, None, nullable=True),
            _bool("key_role"),
            _bool("handover_role"),
            _str("status", 20, "open"),
            _str("recruiting_channel", 30, None, nullable=True),
            _guid("owner_user_id"),
            _guid("resource_request_id"),
            _guid("contract_id"),
            _guid("rfq_id"),
            _text("notes"),
            _int("sort_order", 0),
        ],
        [("ix_oe_staff_position_project", ["project_id"]), ("ix_oe_staff_position_plan", ["plan_id"])],
    ),
    (
        "oe_staffing_fill",
        lambda: [
            _project_fk("fk_oe_staff_fill_project"),
            _fk("position_id", "oe_staffing_position.id", "fk_oe_staff_fill_position"),
            _guid("roster_member_id"),
            _num("fte_share", 5, 2, "1"),
            _day("from_date", nullable=False),
            _day("to_date"),
            _str("status", 20, "proposed"),
        ],
        [
            ("ix_oe_staff_fill_project", ["project_id"]),
            ("ix_oe_staff_fill_position", ["position_id"]),
            ("ix_oe_staff_fill_roster", ["roster_member_id"]),
        ],
    ),
    (
        "oe_staffing_handover",
        lambda: [
            _project_fk("fk_oe_staff_handover_project"),
            _fk("from_fill_id", "oe_staffing_fill.id", "fk_oe_staff_handover_fill"),
            _fk("to_position_id", "oe_staffing_position.id", "fk_oe_staff_handover_position"),
            _int("overlap_days", 0),
            _text("scope"),
            _str("status", 20, "planned"),
        ],
        [("ix_oe_staff_handover_project", ["project_id"])],
    ),
    (
        "oe_staffing_file",
        lambda: [
            _project_fk("fk_oe_staff_file_project"),
            _guid("roster_member_id"),
            _str("employer_organisation", 255),
            _str("employment_basis", 30, "employee"),
            _bool("nationality_required"),
            _str("lawful_basis", 30, "contract"),
            _str("status", 20, "active"),
            _day("ended_on"),
            _day("retention_due_at"),
            _text("hold_rationale"),
            _guid("held_by"),
            _ts("anonymised_at"),
            _json("activity_counts"),
            sa.UniqueConstraint("project_id", "roster_member_id", name="uq_oe_staff_file_member"),
        ],
        [("ix_oe_staff_file_project", ["project_id"]), ("ix_oe_staff_file_due", ["status", "retention_due_at"])],
    ),
    (
        "oe_staffing_document",
        lambda: [
            _project_fk("fk_oe_staff_document_project"),
            _fk("personnel_file_id", "oe_staffing_file.id", "fk_oe_staff_document_file"),
            _str("document_kind", 64, None),
            _guid("credential_id"),
            _str("number_last4", 4, None, nullable=True),
            _guid("recorded_by"),
            _guid("verified_by"),
            _ts("verified_at"),
            _bool("waived"),
            _text("waiver_rationale"),
            _str("fit_for_role", 20, None, nullable=True),
            sa.UniqueConstraint("personnel_file_id", "document_kind", name="uq_oe_staff_document_kind"),
            sa.UniqueConstraint("project_id", "credential_id", name="uq_oe_staff_document_credential"),
        ],
        [("ix_oe_staff_document_project", ["project_id"]), ("ix_oe_staff_document_credential", ["credential_id"])],
    ),
    (
        "oe_staffing_travel",
        lambda: [
            _project_fk("fk_oe_staff_travel_project"),
            _fk("personnel_file_id", "oe_staffing_file.id", "fk_oe_staff_travel_file"),
            _str("kind", 20, None),
            _str("from_place", 120),
            _str("to_place", 120),
            _day("depart_date", nullable=False),
            _day("return_date"),
            _str("booking_ref", 64),
            _num("cost", 14, 2),
            _str("currency", 3),
            _str("status", 20, "planned"),
        ],
        [("ix_oe_staff_travel_project", ["project_id"]), ("ix_oe_staff_travel_file", ["personnel_file_id"])],
    ),
    (
        "oe_staffing_leave",
        lambda: [
            _project_fk("fk_oe_staff_leave_project"),
            _fk("personnel_file_id", "oe_staffing_file.id", "fk_oe_staff_leave_file"),
            _str("leave_type", 30, None),
            _day("from_date", nullable=False),
            _day("to_date", nullable=False),
            _str("status", 20, "requested"),
            _guid("approved_by"),
            _ts("approved_at"),
        ],
        [("ix_oe_staff_leave_project", ["project_id"]), ("ix_oe_staff_leave_file", ["personnel_file_id"])],
    ),
]


def upgrade() -> None:
    """Create the eight tables and their indexes, then the booking column, each only when missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)
    if _BOOKING in sa.inspect(bind).get_table_names():
        if "roster_member_id" not in {c["name"] for c in sa.inspect(bind).get_columns(_BOOKING)}:
            op.add_column(_BOOKING, sa.Column("roster_member_id", GUID(), nullable=True))
        if _BOOKING_IX not in {ix["name"] for ix in sa.inspect(bind).get_indexes(_BOOKING)}:
            op.create_index(_BOOKING_IX, _BOOKING, ["roster_member_id"])


def downgrade() -> None:
    """Drop the booking column, then the eight tables, children before the parents they reference."""
    bind = op.get_bind()
    if _BOOKING in sa.inspect(bind).get_table_names():
        if _BOOKING_IX in {ix["name"] for ix in sa.inspect(bind).get_indexes(_BOOKING)}:
            op.drop_index(_BOOKING_IX, table_name=_BOOKING)
        if "roster_member_id" in {c["name"] for c in sa.inspect(bind).get_columns(_BOOKING)}:
            with op.batch_alter_table(_BOOKING) as batch:
                batch.drop_column("roster_member_id")
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
