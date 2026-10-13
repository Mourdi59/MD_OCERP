# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What another module may ask the commitment matrix. Reads only.

Neither function writes, flushes or commits: both run inside the caller's own
read path with the caller's session. An item of another project is answered
as not found, never as an error.

``released`` means the item stands on a release decided in favour today: its
status is released, committed or closed. A planned item, a pending request, a
rejected or withdrawn one, an item on hold, one that needs a new release, and
an aborted or handed-over one are not released.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

RELEASED_STATES = ("released", "committed", "closed")


@dataclass(frozen=True)
class ReleaseState:
    found: bool
    released: bool = False


@dataclass(frozen=True)
class ItemOption:
    id: uuid.UUID
    code: str
    title: str
    status: str
    released: bool
    released_on: date | None = None
    lead_time_days: int | None = None


async def release_state(session: Any, project_id: uuid.UUID, item_id: uuid.UUID) -> ReleaseState:
    """Whether ``item_id`` is an item of this project and stands on a release today."""
    from app.modules.commitment_release.models import CommitmentItem

    item = await session.get(CommitmentItem, item_id)
    if item is None or item.project_id != project_id:
        return ReleaseState(found=False)
    return ReleaseState(found=True, released=item.status in RELEASED_STATES)


async def item_options(session: Any, project_id: uuid.UUID) -> list[ItemOption]:
    """Every item of the project that still stands, by code, with the day of its latest release."""
    from app.modules.commitment_release.repository import CommitmentRepository

    repo = CommitmentRepository(session)
    items = [i for i in await repo.list_items(project_id) if i.status not in ("aborted", "transferred")]
    released_on: dict[uuid.UUID, date] = {}
    for r in await repo.list_releases(project_id, [i.id for i in items]):
        if r.purpose == "release" and r.outcome == "released" and r.decided_at is not None:
            day = r.decided_at.date()
            if r.item_id not in released_on or day > released_on[r.item_id]:
                released_on[r.item_id] = day
    from datetime import UTC, datetime

    from app.modules.commitment_release import evaluator as ev
    from app.modules.commitment_release import figures

    today = datetime.now(UTC).date()
    lead: dict[uuid.UUID, int | None] = {}
    for i in items:
        # The same lead time the matrix shows: a linked plant item's comes from the plant register.
        plant = await figures.plant_item_dates_of(session, project_id, i.plant_item_id, today=today)
        lead[i.id], _source = ev.lead_time_in_force(
            plant_item_days=plant.lead_time_days if plant is not None else None,
            own_days=i.lead_time_days,
            requisition_days=await figures.requisition_lead_time(session, project_id, i.requisition_id)
            if i.lead_time_days is None
            else None,
        )
    return [
        ItemOption(
            id=i.id,
            code=i.code,
            title=i.title,
            status=i.status,
            released=i.status in RELEASED_STATES,
            released_on=released_on.get(i.id) if i.status in RELEASED_STATES else None,
            lead_time_days=lead[i.id],
        )
        for i in sorted(items, key=lambda i: i.code)
    ]


async def released_drawdown_for_risk(session: Any, project_id: uuid.UUID, risk_id: uuid.UUID) -> str | None:
    """The code of a released contingency drawdown item that names this risk, or ``None``.

    Such an item wrote the risk's drawdown record when its release was approved, so the record is
    the released money and is not the risk's alone to take back. An aborted item, or one whose
    release was withdrawn or rejected, no longer stands on a release and answers ``None``.
    """
    from app.modules.commitment_release.drawdown import ITEM_TYPE
    from app.modules.commitment_release.repository import CommitmentRepository

    for item in await CommitmentRepository(session).items_by_risk(project_id, risk_id, ITEM_TYPE):
        if item.status in RELEASED_STATES:
            return item.code
    return None
