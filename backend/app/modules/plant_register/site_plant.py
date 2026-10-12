# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Site plant positions: where a crane, a hoist or a piece of register plant stands on the site plan.

A position is a row of ``oe_site_logistics_plant_position``. It has a kind
from the plant catalogue (``site_plant_kinds``), a point in the local frame of
the site plan (metres, x to the right, y up, stored exactly as given) and,
optionally, the register item it is the place of and the expansion stage of
the site layout it belongs to. Placing is creating a row, moving is changing
its point or its stage, removing is deleting it.

Two links leave this module:

* the register item is ours and is checked against the project directly;
* the expansion stage belongs to the site logistics plan. It is read through
  the stage port below, and a stage id is stored only when that module
  confirms it for the project. While no provider is registered a stage id is
  refused (``stage_unavailable``): an id nobody can check is not stored.

Who may write is decided by the same function as for the register itself
(``PlantService.require_editor``), and the ``can`` flags of the listing are
computed by calling it, so a button never disagrees with the refusal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plant_register.errors import PlantError, conflict, not_found
from app.modules.plant_register.models import PlantItem
from app.modules.plant_register.service import PlantService

# ── the stage port ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StageRef:
    """An expansion stage of the site layout, as this module sees it."""

    id: uuid.UUID
    code: str = ""
    title: str = ""


class StageProvider(Protocol):
    """What the site logistics plan answers: the stage of this project with this id, or ``None``."""

    async def get_stage(self, session: Any, project_id: uuid.UUID, stage_id: uuid.UUID) -> StageRef | None: ...


_STAGES: list[StageProvider] = []


def register_stage_provider(provider: StageProvider) -> None:
    """Register (or replace) the provider of expansion stages."""
    _STAGES[:] = [provider]


def unregister_stage_provider() -> None:
    _STAGES.clear()


def stage_provider() -> StageProvider | None:
    return _STAGES[0] if _STAGES else None


async def position_project(session: Any, position_id: uuid.UUID) -> uuid.UUID | None:
    """The project a position belongs to, or ``None``: the resolver other modules check a position link with."""
    from app.modules.site_logistics.models import SitePlantPosition

    return await session.scalar(select(SitePlantPosition.project_id).where(SitePlantPosition.id == position_id))


# ── values ────────────────────────────────────────────────────────────────

# (field, digits before the point, decimals, may be negative): the columns of the table.
_NUMBERS: dict[str, tuple[int, int, bool]] = {
    "x": (9, 3, True),
    "y": (9, 3, True),
    "reach_m": (6, 2, False),
    "max_load_t": (8, 2, False),
    "power_demand_kva": (8, 2, False),
}
_TEXT = {"name": 255, "note": 10000}
_DATES = ("from_date", "to_date")
_LINKS = ("plant_item_id", "stage_id", "laydown_zone_id")
# A position without a place is not a position; everything else may be cleared.
_REQUIRED = ("kind", "x", "y")
FIELDS = ("kind", *_TEXT, *_NUMBERS, *_DATES, *_LINKS)


def _number(field: str, value: Any) -> Decimal:
    """A column value as an exact Decimal, refused when the column could not hold it unchanged."""
    whole, places, signed = _NUMBERS[field]
    if isinstance(value, bool) or isinstance(value, float):
        raise PlantError("position_number_invalid", detail=field)
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise PlantError("position_number_invalid", detail=field) from exc
    if not number.is_finite():
        raise PlantError("position_number_invalid", detail=field)
    sign, digits, exponent = number.as_tuple()
    decimals = max(-int(exponent), 0)
    before_point = len(digits) + int(exponent) if int(exponent) > 0 else len(digits) - decimals
    if decimals > places or before_point > whole or (sign and number != 0 and not signed):
        raise PlantError("position_number_invalid", detail=field)
    return number


def _day(field: str, value: Any) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise PlantError("position_date_invalid", detail=field) from exc


