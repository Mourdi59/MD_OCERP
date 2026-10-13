# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""stakeholders - stakeholder register, communication, project organisation and mandates.

Ten new tables, nothing existing touched, all project-scoped and CASCADE with
the project: register settings, stakeholders (the project relation to a
contact, never a copy of the person), append-only assessments, communication
plan items, engagement events, commitments to stakeholders, project role
holders, governance bodies and their members, and the mandate matrix.

Tenant stakeholder frameworks live in the governance catalogue tables of v68
under kind ``stakeholder_framework``; no table here.

The mandate table carries a partial unique index on ``(project_id,
decision_type, scope) WHERE letter = 'D'``: exactly one decider per decision
type and scope, held by the database as well as the service. ``scope`` is NOT
NULL (``''`` = whole project) so the index sees one scope and not many NULLs.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v76_stakeholders
Revises: v74_design_management
Create Date: 2026-10-12
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v76_stakeholders"
down_revision: str | Sequence[str] | None = "v74_design_management"
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


def _fk(column: str, target: str, name: str, ondelete: str, nullable: bool) -> sa.Column:
    return sa.Column(column, GUID(), sa.ForeignKey(target, ondelete=ondelete, name=name), nullable=nullable)


# Defaults are the models' Python-side ones, so the helpers below declare none: a database built by this
# revision and one built by ``create_all`` then carry the same column defaults. The ``default`` arguments
# record what the model fills in and are not sent to the database. The one server default the model
# declares (mandate ``scope``) is spelled out where that column is created.
def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.String(length=length), nullable=nullable)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False)


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False)


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.Integer(), nullable=nullable)


def _guid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, GUID(), nullable=nullable)


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _date(name: str) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=True)


def _json(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=nullable)


_STK = "oe_stakeholders_stakeholder.id"
_Index = tuple[str, list[str], dict[str, Any]]

