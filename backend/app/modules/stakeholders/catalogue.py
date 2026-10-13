# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``stakeholder_framework``: everything configurable about stakeholders and mandates.

One framework body carries the stakeholder categories, the analysis methods
(dimensions and a classification rule as data), participation levels, channels,
participation formats with their statutory references, project roles, body
types, decision types and the default mandate template. Shipped JSON lives in
``catalogues/``; tenant drafts and published versions live in module 1's shared
catalogue tables and resolve through ``project_governance.catalogue_store``.

Classification is a first-match rule list over the method's dimensions, so a
new method is data, never a new code path (SPEC section 2, decision e). Every
statutory reference carries ``url`` and ``review_status``; the module shows the
reference and never claims compliance (decision o).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.project_governance.catalogue import ReviewStatus

FRAMEWORK_KIND = "stakeholder_framework"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_FRAMEWORK_ID = "neutral"
MANDATE_LETTERS: tuple[str, ...] = ("P", "D", "A", "C", "I")
_CODE = r"^[a-z0-9][a-z0-9_]*$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None


class StatutoryRef(_Frozen):
    """A statute or guideline a format refers to. Never a compliance claim."""

    jurisdiction: str = Field(min_length=2, max_length=8)
    ref: str = Field(min_length=1, max_length=200)
    url: str = Field(pattern=r"^https?://")
    review_status: ReviewStatus


class Category(_Labelled):
    kind: Literal["internal", "external"]
    # Private persons (neighbours, the public): confidential by default (rule 17).
    private_person: bool = False


class Dimension(_Labelled):
    """One axis of an analysis method. ``bool`` dimensions ignore ``min`` / ``max``."""

    type: Literal["int", "bool"] = "int"
    min: int = 0
    max: int = 0

    @model_validator(mode="after")
    def _range(self) -> Dimension:
        if self.type == "int" and self.min > self.max:
            raise ValueError(f"dimension {self.code}: min > max")
        return self


class Condition(_Frozen):
    """``gte`` / ``lte`` for an int dimension, ``eq`` for a bool one."""

    gte: int | None = None
    lte: int | None = None
    eq: bool | None = None


class ClassRule(_Frozen):
    when: dict[str, Condition] = Field(default_factory=dict)
    classification: str = Field(pattern=_CODE, max_length=64)


class AnalysisMethod(_Labelled):
    version: int = Field(default=1, ge=1)
    dimensions: tuple[Dimension, ...]
    classes: tuple[_Labelled, ...] = ()
    # First match wins; no match gives ``default`` (``None``: unclassified).
    rules: tuple[ClassRule, ...] = ()
    default: str | None = None
    source_url: str | None = None


class ParticipationLevel(_Labelled):
    order: int = Field(ge=0)
    promise_key: str = ""


class EngagementLevel(_Labelled):
    order: int = Field(ge=0)


class ParticipationFormat(_Labelled):
    default_level: str
    default_channels: tuple[str, ...] = ()
    statutory_refs: tuple[StatutoryRef, ...] = ()


class Role(_Labelled):
    holder_kind: Literal["person", "organisation"] = "person"
    multi: bool = False
    # A required role with no valid holder blocks ``roles_filled`` (rule 20).
    required: bool = False


class BodyType(_Labelled):
    default_decision_level: int = Field(default=1, ge=1)


class DecisionType(_Labelled):
    # Key into module 2's authority schedule (``works``, ``change`` ...); amounts live there.
    commitment_type: str | None = None
    # The approval_routes kind that executes this decision, if any.
    approval_target_kind: str | None = None
    required: bool = False
    forbid_self_approval: bool = False


class MandateTemplateRow(_Frozen):
    decision_type: str
    holder_kind: Literal["role", "body"]
    holder_code: str
    letter: Literal["P", "D", "A", "C", "I"]


