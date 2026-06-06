"""‌⁠‍Procurement Pydantic schemas - request/response models."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _validate_non_negative_decimal(v: str) -> str:
    """‌⁠‍Validate that a string is a valid non-negative decimal number."""
    try:
        d = Decimal(v)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid decimal value: {v!r}") from exc
    if d < 0:
        raise ValueError(f"Value must be non-negative, got {v!r}")
    return v


# ── Purchase Order ───────────────────────────────────────────────────────────


class POItemCreate(BaseModel):
    """‌⁠‍Create a line item within a purchase order."""

    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(..., min_length=1, max_length=500)
    quantity: str = Field(default="1", max_length=50)
    unit: str | None = Field(default=None, max_length=20)
    unit_rate: str = Field(default="0", max_length=50)
    amount: str = Field(default="0", max_length=50)
    wbs_id: str | None = Field(default=None, max_length=36)
    cost_category: str | None = Field(default=None, max_length=100)
    sort_order: int = Field(default=0, ge=0)

    @field_validator("quantity", "unit_rate", "amount")
    @classmethod
    def _check_non_negative_decimal(cls, v: str) -> str:
        return _validate_non_negative_decimal(v)


class POCreate(BaseModel):
    """Create a new purchase order."""

    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: UUID
    vendor_contact_id: str | None = Field(default=None, max_length=36)
    po_number: str | None = Field(default=None, max_length=50)
    po_type: str = Field(default="standard", max_length=50)
    issue_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=20)
    delivery_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=20)
    # Empty by default - the service inherits the parent project's currency
    # when the caller does not supply one. Never hardcode EUR (task #217).
    currency_code: str = Field(default="", max_length=10)
    amount_subtotal: str = Field(default="0", max_length=50)
    tax_amount: str = Field(default="0", max_length=50)
    amount_total: str = Field(default="0", max_length=50)
    status: str = Field(default="draft", max_length=50)
    payment_terms: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)
    items: list[POItemCreate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount_subtotal", "tax_amount", "amount_total")
    @classmethod
    def _check_non_negative_decimal(cls, v: str) -> str:
        return _validate_non_negative_decimal(v)


class POUpdate(BaseModel):
    """Partial update for a purchase order."""

    model_config = ConfigDict(str_strip_whitespace=True)

    vendor_contact_id: str | None = Field(default=None, max_length=36)
    po_type: str | None = Field(default=None, max_length=50)
    issue_date: str | None = Field(default=None, max_length=20)
    delivery_date: str | None = Field(default=None, max_length=20)
    currency_code: str | None = Field(default=None, max_length=10)
    amount_subtotal: str | None = Field(default=None, max_length=50)
    tax_amount: str | None = Field(default=None, max_length=50)
    amount_total: str | None = Field(default=None, max_length=50)
    status: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=5000)
    items: list[POItemCreate] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("amount_subtotal", "tax_amount", "amount_total")
    @classmethod
    def _check_non_negative_decimal(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _validate_non_negative_decimal(v)


# ── Purchase Order responses ─────────────────────────────────────────────────


class POItemResponse(BaseModel):
    """PO item returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    po_id: UUID
    description: str
    quantity: str = "1"
    unit: str | None = None
    unit_rate: str = "0"
    amount: str = "0"
    wbs_id: str | None = None
    cost_category: str | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class POResponse(BaseModel):
    """Purchase order returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    project_id: UUID
    vendor_contact_id: str | None = None
    vendor_name: str | None = None
    po_number: str
    po_type: str = "standard"
    issue_date: str | None = None
    delivery_date: str | None = None
    currency_code: str = ""  # empty until set - never assume EUR (task #217)
    amount_subtotal: str = "0"
    tax_amount: str = "0"
    amount_total: str = "0"
    status: str = "draft"
    payment_terms: str | None = None
    notes: str | None = None
    created_by: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    items: list[POItemResponse] = Field(default_factory=list)
    # ── Retainage (Gap F) ────────────────────────────────────────────────
    # ``retention_percent`` / ``retain_on_receipt`` are persisted columns;
    # ``retainage_amount`` / ``retainage_held`` are computed by the ORM model
    # as METHODS (``po.retainage_amount()``). With ``from_attributes`` pydantic
    # reads the bound method object, which is not a string. The before-validator
    # below collapses any callable to "0" so model_validate succeeds; the router
    # then stamps the real computed values via ``po.retainage_amount()``.
    # Decimal-as-string, always in this PO's ``currency_code``.
    retention_percent: str = "0.00"
    retain_on_receipt: bool = False
    retainage_amount: str = "0"
    retainage_held: str = "0"
    # ── Vendor prequalification gate (TOP-30 #20) ────────────────────────
    # Non-blocking warnings about the PO's vendor (e.g. a rejected/suspended
    # prequalification). A hard-blocked vendor never reaches this response -
    # the service raises 409 before the PO is written. Empty for clean or
    # ad-hoc vendors. Stamped by the router from the service gate; not a
    # persisted column.
    vendor_warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_validator("retention_percent", mode="before")
    @classmethod
    def _coerce_retention_percent(cls, v: Any) -> str:
        """Numeric(5,2) arrives as a Decimal from the ORM - render as string."""
        if v is None:
            return "0.00"
        return str(v)

    @field_validator("retainage_amount", "retainage_held", mode="before")
    @classmethod
    def _coerce_retainage(cls, v: Any) -> str:
        """These are ORM *methods*, not columns. ``from_attributes`` hands us
        the bound method object - collapse any callable (or None) to "0"; the
        router stamps the real computed value after validation."""
        if v is None or callable(v):
            return "0"
        return str(v)


class PORetainageReleaseResponse(BaseModel):
    """A single retainage-release audit-log entry returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    po_id: UUID
    release_date: str
    release_amount: str
    release_reason: str | None = None
    released_by_id: UUID | None = None
    created_at: datetime

    @field_validator("release_amount", mode="before")
    @classmethod
    def _coerce_release_amount(cls, v: Any) -> str:
        """Numeric(18,4) arrives as a Decimal from the ORM - render as string."""
        if v is None:
            return "0"
        return str(v)


