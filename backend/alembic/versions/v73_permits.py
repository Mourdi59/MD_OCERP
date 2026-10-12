# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""permits - permit roadmap and consolidated permit-condition register.

Ten new tables, nothing existing touched, all project-scoped and CASCADE with
the project: the roadmap (pinned ``permit_type`` catalogue and settings),
requirements and their typed dependencies, applications with clock events,
immutable decisions, permits, conditions, condition evidence and immutable
discharges.

Tenant ``permit_type`` catalogues live in the governance catalogue tables of
v68 under their own ``kind``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and only adds what is missing.

Revision ID: v73_permits
Revises: v70_delivery_model
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v73_permits"
down_revision: str | Sequence[str] | None = "v70_delivery_model"
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


def _str(name: str, length: int, default: str | None = "") -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=False)
    return sa.Column(name, sa.String(length=length), nullable=False, server_default=default)


def _nstr(name: str, length: int) -> sa.Column:
    return sa.Column(name, sa.String(length=length), nullable=True)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _int(name: str, default: int | None = None, nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.Integer(), nullable=nullable)
    return sa.Column(name, sa.Integer(), nullable=nullable, server_default=str(default))


def _guid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, GUID(), nullable=nullable)


def _date(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.Date(), nullable=nullable)


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


_REQ = "oe_permits_requirement.id"
_APP = "oe_permits_application.id"
_PERMIT = "oe_permits_permit.id"
_COND = "oe_permits_condition.id"

