# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Registry of catalogue kinds: one store, one resolver, many kinds of catalogue.

A kind names a shape of reference data a company may ship, clone, edit and
publish: ``phase_model`` (this module), and later ``delivery_forms``,
``authority_schedule`` and others owned by their own modules. A module adds a
kind with ONE call::

    register_catalogue_kind(CatalogueKind(
        kind="delivery_forms",
        model=DeliveryFormsCatalogue,           # Pydantic v2 body model
        validator=validate_delivery_forms,      # (obj, source) -> list[str]
        shipped_dir=Path(__file__).with_name("catalogues"),
    ))

Shipped JSON of a kind lives in its owning module's ``catalogues/`` folder.
Tenant drafts and published versions of every kind live in the same two
tables (``oe_governance_catalogue`` keyed by ``(tenant_id, kind, code)``), are
validated by the kind's own model and validator, and are frozen the same way.

The body model must carry ``id: str`` and ``version: int``; the store sets both
on publish. ``labels`` follow the ``phase_model`` convention: shipped items use
i18n keys, tenant items may carry ``labels: {locale: text}``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from app.modules.project_governance.catalogue import InvalidCatalogueError, UnknownCatalogueError

PHASE_MODEL_KIND = "phase_model"


@dataclass(frozen=True)
class CatalogueKind:
    """How one kind of catalogue is typed, validated and found on disk.

    Attributes:
        kind: Stable identifier stored in the ``kind`` column.
        model: Pydantic model of one catalogue body.
        validator: Cross-reference rules: ``(parsed, source) -> errors``,
            where ``source`` is ``"shipped"``, ``"tenant"`` or ``"pack"``.
        shipped_dir: Folder holding the kind's shipped ``<id>.json`` files.
        parse: Optional full override of body parsing (a kind with references
            between files, such as ``areas_from``, resolves them here).
        list_shipped: Optional override of shipped loading.
        diff_groups: Top-level list fields compared by ``diff``.
    """

    kind: str
    model: type[BaseModel]
    validator: Callable[[Any, str], list[str]]
    shipped_dir: Path | None = None
    parse: Callable[[dict[str, Any], str, str], Any] | None = None
    list_shipped: Callable[[], tuple[Any, ...]] | None = None
    diff_groups: tuple[str, ...] = field(default_factory=tuple)

    def parse_body(self, body: dict[str, Any], *, source: str, origin: str) -> Any:
        """Validate a body with this kind's model and rules; raise ``InvalidCatalogueError``."""
        if self.parse is not None:
            return self.parse(body, source, origin)
        try:
            obj = self.model.model_validate(body)
        except ValidationError as exc:
            raise InvalidCatalogueError(origin, [f"schema: {e['loc']} {e['msg']}" for e in exc.errors()]) from exc
        errors = self.validator(obj, source)
        if errors:
            raise InvalidCatalogueError(origin, errors)
        return obj

    def shipped(self) -> tuple[Any, ...]:
        """Every shipped catalogue of this kind, validated."""
        if self.list_shipped is not None:
            return self.list_shipped()
        if self.shipped_dir is None or not self.shipped_dir.is_dir():
            return ()
        out = []
        for path in sorted(self.shipped_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise InvalidCatalogueError(path, [f"unreadable: {exc}"]) from exc
            out.append(self.parse_body(raw, source="shipped", origin=str(path)))
        return tuple(out)

    def get_shipped(self, catalogue_id: str, version: int | None = None) -> Any:
        """One shipped catalogue of this kind; ``UnknownCatalogueError`` when absent."""
        matches = [c for c in self.shipped() if getattr(c, "id", None) == catalogue_id]
        if version is not None:
            matches = [c for c in matches if getattr(c, "version", None) == version]
        if not matches:
            raise UnknownCatalogueError(catalogue_id)
        return max(matches, key=lambda c: getattr(c, "version", 0))


_KINDS: dict[str, CatalogueKind] = {}


def register_catalogue_kind(kind: CatalogueKind) -> CatalogueKind:
    """Register (or replace, idempotently) a catalogue kind."""
    _KINDS[kind.kind] = kind
    return kind


def unregister_catalogue_kind(name: str) -> None:
    """Remove a kind (tests)."""
    _KINDS.pop(name, None)


def get_catalogue_kind(name: str) -> CatalogueKind:
    """The registered kind; ``UnknownCatalogueError`` when nobody registered it."""
    _ensure_builtin()
    try:
        return _KINDS[name]
    except KeyError as exc:
        raise UnknownCatalogueError(name) from exc


def catalogue_kinds() -> tuple[str, ...]:
    """Names of every registered kind."""
    _ensure_builtin()
    return tuple(sorted(_KINDS))


def _ensure_builtin() -> None:
    if PHASE_MODEL_KIND in _KINDS:
        return
    from app.modules.project_governance import catalogue as cat

    def _validate(obj: Any, source: str) -> list[str]:
        return cat.validate_catalogue(obj, source=source)

    def _parse(body: dict[str, Any], source: str, origin: str) -> Any:
        return cat.catalogue_from_body(body, source=source, origin=origin)

    register_catalogue_kind(
        CatalogueKind(
            kind=PHASE_MODEL_KIND,
            model=cat.Catalogue,
            validator=_validate,
            shipped_dir=cat.CATALOGUE_DIR,
            parse=_parse,
            list_shipped=cat.list_catalogues,
            diff_groups=("phases", "gates", "areas", "folders", "document_types", "readiness_criteria"),
        )
    )