_TABLES: list[tuple[str, Callable[[], list], list[_Index]]] = [
    (
        "oe_stakeholders_settings",
        lambda: [
            _project_fk("fk_oe_stk_settings_project"),
            _str("framework_source", 20, "shipped"),
            _str("framework_id", 64, None),
            _int("framework_version"),
            _str("analysis_method", 64, "power_interest"),
            _int("review_interval_days", 90),
            _str("owner_area_code", 64, ""),
            _guid("commitment_route_id"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_stk_settings_project"),
        ],
        [],
    ),
    (
        "oe_stakeholders_stakeholder",
        lambda: [
            _project_fk("fk_oe_stk_stakeholder_project"),
            _str("code", 40, None),
            _str("display_name", 255),
            _str("category", 64, None),
            _guid("contact_id"),
            _bool("is_group", False),
            _int("group_size_estimate", nullable=True),
            _fk("parent_stakeholder_id", _STK, "fk_oe_stk_stakeholder_parent", "SET NULL", True),
            _guid("user_id"),
            _text("interests"),
            _text("expectations"),
            _text("concerns"),
            _guid("relationship_owner_user_id"),
            _json("geo", nullable=True),
            _bool("is_confidential", False),
            _str("status", 20, "active"),
            _guid("risk_id"),
            _ts("review_notified_at"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_stk_stakeholder_code"),
        ],
        [
            ("ix_oe_stakeholders_stakeholder_project_id_status", ["project_id", "status"], {}),
            ("ix_oe_stk_stakeholder_contact", ["contact_id"], {}),
        ],
    ),
    (
        "oe_stakeholders_assessment",
        lambda: [
            _project_fk("fk_oe_stk_assessment_project"),
            _fk("stakeholder_id", _STK, "fk_oe_stk_assessment_stakeholder", "CASCADE", False),
            _str("method_code", 64, None),
            _int("method_version"),
            _json("scores"),
            _str("classification", 64, None, nullable=True),
            _str("engagement_current", 32, None, nullable=True),
            _str("engagement_desired", 32, None, nullable=True),
            _int("attitude", nullable=True),
            _text("rationale"),
            _guid("assessed_by"),
            _ts("assessed_at", nullable=False),
        ],
        [("ix_oe_stk_assessment_stakeholder", ["stakeholder_id", "assessed_at"], {})],
    ),
    (
        "oe_stakeholders_plan_item",
        lambda: [
            _project_fk("fk_oe_stk_plan_project"),
            _str("title", 255, None),
            _text("purpose"),
            _text("key_message"),
            _json("audience_stakeholder_ids"),
            _json("audience_categories"),
            _guid("audience_body_id"),
            _str("participation_level", 32, None),
            _str("channel", 32, None),
            _str("format_code", 64, None, nullable=True),
            _str("frequency", 255, "once"),
            _str("trigger_kind", 20, None, nullable=True),
            _str("trigger_ref", 128),
            _date("triggered_on"),
            _guid("owner_user_id"),
            _date("starts_on"),
            _date("ends_on"),
            _str("status", 20, "planned"),
            _date("next_due"),
            _date("overdue_notified_for"),
            _guid("created_by"),
        ],
        [("ix_oe_stakeholders_plan_item_project_id_status", ["project_id", "status"], {})],
    ),
    (
        "oe_stakeholders_event",
        lambda: [
            _project_fk("fk_oe_stk_event_project"),
            _fk("plan_item_id", "oe_stakeholders_plan_item.id", "fk_oe_stk_event_plan", "SET NULL", True),
            _date("occurrence_date"),
            _str("format_code", 64, None, nullable=True),
            _str("participation_level", 32, None),
            _str("title", 255, None),
            _date("held_on"),
            _str("location", 255),
            _json("stakeholder_ids"),
            _int("attendance_count", nullable=True),
            _text("outcome"),
            _text("feedback_summary"),
            _guid("meeting_id"),
            _json("correspondence_ids"),
            _json("cde_container_ids"),
            _str("status", 20, "planned"),
            _ts("deleted_at"),
            _guid("created_by"),
        ],
        [
            ("ix_oe_stk_event_project", ["project_id", "held_on"], {}),
            ("ix_oe_stk_event_plan", ["plan_item_id", "occurrence_date"], {}),
        ],
    ),
    (
        "oe_stakeholders_commitment",
        lambda: [
            _project_fk("fk_oe_stk_commitment_project"),
            _str("code", 40, None),
            _json("stakeholder_ids"),
            _str("source_kind", 32, "manual"),
            _str("source_ref", 255),
            _json("source_snapshot"),
            sa.Column("text", sa.Text(), nullable=False),
            _str("category", 32, "other"),
            _guid("owner_user_id"),
            _date("due_date"),
            _text("verification"),
            sa.Column("cost_estimate", MoneyType(18, 4), nullable=True),
            _str("currency", 3),
            _guid("release_item_id"),
            _guid("task_id"),
            _guid("risk_id"),
            _guid("requirement_id"),
            _str("status", 20, "proposed"),
            _json("decision_ref"),
            _guid("approval_instance_id"),
            _str("pending_target", 20, None, nullable=True),
            _text("pending_rationale"),
            _text("withdraw_rationale"),
            _text("breach_rationale"),
            _ts("communicated_back_at"),
            _text("loop_not_required_rationale"),
            _date("breach_notified_on"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_stk_commitment_code"),
        ],
        [("ix_oe_stk_commitment_project", ["project_id", "status", "due_date"], {})],
    ),
    (
        "oe_stakeholders_role",
        lambda: [
            _project_fk("fk_oe_stk_role_project"),
            _str("role_code", 64, None),
            _str("custom_label", 255),
            _guid("roster_member_id"),
            _guid("holder_contact_id"),
            _guid("deputy_roster_member_id"),
            _date("valid_from"),
            _date("valid_to"),
            _text("conflict_rationale"),
            _guid("created_by"),
        ],
        [("ix_oe_stk_role_project", ["project_id", "role_code"], {})],
    ),
    (
        "oe_stakeholders_body",
        lambda: [
            _project_fk("fk_oe_stk_body_project"),
            _str("code", 64, None),
            _str("body_type", 64, None),
            _str("name", 255, None),
            _str("chair_role_code", 64, None, nullable=True),
            _str("quorum_kind", 20, "majority"),
            _int("quorum_min", nullable=True),
            _int("decision_level", 1),
            _str("meeting_series_ref", 64),
            _guid("terms_container_id"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_stk_body_code"),
        ],
        [],
    ),
    (
        "oe_stakeholders_body_member",
        lambda: [
            _project_fk("fk_oe_stk_member_project"),
            _fk("body_id", "oe_stakeholders_body.id", "fk_oe_stk_member_body", "CASCADE", False),
            _str("role_code", 64, None, nullable=True),
            _guid("user_id"),
            _guid("contact_id"),
            _bool("voting", True),
            _date("valid_from"),
            _date("valid_to"),
        ],
        [("ix_oe_stk_member_body", ["body_id"], {})],
    ),
    (
        "oe_stakeholders_mandate",
        lambda: [
            _project_fk("fk_oe_stk_mandate_project"),
            _str("decision_type", 64, None),
            sa.Column("scope", sa.String(length=128), nullable=False, server_default=""),
            _str("holder_kind", 10, None),
            _str("holder_code", 64, None),
            _str("letter", 1, None),
            _text("scope_note"),
            _json("limit_ref", nullable=True),
            sa.UniqueConstraint(
                "project_id", "decision_type", "scope", "holder_kind", "holder_code", name="uq_oe_stk_mandate_cell"
            ),
        ],
        [
            (
                "uq_oe_stk_mandate_decider",
                ["project_id", "decision_type", "scope"],
                {
                    "unique": True,
                    "postgresql_where": sa.text("letter = 'D'"),
                    "sqlite_where": sa.text("letter = 'D'"),
                },
            )
        ],
    ),
]


def upgrade() -> None:
    """Create the ten tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols, kw in indexes:
            if name not in existing:
                op.create_index(name, table, cols, **kw)


def downgrade() -> None:
    """Drop the ten tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
