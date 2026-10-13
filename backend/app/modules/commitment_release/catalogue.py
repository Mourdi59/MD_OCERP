# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The two catalogue kinds of this module: authority schedules and abort bases.

Both are data, not code. Shipped JSON lives in ``catalogues/<kind>/``; tenant
drafts and published versions live in the shared governance catalogue tables
and go through the same resolver (``project_governance.catalogue_store``). This
module only adds the body models, their validators and the registration call.

``authority_schedule`` (delegation of authority): which tier of approver a
release needs, by commitment type and amount. Bands are evaluated per type in
tier order; the first band whose ``max_amount`` covers the amount names the
tier; ``max_amount: null`` is an open top band; above every band the release
must be consented outside the schedule (``escalate_outside``).

``abort_basis``: the parameters of one way of computing what aborting a
commitment costs. Methods are generic (``price_less_saved_costs``,
``fee_on_unperformed``, ``profit_on_performed``, ``schedule_only``, ``free``,
``custom``); a statute is a parameter set with a source, never a code path
keyed on a country.

Every figure taken from a statute (``statutory: true``) carries ``source_url``
and ``review_status``. Lead decision e: statutory abort formulas ship as
``review_status: unconfirmed`` and the exposure view says so next to the figure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus

AUTHORITY_SCHEDULE_KIND = "authority_schedule"
ABORT_BASIS_KIND = "abort_basis"
CATALOGUE_ROOT = Path(__file__).with_name("catalogues")
I18N_PREFIX = "commitment.catalogue."
ANY_TYPE = "*"
DEFAULT_SCHEDULE_ID = "neutral"

COMMITMENT_TYPES: tuple[str, ...] = (
    "works",
    "services",
    "supplies",
    "design",
    "change",
    "contingency_drawdown",
    "claim_settlement",
    "termination_settlement",
)
ABORT_METHODS: tuple[str, ...] = (
    "price_less_saved_costs",
    "fee_on_unperformed",
    "profit_on_performed",
    "schedule_only",
    "free",
    "custom",
)


def parse_amount(value: Any) -> Decimal:
    """A money amount from a string or number; junk, NaN and infinity raise ``ValueError``.

    Never turns junk into 0: an authority check on a silently zeroed amount
    would release anything.
    """
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
    """Where a figure comes from and whether it was checked there."""

    statutory: bool = False
    source_url: str | None = None
    review_status: ReviewStatus | None = None


