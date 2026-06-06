"""‌⁠‍Starter seed for cost items + assemblies.

Goal: a freshly-installed OpenConstructionERP (no CWICR import yet) should
not show "0 cost items / 0 assemblies" in the BOQ editor and Resource
Catalog. We ship ~50 universal baseline cost items and ~10 universal
assembly templates so the UI is never empty before the user picks a
regional CWICR catalogue.

The actual CWICR data set is 166k rows - these starter rows are a
seed-of-last-resort, intentionally small and region-tagged ``Universal``
so they never collide with regional imports.

Usage (auto-invoked by ``app.main`` lifespan):

    from app.scripts.seed_starter import seed_starter_data

    async with async_session_factory() as session:
        await seed_starter_data(session)
        await session.commit()

Disable with the ``OE_SKIP_STARTER_SEED=1`` env var (e.g. on production
deploys where the operator owns seed loading).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assemblies.models import Assembly, Component
from app.modules.costs.models import CostItem

logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).parent / "starter_seed_data.json"
_REGION = "Universal"
_SOURCE = "starter"


def _load_payload() -> dict:
    with open(_SEED_FILE, encoding="utf-8") as fh:
        return json.load(fh)


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return result.scalar_one()


async def _seed_cost_items(session: AsyncSession, rows: list[dict]) -> int:
    existing = await _count(session, CostItem)
    if existing > 0:
        logger.info("Starter seed: oe_costs_item already has %d rows, skipping cost items.", existing)
        return 0

    objects = [
        CostItem(
            code=row["code"],
            description=row["description"],
            descriptions={},
            unit=row["unit"],
            rate=row["rate"],
            currency=row.get("currency", "EUR"),
            source=_SOURCE,
            classification={},
            components=[],
            tags=row.get("tags", []),
            region=_REGION,
            is_active=True,
            metadata_={"starter_seed": True},
        )
        for row in rows
    ]
    session.add_all(objects)
    await session.flush()
    logger.info("Starter seed: inserted %d baseline cost items.", len(objects))
    return len(objects)


async def _seed_assemblies(session: AsyncSession, rows: list[dict]) -> int:
    existing = await _count(session, Assembly)
    if existing > 0:
        logger.info("Starter seed: oe_assemblies_assembly already has %d rows, skipping assemblies.", existing)
        return 0

    code_to_cost: dict[str, CostItem] = {}
    cost_q = await session.execute(select(CostItem).where(CostItem.region == _REGION))
    for ci in cost_q.scalars().all():
        code_to_cost[ci.code] = ci

    inserted = 0
    for row in rows:
        components_payload = row.get("components", [])

        total_rate = 0.0
        for comp in components_payload:
            cost = code_to_cost.get(comp["cost_code"])
            if cost is None:
                continue
            try:
                total_rate += float(comp["factor"]) * float(cost.rate)
            except (TypeError, ValueError):
                continue

        assembly = Assembly(
            code=row["code"],
            name=row["name"],
            description=row.get("description", ""),
            unit=row["unit"],
            category=row.get("category", ""),
            classification={},
            total_rate=f"{total_rate:.2f}",
            currency="EUR",
            bid_factor="1.0",
            regional_factors={},
            is_template=True,
            project_id=None,
            owner_id=None,
            is_active=True,
            metadata_={"starter_seed": True},
        )
        session.add(assembly)
        await session.flush()

        for sort_idx, comp in enumerate(components_payload):
            cost = code_to_cost.get(comp["cost_code"])
            unit_cost = cost.rate if cost is not None else "0"
            try:
                line_total = float(comp["factor"]) * float(unit_cost)
            except (TypeError, ValueError):
                line_total = 0.0
            session.add(
                Component(
                    assembly_id=assembly.id,
                    cost_item_id=cost.id if cost is not None else None,
                    catalog_resource_id=None,
                    description=comp.get("description", row["name"]),
                    factor=str(comp["factor"]),
                    quantity=str(comp["factor"]),
                    unit=comp.get("unit", row["unit"]),
                    unit_cost=str(unit_cost),
                    total=f"{line_total:.4f}",
                    sort_order=sort_idx,
                    metadata_={"starter_seed": True},
                ),
            )

        inserted += 1

    await session.flush()
    logger.info("Starter seed: inserted %d baseline assemblies.", inserted)
    return inserted


async def seed_starter_data(session: AsyncSession) -> dict[str, int]:
    """‌⁠‍Idempotently seed baseline cost items + assemblies if the tables are empty.

    Returns counts of newly inserted rows (zero when the tables already had
    data - meaning a regional CWICR catalogue or prior seed run won).
    """
    if os.environ.get("OE_SKIP_STARTER_SEED", "").strip().lower() in {"1", "true", "yes", "on"}:
        logger.info("Starter seed skipped via OE_SKIP_STARTER_SEED.")
        return {"cost_items": 0, "assemblies": 0}

    if not _SEED_FILE.exists():
        logger.warning("Starter seed file missing at %s; nothing to seed.", _SEED_FILE)
        return {"cost_items": 0, "assemblies": 0}

    payload = _load_payload()
    cost_count = await _seed_cost_items(session, payload.get("cost_items", []))
    asm_count = await _seed_assemblies(session, payload.get("assemblies", []))
    return {"cost_items": cost_count, "assemblies": asm_count}
