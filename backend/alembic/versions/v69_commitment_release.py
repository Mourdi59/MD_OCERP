# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""commitment release - commitment and release matrix with delegation of authority.

Eight new tables, nothing existing touched, all project-scoped and CASCADE with
the project: the matrix settings (pinned authority schedule, enforcement, FX
policy, tier routes), authority assignments, commitment items, document links
(unique per project, no amounts stored), preconditions, release requests and
their immutable decisions, abort terms and saved exposure scenarios.

Authority schedules and abort bases a company builds itself live in the
governance catalogue tables of v68 under their own ``kind``; no table here.

Every constraint and index name is written out and matches the model. Every
step is inspector-guarded, so a database whose tables ``create_all`` already
built reaches this revision and does nothing.

Revision ID: v69_commitment_release
Revises: v68_project_governance
Create Date: 2026-10-11
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v69_commitment_release"
down_revision: str | Sequence[str] | None = "v68_project_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROJECT = "oe_projects_project.id"
_ITEM = "oe_commitment_item.id"


def _base() -> list[sa.Column]:
    return [
        sa.Column("id", GUID(), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _project_fk(name: str) -> sa.Column:
    return sa.Column("project_id", GUID(), sa.ForeignKey(_PROJECT, ondelete="CASCADE", name=name), nullable=False)


def _item_fk(name: str) -> sa.Column:
    return sa.Column("item_id", GUID(), sa.ForeignKey(_ITEM, ondelete="CASCADE", name=name), nullable=False)


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


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


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _json(name: str) -> sa.Column:
    return sa.Column(name, sa.JSON(), nullable=False)


def _money(name: str, nullable: bool = True, precision: int = 18, scale: int = 4) -> sa.Column:
    return sa.Column(name, MoneyType(precision, scale), nullable=nullable)


_TABLES: list[tuple[str, Callable[[], list], list[tuple[str, list[str]]]]] = [
    (
        "oe_commitment_matrix",
        lambda: [
            _project_fk("fk_oe_cmt_matrix_project"),
            _str("schedule_source", 20, "shipped"),
            _str("schedule_id", 64, None),
            _int("schedule_version"),
            _str("enforcement", 10, "warn"),
            _bool("require_link", False),
            _str("fx_policy", 30, "fx_service_rate_set"),
            _json("tier_routes"),
            _json("generated_routes"),
            _guid("legal_entity_id"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", name="uq_oe_cmt_matrix_project"),
        ],
        [],
    ),
    (
        "oe_commitment_assignment",
        lambda: [
            _project_fk("fk_oe_cmt_assignment_project"),
            _str("project_role", 64, None),
            _guid("user_id", nullable=False),
            _guid("deputy_user_id"),
            _str("valid_from", 40, None, nullable=True),
            _str("valid_to", 40, None, nullable=True),
            sa.UniqueConstraint("project_id", "project_role", "user_id", name="uq_oe_cmt_assignment"),
        ],
        [("ix_oe_cmt_assignment_role", ["project_id", "project_role"])],
    ),
    (
        "oe_commitment_item",
        lambda: [
            _project_fk("fk_oe_cmt_item_project"),
            _str("code", 64, None),
            _str("title", 255),
            _str("commitment_type", 40, None),
            _str("status", 30, "planned"),
            _str("status_before", 30, None, nullable=True),
            _int("attempt_no", 1),
            _json("flags"),
            _guid("cost_line_id"),
            _guid("control_account_id"),
            _guid("cost_bearer_legal_entity_id"),
            _guid("funding_application_id"),
            _guid("risk_id"),
            _str("governance_area_code", 64, None, nullable=True),
            _str("gate_code", 64, None, nullable=True),
            _bool("deferred", False),
            _text("deferred_reason"),
            _str("split_group", 64, None, nullable=True),
            _guid("owner_user_id"),
            _str("planned_source", 20, "manual"),
            _guid("planned_source_id"),
            _money("planned_manual_amount"),
            _str("currency", 3),
            _guid("need_activity_id"),
            _guid("requisition_id"),
            _guid("plant_item_id"),
            _int("lead_time_days", nullable=True),
            _int("decision_buffer_days", nullable=True),
            _str("latest_decision_date_fixed", 40, None, nullable=True),
            _guid("transferred_to_item_id"),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_cmt_item_code"),
        ],
        [
            ("ix_oe_cmt_item_status", ["project_id", "status"]),
            ("ix_oe_cmt_item_gate", ["project_id", "gate_code"]),
            ("ix_oe_cmt_item_group", ["project_id", "split_group"]),
        ],
    ),
    (
        "oe_commitment_link",
        lambda: [
            _project_fk("fk_oe_cmt_link_project"),
            _item_fk("fk_oe_cmt_link_item"),
            _str("kind", 30, None),
            _guid("target_id", nullable=False),
            _guid("created_by"),
            sa.UniqueConstraint("project_id", "kind", "target_id", name="uq_oe_cmt_link_document"),
        ],
        [("ix_oe_cmt_link_item", ["item_id"])],
    ),
    (
        "oe_commitment_precondition",
        lambda: [
            _project_fk("fk_oe_cmt_precondition_project"),
            _item_fk("fk_oe_cmt_precondition_item"),
            _str("kind", 40, None),
            _str("ref_id", 64, None, nullable=True),
            _text("text"),
            _str("state", 10, "open"),
            _str("evidence_ref", 255),
            _guid("confirmed_by"),
            _ts("confirmed_at"),
        ],
        [("ix_oe_cmt_precondition_item", ["item_id"])],
    ),
    (
        "oe_commitment_release",
        lambda: [
            _project_fk("fk_oe_cmt_release_project"),
            _item_fk("fk_oe_cmt_release_item"),
            _int("attempt"),
            _money("requested_amount", nullable=False),
            _str("currency", 3, None),
            _str("schedule_currency", 3, None),
            _money("amount_in_schedule_currency", nullable=False),
            _str("fx_rate_used", 40, "1"),
            _str("fx_rate_date", 40, None, nullable=True),
            _str("fx_source", 30, "same_currency"),
            _money("evaluated_amount", nullable=False),
            _money("cumulative_after", nullable=False),
            _str("required_tier", 40, None, nullable=True),
            _bool("escalate_outside", False),
            _str("external_approval_ref", 255),
            _str("schedule_source", 20, None),
            _str("schedule_id", 64, None),
            _int("schedule_version"),
            _guid("approval_instance_id"),
            _str("purpose", 12, "release"),
            _str("outcome", 12, "pending"),
            _guid("requested_by"),
            _guid("decided_by"),
            _guid("on_behalf_of"),
            _ts("decided_at"),
            _json("snapshot"),
            _text("tranche_note"),
            _text("conditions"),
            _text("rationale"),
            _str("valid_until", 40, None, nullable=True),
            sa.UniqueConstraint("item_id", "attempt", name="uq_oe_cmt_release_attempt"),
        ],
        [
            ("ix_oe_cmt_release_item", ["item_id"]),
            ("ix_oe_cmt_release_instance", ["approval_instance_id"]),
        ],
    ),
    (
        "oe_commitment_abort_terms",
        lambda: [
            _project_fk("fk_oe_cmt_abort_project"),
            _item_fk("fk_oe_cmt_abort_item"),
            _str("scope", 40, "item"),
            _str("basis_code", 64, None, nullable=True),
            _str("basis_source", 20, "shipped"),
            _int("basis_version", nullable=True),
            _json("cancellation_schedule"),
            _json("parameters"),
            _str("transferable", 20, "no"),
            _money("transfer_value_estimate"),
            _money("salvage_value_estimate"),
            _money("saved_cost_estimate"),
            _money("other_charge_estimate"),
            _money("progress_pct", precision=9, scale=6),
            _int("notice_days", nullable=True),
            _text("source_note"),
            _guid("entered_by"),
            _ts("entered_at"),
            sa.UniqueConstraint("item_id", "scope", name="uq_oe_cmt_abort_scope"),
        ],
        [],
    ),
    (
        "oe_commitment_scenario",
        lambda: [
            _project_fk("fk_oe_cmt_scenario_project"),
            _str("as_of", 40, None),
            _str("label", 255),
            _json("payload"),
            _guid("created_by"),
        ],
        [("ix_oe_cmt_scenario_project", ["project_id"])],
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
