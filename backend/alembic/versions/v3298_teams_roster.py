# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""project roster - who is on the job, for which firm, in which trade and role.

Creates one table and touches no existing one:

    oe_teams_roster_member - one person on one project

Why a new table rather than columns on ``oe_teams_membership``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``oe_teams_membership`` is the authorization table: roughly two dozen modules
read it through ``teams.access.member_project_ids_subquery`` to decide whether
somebody may reach a project at all. Most of the people on a construction job
are not platform users, so holding them there would have meant making
``user_id`` nullable - which voids ``uq_teams_membership_team_user`` (NULLs are
distinct in a unique constraint) and turns every membership-to-user join in the
platform into a source of nameless members counted as viewers. The roster is a
separate table that grants nothing.

Links, and why two of them carry no foreign key
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``project_id`` and ``user_id`` are real foreign keys - the teams module already
declares a dependency on ``oe_projects`` and ``oe_users``. ``contact_id`` and
``resource_id`` are plain columns: those modules are optional, and a module has
to keep working when an optional module is not installed. The same arrangement
``oe_resources_resource.contact_id`` already uses.

``team_id`` is ``ON DELETE SET NULL`` because deleting a team must not delete
the people. The service clears the column explicitly in the same transaction,
so the outcome does not depend on foreign keys being enforced by the engine.

Uniqueness is partial: one project cannot list the same platform user twice, or
the same address-book contact twice. A line typed in by hand carries neither
link and is deliberately unconstrained, because two labourers can genuinely
share a name.

Safe on a populated database: one CREATE TABLE and four CREATE INDEX on a table
that did not exist, so no existing row is read, rewritten or locked.

Inspector-guarded, so a fresh install whose tables env.py already created
through ``Base.metadata.create_all`` hits an idempotent no-op.

Revision ID: v3298_teams_roster
Revises: v3297_boq_markup_scope
Create Date: 2026-08-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3298_teams_roster"
down_revision: Union[str, Sequence[str], None] = "v3297_boq_markup_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROSTER = "oe_teams_roster_member"

# ``GUID`` renders as String(36) on every dialect and the ORM's timestamps are
# TIMESTAMP WITH TIME ZONE. Neither is a native ``uuid`` column.
_GUID = sa.String(36)
_TS = sa.DateTime(timezone=True)


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, _ROSTER):
        return

    op.create_table(
        _ROSTER,
        sa.Column("id", _GUID, primary_key=True, nullable=False),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("project_id", _GUID, sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", _GUID, sa.ForeignKey("oe_teams_team.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", _GUID, sa.ForeignKey("oe_users_user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", _GUID, nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("trade", sa.String(32), nullable=False, server_default=""),
        sa.Column("site_role", sa.String(64), nullable=False, server_default=""),
        sa.Column("email", sa.String(255), nullable=False, server_default=""),
        sa.Column("phone", sa.String(50), nullable=False, server_default=""),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("allocation_percent", sa.Integer(), nullable=True),
        sa.Column("certifications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("resource_id", _GUID, nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.CheckConstraint("user_id IS NULL OR contact_id IS NULL", name="ck_teams_roster_single_link"),
    )
    op.create_index("ix_oe_teams_roster_member_project_id", _ROSTER, ["project_id"])
    op.create_index("ix_oe_teams_roster_member_team_id", _ROSTER, ["team_id"])
    op.create_index("ix_oe_teams_roster_member_user_id", _ROSTER, ["user_id"])
    op.create_index("ix_oe_teams_roster_member_contact_id", _ROSTER, ["contact_id"])
    op.create_index("ix_oe_teams_roster_member_resource_id", _ROSTER, ["resource_id"])
    op.create_index("ix_oe_teams_roster_member_trade", _ROSTER, ["trade"])
    op.create_index("ix_oe_teams_roster_member_site_role", _ROSTER, ["site_role"])
    op.create_index("ix_teams_roster_project_active", _ROSTER, ["project_id", "is_active"])
    # Partial unique indexes: the predicate is what lets a hand-typed line
    # (both links NULL) repeat while a linked person cannot.
    op.create_index(
        "uq_teams_roster_project_user",
        _ROSTER,
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
        sqlite_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_teams_roster_project_contact",
        _ROSTER,
        ["project_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("contact_id IS NOT NULL"),
        sqlite_where=sa.text("contact_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _has_table(inspector, _ROSTER):
        return
    op.drop_table(_ROSTER)