class CommitmentTypeDef(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None


class Approver(_Frozen):
    """Who fills a tier: a platform role, a project role key, or (tenant only) one user."""

    kind: Literal["role", "project_role", "user"]
    ref: str = Field(min_length=1, max_length=64)


class Tier(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    approver: Approver
    steps_mode: Literal["all", "any"] = "any"
    four_eyes: bool = True
    sla_hours: int | None = Field(default=None, ge=1, le=720)


class Band(Sourced):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    commitment_type: str = ANY_TYPE
    tier: str
    # Decimal string in the schedule currency; null = open top band.
    max_amount: str | None = None
    note_key: str = ""


class NoveltyFlag(Sourced):
    """A type or item flag that forces a minimum tier regardless of amount."""

    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    min_tier: str


class Tolerance(_Frozen):
    absolute: str = "0"
    percent: str = "0"


class AuthoritySchedule(_Frozen):
    """One delegation-of-authority schedule (``authority_schedule`` body)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    review_status: ReviewStatus = ReviewStatus.verified
    jurisdiction_countries: tuple[str, ...] = ()
    source_url: str | None = None
    # ISO 4217 of the bands; null = the project's base currency (neutral schedules).
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    basis: Literal["net", "gross"] = "net"
    aggregation: Literal["item_total", "request_only"] = "item_total"
    commitment_types: tuple[CommitmentTypeDef, ...]
    tiers: tuple[Tier, ...]
    bands: tuple[Band, ...]
    novelty_flags: tuple[NoveltyFlag, ...] = ()
    variation_tolerance: Tolerance = Tolerance()
    effective_from: date | None = None
    effective_to: date | None = None
    legal_entity_id: str | None = None

    def tier_order(self) -> dict[str, int]:
        return {t.code: i for i, t in enumerate(self.tiers)}

    def tier(self, code: str) -> Tier:
        for t in self.tiers:
            if t.code == code:
                return t
        raise KeyError(code)

    def type_codes(self) -> set[str]:
        return {t.code for t in self.commitment_types}


class AbortParameter(Sourced):
    """One formula parameter. ``value: null`` = taken from the contract (abort terms)."""

    value: str | None = None
    note_key: str = ""


class AbortBasis(_Frozen):
    """One way of computing the cost of aborting a commitment (``abort_basis`` body)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    review_status: ReviewStatus = ReviewStatus.verified
    jurisdiction_countries: tuple[str, ...] = ()
    source_url: str | None = None
    method: Literal[
        "price_less_saved_costs", "fee_on_unperformed", "profit_on_performed", "schedule_only", "free", "custom"
    ]
    parameters: dict[str, AbortParameter] = Field(default_factory=dict)


# Parameters each method reads. A missing parameter is a catalogue error; a
# parameter with ``value: null`` must come from the abort terms.
METHOD_PARAMETERS: dict[str, tuple[str, ...]] = {
    "price_less_saved_costs": ("presumed_unperformed_pct",),
    "fee_on_unperformed": ("fee_pct",),
    "profit_on_performed": ("profit_pct",),
    "schedule_only": (),
    "free": (),
    "custom": (),
}


def parameter_fields(basis: AbortBasis) -> list[dict[str, Any]]:
    """The parameters abort terms may set for ``basis``, as form fields.

    Every parameter a method reads is a share written as a fraction of one (``0.05`` is five per
    cent). ``default`` is the value the basis ships; ``required`` says the basis ships none, so the
    figure has to come from the contract.
    """
    return [
        {
            "name": name,
            "type": "fraction",
            "unit": "fraction_of_one",
            "min": "0",
            "max": "1",
            "default": p.value,
            "required": p.value is None,
            "statutory": p.statutory,
            "label_key": f"commitment.abort_parameter.{name}",
            "note_key": p.note_key or None,
        }
        for name, p in basis.parameters.items()
    ]


def parameter_violation(basis: AbortBasis | None, parameters: dict[str, Any]) -> tuple[str, str] | None:
    """``(code, names)`` when ``parameters`` do not fit ``basis``, else ``None``.

    A parameter the basis does not have is refused, so the values of a basis the terms used before
    never ride along under a new one; a value has to be a fraction between 0 and 1.
    """
    known = basis.parameters if basis is not None else {}
    foreign = sorted(name for name in parameters if name not in known)
    if foreign:
        return "abort_parameter_not_in_basis", ", ".join(foreign)
    invalid = []
    for name, raw in parameters.items():
        try:
            value = parse_amount(raw)
        except ValueError:
            invalid.append(name)
            continue
        if not (Decimal("0") <= value <= Decimal("1")):
            invalid.append(name)
    if invalid:
        return "abort_parameter_invalid", ", ".join(sorted(invalid))
    return None


def _sourced_errors(where: str, item: Sourced) -> list[str]:
    if not item.statutory:
        return []
    errors = []
    if not item.source_url:
        errors.append(f"statutory_figure_without_source: {where}")
    if item.review_status is None:
        errors.append(f"statutory_figure_without_review_status: {where}")
    return errors


def _label_errors(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped":
        if not name_key.startswith(I18N_PREFIX) and not name_key.startswith("commitment."):
            return [f"shipped_label_not_i18n_key: {where}"]
        return []
    if not name_key and not labels:
        return [f"label_missing: {where}"]
    return []


def validate_authority_schedule(obj: AuthoritySchedule, source: str) -> list[str]:
    """Cross-reference rules of an authority schedule; an empty list means valid."""
    errors: list[str] = []
    errors += _label_errors("schedule", obj.name_key, obj.labels, source)
    types = [t.code for t in obj.commitment_types]
    tiers = [t.code for t in obj.tiers]
    if len(set(types)) != len(types):
        errors.append("duplicate_commitment_type")
    if len(set(tiers)) != len(tiers):
        errors.append("duplicate_tier")
    if not obj.tiers:
        errors.append("no_tiers")
    for t in obj.commitment_types:
        errors += _label_errors(f"type:{t.code}", t.name_key, t.labels, source)
    for t in obj.tiers:
        errors += _label_errors(f"tier:{t.code}", t.name_key, t.labels, source)
        if t.approver.kind == "user" and source == "shipped":
            errors.append(f"user_approver_in_shipped_schedule: {t.code}")
    codes = [b.code for b in obj.bands]
    if len(set(codes)) != len(codes):
        errors.append("duplicate_band_code")
    order = obj.tier_order()
    by_type: dict[str, list[Band]] = {}
    for b in obj.bands:
        errors += _sourced_errors(f"band:{b.code}", b)
        if b.tier not in order:
            errors.append(f"band_unknown_tier: {b.code}")
            continue
        if b.commitment_type != ANY_TYPE and b.commitment_type not in types:
            errors.append(f"band_unknown_type: {b.code}")
            continue
        if b.max_amount is not None:
            try:
                if parse_amount(b.max_amount) <= 0:
                    errors.append(f"band_amount_not_positive: {b.code}")
            except ValueError:
                errors.append(f"band_amount_invalid: {b.code}")
                continue
        by_type.setdefault(b.commitment_type, []).append(b)
    if ANY_TYPE not in by_type and set(types) - set(by_type):
        errors.append("types_without_bands: " + ",".join(sorted(set(types) - set(by_type))))
    for type_code, bands in by_type.items():
        errors += _monotonic_errors(type_code, bands, order)
    for f in obj.novelty_flags:
        errors += _sourced_errors(f"novelty:{f.code}", f)
        errors += _label_errors(f"novelty:{f.code}", f.name_key, f.labels, source)
        if f.min_tier not in order:
            errors.append(f"novelty_unknown_tier: {f.code}")
    try:
        if parse_amount(obj.variation_tolerance.absolute) < 0 or parse_amount(obj.variation_tolerance.percent) < 0:
            errors.append("tolerance_negative")
    except ValueError:
        errors.append("tolerance_invalid")
    if obj.effective_from and obj.effective_to and obj.effective_to < obj.effective_from:
        errors.append("effective_window_inverted")
    return errors


def _monotonic_errors(type_code: str, bands: list[Band], order: dict[str, int]) -> list[str]:
    """Within one type, higher tiers must carry strictly higher ceilings; only the last may be open."""
    errors: list[str] = []
    ordered = sorted(bands, key=lambda b: order[b.tier])
    seen_tiers = [b.tier for b in ordered]
    if len(set(seen_tiers)) != len(seen_tiers):
        errors.append(f"bands_duplicate_tier: {type_code}")
    previous: Decimal | None = None
    for i, b in enumerate(ordered):
        if b.max_amount is None:
            if i != len(ordered) - 1:
                errors.append(f"bands_not_monotonic: {type_code}")
            continue
        try:
            amount = parse_amount(b.max_amount)
        except ValueError:
            continue
        if previous is not None and amount <= previous:
            errors.append(f"bands_not_monotonic: {type_code}")
        previous = amount
    return errors


def validate_abort_basis(obj: AbortBasis, source: str) -> list[str]:
    """Cross-reference rules of an abort basis; an empty list means valid."""
    errors: list[str] = []
    errors += _label_errors("basis", obj.name_key, obj.labels, source)
    for name in METHOD_PARAMETERS[obj.method]:
        if name not in obj.parameters:
            errors.append(f"parameter_missing: {name}")
    for name, p in obj.parameters.items():
        errors += _sourced_errors(f"parameter:{name}", p)
        if p.value is not None:
            try:
                value = parse_amount(p.value)
            except ValueError:
                errors.append(f"parameter_invalid: {name}")
                continue
            if name.endswith("_pct") and not (Decimal("0") <= value <= Decimal("1")):
                errors.append(f"parameter_pct_out_of_range: {name}")
    if any(p.statutory for p in obj.parameters.values()) and obj.review_status == ReviewStatus.verified:
        # Lead decision e: statutory abort formulas are not confirmed by a domain expert yet.
        errors.append("statutory_basis_must_be_unconfirmed")
    return errors


def register_kinds() -> None:
    """Register both kinds with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=AUTHORITY_SCHEDULE_KIND,
            model=AuthoritySchedule,
            validator=validate_authority_schedule,
            shipped_dir=CATALOGUE_ROOT / AUTHORITY_SCHEDULE_KIND,
            diff_groups=("commitment_types", "tiers", "bands", "novelty_flags"),
        )
    )
    register_catalogue_kind(
        CatalogueKind(
            kind=ABORT_BASIS_KIND,
            model=AbortBasis,
            validator=validate_abort_basis,
            shipped_dir=CATALOGUE_ROOT / ABORT_BASIS_KIND,
            diff_groups=(),
        )
    )
