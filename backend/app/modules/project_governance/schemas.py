# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request and response models of the project governance API.

Codes (catalogue ids, phase, gate, area and document type codes) are plain
strings: they are data from a catalogue, not enums. Outcomes and statuses are
closed vocabularies and are ``Literal``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")

Outcome = Literal["go", "go_with_conditions", "hold", "recycle", "stop"]
Severity = Literal["critical", "essential", "recommended"]
CatalogueSource = Literal["shipped", "tenant"]


class Page(BaseModel, Generic[T]):
    """The list envelope every collection endpoint answers with."""

    items: list[T]
    total: int
    offset: int = 0
    limit: int = 0


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── catalogues ──


class CatalogueCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: str = Field(default="phase_model", min_length=1, max_length=40)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=255)
    based_on_source: CatalogueSource | None = None
    based_on_id: str | None = Field(default=None, max_length=64)
    based_on_version: int | None = Field(default=None, ge=1)


class CatalogueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    body: dict[str, Any] | None = None


class CatalogueVersionOut(_Out):
    version: int
    content_hash: str
    published_by: UUID | None
    published_at: datetime


class TenantCatalogueOut(_Out):
    id: UUID
    kind: str
    code: str
    name: str
    based_on: str
    state: str
    draft_body: dict[str, Any]
    versions: list[CatalogueVersionOut] = []
    validation_errors: list[str] = []


# ── model ──


class ModelSet(BaseModel):
    catalogue_source: CatalogueSource = "shipped"
    catalogue_id: str = Field(min_length=1, max_length=64)
    catalogue_version: int | None = Field(default=None, ge=1)
    four_eyes: bool = True


class ModelChange(BaseModel):
    catalogue_source: CatalogueSource = "shipped"
    catalogue_id: str = Field(min_length=1, max_length=64)
    catalogue_version: int | None = Field(default=None, ge=1)
    mapping: dict[str, str]


class ModelSettings(BaseModel):
    four_eyes: bool | None = None
    decision_route_id: UUID | None = None
    change_route_id: UUID | None = None


class ModelOut(_Out):
    id: UUID
    project_id: UUID
    catalogue_source: str
    catalogue_id: str
    catalogue_version: int
    current_phase: str | None
    four_eyes: bool
    decision_route_id: UUID | None
    change_route_id: UUID | None
    stopped: bool
    stopped_at: datetime | None
    phases: list[dict[str, Any]] = []


# ── areas ──


class AreaUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    owner_user_id: UUID | None = None
    deputy_user_id: UUID | None = None
    applicable: bool | None = None
    na_rationale: str | None = Field(default=None, max_length=4000)
    name_override: str | None = Field(default=None, max_length=255)


class AreaOut(_Out):
    id: UUID
    code: str
    name_override: str
    sort_order: int
    owner_user_id: UUID | None
    deputy_user_id: UUID | None
    applicable: bool
    na_rationale: str
    retired: bool


# ── gates ──


class GateOut(_Out):
    id: UUID
    code: str
    catalogue_id: str
    from_phase: str
    to_phase: str
    sort_order: int
    status: str
    attempt_no: int
    target_date: str
    schedule_activity_id: UUID | None
    approval_instance_id: UUID | None
    hold_resume_date: str
    last_outcome: str
    historic: bool
    version: int


class ConditionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    area_code: str | None = Field(default=None, max_length=64)
    document_type: str | None = Field(default=None, max_length=64)
    text: str = Field(max_length=4000)
    owner_user_id: UUID | None = None
    due_date: date | None = None
    severity: Severity = "essential"


class DecisionIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    outcome: Outcome
    rationale: str = Field(default="", max_length=8000)
    conditions: list[ConditionIn] = []
    proceed_at_risk_areas: list[str] = []
    accepted_not_applicable: list[str] = []
    hold_resume_date: date | None = None


class ReopenIn(BaseModel):
    rationale: str = Field(max_length=8000)
    rewind_phase: bool = False


class DecisionOut(_Out):
    id: UUID
    gate_id: UUID
    gate_code: str
    attempt_no: int
    outcome: str
    rationale: str
    decided_by: UUID
    decided_at: datetime
    snapshot: dict[str, Any]
    proceed_at_risk_areas: list[str]
    accepted_not_applicable: list[str]
    hold_resume_date: str
    approval_instance_id: UUID | None


class GateDetailOut(BaseModel):
    gate: GateOut
    blockers: list[dict[str, Any]]
    areas: list[dict[str, Any]]
    decisions: list[DecisionOut]


# ── checks ──


class CheckConfirm(BaseModel):
    status: Literal["ready", "ready_with_risks", "not_ready", "not_assessed"]
    rag: Literal["", "red", "amber", "green"] = ""
    note: str = Field(default="", max_length=4000)


class NotApplicableIn(BaseModel):
    rationale: str = Field(max_length=4000)


class CheckOut(_Out):
    id: UUID
    gate_id: UUID
    attempt_no: int
    area_id: UUID
    status: str
    rag: str
    note: str
    confirmed_by: UUID | None
    confirmed_at: datetime | None
    confirmed_revisions: dict[str, str]
    stale: bool
    na_rationale: str


# ── documents ──


class DocumentCreate(BaseModel):
    area_id: UUID
    doc_type: str = Field(min_length=1, max_length=64)


class AttachIn(BaseModel):
    container_id: UUID


class DocumentOut(_Out):
    id: UUID
    area_id: UUID
    doc_type: str
    required_at_gates: list[str]
    status: str
    container_id: UUID | None
    bound_revision_id: UUID | None
    bound_content_hash: str | None
    approved_gate_id: UUID | None
    read_only: bool


class ChangeRequestIn(BaseModel):
    reason: str = Field(max_length=8000)
    impact: str = Field(default="", max_length=8000)
    proposed_revision_id: UUID | None = None


class ChangeRequestOut(_Out):
    id: UUID
    document_id: UUID
    previous_revision_id: UUID | None
    proposed_revision_id: UUID
    proposed_content_hash: str | None
    reason: str
    impact: str
    status: str
    approval_instance_id: UUID | None
    requested_by: UUID | None
    decided_by: UUID | None
    decided_at: datetime | None
    created_at: datetime


class DocumentHistoryOut(BaseModel):
    document_id: UUID
    revisions: list[dict[str, Any]]
    change_requests: list[ChangeRequestOut]


# ── conditions ──


class ConditionOut(_Out):
    id: UUID
    decision_id: UUID
    gate_id: UUID
    gate_code: str
    area_code: str | None
    document_type: str | None
    text: str
    owner_user_id: UUID | None
    due_date: str
    severity: str
    status: str
    evidence: str
    cleared_by: UUID | None
    cleared_at: datetime | None
    waiver_rationale: str
    waived_by: UUID | None
    waived_at: datetime | None
    escalated_at: datetime | None


class ClearIn(BaseModel):
    evidence: str = Field(default="", max_length=8000)


class WaiveIn(BaseModel):
    rationale: str = Field(max_length=8000)


class FindingOut(BaseModel):
    rule_id: str
    passed: bool
    severity: str
    message: str
    element_ref: str | None = None
    suggestion: str | None = None
