# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``plant_register``: component classes, routes, sources, steps.

Data, not code. Shipped JSON lives in ``catalogues/``; tenant drafts and
published versions live in the governance catalogue tables and resolve through
``project_governance.catalogue_store.resolve_catalogue``. A project pins
``(source, id, version)`` in :class:`~app.modules.plant_register.models.PlantSettings`.

Market lead times are never evidence: every ``typical_lead_weeks`` ships as
``review_status: unconfirmed`` with an ``as_of`` date, and only a dated project
quote (``LeadTimeQuote``) moves an item off the catalogue default. A figure
marked ``verified`` must name its ``source_url``; an unconfirmed one may not
have a source yet (SPEC section 12 lists which).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus

PLANT_KIND = "plant_register"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"

ITEM_CLASSES: tuple[str, ...] = ("main_component", "user_equipment", "operating_equipment")
DISCIPLINES: tuple[str, ...] = ("electrical", "mechanical", "conveying", "process", "structure", "envelope", "it")
_CODE = r"^[a-z0-9][a-z0-9_]*$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None


class LeadWeeks(_Frozen):
    min: int = Field(ge=0, le=520)
    max: int = Field(ge=0, le=520)
    as_of: str = ""
    source_url: str | None = None
    review_status: ReviewStatus = "unconfirmed"


class ComponentClass(_Labelled):
    item_class: Literal["main_component", "user_equipment", "operating_equipment"]
    discipline: Literal["electrical", "mechanical", "conveying", "process", "structure", "envelope", "it"]
    typical_lead_weeks: LeadWeeks
    quote_max_age_days: int = Field(default=90, ge=1, le=3650)
    needs_slot_reservation_above_weeks: int | None = Field(default=None, ge=0, le=520)
    critical_by_default: bool = False
    default_spare_categories: tuple[str, ...] = ()
    default_maintenance_strategy: str = ""
    ifc_class: str = ""


class RedundancyScheme(_Frozen):
    code: str = Field(min_length=1, max_length=16)
    name_key: str = ""
    description_key: str = ""
    labels: dict[str, str] | None = None
    min_quantity: int = Field(default=1, ge=1, le=99)
    source_url: str | None = None
    review_status: ReviewStatus = "unconfirmed"


class RouteAlias(_Frozen):
    country: str = Field(min_length=2, max_length=2)
    text: str
    source_url: str | None = None
    review_status: ReviewStatus = "unconfirmed"


class ProcurementRoute(_Labelled):
    acronym: str = ""
    owner_furnished: bool
    needs_package: bool
    source_url: str | None = None
    review_status: ReviewStatus = "unconfirmed"
    aliases: tuple[RouteAlias, ...] = ()


class LeadTimeSource(_Labelled):
    evidence_rank: int = Field(ge=1, le=99)
    # False for sources that are an opinion rather than the market (rule 6).
    market_evidence: bool


class ItServiceKind(_Labelled):
    responsible_party: str = "owner"


class Step(_Labelled):
    order: int = Field(ge=1)


class OrderBuffers(_Frozen):
    transport_days: int = Field(default=14, ge=0, le=365)
    install_lead_days: int = Field(default=21, ge=0, le=365)
    approval_buffer_days: int = Field(default=14, ge=0, le=365)
    drawing_review_days: int = Field(default=28, ge=0, le=365)
    review_status: ReviewStatus = "unconfirmed"


