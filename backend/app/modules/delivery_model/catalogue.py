# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``delivery_forms``: delivery forms, parties, risk categories and defaults.

Data, not code. Shipped JSON lives in ``catalogues/``; tenant drafts and
published versions live in the shared governance catalogue tables and go
through the one resolver (``project_governance.catalogue_store``). This module
only adds the body model, its validator and the registration call.

A form is defined by responsibility attributes (who designs, how many
construction contracts the owner holds, the contractor's role, the price basis
at award, early involvement, finance and operation scope), never by a national
name. National and standard-form names (general contractor, design and build,
CMAR, FIDIC Yellow) are aliases on a neutral form and carry their source.

Every value checked against another platform vocabulary is checked here, so a
catalogue that names a contract type, party role or risk register category the
platform does not know never publishes.
"""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.project_governance.catalogue import ReviewStatus

DELIVERY_FORMS_KIND = "delivery_forms"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"
I18N_PREFIX = "delivery_model."

DESIGN_RESPONSIBILITY = ("owner", "contractor", "split_at_stage", "shared")
OWNER_CONSTRUCTION_CONTRACTS = ("many", "one", "one_per_package_managed")
CONTRACTOR_ROLES = ("builder", "manager_at_risk", "manager_agency", "integrator", "concessionaire")
PRICE_BASES = ("remeasure", "lump_sum", "gmp", "target_cost", "cost_reimbursable", "availability_payment")
EARLY_INVOLVEMENT = ("none", "preconstruction_services", "two_stage", "multi_party")
SCOPE_EXTENSIONS = ("finance", "operate", "maintain")
ALLOCATION_BASES = ("contract", "insurance", "shared_pain_gain", "statute", "ground_baseline")
PACKAGE_KINDS = (
    "design",
    "construction",
    "design_and_construction",
    "supply",
    "supply_and_install",
    "management_services",
    "operation",
    "project_agreement",
)
CONTRACTING_PARTIES = ("owner", "manager")
SHARED_PARTY = "shared"
# SPEC rule 4: a shared risk is shared through a pain/gain mechanism or a ground baseline, never "by contract".
SHARED_BASES = ("shared_pain_gain", "ground_baseline")
# Form attributes an option may customise for one project (SPEC section 3, option overrides).
OVERRIDABLE = (
    "design_responsibility",
    "design_transfer_stage",
    "owner_construction_contracts",
    "contractor_role",
    "price_basis_at_award",
    "allowed_price_bases",
    "early_involvement",
    "scope_extends",
    "self_performs",
)

# Read from the owning modules at validation time; repeated here only as the
# fallback for a unit test environment that cannot import them.
_RISK_CATEGORY_RE = re.compile(r"^(technical|financial|schedule|regulatory|environmental|safety|procurement)$")


def platform_contract_types() -> tuple[str, ...]:
    """``contracts.CONTRACT_TYPES`` as a tuple (the one vocabulary of contract types)."""
    from app.modules.contracts.schemas import CONTRACT_TYPES

    return tuple(CONTRACT_TYPES.split("|"))


def platform_party_roles() -> tuple[str, ...]:
    """``contracts.PARTY_ROLES`` as a tuple."""
    from app.modules.contracts.schemas import PARTY_ROLES

    return tuple(PARTY_ROLES.split("|"))


def platform_risk_categories() -> tuple[str, ...]:
    """The 7 closed categories of the risk register (``risk/schemas.py`` pattern)."""
    from app.modules.risk.schemas import RiskCreate

    pattern = RiskCreate.model_fields["category"].metadata
    for m in pattern:
        value = getattr(m, "pattern", None)
        if value:
            return tuple(value.strip("^$()").split("|"))
    return tuple(_RISK_CATEGORY_RE.pattern.strip("^$()").split("|"))


def phase_spine() -> tuple[str, ...]:
    from app.modules.requirements.lifecycle import PHASE_SPINE

    return tuple(PHASE_SPINE)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    name_key: str = ""
    labels: dict[str, str] | None = None


class Alias(_Frozen):
    """A national or standard-form name for a neutral form."""

    country: str = ""  # ISO code, or "" for an international standard form
    term: str
    self_performs: bool | None = None
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class DeliveryForm(_Labelled):
    code: str
    description_key: str = ""
    aliases: tuple[Alias, ...] = ()
    design_responsibility: Literal["owner", "contractor", "split_at_stage", "shared"]
    design_transfer_stage: str | None = None
    owner_construction_contracts: Literal["many", "one", "one_per_package_managed"]
    contractor_role: Literal["builder", "manager_at_risk", "manager_agency", "integrator", "concessionaire"]
    price_basis_at_award: Literal[
        "remeasure", "lump_sum", "gmp", "target_cost", "cost_reimbursable", "availability_payment"
    ]
    allowed_price_bases: tuple[str, ...] = ()
    early_involvement: Literal["none", "preconstruction_services", "two_stage", "multi_party"] = "none"
    scope_extends: tuple[str, ...] = ()
    self_performs: bool | None = None
    compatible_contract_types: tuple[str, ...] = ()
    compatible_standard_forms: tuple[str, ...] = ()
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed

    def price_bases(self) -> tuple[str, ...]:
        return self.allowed_price_bases or (self.price_basis_at_award,)


class Party(_Labelled):
    code: str
    contract_party_role: str
    # Which side of the contract the party stands on; rule 6 reads this, never the code.
    side: Literal["owner", "contractor", "operator"] | None = None


class RiskCategory(_Labelled):
    code: str
    description_key: str = ""
    register_category: str
    # What the risk is about, where a form's attributes decide who can carry it (rule 6).
    concerns: Literal["design", "operation"] | None = None


class DefaultAllocation(_Frozen):
    """The typical holder of one risk category under a set of forms. Never applied without confirmation."""

    risk_category: str
    forms: tuple[str, ...]
    party: str
    basis: str = "contract"
    shares: dict[str, str] | None = None  # party -> percent string, only for ``shared``
    rationale_key: str = ""
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class Criterion(_Labelled):
    code: str
    default_weight: str
    rationale_key: str = ""
    scores: dict[str, int] = Field(default_factory=dict)  # form code -> 1..5, higher is better


class CountryRule(_Labelled):
    code: str
    country: str
    severity: Literal["info", "warning"] = "info"
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class PackageTemplateItem(_Frozen):
    code: str
    title_key: str = ""
    labels: dict[str, str] | None = None
    kind: str
    designs: bool = False
    builds: bool = False
    supplies: bool = False
    manages: bool = False
    party: str = "contractor"
    contracting_party: Literal["owner", "manager"] = "owner"
    price_basis: str | None = None
    parent: str | None = None


class PackageTemplate(_Frozen):
    form: str
    packages: tuple[PackageTemplateItem, ...]


class Flag(_Labelled):
    code: str
    aliases: tuple[Alias, ...] = ()
    source_url: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class DeliveryFormsCatalogue(_Labelled):
    """One catalogue body of kind ``delivery_forms``."""

    id: str
    version: int = 1
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    source_url: str = ""
    source_title: str = ""
    jurisdiction_countries: tuple[str, ...] = ()
    forms: tuple[DeliveryForm, ...]
    parties: tuple[Party, ...]
    risk_categories: tuple[RiskCategory, ...]
    default_allocations: tuple[DefaultAllocation, ...] = ()
    criteria: tuple[Criterion, ...]
    price_basis_contract_types: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    country_rules: tuple[CountryRule, ...] = ()
    package_templates: tuple[PackageTemplate, ...] = ()
    flags: tuple[Flag, ...] = ()

    def form(self, code: str | None) -> DeliveryForm | None:
        return next((f for f in self.forms if f.code == code), None)

    def party(self, code: str | None) -> Party | None:
        return next((p for p in self.parties if p.code == code), None)

    def category(self, code: str) -> RiskCategory | None:
        return next((c for c in self.risk_categories if c.code == code), None)

    def default_for(self, form_code: str | None, category: str) -> DefaultAllocation | None:
        if not form_code:
            return None
        return next((a for a in self.default_allocations if a.risk_category == category and form_code in a.forms), None)

    def template_for(self, form_code: str) -> PackageTemplate | None:
        return next((t for t in self.package_templates if t.form == form_code), None)


def override_errors(form: DeliveryForm, overrides: dict[str, Any] | None) -> list[str]:
    """Why ``overrides`` cannot be applied to ``form``; an empty list means they can."""
    raw = overrides or {}
    errors = [f"override_not_allowed: {key}" for key in sorted(raw) if key not in OVERRIDABLE]
    if errors:
        return errors
    try:
        out = DeliveryForm.model_validate({**form.model_dump(mode="json"), **raw})
    except ValidationError as exc:
        return [f"override_invalid: {'.'.join(str(p) for p in e['loc'])}" for e in exc.errors()]
    errors += [f"override_invalid: allowed_price_bases:{b}" for b in out.price_bases() if b not in PRICE_BASES]
    if out.price_basis_at_award not in out.price_bases():
        errors.append("override_invalid: price_basis_at_award")
    errors += [f"override_invalid: scope_extends:{x}" for x in out.scope_extends if x not in SCOPE_EXTENSIONS]
    if out.design_responsibility == "split_at_stage":
        if not out.design_transfer_stage or out.design_transfer_stage not in set(phase_spine()):
            errors.append("override_invalid: design_transfer_stage")
    return errors


def effective_form(form: DeliveryForm | None, overrides: dict[str, Any] | None) -> DeliveryForm | None:
    """``form`` with an option's validated overrides applied; the rules read this, never the bare catalogue form."""
    if form is None or not overrides:
        return form
    return DeliveryForm.model_validate({**form.model_dump(mode="json"), **overrides})


