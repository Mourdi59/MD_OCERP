# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""delivery model - contract-side items (contract forms, land tenure, utility contracts, user agreements, partners).

One new table, nothing existing touched, project-scoped and CASCADE with the project.

Every constraint and index name is written out and matches the model. The step is
inspector-guarded, so a database whose table ``create_all`` already built reaches
this revision and does nothing.

Revision ID: v79_delivery_contract_items
Revises: v78_site_logistics_ext
Create Date: 2026-10-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.database import GUID

revision: str = "v79_delivery_contract_items"
down_revision: str | Sequence[str] | None = "v78_site_logistics_ext"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "oe_delivery_model_contract_item"
_INDEX = "ix_oe_dm_contract_item_project"


def _str(name: str, length: int, default: str | None = "", nullable: bool = False) -> sa.Column:
    if default is None:
        return sa.Column(name, sa.String(length=length), nullable=nullable)
    return sa.Column(name, sa.String(length=length), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the table and its index, each only when it is missing."""
    bind = op.get_bind()
    if _TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            _TABLE,
            sa.Column("id", GUID(), primary_key=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column(
                "project_id",
                GUID(),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE", name="fk_oe_dm_contract_item_project"),
                nullable=False,
            ),
            _str("code", 64, None),
            _str("group_code", 30, None),
            _str("kind_code", 64, None),
            _str("title", 500, ""),
            _str("counterparty", 255, ""),
            sa.Column("package_id", GUID(), nullable=True),
            _str("status", 20, "draft"),
            _str("reference", 120, ""),
            _str("start_date", 40, None, nullable=True),
            _str("end_date", 40, None, nullable=True),
            _str("price_basis", 30, None, nullable=True),
            _str("share_percent", 10, None, nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.UniqueConstraint("project_id", "code", name="uq_oe_dm_contract_item_code"),
        )
    existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(_TABLE)}
    if _INDEX not in existing:
        op.create_index(_INDEX, _TABLE, ["project_id", "group_code"])


def downgrade() -> None:
    """Drop the table."""
    bind = op.get_bind()
    if _TABLE in sa.inspect(bind).get_table_names():
        op.drop_table(_TABLE)