class PlantCatalogue(_Frozen):
    """One body of kind ``plant_register``."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    jurisdiction_countries: tuple[str, ...] = ()
    review_status: ReviewStatus = "unconfirmed"
    long_lead_threshold_weeks: int = Field(default=12, ge=1, le=520)
    warn_days: int = Field(default=30, ge=0, le=365)
    order_buffer_days: OrderBuffers = OrderBuffers()
    component_classes: tuple[ComponentClass, ...]
    redundancy_schemes: tuple[RedundancyScheme, ...]
    procurement_routes: tuple[ProcurementRoute, ...]
    lead_time_sources: tuple[LeadTimeSource, ...]
    spare_categories: tuple[_Labelled, ...]
    maintenance_strategies: tuple[_Labelled, ...]
    delivery_limit_steps: tuple[Step, ...]
    site_plant_kinds: tuple[_Labelled, ...] = ()
    it_service_kinds: tuple[ItServiceKind, ...] = ()
    parties: tuple[_Labelled, ...] = ()

    def component_class(self, code: str) -> ComponentClass | None:
        return next((c for c in self.component_classes if c.code == code), None)

    def route(self, code: str) -> ProcurementRoute | None:
        return next((r for r in self.procurement_routes if r.code == code), None)

    def source(self, code: str) -> LeadTimeSource | None:
        return next((s for s in self.lead_time_sources if s.code == code), None)

    def scheme(self, code: str) -> RedundancyScheme | None:
        return next((s for s in self.redundancy_schemes if s.code == code), None)

    def step_codes(self) -> tuple[str, ...]:
        return tuple(s.code for s in sorted(self.delivery_limit_steps, key=lambda s: s.order))

    def codes(self, group: str) -> set[str]:
        return {getattr(x, "code", "") for x in getattr(self, group)}


def _unique(group: str, codes: list[str]) -> list[str]:
    seen: set[str] = set()
    dup = sorted({c for c in codes if c in seen or seen.add(c)})  # type: ignore[func-returns-value]
    return [f"{group}: duplicate code {c}" for c in dup]


def _sourced(where: str, status: str, url: str | None) -> list[str]:
    if status == "verified" and not (url or "").startswith("http"):
        return [f"{where}: verified without source_url"]
    return []


def _label(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped" and not name_key:
        return [f"{where}: shipped item needs name_key"]
    if source != "shipped" and not name_key and not labels:
        return [f"{where}: needs name_key or labels"]
    return []


def validate_plant_catalogue(obj: PlantCatalogue, source: str) -> list[str]:
    """Cross-reference rules of one catalogue body; empty list means valid."""
    errors: list[str] = []
    for group in (
        "component_classes",
        "procurement_routes",
        "lead_time_sources",
        "spare_categories",
        "maintenance_strategies",
        "delivery_limit_steps",
        "site_plant_kinds",
        "it_service_kinds",
        "parties",
    ):
        items = getattr(obj, group)
        errors += _unique(group, [i.code for i in items])
        for i in items:
            errors += _label(f"{group}.{i.code}", i.name_key, i.labels, source)
    errors += _unique("redundancy_schemes", [s.code for s in obj.redundancy_schemes])
    spares = obj.codes("spare_categories")
    strategies = obj.codes("maintenance_strategies")
    for c in obj.component_classes:
        lw = c.typical_lead_weeks
        if lw.min > lw.max:
            errors.append(f"component_classes.{c.code}: typical_lead_weeks min > max")
        # Rule: a market lead time is never shipped as verified evidence.
        if source == "shipped" and lw.review_status != "unconfirmed":
            errors.append(f"component_classes.{c.code}: shipped lead time must be unconfirmed")
        errors += _sourced(f"component_classes.{c.code}.typical_lead_weeks", lw.review_status, lw.source_url)
        for s in c.default_spare_categories:
            if s not in spares:
                errors.append(f"component_classes.{c.code}: unknown spare category {s}")
        if c.default_maintenance_strategy and c.default_maintenance_strategy not in strategies:
            errors.append(f"component_classes.{c.code}: unknown maintenance strategy")
    for r in obj.procurement_routes:
        errors += _sourced(f"procurement_routes.{r.code}", r.review_status, r.source_url)
        for a in r.aliases:
            errors += _sourced(f"procurement_routes.{r.code}.alias.{a.country}", a.review_status, a.source_url)
    for s in obj.redundancy_schemes:
        errors += _sourced(f"redundancy_schemes.{s.code}", s.review_status, s.source_url)
    if not obj.delivery_limit_steps:
        errors.append("delivery_limit_steps: empty")
    if not any(not s.market_evidence for s in obj.lead_time_sources) and source == "shipped":
        errors.append("lead_time_sources: shipped catalogue must mark expert estimates as non-market")
    return errors


def register_plant_kind() -> None:
    """Register kind ``plant_register`` with the governance catalogue registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=PLANT_KIND,
            model=PlantCatalogue,
            validator=validate_plant_catalogue,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=(
                "component_classes",
                "redundancy_schemes",
                "procurement_routes",
                "lead_time_sources",
                "delivery_limit_steps",
                "it_service_kinds",
            ),
        )
    )


def shipped_default() -> PlantCatalogue:
    """The shipped neutral catalogue, latest version."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_plant_kind()
    return get_catalogue_kind(PLANT_KIND).get_shipped(DEFAULT_CATALOGUE_ID)
