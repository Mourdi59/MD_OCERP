"""Bordereau de prix Pydantic schemas."""

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_decimal(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


# ── Bordereau ────────────────────────────────────────────────────────────


class BordereauCreate(BaseModel):
    project_id: UUID
    name: str = Field(..., max_length=255)
    description: str = ""
    currency: str = Field(default="", max_length=10)


class BordereauUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    currency: str | None = Field(default=None, max_length=10)
    status: str | None = Field(default=None, max_length=50)
    is_locked: bool | None = None


class BordereauResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str
    currency: str
    status: str
    is_locked: bool
    created_at: str
    updated_at: str
    line_count: int = 0
    attached_boq_count: int = 0


class BordereauWithLines(BordereauResponse):
    lines: list["BordereauLineResponse"] = []


# ── BordereauLine ────────────────────────────────────────────────────────


class BordereauLineCreate(BaseModel):
    reference_code: str | None = Field(default=None, max_length=64)
    designation: str = ""
    unit: str = Field(default="", max_length=20)
    unit_rate: float = 0
    is_assembly: bool = False
    source: str = "manual"
    metadata: dict = Field(default_factory=dict)

    @field_validator("unit_rate", mode="before")
    @classmethod
    def _coerce_rate(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0


class BordereauLineUpdate(BaseModel):
    designation: str | None = None
    unit: str | None = Field(default=None, max_length=20)
    unit_rate: float | None = None
    reference_code: str | None = Field(default=None, max_length=64)
    is_assembly: bool | None = None
    version: int | None = None
    metadata: dict | None = None


class BordereauLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    bordereau_id: UUID
    reference_code: str | None
    designation: str
    unit: str
    unit_rate: float
    is_assembly: bool
    source: str
    version: int
    sort_order: int
    position_count: int = 0
    components: list["BordereauComponentResponse"] = []


# ── BordereauComponent ───────────────────────────────────────────────────


class BordereauComponentCreate(BaseModel):
    cost_item_id: UUID | None = None
    description: str = ""
    resource_type: str | None = None
    factor: float = 1.0
    quantity: float = 1.0
    unit: str = ""
    unit_cost: float = 0.0
    metadata: dict = Field(default_factory=dict)

    @field_validator("factor", "quantity", "unit_cost", mode="before")
    @classmethod
    def _coerce_numeric(cls, v: Any) -> float:
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0


class BordereauComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_id: UUID
    cost_item_id: UUID | None
    description: str
    resource_type: str | None
    factor: float
    quantity: float
    unit: str
    unit_cost: float
    total: float
    sort_order: int


# ── Attach / Detach ──────────────────────────────────────────────────────


class AttachBordereauRequest(BaseModel):
    bordereau_id: UUID


class AttachBordereauResponse(BaseModel):
    boq_id: UUID
    bordereau_id: UUID
    attached: bool
    positions_linked: int = 0


# ── Resolve (dedup) ──────────────────────────────────────────────────────


class ResolveLineRequest(BaseModel):
    reference_code: str | None = None
    designation: str = ""
    unit: str = ""


class ResolveLineResponse(BaseModel):
    line: BordereauLineResponse
    created: bool


# ── Propagation result ───────────────────────────────────────────────────


class PropagationResult(BaseModel):
    line_id: UUID
    affected_boq_ids: list[UUID] = []
    positions_updated: int = 0
    locked_boqs_skipped: list[UUID] = []
