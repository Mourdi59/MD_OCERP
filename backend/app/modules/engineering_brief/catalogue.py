# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``engineering_brief_model``: requirement categories, concept topics, programme kinds,
milestone kinds and the backward-planned milestone template.

Data, not code. Shipped JSON lives in ``catalogues/``; tenant drafts and published versions live in the
shared governance catalogue tables and go through the one resolver
(``project_governance.catalogue_store``). This module adds the body model, its validator and the
registration call.

The template is a chain: each template milestone names the one it must precede and how many calendar
days before it. Exactly one template milestone has no successor and is of an anchor kind: the operating
proof the schedule is planned backwards from. The lead times in shipped files are starting points a
project edits, each with its review status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.project_governance.catalogue import ReviewStatus

ENGINEERING_BRIEF_KIND = "engineering_brief_model"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"
I18N_PREFIX = "engineering_brief."

# What a milestone kind may do. Platform vocabulary, closed: the screens and rules branch on it.
ANCHOR_KIND = "operation_proof"
GATE_KIND = "gate"
PERMIT_KIND = "permit_decision"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    name_key: str = ""
    labels: dict[str, str] | None = None


class RequirementCategory(_Labelled):
    code: str
    # A category the brief must cover with at least one requirement before it can be submitted.
    required: bool = True
    # Suggested standard or norm reference for the category, shown as a hint; free text.
    reference: str = ""


class ConceptTopic(_Labelled):
    code: str
    required: bool = True


class ProgrammeKind(_Labelled):
    code: str
    default_unit: str


class MilestoneKind(_Labelled):
    code: str
    # The operating proof the schedule is planned backwards from. Exactly one kind is an anchor.
    anchor: bool = False
    # The kind a governance gate is written as.
    gate: bool = False


class MilestoneTemplate(_Labelled):
    code: str
    kind: str
    successor: str | None = None
    lead_days: int = 0
    review_status: ReviewStatus = ReviewStatus.unconfirmed


class EngineeringBriefCatalogue(_Labelled):
    """One catalogue body of kind ``engineering_brief_model``."""

    id: str
    version: int = 1
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    source_url: str = ""
    source_title: str = ""
    jurisdiction_countries: tuple[str, ...] = ()
    requirement_categories: tuple[RequirementCategory, ...]
    concept_topics: tuple[ConceptTopic, ...]
    programme_kinds: tuple[ProgrammeKind, ...]
    milestone_kinds: tuple[MilestoneKind, ...]
    milestone_templates: tuple[MilestoneTemplate, ...]

    def category(self, code: str | None) -> RequirementCategory | None:
        return next((c for c in self.requirement_categories if c.code == code), None)

    def topic(self, code: str | None) -> ConceptTopic | None:
        return next((t for t in self.concept_topics if t.code == code), None)

    def programme_kind(self, code: str | None) -> ProgrammeKind | None:
        return next((k for k in self.programme_kinds if k.code == code), None)

    def milestone_kind(self, code: str | None) -> MilestoneKind | None:
        return next((k for k in self.milestone_kinds if k.code == code), None)

    @property
    def anchor_kind(self) -> str | None:
        return next((k.code for k in self.milestone_kinds if k.anchor), None)

    @property
    def gate_kind(self) -> str | None:
        return next((k.code for k in self.milestone_kinds if k.gate), None)


def label_of(entry: Any, locale: str, fallback: str = "") -> str:
    """The display text of a catalogue entry: its own text for the locale, else its translated key.

    Tenant catalogues carry plain ``labels``; shipped ones carry an i18n ``name_key``.
    """
    from app.modules.engineering_brief.messages import translate

    if entry is None:
        return fallback
    labels = getattr(entry, "labels", None) or {}
    text = labels.get(locale) or labels.get(locale.split("-")[0]) or labels.get("en")
    if text:
        return text
    key = getattr(entry, "name_key", "")
    return translate(key, locale=locale) if key else (next(iter(labels.values()), "") or fallback)


