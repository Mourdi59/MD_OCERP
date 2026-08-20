# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resolve a procurement line's cost-spine link at the moment it is written.

Two spines, and the difference is the point of this file
=========================================================

The estimate reaches the rest of the platform along two different links, and
they are not interchangeable. Adding the wrong one is the mistake this module
exists to prevent, so it is written down here rather than left to be inferred
from the columns.

**The quantity spine** is ``boq_position_id`` pointing at ``oe_boq_position``.
It answers "how much of this scope item". Site inventory, site logistics,
formwork, progress, prefabrication, QMS and takeoff all carry it, because a
delivery note, a stock movement or an installed quantity is a fact about a
*measured item of work*.

**The money spine** is ``cost_line_id`` pointing at ``oe_costmodel_cost_line``.
It answers "what has this scope item cost us". Purchase orders, requisitions,
contracts, RFQs and the budget all carry it, because estimate, budget,
committed, actual and claimed have to roll up against one row before any of
them can be compared.

So a money table never grows a ``boq_position_id`` column and a quantity table
never grows a ``cost_line_id`` column. The two meet in exactly one place: the
cost line records which position it was generated from, and the position
records which cost line it rolls up into.

What that means for a request body
----------------------------------

The distinction is about *storage*, not about input. A buyer picks a bill
position, because that is the language of the job; nobody raising a purchase
order should be asked what a cost line is. So ``POItemCreate`` accepts
``boq_position_id`` as an input field while ``PurchaseOrderItem`` stores only
``cost_line_id``. The translation happens here, and the position id is not
persisted on the money row. A schema field and a column are allowed to differ,
and here they must.

Why the resolution happens on write and not on read
---------------------------------------------------

An order is a commitment made on a given day against the scope as it was
understood on that day. If the link were derived at read time from the position
the order once named, re-pointing that position at a different cost line
tomorrow would silently rewrite what last month's order committed against.
Resolving on write freezes the answer, which is the behaviour a cost report has
to have.

The failure this replaces
-------------------------

``CostLineRepository.po_committed_by_cost_line`` has been complete since it was
written, and has returned nothing on every project, because it filters
``cost_line_id IS NOT NULL`` and nothing ever wrote that column. The column,
the read side and the report all existed; only the writer was missing. A test
that asserts the happy path fills the column would have passed against a writer
that did nothing on the paths that matter, so the tests for this module assert
the empty case too.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: One procurement line's request for a cost-spine link, as
#: ``(cost_line_id, boq_position_id)``. Both are optional and both arrive as
#: strings, because that is how the schemas carry foreign ids (see
#: ``POItemCreate.wbs_id``). Supplying neither is ordinary: a line for site
#: welfare or a one-off hire belongs to no bill position, and gets no link.
CostSpineRef = tuple[str | None, str | None]


