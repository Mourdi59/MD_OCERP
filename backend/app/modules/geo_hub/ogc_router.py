# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""OGC API - Features routes, mounted under ``/api/v1/geo-hub/ogc``.

Connecting QGIS
---------------
In QGIS: Layer -> Add Layer -> Add WFS / OGC API - Features Layer -> New,
and paste the landing-page URL::

    https://<your-host>/api/v1/geo-hub/ogc

Authentication is required, because the whole point of serving this from
the application rather than from the database is that the per-project
access rules come with it. Either works:

* an ``X-API-Key`` header - create the key under your user profile, then
  in QGIS's connection dialog add an Authentication configuration of type
  "HTTP header" with name ``X-API-Key``. This is the one to use: it does
  not expire mid-session;
* an ``Authorization: Bearer <jwt>`` header, the same token the web UI
  uses. Fine for a quick look, but it expires.

You will see three collections: project anchors, vector overlays and
saved viewpoints. Everything is CRS84 (EPSG:4326, longitude first).

Behaviour notes
---------------
All responses are JSON. The ``f`` parameter is accepted for compatibility
and only ``json`` is supported - we do not serve an HTML browse UI, and
saying otherwise in ``/conformance`` would only send a client looking for
a page that is not there.

Every link is built from the request that asked for it. The module loader
mounts this router at both ``/api/v1/geo-hub`` and the legacy
``/api/v1/geo_hub``, and a deployment may sit behind a path-rewriting
proxy, so a hard-coded prefix would hand out links that 404.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.dependencies import (
    RequirePermissionOrApiKey,
    SessionDep,
    get_optional_user_payload,
    resolve_api_key_principal,
)
from app.modules.geo_hub.ogc_features import (
    COLLECTIONS,
    CONFORMANCE_CLASSES,
    CRS84,
    DEFAULT_LIMIT,
    GEOJSON_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    MAX_LIMIT,
    OPENAPI_MEDIA_TYPE,
    CollectionSpec,
    OgcFeaturesService,
    OgcParameterError,
    feature_collection,
    get_collection,
    items_links,
    link,
    parse_bbox,
    parse_datetime,
    parse_limit,
)

ogc_router = APIRouter(tags=["geo_hub_ogc"])


class _GeoReadPrincipal(RequirePermissionOrApiKey):
    """Authenticate a GIS client and hand back a payload-shaped principal.

    :class:`RequirePermissionOrApiKey` already knows how to accept either a
    bearer token or an ``X-API-Key`` and apply the identical permission
    check to both, but it returns only the caller's user id. The geo_hub
    access helpers - ``_verify_project_owner`` and
    ``list_anchored_projects`` - are written against the JWT payload dict
    and need the ``role`` as well as the ``sub``, so the API-key branch is
    adapted into the same shape here. The authorization decision itself is
    inherited unchanged: a key can never reach further than its owner.
    """

    async def __call__(  # type: ignore[override]
        self,
        request: Request,
        payload: Annotated[dict[str, Any] | None, Depends(get_optional_user_payload)],
    ) -> dict[str, Any]:
        if payload is not None:
            self._authorize(payload.get("role", "") or "", payload.get("permissions", []))
            return payload
        principal = await resolve_api_key_principal(request)
        role = getattr(principal.user, "role", "") or ""
        self._authorize(role, None, principal.scopes)
        return {"sub": str(principal.user.id), "role": role, "permissions": []}


_require_geo_read = _GeoReadPrincipal("geo_hub.read")

PrincipalDep = Annotated[dict[str, Any], Depends(_require_geo_read)]


def _service_root(request: Request, depth: int) -> str:
    """Absolute URL of the OGC service root as seen by this request.

    Args:
        request: The incoming request.
        depth: How many path segments below the service root this route
            sits. ``/ogc/collections/{id}/items`` is three; the landing
            page is zero. Counting relative to the request is what keeps
            the links correct under both mount prefixes and behind a proxy
            that rewrites the path, neither of which a constant survives.

    Returns:
        The service root URL, with no trailing slash and no query string.
    """
    segments = [segment for segment in request.url.path.split("/") if segment]
    if depth:
        segments = segments[: max(len(segments) - depth, 0)]
    return str(request.url.replace(path="/" + "/".join(segments), query="", fragment=""))


def _reject_unsupported_format(fmt: str | None) -> None:
    """Refuse any ``f`` value other than JSON, plainly rather than silently."""
    if fmt is not None and fmt.lower() not in ("json", "geojson", "application/json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported output format '{fmt}'. This service returns JSON only.",
        )


