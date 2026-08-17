# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""bi_dashboards - project dimension for the assets that lacked one.

Adds a nullable ``project_id`` to four tables:

    oe_bi_dashboards_kpi_definition
    oe_bi_dashboards_report_definition
    oe_bi_dashboards_report_schedule
    oe_bi_dashboards_saved_filter

``oe_bi_dashboards_dashboard`` already had the column, ``alert_rule`` has
``scope_project_id`` and ``kpi_value`` has ``project_id``, so the module was
already half project-aware. The missing half was the half the project route
``/projects/{id}/bi-dashboards`` needs: without it the five list endpoints had
no project dimension at all and the route rendered the company-wide page while
claiming to be a project's.

NULL means company-wide. A project view shows its own rows plus the NULL ones,
so every row written before this migration stays visible everywhere instead of
being orphaned into a project nobody names.

The columns are ``String(36)``, not native ``uuid``: the ORM's ``GUID`` type is
``VARCHAR(36)`` on every dialect, and a native ``uuid`` column here would build
a schema the application reads with the wrong type on one of the two install
routes.

Safe on a populated database. A nullable ADD COLUMN with no default is a
catalogue-only change in PostgreSQL - it rewrites no rows and takes the lock
only for the moment it takes to update the catalogue. The indexes are built
non-concurrently, matching every other revision in this tree; these four tables
hold configuration rows, in the hundreds rather than the millions, so the build
is short.

The migration is inspector-guarded so a fresh install, whose tables env.py
already populated through ``Base.metadata.create_all``, hits an idempotent
no-op.

Revision ID: v3293_bi_dashboards_project_scope
Revises: v3292_finance_einvoice_seller_contact
Create Date: 2026-08-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3293_bi_dashboards_project_scope"
down_revision: Union[str, Sequence[str], None] = "v3292_finance_einvoice_seller_contact"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMN = "project_id"

_TABLES: tuple[str, ...] = (
    "oe_bi_dashboards_kpi_definition",
    "oe_bi_dashboards_report_definition",
    "oe_bi_dashboards_report_schedule",
    "oe_bi_dashboards_saved_filter",
)


def _index_name(table: str) -> str:
    return f"ix_{table}_{_COLUMN}"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _has_index(inspector: sa.engine.reflection.Inspector, table: str, index: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return index in {i["name"] for i in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _TABLES:
        if not _has_table(inspector, table):
            continue
        if not _has_column(inspector, table, _COLUMN):
            op.add_column(table, sa.Column(_COLUMN, sa.String(36), nullable=True))
        index = _index_name(table)
        if not _has_index(inspector, table, index):
            op.create_index(index, table, [_COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in _TABLES:
        if not _has_table(inspector, table):
            continue
        index = _index_name(table)
        if _has_index(inspector, table, index):
            op.drop_index(index, table_name=table)
        if _has_column(inspector, table, _COLUMN):
            op.drop_column(table, _COLUMN)
