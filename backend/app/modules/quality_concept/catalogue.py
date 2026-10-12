# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``quality_concept``: the reference data a quality concept is built from.

One body holds standard families, quality requirement categories,
certification schemes, evidence types, material test plans, commissioning
stages (levels as data), acceptance regimes with their legal effects,
documentation sets and evidence-preservation subjects. Shipped JSON lives in
``catalogues/``; a company clones and publishes its own through module 1's
catalogue store, and a project pins ``(source, id, version)``.

Every statutory or scheme fact carries ``source_url`` and ``review_status``.
A threshold or frequency that was not read in the primary text ships
``unconfirmed`` and the screens show a badge next to it. Third-party scheme
content is codes and category names only; criteria texts are licensed and
never shipped.

The validator checks every reference into another module against that
module's own vocabulary: verification methods (requirements), hold gate party
roles (construction_control), limitation regimes (defects_liability) and
closeout slot keys (closeout). A catalogue cannot name a word the platform
does not know.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_governance.catalogue import ReviewStatus
from app.modules.quality_concept import vocab

QUALITY_CONCEPT_KIND = "quality_concept"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"
I18N_PREFIX = "quality_concept.catalogue."

_CODE = r"^[a-z0-9][a-z0-9_]*$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(_Frozen):
    """Where a fact comes from and whether it was checked there."""

    source_url: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class StandardFamily(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    discipline: str = Field(default="general", max_length=40)
    # Open strings ("EN 206", "ACI 318"): reference only, never an enum on evidence rows.
    examples: list[str] = Field(default_factory=list)


class RequirementCategory(_Frozen):
    code: str = Field(pattern=r"^quality\.[a-z0-9_]+$", max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    verification_method: str


class CertificationLevel(Sourced):
    code: str = Field(pattern=_CODE, max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    # Decimal string, compared as Decimal; null for a scheme without a score floor.
    min_score: str | None = None
    score_unit: str = "percent"


class CertificationScheme(Sourced):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    scope: str
    versions: list[str] = Field(default_factory=list)
    levels: list[CertificationLevel] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=lambda: list(vocab.CERTIFICATION_PHASES))
    credit_categories: list[str] = Field(default_factory=list)


class EvidenceType(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    name_key: str = ""
    labels: dict[str, str] | None = None
    kind: str
    fulfilled_by: list[str] = Field(min_length=1)
    default_deliverer: str


class TestFrequency(_Frozen):
    # Decimal string: one test per ``per_quantity`` ``unit`` placed.
    per_quantity: str
    unit: str = Field(max_length=20)
    min_per_period: int | None = Field(default=None, ge=1)
    period: str | None = None


class MaterialTestPlan(Sourced):
    code: str = Field(pattern=_CODE, max_length=64)
    material_family: str
    evidence_type: str
    test_method: str = ""
    frequency: TestFrequency | None = None
    per_lot: bool = False


class Precondition(_Frozen):
    code: str
    params: dict[str, Any] = Field(default_factory=dict)


class StageAlias(Sourced):
    context: str = Field(max_length=64)
    term: str = Field(max_length=120)


class CommissioningStage(_Frozen):
    code: str = Field(pattern=_CODE, max_length=40)
    order: int = Field(ge=0)
    name_key: str = ""
    description_key: str = ""
    labels: dict[str, str] | None = None
    default_owner_role: str = "contractor"
    default_release_party: str
    default_preconditions: list[Precondition] = Field(default_factory=list)
    evidence_types: list[str] = Field(default_factory=list)
    aliases: list[StageAlias] = Field(default_factory=list)


class DeemedAcceptance(Sourced):
    trigger: str
    working_days: int | None = Field(default=None, ge=1)
    # A period counted in calendar days (FIDIC); exclusive with ``working_days``.
    calendar_days: int | None = Field(default=None, ge=1)
    # Weekdays that never count toward ``working_days``, Monday is 0.
    rest_weekdays: list[int] = Field(default_factory=lambda: [6])
    reasonable_period: bool = False
    consumer_notice_required: bool = False
    # Saturdays count as working days (German ``Werktage``) unless the regime says otherwise.
    saturday_is_working_day: bool = True


class LegalEffect(Sourced):
    effect: str
    detail_key: str = ""
    value: str | None = None


class AcceptanceRegime(Sourced):
    code: str = Field(pattern=_CODE, max_length=40)
    country_code: str | None = Field(default=None, max_length=8)
    contract_basis: str
    name_key: str = ""
    act_name: str = Field(max_length=120)
    partial_allowed: bool = False
    partial_term: str = ""
    refusal_threshold: str = ""
    # Precondition kinds a unit may still be requested with, each listed as a reservation (rule 13).
    reservable: list[str] = Field(default_factory=list)
    # Codes of facts in this entry nobody has checked against the source yet, shown with the regime.
    unconfirmed_facts: list[str] = Field(default_factory=list)
    refusal_needs_defect: bool = False
    deemed_acceptance: list[DeemedAcceptance] = Field(default_factory=list)
    effects: list[LegalEffect] = Field(default_factory=list)
    limitation_regime_code: str | None = None


class FmDataDefault(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    deliverable_type: str
    loi: str = ""
    name_key: str = ""


class DocumentationSet(_Frozen):
    code: str = Field(pattern=_CODE, max_length=40)
    name_key: str = ""
    labels: dict[str, str] | None = None
    closeout_template: str | None = None
    slot_keys: list[str] = Field(default_factory=list)
    fm_data: list[FmDataDefault] = Field(default_factory=list)


class PreservationSubject(_Frozen):
    code: str
    name_key: str = ""
    influence_triggers: list[str] = Field(default_factory=list)
    survey_methods: list[str] = Field(default_factory=list)


class QualityConceptCatalogue(Sourced):
    """One shipped or tenant catalogue body of kind ``quality_concept``."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    jurisdiction_countries: list[str] = Field(default_factory=list)
    standard_families: list[StandardFamily] = Field(default_factory=list)
    requirement_categories: list[RequirementCategory] = Field(default_factory=list)
    certification_schemes: list[CertificationScheme] = Field(default_factory=list)
    evidence_types: list[EvidenceType] = Field(default_factory=list)
    material_test_plans: list[MaterialTestPlan] = Field(default_factory=list)
    commissioning_stages: list[CommissioningStage] = Field(default_factory=list)
    acceptance_regimes: list[AcceptanceRegime] = Field(default_factory=list)
    documentation_sets: list[DocumentationSet] = Field(default_factory=list)
    preservation_subjects: list[PreservationSubject] = Field(default_factory=list)

    # ── lookups ─────────────────────────────────────────────────────────────

    def evidence_type(self, code: str) -> EvidenceType | None:
        return next((e for e in self.evidence_types if e.code == code), None)

    def regime(self, code: str | None) -> AcceptanceRegime | None:
        return next((r for r in self.acceptance_regimes if r.code == code), None)

    def scheme(self, code: str) -> CertificationScheme | None:
        return next((s for s in self.certification_schemes if s.code == code), None)

    def documentation_set(self, code: str | None) -> DocumentationSet | None:
        return next((d for d in self.documentation_sets if d.code == code), None)

    def test_plan_for(self, evidence_type: str) -> MaterialTestPlan | None:
        return next((p for p in self.material_test_plans if p.evidence_type == evidence_type), None)


def known_closeout_slot_keys() -> frozenset[str]:
    """Every slot key closeout defines: its templates plus the extra slots quality concepts seed."""
    from app.modules.closeout.checklist_templates import CHECKLIST_TEMPLATES, EXTRA_SLOT_DEFS

    keys = {slot["slot_key"] for slots in CHECKLIST_TEMPLATES.values() for slot in slots}
    keys.update(slot["slot_key"] for slot in EXTRA_SLOT_DEFS)
    return frozenset(keys)


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c in seen and c not in out:
            out.append(c)
        seen.add(c)
    return out


def _check_sourced(errors: list[str], where: str, item: Sourced) -> None:
    if item.review_status is ReviewStatus.verified and not item.source_url:
        errors.append(f"{where}: verified without source_url")


def validate_quality_catalogue(cat: QualityConceptCatalogue, source: str = "shipped") -> list[str]:
    """Cross-reference rules; every error is one human readable line."""
    from pydantic import ValidationError

    from app.modules.defects_liability.limitation import ALL_LIMITATION_REGIMES
    from app.modules.requirements.schemas import DeliverableCreate

    errors: list[str] = []
    groups: dict[str, list[str]] = {
        "standard_families": [s.code for s in cat.standard_families],
        "requirement_categories": [c.code for c in cat.requirement_categories],
        "certification_schemes": [s.code for s in cat.certification_schemes],
        "evidence_types": [e.code for e in cat.evidence_types],
        "material_test_plans": [p.code for p in cat.material_test_plans],
        "commissioning_stages": [s.code for s in cat.commissioning_stages],
        "acceptance_regimes": [r.code for r in cat.acceptance_regimes],
        "documentation_sets": [d.code for d in cat.documentation_sets],
        "preservation_subjects": [p.code for p in cat.preservation_subjects],
    }
    for group, codes in groups.items():
        for dup in _dupes(codes):
            errors.append(f"{group}: duplicate code {dup!r}")
    _check_sourced(errors, "catalogue", cat)

    for c in cat.requirement_categories:
        if c.verification_method not in vocab.VERIFICATION_METHODS:
            errors.append(f"requirement_categories.{c.code}: unknown verification_method {c.verification_method!r}")

    for s in cat.certification_schemes:
        _check_sourced(errors, f"certification_schemes.{s.code}", s)
        if s.scope not in vocab.CERTIFICATION_SCOPES:
            errors.append(f"certification_schemes.{s.code}: unknown scope {s.scope!r}")
        for ph in s.phases:
            if ph not in vocab.CERTIFICATION_PHASES:
                errors.append(f"certification_schemes.{s.code}: unknown phase {ph!r}")
        for dup in _dupes([lv.code for lv in s.levels]):
            errors.append(f"certification_schemes.{s.code}: duplicate level {dup!r}")
        previous = None
        for lv in s.levels:
            _check_sourced(errors, f"certification_schemes.{s.code}.{lv.code}", lv)
            if lv.score_unit not in vocab.SCORE_UNITS:
                errors.append(f"certification_schemes.{s.code}.{lv.code}: unknown score_unit {lv.score_unit!r}")
            if lv.min_score is not None:
                try:
                    value = _decimal(lv.min_score)
                except ValueError:
                    errors.append(f"certification_schemes.{s.code}.{lv.code}: min_score is not a decimal")
                    continue
                if previous is not None and value <= previous:
                    errors.append(f"certification_schemes.{s.code}: levels must ascend by min_score")
                previous = value

    evidence_codes = set(groups["evidence_types"])
    for e in cat.evidence_types:
        if e.kind not in vocab.EVIDENCE_KINDS:
            errors.append(f"evidence_types.{e.code}: unknown kind {e.kind!r}")
        if e.default_deliverer not in vocab.DELIVERER_ROLES:
            errors.append(f"evidence_types.{e.code}: unknown default_deliverer {e.default_deliverer!r}")
        for lk in e.fulfilled_by:
            if lk not in vocab.LINK_KINDS:
                errors.append(f"evidence_types.{e.code}: unknown link kind {lk!r} in fulfilled_by")

    for p in cat.material_test_plans:
        _check_sourced(errors, f"material_test_plans.{p.code}", p)
        if p.material_family not in vocab.MATERIAL_FAMILIES:
            errors.append(f"material_test_plans.{p.code}: unknown material_family {p.material_family!r}")
        if p.evidence_type not in evidence_codes:
            errors.append(f"material_test_plans.{p.code}: unknown evidence_type {p.evidence_type!r}")
        if [q.evidence_type for q in cat.material_test_plans].count(p.evidence_type) > 1:
            # ``test_plan_for`` answers one plan per evidence type; a second one would never be read.
            errors.append(f"material_test_plans.{p.code}: evidence_type {p.evidence_type!r} has another plan")
        if p.frequency is None and not p.per_lot:
            errors.append(f"material_test_plans.{p.code}: needs a frequency or per_lot")
        if p.frequency is not None:
            try:
                if _decimal(p.frequency.per_quantity) <= 0:
                    raise ValueError
            except ValueError:
                errors.append(f"material_test_plans.{p.code}: per_quantity must be a positive decimal")

    stage_codes = set(groups["commissioning_stages"])
    for dup in _dupes([str(s.order) for s in cat.commissioning_stages]):
        errors.append(f"commissioning_stages: duplicate order {dup}")
    for s in cat.commissioning_stages:
        if s.default_release_party not in vocab.PARTY_ROLES:
            errors.append(f"commissioning_stages.{s.code}: release party {s.default_release_party!r} not a gate role")
        if s.default_owner_role not in vocab.DELIVERER_ROLES:
            errors.append(f"commissioning_stages.{s.code}: unknown default_owner_role {s.default_owner_role!r}")
        for pre in s.default_preconditions:
            if pre.code not in vocab.PREDICATES:
                errors.append(f"commissioning_stages.{s.code}: unknown precondition {pre.code!r}")
            for et in pre.params.get("evidence_types", []) or []:
                if et not in evidence_codes:
                    errors.append(f"commissioning_stages.{s.code}: precondition names unknown evidence type {et!r}")
            stage_ref = pre.params.get("stage")
            if stage_ref is not None and stage_ref not in stage_codes:
                errors.append(f"commissioning_stages.{s.code}: precondition names unknown stage {stage_ref!r}")
        for et in s.evidence_types:
            if et not in evidence_codes:
                errors.append(f"commissioning_stages.{s.code}: unknown evidence type {et!r}")
        for alias in s.aliases:
            _check_sourced(errors, f"commissioning_stages.{s.code}.alias", alias)

    for r in cat.acceptance_regimes:
        _check_sourced(errors, f"acceptance_regimes.{r.code}", r)
        if r.contract_basis not in vocab.CONTRACT_BASES:
            errors.append(f"acceptance_regimes.{r.code}: unknown contract_basis {r.contract_basis!r}")
        if r.limitation_regime_code is not None and r.limitation_regime_code not in ALL_LIMITATION_REGIMES:
            errors.append(f"acceptance_regimes.{r.code}: unknown limitation regime {r.limitation_regime_code!r}")
        for d in r.deemed_acceptance:
            if d.trigger not in vocab.DEEMED_TRIGGERS:
                errors.append(f"acceptance_regimes.{r.code}: unknown deemed trigger {d.trigger!r}")
            if not d.source_url:
                errors.append(f"acceptance_regimes.{r.code}: deemed acceptance {d.trigger} without source_url")
            if d.working_days is None and d.calendar_days is None and not d.reasonable_period:
                errors.append(
                    f"acceptance_regimes.{r.code}: deemed {d.trigger} needs working_days, calendar_days"
                    " or a reasonable period"
                )
            if d.working_days is not None and d.calendar_days is not None:
                errors.append(
                    f"acceptance_regimes.{r.code}: deemed {d.trigger} counts working_days or calendar_days, not both"
                )
            if any(w not in range(7) for w in d.rest_weekdays) or len(set(d.rest_weekdays)) >= 7:
                errors.append(f"acceptance_regimes.{r.code}: deemed {d.trigger} has invalid rest_weekdays")
        for eff in r.effects:
            if eff.effect not in vocab.LEGAL_EFFECTS:
                errors.append(f"acceptance_regimes.{r.code}: unknown effect {eff.effect!r}")
            if not eff.source_url:
                errors.append(f"acceptance_regimes.{r.code}: effect {eff.effect} without source_url")
        for dup in _dupes([e.effect for e in r.effects]):
            errors.append(f"acceptance_regimes.{r.code}: effect {dup!r} twice")
        # A warranty effect without ``limitation_regime_code`` is allowed: it then proposes a
        # warranty start without a statutory regime (standard forms under common law).
        for reservable in r.reservable:
            if reservable not in ("stage", "proofs", "documentation", "defects"):
                errors.append(f"acceptance_regimes.{r.code}: unknown reservable kind {reservable!r}")

    slot_keys = known_closeout_slot_keys()
    for d in cat.documentation_sets:
        for key in d.slot_keys:
            if key not in slot_keys:
                errors.append(f"documentation_sets.{d.code}: unknown closeout slot key {key!r}")
        for fm in d.fm_data:
            if fm.deliverable_type not in vocab.FM_DELIVERABLE_TYPES:
                errors.append(
                    f"documentation_sets.{d.code}.{fm.code}: unknown deliverable_type {fm.deliverable_type!r}"
                )
                continue
            # The default becomes a requirement deliverable, so it must be one that module accepts.
            try:
                DeliverableCreate(deliverable_type=fm.deliverable_type, loi=fm.loi or None)
            except ValidationError:
                errors.append(
                    f"documentation_sets.{d.code}.{fm.code}: loi {fm.loi!r} is not a level a deliverable accepts"
                )

    for p in cat.preservation_subjects:
        if p.code not in vocab.PRESERVATION_SUBJECTS:
            errors.append(f"preservation_subjects: unknown subject {p.code!r}")
        for t in p.influence_triggers:
            if t not in vocab.INFLUENCE_TRIGGERS:
                errors.append(f"preservation_subjects.{p.code}: unknown trigger {t!r}")
        for m in p.survey_methods:
            if m not in vocab.SURVEY_METHODS:
                errors.append(f"preservation_subjects.{p.code}: unknown survey method {m!r}")
    return errors


def _decimal(value: str) -> Any:
    from decimal import Decimal, InvalidOperation

    try:
        out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(value) from exc
    if not out.is_finite():
        raise ValueError(value)
    return out


def register_kinds() -> None:
    """Register kind ``quality_concept`` with module 1's catalogue registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=QUALITY_CONCEPT_KIND,
            model=QualityConceptCatalogue,
            validator=validate_quality_catalogue,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=(
                "standard_families",
                "requirement_categories",
                "certification_schemes",
                "evidence_types",
                "material_test_plans",
                "commissioning_stages",
                "acceptance_regimes",
                "documentation_sets",
                "preservation_subjects",
            ),
        )
    )


def shipped_catalogue(catalogue_id: str = DEFAULT_CATALOGUE_ID, version: int | None = None) -> QualityConceptCatalogue:
    """A shipped catalogue of this kind (registers the kind on first use)."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kinds()
    return get_catalogue_kind(QUALITY_CONCEPT_KIND).get_shipped(catalogue_id, version)
