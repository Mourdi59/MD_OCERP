# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Catalogues from every source and of every kind, behind one resolver and one store.

Three sources answer "which content does catalogue X version N of kind K have":

* ``shipped``: JSON files in the owning module's ``catalogues/`` folder;
* ``pack``: catalogues a pack ships as files and declares in its manifest
  (:mod:`catalogue_packs`); same JSON schema, read-only, installation-wide;
* ``tenant``: catalogues a company builds itself, stored in the database. It
  clones a shipped catalogue or starts empty, edits a draft and publishes
  immutable versions.

Kinds are registered in :mod:`catalogue_kinds` (``phase_model`` here; further
modules add theirs with one call). A project pins ``(source, id, version)``,
never a Python object, and a published version never changes, so a project on
v1 is untouched by v2 until a manager migrates it with an explicit mapping.

Tenant scope: the platform has no organisation entity; the tenant is the value
``app.core.tenant_scope`` resolves (today the user id, later an org id with no
change here). A tenant only lists, reads, edits and pins its own catalogues. A
project that already pinned a tenant version keeps resolving it for every
member, because the pin, not the reader, names the version.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.project_governance import catalogue_packs
from app.modules.project_governance.catalogue import (
    InvalidCatalogueError,
    UnknownCatalogueError,
    default_catalogue_id_for_country,
    label_of,
    regional_pack_entry,
)
from app.modules.project_governance.catalogue_kinds import PHASE_MODEL_KIND, get_catalogue_kind
from app.modules.project_governance.catalogue_packs import CataloguePin
from app.modules.project_governance.errors import GovernanceError, conflict, not_found
from app.modules.project_governance.models import GovernanceCatalogue, GovernanceCatalogueVersion
from app.modules.project_governance.repository import GovernanceRepository

logger = logging.getLogger(__name__)

SOURCES: tuple[str, ...] = ("shipped", "tenant", "pack")