def _parse_uuid(raw: str | None, field: str) -> uuid.UUID | None:
    """Parse an optional id, rejecting a malformed one rather than dropping it.

    Silently ignoring an unparseable id would leave the line unlinked and the
    caller believing it was linked, which is the same invisible failure the
    module docstring describes.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except (ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: {raw!r} is not a valid id",
        ) from exc


async def _cost_lines_by_position(
    session: AsyncSession,
    project_id: uuid.UUID,
    position_ids: list[uuid.UUID],
) -> dict[uuid.UUID, uuid.UUID | None]:
    """Read ``Position.cost_line_id`` for a set of positions, in two queries.

    The position's own field is the single source of the answer. The cost line
    also records the position it came from, and that reverse index exists
    (``CostLineRepository.existing_by_boq_position``), but it is the spine
    generator's dedup index and carries a tie-break for a state its own
    docstring calls impossible. Reading it here would give procurement a second
    opinion about a link the position already states, which is how two
    resolvers that disagree come about.
    """
    from app.modules.boq.repository import PositionRepository

    repo = PositionRepository(session)
    positions = await repo.list_by_ids(position_ids)
    found = {pos.id: pos for pos in positions}

    missing = [str(pid) for pid in position_ids if pid not in found]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BoQ position not found: {', '.join(sorted(missing))}",
        )

    # A position carries no project of its own, so ownership is a fact about
    # its BOQ. Without this join the endpoint accepts another project's
    # position id and commits this project's money against it.
    project_by_boq = await repo.project_ids_for_boqs(sorted({pos.boq_id for pos in positions}))
    foreign = [str(pos.id) for pos in positions if project_by_boq.get(pos.boq_id) != project_id]
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"BoQ position not found in this project: {', '.join(sorted(foreign))}",
        )

    return {pos.id: pos.cost_line_id for pos in positions}


async def _cost_lines_in_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    candidates: set[uuid.UUID],
) -> set[uuid.UUID]:
    """Return the subset of ``candidates`` that are cost lines of this project.

    ``Position.cost_line_id`` is a plain column with no foreign key, by design:
    the cost line outlives the position it was generated from. The price of
    that is a link that can dangle, so what the position states is checked
    before it is copied onto a purchase order.
    """
    if not candidates:
        return set()
    from app.modules.costmodel.models import CostLine

    stmt = select(CostLine.id).where(CostLine.project_id == project_id, CostLine.id.in_(sorted(candidates)))
    rows = await session.execute(stmt)
    return set(rows.scalars().all())


async def positions_for_cost_lines(
    session: AsyncSession,
    cost_line_ids: Iterable[uuid.UUID | None],
) -> dict[str, uuid.UUID]:
    """Name the bill position behind each cost line, for the read side.

    Keyed by the cost line id as text, because that is how a response carries a
    foreign id and how every other map in this layer is keyed. A cost line with
    no position of its own simply does not appear, so a caller that finds
    nothing has the same answer as one that asked about a line off the bill.

    Why this is not the read-time resolution the module docstring rules out
    ----------------------------------------------------------------------

    That rule is about *what an order committed against*, and it still holds:
    ``cost_line_id`` is frozen on write and nothing here recomputes it. This
    only answers the next question, which is what to show a person reopening
    the order. They picked a position, the order stored a cost line, and a form
    that cannot turn that back into a position renders its picker empty and
    saves the emptiness. Accepting a field on write that cannot be returned on
    read is what makes an edit form forget the user's own choice.

    The honest limitation, since it is invisible later
    -------------------------------------------------

    What comes back is the position the cost line names *today*. ``CostLine``
    carries ``boq_position_id`` and an update can re-point it, so this is a
    derivation and not a record of what was typed. It is the right answer in
    every ordinary case and there is no better one available, because the money
    row deliberately does not store the position. A caller editing an order it
    did not change should send back the ``cost_line_id`` it was given rather
    than this position; ``resolve_cost_line_ids`` gives an explicit cost line
    priority precisely so that round trip is lossless.
    """
    wanted = {cid for cid in cost_line_ids if cid is not None}
    if not wanted:
        return {}
    from app.modules.costmodel.models import CostLine

    stmt = select(CostLine.id, CostLine.boq_position_id).where(CostLine.id.in_(sorted(wanted)))
    rows = await session.execute(stmt)
    return {str(line_id): position_id for line_id, position_id in rows.all() if position_id is not None}


async def resolve_cost_line_ids(
    session: AsyncSession,
    project_id: uuid.UUID,
    refs: Sequence[CostSpineRef],
) -> list[uuid.UUID | None]:
    """Resolve one cost line per procurement line, in the order given.

    Resolution order for each line:

    1. An explicit ``cost_line_id`` wins. It must belong to this project, and
       a 404 says so when it does not.
    2. Otherwise a ``boq_position_id`` is followed to the position's own
       ``cost_line_id``. The position must belong to this project.
    3. Otherwise the line is unlinked and the result is ``None``.

    A position whose ``cost_line_id`` is unset resolves to ``None`` as well.
    That is the normal state of a project whose cost spine has not been
    generated, and it is not an error: the order is still a valid order, it
    simply commits against nothing yet. Minting a cost line from here was
    considered and rejected. The spine generator skips section headers, derives
    a control account from the position's classification standard, and dedups
    inside one transaction; a line minted outside all of that would be absent
    from the account rollups that give a cost line its purpose, and would race
    the generator on the project/code unique constraint. Telling the buyer up
    front which positions are on the spine is the picker's job, not the
    writer's.

    Returns a list the same length as ``refs`` so a caller can zip it against
    its items.
    """
    if not refs:
        return []

    parsed = [(_parse_uuid(line, "cost_line_id"), _parse_uuid(pos, "boq_position_id")) for line, pos in refs]

    position_ids = sorted({pos for _, pos in parsed if pos is not None})
    by_position = await _cost_lines_by_position(session, project_id, position_ids) if position_ids else {}

    explicit = {line for line, _ in parsed if line is not None}
    derived = {cid for cid in by_position.values() if cid is not None}
    valid = await _cost_lines_in_project(session, project_id, explicit | derived)

    unknown = sorted(str(cid) for cid in explicit - valid)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cost line not found in this project: {', '.join(unknown)}",
        )

    resolved: list[uuid.UUID | None] = []
    for cost_line_id, position_id in parsed:
        if cost_line_id is not None:
            resolved.append(cost_line_id)
            continue
        if position_id is None:
            resolved.append(None)
            continue
        candidate = by_position.get(position_id)
        if candidate is not None and candidate not in valid:
            # The position names a cost line this project does not have. Write
            # nothing rather than a link the money reports cannot follow, and
            # leave a record, because the cause is upstream of procurement.
            logger.warning(
                "BoQ position %s points at cost line %s, which is not a cost line of project %s; "
                "leaving the procurement line unlinked",
                position_id,
                candidate,
                project_id,
            )
            candidate = None
        resolved.append(candidate)

    return resolved
