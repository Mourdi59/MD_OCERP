# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogues a pack ships: the ``pack`` source of the catalogue resolver.

A pack is a folder of data (``app.core.partner_pack``). It declares the
catalogues it carries in its manifest::

    "metadata": {
      "catalogues": [
        {"kind": "phase_model", "id": "my_model", "version": 1,
         "path": "catalogues/phase_model/my_model.json",
         "default_for_new_projects": true},
        {"kind": "permit_type", "id": "my_permits_de", "version": 1,
         "path": "catalogues/permit_type/my_permits_de.json",
         "default_for_countries": ["DE"]}
      ]
    }

Each body is the same JSON a shipped catalogue of that kind is, and it goes
through the kind's own model and validator with ``source="pack"``, so a pack
cannot bring a catalogue the platform would refuse from a tenant.

Two readings, on purpose:

* an id that comes from a request resolves only in the ACTIVE pack: that is
  what a new project may pin;
* a pin the server stored resolves in every DISCOVERED pack, the active one
  first, so a project keeps its catalogue when another pack becomes active.

A pack catalogue belongs to the installation, not to a tenant, exactly like a
shipped one. Nothing here writes: a pack is read-only.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.partner_pack import discovery
from app.modules.project_governance.catalogue import InvalidCatalogueError

logger = logging.getLogger(__name__)

PACK_SOURCE = "pack"


@dataclass(frozen=True)
class PackCatalogue:
    """One catalogue a pack declares in ``metadata.catalogues``.

    Attributes:
        slug: Slug of the pack that ships it.
        kind: Catalogue kind (``phase_model``, ``delivery_forms``, ...).
        id: Catalogue id inside the kind; what a project pins.
        version: Version of the body.
        path: File inside the pack package, relative to it.
        default_for_new_projects: The pack wants this catalogue pinned on new projects of any country.
        default_for_countries: ISO 3166-1 alpha-2 codes the pack wants it pinned for.
    """

    slug: str
    kind: str
    id: str
    version: int
    path: str
    default_for_new_projects: bool = False
    default_for_countries: tuple[str, ...] = ()


@dataclass(frozen=True)
class CataloguePin:
    """What a project stores to name a catalogue: ``(source, id, version)``."""

    source: str
    catalogue_id: str
    version: int


def declared_catalogues(manifest: Any) -> tuple[PackCatalogue, ...]:
    """The catalogues a pack manifest declares; a malformed entry is logged and left out.

    Leaving it out is safe in both directions: the catalogue cannot be pinned,
    and a pin on it answers ``unknown_catalogue`` instead of a half-read body.
    """
    slug = str(getattr(manifest, "slug", "") or "")
    entries = (getattr(manifest, "metadata", None) or {}).get("catalogues")
    if not slug or not isinstance(entries, list):
        return ()
    out: list[PackCatalogue] = []
    for entry in entries:
        ref = _entry(slug, entry)
        if ref is None:
            logger.warning("pack %s declares a catalogue entry that cannot be read: %r", slug, entry)
            continue
        out.append(ref)
    return tuple(out)


def _entry(slug: str, entry: Any) -> PackCatalogue | None:
    if not isinstance(entry, dict):
        return None
    kind, cid, version, path = (entry.get(k) for k in ("kind", "id", "version", "path"))
    if not all(isinstance(v, str) and v.strip() for v in (kind, cid, path)):
        return None
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return None
    countries = entry.get("default_for_countries") or ()
    if not isinstance(countries, (list, tuple)) or not all(isinstance(c, str) for c in countries):
        return None
    return PackCatalogue(
        slug=slug,
        kind=kind.strip(),
        id=cid.strip(),
        version=version,
        path=path.strip(),
        default_for_new_projects=entry.get("default_for_new_projects") is True,
        default_for_countries=tuple(c.strip().upper() for c in countries if c.strip()),
    )


