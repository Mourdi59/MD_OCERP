# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogue kind ``handbook_model``: the chapters of a project handbook.

Data, not code. A chapter names the management area it belongs to, whether it must be approved before a
gate, the live sources it reads (``sources``: names registered in ``sources.py``, never copied text) and
the data room folder its evidence is filed in. Shipped JSON lives in ``catalogues/``; a pack ships the
chapter structure of its framework as ``catalogues/handbook_model/<id>.json``; tenant drafts go through
the one governance catalogue store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.modules.project_governance.catalogue import ReviewStatus

HANDBOOK_KIND = "handbook_model"
CATALOGUE_DIR = Path(__file__).with_name("catalogues")
DEFAULT_CATALOGUE_ID = "neutral"
I18N_PREFIX = "project_handbook."


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class _Labelled(_Frozen):
    name_key: str = ""
    labels: dict[str, str] | None = None


class HandbookChapterSpec(_Labelled):
    """One chapter the catalogue asks for."""

    code: str
    # Code of the management area the chapter belongs to (a soft reference into the phase model).
    area: str
    order: int
    # A required chapter must be approved before the gate that needs the handbook can pass.
    required: bool = False
    # Names of live sources the chapter reads instead of copying (``sources.known_sources``).
    sources: tuple[str, ...] = ()
    # Code of the phase-model folder, within ``area``, that holds the chapter's evidence.
    folder: str = ""


class HandbookCatalogue(_Labelled):
    """One catalogue body of kind ``handbook_model``."""

    id: str
    version: int = 1
    review_status: ReviewStatus = ReviewStatus.unconfirmed
    source_url: str = ""
    source_title: str = ""
    jurisdiction_countries: tuple[str, ...] = ()
    chapters: tuple[HandbookChapterSpec, ...]

    def chapter(self, code: str | None) -> HandbookChapterSpec | None:
        return next((c for c in self.chapters if c.code == code), None)


def label_of(entry: Any, locale: str, fallback: str = "") -> str:
    """The display text of a catalogue entry: its own text for the locale, else its translated key."""
    from app.modules.project_handbook.messages import translate

    if entry is None:
        return fallback
    labels = getattr(entry, "labels", None) or {}
    text = labels.get(locale) or labels.get(locale.split("-")[0]) or labels.get("en")
    if text:
        return text
    key = getattr(entry, "name_key", "")
    return translate(key, locale=locale) if key else (next(iter(labels.values()), "") or fallback)


def _dupes(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: set[str] = set()
    for c in codes:
        if c in seen:
            out.add(c)
        seen.add(c)
    return sorted(out)


def validate_handbook_model(obj: HandbookCatalogue, source: str) -> list[str]:
    """Cross-reference rules of a handbook catalogue; an empty list means valid."""
    from app.modules.project_handbook.sources import known_sources

    errors: list[str] = []
    if not obj.chapters:
        errors.append("no_chapters")
    errors += [f"duplicate_chapter: {c}" for c in _dupes([c.code for c in obj.chapters])]
    errors += [f"duplicate_order: {o}" for o in _dupes([str(c.order) for c in obj.chapters])]
    known = known_sources()
    for c in obj.chapters:
        if source == "shipped":
            if not c.name_key.startswith(I18N_PREFIX):
                errors.append(f"shipped_label_not_i18n_key: chapter:{c.code}")
        elif not c.name_key and not c.labels:
            errors.append(f"label_missing: chapter:{c.code}")
        if c.order < 1:
            errors.append(f"chapter_order_invalid: {c.code}")
        if not c.area:
            errors.append(f"chapter_without_area: {c.code}")
        errors += [f"chapter_source_unknown: {c.code}:{s}" for s in c.sources if s not in known]
    if not obj.source_url and obj.review_status is not ReviewStatus.unconfirmed:
        errors.append("catalogue_without_source")
    return errors


def register_kinds() -> None:
    """Register the kind with module 1's catalogue-kind registry (idempotent)."""
    from app.modules.project_governance.catalogue_kinds import CatalogueKind, register_catalogue_kind

    register_catalogue_kind(
        CatalogueKind(
            kind=HANDBOOK_KIND,
            model=HandbookCatalogue,
            validator=validate_handbook_model,
            shipped_dir=CATALOGUE_DIR,
            diff_groups=("chapters",),
        )
    )
