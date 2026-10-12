# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""project governance - phases, gates, frame documents and tenant catalogues.

Ten new tables, nothing existing touched. Two hold catalogues a company builds
itself (a draft plus immutable published versions); the other eight are
project-scoped and CASCADE with the project: the pinned catalogue version, the
management areas with their owners, the gates, the frame documents (soft links
to CDE containers and revisions, no file copies), readiness checks per gate
attempt, immutable decisions with their snapshot, conditions and change
requests.

Every constraint and index name is written out and matches the model, because
generated names for these tables would pass 63 characters and be shortened by
a hash. Every step is inspector-guarded, so a database whose tables
``create_all`` already built reaches this revision and does nothing.

Revision ID: v68_project_governance
Revises: v67_statutory_tax_lines_and_submittal_register
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v68_project_governance"
down_revision: str | Sequence[str] | None = "v67_statutory_tax_lines_and_submittal_register"
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


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=False)
    return sa.Column(name, sa.Integer(), nullable=False, server_default=str(default))


def _guid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, GUID(), nullable=nullable)


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_governance_catalogue",
        lambda: [
            _str("tenant_id", 64, None),
            _str("kind", 40, "phase_model"),
            _str("code", 64, None),
            _str("name", 255),
            _str("based_on", 160),
            _str("state", 20, "draft"),
            _json("draft_body"),
            _guid("created_by"),
            sa.UniqueConstraint("tenant_id", "kind", "code", name="uq_oe_gov_catalogue_tenant_code"),
        ],
        [("ix_oe_gov_catalogue_tenant", ["tenant_id", "kind"])],
    ),
    (
        "oe_governance_catalogue_version",
        lambda: [
            sa.Column(
                "catalogue_id",
                GUID(),
                sa.ForeignKey("oe_governance_catalogue.id", ondelete="RESTRICT", name="fk_oe_gov_catver_catalogue"),
                nullable=False,
            ),
            _int("version"),
            _json("body"),
            _str("content_hash", 64, None),
            _guid("published_by"),
            _ts("published_at", nullable=False),
            sa.UniqueConstraint("catalogue_id", "version", name="uq_oe_gov_catver_version"),
        ],
        [("ix_oe_gov_catver_catalogue", ["catalogue_id"])],
    ),
    (
        "oe_governance_model",
        lambda: [
            _project_fk("fk_oe_gov_model_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("current_phase", 64, None, nullable=True),
            _bool("four_eyes", True),
            _guid("decision_route_id"),
            _guid("change_route_id"),
            _bool("stopped", False),
            _ts("stopped_at"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_gov_model_project"),
        ],
        [],
    ),
    (
        "oe_governance_area",
        lambda: [
            _project_fk("fk_oe_gov_area_project"),
            _str("code", 64, None),
            _str("name_override", 255),
            _int("sort_order", 0),
            _guid("owner_user_id"),
            _guid("deputy_user_id"),
            _bool("applicable", True),
            _text("na_rationale"),
            _bool("retired", False),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_gov_area_code"),
        ],
        [("ix_oe_gov_area_owner", ["owner_user_id"])],
    ),
    (
        "oe_governance_gate",
        lambda: [
            _project_fk("fk_oe_gov_gate_project"),
            _str("catalogue_id", 64, None),
            _str("code", 64, None),
            _str("from_phase", 64, None),
            _str("to_phase", 64, None),
            _int("sort_order", 0),
            _str("status", 20, "not_started"),
            _int("attempt_no", 1),
            _guid("schedule_activity_id"),
            _str("target_date", 40),
            _guid("approval_instance_id"),
            _str("hold_resume_date", 40),
            _str("last_outcome", 32),
            _bool("historic", False),
            _int("version", 1),
            sa.UniqueConstraint("project_id", "catalogue_id", "code", name="uq_oe_gov_gate_code"),
        ],
        [("ix_oe_gov_gate_project", ["project_id"])],
    ),
    (
        "oe_governance_document",
        lambda: [
            _project_fk("fk_oe_gov_document_project"),
            sa.Column(
                "area_id",
                GUID(),
                sa.ForeignKey("oe_governance_area.id", ondelete="CASCADE", name="fk_oe_gov_document_area"),
                nullable=False,
            ),
            _str("doc_type", 64, None),
            _json("required_at_gates"),
            _str("status", 20, "draft"),
            _guid("container_id"),
            _guid("bound_revision_id"),
            _str("bound_content_hash", 64, None, nullable=True),
            _guid("approved_gate_id"),
            _bool("read_only", False),
            sa.UniqueConstraint("project_id", "area_id", "doc_type", name="uq_oe_gov_document_type"),
        ],
        [("ix_oe_gov_document_project", ["project_id"])],
    ),
    (
        "oe_governance_check",
        lambda: [
            _project_fk("fk_oe_gov_check_project"),
            sa.Column(
                "gate_id",
                GUID(),
                sa.ForeignKey("oe_governance_gate.id", ondelete="CASCADE", name="fk_oe_gov_check_gate"),
                nullable=False,
            ),
            _int("attempt_no"),
            sa.Column(
                "area_id",
                GUID(),
                sa.ForeignKey("oe_governance_area.id", ondelete="CASCADE", name="fk_oe_gov_check_area"),
                nullable=False,
            ),
            _str("status", 20, "not_assessed"),
            _str("rag", 10),
            _text("note"),
            _guid("confirmed_by"),
            _ts("confirmed_at"),
            _json("confirmed_revisions"),
            _bool("stale", False),
            _text("na_rationale"),
            _json("criteria"),
            sa.UniqueConstraint("gate_id", "attempt_no", "area_id", name="uq_oe_gov_check_attempt_area"),
        ],
        [("ix_oe_gov_check_project", ["project_id"])],
    ),
    (
        "oe_governance_decision",
        lambda: [
            _project_fk("fk_oe_gov_decision_project"),
            sa.Column(
                "gate_id",
                GUID(),
                sa.ForeignKey("oe_governance_gate.id", ondelete="CASCADE", name="fk_oe_gov_decision_gate"),
                nullable=False,
            ),
            _str("gate_code", 64, None),
            _int("attempt_no"),
            _str("outcome", 32, None),
            _text("rationale"),
            _guid("decided_by", nullable=False),
            _ts("decided_at", nullable=False),
            _json("snapshot"),
            _json("proceed_at_risk_areas"),
            _json("accepted_not_applicable"),
            _str("hold_resume_date", 40),
            _guid("approval_instance_id"),
            sa.UniqueConstraint("gate_id", "attempt_no", name="uq_oe_gov_decision_attempt"),
        ],
        [("ix_oe_gov_decision_project", ["project_id"])],
    ),
    (
        "oe_governance_condition",
        lambda: [
            _project_fk("fk_oe_gov_condition_project"),
            sa.Column(
                "decision_id",
                GUID(),
                sa.ForeignKey("oe_governance_decision.id", ondelete="CASCADE", name="fk_oe_gov_condition_decision"),
                nullable=False,
            ),
            _guid("gate_id", nullable=False),
            _str("gate_code", 64, None),
            _str("area_code", 64, None, nullable=True),
            _str("document_type", 64, None, nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            _guid("owner_user_id"),
            _str("due_date", 40),
            _str("severity", 20, "essential"),
            _str("status", 20, "open"),
            _text("evidence"),
            _guid("cleared_by"),
            _ts("cleared_at"),
            _text("waiver_rationale"),
            _guid("waived_by"),
            _ts("waived_at"),
            _ts("escalated_at"),
        ],
        [
            ("ix_oe_gov_condition_project_status", ["project_id", "status"]),
            ("ix_oe_gov_condition_decision", ["decision_id"]),
        ],
    ),
    (
        "oe_governance_change_request",
        lambda: [
            _project_fk("fk_oe_gov_change_project"),
            sa.Column(
                "document_id",
                GUID(),
                sa.ForeignKey("oe_governance_document.id", ondelete="CASCADE", name="fk_oe_gov_change_document"),
                nullable=False,
            ),
            _guid("previous_revision_id"),
            _guid("proposed_revision_id", nullable=False),
            _str("proposed_content_hash", 64, None, nullable=True),
            _text("reason"),
            _text("impact"),
            _str("status", 20, "submitted"),
            _guid("approval_instance_id"),
            _guid("requested_by"),
            _guid("decided_by"),
            _ts("decided_at"),
        ],
        [("ix_oe_gov_change_document", ["document_id"])],
    ),
]


def upgrade() -> None:
    """Create the ten tables and their indexes, each only when it is missing."""
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
    """Drop the ten tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
