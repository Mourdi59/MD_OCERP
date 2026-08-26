# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Backfill oe_finance_budget.currency_code from the owning project.

``ProjectBudget.currency_code`` carries no DB default in the model on purpose.
``finance/models.py`` states the contract: service code MUST supply the
currency from the project context so per-project rollups do not silently bias
toward one currency. Four write paths ignored that contract - the demo seeder,
the ``estimate.approved`` and ``variation.approved`` event handlers, and
create-budget-from-BOQ - and every line they wrote landed with ``''``. The
finance table renders those as em-dashes instead of money. The write paths are
fixed; this revision repairs the rows they already wrote.

Why this is safe to run over customer data:

* **Only empty or NULL rows are touched.** A row that already carries a
  currency is never rewritten, whatever its value. That is what makes the
  migration safe for a self-hosted install whose budget lines were imported
  rather than seeded: an imported row carrying a real currency is not empty,
  so it is not considered.
* **A row whose project currency has since changed still has no currency of
  its own today.** The project's current value is the best answer available
  and is strictly better than blank.
* **Nothing is invented.** When the parent project's own currency is blank,
  the budget row stays blank. That is the honest outcome. In particular this
  revision never writes a hardcoded currency of any kind.
* **Idempotent.** The predicate stops matching once a row is filled, so a
  second run updates zero rows.

The length guard is not cosmetic. ``oe_projects_project.currency`` is
``String(10)`` while ``oe_finance_budget.currency_code`` is ``String(3)``, so
copying a longer value across would abort the migration with "value too long
for type character varying(3)". Rows whose project currency does not fit an
ISO 4217 alphabetic code are left blank rather than truncated, because half a
currency code is worse than none. ``UPPER`` is normalisation, not invention:
ISO 4217 alphabetic codes are uppercase by definition and the application's
own writers already normalise with ``.strip()[:3].upper()``.

One thing found while writing this, worth knowing but deliberately not
"fixed" here. ``v2916_project_budget_currency`` added this column with
``server_default="EUR"``, while the model declares ``server_default=""``. So
the two install paths disagree: an install already stamped below v2916 that
upgraded through it had ``EUR`` applied to every budget row existing at that
moment, and a database built by ``create_all`` gives ``''``. A fresh install
is unaffected either way, since it never walks that revision. This revision
cannot repair the upgraded case,
because a row reading ``EUR`` because a migration stamped it is
indistinguishable from a row a user set to EUR. That is a separate decision
and is reported rather than acted on.

Revision ID: v3269_backfill_budget_currency
Revises: v3268_merge_fx_branch
Create Date: 2026-08-01
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3269_backfill_budget_currency"
down_revision: Union[str, Sequence[str], None] = "v3268_merge_fx_branch"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

_BUDGET = "oe_finance_budget"
_PROJECT = "oe_projects_project"

# Raw SQL against the tables, never the ORM: a migration that imports models
# breaks the moment the models move on, and this file must keep running
# against the schema as it was when the revision was written.
_BACKFILL = sa.text(
    f"""
    UPDATE {_BUDGET} AS b
       SET currency_code = UPPER(TRIM(p.currency))
      FROM {_PROJECT} AS p
     WHERE p.id = b.project_id
       AND (b.currency_code IS NULL OR TRIM(b.currency_code) = '')
       AND p.currency IS NOT NULL
       AND TRIM(p.currency) <> ''
       AND CHAR_LENGTH(TRIM(p.currency)) <= 3
    """  # noqa: S608 - table names are module constants, not user input
)


def _has_column(inspector: sa.engine.reflection.Inspector, table: str, column: str) -> bool:
    """True when ``table`` exists and carries ``column``."""
    if table not in inspector.get_table_names():
        return False
    return any(col["name"] == column for col in inspector.get_columns(table))


# data-rewrite-ack: table=oe_finance_budget growth=bounded rows=budget lines scoped by a project's own WBS x cost-category breakdown, bounded by that structure, not by elapsed time
# boot-repair: gap - backfills each budget's currency from its owning project, a per-row lookup no server_default can express; the four write paths are fixed, the rows they already wrote are not
def upgrade() -> None:
    """Fill blank budget currencies from the owning project. Never overwrite."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # A module can be absent on a partial install, and this revision must not
    # be the thing that stops an upgrade over a database that never had the
    # finance module enabled.
    if not _has_column(inspector, _BUDGET, "currency_code"):
        logger.info("%s.currency_code absent, nothing to backfill", _BUDGET)
        return
    if not _has_column(inspector, _PROJECT, "currency"):
        logger.info("%s.currency absent, nothing to backfill from", _PROJECT)
        return

    filled = bind.execute(_BACKFILL).rowcount
    logger.info("backfilled currency_code on %s budget line(s)", filled)


def downgrade() -> None:
    """Deliberately a no-op.

    There is no way to tell a value this migration wrote from one a user
    typed: both are just a currency code sitting in the column. Blanking the
    rows this revision touched would therefore mean blanking rows a user may
    have filled in themselves in the meantime, which destroys real data to
    undo a repair. Downgrading the schema is reversible; downgrading a
    backfill is not, so this side is intentionally empty.
    """
