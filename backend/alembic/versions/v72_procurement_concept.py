# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""procurement concept - award packages, procedures, prequalification, market sounding, frameworks.

Eight new tables, nothing existing touched. Seven are project-scoped and
CASCADE with the project: the concept (pinned catalogue, jurisdiction, client
type, lifecycle), award packages (1:1 procurement attributes of module 3's
ContractPackage; the id IS the ContractPackage id, a soft link because module
3 ships in its own revision), prequalification profiles, candidates with their
criterion scores and project references, and market soundings. Framework
agreements are tenant-level (``tenant_id``), because they outlive projects.

Procurement catalogues a company builds itself live in the governance
catalogue tables of v68 under ``kind = procurement_procedures``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v72_procurement_concept
Revises: v71_plant_register
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v72_procurement_concept"
down_revision: str | Sequence[str] | None = "v71_plant_register"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"
_CANDIDATE = "oe_procurement_concept_candidate.id"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _project_fk(name: str) -> sa.Column:
    return sa.Column("project_id", GUID(), sa.ForeignKey(_PROJECT, ondelete="CASCADE", name=name), nullable=False)


def _candidate_fk(name: str) -> sa.Column:
    return sa.Column("candidate_id", GUID(), sa.ForeignKey(_CANDIDATE, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def _text(name: str) -> sa.Column:
    return sa.Column(name, sa.Text(), nullable=False, server_default="")


def _bool(name: str, default: bool) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("true" if default else "false"))


def _nbool(name: str) -> sa.Column:
    return sa.Column(name, sa.Boolean(), nullable=True)


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


def _money(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, MoneyType(18, 2), nullable=nullable)


def _num(name: str, precision: int, scale: int, nullable: bool = False) -> sa.Column:
    if nullable:
        return sa.Column(name, sa.Numeric(precision, scale), nullable=True)
    return sa.Column(name, sa.Numeric(precision, scale), nullable=False, server_default="0")


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_procurement_concept_concept",
        lambda: [
            _project_fk("fk_oe_pcc_concept_project"),
            _str("catalogue_source", 20, "shipped"),
            _str("catalogue_id", 64, None),
            _int("catalogue_version"),
            _str("jurisdiction", 20, "none"),
            _str("client_type", 20, "private"),
            _bool("public_client", False),
            _num("vat_rate_pct", 5, 2),
            _str("state", 20, "draft"),
            sa.Column(
                "governance_document_id",
                GUID(),
                sa.ForeignKey("oe_governance_document.id", ondelete="SET NULL", name="fk_oe_pcc_concept_gov_document"),
                nullable=True,
            ),
            _str("release_gate_code", 64, ""),
            _guid("default_profile_id"),
            _guid("submitted_by"),
            _guid("approved_by"),
            _ts("approved_at"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("project_id", name="uq_oe_pcc_concept_project"),
        ],
        [],
    ),
    (
        "oe_procurement_concept_award_package",
        lambda: [
            _project_fk("fk_oe_pcc_award_project"),
            _str("split_basis", 20, "whole"),
            _bool("is_advance", False),
            _text("advance_reason"),
            _str("advance_release_kind", 20, None, nullable=True),
            _guid("advance_release_id"),
            _money("estimated_value"),
            _str("currency", 3),
            _str("cost_ref_kind", 20, None, nullable=True),
            _guid("cost_ref_id"),
            _str("lot_group", 64),
            _bool("small_lot_exemption", False),
            _str("procedure_code", 64, None, nullable=True),
            _str("tender_basis", 20, None, nullable=True),
            _guid("framework_agreement_id"),
            _str("evaluation_method", 20, "lowest_price"),
            _json("evaluation_weights"),
            _guid("need_activity_id"),
            _str("need_date", 40, None, nullable=True),
            _int("lead_time_days", nullable=True),
            _int("procedure_days", nullable=True),
            _str("planned_start", 40, None, nullable=True),
            _guid("prequal_profile_id"),
            _guid("start_activity_id"),
            _guid("award_activity_id"),
            _str("state", 20, "planned"),
            _str("state_before", 20, None, nullable=True),
            _text("notes"),
            _guid("created_by"),
        ],
        [
            ("ix_oe_pcc_award_project", ["project_id"]),
            ("ix_oe_pcc_award_framework", ["framework_agreement_id"]),
        ],
    ),
    (
        "oe_procurement_concept_prequal_profile",
        lambda: [
            _project_fk("fk_oe_pcc_profile_project"),
            _guid("package_id"),
            _str("name", 255),
            _json("criteria"),
            _num("pass_mark", 6, 2),
            _int("validity_months", 12),
        ],
        [("ix_oe_pcc_profile_project", ["project_id", "package_id"])],
    ),
    (
        "oe_procurement_concept_candidate",
        lambda: [
            _project_fk("fk_oe_pcc_candidate_project"),
            _guid("package_id", nullable=False),
            _guid("subcontractor_id"),
            _guid("vendor_id"),
            _str("free_name", 255),
            _str("source", 20, "own_list"),
            _str("list_kind", 10, "long"),
            _text("decision_rationale"),
            _bool("conflict_of_interest_declared", False),
            _text("conflict_note"),
            sa.UniqueConstraint("package_id", "subcontractor_id", name="uq_oe_pcc_candidate_sub"),
            sa.UniqueConstraint("package_id", "vendor_id", name="uq_oe_pcc_candidate_vendor"),
        ],
        [("ix_oe_pcc_candidate_package", ["project_id", "package_id"])],
    ),
    (
        "oe_procurement_concept_candidate_score",
        lambda: [
            _candidate_fk("fk_oe_pcc_score_candidate"),
            _str("criterion_code", 64, None),
            _nbool("passed"),
            _num("score", 6, 2, nullable=True),
            _json("evidence"),
            _text("note"),
            _guid("scored_by"),
            sa.UniqueConstraint("candidate_id", "criterion_code", name="uq_oe_pcc_score"),
        ],
        [],
    ),
    (
        "oe_procurement_concept_reference",
        lambda: [
            _candidate_fk("fk_oe_pcc_reference_candidate"),
            _str("project_name", 255, None),
            _str("client", 255),
            _money("value"),
            _str("currency", 3),
            _int("year", nullable=True),
            _str("role", 120),
            _str("contact", 255),
            _guid("verified_by"),
            _ts("verified_at"),
        ],
        [("ix_oe_pcc_reference_candidate", ["candidate_id"])],
    ),
    (
        "oe_procurement_concept_sounding",
        lambda: [
            _project_fk("fk_oe_pcc_sounding_project"),
            _json("package_ids"),
            _str("trade", 120),
            _str("held_on", 40, None),
            _str("method", 10, "meeting"),
            _json("participant_candidate_ids"),
            _text("findings"),
            _str("capacity_signal", 20, "adequate"),
            _str("price_signal", 20, "unknown"),
            _int("lead_time_signal_days", nullable=True),
            _text("mitigation"),
            _bool("resplit", False),
            _guid("created_by"),
        ],
        [("ix_oe_pcc_sounding_project", ["project_id"])],
    ),
    (
        "oe_procurement_concept_framework",
        lambda: [
            _str("tenant_id", 64, None),
            _str("code", 64, None),
            _str("title", 255),
            _guid("subcontractor_id"),
            _guid("vendor_id"),
            _str("supplier_name", 255),
            _text("scope"),
            _json("package_kinds"),
            _json("lots"),
            _money("max_value", nullable=False),
            _str("currency", 3, None),
            _str("start_date", 40, None),
            _str("end_date", 40, None),
            _str("call_off_mode", 20, "direct"),
            _str("source_procedure_ref", 255),
            _str("state", 20, "draft"),
            _guid("created_by"),
            _int("version", 1),
            sa.UniqueConstraint("tenant_id", "code", name="uq_oe_pcc_framework_code"),
        ],
        [("ix_oe_pcc_framework_tenant", ["tenant_id", "state"])],
    ),
]


def upgrade() -> None:
    """Create the eight tables and their indexes, each only when it is missing."""
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
    """Drop the eight tables, children before the parents they reference."""
    bind = op.get_bind()
    for table, _columns, _indexes in reversed(_TABLES):
        if table in sa.inspect(bind).get_table_names():
            op.drop_table(table)
