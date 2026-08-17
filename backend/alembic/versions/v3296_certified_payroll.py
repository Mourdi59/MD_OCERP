# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""certified payroll - wage determinations, worker classification and the weekly form.

Creates five tables and touches no existing one:

    oe_certpay_determination  - a wage determination the contractor has on file
    oe_certpay_classification - one craft inside it, basic rate and fringe apart
    oe_certpay_assignment     - which classification a worker works under
    oe_certpay_week           - one week's certified payroll and its signature
    oe_certpay_line           - the frozen per-worker record of a certified week

Nothing is added to ``oe_payroll_entry`` or to any other module's table, and
that is deliberate rather than incidental. The weekly form is a pivot of payroll
entries that already exist; a draft week writes no rows at all and derives its
lines on read. Only certification writes, and what it writes is the frozen legal
record in ``oe_certpay_line``. So there is no second live copy of anybody's
hours to drift away from the first, and no column added to a table eight other
modules read.

Basic and fringe are separate columns everywhere they appear, on the required
side and on the paid side alike. There is no combined prevailing-rate column in
this revision and there is deliberately no room for one: overtime is computed on
the basic wage alone, and a schema that can store a blended rate is a schema
that will eventually be asked to multiply it.

No wage data is seeded. A determination row is a document the contractor
received from an awarding body and typed in. Rates change per craft, per county
and per issuing body on a schedule this repository cannot track, so what ships
is the structure that records which determination was used, never a snapshot of
what it said.

``oe_certpay_line`` denormalises the classification title, the determination
identifier and the authority alongside their ids. A certified payroll has to
read back in three years exactly as it was signed, whatever happened since to
the rows it pointed at.

Safe on a populated database: every statement creates a new table, so no
existing row is read, rewritten or locked.

Inspector-guarded, so a fresh install whose tables env.py already created
through ``Base.metadata.create_all`` hits an idempotent no-op.

Revision ID: v3296_certified_payroll
Revises: v3295_dlp_warranty_limitation_regime
Create Date: 2026-08-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3296_certified_payroll"
down_revision: Union[str, Sequence[str], None] = "v3295_dlp_warranty_limitation_regime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DETERMINATION = "oe_certpay_determination"
_CLASSIFICATION = "oe_certpay_classification"
_ASSIGNMENT = "oe_certpay_assignment"
_WEEK = "oe_certpay_week"
_LINE = "oe_certpay_line"

# Created child-last so a foreign key never points at a table that does not
# exist yet, and dropped in the reverse order for the same reason.
_TABLES_IN_ORDER = (_DETERMINATION, _CLASSIFICATION, _ASSIGNMENT, _WEEK, _LINE)

