# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The two catalogue kinds of design management: numbering schemes and design reports.

Both are data, not code. Shipped JSON lives in ``catalogues/<kind>/``; tenant
drafts and published versions live in the shared governance catalogue tables
and go through module 1's one resolver (``project_governance.catalogue_store``).

``drawing_numbering``: the fields of a drawing number in order, each with a
regex, an optional code list, the place its value comes from and (for the
sequence) zero padding. Status (suitability) and revision are metadata and
never part of the number (SPEC decision 6); a scheme may only narrow the CDE
suitability codes, never add to them.

``design_reports``: the kinds of expert report and proof a design needs, the
country hints on when an independent check is likely required (shown, never
enforced, SPEC decision 13), and the ordered permit steps of each jurisdiction
profile mapped to ``review_authority`` cycle states.

Every statutory fact carries ``source_url`` or ``review_status: unconfirmed``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus

NUMBERING_KIND = "drawing_numbering"
REPORTS_KIND = "design_reports"
CATALOGUE_ROOT = Path(__file__).with_name("catalogues")
DEFAULT_SCHEME_ID = "iso19650_generic"
DEFAULT_REPORTS_ID = "default"

#: Field codes a scheme may use. ``custom_*`` adds company fields.
STANDARD_FIELDS: tuple[str, ...] = (
    "project",
    "originator",
    "functional",
    "spatial",
    "form",
    "discipline",
    "number",
    "phase",
    "sheet_size",
)
_FIELD_CODE = r"^(project|originator|functional|spatial|form|discipline|number|phase|sheet_size|custom_[a-z0-9_]+)$"

#: Where a field's value is stored on the CDE container (rule 7). Fields not
#: listed live in ``container.metadata["numbering"]["parts"]``.
CONTAINER_PART: dict[str, str] = {
    "originator": "originator_code",
    "functional": "functional_breakdown",
    "spatial": "spatial_breakdown",
    "form": "form_code",
    "discipline": "discipline_code",
    "number": "sequence_number",
}

#: Values a field may be filled from when the user does not type it.
SOURCE_FIELDS: tuple[str, ...] = (
    "project.code",
    "role.originator_code",
    "role.discipline_code",
    "drawing.phase_code",
    "drawing.sheet_size",
    "wbs.code",
    "input",
)

