# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""quality concept - requirements, certification, proofs, stages, acceptance, preservation.

Thirteen new ``oe_qconcept_*`` tables plus seven nullable link columns on
existing tables (test result calibration, hold gate and NCR package, handover
regime and packages, commissioning system plant item and checklist stage).

MUST be RUN on an existing installation: ``create_all(checkfirst)`` skips a
table that already exists, so the added columns on existing tables only arrive
through this revision.

Every column, constraint and index is written out here and none is read from
the models, so a later model change cannot alter this revision; a test compares
the schema it builds with the one the models build. Every step is
inspector-guarded, so a database whose new tables ``create_all`` already built
reaches this revision and only adds what is missing.

Revision ID: v75_quality_concept
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v75_quality_concept"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, type) added to existing tables; all nullable, no default.
_COLUMNS: list[tuple[str, str, Callable[[], sa.types.TypeEngine]]] = [
    ("oe_cc_test_result", "calibration_id", lambda: sa.String(36)),
    ("oe_cc_hold_gate", "package_ref", lambda: sa.String(64)),
    ("oe_cc_handover_package", "regime_code", lambda: sa.String(40)),
    ("oe_cc_handover_package", "package_refs", sa.JSON),
    ("oe_ncr_ncr", "package_ref", lambda: sa.String(64)),
    ("oe_commissioning_system", "plant_item_id", lambda: sa.String(36)),
    ("oe_commissioning_checklist", "stage_code", lambda: sa.String(40)),
]


