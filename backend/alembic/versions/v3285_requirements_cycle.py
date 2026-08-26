# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""requirements_cycle: why, who, when, how and which priced work.

A requirement stored as an EAC triplet says what is required. It does not say
who asked for it, at which phase it applies, how anyone would prove it was met,
or why it exists at all, and it could name only one priced position.

``oe_requirements_item`` gains five columns and a self-reference
    ``rationale`` (why), ``originator`` and ``originator_role`` (who),
    ``phase`` (when) and ``verification_method`` (how).
    ``parent_requirement_id`` lets a client demand be decomposed into the
    constraints that satisfy it without losing the trail back.

    All five are controlled keys or free text, never display words. ``phase``
    holds ``detail``, and a German screen renders "Ausführungsplanung" while a
    British one renders "Technical Design" off the same row. Storing the words
    would make the data readable in one country and untranslatable everywhere
    else.

``oe_requirements_set`` gains ``vocabulary``
    ``iso19650`` or ``neutral``. A set belongs to exactly one project, so this
    is the per-project wording switch. Existing sets get ``neutral``, which is
    what they have been reading all along.

``oe_requirement_position_link`` is new
    A requirement governs work, plural. "Every exterior wall is F90" applies to
    each wall position in the bill. The single ``linked_position_id`` column
    forced a choice between them, so this table replaces it and every non-null
    value is copied across with ``link_source='migrated'``.

    The old column stays. Callers that only ever wanted one position keep
    working, and ``Requirement.linked_position_ids`` reads through both.

``oe_requirement_deliverable.due_milestone_id`` gains its foreign key
    It was a bare id that no constraint ever checked, so a deleted milestone
    left deliverables pointing at nothing. Any value that does not resolve to a
    milestone is set to null before the constraint goes on: such a value is
    already unjoinable, and nulling it makes the column say what it has meant
    since the milestone went away. The count is logged rather than silently
    swallowed.

Idempotent: every step is guarded by the inspector, so a fresh install built by
``Base.metadata.create_all`` is a no-op here.

Revision ID: v3285_requirements_cycle
Revises: v3284_payment_clock
Create Date: 2026-08-11
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3285_requirements_cycle"
down_revision: Union[str, Sequence[str], None] = "v3284_payment_clock"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_ITEM = "oe_requirements_item"
_SET = "oe_requirements_set"
_DELIVERABLE = "oe_requirement_deliverable"
_LINK = "oe_requirement_position_link"
_MILESTONE = "oe_projects_milestone"
_POSITION = "oe_boq_position"

_FK_DELIVERABLE_MILESTONE = "fk_requirement_deliverable_due_milestone"
_UQ_LINK = "uq_requirement_position_link"

# SQLAlchemy's own naming for an ``index=True`` column, so an upgraded database
# ends up with the same index names as one built by ``create_all``.
_IX_ITEM_PHASE = f"ix_{_ITEM}_phase"
_IX_ITEM_PARENT = f"ix_{_ITEM}_parent_requirement_id"
_IX_LINK_REQUIREMENT = f"ix_{_LINK}_requirement_id"
_IX_LINK_POSITION = f"ix_{_LINK}_position_id"
_IX_DELIVERABLE_MILESTONE = f"ix_{_DELIVERABLE}_due_milestone_id"

#: Added to ``oe_requirements_item``: name, type, server default.
_ITEM_COLUMNS: tuple[tuple[str, sa.types.TypeEngine, str | None], ...] = (
    ("rationale", sa.Text(), ""),
    ("originator", sa.String(255), ""),
    ("originator_role", sa.String(50), ""),
    ("phase", sa.String(50), ""),
    ("verification_method", sa.String(50), ""),
    ("parent_requirement_id", sa.String(36), None),
)


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
    return {name for idx in inspector.get_indexes(table) if (name := idx.get("name"))}


def _foreign_keys(table: str) -> set[str]:
    """Named foreign key constraints on ``table``."""
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return set()
    return {name for fk in inspector.get_foreign_keys(table) if (name := fk.get("name"))}


