# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""delivery model - project delivery form decision, risk allocation and package plan.

Eight new tables, nothing existing touched, all project-scoped and CASCADE with
the project: the model (pinned delivery forms catalogue, chosen form, status),
compared options, criteria with weights, scores, decisions with their frozen
snapshot, risk allocations, the contract package plan and owner-furnished items.

Delivery forms catalogues a company builds itself live in the governance
catalogue tables of v68 under ``kind = delivery_forms``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v70_delivery_model
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v70_delivery_model"
down_revision: str | Sequence[str] | None = "v68_project_governance"
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


def _bool(name: str, default: bool = False) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=str(default))


def _guid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, GUID(), nullable=nullable)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_delivery_model_model",
        lambda: [
            _project_fk("fk_oe_dm_model_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("selected_form_code", 64, None, nullable=True),
            _str("status", 20, "draft"),
            _bool("underground_risk_sharing"),
            _json("owner_capability"),
            _guid("governance_document_id"),
            _guid("current_decision_id"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_dm_model_project"),
        ],
        [],
    ),
    (
        "oe_delivery_model_option",
        lambda: [
            _project_fk("fk_oe_dm_option_project"),
            _str("form_code", 64, None),
            _json("overrides"),
            _text("notes"),
            _int("sort_order", 0),
            sa.UniqueConstraint("project_id", "form_code", name="uq_oe_dm_option_form"),
        ],
        [("ix_oe_dm_option_project", ["project_id"])],
    ),
    (
        "oe_delivery_model_criterion",
        lambda: [
            _project_fk("fk_oe_dm_criterion_project"),
            _str("code", 64, None),
            sa.Column("weight", sa.Numeric(9, 4), nullable=False, server_default="0"),
            _int("sort_order", 0),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dm_criterion_code"),
        ],
        [("ix_oe_dm_criterion_project", ["project_id"])],
    ),
    (
        "oe_delivery_model_score",
        lambda: [
            _project_fk("fk_oe_dm_score_project"),
            sa.Column(
                "option_id",
                GUID(),
                sa.ForeignKey("oe_delivery_model_option.id", ondelete="CASCADE", name="fk_oe_dm_score_option"),
                nullable=False,
            ),
            sa.Column(
                "criterion_id",
                GUID(),
                sa.ForeignKey("oe_delivery_model_criterion.id", ondelete="CASCADE", name="fk_oe_dm_score_criterion"),
                nullable=False,
            ),
            _int("score"),
            _text("rationale"),
            sa.UniqueConstraint("option_id", "criterion_id", name="uq_oe_dm_score_pair"),
        ],
        [("ix_oe_dm_score_project", ["project_id"])],
    ),
    (
        "oe_delivery_model_decision",
        lambda: [
            _project_fk("fk_oe_dm_decision_project"),
            _str("form_code", 64, None),
            _guid("option_id"),
            _str("status", 20, "proposed"),
            _text("rationale"),
            _json("snapshot"),
            _json("owner_capability"),
            _json("dispositions"),
            _guid("proposed_by"),
            _ts("proposed_at"),
            _guid("approved_by"),
            _ts("approved_at"),
            _str("approval_source", 20),
            _guid("governance_document_id"),
            _guid("governance_ref_id"),
            _guid("bound_revision_id"),
            _str("bound_content_hash", 64, None, nullable=True),
            _guid("supersedes_id"),
        ],
        [("ix_oe_dm_decision_project", ["project_id"])],
    ),
    (
        "oe_delivery_model_allocation",
        lambda: [
            _project_fk("fk_oe_dm_allocation_project"),
            _str("category_code", 64, None),
            _str("party", 40, None, nullable=True),
            _str("basis", 30, "contract"),
            _json("shares"),
            _text("rationale"),
            _bool("not_applicable"),
            _str("source", 30, "catalogue_default"),
            _str("status", 20, "unconfirmed"),
            _guid("confirmed_by"),
            _ts("confirmed_at"),
            _json("risk_item_ids"),
            sa.UniqueConstraint("project_id", "category_code", name="uq_oe_dm_allocation_category"),
        ],
        [("ix_oe_dm_allocation_project", ["project_id"])],
    ),
    (
        "oe_delivery_model_package",
        lambda: [
            _project_fk("fk_oe_dm_package_project"),
            _str("code", 64, None),
            _str("title", 500),
            _str("kind", 40, None),
            _bool("designs"),
            _bool("builds"),
            _bool("supplies"),
            _bool("manages"),
            _str("party", 40, "contractor"),
            _str("contracting_party", 20, "owner"),
            _str("price_basis", 30, None, nullable=True),
            _str("standard_form", 120),
            _guid("parent_id"),
            _text("scope"),
            _str("wbs_ref", 120),
            _str("boq_ref", 120),
            _str("need_date", 40, None, nullable=True),
            _str("status", 20, "planned"),
            _str("link_kind", 30, None, nullable=True),
            _guid("link_id"),
            _int("sort_order", 0),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dm_package_code"),
        ],
        [("ix_oe_dm_package_project", ["project_id"]), ("ix_oe_dm_package_link", ["link_kind", "link_id"])],
    ),
    (
        "oe_delivery_model_ofi",
        lambda: [
            _project_fk("fk_oe_dm_ofi_project"),
            _str("code", 64, None),
            _text("description"),
            _str("item_kind", 20, "equipment"),
            _str("install_by", 20, "package"),
            _guid("package_id"),
            _str("procurement_route", 20, "none_yet"),
            _str("link_kind", 20, None, nullable=True),
            _guid("link_id"),
            _guid("schedule_activity_id"),
            _str("need_by_date", 40, None, nullable=True),
            _str("expected_delivery_date", 40, None, nullable=True),
            _str("enquiry_date", 40, None, nullable=True),
            _int("lead_time_days", nullable=True),
            _str("status", 20, "identified"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dm_ofi_code"),
        ],
        [("ix_oe_dm_ofi_project", ["project_id"])],
    ),
]


def upgrade() -> None:
    """Create the eight tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)


def downgrade() -> None:
    """Drop the eight tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
