# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``permit_type``: which authority permits exist, their clocks and validity.

Data, not code (SPEC section 2, lead decision g). Shipped JSON lives in
``catalogues/permit_type/``; tenant drafts and published versions live in the
shared governance catalogue tables and go through module 1's resolver. A
catalogue may ``extend`` another one (a German Land overlay extends ``de``):
the overlay's permit types replace the parent's by code, the rest is inherited.

Every statutory figure (a clock period, a validity period, a deemed-outcome
regime) carries ``source_url`` and ``review_status``. The review vocabulary is
module 1's ``verified | unconfirmed``: a figure read on the cited primary source
is ``verified``, anything else ships ``unconfirmed`` and the screens say so.
No national period appears in code; a type without a period has an unknown
clock and the forecast says ``no_statutory_period`` instead of guessing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus

PERMIT_TYPE_KIND = "permit_type"
CATALOGUE_DIR = Path(__file__).with_name("catalogues") / PERMIT_TYPE_KIND
I18N_PREFIX = "permits."
DEFAULT_CATALOGUE_ID = "neutral"

CATEGORIES: tuple[str, ...] = (
    "planning_zoning",
    "building",
    "environmental",
    "water",
    "immission",
    "heritage",
    "traffic_road",
    "utility",
    "occupancy",
    "discharge",
    "early_start",
    "other",
)
# review_authority AUTHORITY_KINDS plus the three kinds permits need.
AUTHORITY_KINDS: tuple[str, ...] = (
    "state_expertise",
    "building_control",
    "ahj",
    "technical_review",
    "other",
    "planning_authority",
    "environmental_agency",
    "utility_operator",
)
APPLICANT_ROLES: tuple[str, ...] = ("owner", "designer", "contractor", "operator")
SCOPES: tuple[str, ...] = ("full", "partial", "preliminary", "early_start")
ENABLES: tuple[str, ...] = ("site_start", "construction", "occupation", "operation")
UNITS: tuple[str, ...] = ("calendar_days", "working_days", "weeks", "months", "years")
CONDITION_KINDS: tuple[str, ...] = (
    "suspensive",
    "obligation",
    "time_limit",
    "revocation_reserve",
    "reserved_obligation",
    "information",
)
CONDITION_TRIGGERS: tuple[str, ...] = (
    "before_application_x",
    "before_start",
    "before_stage",
    "before_occupation",
    "ongoing",
    "by_date",
    "on_event",
    "after_completion",
)

Unit = Literal["calendar_days", "working_days", "weeks", "months", "years"]
_CODE = r"^[a-z0-9][a-z0-9_]*$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(_Frozen):
    """Where a figure comes from and whether it was read there."""

    source_url: str | None = None
    review_status: ReviewStatus | None = None
    as_of: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class Period(_Frozen):
    period: int = Field(ge=1, le=3650)
    unit: Unit


class Extension(_Frozen):
    """How the decision period may be extended.

    ``by_authority_once``: the authority may extend once, by at most ``max``
    ``unit``, with reasons when ``reason_required`` (BImSchG §10 Abs. 6a).
    ``by_agreement``: extended as often as applicant and authority agree in writing.
    """

    mode: Literal["none", "by_authority_once", "by_agreement"] = "none"
    max: int | None = Field(default=None, ge=1, le=3650)
    unit: Unit | None = None
    reason_required: bool = False


