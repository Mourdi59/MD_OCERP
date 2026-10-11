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