class PORetainageReleaseRequest(BaseModel):
    """Request body for releasing withheld retainage on a PO."""

    model_config = ConfigDict(str_strip_whitespace=True)

    amount: str = Field(..., max_length=50)
    reason: str | None = Field(default=None, max_length=255)

    @field_validator("amount")
    @classmethod
    def _check_positive_decimal(cls, v: str) -> str:
        """A release must be a strictly positive decimal amount."""
        try:
            d = Decimal(v)
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid decimal value: {v!r}") from exc
        if d <= 0:
            raise ValueError(f"Release amount must be positive, got {v!r}")
        return v


class PORetainageReleaseListResponse(BaseModel):
    """Paginated list of retainage-release records for a PO."""

    items: list[PORetainageReleaseResponse]
    total: int


class POListResponse(BaseModel):
    """Paginated list of purchase orders."""

    items: list[POResponse]
    total: int
    offset: int
    limit: int


# ── Goods Receipt ────────────────────────────────────────────────────────────


class GRItemCreate(BaseModel):
    """Create a goods receipt line item."""

    model_config = ConfigDict(str_strip_whitespace=True)

    po_item_id: UUID | None = None
    quantity_ordered: str = Field(default="0", max_length=50)
    quantity_received: str = Field(default="0", max_length=50)
    quantity_rejected: str = Field(default="0", max_length=50)
    rejection_reason: str | None = None

    @field_validator("quantity_ordered", "quantity_received", "quantity_rejected")
    @classmethod
    def _check_non_negative_decimal(cls, v: str) -> str:
        return _validate_non_negative_decimal(v)


class GRCreate(BaseModel):
    """Create a goods receipt against a PO."""

    model_config = ConfigDict(str_strip_whitespace=True)

    po_id: UUID
    receipt_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", max_length=20)
    received_by_id: UUID | None = None
    delivery_note_number: str | None = Field(default=None, max_length=100)
    status: str = Field(default="draft", max_length=50)
    notes: str | None = Field(default=None, max_length=5000)
    items: list[GRItemCreate] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Goods Receipt responses ──────────────────────────────────────────────────


