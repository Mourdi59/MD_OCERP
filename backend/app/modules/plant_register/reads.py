# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The read path other modules use instead of keeping their own lead time (Decision 4).

The commitment release matrix (``CommitmentItem.plant_item_id``) and the
delivery model (``OwnerFurnishedItem``) call :func:`plant_item_dates` and show
what it returns. They never copy lead time, enquiry date or need date into a
column of their own (rule 12, grep-tested).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any


@dataclass(frozen=True)
class PlantItemDates:
    plant_item_id: uuid.UUID
    code: str
    need_date: date | None
    date_basis: str
    latest_order_date: date | None
    effective_lead_weeks: int | None
    lead_time_days: int | None
    enquiry_date: date | None
    lead_source: str
    long_lead: bool


async def plant_item_for_submittal(
    session: Any, project_id: uuid.UUID, submittal_id: uuid.UUID, *, today: date | None = None
) -> PlantItemDates | None:
    """The plant item that owns the lead time of this submittal, or ``None`` when none is linked.

    A submittal linked to a plant item shows the item's effective lead time;
    its own ``long_lead`` and ``lead_time_weeks`` are then read-only
    (``lead_time_owned_by_plant_item``). The submittals module and the UI ask
    here instead of comparing columns.
    """
    from sqlalchemy import select

    from app.modules.plant_register.models import PlantItem

    stmt = (
        select(PlantItem.id)
        .where(PlantItem.project_id == project_id, PlantItem.submittal_id == submittal_id)
        .where(PlantItem.status != "cancelled")
        .order_by(PlantItem.code)
        .limit(1)
    )
    item_id = (await session.execute(stmt)).scalar_one_or_none()
    return None if item_id is None else await plant_item_dates(session, project_id, item_id, today=today)


async def plant_item_dates(
    session: Any, project_id: uuid.UUID, plant_item_id: uuid.UUID, *, today: date | None = None
) -> PlantItemDates | None:
    """Derived dates of one item of this project; ``None`` for a missing or foreign item."""
    from app.modules.plant_register.models import PlantItem
    from app.modules.plant_register.service import PlantService

    svc = PlantService(session)
    if await svc.repo.get_scoped(PlantItem, project_id, plant_item_id) is None:
        return None
    views = await svc.item_views(project_id, today=today or datetime.now(UTC).date(), only=[plant_item_id])
    if not views:
        return None
    v = views[0]
    weeks = v["effective_lead_weeks"]
    return PlantItemDates(
        plant_item_id=plant_item_id,
        code=v["code"],
        need_date=v["need_date"],
        date_basis=v["date_basis"],
        latest_order_date=v["latest_order_date"],
        effective_lead_weeks=weeks,
        lead_time_days=weeks * 7 if weeks is not None else None,
        enquiry_date=v["basis_enquiry_date"],
        lead_source=v["lead_source"],
        long_lead=v["long_lead"],
    )
