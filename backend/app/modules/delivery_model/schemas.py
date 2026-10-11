# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Request and response schemas of the delivery model API.

Weights, shares and scores travel as strings or ints, never floats. Vocabulary
fields are closed literals where the platform owns the vocabulary; catalogue
codes (forms, categories, parties, criteria) are open strings checked against
the pinned catalogue by the service, because a tenant catalogue may add codes.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PackageKind = Literal[
    "design",
    "construction",
    "design_and_construction",
    "supply",
    "supply_and_install",
    "management_services",
    "operation",
    "project_agreement",
]
PriceBasis = Literal["remeasure", "lump_sum", "gmp", "target_cost", "cost_reimbursable", "availability_payment"]
PackageLinkKind = Literal["bid_package", "tender_package", "rfq", "subcontract_agreement", "contract"]
OfiLinkKind = Literal["rfq", "purchase_order", "requisition"]
OfiRoute = Literal["rfq", "purchase_order", "requisition", "framework", "existing_stock", "none_yet"]
OfiKind = Literal["equipment", "material", "design", "service", "utility"]
Basis = Literal["contract", "insurance", "shared_pain_gain", "statute", "ground_baseline"]
Disposition = Literal["keep", "re_scope", "cancel"]
_CODE = r"^[a-z0-9][a-z0-9_]*$"
_PKG_CODE = r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$"


class _In(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


def _no_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("send decimals as strings")
    return value


class Page[T](BaseModel):
    items: list[T]
    total: int
    offset: int = 0
    limit: int = 0


class OwnerCapability(_In):
    owner_has_design_team: bool | None = None
    owner_has_cm_capacity: bool | None = None
    public_client: bool | None = None
    funding_source: str = Field(default="", max_length=120)


class ModelSet(_In):
    catalogue_source: Literal["shipped", "tenant"] = "shipped"
    catalogue_id: str | None = Field(default=None, max_length=64)
    catalogue_version: int | None = None


class ModelPatch(_In):
    underground_risk_sharing: bool | None = None
    owner_capability: OwnerCapability | None = None


class CatalogueChange(_In):
    catalogue_source: Literal["shipped", "tenant"]
    catalogue_id: str = Field(max_length=64)
    catalogue_version: int | None = None
    form_mapping: dict[str, str] = Field(default_factory=dict)
    category_mapping: dict[str, str] = Field(default_factory=dict)


class OptionIn(_In):
    form_code: str = Field(pattern=_CODE, max_length=64)
    overrides: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=5000)


class OptionPatch(_In):
    overrides: dict[str, Any] | None = None
    notes: str | None = Field(default=None, max_length=5000)
    sort_order: int | None = None


class WeightsPatch(_In):
    weights: dict[str, str]

    @field_validator("weights", mode="before")
    @classmethod
    def _decimal_strings(cls, v: Any) -> Any:
        return {k: _no_float(x) for k, x in (v or {}).items()}


class ScoreIn(_In):
    option_id: uuid.UUID
    criterion_code: str = Field(max_length=64)
    score: int = Field(ge=1, le=5)
    rationale: str = Field(default="", max_length=2000)


class ScoresPut(_In):
    scores: list[ScoreIn]


class ProposeIn(_In):
    option_id: uuid.UUID
    rationale: str = Field(min_length=1, max_length=10000)
    owner_capability: OwnerCapability | None = None
    dispositions: dict[str, Disposition] = Field(default_factory=dict)


class AllocationPut(_In):
    party: str | None = Field(default=None, max_length=40)
    basis: Basis = "contract"
    shares: dict[str, str] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=5000)
    not_applicable: bool = False

    @field_validator("shares", mode="before")
    @classmethod
    def _decimal_strings(cls, v: Any) -> Any:
        return {k: _no_float(x) for k, x in (v or {}).items()}


class ConfirmIn(_In):
    categories: list[str] | None = None


class SeedRisksIn(_In):
    categories: list[str] | None = None
    preview: bool = True


class PackageIn(_In):
    code: str = Field(pattern=_PKG_CODE, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    kind: PackageKind
    designs: bool = False
    builds: bool = False
    supplies: bool = False
    manages: bool = False
    party: str = Field(default="contractor", max_length=40)
    contracting_party: Literal["owner", "manager"] = "owner"
    price_basis: PriceBasis | None = None
    standard_form: str = Field(default="", max_length=120)
    parent_id: uuid.UUID | None = None
    scope: str = Field(default="", max_length=10000)
    wbs_ref: str = Field(default="", max_length=120)
    boq_ref: str = Field(default="", max_length=120)
    need_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class PackagePatch(_In):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    kind: PackageKind | None = None
    designs: bool | None = None
    builds: bool | None = None
    supplies: bool | None = None
    manages: bool | None = None
    party: str | None = Field(default=None, max_length=40)
    contracting_party: Literal["owner", "manager"] | None = None
    price_basis: PriceBasis | None = None
    standard_form: str | None = Field(default=None, max_length=120)
    parent_id: uuid.UUID | None = None
    scope: str | None = Field(default=None, max_length=10000)
    wbs_ref: str | None = Field(default=None, max_length=120)
    boq_ref: str | None = Field(default=None, max_length=120)
    need_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    sort_order: int | None = None


class PackageLinkIn(_In):
    link_kind: PackageLinkKind
    link_id: uuid.UUID


class PackageStatusIn(_In):
    status: Literal["planned", "closed", "cancelled"]


class OfiIn(_In):
    code: str = Field(pattern=_PKG_CODE, max_length=64)
    description: str = Field(min_length=1, max_length=5000)
    item_kind: OfiKind = "equipment"
    install_by: Literal["owner", "package"] = "package"
    package_id: uuid.UUID | None = None
    need_by_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    expected_delivery_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    enquiry_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    schedule_activity_id: uuid.UUID | None = None


class OfiPatch(_In):
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    item_kind: OfiKind | None = None
    install_by: Literal["owner", "package"] | None = None
    package_id: uuid.UUID | None = None
    need_by_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    expected_delivery_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    enquiry_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    schedule_activity_id: uuid.UUID | None = None


class OfiRouteIn(_In):
    procurement_route: OfiRoute
    link_kind: OfiLinkKind | None = None
    link_id: uuid.UUID | None = None


class OfiStatusIn(_In):
    status: Literal["identified", "route_set", "ordered", "delivered", "handed_to_installer"]


class FindingOut(BaseModel):
    rule_id: str
    passed: bool
    severity: str
    message: str
    element_ref: str | None = None
    suggestion: str | None = None
