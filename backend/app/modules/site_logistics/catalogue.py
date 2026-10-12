# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``site_logistics``: area kinds, load classes, media, permits, incoterms, noise limits.

Data, not code (SPEC section 2). Shipped JSON lives in ``catalogues/site_logistics/``;
tenant drafts and published versions live in module 1's shared catalogue tables
and resolve through its one resolver. A national catalogue ``extends`` the
neutral one: its entries replace the parent's by ``code`` group by group, the
rest is inherited, thresholds merge key by key.

Every statutory figure (a weight or dimension limit, a noise limit, a permit
lead time) carries ``source_url`` and ``review_status``; the review vocabulary is
module 1's ``verified | unconfirmed``. A shipped catalogue with a jurisdiction
ships every figure ``unconfirmed`` until a reviewer read it on the source.

Incoterms are data with a version tag (Decision 6): ICC revises the rules, and a
case keeps the version it was opened under. A later revision ships as a new
catalogue version, never as an edit.

Labels: shipped entries are translated by the frontend under
``site_logistics.catalogue.<group>.<code>``; tenant entries may carry
``labels: {locale: text}`` instead.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus

SITE_LOGISTICS_KIND = "site_logistics"
CATALOGUE_DIR = Path(__file__).with_name("catalogues") / SITE_LOGISTICS_KIND
DEFAULT_CATALOGUE_ID = "neutral"

BALANCE_GROUPS: tuple[str, ...] = ("built", "logistics", "reserve", "external")
MEDIA_PHASES: tuple[str, ...] = ("construction", "operation", "both")
DIRECTIONS: tuple[str, ...] = ("inbound", "outbound")
ZONE_TYPES: tuple[str, ...] = ("residential", "mixed", "industrial")
TRANSPORT_MODES: tuple[str, ...] = ("road", "rail", "sea", "inland_waterway", "air", "multimodal")

_CODE = r"^[a-z0-9][a-z0-9_]*$"
_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(_Frozen):
    """Where a figure comes from and whether a reviewer read it there."""

    source_url: str | None = None
    review_status: ReviewStatus | None = None
    jurisdiction: str = ""
    as_of: date | None = None


class Entry(_Frozen):
    code: str = Field(pattern=_CODE, max_length=40)
    labels: dict[str, str] | None = None


class AreaKind(Entry):
    counts_in_balance: bool = True
    balance_group: Literal["built", "logistics", "reserve", "external"]


class AccessKind(Entry):
    pass


class LoadClass(Entry, Sourced):
    """A set of default limits for a vehicle or a gate (EU 96/53/EC maxima, a national road class...)."""

    axle_load_t: Decimal | None = Field(default=None, ge=0)
    gross_weight_t: Decimal | None = Field(default=None, ge=0)
    max_height_m: Decimal | None = Field(default=None, ge=0)
    max_width_m: Decimal | None = Field(default=None, ge=0)
    max_length_m: Decimal | None = Field(default=None, ge=0)
    turning_radius_m: Decimal | None = Field(default=None, ge=0)


class MediaKind(Entry):
    capacity_unit: str = Field(min_length=1, max_length=20)
    phase: Literal["construction", "operation", "both"] = "both"


class TransportKind(Entry):
    direction: Literal["inbound", "outbound", "both"] = "both"
    always_heavy: bool = False


class PermitKind(Entry, Sourced):
    national_name: str = ""
    authority: str = ""
    legal_basis: str = ""
    typical_lead_days: int | None = Field(default=None, ge=0, le=365)


class Incoterm(_Frozen):
    code: str = Field(pattern=r"^[A-Z]{3}$")
    risk_transfer_point: str = Field(min_length=1)
    export_clearance_by: Literal["buyer", "seller"]
    import_clearance_by: Literal["buyer", "seller"]
    sea_only: bool = False


class CustomsDocumentKind(Entry):
    pass


