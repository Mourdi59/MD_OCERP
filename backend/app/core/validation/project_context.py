# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
"""The project-derived half of a validation payload, built in one place.

A rule reads its inputs from the mapping the caller hands the engine, and a
rule whose input is missing returns nothing rather than failing. So a surface
that assembles that mapping by hand does not get a smaller report - it gets a
report silently missing whatever the absent key would have decided, and no exit
code says so. That is not hypothetical: ``BOQUnitSystemConsistencyRule`` shipped
registered and enabled while every caller omitted the one key it reads, and when
one caller finally wrote it the others carried on without it, so the same bill
answered differently depending on which button ran it.

The split this module draws is between the two halves of such a payload. The
rows are the caller's own: a bill, a contract's schedule of values and a
pipeline's upstream rows are projected differently on purpose, and forcing one
projection on all of them would change what every rule sees. Anything derived
from the *project* is not the caller's own, because it is the same fact whoever
asks. This module owns that half, and every surface that validates rows calls
it, so a new surface inherits a key it has never heard of.

The keys are always written, nulls included. An absent key and a null one used
to mean the same thing - "nothing to check" - which is exactly why a payload
nobody built properly was indistinguishable from a project no regional pack
claims. Now a null says the question was asked and nothing answered, and an
absent key says nobody asked at all.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.core.regional_packs import resolve_measurement_system

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Every key this module contributes. Named so a test can assert the property
#: ("each surface reaches the engine with these") without repeating the list,
#: and so adding a key here reaches every surface at once.
PROJECT_CONTEXT_KEYS: tuple[str, ...] = ("project_unit_system",)


def _as_uuid(project_id: uuid.UUID | str | None) -> uuid.UUID | None:
    """Coerce a project id to :class:`uuid.UUID`, or ``None`` if it is not one."""
    if isinstance(project_id, uuid.UUID):
        return project_id
    if isinstance(project_id, str) and project_id.strip():
        try:
            return uuid.UUID(project_id.strip())
        except ValueError:
            return None
    return None


async def _measurement_system(session: AsyncSession, project_id: uuid.UUID) -> str | None:
    """Resolve the measurement system the project's regional pack declares.

    Args:
        session: Live session the caller owns.
        project_id: Project the validation run is scoped to.

    Returns:
        ``"metric"`` or ``"imperial"`` when the project's country (or, as a
        fallback, its region) resolves to a regional pack, otherwise ``None``.
    """
    from app.modules.projects.models import Project

    row = (await session.execute(select(Project.country_code, Project.region).where(Project.id == project_id))).first()
    if row is None:
        return None
    country_code, region = row
    return resolve_measurement_system(country_code=country_code, region=region)


async def with_project_context(
    session: AsyncSession | None,
    project_id: uuid.UUID | str | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Return ``data`` plus the validation keys derived from its project.

    The session is the caller's own rather than one opened here. A validation
    run frequently happens inside a transaction that has not committed - the
    demo seeder validates projects it created moments earlier in the same unit
    of work - and a second session cannot see those rows, so it would resolve
    nothing and call the result "no pack answered".

    Args:
        session: The caller's live session. ``None`` is tolerated so a surface
            with no database in scope still produces a well-formed payload,
            and it is the one case where a null key means "could not ask"
            rather than "asked and nothing answered". The rule is silent
            either way, which is why the two are allowed to share a value;
            a caller that has a session should pass it rather than rely on it.
        project_id: Project the run is scoped to, as a UUID or its string form.
            ``None``, or an id no project matches, yields null keys.
        data: The caller's own payload - positions, markups, whatever its rules
            read. Left unmodified; a new mapping is returned.

    Returns:
        A new mapping carrying ``data`` plus every key in
        :data:`PROJECT_CONTEXT_KEYS`.
    """
    unit_system: str | None = None
    scoped = _as_uuid(project_id)
    if session is not None and scoped is not None:
        try:
            unit_system = await _measurement_system(session, scoped)
        except Exception:  # noqa: BLE001 - a payload is still owed to the caller
            # Degrading to a null key is safe in a way that omitting it is not:
            # null still says the question was asked, so the rule skips rather
            # than reporting that nobody built the payload.
            logger.warning("Could not resolve the measurement system for project=%s", scoped, exc_info=True)
    return {**data, "project_unit_system": unit_system}
