"""Governance catalogues: phase models, gates, areas and frame document types.

A catalogue is data, shipped as one versioned JSON file per catalogue in
``catalogues/``. This module types it (Pydantic v2), validates the cross
references a model cannot express on its own (unique codes, gates between
consecutive phases, document types pointing at existing areas and gates,
spine keys known to :data:`app.modules.requirements.lifecycle.PHASE_SPINE`),
caches the result and resolves a country's default catalogue.

Country default resolution reads the regional packs through
:mod:`app.core.regional_packs` without changing them. A national pack may
declare ``PACK_CONFIG["governance_catalogue"] = {"DE": "hoai_lph"}`` keyed by
the exact country; when no pack answers, the one shipped catalogue whose
``jurisdiction_countries`` names the country is used; otherwise ``neutral``.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core import regional_packs
from app.modules.requirements.lifecycle import PHASE_SPINE

CATALOGUE_DIR: Path = Path(__file__).with_name("catalogues")

#: The catalogue a project gets when nothing else answers.
DEFAULT_CATALOGUE_ID = "neutral"

#: The shipped catalogues, in display order. A file on disk not listed here is
#: not loaded, so the set is explicit.
CATALOGUE_IDS: tuple[str, ...] = (
    "neutral",
    "elf_module_framework",
    "aho_heft9",
    "hoai_lph",
    "riba_2020",
    "aia_b101",
)

I18N_PREFIX = "governance.catalogue."


class ReviewStatus(StrEnum):
    """Whether the facts of a catalogue or phase were checked on the cited source."""

    verified = "verified"
    unconfirmed = "unconfirmed"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CataloguePhase(_Frozen):
    """One phase of a catalogue, mapped onto the platform phase spine."""

    code: str = Field(min_length=1)
    order: int = Field(ge=1)
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None
    spine_keys: tuple[str, ...] = Field(min_length=1)
    # What entering this phase enables ("construction_start", "handover", ...); modules read
    # the tag instead of matching a phase code. Vocabulary: ``catalogue_kinds.phase_capabilities``.
    enables: tuple[str, ...] = ()
    source_ref: str | None = None
    review_status: ReviewStatus = ReviewStatus.verified

    @property
    def spine_key(self) -> str:
        """The spine phase this phase starts at, the value mirrored into ``Project.phase``."""
        return self.spine_keys[0]


class CatalogueGate(_Frozen):
    """A decision point between two consecutive phases."""

    code: str = Field(min_length=1)
    from_phase: str
    to_phase: str
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None


class CatalogueArea(_Frozen):
    """A management area (an owner's responsibility)."""

    code: str = Field(min_length=1)
    order: int = Field(ge=1)
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None
    parent: str | None = None


class CatalogueFolder(_Frozen):
    """A working subfolder of an area within one phase."""

    code: str = Field(min_length=1)
    area: str
    phase: str
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None
    parent: str | None = None


class CatalogueDocumentType(_Frozen):
    """A frame document type of an area, required at the listed gates."""

    code: str = Field(min_length=1)
    area: str
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None
    required_at_gates: tuple[str, ...] = ()
    # Subjects whose module writes into this frame document ("design", "permits", ...). The
    # hosting area is the document's own area. Vocabulary: ``catalogue_kinds.host_subjects``.
    hosts: tuple[str, ...] = ()
    source_ref: str | None = None


class ReadinessCriterion(_Frozen):
    """A default readiness criterion of an area at a gate, where the source defines one."""

    code: str = Field(min_length=1)
    area: str
    gate: str
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None


class Catalogue(_Frozen):
    """A complete, validated governance catalogue."""

    id: str = Field(min_length=1)
    version: int = Field(ge=1)
    name_key: str
    # Plain text per locale, used by tenant catalogues instead of an i18n key.
    labels: dict[str, str] | None = None
    description_key: str
    description_labels: dict[str, str] | None = None
    source_url: str | None = None
    source_title: str | None = None
    review_status: ReviewStatus
    jurisdiction_countries: tuple[str, ...] = ()
    areas_from: str | None = None
    phases: tuple[CataloguePhase, ...] = Field(min_length=1)
    gates: tuple[CatalogueGate, ...] = ()
    areas: tuple[CatalogueArea, ...] = ()
    folders: tuple[CatalogueFolder, ...] = ()
    document_types: tuple[CatalogueDocumentType, ...] = ()
    readiness_criteria: tuple[ReadinessCriterion, ...] = ()

    def phase(self, code: str) -> CataloguePhase:
        """Return the phase with ``code``; raise ``KeyError`` if absent."""
        return _by_code(self.phases, code, "phase")

    def gate(self, code: str) -> CatalogueGate:
        """Return the gate with ``code``; raise ``KeyError`` if absent."""
        return _by_code(self.gates, code, "gate")

    def area(self, code: str) -> CatalogueArea:
        """Return the area with ``code``; raise ``KeyError`` if absent."""
        return _by_code(self.areas, code, "area")

    @property
    def first_phase(self) -> CataloguePhase:
        """The phase a new project starts in."""
        return self.phases[0]

    def next_gate(self, phase_code: str) -> CatalogueGate | None:
        """The gate leaving ``phase_code``, or ``None`` for the last phase."""
        self.phase(phase_code)
        return next((g for g in self.gates if g.from_phase == phase_code), None)

    def documents_required_at(self, gate_code: str) -> tuple[CatalogueDocumentType, ...]:
        """Document types that must be approved at ``gate_code``."""
        self.gate(gate_code)
        return tuple(d for d in self.document_types if gate_code in d.required_at_gates)

    def documents_for_area(self, area_code: str) -> tuple[CatalogueDocumentType, ...]:
        """Document types owned by ``area_code``."""
        self.area(area_code)
        return tuple(d for d in self.document_types if d.area == area_code)

    def criteria_for(self, gate_code: str, area_code: str) -> tuple[ReadinessCriterion, ...]:
        """Default readiness criteria of ``area_code`` at ``gate_code``."""
        return tuple(c for c in self.readiness_criteria if c.gate == gate_code and c.area == area_code)

    def folders_for(self, area_code: str, phase_code: str | None = None) -> tuple[CatalogueFolder, ...]:
        """Working folders of an area, optionally limited to one phase."""
        return tuple(f for f in self.folders if f.area == area_code and (phase_code is None or f.phase == phase_code))

    def phases_enabling(self, capability: str) -> tuple[CataloguePhase, ...]:
        """Phases tagged ``enables: [capability]``, in phase order; empty when none is."""
        return tuple(p for p in sorted(self.phases, key=lambda p: p.order) if capability in p.enables)

    def host_of(self, subject: str) -> CatalogueDocumentType | None:
        """The one document type tagged ``hosts: [subject]``, or ``None`` when the catalogue hosts it nowhere."""
        return next((d for d in self.document_types if subject in d.hosts), None)

    def i18n_keys(self) -> frozenset[str]:
        """Every i18n key the catalogue references."""
        keys = {self.name_key, self.description_key}
        for group in (self.phases, self.gates, self.areas, self.folders, self.document_types, self.readiness_criteria):
            keys.update(item.name_key for item in group)
        return frozenset(keys)


def _by_code(items: tuple[Any, ...], code: str, kind: str) -> Any:
    for item in items:
        if item.code == code:
            return item
    raise KeyError(f"unknown {kind} {code!r}")


class CatalogueError(Exception):
    """Base class of catalogue errors."""


class UnknownCatalogueError(CatalogueError, LookupError):
    """No shipped catalogue has this id."""

    def __init__(self, catalogue_id: str) -> None:
        super().__init__(f"unknown governance catalogue {catalogue_id!r}")
        self.catalogue_id = catalogue_id


class UnknownCatalogueVersionError(UnknownCatalogueError):
    """The catalogue exists, but not in the requested version."""

    def __init__(self, catalogue_id: str, version: int, available: tuple[int, ...]) -> None:
        super().__init__(catalogue_id)
        self.args = (f"governance catalogue {catalogue_id!r} has no version {version} (available: {available})",)
        self.version = version
        self.available = available


class InvalidCatalogueError(CatalogueError, ValueError):
    """A catalogue file is malformed or breaks a cross-reference rule."""

    def __init__(self, path: Path | str, errors: list[str]) -> None:
        super().__init__(f"invalid governance catalogue {path}: " + "; ".join(errors))
        self.path = path
        self.errors = errors


def _duplicates(codes: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    return sorted({c for c in codes if c in seen or seen.add(c)}, key=str)


def validate_catalogue(catalogue: Catalogue, *, source: str = "shipped") -> list[str]:
    """Return every cross-reference rule the catalogue breaks (empty when valid).

    Args:
        catalogue: A catalogue with ``areas`` already resolved.
        source: ``"shipped"`` (labels must be i18n keys in the catalogue's
            namespace) or ``"tenant"`` / ``"pack"`` (every label is either an
            i18n key of a shipped catalogue it was cloned from, or plain text
            with at least an English entry in ``labels``).

    Returns:
        Human-readable error strings, each starting with a stable rule code.
    """
    errors: list[str] = []
    for name, items in (
        ("phase", catalogue.phases),
        ("gate", catalogue.gates),
        ("area", catalogue.areas),
        ("document_type", catalogue.document_types),
    ):
        for dup in _duplicates([i.code for i in items]):
            errors.append(f"duplicate_code: {name} {dup!r}")
    for dup in _duplicates([(f.area, f.code) for f in catalogue.folders]):
        errors.append(f"duplicate_code: folder {dup!r}")
    for dup in _duplicates([(c.area, c.gate, c.code) for c in catalogue.readiness_criteria]):
        errors.append(f"duplicate_code: criterion {dup!r}")

    for name, items in (("phase", catalogue.phases), ("area", catalogue.areas)):
        orders = sorted(i.order for i in items)
        if orders != list(range(1, len(items) + 1)):
            errors.append(f"order_not_contiguous: {name} orders {orders}")

    phases = sorted(catalogue.phases, key=lambda p: p.order)
    position = {p.code: i for i, p in enumerate(phases)}
    for phase in phases:
        unknown = [s for s in phase.spine_keys if s not in PHASE_SPINE]
        if unknown:
            errors.append(f"unknown_spine_key: phase {phase.code!r} {unknown}")
        elif list(phase.spine_keys) != sorted(phase.spine_keys, key=PHASE_SPINE.index):
            errors.append(f"spine_keys_out_of_order: phase {phase.code!r}")

    pairs = set()
    for gate in catalogue.gates:
        a, b = position.get(gate.from_phase), position.get(gate.to_phase)
        if a is None or b is None:
            errors.append(f"gate_unknown_phase: gate {gate.code!r}")
        elif b != a + 1:
            errors.append(f"gate_not_consecutive: gate {gate.code!r}")
        pairs.add((gate.from_phase, gate.to_phase))
    for a, b in zip(phases, phases[1:], strict=False):
        if (a.code, b.code) not in pairs:
            errors.append(f"gate_missing: between {a.code!r} and {b.code!r}")

    areas = {a.code for a in catalogue.areas}
    gates = {g.code for g in catalogue.gates}
    for area in catalogue.areas:
        if area.parent is not None and (area.parent not in areas or area.parent == area.code):
            errors.append(f"area_unknown_parent: area {area.code!r}")
    for doc in catalogue.document_types:
        if doc.area not in areas:
            errors.append(f"document_unknown_area: document_type {doc.code!r} area {doc.area!r}")
        for g in doc.required_at_gates:
            if g not in gates:
                errors.append(f"document_unknown_gate: document_type {doc.code!r} gate {g!r}")
    folder_keys = {(f.area, f.code): f for f in catalogue.folders}
    for f in catalogue.folders:
        if f.area not in areas:
            errors.append(f"folder_unknown_area: folder {f.code!r}")
        if f.phase not in position:
            errors.append(f"folder_unknown_phase: folder {f.code!r}")
        if f.parent is not None:
            parent = folder_keys.get((f.area, f.parent))
            if parent is None or parent.phase != f.phase or parent.parent is not None:
                errors.append(f"folder_unknown_parent: folder {f.code!r}")
    for c in catalogue.readiness_criteria:
        if c.area not in areas or c.gate not in gates:
            errors.append(f"criterion_unknown_ref: criterion {c.code!r} ({c.area!r}, {c.gate!r})")
    errors.extend(_tag_errors(catalogue))

    if source == "shipped":
        namespaces = tuple(f"{I18N_PREFIX}{cid}." for cid in (catalogue.id, catalogue.areas_from) if cid)
        for key in catalogue.i18n_keys():
            if not key.startswith(namespaces):
                errors.append(f"i18n_key_outside_namespace: {key!r}")
    else:
        if not _has_label(catalogue.name_key, catalogue.labels):
            errors.append("label_missing: catalogue name")
        for name, items in (
            ("phase", catalogue.phases),
            ("gate", catalogue.gates),
            ("area", catalogue.areas),
            ("folder", catalogue.folders),
            ("document_type", catalogue.document_types),
            ("criterion", catalogue.readiness_criteria),
        ):
            for item in items:
                if not _has_label(item.name_key, item.labels):
                    errors.append(f"label_missing: {name} {item.code!r}")
    if catalogue.review_status is ReviewStatus.verified and not (catalogue.source_url or catalogue.source_title):
        errors.append("verified_without_source")
    return errors


def _tag_errors(catalogue: Catalogue) -> list[str]:
    """Rules of the ``enables`` and ``hosts`` tags, the same for every source.

    A subject hosted by no document type is legal (the reading module then
    reports ``unknown``); a subject hosted twice is not, because the reader
    could not tell which document is meant.
    """
    # Imported here: ``catalogue_kinds`` imports this module for its error types.
    from app.modules.project_governance.catalogue_kinds import host_subjects, phase_capabilities

    errors: list[str] = []
    capabilities, subjects = phase_capabilities(), host_subjects()
    for phase in catalogue.phases:
        unknown = sorted(set(phase.enables) - capabilities)
        if unknown:
            errors.append(f"phase_enables_unknown: phase {phase.code!r} {unknown}")
        if _duplicates(list(phase.enables)):
            errors.append(f"phase_enables_duplicate: phase {phase.code!r}")
    hosted: dict[str, list[str]] = {}
    for doc in catalogue.document_types:
        unknown = sorted(set(doc.hosts) - subjects)
        if unknown:
            errors.append(f"document_hosts_unknown: document_type {doc.code!r} {unknown}")
        if _duplicates(list(doc.hosts)):
            errors.append(f"document_hosts_duplicate: document_type {doc.code!r}")
        for subject in set(doc.hosts):
            hosted.setdefault(subject, []).append(doc.code)
        if doc.hosts and not doc.required_at_gates:
            # A frame document becomes binding at a gate that lists it, and the module whose
            # subject it hosts waits for that. With no gate it would wait for the whole project.
            errors.append(f"hosting_document_never_required: document_type {doc.code!r} hosts {sorted(doc.hosts)}")
    for subject, codes in sorted(hosted.items()):
        if len(codes) > 1:
            errors.append(f"subject_hosted_twice: {subject!r} by {sorted(codes)}")
    return errors


def _has_label(name_key: str, labels: dict[str, str] | None) -> bool:
    if (labels or {}).get("en", "").strip():
        return True
    return bool(name_key) and name_key.startswith(I18N_PREFIX)


def label_of(name_key: str, labels: dict[str, str] | None) -> dict[str, Any]:
    """One label type for both sources: an i18n key, or plain text per locale.

    Shipped catalogues answer ``{"key": ..., "text": None}`` and the client
    translates the key; tenant catalogues answer their own text map.
    """
    return {"key": name_key or None, "text": dict(labels) if labels else None}


def catalogue_from_body(body: dict[str, Any], *, source: str, origin: str) -> Catalogue:
    """Validate a catalogue body that does not come from a shipped file.

    The same Pydantic models and the same cross-reference rules as a shipped
    file, so a tenant draft that would break a project is refused before it
    can be published. ``areas_from`` is resolved against shipped catalogues.

    Raises:
        InvalidCatalogueError: The body is malformed or breaks a rule.
    """
    try:
        catalogue = Catalogue.model_validate(body)
    except ValidationError as exc:
        raise InvalidCatalogueError(origin, [f"schema: {e['loc']} {e['msg']}" for e in exc.errors()]) from exc
    if catalogue.areas_from:
        if catalogue.areas:
            raise InvalidCatalogueError(origin, ["areas_conflict: areas_from and areas are both set"])
        try:
            catalogue = catalogue.model_copy(update={"areas": get_catalogue(catalogue.areas_from).areas})
        except UnknownCatalogueError as exc:
            raise InvalidCatalogueError(origin, [f"areas_from_unknown: {catalogue.areas_from!r}"]) from exc
    errors = validate_catalogue(catalogue, source=source)
    if errors:
        raise InvalidCatalogueError(origin, errors)
    return catalogue


def _read_raw(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidCatalogueError(path, [f"unreadable: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise InvalidCatalogueError(path, ["unreadable: top level is not an object"])
    return raw


def load_catalogue_file(path: Path, *, area_source: Catalogue | None = None) -> Catalogue:
    """Load and validate one catalogue file, without caching.

    Args:
        path: The JSON file.
        area_source: The catalogue named by ``areas_from``. When omitted and the
            file names one, it is read from the same directory.

    Returns:
        The validated catalogue, with ``areas`` resolved.

    Raises:
        InvalidCatalogueError: The file is malformed or breaks a rule.
    """
    raw = _read_raw(path)
    try:
        catalogue = Catalogue.model_validate(raw)
    except ValidationError as exc:
        raise InvalidCatalogueError(path, [f"schema: {e['loc']} {e['msg']}" for e in exc.errors()]) from exc
    if catalogue.areas_from:
        if catalogue.areas:
            raise InvalidCatalogueError(path, ["areas_conflict: areas_from and areas are both set"])
        source = area_source or load_catalogue_file(path.with_name(f"{catalogue.areas_from}.json"))
        catalogue = catalogue.model_copy(update={"areas": source.areas})
    errors = validate_catalogue(catalogue)
    if errors:
        raise InvalidCatalogueError(path, errors)
    return catalogue


@lru_cache(maxsize=1)
def list_catalogues() -> tuple[Catalogue, ...]:
    """Every shipped catalogue, loaded once and cached, in :data:`CATALOGUE_IDS` order."""
    loaded: dict[str, Catalogue] = {}
    for cid in CATALOGUE_IDS:
        path = CATALOGUE_DIR / f"{cid}.json"
        raw_from = _read_raw(path).get("areas_from")
        catalogue = load_catalogue_file(path, area_source=loaded.get(raw_from) if raw_from else None)
        if catalogue.id != cid:
            raise InvalidCatalogueError(path, [f"id_mismatch: file {cid!r} declares {catalogue.id!r}"])
        loaded[cid] = catalogue
    return tuple(loaded.values())


def clear_catalogue_cache() -> None:
    """Drop the cached catalogues (tests)."""
    list_catalogues.cache_clear()


def get_catalogue(catalogue_id: str, version: int | None = None) -> Catalogue:
    """Return a shipped catalogue, optionally pinned to a version.

    Args:
        catalogue_id: Catalogue id, for example ``"hoai_lph"``.
        version: The version a project pinned; ``None`` means the current one.

    Raises:
        UnknownCatalogueError: No catalogue has this id.
        UnknownCatalogueVersionError: The id exists but not in this version.
    """
    matches = [c for c in list_catalogues() if c.id == catalogue_id]
    if not matches:
        raise UnknownCatalogueError(catalogue_id)
    if version is None:
        return max(matches, key=lambda c: c.version)
    for catalogue in matches:
        if catalogue.version == version:
            return catalogue
    raise UnknownCatalogueVersionError(catalogue_id, version, tuple(sorted(c.version for c in matches)))


def _pack_declared_catalogue(country: str) -> str | None:
    """The catalogue the national packs declare for exactly ``country``, if they agree."""
    declared: set[str] = set()
    for config in regional_packs.packs_for_country(country):
        if config.get("parent_pack"):
            continue
        block = config.get("governance_catalogue")
        if isinstance(block, dict) and isinstance(block.get(country), str):
            declared.add(block[country].strip())
    if len(declared) != 1:
        return None
    value = declared.pop()
    return value if value in CATALOGUE_IDS else None


def default_catalogue_id_for_country(country_code: str | None, region: str | None = None) -> str:
    """Resolve the default catalogue id for a project's country.

    Order: the national regional packs' ``governance_catalogue`` entry for the
    exact country (packs must agree); then the one shipped catalogue whose
    ``jurisdiction_countries`` names the country; then :data:`DEFAULT_CATALOGUE_ID`.
    ``region`` is accepted for signature parity with the regional pack
    resolvers and deliberately ignored: a region such as ``"DACH"`` names a
    market, and HOAI binds Germany only.

    Args:
        country_code: ISO 3166-1 alpha-2 code; case and space are ignored.
        region: Unused, see above.

    Returns:
        A shipped catalogue id. Never raises.
    """
    del region
    country = (country_code or "").strip().upper()
    if not country:
        return DEFAULT_CATALOGUE_ID
    declared = _pack_declared_catalogue(country)
    if declared:
        return declared
    claims = [c.id for c in list_catalogues() if country in c.jurisdiction_countries]
    return claims[0] if len(claims) == 1 else DEFAULT_CATALOGUE_ID
