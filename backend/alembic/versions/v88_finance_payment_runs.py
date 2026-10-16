# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""finance - payment runs.

Two new tables, nothing changed in an existing one:

* ``oe_finance_payment_run``: a batch of supplier invoices to pay on one date, from one legal entity, in one
  currency (run number, entity, currency, payment date, due-by date, status, who drew it up, approved and
  executed it and when). Run numbers are unique.
* ``oe_finance_payment_run_item``: one invoice in a run, the amount to pay on it, what was open on it when
  proposed and the payment that executing the run recorded. An invoice appears once per run; items cascade
  with their run and with their invoice.

Purely additive, so an installed base gets the tables from ``create_all`` on boot as well. Every constraint
and index name is written out and matches the models. Every step is inspector-guarded, so a database whose
tables ``create_all`` already built reaches this revision and does nothing.

Revision ID: v88_finance_payment_runs
Revises: v87_rfi_request_types
Create Date: 2026-10-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

revision: str = "v88_finance_payment_runs"
down_revision: str | Sequence[str] | None = "v87_rfi_request_types"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RUN = "oe_finance_payment_run"
_ITEM = "oe_finance_payment_run_item"


def upgrade() -> None:
    """Create the run table, then the item table; each only when missing."""
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if _RUN not in tables:
        op.create_table(
            _RUN,
            sa.Column("id", GUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("run_number", sa.String(length=32), nullable=False),
            sa.Column("legal_entity_id", GUID(), nullable=True),
            sa.Column("currency_code", sa.String(length=10), nullable=False),
            sa.Column("payment_date", sa.String(length=10), nullable=False),
            sa.Column("due_by", sa.String(length=10), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("approved_by", sa.String(length=36), nullable=True),
            sa.Column("approved_at", sa.String(length=40), nullable=True),
            sa.Column("executed_by", sa.String(length=36), nullable=True),
            sa.Column("executed_at", sa.String(length=40), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.PrimaryKeyConstraint("id", name="pk_oe_finance_payment_run"),
            sa.UniqueConstraint("run_number", name="uq_finance_payment_run_number"),
        )
    if "ix_finance_payment_run_entity_status" not in {ix["name"] for ix in sa.inspect(bind).get_indexes(_RUN)}:
        op.create_index("ix_finance_payment_run_entity_status", _RUN, ["legal_entity_id", "status"])

    if _ITEM not in tables:
        op.create_table(
            _ITEM,
            sa.Column("id", GUID(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "run_id",
                GUID(),
                sa.ForeignKey(
                    "oe_finance_payment_run.id",
                    ondelete="CASCADE",
                    name="fk_oe_finance_payment_run_item_run_id_oe_finance_payment_run",
                ),
                nullable=False,
            ),
            sa.Column(
                "invoice_id",
                GUID(),
                sa.ForeignKey(
                    "oe_finance_invoice.id",
                    ondelete="CASCADE",
                    name="fk_oe_finance_payment_run_item_invoice_id_oe_finance_invoice",
                ),
                nullable=False,
            ),
            sa.Column("project_id", GUID(), nullable=False),
            sa.Column("contact_id", sa.String(length=36), nullable=True),
            sa.Column("amount", MoneyType(), nullable=False),
            sa.Column("open_at_proposal", MoneyType(), nullable=False),
            sa.Column("payment_id", GUID(), nullable=True),
            sa.PrimaryKeyConstraint("id", name="pk_oe_finance_payment_run_item"),
            sa.UniqueConstraint("run_id", "invoice_id", name="uq_finance_payment_run_item_invoice"),
        )
    existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(_ITEM)}
    if "ix_oe_finance_payment_run_item_run_id" not in existing:
        op.create_index("ix_oe_finance_payment_run_item_run_id", _ITEM, ["run_id"])
    if "ix_finance_payment_run_item_invoice" not in existing:
        op.create_index("ix_finance_payment_run_item_invoice", _ITEM, ["invoice_id"])


def downgrade() -> None:
    """Drop the item table, then the run table."""
    tables = sa.inspect(op.get_bind()).get_table_names()
    if _ITEM in tables:
        op.drop_table(_ITEM)
    if _RUN in tables:
        op.drop_table(_RUN)
