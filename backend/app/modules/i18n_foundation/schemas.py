# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Internationalization foundation Pydantic schemas for request/response validation.

Covers exchange rates, countries, work calendars, tax configurations,
and utility schemas for currency conversion and working-day calculations.
"""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── ExchangeRate ─────────────────────────────────────────────────────────


class ExchangeRateCreate(BaseModel):
    """Create a new exchange rate entry."""

    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    rate: str = Field(..., min_length=1, max_length=50)
    rate_date: str = Field(..., min_length=1, max_length=20)
    source: str = Field(default="manual", max_length=50)
    is_manual: bool = Field(default=True)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExchangeRateUpdate(BaseModel):
    """Update an exchange rate (all fields optional)."""

    from_currency: str | None = Field(default=None, min_length=3, max_length=3)
    to_currency: str | None = Field(default=None, min_length=3, max_length=3)
    rate: str | None = Field(default=None, min_length=1, max_length=50)
    rate_date: str | None = Field(default=None, min_length=1, max_length=20)
    source: str | None = Field(default=None, max_length=50)
    is_manual: bool | None = None
    metadata: dict[str, Any] | None = None


class ExchangeRateResponse(BaseModel):
    """Exchange rate in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    from_currency: str
    to_currency: str
    rate: str
    rate_date: str
    source: str
    is_manual: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class ExchangeRateListResponse(BaseModel):
    """Paginated list of exchange rates."""

    items: list[ExchangeRateResponse]
    total: int


# ── Country ──────────────────────────────────────────────────────────────


class CountryResponse(BaseModel):
    """Country in API responses.

    Countries are seeded - no Create/Update schemas needed for now.
    Admin endpoints will be added later.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    iso_code: str
    iso_code_3: str | None
    name_en: str
    name_translations: dict[str, str]
    currency_default: str | None
    measurement_default: str | None
    phone_code: str | None
    address_format_template: dict[str, Any] | None
    region_group: str | None
    is_active: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime


class CountryListResponse(BaseModel):
    """Paginated list of countries."""

    items: list[CountryResponse]
    total: int


# ── WorkCalendar ─────────────────────────────────────────────────────────


# ISO weekday numbers, Monday = 1 through Sunday = 7. That is the convention
# ``I18nFoundationService.get_working_days`` counts with, because it matches
# each date's ``isoweekday()`` against this list. A value outside 1..7 is not a
# weekday under that reading, matches no date, and turns into a working week
# quietly shorter than the one that was asked for - so it is refused on the way
# in rather than stored. Note the zero-based conventions in reach of anyone
# authoring a calendar: JavaScript's ``getDay()`` counts Sunday as 0, and this
# platform's other work calendar (``app/core/calendar.py`` and the
# schedule module) counts Monday as 0. Neither is this one.
IsoWeekday = Annotated[int, Field(ge=1, le=7)]


class WorkCalendarCreate(BaseModel):
    """Create a new work calendar."""

    country_code: str = Field(..., min_length=2, max_length=2)
    name: str = Field(..., min_length=1, max_length=255)
    name_translations: dict[str, str] | None = None
    year: str = Field(..., min_length=4, max_length=4)
    work_hours_per_day: str = Field(default="8", max_length=10)
    work_days: list[IsoWeekday] = Field(..., min_length=1)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkCalendarUpdate(BaseModel):
    """Update a work calendar (all fields optional)."""

    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    name_translations: dict[str, str] | None = None
    year: str | None = Field(default=None, min_length=4, max_length=4)
    work_hours_per_day: str | None = Field(default=None, max_length=10)
    work_days: list[IsoWeekday] | None = None
    exceptions: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None


class WorkCalendarResponse(BaseModel):
    """Work calendar in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    name: str
    name_translations: dict[str, str] | None
    year: str
    work_hours_per_day: str
    # Deliberately unconstrained, unlike the write schemas above: a row written
    # before the guard existed still has to be readable, and refusing to
    # serialise it would hide the very calendar an operator needs to see to fix.
    work_days: list[int]
    exceptions: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class WorkCalendarListResponse(BaseModel):
    """Paginated list of work calendars."""

    items: list[WorkCalendarResponse]
    total: int


# ── TaxConfiguration ─────────────────────────────────────────────────────