def content_hash(body: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a catalogue body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def shipped_body(catalogue: Any) -> dict[str, Any]:
    """A shipped catalogue as an editable body (``areas_from`` already resolved)."""
    body = catalogue.model_dump(mode="json")
    if "areas_from" in body:
        body["areas_from"] = None
    return body


def empty_body(code: str, name: str, kind: str = PHASE_MODEL_KIND) -> dict[str, Any]:
    """The draft a catalogue started from nothing begins with (invalid until filled in)."""
    if kind != PHASE_MODEL_KIND:
        return {"id": code, "version": 1, "labels": {"en": name}}
    return {
        "id": code,
        "version": 1,
        "name_key": "",
        "labels": {"en": name},
        "description_key": "",
        "review_status": "unconfirmed",
        "phases": [],
        "gates": [],
        "areas": [],
        "folders": [],
        "document_types": [],
        "readiness_criteria": [],
    }


def _item_key(group: str, item: Any) -> str:
    if not isinstance(item, dict):
        return json.dumps(item, sort_keys=True)
    if group == "folders":
        return f"{item.get('area')}/{item.get('code')}"
    if group == "readiness_criteria":
        return f"{item.get('area')}/{item.get('gate')}/{item.get('code')}"
    return str(item.get("code"))


def diff_bodies(
    old: dict[str, Any], new: dict[str, Any], groups: tuple[str, ...] | None = None
) -> dict[str, dict[str, list[str]]]:
    """Codes added, removed and changed per list group between two bodies."""
    if groups is None:
        groups = get_catalogue_kind(PHASE_MODEL_KIND).diff_groups
    if not groups:
        groups = tuple(sorted(k for k in set(old) | set(new) if isinstance((new.get(k) or old.get(k)), list)))
    out: dict[str, dict[str, list[str]]] = {}
    for group in groups:
        a = {_item_key(group, i): i for i in old.get(group) or []}
        b = {_item_key(group, i): i for i in new.get(group) or []}
        out[group] = {
            "added": sorted(set(b) - set(a)),
            "removed": sorted(set(a) - set(b)),
            "changed": sorted(k for k in set(a) & set(b) if a[k] != b[k]),
        }
    return out


def _kind(kind: str) -> Any:
    try:
        return get_catalogue_kind(kind)
    except UnknownCatalogueError as exc:
        raise not_found("unknown_catalogue") from exc


async def resolve_catalogue(
    session: AsyncSession,
    source: str,
    catalogue_id: str,
    version: int | None,
    *,
    kind: str = PHASE_MODEL_KIND,
    tenant_id: str | None = None,
    from_pin: bool = False,
) -> Any:
    """The one resolver: ``(kind, source, id, version)`` to a validated catalogue.

    A tenant catalogue is private. An id that reaches this function from a
    request resolves only for its own tenant and only while the catalogue is
    not retired, so pass the caller's ``tenant_id``. Without it nothing of the
    tenant source resolves.

    A pack catalogue belongs to the installation. An id from a request
    resolves only in the active pack; a stored pin resolves in every
    discovered pack, so a project keeps its catalogue when another pack
    becomes active.

    Args:
        session: The database session.
        source: ``"shipped"``, ``"tenant"`` or ``"pack"``.
        catalogue_id: Shipped id, the uuid of a tenant catalogue, or the id a pack declares.
        version: The version wanted; ``None`` means the latest published one.
        kind: The catalogue kind.
        tenant_id: The caller's tenant. Required for the tenant source unless
            ``from_pin`` is set.
        from_pin: The triple was read from a pin the server stored (a project's
            model row), never from a request. The pin was checked when it was
            written, and it keeps resolving for every member of the project
            and after the catalogue is retired, so neither check runs. For the
            pack source it widens the search from the active pack to every
            discovered one.

    Raises:
        GovernanceError: ``unknown_catalogue`` (404) for anything that does not
            resolve, a foreign tenant's catalogue included; ``catalogue_retired``
            (409) for the caller's own retired catalogue; ``pack_catalogue_invalid``
            (422) for a pack file that is declared but breaks the kind's rules.
    """
    spec = _kind(kind)
    if source == "shipped":
        try:
            return spec.get_shipped(catalogue_id, version)
        except UnknownCatalogueError as exc:
            raise not_found("unknown_catalogue") from exc
    if source == catalogue_packs.PACK_SOURCE:
        ref = catalogue_packs.find_pack_catalogue(kind, str(catalogue_id), version, active_only=not from_pin)
        if ref is None:
            raise not_found("unknown_catalogue")
        return _load_pack(spec, ref)
    if source == "tenant":
        try:
            cid = uuid.UUID(str(catalogue_id))
        except ValueError as exc:
            raise not_found("unknown_catalogue") from exc
        repo = GovernanceRepository(session)
        head = await session.get(GovernanceCatalogue, cid)
        if head is None or head.kind != kind:
            raise not_found("unknown_catalogue")
        if not from_pin:
            if not tenant_id or head.tenant_id != tenant_id:
                raise not_found("unknown_catalogue")
            if head.state == "retired":
                raise conflict("catalogue_retired")
        if version is None:
            versions = await repo.list_catalogue_versions(cid)
            row = versions[-1] if versions else None
        else:
            row = await repo.get_catalogue_version(cid, version)
        if row is None:
            raise not_found("unknown_catalogue")
        return spec.parse_body(row.body, source="tenant", origin=f"tenant:{cid}@{row.version}")
    raise not_found("unknown_catalogue")


def _load_pack(spec: Any, ref: catalogue_packs.PackCatalogue) -> Any:
    """A declared pack catalogue, or a named refusal that says what is wrong with the file."""
    try:
        return catalogue_packs.load_pack_catalogue(spec, ref)
    except InvalidCatalogueError as exc:
        raise GovernanceError("pack_catalogue_invalid", 422, detail="; ".join(exc.errors[:5])) from exc


def default_catalogue_pin(kind: str = PHASE_MODEL_KIND, country_code: str | None = None) -> CataloguePin | None:
    """The catalogue a new project should pin for ``kind``, or ``None``.

    The active pack is asked first (:func:`catalogue_packs.pack_default_pin`);
    a default whose file does not load is passed over, so a broken pack never
    becomes what new projects pin.

    Without an opinion of the active pack the order is the same for every
    registered kind, and this function is the only place that knows it:

    1. the shipped catalogue the national regional packs name for the
       project's country (``<kind>: {CC: id}`` in a pack's configuration, see
       :func:`catalogue.regional_pack_entry`). A regional pack never loses to
       a shipped file;
    2. the one shipped catalogue of the kind whose ``jurisdiction_countries``
       names the country;
    3. ``None``: no shipped catalogue claims the country, more than one does
       (a choice the module or the user has to make), or the country is empty.
       ``None`` says the owning module pins its neutral file.

    So a module needs no country rule of its own. The phase model alone has a
    last resort here, its neutral catalogue: governance is the owning module
    of that kind.
    """
    for pin in catalogue_packs.pack_default_candidates(kind, country_code):
        ref = catalogue_packs.find_pack_catalogue(kind, pin.catalogue_id, pin.version, active_only=True)
        try:
            if ref is not None:
                catalogue_packs.load_pack_catalogue(_kind(kind), ref)
                return pin
        except InvalidCatalogueError as exc:
            logger.warning("the active pack names a default %s catalogue that does not load: %s", kind, exc)
    if kind != PHASE_MODEL_KIND:
        return _country_pin(kind, country_code)
    cid = default_catalogue_id_for_country(country_code)
    return CataloguePin("shipped", cid, _kind(kind).get_shipped(cid).version)


def _country_pin(kind: str, country_code: str | None) -> CataloguePin | None:
    """The shipped catalogue of ``kind`` for a country: the regional packs' choice, else the one claimant."""
    country = (country_code or "").strip().upper()
    if not country:
        return None
    try:
        shipped = get_catalogue_kind(kind).shipped()
    except UnknownCatalogueError:
        return None
    except InvalidCatalogueError as exc:
        logger.warning("the shipped %s catalogues do not load, so none is a default: %s", kind, exc)
        return None
    newest: dict[str, int] = {}
    claimants: set[str] = set()
    for item in shipped:
        newest[item.id] = max(newest.get(item.id, 0), getattr(item, "version", 0) or 0)
        if country in {str(c).strip().upper() for c in getattr(item, "jurisdiction_countries", None) or ()}:
            claimants.add(item.id)
    try:
        named = regional_pack_entry(kind, country)
    except Exception:
        # The registry of another module failing must not take a project's default with it.
        logger.warning("the regional packs could not be asked for the %s catalogue of %s", kind, country, exc_info=True)
        named = None
    if named in newest:
        return CataloguePin("shipped", named, newest[named])
    if len(claimants) != 1:
        return None
    (catalogue_id,) = claimants
    return CataloguePin("shipped", catalogue_id, newest[catalogue_id])


def _phase_items(phases: Any) -> list[dict[str, Any]]:
    """``[{code, order, name}]`` from parsed phases or raw phase dicts, for the model picker's mapping."""
    out = []
    for p in phases:
        get = p.get if isinstance(p, dict) else (lambda k, _p=p: getattr(_p, k, None))
        out.append({"code": get("code"), "order": get("order"), "name": label_of(get("name_key") or "", get("labels"))})
    return sorted(out, key=lambda x: (x["order"] is None, x["order"] or 0))


class CatalogueStore:
    """Tenant catalogue lifecycle: create (clone or empty), edit, validate, publish, retire, diff."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GovernanceRepository(session)

    async def list_available(
        self, tenant_id: str | None, *, kind: str = PHASE_MODEL_KIND, country_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Shipped catalogues of a kind, the active pack's, and the caller's own, in one list.

        Every item says whether it is the ``default`` for a new project of
        ``country_code``; at most one is.
        """
        items = await self._available(tenant_id, kind)
        pin = default_catalogue_pin(kind, country_code)
        for item in items:
            item["default"] = pin is not None and (item["source"], item["id"]) == (pin.source, pin.catalogue_id)
        return items

    async def _available(self, tenant_id: str | None, kind: str) -> list[dict[str, Any]]:
        spec = _kind(kind)
        items: list[dict[str, Any]] = []
        for ref in catalogue_packs.active_pack_catalogues(kind):
            try:
                c = catalogue_packs.load_pack_catalogue(spec, ref)
            except (InvalidCatalogueError, GovernanceError, OSError) as exc:
                # A pack file that does not load is not offered, and never takes the rest of the
                # list down with it; pinning it by hand names the fault.
                logger.warning("pack catalogue %s:%s is not offered: %s", ref.slug, ref.id, exc)
                continue
            items.append(
                {
                    "kind": kind,
                    "source": catalogue_packs.PACK_SOURCE,
                    "id": c.id,
                    "code": c.id,
                    "name": label_of(getattr(c, "name_key", "") or "", getattr(c, "labels", None)),
                    "state": "published",
                    "versions": [c.version],
                    "latest_version": c.version,
                    "review_status": str(getattr(c, "review_status", "unconfirmed")),
                    "jurisdiction_countries": list(getattr(c, "jurisdiction_countries", ()) or ()),
                    "phases": _phase_items(getattr(c, "phases", ())),
                    "pack": ref.slug,
                }
            )
        for c in spec.shipped():
            items.append(
                {
                    "kind": kind,
                    "source": "shipped",
                    "id": c.id,
                    "code": c.id,
                    "name": label_of(getattr(c, "name_key", "") or "", getattr(c, "labels", None)),
                    "state": "published",
                    "versions": [c.version],
                    "latest_version": c.version,
                    "review_status": str(getattr(c, "review_status", "verified")),
                    "jurisdiction_countries": list(getattr(c, "jurisdiction_countries", ()) or ()),
                    "phases": _phase_items(getattr(c, "phases", ())),
                }
            )
        if tenant_id:
            for row in await self.repo.list_tenant_catalogues(tenant_id, kind=kind):
                version_rows = await self.repo.list_catalogue_versions(row.id)
                versions = [v.version for v in version_rows]
                # The latest published body when there is one, else the draft as written.
                body = version_rows[-1].body if version_rows else (row.draft_body or {})
                items.append(
                    {
                        "kind": kind,
                        "source": "tenant",
                        "id": str(row.id),
                        "code": row.code,
                        "name": label_of("", {"en": row.name}),
                        "state": row.state,
                        "versions": versions,
                        "latest_version": versions[-1] if versions else None,
                        "based_on": row.based_on,
                        "review_status": str((row.draft_body or {}).get("review_status", "unconfirmed")),
                        "jurisdiction_countries": [],
                        "phases": _phase_items(body.get("phases") or ()),
                    }
                )
        return items

    async def get(self, tenant_id: str, catalogue_id: uuid.UUID, *, lock: bool = False) -> GovernanceCatalogue:
        row = await self.repo.get_tenant_catalogue(tenant_id, catalogue_id, lock=lock)
        if row is None:
            raise not_found("unknown_catalogue")
        return row

    async def create(
        self,
        tenant_id: str,
        *,
        code: str,
        name: str,
        based_on_source: str | None,
        based_on_id: str | None,
        based_on_version: int | None,
        actor_id: uuid.UUID | None,
        kind: str = PHASE_MODEL_KIND,
    ) -> GovernanceCatalogue:
        """Clone a catalogue of the same kind the tenant can see, or start an empty draft."""
        _kind(kind)
        for existing in await self.repo.list_tenant_catalogues(tenant_id, kind=kind):
            if existing.code == code:
                raise conflict("catalogue_code_taken")
        if based_on_source:
            if based_on_source == "tenant":
                try:
                    own_id = uuid.UUID(str(based_on_id))
                except ValueError as exc:
                    # A tenant catalogue is addressed by its uuid; anything else names nothing.
                    raise not_found("unknown_catalogue") from exc
                await self.get(tenant_id, own_id)
            # Ownership was checked just above; a retired catalogue may still be cloned
            # into its successor, so the retired refusal of a request id does not apply.
            # A pack catalogue is offered by the active pack only, as for pinning.
            source = await resolve_catalogue(
                self.session,
                based_on_source,
                str(based_on_id),
                based_on_version,
                kind=kind,
                from_pin=based_on_source != catalogue_packs.PACK_SOURCE,
            )
            body = shipped_body(source)
            body["id"] = code
            body["version"] = 1
            body["labels"] = {"en": name}
            origin = str(based_on_id)
            if based_on_source == catalogue_packs.PACK_SOURCE:
                ref = catalogue_packs.find_pack_catalogue(kind, origin, source.version, active_only=True)
                # Two packs may carry one id, so the provenance names the pack as well.
                origin = f"{ref.slug}/{origin}" if ref is not None else origin
            based_on = f"{based_on_source}:{origin}@{source.version}"
        else:
            body = empty_body(code, name, kind)
            based_on = ""
        return await self.repo.add(
            GovernanceCatalogue(
                tenant_id=tenant_id,
                kind=kind,
                code=code,
                name=name,
                based_on=based_on,
                state="draft",
                draft_body=body,
                created_by=actor_id,
            )
        )

    async def update_draft(
        self, tenant_id: str, catalogue_id: uuid.UUID, *, body: dict[str, Any] | None, name: str | None
    ) -> GovernanceCatalogue:
        """Replace the draft body; published versions stay as they are."""
        row = await self.get(tenant_id, catalogue_id, lock=True)
        if row.state == "retired":
            raise conflict("catalogue_retired")
        if body is not None:
            new_body = copy.deepcopy(body)
            new_body["id"] = row.code
            row.draft_body = new_body
        if name is not None:
            row.name = name
        await self.session.flush()
        return row

    @staticmethod
    def validation_errors(row: GovernanceCatalogue) -> list[str]:
        """What the kind's own validator says about the draft."""
        try:
            get_catalogue_kind(row.kind).parse_body(
                row.draft_body or {}, source="tenant", origin=f"tenant:{row.id}:draft"
            )
        except InvalidCatalogueError as exc:
            return list(exc.errors)
        except UnknownCatalogueError:
            return [f"unknown_kind: {row.kind!r}"]
        return []

    async def publish(
        self, tenant_id: str, catalogue_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> GovernanceCatalogueVersion:
        """Freeze the draft as the next immutable version."""
        row = await self.get(tenant_id, catalogue_id, lock=True)
        if row.state == "retired":
            raise conflict("catalogue_retired")
        spec = _kind(row.kind)
        versions = await self.repo.list_catalogue_versions(row.id)
        number = (versions[-1].version + 1) if versions else 1
        body = copy.deepcopy(row.draft_body or {})
        body["id"] = row.code
        body["version"] = number
        try:
            spec.parse_body(body, source="tenant", origin=f"tenant:{row.id}@{number}")
        except InvalidCatalogueError as exc:
            raise GovernanceError(
                "catalogue_invalid", 422, violations=[{"code": "catalogue_invalid", "ref": e} for e in exc.errors]
            ) from exc
        version = await self.repo.add(
            GovernanceCatalogueVersion(
                catalogue_id=row.id,
                version=number,
                body=body,
                content_hash=content_hash(body),
                published_by=actor_id,
                published_at=datetime.now(UTC),
            )
        )
        row.state = "published"
        await self.session.flush()
        return version

    async def retire(self, tenant_id: str, catalogue_id: uuid.UUID) -> GovernanceCatalogue:
        """No new project can pin it; projects already on it keep their version."""
        row = await self.get(tenant_id, catalogue_id, lock=True)
        row.state = "retired"
        await self.session.flush()
        return row

    async def diff(self, tenant_id: str, catalogue_id: uuid.UUID, v_from: int, v_to: int) -> dict[str, Any]:
        """Differences between two published versions of one catalogue."""
        row = await self.get(tenant_id, catalogue_id)
        a = await self.repo.get_catalogue_version(row.id, v_from)
        b = await self.repo.get_catalogue_version(row.id, v_to)
        if a is None or b is None:
            raise not_found("unknown_catalogue")
        groups = _kind(row.kind).diff_groups
        return {"from": v_from, "to": v_to, "groups": diff_bodies(a.body, b.body, groups)}

    async def assert_pinnable(
        self,
        tenant_id: str | None,
        source: str,
        catalogue_id: str,
        version: int | None,
        *,
        kind: str = PHASE_MODEL_KIND,
    ) -> int:
        """Whether this caller may pin the catalogue; returns the version to pin."""
        if source in ("shipped", catalogue_packs.PACK_SOURCE):
            # Installation-wide sources. For a pack only the active pack's catalogues are pinnable.
            return (await resolve_catalogue(self.session, source, catalogue_id, version, kind=kind)).version
        if source != "tenant" or not tenant_id:
            raise not_found("unknown_catalogue")
        try:
            cid = uuid.UUID(str(catalogue_id))
        except ValueError as exc:
            raise not_found("unknown_catalogue") from exc
        row = await self.get(tenant_id, cid)
        if row.kind != kind:
            raise not_found("unknown_catalogue")
        if row.state == "retired":
            raise conflict("catalogue_retired")
        resolved = await resolve_catalogue(self.session, source, catalogue_id, version, kind=kind, tenant_id=tenant_id)
        return resolved.version