def _bad_parameter(exc: OgcParameterError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _collection_body(spec: CollectionSpec, *, root: str) -> dict[str, Any]:
    """Metadata document for one collection."""
    collection_url = f"{root}/collections/{spec.name}"
    extent: dict[str, Any] = {"spatial": {"bbox": [[-180.0, -90.0, 180.0, 90.0]], "crs": CRS84}}
    if spec.temporal:
        extent["temporal"] = {"interval": [[None, None]], "trs": "http://www.opengis.net/def/uom/ISO-8601/0/Gregorian"}
    return {
        "id": spec.name,
        "title": spec.title,
        "description": spec.description,
        "itemType": "feature",
        "crs": [CRS84],
        "storageCrs": CRS84,
        "extent": extent,
        # Non-standard but honest: a GIS client cannot otherwise tell that
        # these features come from many projects at once, nor that it may
        # narrow them. OGC API - Features allows extra members here.
        "projectScoped": True,
        "additionalParameters": [
            {
                "name": "project_id",
                "description": "Narrow the collection to a single project. Omit to span every project you can read.",
            },
        ],
        "links": [
            link(collection_url, "self", JSON_MEDIA_TYPE, spec.title),
            link(f"{collection_url}/items", "items", GEOJSON_MEDIA_TYPE, f"{spec.title} as GeoJSON"),
            link(root, "root", JSON_MEDIA_TYPE, "Service landing page"),
        ],
    }


# Registered at both ``/ogc`` and ``/ogc/``. The app runs with
# ``redirect_slashes=False`` (see ``app/main.py``), so the two forms are
# genuinely different routes and a missing alias is a 404 rather than a
# redirect. A person pasting a service URL into QGIS types whichever one they
# type, and being wrong about that must not be how they find out the service
# exists. The slashed form is kept out of the schema so the OpenAPI document
# describes one landing page, not two.
@ogc_router.get("", response_model=None, summary="OGC API - Features landing page")
@ogc_router.get("/", response_model=None, include_in_schema=False)
async def ogc_landing_page(
    request: Request,
    _principal: PrincipalDep,
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """The landing page a GIS client is pointed at.

    Paste this URL into QGIS under Layer -> Add Layer -> Add WFS / OGC API
    - Features Layer, with an ``X-API-Key`` or bearer header configured,
    and QGIS will walk the links from here to the collections on its own.
    """
    _reject_unsupported_format(f)
    root = _service_root(request, 0)
    links = [
        link(root, "self", JSON_MEDIA_TYPE, "This document"),
        link(f"{root}/conformance", "conformance", JSON_MEDIA_TYPE, "Conformance classes"),
        link(f"{root}/collections", "data", JSON_MEDIA_TYPE, "Feature collections"),
    ]
    # Only advertise the API description when this deployment actually
    # serves one - a hard-coded /openapi.json link would 404 on any install
    # that turned the schema off, and a broken service-desc is worse than
    # an absent one for a client that follows links.
    openapi_url = getattr(request.app, "openapi_url", None)
    if openapi_url:
        links.append(
            link(
                str(request.url.replace(path=openapi_url, query="", fragment="")),
                "service-desc",
                OPENAPI_MEDIA_TYPE,
                "OpenAPI description of this API",
            ),
        )
    body = {
        "title": "OpenConstructionERP Geo Hub",
        "description": (
            "Project locations, vector overlays and saved viewpoints from OpenConstructionERP, "
            "served as OGC API - Features. Everything is scoped to the projects your account "
            "can read; nothing here is public."
        ),
        "links": links,
    }
    return JSONResponse(content=body, media_type=JSON_MEDIA_TYPE)


@ogc_router.get("/conformance", response_model=None, summary="OGC conformance declaration")
async def ogc_conformance(
    request: Request,
    _principal: PrincipalDep,
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """The conformance classes this service actually implements.

    HTML output is deliberately not claimed - this service is JSON only.
    """
    _reject_unsupported_format(f)
    return JSONResponse(content={"conformsTo": list(CONFORMANCE_CLASSES)}, media_type=JSON_MEDIA_TYPE)


@ogc_router.get("/collections", response_model=None, summary="List feature collections")
async def ogc_collections(
    request: Request,
    _principal: PrincipalDep,
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """Every collection this service publishes.

    The list is the same for every caller; what differs is what the items
    endpoints will show them.
    """
    _reject_unsupported_format(f)
    root = _service_root(request, 1)
    body = {
        "links": [
            link(f"{root}/collections", "self", JSON_MEDIA_TYPE, "Feature collections"),
            link(root, "root", JSON_MEDIA_TYPE, "Service landing page"),
        ],
        "collections": [_collection_body(spec, root=root) for spec in COLLECTIONS],
    }
    return JSONResponse(content=body, media_type=JSON_MEDIA_TYPE)


@ogc_router.get("/collections/{collection_id}", response_model=None, summary="Describe one collection")
async def ogc_collection(
    collection_id: str,
    request: Request,
    _principal: PrincipalDep,
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """Metadata for one collection: extent, CRS and its item links."""
    _reject_unsupported_format(f)
    spec = get_collection(collection_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    root = _service_root(request, 2)
    return JSONResponse(content=_collection_body(spec, root=root), media_type=JSON_MEDIA_TYPE)


@ogc_router.get(
    "/collections/{collection_id}/items",
    response_model=None,
    summary="One page of features as GeoJSON",
)
async def ogc_items(
    collection_id: str,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    bbox: str | None = Query(default=None, description="west,south,east,north in CRS84 (or 6 values with elevation)"),
    datetime_filter: str | None = Query(
        default=None,
        alias="datetime",
        description="RFC 3339 instant or interval, e.g. 2026-01-01T00:00:00Z/..",
    ),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    project_id: uuid.UUID | None = Query(default=None, description="Narrow to a single project"),
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """Return one page of a collection as a GeoJSON ``FeatureCollection``.

    Supports ``bbox`` (envelope intersection), ``datetime`` where the
    collection has a time, ``limit`` / ``offset`` paging with ``next`` and
    ``prev`` links, and the extra ``project_id`` narrowing parameter.

    ``numberMatched`` is present whenever the count is known. It is omitted
    when the underlying scan hit its row ceiling, because at that point the
    only count we could report would be a guess.
    """
    _reject_unsupported_format(f)
    spec = get_collection(collection_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    try:
        parsed_bbox = parse_bbox(bbox)
        start, end = parse_datetime(datetime_filter)
        page_limit = parse_limit(limit)
    except OgcParameterError as exc:
        raise _bad_parameter(exc) from None
    if (start is not None or end is not None) and not spec.temporal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collection '{spec.name}' carries no time and cannot be filtered by datetime",
        )

    service = OgcFeaturesService(session)
    scoped_project = await service._resolve_project_scope(project_id, principal)
    page = await service.page(
        spec,
        principal,
        project_id=scoped_project,
        bbox=parsed_bbox,
        start=start,
        end=end,
        offset=offset,
        limit=page_limit,
    )

    root = _service_root(request, 3)
    items_url = f"{root}/collections/{spec.name}/items"
    body = feature_collection(
        page.features,
        number_matched=page.number_matched,
        links=items_links(
            items_url=items_url,
            collection_url=f"{root}/collections/{spec.name}",
            query={
                "bbox": bbox,
                "datetime": datetime_filter,
                "project_id": str(project_id) if project_id else None,
                "f": f,
            },
            offset=offset,
            limit=page_limit,
            number_returned=len(page.features),
            number_matched=page.number_matched,
        ),
    )
    return JSONResponse(content=body, media_type=GEOJSON_MEDIA_TYPE)


@ogc_router.get(
    "/collections/{collection_id}/items/{feature_id}",
    response_model=None,
    summary="One feature as GeoJSON",
)
async def ogc_item(
    collection_id: str,
    feature_id: str,
    request: Request,
    session: SessionDep,
    principal: PrincipalDep,
    f: str | None = Query(default=None, description="Output format. Only 'json' is supported."),
) -> JSONResponse:
    """Return a single feature.

    A feature that belongs to a project the caller cannot read is reported
    as missing, not as forbidden, so this endpoint cannot be used to find
    out which ids exist.
    """
    _reject_unsupported_format(f)
    spec = get_collection(collection_id)
    if spec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    service = OgcFeaturesService(session)
    feature = await service.one(spec, feature_id, principal)
    if feature is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not found")

    root = _service_root(request, 4)
    body = dict(feature)
    body["links"] = [
        link(
            f"{root}/collections/{spec.name}/items/{feature_id}",
            "self",
            GEOJSON_MEDIA_TYPE,
            "This feature",
        ),
        link(
            f"{root}/collections/{spec.name}",
            "collection",
            JSON_MEDIA_TYPE,
            spec.title,
        ),
    ]
    return JSONResponse(content=body, media_type=GEOJSON_MEDIA_TYPE)


__all__ = ["ogc_router"]
