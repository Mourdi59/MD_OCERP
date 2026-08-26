# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""saved_views: share a view with a team, and constrain the enum columns.

Sharing a saved view was all-or-nothing: private, the whole project, or the
whole workspace. There was no way to hand a view to the five people who
actually work on that package. ``oe_teams`` now owns team membership, so a
share can name a team.

Adds to ``oe_saved_views_view``:

* ``shared_team_id`` - nullable foreign key into ``oe_teams_team``, ``ON DELETE
                       SET NULL``. Deleting a team revokes the share rather
                       than deleting other people's saved views; the view then
                       degrades to owner-only, which the module's validation
                       rules report as a finding instead of silently widening
                       it to the project.

Adds three CHECK constraints that encode rules the application already relies
on but the database never enforced:

* ``ck_oe_saved_views_view_share_scope``      - the four known scopes
* ``ck_oe_saved_views_view_team_pin_scope``   - a team pin only on a team share.
                                                Deliberately NOT the reverse:
                                                the SET NULL above must stay
                                                legal.
* ``ck_oe_saved_views_run_outcome``           - the five run outcomes

These are the names ``Base.metadata`` would give them, so an install built by
``create_all`` and one built by this migration carry the same constraint under
the same name and a later migration can drop it by name on either route.

Idempotent: every step is guarded by the inspector, so a fresh install that ran
``Base.metadata.create_all`` first is a no-op here. Rows that would violate a
new constraint are normalised first, and both normalisations are
behaviour-preserving - an unrecognised share scope is already treated as
private by the visibility check, and an unrecognised run outcome is already
read as a failure.

Revision ID: v3267_saved_views_team_share
Revises: v3266_credentials_requirements
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3267_saved_views_team_share"
down_revision: Union[str, Sequence[str], None] = "v3266_credentials_requirements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_VIEW = "oe_saved_views_view"
_RUN = "oe_saved_views_run"
_TEAM = "oe_teams_team"

_COLUMN = "shared_team_id"
_INDEX = "ix_oe_saved_views_view_shared_team_id"
_FK = "fk_oe_saved_views_view_shared_team_id_oe_teams_team"

# The Base metadata names CHECK constraints ``ck_%(table_name)s_%(constraint_name)s``.
# These are the finished names, so a database built by ``create_all`` and one
# built by this migration carry the same constraint under the same name.
_CK_SHARE_SCOPE = f"ck_{_VIEW}_share_scope"
_CK_TEAM_PIN = f"ck_{_VIEW}_team_pin_scope"
_CK_RUN_OUTCOME = f"ck_{_RUN}_outcome"

_SHARE_SCOPES = ("private", "team", "project", "workspace")
_RUN_OUTCOMES = ("ok", "budget", "scope", "whitelist", "error")


def _table_exists(table: str) -> bool:
    """Whether ``table`` is present in the database being migrated."""
    return table in sa.inspect(op.get_bind()).get_table_names()


def _columns(table: str) -> set[str]:
    """Column names on ``table`` (empty when the table does not exist)."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _indexes(table: str) -> set[str]:
    """Index names on ``table`` (empty when the table does not exist)."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table) if idx.get("name")}