class GRItemResponse(BaseModel):
    """GR item returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    receipt_id: UUID
    po_item_id: UUID | None = None
    quantity_ordered: str = "0"
    quantity_received: str = "0"
    quantity_rejected: str = "0"
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class GRResponse(BaseModel):
    """Goods receipt returned from the API."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    po_id: UUID
    receipt_date: str
    received_by_id: UUID | None = None
    delivery_note_number: str | None = None
    status: str = "draft"
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    items: list[GRItemResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    # api-HIGH (GR tab): the frontend Goods-Receipts table renders these
    # fields, but they were missing from the response and rendered blank.
    # All ADDITIVE + OPTIONAL - existing consumers are unaffected.
    #   * gr_reference   - friendly label, aliased from delivery_note_number
    #   * po_number      - parent PO number (populated by the router/service)
    #   * received_qty   - Σ items[].quantity_received  (Decimal-as-string)
    #   * ordered_qty    - Σ items[].quantity_ordered   (Decimal-as-string)
    #   * description    - passthrough notes/summary for the row
    gr_reference: str | None = Field(
        default=None,
        # ``delivery_note_number`` is the natural reference shown to the user;
        # populate gr_reference from it when serialising from the ORM model.
        validation_alias="delivery_note_number",
    )
    po_number: str | None = None
    # Decimal quantities MUST serialise as STRING (never float) - mirrors
    # quantity_received / quantity_ordered on GRItemResponse.
    received_qty: str | None = None
    ordered_qty: str | None = None
    description: str | None = Field(default=None, validation_alias="notes")

    @model_validator(mode="after")
    def _aggregate_item_quantities(self) -> "GRResponse":
        """Aggregate received_qty / ordered_qty from the GR line items.

        api-HIGH (GR tab): the FE shows per-receipt received vs ordered
        totals. We sum the already-serialised string quantities on
        ``items`` so the aggregate is computed from exactly what the API
        returns. Both totals are emitted as canonical Decimal STRINGS
        (never floats). Only fills the aggregates when they were not set
        explicitly, so it stays purely additive.
        """
        if self.received_qty is None or self.ordered_qty is None:
            received = Decimal("0")
            ordered = Decimal("0")
            for item in self.items:
                try:
                    received += Decimal(item.quantity_received or "0")
                except (InvalidOperation, ValueError, TypeError):
                    pass
                try:
                    ordered += Decimal(item.quantity_ordered or "0")
                except (InvalidOperation, ValueError, TypeError):
                    pass
            if self.received_qty is None:
                self.received_qty = format(received, "f")
            if self.ordered_qty is None:
                self.ordered_qty = format(ordered, "f")
        return self


class GRListResponse(BaseModel):
    """Paginated list of goods receipts."""

    items: list[GRResponse]
    total: int


# ── Stats ────────────────────────────────────────────────────────────────


class ProcurementStatsResponse(BaseModel):
    """Aggregate statistics for procurement within a project."""

    total_pos: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    total_committed: str = "0"
    total_received: int = 0
    pending_delivery_count: int = 0


# ── 3-way match status (Wave 2 / T4) ─────────────────────────────────────


class POLineMatchStatus(BaseModel):
    """‌⁠‍Per-PO-line 3-way match summary.

    ``match_status`` collapses the PO/GR/Invoice quantity comparison into
    one tag the UI badge consumes:

    * ``ok``             - invoiced and received quantities cover the order.
    * ``partial``        - some quantity received or invoiced, more pending.
    * ``unmatched``      - nothing received or invoiced yet.
    * ``over_received``  - confirmed GR quantity exceeds the PO line.
    * ``over_invoiced``  - invoiced quantity exceeds received quantity.
    """

    model_config = ConfigDict(from_attributes=True)

    line_id: UUID
    description: str
    ordered_qty: str = "0"
    received_qty: str = "0"
    invoiced_qty: str = "0"
    match_status: str = "unmatched"


class POMatchStatusResponse(BaseModel):
    """Aggregate 3-way match envelope for a single PO."""

    po_id: UUID
    po_number: str
    overall_status: str = "unmatched"
    lines: list[POLineMatchStatus] = Field(default_factory=list)


# ── Supplier scorecard (Wave 2 / T4) ─────────────────────────────────────


class SupplierScorecardResponse(BaseModel):
    """Trailing-window supplier performance KPIs.

    ``on_time_delivery_pct`` / ``qty_variance_pct`` / ``gr_rejection_rate``
    are decimals in 0.0–1.0 (frontend renders as ``× 100`` percentages).
    ``total_po_value`` is summed across the trailing window in the supplier
    or project currency, returned as a string-Decimal for compatibility
    with the PO ``amount_total`` model field.
    """

    model_config = ConfigDict(from_attributes=True)

    supplier_contact_id: str
    supplier_name: str | None = None
    project_id: UUID | None = None
    period_days: int = 365
    total_po_count: int = 0
    total_po_value: str = "0"
    currency: str = ""
    on_time_delivery_pct: float = 0.0
    qty_variance_pct: float = 0.0
    gr_rejection_rate: float = 0.0
    total_gr_count: int = 0
    # Number of GRs counted as on-time (numerator of on_time_delivery_pct).
    on_time_count: int = 0
    # GRs whose parent PO had no delivery_date - excluded from on-time
    # denominator so unscheduled POs do not inflate the score (P0-2).
    unscheduled_count: int = 0