def _manifests(*, active_only: bool) -> list[Any]:
    """The packs to look in: the active one, then (for a stored pin) every other discovered one."""
    active = discovery.get_active_pack()
    packs = [active] if active is not None else []
    if not active_only:
        active_slug = getattr(active, "slug", None)
        packs.extend(m for m in discovery.discover_packs() if m.slug != active_slug)
    return packs


def find_pack_catalogue(
    kind: str, catalogue_id: str, version: int | None, *, active_only: bool
) -> PackCatalogue | None:
    """The declaration of ``(kind, id, version)``, or ``None``.

    ``version=None`` means the highest version the pack declares. The first
    pack that declares the catalogue wins; the active pack is asked first.
    """
    for manifest in _manifests(active_only=active_only):
        matches = [c for c in declared_catalogues(manifest) if c.kind == kind and c.id == catalogue_id]
        if version is not None:
            matches = [c for c in matches if c.version == version]
        if matches:
            return max(matches, key=lambda c: c.version)
    return None


def active_pack_catalogues(kind: str) -> tuple[PackCatalogue, ...]:
    """Catalogues of one kind the ACTIVE pack declares, the latest version of each id."""
    active = discovery.get_active_pack()
    if active is None:
        return ()
    latest: dict[str, PackCatalogue] = {}
    for ref in declared_catalogues(active):
        if ref.kind == kind and (ref.id not in latest or ref.version > latest[ref.id].version):
            latest[ref.id] = ref
    return tuple(latest.values())


_PARSED: dict[tuple[str, str, str, str], Any] = {}
_PARSED_LIMIT = 64


def clear_pack_catalogue_cache() -> None:
    """Drop parsed pack catalogues (tests, and after a pack is installed or removed)."""
    _PARSED.clear()


def load_pack_catalogue(spec: Any, ref: PackCatalogue) -> Any:
    """Read, validate and return the body a declaration points at.

    The file is read on every call and the parsed result is kept by content
    hash, so a pack replaced on disk is picked up without a restart.

    Raises:
        InvalidCatalogueError: The file is missing, not JSON, breaks the
            kind's rules, or carries another id or version than declared.
    """
    origin = f"pack:{ref.slug}:{ref.path}"
    raw = discovery.read_pack_file(ref.slug, ref.path)
    if raw is None:
        raise InvalidCatalogueError(origin, ["unreadable: file not found in the pack"])
    key = (ref.slug, ref.kind, ref.path, hashlib.sha256(raw).hexdigest())
    if key in _PARSED:
        return _PARSED[key]
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidCatalogueError(origin, [f"unreadable: {exc}"]) from exc
    if not isinstance(body, dict):
        raise InvalidCatalogueError(origin, ["unreadable: top level is not an object"])
    parsed = spec.parse_body(body, source=PACK_SOURCE, origin=origin)
    declared, carried = (ref.id, ref.version), (getattr(parsed, "id", None), getattr(parsed, "version", None))
    if declared != carried:
        raise InvalidCatalogueError(origin, [f"declaration_mismatch: manifest says {declared}, body says {carried}"])
    if len(_PARSED) >= _PARSED_LIMIT:
        _PARSED.clear()
    _PARSED[key] = parsed
    return parsed


def pack_default_pin(kind: str, country_code: str | None = None) -> CataloguePin | None:
    """The catalogue the ACTIVE pack wants pinned on a new project, or ``None``.

    A catalogue the pack names for the project's country wins over the one it
    names for every country; a pack names at most one of each per kind, and
    with several the lowest id is taken so the answer is stable. ``None``
    means the pack has no opinion and the caller's own default (country
    packs, jurisdiction, the neutral catalogue) applies.
    """
    country = (country_code or "").strip().upper()
    refs = sorted(active_pack_catalogues(kind), key=lambda c: c.id)
    chosen = next((c for c in refs if country and country in c.default_for_countries), None)
    chosen = chosen or next((c for c in refs if c.default_for_new_projects), None)
    if chosen is None:
        return None
    return CataloguePin(source=PACK_SOURCE, catalogue_id=chosen.id, version=chosen.version)