def _label_errors(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped":
        if not name_key.startswith(I18N_PREFIX):
            return [f"shipped_label_not_i18n_key: {where}"]
        return []
    if not name_key and not labels:
        return [f"label_missing: {where}"]
    return []


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({c for c in codes if c in seen or seen.add(c)})  # type: ignore[func-returns-value]


def _decimal(value: str) -> Decimal | None:
    try:
        out = Decimal(str(value))
    except Exception:
        return None
    return out if out.is_finite() else None


def validate_delivery_forms(obj: DeliveryFormsCatalogue, source: str) -> list[str]:
    """Cross-reference rules of a delivery forms catalogue; an empty list means valid."""
    errors: list[str] = []
    contract_types = set(platform_contract_types())
    party_roles = set(platform_party_roles())
    register = set(platform_risk_categories())
    spine = set(phase_spine())
    errors += _label_errors("catalogue", obj.name_key, obj.labels, source)

    forms = [f.code for f in obj.forms]
    parties = [p.code for p in obj.parties]
    cats = [c.code for c in obj.risk_categories]
    crits = [c.code for c in obj.criteria]
    for group, codes in (("form", forms), ("party", parties), ("risk_category", cats), ("criterion", crits)):
        errors += [f"duplicate_{group}: {c}" for c in _dupes(codes)]
    if len(forms) < 2:
        errors.append("fewer_than_two_forms")
    if SHARED_PARTY not in parties:
        errors.append("party_shared_missing")

    for basis, types in obj.price_basis_contract_types.items():
        if basis not in PRICE_BASES:
            errors.append(f"price_basis_unknown: {basis}")
        errors += [f"contract_type_unknown: {basis}:{t}" for t in types if t not in contract_types]

    for f in obj.forms:
        errors += _label_errors(f"form:{f.code}", f.name_key, f.labels, source)
        errors += [f"form_price_basis_unknown: {f.code}:{b}" for b in f.price_bases() if b not in PRICE_BASES]
        if f.price_basis_at_award not in f.price_bases():
            errors.append(f"form_award_basis_not_allowed: {f.code}")
        errors += [f"form_scope_unknown: {f.code}:{s}" for s in f.scope_extends if s not in SCOPE_EXTENSIONS]
        errors += [
            f"form_contract_type_unknown: {f.code}:{t}" for t in f.compatible_contract_types if t not in contract_types
        ]
        if f.design_responsibility == "split_at_stage":
            if not f.design_transfer_stage:
                errors.append(f"form_transfer_stage_missing: {f.code}")
            elif f.design_transfer_stage not in spine:
                errors.append(f"form_transfer_stage_unknown: {f.code}:{f.design_transfer_stage}")
        for a in f.aliases:
            if not a.source_url:
                errors.append(f"alias_without_source: {f.code}:{a.term}")
        if f.review_status is ReviewStatus.verified and not f.source_url:
            errors.append(f"verified_without_source: form:{f.code}")

    for p in obj.parties:
        errors += _label_errors(f"party:{p.code}", p.name_key, p.labels, source)
        if p.contract_party_role not in party_roles:
            errors.append(f"party_role_unknown: {p.code}:{p.contract_party_role}")

    for c in obj.risk_categories:
        errors += _label_errors(f"risk_category:{c.code}", c.name_key, c.labels, source)
        if c.register_category not in register:
            errors.append(f"register_category_unknown: {c.code}:{c.register_category}")
    # Rule 6 reads these attributes; a catalogue without them would lose the rule without a word.
    concerns = {c.concerns for c in obj.risk_categories}
    sides = {p.side for p in obj.parties}
    if "design" not in concerns:
        errors.append("risk_concern_missing: design")
    if any("operate" in f.scope_extends for f in obj.forms) and "operation" not in concerns:
        errors.append("risk_concern_missing: operation")
    errors += [f"party_side_missing: {side}" for side in ("owner", "contractor") if side not in sides]
    if "operation" in concerns and "operator" not in sides:
        errors.append("party_side_missing: operator")

    seen_pairs: set[tuple[str, str]] = set()
    for a in obj.default_allocations:
        where = f"{a.risk_category}:{a.party}"
        if a.risk_category not in cats:
            errors.append(f"allocation_category_unknown: {where}")
        if a.party not in parties:
            errors.append(f"allocation_party_unknown: {where}")
        if a.basis not in ALLOCATION_BASES:
            errors.append(f"allocation_basis_unknown: {where}:{a.basis}")
        for fc in a.forms:
            if fc not in forms:
                errors.append(f"allocation_form_unknown: {where}:{fc}")
            if (fc, a.risk_category) in seen_pairs:
                errors.append(f"allocation_duplicate: {fc}:{a.risk_category}")
            seen_pairs.add((fc, a.risk_category))
        errors += [f"allocation_{e}: {where}" for e in share_errors(a.party, a.shares, set(parties))]
        if a.party == SHARED_PARTY and a.basis not in SHARED_BASES:
            errors.append(f"allocation_shared_needs_basis: {where}")

    total = Decimal("0")
    for c in obj.criteria:
        errors += _label_errors(f"criterion:{c.code}", c.name_key, c.labels, source)
        w = _decimal(c.default_weight)
        if w is None or w < 0:
            errors.append(f"criterion_weight_invalid: {c.code}")
        else:
            total += w
        for fc, score in c.scores.items():
            if fc not in forms:
                errors.append(f"criterion_form_unknown: {c.code}:{fc}")
            if not 1 <= int(score) <= 5:
                errors.append(f"criterion_score_out_of_range: {c.code}:{fc}")
    if obj.criteria and total != Decimal("100"):
        errors.append("criteria_weights_not_100")

    for r in obj.country_rules:
        errors += _label_errors(f"country_rule:{r.code}", r.name_key, r.labels, source)
        if r.review_status is ReviewStatus.verified and not r.source_url:
            errors.append(f"verified_without_source: country_rule:{r.code}")

    for t in obj.package_templates:
        if t.form not in forms:
            errors.append(f"template_form_unknown: {t.form}")
        codes = [p.code for p in t.packages]
        errors += [f"template_duplicate_package: {t.form}:{c}" for c in _dupes(codes)]
        for p in t.packages:
            if p.kind not in PACKAGE_KINDS:
                errors.append(f"template_kind_unknown: {t.form}:{p.code}")
            if p.party not in parties:
                errors.append(f"template_party_unknown: {t.form}:{p.code}")
            if p.price_basis and p.price_basis not in PRICE_BASES:
                errors.append(f"template_price_basis_unknown: {t.form}:{p.code}")
            if p.parent and p.parent not in codes:
                errors.append(f"template_parent_unknown: {t.form}:{p.code}")
            if source == "shipped" and not p.title_key.startswith(I18N_PREFIX):
                errors.append(f"shipped_label_not_i18n_key: template:{t.form}:{p.code}")

    for fl in obj.flags:
        errors += _label_errors(f"flag:{fl.code}", fl.name_key, fl.labels, source)
        errors += [f"alias_without_source: flag:{fl.code}:{a.term}" for a in fl.aliases if not a.source_url]
    return errors


def share_errors(party: str, shares: dict[str, str] | None, parties: set[str] | None = None) -> list[str]:
    """SPEC rule 4: a ``shared`` holder needs shares of named parties summing to exactly 100."""
    if party != SHARED_PARTY:
        return ["shares_without_shared_party"] if shares else []
    if not shares or len(shares) < 2:
        return ["shared_needs_two_parties"]
    total = Decimal("0")
    for p, pct in shares.items():
        if p == SHARED_PARTY or (parties is not None and p not in parties):
            return ["share_party_unknown"]
        value = _decimal(pct)
        if value is None or value <= 0:
            return ["share_invalid"]
        total += value
    return [] if total == Decimal("100") else ["shares_not_100"]


def register_kinds() -> None:
    """Register the kind with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=DELIVERY_FORMS_KIND,
            model=DeliveryFormsCatalogue,
            validator=validate_delivery_forms,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=(
                "forms",
                "parties",
                "risk_categories",
                "default_allocations",
                "criteria",
                "package_templates",
                "country_rules",
                "flags",
            ),
        )
    )