# data-rewrite-ack: table=oe_requirement_deliverable growth=bounded rows=one row per requirement-deliverable pairing, states updated in place, bounded by requirement count
# boot-repair: gap - clears orphaned foreign-key values so the FK can be added; the boot heal adds foreign keys and not the cleanup, so on a database holding an orphan the FK is refused
def upgrade() -> None:
    # ── The five questions ──────────────────────────────────────────────────
    if _table_exists(_ITEM):
        present = _columns(_ITEM)
        for name, type_, default in _ITEM_COLUMNS:
            if name in present:
                continue
            # A column with a server default is NOT NULL and backfills itself;
            # the one without a default is the self-reference, which is nullable
            # because most requirements are not decomposed from another.
            op.add_column(
                _ITEM,
                sa.Column(name, type_, nullable=default is None, server_default=default),
            )

        existing = _indexes(_ITEM)
        if _IX_ITEM_PHASE not in existing and "phase" in _columns(_ITEM):
            op.create_index(_IX_ITEM_PHASE, _ITEM, ["phase"])
        if _IX_ITEM_PARENT not in existing and "parent_requirement_id" in _columns(_ITEM):
            op.create_index(_IX_ITEM_PARENT, _ITEM, ["parent_requirement_id"])

    # ── The wording switch ──────────────────────────────────────────────────
    if _table_exists(_SET) and "vocabulary" not in _columns(_SET):
        op.add_column(
            _SET,
            sa.Column("vocabulary", sa.String(20), nullable=False, server_default="neutral"),
        )

    # ── Which priced work ───────────────────────────────────────────────────
    if not _table_exists(_LINK):
        op.create_table(
            _LINK,
            # String(36), not a native UUID type, matching the ORM's GUID.
            sa.Column("id", sa.String(36), primary_key=True, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("requirement_id", sa.String(36), nullable=False),
            sa.Column("position_id", sa.String(36), nullable=False),
            sa.Column("link_source", sa.String(20), server_default="manual", nullable=False),
            sa.Column("confirmed_by", sa.String(36), server_default="", nullable=False),
            sa.Column("notes", sa.Text(), server_default="", nullable=False),
            sa.ForeignKeyConstraint(["requirement_id"], [f"{_ITEM}.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["position_id"], [f"{_POSITION}.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("requirement_id", "position_id", name=_UQ_LINK),
        )

    link_indexes = _indexes(_LINK)
    if _IX_LINK_REQUIREMENT not in link_indexes:
        op.create_index(_IX_LINK_REQUIREMENT, _LINK, ["requirement_id"])
    if _IX_LINK_POSITION not in link_indexes:
        op.create_index(_IX_LINK_POSITION, _LINK, ["position_id"])

    # Backfill. Guarded by NOT EXISTS rather than by a first-run flag, so
    # re-running the migration after a partial failure cannot double up, and the
    # unique constraint is never the thing that catches it.
    if _table_exists(_LINK) and _table_exists(_ITEM):
        bind = op.get_bind()
        copied = bind.execute(
            sa.text(
                f"""
                INSERT INTO {_LINK} (id, created_at, updated_at, requirement_id,
                                     position_id, link_source, confirmed_by, notes)
                SELECT gen_random_uuid()::text, NOW(), NOW(), i.id,
                       i.linked_position_id, 'migrated', '', ''
                  FROM {_ITEM} i
                 WHERE i.linked_position_id IS NOT NULL
                   AND NOT EXISTS (
                       SELECT 1 FROM {_LINK} l
                        WHERE l.requirement_id = i.id
                          AND l.position_id = i.linked_position_id
                   )
                """
            )
        ).rowcount
        if copied:
            logger.info("requirements_cycle: copied %s single position links into %s", copied, _LINK)

    # ── The deliverable's due milestone ─────────────────────────────────────
    if _table_exists(_DELIVERABLE) and _table_exists(_MILESTONE):
        if _FK_DELIVERABLE_MILESTONE not in _foreign_keys(_DELIVERABLE):
            bind = op.get_bind()
            orphaned = bind.execute(
                sa.text(
                    f"""
                    UPDATE {_DELIVERABLE}
                       SET due_milestone_id = NULL
                     WHERE due_milestone_id IS NOT NULL
                       AND due_milestone_id NOT IN (SELECT id FROM {_MILESTONE})
                    """
                )
            ).rowcount
            if orphaned:
                logger.warning(
                    "requirements_cycle: cleared %s due_milestone_id values that named no milestone",
                    orphaned,
                )
            op.create_foreign_key(
                _FK_DELIVERABLE_MILESTONE,
                _DELIVERABLE,
                _MILESTONE,
                ["due_milestone_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if _IX_DELIVERABLE_MILESTONE not in _indexes(_DELIVERABLE):
            op.create_index(_IX_DELIVERABLE_MILESTONE, _DELIVERABLE, ["due_milestone_id"])


def downgrade() -> None:
    if _table_exists(_DELIVERABLE):
        if _IX_DELIVERABLE_MILESTONE in _indexes(_DELIVERABLE):
            op.drop_index(_IX_DELIVERABLE_MILESTONE, table_name=_DELIVERABLE)
        if _FK_DELIVERABLE_MILESTONE in _foreign_keys(_DELIVERABLE):
            op.drop_constraint(_FK_DELIVERABLE_MILESTONE, _DELIVERABLE, type_="foreignkey")

    # The link table goes whole. The single-column values it was filled from
    # were never deleted, so nothing written before this migration is lost;
    # links added afterwards to a second position are, and they have nowhere to
    # go in the old shape.
    if _table_exists(_LINK):
        op.drop_table(_LINK)

    if _table_exists(_SET) and "vocabulary" in _columns(_SET):
        op.drop_column(_SET, "vocabulary")

    if _table_exists(_ITEM):
        existing = _indexes(_ITEM)
        if _IX_ITEM_PARENT in existing:
            op.drop_index(_IX_ITEM_PARENT, table_name=_ITEM)
        if _IX_ITEM_PHASE in existing:
            op.drop_index(_IX_ITEM_PHASE, table_name=_ITEM)
        present = _columns(_ITEM)
        for name, _type, _default in reversed(_ITEM_COLUMNS):
            if name in present:
                op.drop_column(_ITEM, name)