REPORT_KINDS_V1: tuple[str, ...] = (
    "structural_design",
    "structural_proof_check",
    "fire_safety_concept",
    "fire_proof_check",
    "acoustics",
    "thermal_energy",
    "geotechnical",
    "environmental",
    "sound_insulation",
    "vibration",
    "daylight",
    "traffic",
    "drainage",
    "kitchen_planning",
    "survey",
    "contamination",
    "uxo",
)
PERMIT_STEP_CODES: tuple[str, ...] = (
    "pre_application",
    "application",
    "completeness_check",
    "remarks",
    "approval",
    "partial_approval",
    "start_notice",
)
#: ``review_authority`` cycle states a permit step may map to.
REVIEW_CYCLE_STATES: tuple[str, ...] = (
    "draft",
    "submitted",
    "under_review",
    "remarks_issued",
    "responding",
    "resubmitted",
    "approved",
    "rejected",
    "withdrawn",
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CodeListEntry(_Frozen):
    code: str = Field(min_length=1, max_length=20)
    label_key: str = ""
    labels: dict[str, str] | None = None


class NumberingField(_Frozen):
    """One field of a drawing number."""

    code: str = Field(pattern=_FIELD_CODE, max_length=40)
    label_key: str = ""
    labels: dict[str, str] | None = None
    required: bool = True
    pattern: str | None = None
    length_min: int | None = Field(default=None, ge=1, le=40)
    length_max: int | None = Field(default=None, ge=1, le=40)
    code_list: list[CodeListEntry] | Literal["free"] = "free"
    # Zero padding of the sequence; only the ``number`` field.
    pad: int | None = Field(default=None, ge=1, le=10)
    source_field: str = "input"
    # Text written BEFORE this field; ``None`` = the scheme separator, ``""`` = none
    # (``A-101``: sheet type and sequence follow each other directly).
    joiner: str | None = None

    def codes(self) -> set[str] | None:
        return None if self.code_list == "free" else {c.code for c in self.code_list}


class MetadataField(_Frozen):
    """Status or revision: metadata of the container, never part of the number."""

    code: Literal["status", "revision"]
    # ``None`` = the CDE defaults; a list may only narrow them.
    code_list: list[str] | None = None


class DrawingNumbering(_Frozen):
    """One numbering scheme (catalogue body of kind ``drawing_numbering``)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    description_key: str = ""
    source_url: str | None = None
    source_title: str | None = None
    review_status: ReviewStatus = ReviewStatus.verified
    jurisdiction_countries: list[str] = Field(default_factory=list)
    fields: list[NumberingField] = Field(min_length=1)
    separator: str = Field(default="-", min_length=1, max_length=1)
    case: Literal["upper", "lower", "any"] = "upper"
    max_length: int = Field(default=60, ge=3, le=255)
    allowed_chars: str = r"^[A-Z0-9-]+$"
    metadata_fields: list[MetadataField] = Field(default_factory=list)
    drawing_forms: list[str] = Field(default_factory=list)
    number_scope: list[str] = Field(default_factory=list)
    #: Illustrative values per field, keyed by a neutral meaning (``architecture``, ``plan``,
    #: ``ground``). Demo data and hints read them, so no code compares a scheme id.
    examples: dict[str, dict[str, str]] = Field(default_factory=dict)

    def field(self, code: str) -> NumberingField | None:
        return next((f for f in self.fields if f.code == code), None)

    def scope_fields(self) -> list[str]:
        """Fields that together key the counter; default every field but the number."""
        if self.number_scope:
            return list(self.number_scope)
        return [f.code for f in self.fields if f.code != "number"]


class CountryRule(_Frozen):
    country: str = Field(pattern=r"^[A-Z]{2}$")
    region: str | None = None
    condition_key: str = ""
    text_key: str = ""
    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class ReportKind(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    discipline: str = ""
    typical_phase: str
    independent_check: Literal["none", "optional", "required_by_rule"] = "none"
    country_rules: list[CountryRule] = Field(default_factory=list)


class PermitStep(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    order: int = Field(ge=1)
    name_key: str = ""
    spine_key: str
    cycle_state: str | None = None
    statutory_days: int | None = Field(default=None, ge=1, le=730)
    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class PermitProfile(_Frozen):
    code: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    jurisdiction_countries: list[str] = Field(default_factory=list)
    steps: list[PermitStep] = Field(min_length=1)


class DesignReports(_Frozen):
    """One reports catalogue (body of kind ``design_reports``)."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$", max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.verified
    report_kinds: list[ReportKind] = Field(min_length=1)
    permit_steps: list[PermitProfile] = Field(default_factory=list)

    def kind(self, code: str) -> ReportKind | None:
        return next((k for k in self.report_kinds if k.code == code), None)

    def profile(self, code: str) -> PermitProfile | None:
        return next((p for p in self.permit_steps if p.code == code), None)


def _label_errors(what: str, key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped" and not key:
        return [f"label_key_missing: {what}"]
    if source != "shipped" and not key and not (labels or {}).get("en"):
        return [f"label_missing: {what}"]
    return []


def _regex_error(what: str, pattern: str | None) -> list[str]:
    if pattern is None:
        return []
    try:
        re.compile(pattern)
    except re.error:
        return [f"pattern_invalid: {what}"]
    return []


def validate_numbering(obj: DrawingNumbering, source: str) -> list[str]:
    """Cross-reference rules of a numbering scheme; an empty list means valid."""
    from app.modules.cde.suitability import SUITABILITY_CODES

    errors: list[str] = []
    errors += _label_errors("scheme", obj.name_key, obj.labels, source)
    codes = [f.code for f in obj.fields]
    if len(codes) != len(set(codes)):
        errors.append("field_duplicate")
    numbers = [f for f in obj.fields if f.code == "number"]
    if len(numbers) != 1:
        errors.append("number_field_count")
    elif numbers[0].pad is None:
        errors.append("number_field_without_pad")
    errors += _regex_error("allowed_chars", obj.allowed_chars)
    if not errors and not re.fullmatch(obj.allowed_chars, obj.separator):
        errors.append("separator_not_allowed")
    for i, f in enumerate(obj.fields):
        errors += _label_errors(f"field:{f.code}", f.label_key, f.labels, source)
        errors += _regex_error(f"field:{f.code}", f.pattern)
        if f.length_min and f.length_max and f.length_min > f.length_max:
            errors.append(f"length_range_invalid: {f.code}")
        if f.code_list != "free":
            entries = [c.code for c in f.code_list]
            if len(entries) != len(set(entries)):
                errors.append(f"code_list_duplicate: {f.code}")
            if not entries:
                errors.append(f"code_list_empty: {f.code}")
        if f.source_field not in SOURCE_FIELDS:
            errors.append(f"source_field_unknown: {f.code}")
        if f.pad is not None and f.code != "number":
            errors.append(f"pad_on_non_number: {f.code}")
        if i == 0 and f.joiner is not None:
            errors.append(f"joiner_on_first_field: {f.code}")
        if not f.required and f.joiner == "":
            errors.append(f"optional_field_without_joiner: {f.code}")
        # A field glued to the next one must have a fixed width, or the
        # number cannot be parsed back into its parts (rule 7).
        nxt = obj.fields[i + 1] if i + 1 < len(obj.fields) else None
        if nxt is not None and nxt.joiner == "" and f.code != "number" and not (f.length_min and f.length_max):
            errors.append(f"glued_field_without_length: {f.code}")
        if f.joiner and not re.fullmatch(obj.allowed_chars, f.joiner):
            errors.append(f"joiner_not_allowed: {f.code}")
    for s in obj.number_scope:
        if s not in codes or s == "number":
            errors.append(f"number_scope_unknown: {s}")
    for field_code, values in obj.examples.items():
        target = obj.field(field_code)
        if target is None:
            errors.append(f"examples_field_unknown: {field_code}")
            continue
        listed = target.codes()
        bad = sorted(v for v in values.values() if listed is not None and v not in listed)
        if bad:
            errors.append(f"examples_not_in_code_list: {field_code}: " + ",".join(bad))
    form = obj.field("form")
    if obj.drawing_forms and form is not None and form.codes() is not None:
        missing = set(obj.drawing_forms) - (form.codes() or set())
        if missing:
            errors.append("drawing_forms_not_in_form_list: " + ",".join(sorted(missing)))
    all_status = {c for entries in SUITABILITY_CODES.values() for c, _ in entries}
    for m in obj.metadata_fields:
        if m.code == "status" and m.code_list is not None and set(m.code_list) - all_status:
            errors.append("status_codes_outside_cde")
    if len({m.code for m in obj.metadata_fields}) != len(obj.metadata_fields):
        errors.append("metadata_field_duplicate")
    if obj.review_status == ReviewStatus.verified and source == "shipped" and not obj.source_url:
        errors.append("verified_without_source")
    return errors


def validate_reports(obj: DesignReports, source: str) -> list[str]:
    """Cross-reference rules of a reports catalogue; an empty list means valid."""
    from app.modules.requirements.lifecycle import PHASE_SPINE

    errors: list[str] = []
    errors += _label_errors("catalogue", obj.name_key, obj.labels, source)
    kinds = [k.code for k in obj.report_kinds]
    if len(kinds) != len(set(kinds)):
        errors.append("report_kind_duplicate")
    for k in obj.report_kinds:
        errors += _label_errors(f"kind:{k.code}", k.name_key, k.labels, source)
        if k.typical_phase not in PHASE_SPINE:
            errors.append(f"typical_phase_unknown: {k.code}")
        for r in k.country_rules:
            if r.review_status == ReviewStatus.verified and not r.source_url:
                errors.append(f"country_rule_without_source: {k.code}:{r.country}")
    profiles = [p.code for p in obj.permit_steps]
    if len(profiles) != len(set(profiles)):
        errors.append("permit_profile_duplicate")
    for p in obj.permit_steps:
        steps = [s.code for s in p.steps]
        if len(steps) != len(set(steps)):
            errors.append(f"permit_step_duplicate: {p.code}")
        orders = [s.order for s in p.steps]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            errors.append(f"permit_step_order: {p.code}")
        for s in p.steps:
            if s.spine_key not in PHASE_SPINE:
                errors.append(f"permit_step_spine_unknown: {p.code}:{s.code}")
            if s.cycle_state is not None and s.cycle_state not in REVIEW_CYCLE_STATES:
                errors.append(f"permit_step_cycle_state_unknown: {p.code}:{s.code}")
            if s.statutory_days is not None and s.review_status == ReviewStatus.verified and not s.source_url:
                errors.append(f"permit_step_deadline_without_source: {p.code}:{s.code}")
    return errors


def register_kinds() -> None:
    """Register both kinds with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=NUMBERING_KIND,
            model=DrawingNumbering,
            validator=validate_numbering,
            shipped_dir=CATALOGUE_ROOT / NUMBERING_KIND,
            diff_groups=("fields", "metadata_fields"),
        )
    )
    register_catalogue_kind(
        CatalogueKind(
            kind=REPORTS_KIND,
            model=DesignReports,
            validator=validate_reports,
            shipped_dir=CATALOGUE_ROOT / REPORTS_KIND,
            diff_groups=("report_kinds", "permit_steps"),
        )
    )
