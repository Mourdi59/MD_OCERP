# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``hse_frame``: topics, roles, requirement templates, hazardous works, thresholds.

Data, not code. Shipped JSON lives in ``catalogues/``; tenant drafts and
published versions live in the governance module's shared catalogue tables and
resolve through its one resolver. A national catalogue ``extends`` the neutral
one: its entries replace the parent's by ``code`` group by group, the rest is
inherited, thresholds merge key by key.

Every statutory figure and every entry that names a law carries ``source_url``
and ``review_status``. A shipped catalogue with a jurisdiction ships every
figure ``unconfirmed`` until a reviewer read it on the source. The neutral
catalogue names no figure at all: a rule that needs one reports "unknown".

Labels: shipped entries carry ``labels: {locale: text}``; the screens fall back
to the code.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.hse_frame.vocab import AUDIENCES, TOPIC_BASES, TRIGGERS
from app.modules.project_governance.catalogue import ReviewStatus

HSE_FRAME_KIND = "hse_frame"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"

_CODE = r"^[a-z0-9][a-z0-9_]*$"
_Audience = Literal["owner", "designer", "contractor", "coordinator", "operator"]
_Trigger = Literal["always", "multiple_employers", "plan_required", "advance_notice", "hazardous_work"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Sourced(_Frozen):
    """Where a legal statement comes from and whether a reviewer read it there."""

    legal_basis: str = ""
    source_url: str | None = None
    review_status: ReviewStatus | None = None
    as_of: date | None = None


class Entry(_Frozen):
    code: str = Field(pattern=_CODE, max_length=64)
    labels: dict[str, str] | None = None


class Topic(Entry):
    """One of the subject areas of the frame (requirements, environmental review, clearances, ...).

    ``criterion`` is the readiness criterion of the phase model this topic answers; ``basis`` says
    where the answer is read: the item register, the appointed roles or the permit conditions.
    """

    criterion: str | None = Field(default=None, pattern=_CODE, max_length=80)
    basis: Literal["items", "roles", "permits"] = "items"


class RoleKind(Entry, Sourced):
    """A responsibility the frame names a person for."""

    party: _Audience = "owner"
    phase: Literal["development", "execution", "both"] = "both"
    required_when: _Trigger | None = None
    # A national title: shown next to the neutral label, never matched.
    national_name: str = ""
    qualification_required: bool = False


class Template(Entry, Sourced):
    """A requirement a jurisdiction usually puts on the project; applying it creates register rows."""

    topic: str = Field(pattern=_CODE, max_length=64)
    audience: tuple[_Audience, ...] = ()
    obligation: Literal["mandatory", "recommended"] = "mandatory"
    in_tender_documents: bool = False
    # A record kind (vocab.LINK_KINDS) that usually proves it; shown as a hint.
    evidence_kind: str | None = None
    # The template is created only when the trigger holds (None = always).
    applies_when: _Trigger | None = None


class HazardousWork(Entry, Sourced):
    """A kind of work that makes the health and safety plan compulsory."""


class PlanElement(Entry, Sourced):
    """One content point of the health and safety plan."""

    required: bool = True


class Thresholds(_Frozen):
    """The figures behind the duties. ``None`` = the catalogue states none, so the rule reports unknown."""

    advance_notice_min_working_days: int | None = Field(default=None, ge=0, le=100000)
    advance_notice_min_workers: int | None = Field(default=None, ge=0, le=100000)
    advance_notice_person_days: int | None = Field(default=None, ge=0, le=10000000)
    advance_notice_lead_days: int | None = Field(default=None, ge=0, le=365)
    coordinator_min_employers: int | None = Field(default=None, ge=1, le=1000)
    later_works_file_with_coordinator: bool | None = None
    item_due_warn_days: int | None = Field(default=None, ge=0, le=365)
    source_url: str | None = None
    review_status: ReviewStatus | None = None
    legal_basis: str = ""
    as_of: date | None = None

    def merged_over(self, parent: Thresholds) -> Thresholds:
        data = parent.model_dump()
        data.update({k: v for k, v in self.model_dump().items() if v is not None and v != ""})
        return Thresholds(**data)

    def has_figure(self) -> bool:
        return any(
            getattr(self, f) is not None
            for f in (
                "advance_notice_min_working_days",
                "advance_notice_min_workers",
                "advance_notice_person_days",
                "advance_notice_lead_days",
                "coordinator_min_employers",
                "later_works_file_with_coordinator",
            )
        )


class HseFrameCatalogue(_Frozen):
    """One catalogue body of kind ``hse_frame``."""

    id: str = Field(pattern=_CODE, max_length=64)
    version: int = Field(default=1, ge=1)
    name_key: str = ""
    labels: dict[str, str] | None = None
    # The label of the legal area the figures come from (a country, a Land); shown, never matched.
    jurisdiction: str = ""
    # The countries whose new projects use this catalogue; the governance port is the only country rule.
    jurisdiction_countries: tuple[str, ...] = ()
    extends: str | None = None
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    topics: tuple[Topic, ...] = ()
    role_kinds: tuple[RoleKind, ...] = ()
    templates: tuple[Template, ...] = ()
    hazardous_works: tuple[HazardousWork, ...] = ()
    plan_elements: tuple[PlanElement, ...] = ()
    thresholds: Thresholds = Thresholds()

    def codes(self, group: str) -> set[str]:
        return {e.code for e in getattr(self, group)}

    def entry(self, group: str, code: str) -> Any:
        return next((e for e in getattr(self, group) if e.code == code), None)


GROUPS: tuple[str, ...] = ("topics", "role_kinds", "templates", "hazardous_works", "plan_elements")
_SOURCED_GROUPS = ("role_kinds", "templates", "hazardous_works", "plan_elements")


def validate_hse_frame_catalogue(obj: HseFrameCatalogue, source: str) -> list[str]:
    """Cross-field rules of one body. ``source`` is ``shipped``, ``tenant`` or ``pack``."""
    errors: list[str] = []
    if obj.extends == obj.id:
        errors.append("catalogue_extends_itself")
    for group in GROUPS:
        codes = [e.code for e in getattr(obj, group)]
        if len(set(codes)) != len(codes):
            errors.append(f"duplicate_code: {group}")
    for group in _SOURCED_GROUPS:
        for e in getattr(obj, group):
            # A statement that names a law carries its source and a review status.
            if e.legal_basis and (not e.source_url or e.review_status is None):
                errors.append(f"legal_basis_without_source: {group}:{e.code}")
            national = bool(obj.jurisdiction or obj.jurisdiction_countries)
            if source == "shipped" and national and e.review_status == ReviewStatus.verified and not e.as_of:
                errors.append(f"verified_without_as_of: {group}:{e.code}")
    t = obj.thresholds
    if t.has_figure() and (not t.source_url or t.review_status is None):
        errors.append("statutory_figure_without_source: thresholds")
    for country in obj.jurisdiction_countries:
        if not re.fullmatch(r"[A-Z]{2}(-[A-Z0-9]{1,3})?", country):
            errors.append(f"bad_country_code: {country}")
    topic_codes = obj.codes("topics")
    for template in obj.templates:
        # A child catalogue may add a template to a topic its parent defines; only a root is checked whole.
        if obj.extends is None and template.topic not in topic_codes:
            errors.append(f"template_unknown_topic: {template.code}")
    for topic in obj.topics:
        if topic.basis not in TOPIC_BASES:
            errors.append(f"bad_topic_basis: {topic.code}")
    for role in obj.role_kinds:
        if role.required_when is not None and role.required_when not in TRIGGERS:
            errors.append(f"bad_trigger: {role.code}")
        if role.party not in AUDIENCES:
            errors.append(f"bad_party: {role.code}")
    return errors


def merged(obj: HseFrameCatalogue, lookup: Callable[[str], HseFrameCatalogue]) -> HseFrameCatalogue:
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
    thresholds = Thresholds()
    for c in reversed(chain):
        thresholds = c.thresholds.merged_over(thresholds)
    update["thresholds"] = thresholds
    return obj.model_copy(update=update)


def register_kind() -> None:
    """Register ``hse_frame`` with the governance catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import (
        CatalogueKind,
        register_catalogue_kind,
        register_host_subject,
    )

    register_host_subject("hse")
    register_catalogue_kind(
        CatalogueKind(
            kind=HSE_FRAME_KIND,
            model=HseFrameCatalogue,
            validator=validate_hse_frame_catalogue,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=GROUPS,
        )
    )


def shipped_catalogues() -> dict[str, HseFrameCatalogue]:
    """Every shipped catalogue by id, validated by the registered kind."""
    from app.modules.project_governance.catalogue_kinds import get_catalogue_kind

    register_kind()
    return {c.id: c for c in get_catalogue_kind(HSE_FRAME_KIND).shipped()}


def resolved_shipped(catalogue_id: str) -> HseFrameCatalogue:
    """A shipped catalogue with its parent chain merged in."""
    shipped = shipped_catalogues()
    return merged(shipped[catalogue_id], shipped.__getitem__)
