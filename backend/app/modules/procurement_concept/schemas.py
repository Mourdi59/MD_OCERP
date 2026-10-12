# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request and response schemas of the procurement concept API.

Money travels as a decimal string ("1250000.00"); a JSON number for an amount
is refused (422), so no float ever touches a threshold comparison. Calendar
days are ``YYYY-MM-DD``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.procurement_concept.catalogue import parse_amount


def _money(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        out = parse_amount(v)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if out < 0:
        raise ValueError("amount must not be negative")
    return out


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int = 0
    limit: int = 0


# ── Concept ──────────────────────────────────────────────────────────────


class ConceptSet(_In):
    """Create or change the concept. Absent fields keep their value."""

    catalogue_source: Literal["shipped", "tenant"] | None = None
    catalogue_id: str | None = Field(default=None, max_length=64)
    catalogue_version: int | None = Field(default=None, ge=1)
    jurisdiction: Literal["eu", "uk", "us_federal", "de_national", "none"] | None = None
    client_type: Literal["central", "sub_central", "utility", "private"] | None = None
    # None on create = take module 3's owner capability (public_client), else False.
    public_client: bool | None = None
    vat_rate_pct: Decimal | None = Field(default=None, ge=0, le=100)
    release_gate_code: str | None = Field(default=None, max_length=64)
    governance_document_id: uuid.UUID | None = None
    default_profile_id: uuid.UUID | None = None

    @field_validator("vat_rate_pct", mode="before")
    @classmethod
    def _vat(cls, v: Any) -> Any:
        return _money(v)


class RationaleIn(_In):
    rationale: str = Field(default="", max_length=4000)


# ── Packages ─────────────────────────────────────────────────────────────


class PackagePut(_In):
    """Procurement attributes of one ContractPackage (created on first PUT)."""

    split_basis: Literal["trade", "section", "system", "whole"] | None = None
    is_advance: bool | None = None
    advance_reason: str | None = Field(default=None, max_length=4000)
    advance_release_kind: Literal["gate_decision", "condition"] | None = None
    advance_release_id: uuid.UUID | None = None
    estimated_value: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    cost_ref_kind: Literal["cost_line", "boq_section", "budget_line"] | None = None
    cost_ref_id: uuid.UUID | None = None
    lot_group: str | None = Field(default=None, max_length=64)
    small_lot_exemption: bool | None = None
    procedure_code: str | None = Field(default=None, max_length=64)
    tender_basis: Literal["detailed", "functional", "mixed"] | None = None
    framework_agreement_id: uuid.UUID | None = None
    evaluation_method: Literal["lowest_price", "best_value"] | None = None
    evaluation_weights: dict[str, str] | None = None
    need_activity_id: uuid.UUID | None = None
    need_date: date | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=1500)
    procedure_days: int | None = Field(default=None, ge=0, le=1500)
    planned_start: date | None = None
    prequal_profile_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=8000)

    @field_validator("estimated_value", mode="before")
    @classmethod
    def _value(cls, v: Any) -> Any:
        return _money(v)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PackageStateIn(_In):
    action: Literal["hold", "resume", "cancel"]
    reason: str = Field(default="", max_length=4000)


# ── Prequalification ─────────────────────────────────────────────────────


class ProfileCriterion(_In):
    code: str = Field(min_length=1, max_length=64)
    weight: Decimal = Decimal("0")

    @field_validator("weight", mode="before")
    @classmethod
    def _w(cls, v: Any) -> Any:
        return _money(v)


class ProfileIn(_In):
    package_id: uuid.UUID | None = None
    name: str = Field(default="", max_length=255)
    criteria: list[ProfileCriterion] = Field(default_factory=list, max_length=60)
    pass_mark: Decimal = Decimal("0")
    validity_months: int = Field(default=12, ge=1, le=120)

    @field_validator("pass_mark", mode="before")
    @classmethod
    def _pm(cls, v: Any) -> Any:
        return _money(v)


class CandidateIn(_In):
    subcontractor_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    free_name: str = Field(default="", max_length=255)
    source: Literal["market_sounding", "own_list", "framework", "public_notice"] = "own_list"
    list: Literal["long", "short", "excluded"] = "long"
    decision_rationale: str = Field(default="", max_length=4000)
    conflict_of_interest_declared: bool = False
    conflict_note: str = Field(default="", max_length=4000)


class CandidatePatch(_In):
    subcontractor_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    free_name: str | None = Field(default=None, max_length=255)
    source: Literal["market_sounding", "own_list", "framework", "public_notice"] | None = None
    list: Literal["long", "short", "excluded"] | None = None
    decision_rationale: str | None = Field(default=None, max_length=4000)
    conflict_of_interest_declared: bool | None = None
    conflict_note: str | None = Field(default=None, max_length=4000)


