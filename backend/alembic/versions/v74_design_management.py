# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""design management - design organisation, schedule, numbering, register, distribution, reports, permits.

Thirteen new tables, nothing existing touched, all project-scoped and CASCADE
with the project: the per-project setup (pinned numbering scheme and reports
catalogue), design roles, approval points, design schedule lines, the 1:1
register extension of a CDE container, numbering counters, the distribution
matrix, releases, internal reviews and their comments, expert reports, permit
packages and their items.

The WBS stays ``oe_projects_wbs`` with no DDL (SPEC decision 2: running
installs may hold duplicate codes, the unique rule is enforced in the service
and the rule set first). Numbering schemes and reports catalogues a company
builds itself live in the governance catalogue tables of v68 under their own
``kind``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v74_design_management
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v74_design_management"
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


def _fk(column: str, target: str, name: str) -> sa.Column:
    return sa.Column(column, GUID(), sa.ForeignKey(target, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _nstr(name: str, length: int) -> sa.Column:
    return sa.Column(name, sa.String(length=length), nullable=True)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=False)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def _guid(name: str) -> sa.Column:
    return sa.Column(name, GUID(), nullable=True)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_design_setup",
        lambda: [
            _project_fk("fk_oe_dsg_setup_project"),
            _str("scheme_source", 20, "shipped"),
            _str("scheme_id", 64, None),
            _int("scheme_version"),
            _str("reports_source", 20, "shipped"),
            _str("reports_id", 64, None),
            _int("reports_version"),
            _json("previous_schemes"),
            _bool("four_eyes_release", True),
            _str("default_distribution_purpose", 30, "for_information"),
            _guid("lead_designer_role_id"),
            _bool("hierarchical_codes", True),
            _str("wbs_separator", 1, "."),
            _json("target_suitability"),
            _guid("approval_route_id"),
            _guid("release_route_id"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_dsg_setup_project"),
        ],
        [],
    ),
    (
        "oe_design_role",
        lambda: [
            _project_fk("fk_oe_dsg_role_project"),
            _str("code", 40, None),
            _str("title", 255),
            _str("party_kind", 30, None),
            _nstr("discipline_code", 20),
            _guid("contact_id"),
            _guid("user_id"),
            _nstr("originator_code", 20),
            _guid("contract_package_id"),
            _json("responsible_wbs_ids"),
            _str("status", 20, "planned"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_role_code"),
        ],
        [("ix_oe_dsg_role_originator", ["project_id", "originator_code"])],
    ),
    (
        "oe_design_approval_point",
        lambda: [
            _project_fk("fk_oe_dsg_ap_project"),
            _str("code", 40, None),
            _str("title", 255),
            _nstr("phase_code", 64),
            _str("kind", 30, None),
            _guid("governance_gate_id"),
            _guid("approver_role_id"),
            _str("status", 20, "open"),
            _guid("approval_instance_id"),
            _guid("submitted_by"),
            _guid("decided_by"),
            _ts("decided_at"),
            _text("note"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_ap_code"),
        ],
        [("ix_oe_dsg_ap_instance", ["approval_instance_id"])],
    ),
    (
        "oe_design_deliverable",
        lambda: [
            _project_fk("fk_oe_dsg_deliverable_project"),
            _str("code", 40, None),
            _str("title", 255),
            _str("phase_code", 64, None),
            _guid("role_id"),
            _nstr("discipline_code", 20),
            _nstr("form_code", 20),
            _guid("wbs_node_id"),
            _int("planned_count", 1),
            _text("planned_count_rationale"),
            _guid("schedule_activity_id"),
            _bool("required", True),
            _json("required_for"),
            _nstr("target_suitability", 10),
            _bool("waived", False),
            _text("waived_rationale"),
            _str("status", 30, "not_started"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_deliverable_code"),
        ],
        [("ix_oe_dsg_deliverable_phase", ["project_id", "phase_code"])],
    ),
    (
        "oe_design_drawing",
        lambda: [
            _project_fk("fk_oe_dsg_drawing_project"),
            _fk("container_id", "oe_cde_container.id", "fk_oe_dsg_drawing_container"),
            _str("title", 500),
            _str("scale", 40),
            _str("sheet_size", 10),
            _nstr("phase_code", 64),
            _guid("deliverable_id"),
            _guid("wbs_node_id"),
            _guid("role_id"),
            _nstr("planned_first_issue", 10),
            _nstr("forecast_issue", 10),
            _guid("schedule_activity_id"),
            _guid("superseded_by_container_id"),
            _str("scheme_id", 64),
            _int("scheme_version", 0),
            _bool("legacy_scheme", False),
            _json("aliases"),
            _nstr("title_block_number", 255),
            sa.UniqueConstraint("container_id", name="uq_oe_dsg_drawing_container"),
        ],
        [
            ("ix_oe_dsg_drawing_project", ["project_id"]),
            ("ix_oe_dsg_drawing_deliverable", ["deliverable_id"]),
        ],
    ),
    (
        "oe_design_number_counter",
        lambda: [
            _project_fk("fk_oe_dsg_counter_project"),
            _str("scope_key", 255, None),
            _int("next_value", 1),
            sa.UniqueConstraint("project_id", "scope_key", name="uq_oe_dsg_counter_scope"),
        ],
        [],
    ),
    (
        "oe_design_dist_rule",
        lambda: [
            _project_fk("fk_oe_dsg_dist_rule_project"),
            _guid("recipient_list_id"),
            _guid("recipient_role_id"),
            _json("discipline_codes"),
            _json("form_codes"),
            _json("phase_codes"),
            _json("wbs_node_ids"),
            _nstr("min_suitability", 10),
            _str("purpose", 30, "for_information"),
            _str("format", 10, "pdf"),
            _int("copies_paper", 0),
            _bool("ack_required", False),
            _bool("active", True),
        ],
        [("ix_oe_dsg_dist_rule_project", ["project_id"])],
    ),
    (
        "oe_design_release",
        lambda: [
            _project_fk("fk_oe_dsg_release_project"),
            _str("code", 40, None),
            _str("title", 255),
            _str("purpose", 30, "for_information"),
            _json("revision_ids"),
            _str("status", 20, "draft"),
            _json("transmittal_ids"),
            _json("issue_plan"),
            _text("duplicate_reason"),
            _guid("approval_instance_id"),
            _guid("prepared_by"),
            _guid("issued_by"),
            _ts("issued_at"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_release_code"),
        ],
        [("ix_oe_dsg_release_instance", ["approval_instance_id"])],
    ),
    (
        "oe_design_review",
        lambda: [
            _project_fk("fk_oe_dsg_review_project"),
            _str("code", 40, None),
            _str("title", 255),
            _str("phase_code", 64, None),
            _json("deliverable_ids"),
            _json("reviewer_role_ids"),
            _str("status", 20, "planned"),
            _nstr("outcome", 30),
            _guid("concluded_by"),
            _ts("concluded_at"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_review_code"),
        ],
        [],
    ),
    (
        "oe_design_review_comment",
        lambda: [
            _project_fk("fk_oe_dsg_comment_project"),
            _fk("review_id", "oe_design_review.id", "fk_oe_dsg_comment_review"),
            _guid("container_id"),
            _guid("revision_id"),
            sa.Column("text", sa.Text(), nullable=False),
            _str("severity", 10, "minor"),
            _str("status", 20, "open"),
            _text("answer"),
            _guid("answered_by_role_id"),
            _guid("created_by"),
        ],
        [("ix_oe_dsg_comment_review", ["review_id"])],
    ),
    (
        "oe_design_report",
        lambda: [
            _project_fk("fk_oe_dsg_report_project"),
            _str("code", 40, None),
            _str("kind_code", 40, None),
            _str("title", 255),
            _nstr("phase_code", 64),
            _guid("author_role_id"),
            _guid("container_id"),
            _guid("checker_role_id"),
            _bool("external_check", False),
            _guid("review_cycle_id"),
            _bool("required", True),
            _str("required_reason", 20, "manual"),
            _str("independent_check", 20, "none"),
            _bool("hint_overridden", False),
            _text("rationale"),
            _str("status", 20, "required"),
            _text("conditions_text"),
            _json("governance_condition_ids"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_report_code"),
        ],
        [("ix_oe_dsg_report_cycle", ["review_cycle_id"])],
    ),
    (
        "oe_design_permit",
        lambda: [
            _project_fk("fk_oe_dsg_permit_project"),
            _str("code", 40, None),
            _str("title", 255),
            _str("profile_code", 40, None),
            _guid("authority_submission_id"),
            _guid("review_cycle_id"),
            _guid("permit_application_id"),
            _nstr("target_submission_date", 10),
            _guid("schedule_activity_id"),
            _str("status", 20, "assembling"),
            _guid("submitted_by"),
            _ts("submitted_at"),
            _bool("superseded_content", False),
            _json("conditions"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dsg_permit_code"),
        ],
        [("ix_oe_dsg_permit_cycle", ["review_cycle_id"])],
    ),
    (
        "oe_design_permit_item",
        lambda: [
            _project_fk("fk_oe_dsg_permit_item_project"),
            _fk("permit_id", "oe_design_permit.id", "fk_oe_dsg_permit_item_permit"),
            _str("kind", 10, None),
            _str("title", 255),
            _guid("container_id"),
            _guid("report_id"),
            _bool("required", True),
            _guid("included_revision_id"),
        ],
        [("ix_oe_dsg_permit_item_permit", ["permit_id"])],
    ),
]


def upgrade() -> None:
    """Create the thirteen tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        inspector = sa.inspect(bind)
        if table not in inspector.get_table_names():
            op.create_table(table, *_base(), *columns())
        existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(table)}
        for name, cols in indexes:
            if name not in existing:
                op.create_index(name, table, cols)


def downgrade() -> None:
    """Drop the thirteen tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