_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_permits_roadmap",
        lambda: [
            _project_fk("fk_oe_permits_roadmap_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("jurisdiction", 12),
            _guid("route_assessment_id"),
            _guid("delivery_model_id"),
            sa.Column(
                "governance_document_id",
                GUID(),
                sa.ForeignKey(
                    "oe_governance_document.id", ondelete="SET NULL", name="fk_oe_permits_roadmap_governance_document"
                ),
                nullable=True,
            ),
            _str("status", 20, "draft"),
            _str("roadmap_area_code", 64),
            _str("conditions_area_code", 64),
            _bool("internal_review", False),
            _guid("approval_route_id"),
            _int("escalation_days", 7),
            _int("buffer_days", 14),
            _json("consumed_change_request_ids"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_permits_roadmap_project"),
        ],
        [],
    ),
    (
        "oe_permits_requirement",
        lambda: [
            _project_fk("fk_oe_permits_requirement_project"),
            _str("permit_type_code", 64, None),
            _str("title", 255),
            _bool("applicable", True),
            _text("applicability_rationale"),
            _str("applicant_role", 20, "owner"),
            _str("applicant_source", 20, "catalogue"),
            _text("applicant_rationale"),
            _str("applicant_party", 255),
            _guid("applicant_contact_id"),
            _guid("responsible_user_id"),
            _date("planned_submit_date"),
            _guid("needed_by_activity_id"),
            _date("needed_by_date"),
            _str("clock_variant", 40),
            _date("expected_decision_date"),
            _guid("schedule_activity_id"),
            _str("governance_area_code", 64),
            _bool("conflict_accepted", False),
            _guid("follow_up_of_id"),
            _str("proposed_from_route", 40),
            _int("sort_order", 0),
        ],
        [
            ("ix_oe_permits_requirement_project", ["project_id", "permit_type_code"]),
            ("ix_oe_permits_requirement_activity", ["project_id", "needed_by_activity_id"]),
        ],
    ),
    (
        "oe_permits_requirement_dependency",
        lambda: [
            _project_fk("fk_oe_permits_dependency_project"),
            _fk("requirement_id", _REQ, "fk_oe_permits_dependency_req"),
            _fk("depends_on_id", _REQ, "fk_oe_permits_dependency_on"),
            _str("dep_type", 12, "granted"),
            sa.UniqueConstraint("requirement_id", "depends_on_id", name="uq_oe_permits_dependency"),
        ],
        [("ix_oe_permits_dependency_project", ["project_id"])],
    ),
    (
        "oe_permits_application",
        lambda: [
            _project_fk("fk_oe_permits_application_project"),
            _fk("requirement_id", _REQ, "fk_oe_permits_application_req"),
            _int("attempt", 1),
            _str("kind", 30, "new"),
            _guid("parent_permit_id"),
            _json("discharges_condition_ids"),
            _str("applicant_role", 20),
            _str("applicant_source", 20),
            _str("authority_name", 255),
            _str("authority_reference", 120),
            _date("submitted_at"),
            _date("received_at"),
            _date("validated_at"),
            _json("review_cycle_ids"),
            _guid("submission_id"),
            _guid("cde_container_id"),
            _guid("approval_instance_id"),
            _str("status", 30, "planned"),
            _text("appeal_note"),
            _guid("created_by"),
            sa.UniqueConstraint("requirement_id", "kind", "attempt", name="uq_oe_permits_application_attempt"),
        ],
        [("ix_oe_permits_application_state", ["project_id", "status"])],
    ),
    (
        "oe_permits_clock_event",
        lambda: [
            _project_fk("fk_oe_permits_clock_event_project"),
            _fk("application_id", _APP, "fk_oe_permits_clock_event_app"),
            _str("kind", 30, None),
            _date("event_date", nullable=False),
            _int("period", nullable=True),
            _nstr("unit", 20),
            _text("reason"),
            _guid("created_by"),
        ],
        [("ix_oe_permits_clock_event_app", ["application_id"])],
    ),
    (
        "oe_permits_decision",
        lambda: [
            _project_fk("fk_oe_permits_decision_project"),
            _fk("application_id", _APP, "fk_oe_permits_decision_app"),
            _int("revision", 1),
            _guid("supersedes_id"),
            _str("outcome", 30, None),
            _date("decision_date", nullable=False),
            _date("served_date"),
            _str("reference", 120),
            _text("scope_note"),
            _json("scope_activity_ids"),
            _bool("conditions_pending", False),
            _date("appeal_deadline"),
            _guid("document_revision_id"),
            _str("content_hash", 64),
            _bool("deemed", False),
            _guid("decided_by"),
            _json("snapshot"),
            sa.UniqueConstraint("application_id", "revision", name="uq_oe_permits_decision_revision"),
        ],
        [],
    ),
    (
        "oe_permits_permit",
        lambda: [
            _project_fk("fk_oe_permits_permit_project"),
            _fk("requirement_id", _REQ, "fk_oe_permits_permit_req"),
            _guid("application_id", nullable=False),
            _guid("decision_id", nullable=False),
            _str("permit_type_code", 64, None),
            _str("scope", 20, "full"),
            _str("status", 20, "in_force"),
            _str("reference", 120),
            _bool("revocable", False),
            sa.Column("security_amount", MoneyType(18, 4), nullable=True),
            _str("security_currency", 3),
            _date("start_notified_at"),
            _date("paused_since"),
            _date("valid_until"),
            _guid("superseded_by_id"),
            sa.UniqueConstraint("decision_id", name="uq_oe_permits_permit_decision"),
        ],
        [("ix_oe_permits_permit_state", ["project_id", "status"])],
    ),
    (
        "oe_permits_condition",
        lambda: [
            _project_fk("fk_oe_permits_condition_project"),
            _fk("permit_id", _PERMIT, "fk_oe_permits_condition_permit"),
            _str("number", 40, None),
            _text("text"),
            _str("text_hash", 64),
            _str("kind", 30, "obligation"),
            _str("national_kind", 64),
            _str("trigger", 30),
            _str("stage_ref", 120),
            _text("event_text"),
            _date("due_date"),
            _str("topic", 20, "other"),
            _str("purpose", 20),
            _guid("owner_user_id"),
            _guid("evidence_submitted_by"),
            _str("responsible_party", 255),
            _bool("requires_authority_approval", False),
            _text("evidence_required"),
            _guid("requirement_id"),
            sa.Column("hse_override", sa.Boolean(), nullable=True),
            _str("status", 30, "open"),
            _str("source", 20, "manual"),
            sa.Column("confidence", MoneyType(5, 4), nullable=True),
            _str("text_span", 40),
            _text("source_passage"),
            _bool("confirmed", True),
            _guid("gate_condition_id"),
            _guid("original_id"),
            _guid("decision_id"),
            _str("breach_ref_kind", 30),
            _guid("breach_ref_id"),
            _text("breach_note"),
            _ts("overdue_notified_at"),
            _ts("escalated_at"),
            _guid("created_by"),
            sa.UniqueConstraint("permit_id", "number", name="uq_oe_permits_condition_number"),
        ],
        [
            ("ix_oe_permits_condition_state", ["project_id", "status"]),
            ("ix_oe_permits_condition_trigger", ["project_id", "trigger", "status"]),
            ("ix_oe_permits_condition_due", ["project_id", "due_date"]),
        ],
    ),
    (
        "oe_permits_condition_evidence",
        lambda: [
            _project_fk("fk_oe_permits_evidence_project"),
            _fk("condition_id", _COND, "fk_oe_permits_evidence_condition"),
            _str("kind", 30, None),
            _str("ref_id", 500),
            _str("content_hash", 64),
            _text("note"),
            _guid("added_by"),
        ],
        [("ix_oe_permits_evidence_condition", ["condition_id"])],
    ),
    (
        "oe_permits_condition_discharge",
        lambda: [
            _project_fk("fk_oe_permits_discharge_project"),
            _fk("condition_id", _COND, "fk_oe_permits_discharge_condition"),
            _str("mode", 30, None),
            _guid("decided_by"),
            _guid("discharge_application_id"),
            _guid("verifier_user_id"),
            _date("discharged_on", nullable=False),
            _guid("document_revision_id"),
            _text("note"),
            _json("evidence_snapshot"),
            _guid("carried_from_id"),
        ],
        [("ix_oe_permits_discharge_condition", ["condition_id"])],
    ),
]


def upgrade() -> None:
    """Create the ten tables and their indexes, each only when it is missing."""
    bind = op.get_bind()
    for table, columns, indexes in _TABLES:
        if table not in sa.inspect(bind).get_table_names():
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