class NoiseLimit(Entry, Sourced):
    zone_type: Literal["residential", "mixed", "industrial"]
    day_dba: Decimal | None = Field(default=None, ge=0, le=200)
    night_dba: Decimal | None = Field(default=None, ge=0, le=200)
    day_hours: tuple[str, str] | None = None
    quiet_hours: tuple[str, str] | None = None
    # A jurisdiction without fixed values (a method instead): the project enters its own.
    project_value_required: bool = False


class NeighbourIssueKind(Entry):
    pass


class Thresholds(_Frozen):
    area_balance_tolerance_pct: Decimal = Field(default=Decimal("2"), ge=0, le=100)
    media_reserve_pct: Decimal = Field(default=Decimal("10"), ge=0, le=500)
    permit_warn_days: int = Field(default=14, ge=0, le=365)
    customs_hs_digits_min: int = Field(default=6, ge=2, le=10)
    neighbour_response_days: int = Field(default=5, ge=0, le=90)


class ThresholdOverrides(_Frozen):
    area_balance_tolerance_pct: Decimal | None = Field(default=None, ge=0, le=100)
    media_reserve_pct: Decimal | None = Field(default=None, ge=0, le=500)
    permit_warn_days: int | None = Field(default=None, ge=0, le=365)
    customs_hs_digits_min: int | None = Field(default=None, ge=2, le=10)
    neighbour_response_days: int | None = Field(default=None, ge=0, le=90)