def _label_errors(where: str, name_key: str, labels: dict[str, str] | None, source: str) -> list[str]:
    if source == "shipped":
        return [] if name_key.startswith(I18N_PREFIX) else [f"shipped_label_not_i18n_key: {where}"]
    if not name_key and not labels:
        return [f"label_missing: {where}"]
    return []


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: set[str] = set()
    for c in codes:
        if c in seen:
            out.add(c)
        seen.add(c)
    return sorted(out)


def _template_cycle(templates: tuple[MilestoneTemplate, ...]) -> list[str]:
    """Codes of templates that lead back to themselves through their successors."""
    succ = {t.code: t.successor for t in templates}
    bad: list[str] = []
    for code in succ:
        seen: set[str] = set()
        cur: str | None = code
        while cur is not None and cur in succ:
            if cur in seen:
                bad.append(code)
                break
            seen.add(cur)
            cur = succ[cur]
    return bad


def validate_engineering_brief_model(obj: EngineeringBriefCatalogue, source: str) -> list[str]:
    """Cross-reference rules of an engineering brief catalogue; an empty list means valid."""
    errors: list[str] = []
    errors += _label_errors("catalogue", obj.name_key, obj.labels, source)
    groups = (
        ("requirement_category", obj.requirement_categories),
        ("concept_topic", obj.concept_topics),
        ("programme_kind", obj.programme_kinds),
        ("milestone_kind", obj.milestone_kinds),
        ("milestone_template", obj.milestone_templates),
    )
    for group, entries in groups:
        errors += [f"duplicate_{group}: {c}" for c in _dupes([e.code for e in entries])]
        for e in entries:
            errors += _label_errors(f"{group}:{e.code}", e.name_key, e.labels, source)
    anchors = [k.code for k in obj.milestone_kinds if k.anchor]
    gates = [k.code for k in obj.milestone_kinds if k.gate]
    if len(anchors) != 1:
        errors.append(f"anchor_kind_count: {len(anchors)}")
    if len(gates) != 1:
        errors.append(f"gate_kind_count: {len(gates)}")
    kinds = {k.code for k in obj.milestone_kinds}
    codes = {t.code for t in obj.milestone_templates}
    roots = [t.code for t in obj.milestone_templates if t.successor is None]
    for t in obj.milestone_templates:
        if t.kind not in kinds:
            errors.append(f"template_kind_unknown: {t.code}:{t.kind}")
        if t.kind in gates:
            errors.append(f"template_is_gate: {t.code}")
        if t.successor is not None and t.successor not in codes:
            errors.append(f"template_successor_unknown: {t.code}:{t.successor}")
        if t.successor == t.code:
            errors.append(f"template_successor_self: {t.code}")
        if t.lead_days < 0:
            errors.append(f"template_lead_days_invalid: {t.code}")
    errors += [f"template_cycle: {c}" for c in _template_cycle(obj.milestone_templates)]
    if obj.milestone_templates:
        if len(roots) != 1:
            errors.append(f"template_root_count: {len(roots)}")
        elif next(t.kind for t in obj.milestone_templates if t.code == roots[0]) not in anchors:
            errors.append(f"template_root_not_anchor: {roots[0]}")
    for k in obj.programme_kinds:
        if not k.default_unit:
            errors.append(f"programme_kind_without_unit: {k.code}")
    if not obj.source_url and obj.review_status is not ReviewStatus.unconfirmed:
        errors.append("catalogue_without_source")
    return errors


def register_kinds() -> None:
    """Register the kind with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=ENGINEERING_BRIEF_KIND,
            model=EngineeringBriefCatalogue,
            validator=validate_engineering_brief_model,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=(
                "requirement_categories",
                "concept_topics",
                "programme_kinds",
                "milestone_kinds",
                "milestone_templates",
            ),
        )
    )