class ClockVariant(Sourced):
    code: str = Field(pattern=_CODE, max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    period: int = Field(ge=1, le=3650)
    unit: Unit


class Clock(Sourced):
    """The statutory decision period of a permit type. ``period: null`` = unknown clock (rule 5)."""

    period: int | None = Field(default=None, ge=1, le=3650)
    unit: Unit | None = None
    start_event: Literal["receipt", "day_after_receipt", "complete"] = "receipt"
    stop_on_rfi: bool = False
    extension: Extension = Extension()
    deemed_outcome: Literal["none", "granted", "discharged"] = "none"
    deemed_requires_notice: bool = False
    deemed_source_url: str | None = None
    deemed_review_status: ReviewStatus | None = None
    variants: tuple[ClockVariant, ...] = ()


class Validity(Sourced):
    lapse_if_not_started: Period | None = None
    lapse_if_paused: Period | None = None
    extension_per_request: Period | None = None


class Requires(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    on: Literal["granted", "submitted"] = "granted"


class PermitType(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    category: Literal[
        "planning_zoning",
        "building",
        "environmental",
        "water",
        "immission",
        "heritage",
        "traffic_road",
        "utility",
        "occupancy",
        "discharge",
        "early_start",
        "other",
    ]
    authority_kind: Literal[
        "state_expertise",
        "building_control",
        "ahj",
        "technical_review",
        "other",
        "planning_authority",
        "environmental_agency",
        "utility_operator",
    ] = "other"
    default_applicant_role: Literal["owner", "designer", "contractor", "operator"] = "owner"
    # delivery_model risk category whose allocation names the applicant (rule 2).
    allocation_category: str = "permits_approval"
    typical_documents: tuple[str, ...] = ()
    scope: Literal["full", "partial", "preliminary", "early_start"] = "full"
    requires: tuple[Requires, ...] = ()
    enables: tuple[Literal["site_start", "construction", "occupation", "operation"], ...] = ()
    triggered_by_route: tuple[str, ...] = ()
    revocable: bool = False
    security_possible: bool = False
    clock: Clock = Clock()
    validity: Validity | None = None
    legal_basis: str = ""
    legal_basis_url: str | None = None
    legal_basis_review_status: ReviewStatus | None = None


class ConditionKindLabel(Sourced):
    """A national condition label mapped onto a neutral kind (and, optionally, a default trigger)."""

    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    maps_to: Literal[
        "suspensive", "obligation", "time_limit", "revocation_reserve", "reserved_obligation", "information"
    ]
    default_trigger: str | None = None


class PermitTypeCatalogue(_Frozen):
    """One ``permit_type`` catalogue body."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    jurisdiction_countries: tuple[str, ...] = ()
    # ISO 3166-1 or 3166-2 code this catalogue speaks for ("DE", "DE-NW", "GB-ENG").
    jurisdiction: str | None = None
    extends: str | None = Field(default=None, pattern=_CODE, max_length=64)
    source_url: str | None = None
    permit_types: tuple[PermitType, ...] = ()
    condition_kinds: tuple[ConditionKindLabel, ...] = ()

    def type_map(self) -> dict[str, PermitType]:
        return {t.code: t for t in self.permit_types}


def _sourced_errors(where: str, item: Sourced) -> list[str]:
    errors = []
    if not item.source_url:
        errors.append(f"statutory_figure_without_source: {where}")
    if item.review_status is None:
        errors.append(f"statutory_figure_without_review_status: {where}")
    return errors


def _label_errors(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped":
        return [] if name_key.startswith(I18N_PREFIX) else [f"shipped_label_not_i18n_key: {where}"]
    return [] if (name_key or labels) else [f"label_missing: {where}"]


def validate_permit_type_catalogue(obj: PermitTypeCatalogue, source: str) -> list[str]:
    """Cross-reference rules of one catalogue; an empty list means valid.

    References to types of the parent catalogue (``extends``) cannot be checked
    here, the body alone does not see the parent; :func:`merged` checks them.
    """
    from app.modules.project_route.schemas import ROUTE_OPTIONS

    errors: list[str] = []
    errors += _label_errors("catalogue", obj.name_key, obj.labels, source)
    codes = [t.code for t in obj.permit_types]
    if len(set(codes)) != len(codes):
        errors.append("duplicate_permit_type")
    if obj.extends == obj.id:
        errors.append("catalogue_extends_itself")
    for t in obj.permit_types:
        where = f"type:{t.code}"
        errors += _label_errors(where, t.name_key, t.labels, source)
        for route in t.triggered_by_route:
            if route not in ROUTE_OPTIONS:
                errors.append(f"unknown_route: {where}:{route}")
        if t.requires and any(r.code == t.code for r in t.requires):
            errors.append(f"type_requires_itself: {where}")
        if not obj.extends:
            for r in t.requires:
                if r.code not in codes:
                    errors.append(f"requires_unknown_type: {where}:{r.code}")
        c = t.clock
        if (c.period is None) != (c.unit is None):
            errors.append(f"clock_period_without_unit: {where}")
        if c.period is not None:
            errors += _sourced_errors(f"{where}:clock", c)
        if c.extension.mode == "by_authority_once" and (c.extension.max is None or c.extension.unit is None):
            errors.append(f"extension_without_max: {where}")
        if c.deemed_outcome != "none":
            if c.period is None:
                errors.append(f"deemed_without_period: {where}")
            if not c.deemed_source_url or c.deemed_review_status is None:
                errors.append(f"statutory_figure_without_source: {where}:deemed")
        for v in c.variants:
            errors += _sourced_errors(f"{where}:variant:{v.code}", v)
            errors += _label_errors(f"{where}:variant:{v.code}", v.name_key, v.labels, source)
        if t.validity is not None and any(
            p is not None
            for p in (t.validity.lapse_if_not_started, t.validity.lapse_if_paused, t.validity.extension_per_request)
        ):
            errors += _sourced_errors(f"{where}:validity", t.validity)
        if t.category == "early_start" and t.scope != "early_start":
            errors.append(f"early_start_scope_mismatch: {where}")
        if t.legal_basis_url and t.legal_basis_review_status is None:
            errors.append(f"statutory_figure_without_review_status: {where}:legal_basis")
    for k in obj.condition_kinds:
        errors += _label_errors(f"condition_kind:{k.code}", k.name_key, k.labels, source)
        if k.default_trigger is not None and k.default_trigger not in CONDITION_TRIGGERS:
            errors.append(f"unknown_trigger: condition_kind:{k.code}")
        if k.source_url and k.review_status is None:
            errors.append(f"statutory_figure_without_review_status: condition_kind:{k.code}")
    return errors


def merged(obj: PermitTypeCatalogue, lookup: Callable[[str], PermitTypeCatalogue]) -> PermitTypeCatalogue:
    """The catalogue with its ``extends`` chain resolved: own types replace the parent's by code.

    Raises ``ValueError`` on a cycle or on a ``requires`` that names no type of the merged result.
    """
    chain = [obj]
    seen = {obj.id}
    while chain[-1].extends:
        parent = lookup(chain[-1].extends)
        if parent.id in seen:
            raise ValueError(f"catalogue_extends_cycle: {obj.id}")
        seen.add(parent.id)
        chain.append(parent)
    types: dict[str, PermitType] = {}
    kinds: dict[str, ConditionKindLabel] = {}
    for c in reversed(chain):
        for t in c.permit_types:
            types[t.code] = t
        for k in c.condition_kinds:
            kinds[k.code] = k
    for t in types.values():
        for r in t.requires:
            if r.code not in types:
                raise ValueError(f"requires_unknown_type: {t.code}:{r.code}")
    return obj.model_copy(update={"permit_types": tuple(types.values()), "condition_kinds": tuple(kinds.values())})


def register_kind() -> None:
    """Register ``permit_type`` with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=PERMIT_TYPE_KIND,
            model=PermitTypeCatalogue,
            validator=validate_permit_type_catalogue,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=("permit_types", "condition_kinds"),
        )
    )


def shipped_catalogues() -> dict[str, PermitTypeCatalogue]:
    """Every shipped catalogue by id (validated by the registered kind)."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    return {c.id: c for c in get_catalogue_kind(PERMIT_TYPE_KIND).shipped()}


def default_catalogue_id(country_code: str | None, subdivision: str | None = None) -> str:
    """The shipped catalogue for a project's jurisdiction: Land overlay, then country, then ``neutral``.

    A regional pack may declare ``permit_type: {CC: id}``; when the national packs
    agree that wins, in the same order as the governance catalogue.
    """
    from app.core import regional_packs

    country = (country_code or "").strip().upper()
    sub = (subdivision or "").strip().upper()
    shipped = shipped_catalogues()
    if sub and sub.startswith(f"{country}-"):
        claims = [c.id for c in shipped.values() if c.jurisdiction == sub]
        if len(claims) == 1:
            return claims[0]
    if not country:
        return DEFAULT_CATALOGUE_ID
    declared: set[str] = set()
    try:
        for config in regional_packs.packs_for_country(country):
            if config.get("parent_pack"):
                continue
            block = config.get(PERMIT_TYPE_KIND)
            if isinstance(block, dict) and isinstance(block.get(country), str):
                declared.add(block[country].strip())
    except Exception:
        declared = set()
    if len(declared) == 1 and (value := declared.pop()) in shipped:
        return value
    claims = [c.id for c in shipped.values() if c.jurisdiction == country]
    return claims[0] if len(claims) == 1 else DEFAULT_CATALOGUE_ID