def _check_constraints(table: str) -> set[str]:
    """CHECK constraint names on ``table``, best effort across backends."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    try:
        return {ck["name"] for ck in inspector.get_check_constraints(table) if ck.get("name")}
    except NotImplementedError:  # pragma: no cover - backend without reflection
        return set()


def _quoted(values: tuple[str, ...]) -> str:
    """Render a tuple of literals for a SQL ``IN`` list."""
    return ", ".join(f"'{value}'" for value in values)


def _add_check(table: str, name: str, condition: str) -> None:
    """Add a named CHECK constraint by explicit DDL.

    ``op.create_check_constraint`` would re-apply the ``ck_%(table_name)s_...``
    naming convention on top of the name it is given, so the finished name
    would depend on which route built the schema. Spelling the DDL out keeps
    one name for both.
    """
    op.execute(sa.text(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" CHECK ({condition})'))


def _drop_check(table: str, name: str) -> None:
    """Drop a named CHECK constraint if it is there."""
    op.execute(sa.text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{name}"'))


# data-rewrite-ack: table=oe_saved_views_view growth=bounded rows=saved view definitions, a handful per user, not a log
# data-rewrite-ack: table=oe_saved_views_run growth=tenure rows=append-only audit row written after every run, an execution log by its own docstring
# boot-repair: gap - normalises out-of-range enum values so the CHECK constraints can be added; the boot heal adds constraints and not the normalisation, so on a database holding such a value the CHECK is refused
def upgrade() -> None:
    if not _table_exists(_VIEW):
        # The module was never installed on this database; create_all will
        # build both tables complete when it is.
        return

    if _COLUMN not in _columns(_VIEW):
        op.add_column(_VIEW, sa.Column(_COLUMN, sa.String(36), nullable=True))

    if _INDEX not in _indexes(_VIEW):
        op.create_index(_INDEX, _VIEW, [_COLUMN])

    # The foreign key is only creatable once the teams module has its table.
    # oe_teams is auto_install, so this is the normal path; skipping keeps a
    # trimmed deployment migratable rather than wedged.
    if _table_exists(_TEAM):
        existing_fks = {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(_VIEW) if fk.get("name")}
        if _FK not in existing_fks:
            op.create_foreign_key(_FK, _VIEW, _TEAM, [_COLUMN], ["id"], ondelete="SET NULL")

    view_checks = _check_constraints(_VIEW)
    if _CK_SHARE_SCOPE not in view_checks:
        # An unrecognised scope is already treated as private by the visibility
        # check, so writing that down changes no behaviour.
        op.execute(
            sa.text(
                f"UPDATE {_VIEW} SET share_scope = 'private' "  # noqa: S608 - table names are module constants
                f"WHERE share_scope IS NULL OR share_scope NOT IN ({_quoted(_SHARE_SCOPES)})"
            )
        )
        _add_check(_VIEW, _CK_SHARE_SCOPE, f"share_scope IN ({_quoted(_SHARE_SCOPES)})")

    if _CK_TEAM_PIN not in view_checks:
        _add_check(_VIEW, _CK_TEAM_PIN, f"{_COLUMN} IS NULL OR share_scope = 'team'")

    if _table_exists(_RUN) and _CK_RUN_OUTCOME not in _check_constraints(_RUN):
        op.execute(
            sa.text(
                f"UPDATE {_RUN} SET outcome = 'error' "  # noqa: S608 - table names are module constants
                f"WHERE outcome IS NULL OR outcome NOT IN ({_quoted(_RUN_OUTCOMES)})"
            )
        )
        _add_check(_RUN, _CK_RUN_OUTCOME, f"outcome IN ({_quoted(_RUN_OUTCOMES)})")


def downgrade() -> None:
    if _table_exists(_RUN):
        _drop_check(_RUN, _CK_RUN_OUTCOME)

    if not _table_exists(_VIEW):
        return

    _drop_check(_VIEW, _CK_TEAM_PIN)
    _drop_check(_VIEW, _CK_SHARE_SCOPE)

    existing_fks = {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(_VIEW) if fk.get("name")}
    if _FK in existing_fks:
        op.drop_constraint(_FK, _VIEW, type_="foreignkey")

    if _INDEX in _indexes(_VIEW):
        op.drop_index(_INDEX, table_name=_VIEW)

    if _COLUMN in _columns(_VIEW):
        # Team shares lose their pin on the way down. The scope column keeps
        # the value 'team', which the pre-team code path treats as unshared,
        # so a downgraded database hides those views from everyone but their
        # owner rather than exposing them project-wide.
        op.drop_column(_VIEW, _COLUMN)