class EvidenceRef(_In):
    kind: Literal["certificate", "prequal_application", "rating", "reference", "document"]
    id: str = Field(min_length=1, max_length=64)


class ScoreIn(_In):
    criterion_code: str = Field(min_length=1, max_length=64)
    passed: bool | None = None
    score: Decimal | None = Field(default=None, ge=0, le=100)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=2000)

    @field_validator("score", mode="before")
    @classmethod
    def _s(cls, v: Any) -> Any:
        return _money(v)


class ScoresPut(_In):
    scores: list[ScoreIn] = Field(max_length=60)


class ReferenceIn(_In):
    project_name: str = Field(min_length=1, max_length=255)
    client: str = Field(default="", max_length=255)
    value: Decimal | None = None
    currency: str = Field(default="", max_length=3)
    year: int | None = Field(default=None, ge=1900, le=2100)
    role: str = Field(default="", max_length=120)
    contact: str = Field(default="", max_length=255)
    verified: bool = False

    @field_validator("value", mode="before")
    @classmethod
    def _v(cls, v: Any) -> Any:
        return _money(v)


# ── Market sounding ──────────────────────────────────────────────────────


class SoundingIn(_In):
    package_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    trade: str = Field(default="", max_length=120)
    held_on: date
    method: Literal["survey", "meeting", "rfi", "notice"] = "meeting"
    participant_candidate_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    findings: str = Field(default="", max_length=8000)
    capacity_signal: Literal["ample", "adequate", "tight", "insufficient"] = "adequate"
    price_signal: Literal["below_estimate", "in_line", "above_estimate", "unknown"] = "unknown"
    lead_time_signal_days: int | None = Field(default=None, ge=0, le=1500)
    mitigation: str = Field(default="", max_length=4000)
    resplit: bool = False


class SoundingPatch(_In):
    package_ids: list[uuid.UUID] | None = None
    trade: str | None = Field(default=None, max_length=120)
    held_on: date | None = None
    method: Literal["survey", "meeting", "rfi", "notice"] | None = None
    participant_candidate_ids: list[uuid.UUID] | None = None
    findings: str | None = Field(default=None, max_length=8000)
    capacity_signal: Literal["ample", "adequate", "tight", "insufficient"] | None = None
    price_signal: Literal["below_estimate", "in_line", "above_estimate", "unknown"] | None = None
    lead_time_signal_days: int | None = Field(default=None, ge=0, le=1500)
    mitigation: str | None = Field(default=None, max_length=4000)
    resplit: bool | None = None


# ── Schedule and execution ───────────────────────────────────────────────


class ScheduleConfirm(_In):
    package_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class ExecutionIn(_In):
    # Override of the vehicle chosen from the package kind (rule 15); never both.
    vehicle: Literal["bid_package", "rfq"] | None = None
    submission_deadline: date | None = None


# ── Frameworks ───────────────────────────────────────────────────────────


class FrameworkIn(_In):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=255)
    subcontractor_id: uuid.UUID | None = None
    vendor_id: uuid.UUID | None = None
    supplier_name: str = Field(default="", max_length=255)
    scope: str = Field(default="", max_length=8000)
    package_kinds: list[Literal["design", "works", "supply", "supply_and_install", "services"]] = Field(
        default_factory=list
    )
    lots: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    max_value: Decimal
    currency: str = Field(min_length=3, max_length=3)
    start_date: date
    end_date: date
    call_off_mode: Literal["direct", "mini_competition"] = "direct"
    source_procedure_ref: str = Field(default="", max_length=255)

    @field_validator("max_value", mode="before")
    @classmethod
    def _mv(cls, v: Any) -> Any:
        return _money(v)

    @field_validator("currency")
    @classmethod
    def _cur(cls, v: str) -> str:
        return v.upper()


class FrameworkPatch(_In):
    title: str | None = Field(default=None, max_length=255)
    supplier_name: str | None = Field(default=None, max_length=255)
    scope: str | None = Field(default=None, max_length=8000)
    package_kinds: list[Literal["design", "works", "supply", "supply_and_install", "services"]] | None = None
    lots: list[dict[str, Any]] | None = None
    max_value: Decimal | None = None
    end_date: date | None = None
    call_off_mode: Literal["direct", "mini_competition"] | None = None
    source_procedure_ref: str | None = Field(default=None, max_length=255)

    @field_validator("max_value", mode="before")
    @classmethod
    def _mv(cls, v: Any) -> Any:
        return _money(v)


class FrameworkStateIn(_In):
    target: Literal["active", "expired", "exhausted", "terminated"]
