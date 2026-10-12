# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``procurement_procedures``: procedures, thresholds, lot rules, criteria, lead times.

All of it is data. Shipped JSON lives in ``catalogues/``; a company clones,
edits and publishes its own versions through module 1's catalogue store
(``/api/v1/project-governance/catalogues?kind=procurement_procedures``), and a
project pins ``(source, id, version)`` on its procurement concept.

Procedures are neutral codes (``open``, ``restricted``, ...) with national
names as ``aliases``. A threshold is a dated, sourced figure: the resolver
picks the one valid on the planned procedure start, never a constant in code.
Every legal fact carries ``source_url`` and ``review_status``; the governance
vocabulary is reused, so the SPEC's ``confirmed`` is ``verified`` here. A fact
that is ``unconfirmed`` never produces a hard error (SPEC rule 5).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.project_governance.catalogue import ReviewStatus

PROCUREMENT_KIND = "procurement_procedures"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"

COMPETITIONS = (
    "open",
    "restricted",
    "negotiated",
    "dialogue",
    "innovation_partnership",
    "direct",
    "framework_call_off",
    "mini_competition",
)
CONTRACT_KINDS = ("works", "supplies", "services", "design_services", "concession", "light_touch")
CLIENT_TYPES = ("central", "sub_central", "utility", "private")
JURISDICTIONS = ("eu", "uk", "us_federal", "de_national", "none")
THRESHOLD_EFFECTS = ("above_requires_publication", "below_allows_direct", "below_allows_simplified")
LOT_RULE_KINDS = ("aggregation", "small_lots_exemption", "splitting_preference")
CRITERION_GROUPS = (
    "financial",
    "technical",
    "experience",
    "hse",
    "quality",
    "legal",
    "sustainability",
    "capacity",
)
LEAD_TIME_STEPS = ("prep", "publication", "bid_period", "evaluation", "standstill", "award")

# mod3 ``ContractPackage.kind`` -> catalogue package kind. ``project_agreement``
# is the one multi-party agreement of an alliance or PPP; it is procured as the
# project itself, not as an award package (SPEC rule 1).
CONTRACT_PACKAGE_KIND_MAP: dict[str, str | None] = {
    "design": "design",
    "construction": "works",
    "design_and_construction": "works",
    "supply": "supply",
    "supply_and_install": "supply_and_install",
    "management_services": "services",
    "operation": "services",
    "project_agreement": None,
}


