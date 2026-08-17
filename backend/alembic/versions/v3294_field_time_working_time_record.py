# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""field_time - clock times, the employer, and the statutory regime a day is recorded under.

Adds one column to ``oe_field_time_timesheet``:

    working_time_regime        VARCHAR(30)   - which statutory regime, or NULL

and five to ``oe_field_time_line``:

    started_at                 TIMESTAMPTZ   - when the worker started
    ended_at                   TIMESTAMPTZ   - when the worker stopped
    break_minutes              INTEGER       - unpaid break inside those times
    employer_kind              VARCHAR(20)   - "own" or "subcontractor"
    employer_subcontractor_id  VARCHAR(36)   - which subcontractor, when one

Every column is nullable and carries no server default, which is the whole
point. A country that obliges an employer to record the start, the end and the
duration of each worker's daily working time is one country among many, and the
rows already in these tables were written by people who mostly do not live in
it. NULL everywhere means those rows behave exactly as they did before this
revision existed: no clock times, no employer, no regime, no deadline and no
retention window. A server default of 0 on ``break_minutes`` would have written
a number into every historical row and made that claim false.

``employer_subcontractor_id`` is a soft link with no foreign key, matching
``daywork_sheet_id`` in the same table. A working-time record is kept for years
after the works finish and has to survive a subcontractor being tidied out of
the register it points at.

The timestamp columns are ``TIMESTAMP WITH TIME ZONE``, the type the ORM's
``AwareDateTime`` renders, and the subcontractor id is ``String(36)``, the type
the ORM's ``GUID`` renders on every dialect. Neither is a native ``uuid``.

Safe on a populated database. A nullable ADD COLUMN with no default is a
catalogue-only change in PostgreSQL: it rewrites no rows and holds the lock only
for as long as the catalogue update takes.

Inspector-guarded, so a fresh install whose tables env.py already created
through ``Base.metadata.create_all`` hits an idempotent no-op.

Revision ID: v3294_field_time_working_time_record
Revises: v3293_bi_dashboards_project_scope
Create Date: 2026-08-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3294_field_time_working_time_record"
down_revision: Union[str, Sequence[str], None] = "v3293_bi_dashboards_project_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TIMESHEET_TABLE = "oe_field_time_timesheet"
_LINE_TABLE = "oe_field_time_line"

_TIMESHEET_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (("working_time_regime", sa.String(30)),)

_LINE_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("started_at", sa.DateTime(timezone=True)),
    ("ended_at", sa.DateTime(timezone=True)),
    ("break_minutes", sa.Integer()),
    ("employer_kind", sa.String(20)),
    ("employer_subcontractor_id", sa.String(36)),
)


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    if not _has_table(inspector, table):
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, columns in ((_TIMESHEET_TABLE, _TIMESHEET_COLUMNS), (_LINE_TABLE, _LINE_COLUMNS)):
        if not _has_table(inspector, table):
            continue
        for name, column_type in columns:
            if not _has_column(inspector, table, name):
                op.add_column(table, sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, columns in ((_TIMESHEET_TABLE, _TIMESHEET_COLUMNS), (_LINE_TABLE, _LINE_COLUMNS)):
        if not _has_table(inspector, table):
            continue
        for name, _column_type in columns:
            if _has_column(inspector, table, name):
                op.drop_column(table, name)