# ``GUID`` renders as String(36) on every dialect and the ORM's timestamps are
# TIMESTAMP WITH TIME ZONE. Neither is a native ``uuid`` column.
_GUID = sa.String(36)
_TS = sa.DateTime(timezone=True)


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _base_columns() -> list[sa.Column]:
    """The three columns every model in this platform inherits from ``Base``."""
    return [
        sa.Column("id", _GUID, primary_key=True, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
    ]


def _create_determination() -> None:
    op.create_table(
        _DETERMINATION,
        *_base_columns(),
        sa.Column("project_id", _GUID, sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("authority", sa.String(20), nullable=False, server_default="federal"),
        sa.Column("authority_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("jurisdiction", sa.String(20), nullable=False, server_default=""),
        sa.Column("locality", sa.String(160), nullable=False, server_default=""),
        sa.Column("identifier", sa.String(120), nullable=False, server_default=""),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("determination_method", sa.String(40), nullable=True),
        sa.Column("decision_date", sa.String(20), nullable=True),
        sa.Column("effective_date", sa.String(20), nullable=True),
        sa.Column("expires_on", sa.String(20), nullable=True),
        sa.Column("statute_reference", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("project_id", "authority", "identifier", name="uq_oe_certpay_determination_project_ident"),
    )
    op.create_index("ix_oe_certpay_determination_project_id", _DETERMINATION, ["project_id"])
    op.create_index("ix_oe_certpay_determination_project_authority", _DETERMINATION, ["project_id", "authority"])


def _create_classification() -> None:
    op.create_table(
        _CLASSIFICATION,
        *_base_columns(),
        sa.Column(
            "determination_id",
            _GUID,
            sa.ForeignKey(f"{_DETERMINATION}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(120), nullable=False, server_default=""),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        # Two rate columns, never one. See the module docstring.
        sa.Column("basic_hourly_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("fringe_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("determination_id", "code", name="uq_oe_certpay_classification_det_code"),
    )
    op.create_index("ix_oe_certpay_classification_determination_id", _CLASSIFICATION, ["determination_id"])


def _create_assignment() -> None:
    op.create_table(
        _ASSIGNMENT,
        *_base_columns(),
        sa.Column("project_id", _GUID, sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
        # Soft link, no foreign key: a wage record outlives a resource being
        # tidied out of the register, exactly as ``oe_payroll_entry`` does.
        sa.Column("resource_id", _GUID, nullable=True),
        sa.Column("worker_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("worker_identifier", sa.String(60), nullable=False, server_default=""),
        sa.Column(
            "classification_id",
            _GUID,
            sa.ForeignKey(f"{_CLASSIFICATION}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.String(20), nullable=True),
        sa.Column("valid_to", sa.String(20), nullable=True),
        # Nullable with no server default: a NULL says nobody stated the split,
        # and the service then derives one and records that it derived it. A
        # default of "0" here would have every assignment asserting a zero
        # fringe, which is a claim rather than a silence.
        sa.Column("paid_basic_rate", sa.String(50), nullable=True),
        sa.Column("paid_fringe_rate", sa.String(50), nullable=True),
        sa.Column("fringe_election", sa.String(12), nullable=True),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_oe_certpay_assignment_project_id", _ASSIGNMENT, ["project_id"])
    op.create_index("ix_oe_certpay_assignment_resource_id", _ASSIGNMENT, ["resource_id"])
    op.create_index("ix_oe_certpay_assignment_classification_id", _ASSIGNMENT, ["classification_id"])
    op.create_index("ix_oe_certpay_assignment_project_resource", _ASSIGNMENT, ["project_id", "resource_id"])


def _create_week() -> None:
    op.create_table(
        _WEEK,
        *_base_columns(),
        sa.Column("project_id", _GUID, sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
        # Soft link to oe_payroll_batch: the batch may be archived while the
        # certified week survives.
        sa.Column("batch_id", _GUID, nullable=True),
        sa.Column("week_ending", sa.String(20), nullable=False, server_default=""),
        sa.Column("payroll_number", sa.String(40), nullable=False, server_default=""),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("contractor_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("contractor_address", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_subcontractor", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("project_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("project_location", sa.String(255), nullable=False, server_default=""),
        sa.Column("contract_number", sa.String(120), nullable=False, server_default=""),
        sa.Column("covered_authorities", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("governing_determination_id", _GUID, nullable=True),
        sa.Column("governing_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("fringe_election", sa.String(12), nullable=False, server_default="plan"),
        sa.Column("fringe_exception_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        # The signature. Nullable with no default: an unsigned week must not
        # look like it carries a statement of compliance.
        sa.Column("signatory_name", sa.String(255), nullable=True),
        sa.Column("signatory_title", sa.String(160), nullable=True),
        sa.Column("signed_at", _TS, nullable=True),
        sa.Column("signed_by", _GUID, nullable=True),
        sa.Column("statement_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("currency", sa.String(10), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", _GUID, nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_oe_certpay_week_project_id", _WEEK, ["project_id"])
    op.create_index("ix_oe_certpay_week_batch_id", _WEEK, ["batch_id"])
    op.create_index("ix_oe_certpay_week_status", _WEEK, ["status"])
    op.create_index("ix_oe_certpay_week_project_ending", _WEEK, ["project_id", "week_ending"])


def _create_line() -> None:
    op.create_table(
        _LINE,
        *_base_columns(),
        sa.Column("week_id", _GUID, sa.ForeignKey(f"{_WEEK}.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", _GUID, nullable=True),
        sa.Column("worker_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("worker_identifier", sa.String(60), nullable=False, server_default=""),
        # Soft ids plus the words they resolved to at the moment of signature.
        sa.Column("classification_id", _GUID, nullable=True),
        sa.Column("classification_code", sa.String(120), nullable=False, server_default=""),
        sa.Column("classification_title", sa.String(255), nullable=False, server_default=""),
        sa.Column("determination_id", _GUID, nullable=True),
        sa.Column("determination_identifier", sa.String(120), nullable=False, server_default=""),
        sa.Column("determination_authority", sa.String(20), nullable=False, server_default=""),
        sa.Column("hours_by_day", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("straight_hours", sa.String(50), nullable=False, server_default="0"),
        sa.Column("overtime_hours", sa.String(50), nullable=False, server_default="0"),
        sa.Column("required_basic_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("required_fringe_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("paid_basic_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("paid_fringe_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("fringe_election", sa.String(12), nullable=False, server_default="plan"),
        sa.Column("overtime_multiplier", sa.String(20), nullable=False, server_default="1.5"),
        # Stored rather than recomputed, so the record can be checked against
        # the basic rate beside it without trusting the application's maths.
        sa.Column("overtime_base_rate", sa.String(50), nullable=False, server_default="0"),
        sa.Column("gross_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("total_deductions", sa.String(50), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.String(50), nullable=False, server_default="0"),
        sa.Column("deductions_detail", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("currency", sa.String(10), nullable=False, server_default=""),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_oe_certpay_line_week_id", _LINE, ["week_id"])
    op.create_index("ix_oe_certpay_line_resource_id", _LINE, ["resource_id"])
    op.create_index("ix_oe_certpay_line_week_ordinal", _LINE, ["week_id", "ordinal"])


_CREATORS = {
    _DETERMINATION: _create_determination,
    _CLASSIFICATION: _create_classification,
    _ASSIGNMENT: _create_assignment,
    _WEEK: _create_week,
    _LINE: _create_line,
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES_IN_ORDER:
        if not _has_table(inspector, table):
            _CREATORS[table]()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in reversed(_TABLES_IN_ORDER):
        if _has_table(inspector, table):
            op.drop_table(table)
