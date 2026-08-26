# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Rename the eight trademarked rows in oe_formwork_system.

The starter formwork catalogue shipped eight rows named after real products
from four suppliers, with the supplier's own name in ``supplier``. The
catalogue source was fixed so a fresh install never sees them again, but the
seeding path keys on ``name`` and skips what already exists, so that fix
reaches nobody who already installed. A de-branding that only helps future
installs leaves every existing tenant shipping the trademarks, which is the
whole thing we set out to stop. This revision repairs the rows already
written.

There is a second reason, independent of trademark. Because seed-defaults
compares per row on ``name``, a tenant who upgrades and re-runs it today gets
the eight new rows inserted *beside* the eight old ones - sixteen rows, eight
concepts. After this revision the old names are gone, so seed-defaults skips
all eight and the duplicate path closes.

Why this is safe to run over customer data:

* **Keyed on the exact old name.** A tenant who renamed a row themselves no
  longer matches and is left alone. We do not guess at near-misses.
* **A tenant's own supplier edit survives.** ``supplier`` is only cleared
  where it still holds the original brand. If someone repointed the row at
  their own hire yard, that value stays.
* **No row is renamed onto a name already present for that tenant.** There is
  no unique constraint on ``name``, so an install that already re-ran
  seed-defaults holds both the old row and its replacement; renaming blindly
  would leave two identical names in one catalogue. Those rows are skipped and
  counted, not merged and not deleted - the old row may carry assignments, and
  deciding which of the two an assignment should point at is a judgement about
  a tenant's own data that a migration has no standing to make.
* **Nothing is invented and no price moves.** Assignments reference the
  catalogue by ``formwork_system_id``, and neither ``unit_rate`` nor
  ``erect_strike_rate`` is touched, so no rate can change under an estimate.
* **Idempotent.** The predicate stops matching once a row is renamed, so a
  second run updates zero rows.

Per-pair rowcounts are logged rather than a total. One of the eight carries a
non-ASCII character in both the name and the supplier, and if that literal
ever stops byte-matching what is in the column, the pair silently matches
nothing while the other seven succeed - a single total of "7 rows updated"
would read as success.

Revision ID: v3271_formwork_debrand
Revises: v3270_dwg_conversion_heartbeat
Create Date: 2026-08-02
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3271_formwork_debrand"
down_revision: Union[str, Sequence[str], None] = "v3270_dwg_conversion_heartbeat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_SYSTEM = "oe_formwork_system"

# (old name, old supplier, new name). The new names are the descriptors now in
# ``default_seed_systems()``; keep the two in step if that catalogue is ever
# re-worded, or an upgraded install and a fresh one will disagree.
_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("Doka Framax Xlife", "Doka", "Steel framed wall panel"),
    ("Doka Dokadek 30", "Doka", "Aluminium slab deck panel"),
    ("PERI MAXIMO", "PERI", "Steel wall panel, single-side tie"),
    ("PERI SKYDECK", "PERI", "Aluminium drophead slab panel"),
    ("MEVA Mammut 350", "MEVA", "Heavy-duty steel wall panel"),
    ("Hünnebeck MANTO", "Hünnebeck", "Crane-set steel wall panel"),
    ("Ulma ENKOFORM V-100", "Ulma", "Girder wall formwork"),
    ("PERI ACS climbing", "PERI", "Self-climbing core system"),
)

# Raw SQL against the table, never the ORM: a migration that imports models
# breaks the moment the models move on, and this file must keep running
# against the schema as it was when the revision was written.
#
# ``IS NOT DISTINCT FROM`` rather than ``=`` on tenant_id because the column is
# nullable and a single-tenant install leaves it NULL, where ``=`` would never
# match and the duplicate guard would not fire at all.
_RENAME = sa.text(
    f"""
    UPDATE {_SYSTEM} AS s
       SET name = :new_name,
           supplier = CASE
                          WHEN s.supplier = :old_supplier THEN NULL
                          ELSE s.supplier
                      END
     WHERE s.name = :old_name
       AND NOT EXISTS (
               SELECT 1
                 FROM {_SYSTEM} AS other
                WHERE other.name = :new_name
                  AND other.tenant_id IS NOT DISTINCT FROM s.tenant_id
           )
    """  # noqa: S608 - table name is a module constant, not user input
)

_COUNT_OLD = sa.text(
    f"SELECT COUNT(*) FROM {_SYSTEM} WHERE name = :old_name"  # noqa: S608
)


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    """True when ``table`` exists and carries ``column``."""
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


# data-rewrite-ack: table=oe_formwork_system growth=bounded rows=formwork system catalogue, grows with the product library, not per project
# boot-repair: registry=formwork_debrand
def upgrade() -> None:
    """Rename the trademarked catalogue rows and clear the brand supplier."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # A module can be absent on a partial install, and this revision must not
    # be the thing that stops an upgrade over a database that never had the
    # formwork module enabled.
    if not _has_column(inspector, _SYSTEM, "name"):
        logger.info("%s absent, nothing to rename", _SYSTEM)
        return

    renamed = 0
    blocked = 0
    for old_name, old_supplier, new_name in _RENAMES:
        params = {
            "old_name": old_name,
            "old_supplier": old_supplier,
            "new_name": new_name,
        }
        before = bind.execute(_COUNT_OLD, {"old_name": old_name}).scalar_one()
        moved = bind.execute(_RENAME, params).rowcount
        renamed += moved
        # Rows still carrying the old name after the update are the ones whose
        # replacement was already present for that tenant. Report them: they
        # are the residue this revision deliberately declines to resolve.
        left = before - moved
        blocked += left
        if left:
            logger.warning(
                "%s: %d row(s) named %r left alone, %r already exists for that tenant",
                _SYSTEM,
                left,
                old_name,
                new_name,
            )
        elif not moved:
            logger.info("%s: no row named %r", _SYSTEM, old_name)

    logger.info(
        "renamed %d formwork catalogue row(s), %d left for the duplicate guard",
        renamed,
        blocked,
    )


def downgrade() -> None:
    """Deliberately a no-op.

    Reversing this would write real company names back into tenant databases,
    which is the one direction this change must not be able to travel. An
    alembic chain is also the wrong place to keep a copy of the strings we are
    removing: the revision would ship the trademarks in the source tree
    forever, in a file whose whole purpose is to take them out.

    Nor is the rename cleanly reversible even in principle. A row reading
    "Steel framed wall panel" because this revision renamed it is
    indistinguishable from one a tenant typed, or from one seed-defaults
    inserted on a fresh install, so a downgrade could not tell which rows were
    its own. Downgrading the schema is reversible; downgrading a repair is
    not, so this side is intentionally empty.
    """