def parse_amount(value: Any) -> Decimal:
    """A money amount from a decimal string or int; floats, junk, NaN and infinity raise ``ValueError``."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"not an amount: {value!r}")
    if isinstance(value, float):
        raise ValueError("floats are not accepted for money; send a decimal string")
    try:
        out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"not an amount: {value!r}") from exc
    if not out.is_finite():
        raise ValueError(f"not a finite amount: {value!r}")
    return out


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(_Frozen):
    """Where a legal fact comes from, whether it was checked there, and when it holds."""

    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    valid_from: date | None = None
    valid_to: date | None = None

    def valid_on(self, day: date) -> bool:
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_to is None or day <= self.valid_to)


class Alias(_Frozen):
    jurisdiction: str = Field(min_length=1, max_length=20)
    term: str = Field(min_length=1, max_length=200)
    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class Procedure(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    competition: Literal[
        "open",
        "restricted",
        "negotiated",
        "dialogue",
        "innovation_partnership",
        "direct",
        "framework_call_off",
        "mini_competition",
    ]
    # public: only public clients; private: only private clients; both.
    sector: Literal["public", "private", "both"] = "both"
    stages: Literal[1, 2] = 1
    has_prequalification: bool = False
    negotiation_allowed: bool = False
    tender_basis_allowed: tuple[Literal["detailed", "functional"], ...] = ("detailed", "functional")
    min_bidders: int | None = Field(default=None, ge=1, le=50)
    min_period_days: int | None = Field(default=None, ge=0, le=365)
    aliases: tuple[Alias, ...] = ()


class Threshold(Sourced):
    contract_kind: Literal["works", "supplies", "services", "design_services", "concession", "light_touch"]
    client_type: Literal["central", "sub_central", "utility", "private"]
    amount: str
    currency: str = Field(min_length=3, max_length=3)
    vat_basis: Literal["net", "gross"] = "net"
    effect: Literal["above_requires_publication", "below_allows_direct", "below_allows_simplified"]
    allowed_above: tuple[str, ...] = ()
    allowed_below: tuple[str, ...] = ()

    @field_validator("amount")
    @classmethod
    def _amount(cls, v: str) -> str:
        if parse_amount(v) <= 0:
            raise ValueError("threshold amount must be positive")
        return v

    @property
    def value(self) -> Decimal:
        return parse_amount(self.amount)


class LotRule(Sourced):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    kind: Literal["aggregation", "small_lots_exemption", "splitting_preference"]
    contract_kind: str
    # small_lots_exemption: a lot below max_lot_value may be awarded under the
    # below-threshold rules while the exempted lots together stay within
    # max_share_pct of the aggregated value.
    max_lot_value: str | None = None
    max_share_pct: str | None = None
    currency: str | None = None
    name_key: str = ""


class MinPeriod(Sourced):
    procedure: str
    stage: Literal["request_to_participate", "tender"] = "tender"
    days: int = Field(ge=0, le=365)


class Jurisdiction(_Frozen):
    code: Literal["eu", "uk", "us_federal", "de_national", "none"]
    name_key: str = ""
    labels: dict[str, str] | None = None
    client_types: tuple[Literal["central", "sub_central", "utility", "private"], ...] = ()
    thresholds: tuple[Threshold, ...] = ()
    lot_rules: tuple[LotRule, ...] = ()
    min_periods: tuple[MinPeriod, ...] = ()


class PackageKind(_Frozen):
    code: Literal["design", "works", "supply", "supply_and_install", "services"]
    name_key: str = ""
    contract_kind: Literal["works", "supplies", "services", "design_services"]
    # design packages: architect, engineer, consultant, surveyor
    roles: tuple[str, ...] = ()
    fee_estimate_required: bool = False


class PrequalCriterion(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    group: Literal["financial", "technical", "experience", "hse", "quality", "legal", "sustainability", "capacity"]
    kind: Literal["pass_fail", "scored"]
    default_weight: str = "0"
    evidence_type: Literal["document", "reference", "certificate", "rating"] = "document"
    certificate_type: str | None = None


class LeadTime(Sourced):
    procedure: str
    prep: int = Field(ge=0, le=730)
    publication: int = Field(ge=0, le=365)
    bid_period: int = Field(ge=0, le=365)
    evaluation: int = Field(ge=0, le=365)
    standstill: int = Field(ge=0, le=365)
    award: int = Field(ge=0, le=365)

    def total_days(self) -> int:
        return self.prep + self.publication + self.bid_period + self.evaluation + self.standstill + self.award


class CurrencyRate(Sourced):
    """Fixed conversion a threshold regime publishes (e.g. EUR values in national currency)."""

    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: str


class ProcurementCatalogue(_Frozen):
    id: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    jurisdiction_countries: tuple[str, ...] = ()
    procedures: tuple[Procedure, ...] = ()
    jurisdictions: tuple[Jurisdiction, ...] = ()
    package_kinds: tuple[PackageKind, ...] = ()
    prequal_criteria: tuple[PrequalCriterion, ...] = ()
    lead_time_defaults: tuple[LeadTime, ...] = ()
    currency_rates: tuple[CurrencyRate, ...] = ()

    def procedure(self, code: str | None) -> Procedure | None:
        return next((p for p in self.procedures if p.code == code), None)

    def jurisdiction(self, code: str | None) -> Jurisdiction | None:
        return next((j for j in self.jurisdictions if j.code == code), None)

    def package_kind(self, code: str | None) -> PackageKind | None:
        return next((k for k in self.package_kinds if k.code == code), None)

    def criterion(self, code: str) -> PrequalCriterion | None:
        return next((c for c in self.prequal_criteria if c.code == code), None)

    def lead_time(self, procedure: str | None) -> LeadTime | None:
        return next((t for t in self.lead_time_defaults if t.procedure == procedure), None)


def _dupes(values: list[str]) -> set[str]:
    seen: set[str] = set()
    return {v for v in values if v in seen or seen.add(v)}  # type: ignore[func-returns-value]


def validate_procurement_catalogue(obj: ProcurementCatalogue, source: str) -> list[str]:
    """Cross-reference rules of one catalogue body; empty list = valid."""
    errors: list[str] = []
    codes = [p.code for p in obj.procedures]
    for d in sorted(_dupes(codes)):
        errors.append(f"duplicate_procedure: {d}")
    for d in sorted(_dupes([c.code for c in obj.prequal_criteria])):
        errors.append(f"duplicate_criterion: {d}")
    for d in sorted(_dupes([j.code for j in obj.jurisdictions])):
        errors.append(f"duplicate_jurisdiction: {d}")
    known = set(codes)
    for p in obj.procedures:
        for a in p.aliases:
            if not a.source_url:
                errors.append(f"alias_without_source: {p.code}/{a.term}")
    for j in obj.jurisdictions:
        for t in j.thresholds:
            if not t.source_url or t.valid_from is None:
                errors.append(f"threshold_without_source: {j.code}/{t.contract_kind}/{t.client_type}")
            if t.valid_from and t.valid_to and t.valid_to < t.valid_from:
                errors.append(f"threshold_validity_inverted: {j.code}/{t.contract_kind}/{t.client_type}")
            for code in (*t.allowed_above, *t.allowed_below):
                if code not in known:
                    errors.append(f"threshold_unknown_procedure: {j.code}/{code}")
        for r in j.lot_rules:
            if not r.source_url:
                errors.append(f"lot_rule_without_source: {j.code}/{r.code}")
        for m in j.min_periods:
            if m.procedure not in known:
                errors.append(f"min_period_unknown_procedure: {j.code}/{m.procedure}")
        # Two thresholds for the same (kind, client) may not overlap in time.
        by_key: dict[tuple[str, str, str], list[Threshold]] = {}
        for t in j.thresholds:
            by_key.setdefault((t.contract_kind, t.client_type, t.effect), []).append(t)
        for key, rows in by_key.items():
            rows = sorted(rows, key=lambda t: t.valid_from or date.min)
            for a, b in zip(rows, rows[1:], strict=False):
                if a.valid_to is None or (b.valid_from and b.valid_from <= a.valid_to):
                    errors.append(f"threshold_validity_overlap: {j.code}/{key[0]}/{key[1]}")
    for t in obj.lead_time_defaults:
        if t.procedure not in known:
            errors.append(f"lead_time_unknown_procedure: {t.procedure}")
    scored = [c for c in obj.prequal_criteria if c.kind == "scored"]
    for c in scored:
        try:
            parse_amount(c.default_weight)
        except ValueError:
            errors.append(f"criterion_weight_invalid: {c.code}")
    for r in obj.currency_rates:
        try:
            if parse_amount(r.rate) <= 0:
                errors.append(f"currency_rate_not_positive: {r.from_currency}/{r.to_currency}")
        except ValueError:
            errors.append(f"currency_rate_invalid: {r.from_currency}/{r.to_currency}")
    if source == "shipped" and obj.review_status == ReviewStatus.verified:
        unconfirmed = [t for j in obj.jurisdictions for t in j.thresholds if t.review_status != ReviewStatus.verified]
        if unconfirmed:
            errors.append("catalogue_verified_with_unconfirmed_thresholds")
    return errors


def register_kind() -> None:
    """Register ``procurement_procedures`` with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=PROCUREMENT_KIND,
            model=ProcurementCatalogue,
            validator=validate_procurement_catalogue,
            shipped_dir=CATALOGUE_DIR,
            # Groups whose items carry a ``code`` (the store diffs by it).
            diff_groups=("procedures", "jurisdictions", "package_kinds", "prequal_criteria"),
        )
    )