class SiteLogisticsCatalogue(_Frozen):
    """One catalogue body of kind ``site_logistics``."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(default=1, ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    jurisdiction: str = ""
    extends: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    incoterm_version: str = "2020"
    # The clearance split per incoterm is read from the ICC rule texts (A2/B2); the
    # document template derived from it is unconfirmed until a reviewer signs it off.
    incoterms_source_url: str | None = None
    incoterms_review_status: ReviewStatus | None = None
    hs_source_url: str | None = None
    area_kinds: tuple[AreaKind, ...] = ()
    access_kinds: tuple[AccessKind, ...] = ()
    load_classes: tuple[LoadClass, ...] = ()
    media_kinds: tuple[MediaKind, ...] = ()
    transport_kinds: tuple[TransportKind, ...] = ()
    permit_kinds: tuple[PermitKind, ...] = ()
    incoterms: tuple[Incoterm, ...] = ()
    customs_document_kinds: tuple[CustomsDocumentKind, ...] = ()
    noise_limits: tuple[NoiseLimit, ...] = ()
    neighbour_issue_kinds: tuple[NeighbourIssueKind, ...] = ()
    thresholds: ThresholdOverrides = ThresholdOverrides()

    def resolved_thresholds(self) -> Thresholds:
        """Thresholds with the defaults filled in."""
        return Thresholds(**{k: v for k, v in self.thresholds.model_dump().items() if v is not None})

    def codes(self, group: str) -> set[str]:
        return {e.code for e in getattr(self, group)}

    def entry(self, group: str, code: str) -> Any:
        return next((e for e in getattr(self, group) if e.code == code), None)


GROUPS: tuple[str, ...] = (
    "area_kinds",
    "access_kinds",
    "load_classes",
    "media_kinds",
    "transport_kinds",
    "permit_kinds",
    "incoterms",
    "customs_document_kinds",
    "noise_limits",
    "neighbour_issue_kinds",
)
_SOURCED_GROUPS = ("load_classes", "permit_kinds", "noise_limits")
_REQUIRED_AREA_KINDS = ("site_total", "storage", "laydown", "site_setup")
INCOTERM_CODES_2020 = ("EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF")


def has_figure(entry: Any) -> bool:
    """True when a sourced entry carries a statutory figure, which then needs a source and a review status."""
    if isinstance(entry, LoadClass):
        return any(
            getattr(entry, f) is not None
            for f in (
                "axle_load_t",
                "gross_weight_t",
                "max_height_m",
                "max_width_m",
                "max_length_m",
                "turning_radius_m",
            )
        )
    if isinstance(entry, PermitKind):
        return entry.typical_lead_days is not None
    if isinstance(entry, NoiseLimit):
        return entry.day_dba is not None or entry.night_dba is not None or entry.quiet_hours is not None
    return False


def validate_site_logistics_catalogue(obj: SiteLogisticsCatalogue, source: str) -> list[str]:
    """Cross-field rules of one body. ``source`` is ``shipped``, ``tenant`` or ``pack``."""
    import re

    errors: list[str] = []
    if obj.extends == obj.id:
        errors.append("catalogue_extends_itself")
    for group in GROUPS:
        codes = [e.code for e in getattr(obj, group)]
        if len(set(codes)) != len(codes):
            errors.append(f"duplicate_code: {group}")
    for group in _SOURCED_GROUPS:
        for e in getattr(obj, group):
            if not has_figure(e):
                continue
            if not e.source_url or e.review_status is None:
                errors.append(f"statutory_figure_without_source: {group}:{e.code}")
            # A reviewer has to read a national figure on its source before it is "verified".
            national = bool(e.jurisdiction or obj.jurisdiction)
            if source == "shipped" and national and e.review_status == ReviewStatus.verified and not e.as_of:
                errors.append(f"verified_without_as_of: {group}:{e.code}")
    for n in obj.noise_limits:
        for pair in (n.day_hours, n.quiet_hours):
            if pair is not None and not all(re.match(_HHMM, v) for v in pair):
                errors.append(f"bad_hours: noise_limits:{n.code}")
    if obj.extends is None:
        missing = [k for k in _REQUIRED_AREA_KINDS if k not in obj.codes("area_kinds")]
        if missing:
            errors.append(f"missing_area_kinds: {','.join(missing)}")
        if obj.incoterm_version == "2020" and obj.incoterms and obj.codes("incoterms") != set(INCOTERM_CODES_2020):
            errors.append("incoterms_2020_incomplete")
    if obj.incoterms and (not obj.incoterms_source_url or obj.incoterms_review_status is None):
        errors.append("statutory_figure_without_source: incoterms")
    return errors


def merged(obj: SiteLogisticsCatalogue, lookup: Callable[[str], SiteLogisticsCatalogue]) -> SiteLogisticsCatalogue:
    """The catalogue with its ``extends`` chain resolved; own entries replace the parent's by code.

    Raises:
        ValueError: on an ``extends`` cycle.
    """
    chain = [obj]
    seen = {obj.id}
    while chain[-1].extends:
        parent = lookup(chain[-1].extends)
        if parent.id in seen:
            raise ValueError(f"catalogue_extends_cycle: {obj.id}")
        seen.add(parent.id)
        chain.append(parent)
    update: dict[str, Any] = {}
    for group in GROUPS:
        by_code: dict[str, Any] = {}
        for c in reversed(chain):
            for e in getattr(c, group):
                by_code[e.code] = e
        update[group] = tuple(by_code.values())
    thresholds: dict[str, Any] = {}
    for c in reversed(chain):
        thresholds.update({k: v for k, v in c.thresholds.model_dump().items() if v is not None})
    update["thresholds"] = ThresholdOverrides(**thresholds)
    return obj.model_copy(update=update)


def register_kind() -> None:
    """Register ``site_logistics`` with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=SITE_LOGISTICS_KIND,
            model=SiteLogisticsCatalogue,
            validator=validate_site_logistics_catalogue,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=GROUPS,
        )
    )


def shipped_catalogues() -> dict[str, SiteLogisticsCatalogue]:
    """Every shipped catalogue by id, validated by the registered kind."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    return {c.id: c for c in get_catalogue_kind(SITE_LOGISTICS_KIND).shipped()}


def resolved_shipped(catalogue_id: str) -> SiteLogisticsCatalogue:
    """A shipped catalogue with its parent chain merged in."""
    shipped = shipped_catalogues()
    return merged(shipped[catalogue_id], shipped.__getitem__)


def default_catalogue_id(country_code: str | None) -> str:
    """The shipped catalogue for a project's country, else ``neutral``."""
    country = (country_code or "").strip().upper()
    if not country:
        return DEFAULT_CATALOGUE_ID
    claims = [c.id for c in shipped_catalogues().values() if c.jurisdiction.upper() == country]
    return claims[0] if len(claims) == 1 else DEFAULT_CATALOGUE_ID