class StakeholderFramework(_Frozen):
    """One ``stakeholder_framework`` catalogue body."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    source_url: str | None = None
    jurisdiction_countries: tuple[str, ...] = ()
    default_method: str = "power_interest"
    # Days after ``held_on`` within which feedback must be reported (rule 8).
    feedback_due_days: int = Field(default=30, ge=1, le=365)
    # Lowest participation level that promises feedback (IAP2: consult).
    feedback_from_level: str = "consult"
    stakeholder_categories: tuple[Category, ...]
    analysis_methods: tuple[AnalysisMethod, ...]
    engagement_levels: tuple[EngagementLevel, ...]
    participation_levels: tuple[ParticipationLevel, ...]
    channels: tuple[_Labelled, ...]
    participation_formats: tuple[ParticipationFormat, ...] = ()
    roles: tuple[Role, ...] = ()
    body_types: tuple[BodyType, ...] = ()
    decision_types: tuple[DecisionType, ...] = ()
    mandate_template: tuple[MandateTemplateRow, ...] = ()

    # lookups used by the service and the rules

    def category(self, code: str) -> Category | None:
        return next((c for c in self.stakeholder_categories if c.code == code), None)

    def method(self, code: str) -> AnalysisMethod | None:
        return next((m for m in self.analysis_methods if m.code == code), None)

    def decision_type(self, code: str) -> DecisionType | None:
        return next((d for d in self.decision_types if d.code == code), None)

    def role(self, code: str) -> Role | None:
        return next((r for r in self.roles if r.code == code), None)

    def level_order(self) -> dict[str, int]:
        return {p.code: p.order for p in self.participation_levels}

    def engagement_order(self) -> dict[str, int]:
        return {e.code: e.order for e in self.engagement_levels}

    def format(self, code: str) -> ParticipationFormat | None:
        return next((f for f in self.participation_formats if f.code == code), None)


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    return sorted({c for c in codes if c in seen or seen.add(c)})  # type: ignore[func-returns-value]


def validate_framework(fw: StakeholderFramework, source: str = "shipped") -> list[str]:
    """Cross-reference rules a schema cannot express. Empty list = valid.

    ``framework_scales_valid`` (SPEC section 7) runs this on tenant drafts.
    Shipped bodies must also carry an i18n key on every item, tenant bodies
    may carry ``labels`` instead.
    """
    errors: list[str] = []
    groups: dict[str, tuple[Any, ...]] = {
        "stakeholder_categories": fw.stakeholder_categories,
        "analysis_methods": fw.analysis_methods,
        "engagement_levels": fw.engagement_levels,
        "participation_levels": fw.participation_levels,
        "channels": fw.channels,
        "participation_formats": fw.participation_formats,
        "roles": fw.roles,
        "body_types": fw.body_types,
        "decision_types": fw.decision_types,
    }
    for group, items in groups.items():
        for d in _dupes([i.code for i in items]):
            errors.append(f"{group}: duplicate code {d}")
        if source == "shipped":
            for i in items:
                if not i.name_key and not i.labels:
                    errors.append(f"{group}.{i.code}: no name_key")
    if not fw.stakeholder_categories:
        errors.append("stakeholder_categories: empty")
    if fw.method(fw.default_method) is None:
        errors.append(f"default_method {fw.default_method} is not a method")
    for m in fw.analysis_methods:
        dims = {d.code: d for d in m.dimensions}
        classes = {c.code for c in m.classes}
        for d in _dupes(list(dims)):
            errors.append(f"method {m.code}: duplicate dimension {d}")
        targets = [r.classification for r in m.rules] + ([m.default] if m.default else [])
        for t in targets:
            if t not in classes:
                errors.append(f"method {m.code}: class {t} not declared")
        for r in m.rules:
            for dim_code, cond in r.when.items():
                dim = dims.get(dim_code)
                if dim is None:
                    errors.append(f"method {m.code}: rule names unknown dimension {dim_code}")
                    continue
                if dim.type == "bool" and (cond.eq is None or cond.gte is not None or cond.lte is not None):
                    errors.append(f"method {m.code}: bool dimension {dim_code} needs eq only")
                if dim.type == "int" and (cond.eq is not None or (cond.gte is None and cond.lte is None)):
                    errors.append(f"method {m.code}: int dimension {dim_code} needs gte or lte")
                for bound in (cond.gte, cond.lte):
                    if dim.type == "int" and bound is not None and not dim.min <= bound <= dim.max:
                        errors.append(f"method {m.code}: bound {bound} outside {dim_code} scale")
    for group, items in (
        ("participation_levels", fw.participation_levels),
        ("engagement_levels", fw.engagement_levels),
    ):
        for d in _dupes([str(i.order) for i in items]):
            errors.append(f"{group}: duplicate order {d}")
    levels = fw.level_order()
    if fw.feedback_from_level not in levels:
        errors.append(f"feedback_from_level {fw.feedback_from_level} is not a level")
    channels = {c.code for c in fw.channels}
    for f in fw.participation_formats:
        if f.default_level not in levels:
            errors.append(f"format {f.code}: unknown level {f.default_level}")
        for ch in f.default_channels:
            if ch not in channels:
                errors.append(f"format {f.code}: unknown channel {ch}")
    roles = {r.code for r in fw.roles}
    bodies = {b.code for b in fw.body_types}
    decisions = {d.code for d in fw.decision_types}
    deciders: dict[str, int] = {}
    for row in fw.mandate_template:
        if row.decision_type not in decisions:
            errors.append(f"mandate_template: unknown decision type {row.decision_type}")
        pool = roles if row.holder_kind == "role" else bodies
        if row.holder_code not in pool:
            errors.append(f"mandate_template: unknown {row.holder_kind} {row.holder_code}")
        if row.letter == "D":
            deciders[row.decision_type] = deciders.get(row.decision_type, 0) + 1
    for dt, n in sorted(deciders.items()):
        if n > 1:
            errors.append(f"mandate_template: {n} deciders for {dt}")
    for dt in fw.decision_types:
        if dt.required and dt.code not in deciders:
            errors.append(f"mandate_template: required decision type {dt.code} has no decider")
    return errors


def list_frameworks() -> tuple[StakeholderFramework, ...]:
    """Every shipped framework, validated (through the registered kind)."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    return get_catalogue_kind(FRAMEWORK_KIND).shipped()


def register_kind() -> None:
    """Register ``stakeholder_framework`` with module 1's catalogue registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=FRAMEWORK_KIND,
            model=StakeholderFramework,
            validator=validate_framework,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=(
                "stakeholder_categories",
                "analysis_methods",
                "engagement_levels",
                "participation_levels",
                "channels",
                "participation_formats",
                "roles",
                "body_types",
                "decision_types",
                "mandate_template",
            ),
        )
    )


def default_framework_pin(country_code: str | None) -> tuple[str, str, int | None]:
    """``(source, id, version)`` a new project pins when the caller names no framework.

    The governance port is the only place that knows which catalogue a country
    gets: the active pack, the regional packs, then the one shipped framework
    that claims the country. This module has no country rule of its own. When
    the port has no answer the neutral framework is pinned at its latest
    version.
    """
    from app.modules.project_governance.public import default_catalogue_pin

    register_kind()
    pin = default_catalogue_pin(FRAMEWORK_KIND, country_code)
    if pin is not None:
        return pin.source, pin.catalogue_id, pin.version
    return "shipped", DEFAULT_FRAMEWORK_ID, None