def _oe_qconcept_concept() -> None:
    op.create_table(
        "oe_qconcept_concept",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_concept_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("catalogue_source", sa.String(20), nullable=False),
        sa.Column("catalogue_id", sa.String(64), nullable=False),
        sa.Column("catalogue_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("governance_doc_id", GUID(), nullable=True),
        sa.Column("requirement_set_id", GUID(), nullable=True),
        sa.Column("documentation_set_code", sa.String(40), nullable=True),
        sa.Column("packages", sa.JSON(), nullable=False),
        sa.Column("holidays", sa.JSON(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("submitted_by", GUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", name="uq_oe_qconcept_concept_project"),
    )


def _oe_qconcept_revision() -> None:
    op.create_table(
        "oe_qconcept_revision",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_revision_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            GUID(),
            sa.ForeignKey(
                "oe_qconcept_concept.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_revision_concept_id_oe_qconcept_concept",
            ),
            nullable=False,
        ),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("concept_id", "revision_no", name="uq_oe_qconcept_revision_no"),
    )
    op.create_index("ix_oe_qconcept_revision_project", "oe_qconcept_revision", ["project_id"])


def _oe_qconcept_standard() -> None:
    op.create_table(
        "oe_qconcept_standard",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_standard_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("edition", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("family_code", sa.String(64), nullable=True),
        sa.Column("discipline", sa.String(40), nullable=False),
        sa.Column("package_refs", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("mandate", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_standard_project", "oe_qconcept_standard", ["project_id"])


def _oe_qconcept_cert_target() -> None:
    op.create_table(
        "oe_qconcept_cert_target",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_cert_target_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("scheme_code", sa.String(64), nullable=False),
        sa.Column("scheme_version", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("target_level", sa.String(40), nullable=False),
        sa.Column("achieved_level", sa.String(40), nullable=True),
        sa.Column("assessor_contact_id", GUID(), nullable=True),
        sa.Column("registration_no", sa.String(120), nullable=False),
        sa.Column("points_available", sa.Numeric(12, 4), nullable=True),
        sa.Column("certificate_cde_id", GUID(), nullable=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("registered_on", sa.String(40), nullable=True),
        sa.Column("certified_on", sa.String(40), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_cert_project", "oe_qconcept_cert_target", ["project_id"])


def _oe_qconcept_credit() -> None:
    op.create_table(
        "oe_qconcept_credit",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_credit_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            GUID(),
            sa.ForeignKey(
                "oe_qconcept_cert_target.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_credit_target_id_oe_qconcept_cert_target",
            ),
            nullable=False,
        ),
        sa.Column("credit_code", sa.String(64), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("points_targeted", sa.Numeric(12, 4), nullable=False),
        sa.Column("points_achieved", sa.Numeric(12, 4), nullable=True),
        sa.Column("owner_user_id", GUID(), nullable=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("target_id", "credit_code", name="uq_oe_qconcept_credit_code"),
    )
    op.create_index("ix_oe_qconcept_credit_project", "oe_qconcept_credit", ["project_id"])


def _oe_qconcept_proof() -> None:
    op.create_table(
        "oe_qconcept_proof",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id", ondelete="CASCADE", name="fk_oe_qconcept_proof_project_id_oe_projects_project"
            ),
            nullable=False,
        ),
        sa.Column("package_ref", sa.String(64), nullable=True),
        sa.Column("plant_item_id", sa.String(36), nullable=True),
        sa.Column("cx_system_id", GUID(), nullable=True),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("deliverer_role", sa.String(30), nullable=False),
        sa.Column("deliverer_contact_id", GUID(), nullable=True),
        sa.Column("required_by_kind", sa.String(20), nullable=False),
        sa.Column("required_by_ref", sa.String(64), nullable=False),
        sa.Column("quantity_rule", sa.JSON(), nullable=False),
        sa.Column("review_by_role", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("decision_rationale", sa.Text(), nullable=False),
        sa.Column("requested_by", GUID(), nullable=True),
        sa.Column("decided_by", GUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_instance_id", GUID(), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_proof_package", "oe_qconcept_proof", ["project_id", "package_ref"])
    op.create_index("ix_oe_qconcept_proof_project", "oe_qconcept_proof", ["project_id"])


def _oe_qconcept_evidence_link() -> None:
    op.create_table(
        "oe_qconcept_evidence_link",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_evidence_link_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("owner_kind", sa.String(30), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("link_kind", sa.String(40), nullable=False),
        sa.Column("link_id", sa.String(36), nullable=False),
        sa.Column("retest_of", sa.String(36), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", GUID(), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_kind", "owner_id", "link_kind", "link_id", name="uq_oe_qconcept_link"),
    )
    op.create_index("ix_oe_qconcept_link_owner", "oe_qconcept_evidence_link", ["owner_kind", "owner_id"])
    op.create_index("ix_oe_qconcept_link_project", "oe_qconcept_evidence_link", ["project_id"])
    op.create_index("ix_oe_qconcept_link_target", "oe_qconcept_evidence_link", ["link_kind", "link_id"])


def _oe_qconcept_stage_def() -> None:
    op.create_table(
        "oe_qconcept_stage_def",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_stage_def_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("name_override", sa.String(255), nullable=False),
        sa.Column("owner_user_id", GUID(), nullable=True),
        sa.Column("release_party_role", sa.String(10), nullable=False),
        sa.Column("release_user_ids", sa.JSON(), nullable=False),
        sa.Column("preconditions", sa.JSON(), nullable=False),
        sa.Column("evidence_types", sa.JSON(), nullable=False),
        sa.Column("applies_to", sa.JSON(), nullable=False),
        sa.Column("catalogue_code", sa.String(40), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "code", name="uq_oe_qconcept_stage_code"),
    )
    op.create_index("ix_oe_qconcept_stage_project", "oe_qconcept_stage_def", ["project_id"])


def _oe_qconcept_stage_progress() -> None:
    op.create_table(
        "oe_qconcept_stage_progress",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_stage_progress_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("system_id", GUID(), nullable=False),
        sa.Column("stage_code", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("depends_on_system_ids", sa.JSON(), nullable=False),
        sa.Column("hold_gate_id", GUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", GUID(), nullable=True),
        sa.Column("last_issue_id", GUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("system_id", "stage_code", name="uq_oe_qconcept_progress_unit_stage"),
    )
    op.create_index("ix_oe_qconcept_progress_gate", "oe_qconcept_stage_progress", ["hold_gate_id"])
    op.create_index("ix_oe_qconcept_progress_project", "oe_qconcept_stage_progress", ["project_id"])


def _oe_qconcept_acceptance_unit() -> None:
    op.create_table(
        "oe_qconcept_acceptance_unit",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_acceptance_unit_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("package_refs", sa.JSON(), nullable=False),
        sa.Column("section_ref", sa.String(255), nullable=False),
        sa.Column("regime_code", sa.String(40), nullable=True),
        sa.Column("planned_date", sa.String(40), nullable=True),
        sa.Column("schedule_activity_id", sa.String(36), nullable=True),
        sa.Column("preconditions", sa.JSON(), nullable=False),
        sa.Column("handover_package_id", GUID(), nullable=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("completion_notice_at", sa.String(40), nullable=True),
        sa.Column("use_started_at", sa.String(40), nullable=True),
        sa.Column("deadline_at", sa.String(40), nullable=True),
        sa.Column("accepted_on", sa.String(40), nullable=True),
        sa.Column("reservations", sa.JSON(), nullable=False),
        sa.Column("refusal_reason", sa.Text(), nullable=False),
        sa.Column("refusal_defects", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_unit_project", "oe_qconcept_acceptance_unit", ["project_id"])


def _oe_qconcept_effect() -> None:
    op.create_table(
        "oe_qconcept_effect",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_effect_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column(
            "unit_id",
            GUID(),
            sa.ForeignKey(
                "oe_qconcept_acceptance_unit.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_effect_unit_id_oe_qconcept_acceptance_unit",
            ),
            nullable=False,
        ),
        sa.Column("effect", sa.String(40), nullable=False),
        sa.Column("effective_date", sa.String(40), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("outcome", sa.JSON(), nullable=False),
        sa.Column("confirmed_by", GUID(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("unit_id", "effect", name="uq_oe_qconcept_effect_unit"),
    )
    op.create_index("ix_oe_qconcept_effect_project", "oe_qconcept_effect", ["project_id"])


def _oe_qconcept_preservation() -> None:
    op.create_table(
        "oe_qconcept_preservation",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_preservation_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("subject_kind", sa.String(40), nullable=False),
        sa.Column("subject_ref", sa.String(64), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("parcel", sa.String(120), nullable=False),
        sa.Column("owner_contact_id", GUID(), nullable=True),
        sa.Column("influence_triggers", sa.JSON(), nullable=False),
        sa.Column("trigger_activities", sa.JSON(), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("methods", sa.JSON(), nullable=False),
        sa.Column("surveyor_contact_id", GUID(), nullable=True),
        sa.Column("planned_date", sa.String(40), nullable=True),
        sa.Column("survey_date", sa.String(40), nullable=True),
        sa.Column("invitation_sent_on", sa.String(40), nullable=True),
        sa.Column("owner_acknowledged", sa.Boolean(), nullable=True),
        sa.Column("acknowledgment_cde_id", GUID(), nullable=True),
        sa.Column("access_refused_on", sa.String(40), nullable=True),
        sa.Column("access_refusal_note", sa.Text(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("paired_with_id", GUID(), nullable=True),
        sa.Column("lat", sa.Numeric(10, 7), nullable=True),
        sa.Column("lng", sa.Numeric(10, 7), nullable=True),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_preservation_project", "oe_qconcept_preservation", ["project_id"])


def _oe_qconcept_expert_report() -> None:
    op.create_table(
        "oe_qconcept_expert_report",
        sa.Column(
            "project_id",
            GUID(),
            sa.ForeignKey(
                "oe_projects_project.id",
                ondelete="CASCADE",
                name="fk_oe_qconcept_expert_report_project_id_oe_projects_project",
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("expert_contact_id", GUID(), nullable=True),
        sa.Column("trigger", sa.String(255), nullable=False),
        sa.Column("frequency", sa.String(64), nullable=False),
        sa.Column("due_dates", sa.JSON(), nullable=False),
        sa.Column("commitment_ref", sa.String(64), nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_oe_qconcept_expert_project", "oe_qconcept_expert_report", ["project_id"])


# Parent before child, so the foreign keys inside the module resolve in order.
_TABLES: list[tuple[str, Callable[[], None]]] = [
    ("oe_qconcept_concept", _oe_qconcept_concept),
    ("oe_qconcept_revision", _oe_qconcept_revision),
    ("oe_qconcept_standard", _oe_qconcept_standard),
    ("oe_qconcept_cert_target", _oe_qconcept_cert_target),
    ("oe_qconcept_credit", _oe_qconcept_credit),
    ("oe_qconcept_proof", _oe_qconcept_proof),
    ("oe_qconcept_evidence_link", _oe_qconcept_evidence_link),
    ("oe_qconcept_stage_def", _oe_qconcept_stage_def),
    ("oe_qconcept_stage_progress", _oe_qconcept_stage_progress),
    ("oe_qconcept_acceptance_unit", _oe_qconcept_acceptance_unit),
    ("oe_qconcept_effect", _oe_qconcept_effect),
    ("oe_qconcept_preservation", _oe_qconcept_preservation),
    ("oe_qconcept_expert_report", _oe_qconcept_expert_report),
]


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table, create in _TABLES:
        if table not in existing:
            create()
    for table, column, type_ in _COLUMNS:
        if table in existing and column not in {c["name"] for c in inspector.get_columns(table)}:
            op.add_column(table, sa.Column(column, type_(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    for table, column, _type in reversed(_COLUMNS):
        if table in existing and column in {c["name"] for c in inspector.get_columns(table)}:
            op.drop_column(table, column)
    for table, _create in reversed(_TABLES):
        if table in existing:
            op.drop_table(table)
