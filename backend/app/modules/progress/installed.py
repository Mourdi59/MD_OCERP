# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Installed quantity per bill position, defined once.

There is no installed-quantity table. What the site reports is a percent
complete per position, append-only, and the quantity installed is the planned
quantity times the LATEST reading - never the largest, because a correction is
recorded as a new, lower entry. Post-calculation needs this number per position
and the KPI catalog needs it per row of a portfolio query, and two spellings of
it would be two answers to "how much did we build" that drift apart the first
time somebody touches one of them.

So both read it from here, and both read it as SQL. Post-calculation used to
multiply in Python after fetching the percent; it now asks the database for the
product through :func:`installed_quantity_expr`, the same expression the KPI
binder puts into its SELECT, and the parity test in
``tests/unit/test_performance_benchmark.py`` holds the two readers together.

The product is cast to ``NUMERIC(28, 6)``. ``numeric_value`` reads the text
quantity column as a double, and a double times a percent lands on binary
noise (``16.649999999999998``) that a report would print. Six places is far
below anything a site measures and far above anything the reports display.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection
from decimal import Decimal
from typing import Any

from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Subquery
from sqlalchemy.sql.elements import ColumnElement

from app.core.sql_numeric import numeric_value
from app.modules.progress.models import ProgressEntry

#: Scale of a computed installed quantity, see the module docstring.
INSTALLED_QUANTITY_SCALE = 6
_INSTALLED_TYPE = Numeric(28, INSTALLED_QUANTITY_SCALE)


def latest_percent_subquery(
    *,
    project_id: uuid.UUID | None = None,
    position_ids: Collection[uuid.UUID] | None = None,
) -> Subquery:
    """One row per position: its latest ``percent_complete``.

    Columns are ``boq_position_id``, ``project_id`` and ``percent_complete``;
    one row per position and project, which is one row per position on any
    sane data.
    "Latest" is the progress module's own total order (``seq`` first), so this
    and :meth:`ProgressRepository.latest_pct_for_positions` cannot pick
    different winners.

    Args:
        project_id: Restrict to one project's entries. ``None`` reads every
            project; the caller scopes the outer query.
        position_ids: Restrict to these positions.
    """
    from app.modules.progress.repository import _latest_first

    ranked = select(
        ProgressEntry.boq_position_id,
        ProgressEntry.project_id,
        ProgressEntry.percent_complete,
        # Partitioned by project as well as position, so a reading filed under
        # another project never wins a position here: the project-filtered
        # call and the unfiltered portfolio call pick the same entry.
        func.row_number()
        .over(partition_by=(ProgressEntry.boq_position_id, ProgressEntry.project_id), order_by=_latest_first())
        .label("rn"),
    ).where(ProgressEntry.boq_position_id.is_not(None))
    if project_id is not None:
        ranked = ranked.where(ProgressEntry.project_id == project_id)
    if position_ids is not None:
        ranked = ranked.where(ProgressEntry.boq_position_id.in_(list(position_ids)))
    inner = ranked.subquery()
    return (
        select(inner.c.boq_position_id, inner.c.project_id, inner.c.percent_complete)
        .where(inner.c.rn == 1)
        .subquery("latest_progress")
    )


def installed_quantity_expr(planned_quantity: Any, percent_complete: Any) -> ColumnElement[Decimal]:
    """``planned quantity * latest percent / 100`` as a SQL expression.

    Args:
        planned_quantity: The position's text quantity column.
        percent_complete: The latest percent, as selected from
            :func:`latest_percent_subquery`. NULL (no reading) stays NULL, so
            a position nobody has reported on is unknown rather than zero.
    """
    return cast(numeric_value(planned_quantity) * percent_complete / 100, _INSTALLED_TYPE)


async def installed_quantities(
    session: AsyncSession,
    project_id: uuid.UUID,
    position_ids: Collection[uuid.UUID],
) -> dict[uuid.UUID, Decimal]:
    """``{position_id: installed quantity}`` for the positions with a reading.

    Positions with no progress entry are absent rather than zero; callers that
    need a zero default supply it themselves.
    """
    from app.modules.boq.models import Position

    ids = list(position_ids)
    if not ids:
        return {}
    latest = latest_percent_subquery(project_id=project_id, position_ids=ids)
    stmt = select(Position.id, installed_quantity_expr(Position.quantity, latest.c.percent_complete)).join(
        latest, latest.c.boq_position_id == Position.id
    )
    rows = (await session.execute(stmt)).all()
    return {row[0]: Decimal(row[1]) for row in rows if row[1] is not None}


__all__ = [
    "INSTALLED_QUANTITY_SCALE",
    "installed_quantities",
    "installed_quantity_expr",
    "latest_percent_subquery",
]
