"""Widen ``classified_at`` to an aware timestamp on databases that predate it.

``RouteAssessment.classified_at`` was the one naive ``DateTime`` column in the
platform: the other 197 module timestamps all declare ``timezone=True``. The
service has always stamped it with an aware ``datetime.now(UTC)``, which asyncpg
refuses to put into a naive ``timestamp``, so the column was simply declared
wrong and the declaration has now been corrected.

Correcting the model corrects new installations, because ``create_all`` builds
the column as ``timestamptz`` from the start. It does nothing for existing ones.
The auto-migrator that stands in for Alembic on module tables only ever issues
``ADD COLUMN`` / ``ADD CONSTRAINT`` / ``CREATE INDEX``; it never changes the type
of a column that is already there. An upgrade would therefore keep the naive
column and keep the failure, and an upgrade is the case this release exists to
get right.

So the widening happens here, next to the sequence repair that lives in the boot
path for the same reason. ``AT TIME ZONE 'UTC'`` is not decoration: without it
PostgreSQL reads the stored values in the session's time zone, and those values
are UTC wall-clock, so any session that is not itself UTC would shift every
historical classification instead of relabelling it.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_TABLE = "oe_project_route_assessment"
_COLUMN = "classified_at"

# Fixed table and column names, no user input reaches this statement.
_WIDEN = (
    f'ALTER TABLE "{_TABLE}" ALTER COLUMN "{_COLUMN}" '  # noqa: S608
    f"TYPE timestamptz USING \"{_COLUMN}\" AT TIME ZONE 'UTC'"
)


async def widen_classified_at(conn: AsyncConnection) -> int:
    """Convert a naive ``classified_at`` to ``timestamptz``, preserving its instant.

    Args:
        conn: An open async PostgreSQL connection (inside a transaction).

    Returns:
        1 when the column was widened, 0 when there was nothing to do, which is
        the case on a fresh database and on every boot after the first.
    """
    has_table = await conn.run_sync(lambda c: inspect(c).has_table(_TABLE))
    if not has_table:
        # Fresh database: create_all has not built the table yet, and it will
        # build the column aware, so there is nothing to widen.
        return 0

    columns = await conn.run_sync(lambda c: inspect(c).get_columns(_TABLE))
    column = next((col for col in columns if col["name"] == _COLUMN), None)
    if column is None:
        return 0

    # ``timezone`` is what separates the two PostgreSQL types here, and reading
    # it off the reflected type asks the database rather than assuming from the
    # version we upgraded from.
    if getattr(column["type"], "timezone", False):
        return 0

    await conn.execute(text(_WIDEN))
    logger.info("Widened %s.%s to timestamptz", _TABLE, _COLUMN)
    return 1
