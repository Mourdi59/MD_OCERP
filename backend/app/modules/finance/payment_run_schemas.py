# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Payment run request and response schemas. Money is Decimal-as-string."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ISO_DATE = r"^\d{4}-\d{2}-\d{2}$"


def _real_date(value: str) -> str:
    date.fromisoformat(value)
    return value


class PaymentRunCreate(BaseModel):
    """Draw up a run: what falls due by ``due_by``, to pay on ``payment_date``."""

    model_config = ConfigDict(str_strip_whitespace=True)

    # Omitted: the projects that name no legal entity.
    legal_entity_id: UUID | None = None
    currency_code: str = Field(..., min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    payment_date: str = Field(..., pattern=_ISO_DATE)
    due_by: str | None = Field(default=None, pattern=_ISO_DATE)
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("currency_code")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("payment_date", "due_by")
    @classmethod
    def _valid_date(cls, value: str | None) -> str | None:
        return None if value is None else _real_date(value)

    @model_validator(mode="after")
    def _default_due_by(self) -> PaymentRunCreate:
        if self.due_by is None:
            self.due_by = self.payment_date
        return self


class PaymentRunItemUpdate(BaseModel):
    """Change what a draft run pays on one invoice."""

    amount: str = Field(..., max_length=50)

    @field_validator("amount")
    @classmethod
    def _positive(cls, value: str) -> str:
        try:
            parsed = Decimal(value.strip())
        except (InvalidOperation, AttributeError) as exc:
            raise ValueError("amount must be a number") from exc
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("amount must be more than zero")
        return format(parsed.quantize(Decimal("0.01")), "f")


class PaymentRunIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    item_id: str | None = None
    invoice_id: str | None = None


class PaymentRunItemResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    invoice_number: str = ""
    project_id: UUID
    project_name: str | None = None
    contact_id: str | None = None
    counterparty_name: str | None = None
    due_date: str | None = None
    amount: str
    open_at_proposal: str
    payment_id: UUID | None = None


class PaymentRunResponse(BaseModel):
    id: UUID
    run_number: str
    legal_entity_id: UUID | None = None
    legal_entity_name: str | None = None
    currency_code: str
    payment_date: str
    due_by: str
    status: str
    note: str | None = None
    created_by: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    executed_by: str | None = None
    executed_at: str | None = None
    created_at: str | None = None
    total: str
    item_count: int
    items: list[PaymentRunItemResponse] = Field(default_factory=list)
    issues: list[PaymentRunIssueResponse] = Field(default_factory=list)


class PaymentRunListResponse(BaseModel):
    items: list[PaymentRunResponse] = Field(default_factory=list)
    total: int = 0