#: Mirrors ``TAX_COMBINATIONS`` in models.py. How a rate combines with the
#: federal rate of the same country; see the model for what each means.
TaxCombination = Literal["national", "federal", "replaces_federal", "stacks_on_federal"]


class TaxConfigCreate(BaseModel):
    """Create a new tax configuration."""

    country_code: str = Field(..., min_length=2, max_length=2)
    tax_name: str = Field(..., min_length=1, max_length=255)
    tax_name_translations: dict[str, str] | None = None
    tax_code: str | None = Field(default=None, max_length=50)
    rate_pct: str = Field(..., min_length=1, max_length=20)
    tax_type: str = Field(..., min_length=1, max_length=50)
    combination: TaxCombination = "national"
    effective_from: str | None = Field(default=None, max_length=20)
    effective_to: str | None = Field(default=None, max_length=20)
    is_default: bool = Field(default=False)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaxConfigUpdate(BaseModel):
    """Update a tax configuration (all fields optional)."""

    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    tax_name: str | None = Field(default=None, min_length=1, max_length=255)
    tax_name_translations: dict[str, str] | None = None
    tax_code: str | None = Field(default=None, max_length=50)
    rate_pct: str | None = Field(default=None, min_length=1, max_length=20)
    tax_type: str | None = Field(default=None, min_length=1, max_length=50)
    combination: TaxCombination | None = None
    effective_from: str | None = Field(default=None, max_length=20)
    effective_to: str | None = Field(default=None, max_length=20)
    is_default: bool | None = None
    metadata: dict[str, Any] | None = None


class TaxConfigResponse(BaseModel):
    """Tax configuration in API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    country_code: str
    tax_name: str
    tax_name_translations: dict[str, str] | None
    tax_code: str | None
    rate_pct: str
    tax_type: str
    combination: str
    effective_from: str | None
    effective_to: str | None
    is_default: bool
    metadata: dict[str, Any] = Field(alias="metadata_")
    created_at: datetime
    updated_at: datetime


class TaxConfigListResponse(BaseModel):
    """Paginated list of tax configurations."""

    items: list[TaxConfigResponse]
    total: int


# ── Utility Schemas ──────────────────────────────────────────────────────


class ConvertRequest(BaseModel):
    """Request to convert an amount between currencies."""

    from_currency: str = Field(..., min_length=3, max_length=3)
    to_currency: str = Field(..., min_length=3, max_length=3)
    amount: str = Field(..., min_length=1)
    date: str | None = Field(default=None, max_length=20)


class ConvertResponse(BaseModel):
    """Result of a currency conversion."""

    original_amount: str
    converted_amount: str
    from_currency: str
    to_currency: str
    rate: str
    rate_date: str


class WorkingDaysRequest(BaseModel):
    """Request to calculate working days between two dates."""

    country_code: str = Field(..., min_length=2, max_length=2)
    from_date: str = Field(..., min_length=1, max_length=20)
    to_date: str = Field(..., min_length=1, max_length=20)


class WorkingDaysYear(BaseModel):
    """How one year inside the requested range was resolved.

    The seeded calendars cover a single year, so a range reaching past it is
    still answered rather than refused - but the caller cannot otherwise tell
    which part of the answer came from a declared calendar and which from a
    fallback. One flag for the whole range would be the least useful true
    thing to say about a range that straddles the boundary, so this is
    reported per year.

    ``work_week_source`` is ``declared`` when the year has its own calendar,
    ``carried`` when the week was taken from ``work_week_from_year``, and
    ``default`` when the country has no calendar at all and the week is the
    hardcoded Monday-Friday.

    ``holidays_applied`` is a separate axis on purpose. A working week is a
    rule and is carried across years; a holiday is a date and is not, so a
    year whose week was carried still contributed no holidays. Today the flag
    is true exactly when ``work_week_source`` is ``declared``, because both
    depend on the year having its own calendar. They are reported separately
    because they are separate facts, and treating them as one is what let a
    missing holiday hide behind a correctly carried week.
    """

    year: int
    work_week_source: Literal["declared", "carried", "default"]
    work_week_from_year: int | None = None
    holidays_applied: bool


class WorkingDaysResponse(BaseModel):
    """Result of a working-days calculation."""

    country_code: str
    from_date: str
    to_date: str
    working_days: int
    calendar_days: int
    years: list[WorkingDaysYear] = Field(default_factory=list)