def _id(field: str, value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise not_found("link_not_found") if field != "stage_id" else not_found("stage_not_found") from exc


def clean(data: dict[str, Any]) -> dict[str, Any]:
    """The changes of one write, typed. A direct caller may hand in text; the columns get exact values."""
    out: dict[str, Any] = {}
    for field, value in data.items():
        if field not in FIELDS:
            continue
        if value is None:
            if field in _REQUIRED:
                raise PlantError("null_not_allowed", detail=field)
            out[field] = "" if field in _TEXT else None
        elif field in _NUMBERS:
            out[field] = _number(field, value)
        elif field in _DATES:
            out[field] = _day(field, value)
        elif field in _LINKS:
            out[field] = _id(field, value)
        else:
            text = str(value).strip()
            if len(text) > _TEXT.get(field, 40) or (field == "kind" and not text):
                raise PlantError("position_text_invalid", detail=field)
            out[field] = text
    return out


# ── service ───────────────────────────────────────────────────────────────


class SitePlantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.plant = PlantService(session)

    # reads

    async def get(self, project_id: uuid.UUID, position_id: uuid.UUID, *, lock: bool = False) -> Any:
        from app.modules.site_logistics.models import SitePlantPosition

        row = await self.plant.repo.get_scoped(SitePlantPosition, project_id, position_id, lock=lock)
        if row is None:
            raise not_found("position_not_found")
        return row

    async def listing(
        self, project_id: uuid.UUID, *, stage_id: uuid.UUID | None = None, plant_item_id: uuid.UUID | None = None
    ) -> list[dict[str, Any]]:
        """Every position of the project, each with the register item it places; what the site plan draws."""
        from app.modules.site_logistics.models import SitePlantPosition

        stmt = (
            select(SitePlantPosition, PlantItem.code, PlantItem.title, PlantItem.status)
            .outerjoin(
                PlantItem,
                (PlantItem.id == SitePlantPosition.plant_item_id) & (PlantItem.project_id == project_id),
            )
            .where(SitePlantPosition.project_id == project_id)
            .order_by(SitePlantPosition.kind, SitePlantPosition.name, SitePlantPosition.id)
        )
        if stage_id is not None:
            stmt = stmt.where(SitePlantPosition.stage_id == stage_id)
        if plant_item_id is not None:
            stmt = stmt.where(SitePlantPosition.plant_item_id == plant_item_id)
        return [
            {"position": row, "plant_item_code": code, "plant_item_title": title, "plant_item_status": status}
            for row, code, title, status in (await self.session.execute(stmt)).all()
        ]

    async def view(self, project_id: uuid.UUID, position_id: uuid.UUID) -> dict[str, Any]:
        row = await self.get(project_id, position_id)
        item = await self.plant.repo.get_scoped(PlantItem, project_id, row.plant_item_id) if row.plant_item_id else None
        return {
            "position": row,
            "plant_item_code": getattr(item, "code", None),
            "plant_item_title": getattr(item, "title", None),
            "plant_item_status": getattr(item, "status", None),
        }

    async def capabilities(
        self, project_id: uuid.UUID, user_id: uuid.UUID, *, can_edit: bool, can_manage: bool
    ) -> dict[str, dict[str, Any]]:
        """``place``, ``move`` and ``remove`` for this caller, each with the code the write would refuse with."""
        edit = (await self.plant.capabilities(project_id, user_id, can_edit=can_edit, can_manage=can_manage))["edit"]
        return {"place": dict(edit), "move": dict(edit), "remove": dict(edit)}

    # checks

    async def _check(self, project_id: uuid.UUID, row: Any, changed: dict[str, Any]) -> None:
        """Everything a stored position must satisfy; ``changed`` names what this write touched."""
        if "kind" in changed and row.kind not in (await self.plant.catalogue(project_id)).codes("site_plant_kinds"):
            raise PlantError("unknown_site_plant_kind")
        if row.from_date and row.to_date and row.to_date < row.from_date:
            raise PlantError("position_range_invalid")
        if changed.get("plant_item_id") is not None:
            item = await self.plant.repo.get_scoped(PlantItem, project_id, row.plant_item_id)
            if item is None:
                raise not_found("item_not_found")
            if item.status == "cancelled":
                raise conflict("item_closed")
        if changed.get("stage_id") is not None:
            provider = stage_provider()
            if provider is None:
                raise PlantError("stage_unavailable")
            if await provider.get_stage(self.session, project_id, row.stage_id) is None:
                raise not_found("stage_not_found")
        if changed.get("laydown_zone_id") is not None:
            from app.modules.site_logistics.models import LaydownZone

            if await self.plant.repo.get_scoped(LaydownZone, project_id, row.laydown_zone_id) is None:
                raise not_found("laydown_zone_not_found")

    # writes

    async def place(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> Any:
        from app.modules.site_logistics.models import SitePlantPosition

        values = clean(data)
        missing = [f for f in _REQUIRED if values.get(f) is None]
        if missing:
            raise PlantError("position_incomplete", detail=missing[0])
        row = SitePlantPosition(project_id=project_id, **values)
        await self._check(project_id, row, values)
        self.session.add(row)
        await self.session.flush()
        await self.plant._audit(actor_id, "site_plant_position", row.id, "placed", fields=sorted(values))
        return row

    async def move(
        self, project_id: uuid.UUID, position_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> Any:
        row = await self.get(project_id, position_id, lock=True)
        changed = {f: v for f, v in clean(data).items() if getattr(row, f) != v}
        if not changed:
            return row
        for field, value in changed.items():
            setattr(row, field, value)
        await self._check(project_id, row, changed)
        await self.session.flush()
        await self.plant._audit(actor_id, "site_plant_position", row.id, "moved", fields=sorted(changed))
        return row

    async def remove(self, project_id: uuid.UUID, position_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self.get(project_id, position_id, lock=True)
        await self.plant._audit(actor_id, "site_plant_position", row.id, "removed", fields=[row.kind])
        await self.session.delete(row)
        await self.session.flush()


# ── API shapes ────────────────────────────────────────────────────────────


def _exact(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("send lengths and loads as strings, not floats")
    return value


class PositionIn(BaseModel):
    """A change to a position; send only what changes. ``null`` clears a field that may be empty."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, max_length=255)
    x: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    y: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    reach_m: Decimal | None = Field(default=None, max_digits=8, decimal_places=2, ge=0)
    max_load_t: Decimal | None = Field(default=None, max_digits=10, decimal_places=2, ge=0)
    power_demand_kva: Decimal | None = Field(default=None, max_digits=10, decimal_places=2, ge=0)
    from_date: date | None = None
    to_date: date | None = None
    plant_item_id: uuid.UUID | None = None
    stage_id: uuid.UUID | None = None
    laydown_zone_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=10000)

    _numbers = field_validator("x", "y", "reach_m", "max_load_t", "power_demand_kva", mode="before")(_exact)

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class PositionCreate(PositionIn):
    """A new position: its kind and its point in the local frame of the site plan (metres, y up)."""

    kind: str = Field(min_length=1, max_length=40)
    x: Decimal = Field(max_digits=12, decimal_places=3)
    y: Decimal = Field(max_digits=12, decimal_places=3)


class Verdict(BaseModel):
    # Whether the action exists here at all (hide when false); placing, moving and
    # removing a position exist in every state, so a refusal is shown with its reason.
    applies: bool
    allowed: bool
    reason: str | None = None


class PositionOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    kind: str
    name: str
    x: Decimal | None
    y: Decimal | None
    reach_m: Decimal | None
    max_load_t: Decimal | None
    power_demand_kva: Decimal | None
    from_date: date | None
    to_date: date | None
    plant_item_id: uuid.UUID | None
    plant_item_code: str | None = None
    plant_item_title: str | None = None
    plant_item_status: str | None = None
    stage_id: uuid.UUID | None
    laydown_zone_id: uuid.UUID | None
    equipment_id: uuid.UUID | None
    note: str
    # ``move`` and ``remove`` for this caller, with the code the write would answer.
    can: dict[str, Verdict] = Field(default_factory=dict)

    @classmethod
    def of(cls, view: dict[str, Any], can: dict[str, dict[str, Any]]) -> PositionOut:
        row = view["position"]
        return cls(
            **{name: getattr(row, name) for name in ("id", "project_id", "equipment_id", *FIELDS)},
            plant_item_code=view["plant_item_code"],
            plant_item_title=view["plant_item_title"],
            plant_item_status=view["plant_item_status"],
            can={"move": can["move"], "remove": can["remove"]},
        )


class PositionList(BaseModel):
    items: list[PositionOut]
    total: int
    offset: int
    limit: int
    # ``place`` for this caller on this project.
    can: dict[str, Verdict]
