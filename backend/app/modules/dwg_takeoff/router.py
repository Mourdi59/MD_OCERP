"""‌⁠‍DWG Takeoff API routes.

Endpoints:
    Drawings:
        POST   /drawings/upload               - Upload DWG/DXF file
        GET    /drawings/?project_id=X        - List drawings
        GET    /drawings/{id}                 - Get single drawing with latest version
        DELETE /drawings/{id}                 - Delete drawing
        GET    /drawings/{id}/entities        - Parsed entities (filtered by layers)
        GET    /drawings/{id}/thumbnail       - SVG thumbnail
        PATCH  /drawings/{id}/layers          - Toggle layer visibility

    Annotations:
        POST   /annotations/                  - Create annotation
        GET    /annotations/?drawing_id=X     - List annotations
        PATCH  /annotations/{id}              - Update annotation
        DELETE /annotations/{id}              - Delete annotation
        POST   /annotations/{id}/link-boq     - Link to BOQ position

    Pins:
        GET    /pins/?drawing_id=X            - Task/punchlist pins
"""

import ipaddress
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from app.config import get_settings
from app.core.rate_limiter import upload_limiter
from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.dwg_takeoff.schemas import (
    BoqLinkRequest,
    DwgAnnotationCreate,
    DwgAnnotationResponse,
    DwgAnnotationUpdate,
    DwgDrawingDiffResponse,
    DwgDrawingFromDocument,
    DwgDrawingResponse,
    DwgDrawingScaleUpdate,
    DwgDrawingVersionResponse,
    DwgEntityGroupCreate,
    DwgEntityGroupResponse,
    DwgLayerVisibilityUpdate,
    DwgOfflineReadinessResponse,
)
from app.modules.dwg_takeoff.service import DwgTakeoffService

router = APIRouter(tags=["dwg_takeoff"])
logger = logging.getLogger(__name__)


def _get_service(session: SessionDep) -> DwgTakeoffService:
    return DwgTakeoffService(session)


# ── IDOR helpers (Round-6 audit) ───────────────────────────────────────────
#
# Every read/write endpoint in this module must funnel through one of these
# helpers so that no resource is reachable by guessing a UUID. They resolve
# the resource's owning ``project_id`` and delegate to
# ``verify_project_access`` (404 on both missing and forbidden - never 403,
# never silent 200).


async def _gate_by_drawing(
    drawing_id: uuid.UUID,
    user_id: str | None,
    service: DwgTakeoffService,
    session: SessionDep,
) -> "object":
    """Resolve a DwgDrawing and gate the caller on its project.

    Returns the drawing so callers don't re-fetch (one less round trip).
    A missing drawing or one in a foreign tenant's project both 404 -
    the response is indistinguishable, preventing UUID-existence probes.
    """
    drawing = await service.get_drawing(drawing_id)
    await verify_project_access(drawing.project_id, str(user_id or ""), session)
    return drawing


async def _gate_by_annotation(
    annotation_id: uuid.UUID,
    user_id: str | None,
    service: DwgTakeoffService,
    session: SessionDep,
) -> "object":
    """Resolve a DwgAnnotation and gate the caller on its project."""
    annotation = await service.get_annotation(annotation_id)
    await verify_project_access(annotation.project_id, str(user_id or ""), session)
    return annotation


async def _gate_by_group(
    group_id: uuid.UUID,
    user_id: str | None,
    service: DwgTakeoffService,
    session: SessionDep,
) -> "object":
    """Resolve a DwgEntityGroup → drawing → project, then gate."""
    group = await service.get_entity_group(group_id)
    drawing = await service.get_drawing(group.drawing_id)
    await verify_project_access(drawing.project_id, str(user_id or ""), session)
    return group


def _drawing_to_response(
    item: object,
    latest_version: object | None = None,
) -> DwgDrawingResponse:
    """‌⁠‍Build a DwgDrawingResponse from a DwgDrawing ORM object."""
    version_resp = None
    if latest_version is not None:
        version_resp = _version_to_response(latest_version)
    return DwgDrawingResponse(
        id=item.id,  # type: ignore[attr-defined]
        project_id=item.project_id,  # type: ignore[attr-defined]
        name=item.name,  # type: ignore[attr-defined]
        filename=item.filename,  # type: ignore[attr-defined]
        file_format=item.file_format,  # type: ignore[attr-defined]
        size_bytes=item.size_bytes,  # type: ignore[attr-defined]
        status=item.status,  # type: ignore[attr-defined]
        discipline=item.discipline,  # type: ignore[attr-defined]
        sheet_number=item.sheet_number,  # type: ignore[attr-defined]
        thumbnail_key=item.thumbnail_key,  # type: ignore[attr-defined]
        error_message=item.error_message,  # type: ignore[attr-defined]
        scale_denominator=float(getattr(item, "scale_denominator", 1.0) or 1.0),
        scale_mode=str(getattr(item, "scale_mode", "preset") or "preset"),
        metadata=getattr(item, "metadata_", {}),  # type: ignore[attr-defined]
        created_by=item.created_by,  # type: ignore[attr-defined]
        created_at=item.created_at,  # type: ignore[attr-defined]
        updated_at=item.updated_at,  # type: ignore[attr-defined]
        latest_version=version_resp,
    )


def _version_to_response(item: object) -> DwgDrawingVersionResponse:
    """‌⁠‍Build a DwgDrawingVersionResponse from a DwgDrawingVersion ORM object."""
    return DwgDrawingVersionResponse(
        id=item.id,  # type: ignore[attr-defined]
        drawing_id=item.drawing_id,  # type: ignore[attr-defined]
        version_number=item.version_number,  # type: ignore[attr-defined]
        layers=item.layers,  # type: ignore[attr-defined]
        entities_key=item.entities_key,  # type: ignore[attr-defined]
        entity_count=item.entity_count,  # type: ignore[attr-defined]
        extents=item.extents,  # type: ignore[attr-defined]
        units=item.units,  # type: ignore[attr-defined]
        status=item.status,  # type: ignore[attr-defined]
        metadata=getattr(item, "metadata_", {}),  # type: ignore[attr-defined]
        created_at=item.created_at,  # type: ignore[attr-defined]
        updated_at=item.updated_at,  # type: ignore[attr-defined]
    )


def _annotation_to_response(item: object) -> DwgAnnotationResponse:
    """Build a DwgAnnotationResponse from a DwgAnnotation ORM object."""
    return DwgAnnotationResponse(
        id=item.id,  # type: ignore[attr-defined]
        project_id=item.project_id,  # type: ignore[attr-defined]
        drawing_id=item.drawing_id,  # type: ignore[attr-defined]
        drawing_version_id=item.drawing_version_id,  # type: ignore[attr-defined]
        annotation_type=item.annotation_type,  # type: ignore[attr-defined]
        geometry=item.geometry,  # type: ignore[attr-defined]
        text=item.text,  # type: ignore[attr-defined]
        color=item.color,  # type: ignore[attr-defined]
        line_width=item.line_width,  # type: ignore[attr-defined]
        measurement_value=item.measurement_value,  # type: ignore[attr-defined]
        measurement_unit=item.measurement_unit,  # type: ignore[attr-defined]
        scale_override=getattr(item, "scale_override", None),
        linked_boq_position_id=item.linked_boq_position_id,  # type: ignore[attr-defined]
        linked_task_id=item.linked_task_id,  # type: ignore[attr-defined]
        linked_punch_item_id=item.linked_punch_item_id,  # type: ignore[attr-defined]
        created_by=item.created_by,  # type: ignore[attr-defined]
        metadata=getattr(item, "metadata_", {}),  # type: ignore[attr-defined]
        created_at=item.created_at,  # type: ignore[attr-defined]
        updated_at=item.updated_at,  # type: ignore[attr-defined]
    )


# ── Drawing Upload ──────────────────────────────────────────────────────────


@router.post("/drawings/upload/", response_model=DwgDrawingResponse, status_code=201)
async def upload_drawing(
    file: UploadFile,
    project_id: uuid.UUID = Query(...),
    name: str | None = Query(default=None, max_length=500),
    discipline: str | None = Query(default=None),
    sheet_number: str | None = Query(default=None),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.create")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingResponse:
    """Upload a DWG/DXF file and trigger processing.

    Audit B-DWG-IDOR - was IDOR-on-write. ``project_id`` came in as a
    free-form query parameter and was persisted verbatim, so anyone with
    ``dwg_takeoff.create`` could attach a DWG to another tenant's project.
    We verify access *before* reading the upload body to fail fast.
    """
    await verify_project_access(project_id, str(user_id or ""), session)

    # Use upload_limiter (30/min - matches BIM / documents / takeoff)
    # rather than approval_limiter (20/min, intended for financial
    # mutations). Bench-driven fix: 30-file batch uploads were tripping
    # the wrong limit and surfacing 429s on legitimate workflows.
    allowed, _ = upload_limiter.is_allowed(str(user_id))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": "60"},
        )

    # Validate file extension
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("dwg", "dxf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only .dwg and .dxf files are accepted.",
        )

    # Per product policy, no upload size cap - memory-safety still
    # comes from the streaming downstream pipeline.

    try:
        drawing = await service.upload_drawing(
            project_id,
            file,
            user_id,
            name=name,
            discipline=discipline,
            sheet_number=sheet_number,
        )
        version = await service.get_latest_version(drawing.id)
        return _drawing_to_response(drawing, version)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to upload drawing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to upload drawing - please try again",
        )


@router.post(
    "/drawings/from-document/",
    response_model=DwgDrawingResponse,
    status_code=201,
)
async def import_drawing_from_document(
    data: DwgDrawingFromDocument,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.create")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingResponse:
    """Materialise a DWG/DXF drawing from an existing project Document.

    Powers the Documents / File Manager "Open in DWG Takeoff" action for a
    CAD file that lives only as a Document (uploaded via /files or another
    module) and therefore has no drawing to render - the deep-link used to
    land on a blank page. Idempotent per document: re-opening returns the
    same drawing rather than creating a duplicate.

    Access is gated on the *document's* owning project (resolved server-side
    from the trusted document row), mirroring the IDOR policy on every other
    write in this module - a 404 is returned for both a missing document and
    one in a foreign tenant's project.
    """
    # Resolve the document first to learn its project, then gate. We import
    # the documents service lazily to avoid a module-load-order dependency.
    from app.modules.documents.service import DocumentService

    doc_service = DocumentService(session)
    document = await doc_service.get_document(data.document_id)
    await verify_project_access(document.project_id, str(user_id or ""), session)

    try:
        drawing = await service.import_drawing_from_document(
            data.document_id,
            user_id,
            name=data.name,
            discipline=data.discipline,
        )
        version = await service.get_latest_version(drawing.id)
        return _drawing_to_response(drawing, version)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to import drawing from document")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to open this document in DWG Takeoff - please try again",
        )


# ── Drawing CRUD ────────────────────────────────────────────────────────────


@router.get("/drawings/", response_model=list[DwgDrawingResponse])
async def list_drawings(
    project_id: uuid.UUID = Query(...),
    status_filter: Literal["uploaded", "processing", "ready", "error"] | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[DwgDrawingResponse]:
    """List drawings for a project.

    Audit B-DWG-IDOR - was IDOR. Any user could pass a foreign tenant's
    ``project_id`` and enumerate their drawings. Gated by
    ``verify_project_access`` so foreign projects 404.
    """
    await verify_project_access(project_id, str(user_id or ""), session)
    items, _ = await service.list_drawings(
        project_id,
        offset=offset,
        limit=limit,
        status_filter=status_filter,
    )
    return [_drawing_to_response(i) for i in items]


@router.get("/drawings/{drawing_id}", response_model=DwgDrawingResponse)
async def get_drawing(
    drawing_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingResponse:
    """Get a single drawing with its latest version.

    Audit B-DWG-IDOR - was IDOR. The ``drawing_id`` was trusted blindly.
    """
    drawing = await _gate_by_drawing(drawing_id, user_id, service, session)
    version = await service.get_latest_version(drawing_id)
    return _drawing_to_response(drawing, version)


@router.delete("/drawings/{drawing_id}", status_code=204)
async def delete_drawing(
    drawing_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.delete")),
    service: DwgTakeoffService = Depends(_get_service),
) -> None:
    """Delete a drawing.

    Audit B-DWG-IDOR - was IDOR-on-write. Anyone with ``dwg_takeoff.delete``
    could blow away another tenant's drawing by UUID.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    await service.delete_drawing(drawing_id)


# ── Entities & Thumbnail ────────────────────────────────────────────────────


@router.get("/drawings/{drawing_id}/entities/")
async def get_entities(
    drawing_id: uuid.UUID,
    layers: str | None = Query(default=None, description="Comma-separated visible layer names"),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[dict]:
    """Get parsed entities for a drawing, optionally filtered by visible layers.

    Audit B-DWG-IDOR - was IDOR. Entities expose layer geometry that
    contains takeoff measurements - a juicy target for competitive
    enumeration.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    visible_layers = None
    if layers:
        visible_layers = [layer.strip() for layer in layers.split(",") if layer.strip()]
    return await service.get_entities(drawing_id, visible_layers=visible_layers)


@router.get("/drawings/{drawing_id}/thumbnail/")
async def get_thumbnail(
    drawing_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> Response:
    """Get SVG thumbnail for a drawing.

    Audit B-DWG-IDOR - was IDOR. SVG thumbnails leak both layout and
    proprietary symbology.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    svg_content = await service.get_thumbnail_svg(drawing_id)
    if svg_content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available",
        )
    return Response(content=svg_content, media_type="image/svg+xml")


# ── Revision compare (Item 17) ───────────────────────────────────────────────


@router.get(
    "/drawings/{drawing_id}/versions/",
    response_model=list[DwgDrawingVersionResponse],
)
async def list_drawing_versions(
    drawing_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[DwgDrawingVersionResponse]:
    """List every parsed version of a drawing (newest first).

    Powers the revision-compare version picker. Gated on the drawing's
    owning project - a foreign-tenant or missing drawing both 404.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    versions = await service.list_drawing_versions(drawing_id)
    return [_version_to_response(v) for v in versions]


@router.post(
    "/drawings/{drawing_id}/compare/{other_version_id}",
    response_model=DwgDrawingDiffResponse,
)
async def compare_drawing_versions(
    drawing_id: uuid.UUID,
    other_version_id: uuid.UUID,
    from_version_id: uuid.UUID = Query(
        ...,
        description="Baseline version id (the 'before' side of the diff).",
    ),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingDiffResponse:
    """Compare two versions of a drawing and return the entity/annotation diff.

    ``from_version_id`` is the baseline ("before") and the path
    ``other_version_id`` is the target ("after"). Both must belong to
    ``drawing_id`` (404 otherwise). Linked-to-BOQ annotations whose
    measured value changed carry a money cost impact in the project's
    base currency.

    Access is gated on the drawing's owning project, mirroring the IDOR
    policy on every other read in this module.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    payload = await service.compare_drawing_versions(
        drawing_id,
        from_version_id,
        other_version_id,
    )
    return DwgDrawingDiffResponse(**payload)


# ── Layer Visibility ────────────────────────────────────────────────────────


@router.patch("/drawings/{drawing_id}/scale/", response_model=DwgDrawingResponse)
async def update_drawing_scale(
    drawing_id: uuid.UUID,
    data: DwgDrawingScaleUpdate,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.create")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingResponse:
    """Persist the drawing's scale denominator + active scale mode.

    Audit B-DWG-IDOR - was IDOR-on-write. Scale tampering flips every
    derived measurement on the drawing - a 1:50 plan rescaled to 1:5
    inflates BOQ totals 100×.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    drawing = await service.update_drawing_scale(
        drawing_id,
        scale_denominator=data.scale_denominator,
        scale_mode=data.scale_mode,
    )
    version = await service.get_latest_version(drawing_id)
    return _drawing_to_response(drawing, version)


@router.patch("/drawings/{drawing_id}/layers", response_model=DwgDrawingVersionResponse)
async def update_layer_visibility(
    drawing_id: uuid.UUID,
    data: DwgLayerVisibilityUpdate,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgDrawingVersionResponse:
    """Toggle layer visibility in the latest drawing version.

    Audit B-DWG-IDOR - was IDOR-on-write.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    version = await service.update_layer_visibility(drawing_id, data.layers)
    return _version_to_response(version)


# ── Annotation CRUD ─────────────────────────────────────────────────────────


@router.post("/annotations/", response_model=DwgAnnotationResponse, status_code=201)
async def create_annotation(
    data: DwgAnnotationCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("dwg_takeoff.create")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgAnnotationResponse:
    """Create a new annotation on a drawing.

    Audit B-DWG-IDOR - was IDOR-on-write. ``project_id`` + ``drawing_id``
    were trusted blindly from the body, so anyone with ``dwg_takeoff.create``
    could plant annotations (including measurement values) onto a
    foreign tenant's drawing. Gate both the project and confirm the
    drawing actually belongs to it.
    """
    # First gate the asserted project, then resolve the drawing and
    # confirm consistency. We accept BOTH paths so a body that
    # references a foreign drawing inside the caller's own project 404s
    # (instead of silently linking to the wrong drawing).
    await verify_project_access(data.project_id, str(user_id or ""), session)
    drawing = await service.get_drawing(data.drawing_id)
    if str(drawing.project_id) != str(data.project_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Drawing not found",
        )
    try:
        item = await service.create_annotation(data, user_id)
        return _annotation_to_response(item)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to create annotation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create annotation - please try again",
        )


@router.get("/annotations/", response_model=list[DwgAnnotationResponse])
async def list_annotations(
    drawing_id: uuid.UUID = Query(...),
    annotation_type: str | None = Query(default=None, alias="type"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[DwgAnnotationResponse]:
    """List annotations for a drawing.

    Audit B-DWG-IDOR - was IDOR. Annotations carry measurement_value
    fields that flow into BOQ totals via link-boq.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    items, _ = await service.list_annotations(
        drawing_id,
        offset=offset,
        limit=limit,
        annotation_type=annotation_type,
    )
    return [_annotation_to_response(i) for i in items]


@router.patch("/annotations/{annotation_id}", response_model=DwgAnnotationResponse)
async def update_annotation(
    annotation_id: uuid.UUID,
    data: DwgAnnotationUpdate,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.update")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgAnnotationResponse:
    """Update an annotation.

    Audit B-DWG-IDOR - was IDOR-on-write.
    """
    await _gate_by_annotation(annotation_id, user_id, service, session)
    item = await service.update_annotation(annotation_id, data)
    return _annotation_to_response(item)


@router.delete("/annotations/{annotation_id}", status_code=204)
async def delete_annotation(
    annotation_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.delete")),
    service: DwgTakeoffService = Depends(_get_service),
) -> None:
    """Delete an annotation.

    Audit B-DWG-IDOR - was IDOR-on-write.
    """
    await _gate_by_annotation(annotation_id, user_id, service, session)
    await service.delete_annotation(annotation_id)


# ── BOQ Link ────────────────────────────────────────────────────────────────


@router.post("/annotations/{annotation_id}/link-boq/", response_model=DwgAnnotationResponse)
async def link_to_boq(
    annotation_id: uuid.UUID,
    data: BoqLinkRequest,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.update")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgAnnotationResponse:
    """Link an annotation to a BOQ position.

    Audit B-DWG-IDOR - was IDOR-on-write. Without the gate, a user could
    redirect a foreign tenant's measurement at their own BOQ position
    (poisoning their estimate) or vice versa.
    """
    await _gate_by_annotation(annotation_id, user_id, service, session)
    item = await service.link_annotation_to_boq(
        annotation_id,
        data.position_id,
        push_quantity=data.push_quantity,
    )
    return _annotation_to_response(item)


# ── Pins ────────────────────────────────────────────────────────────────────


@router.get("/pins/", response_model=list[DwgAnnotationResponse])
async def get_pins(
    drawing_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[DwgAnnotationResponse]:
    """Get task/punchlist pins for a drawing.

    Audit B-DWG-IDOR - was IDOR. Pin coordinates + task linkage are
    sensitive (locations of incidents, defect counts).
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    items = await service.get_pins(drawing_id)
    return [_annotation_to_response(i) for i in items]


# ── Entity Groups (RFC 11) ───────────────────────────────────────────────────


def _group_to_response(item: object) -> DwgEntityGroupResponse:
    """Build a DwgEntityGroupResponse from a DwgEntityGroup ORM object."""
    return DwgEntityGroupResponse(
        id=item.id,  # type: ignore[attr-defined]
        drawing_id=item.drawing_id,  # type: ignore[attr-defined]
        entity_ids=list(item.entity_ids or []),  # type: ignore[attr-defined]
        name=item.name,  # type: ignore[attr-defined]
        metadata=getattr(item, "metadata_", {}),
        created_at=item.created_at,  # type: ignore[attr-defined]
        updated_at=item.updated_at,  # type: ignore[attr-defined]
    )


@router.post("/groups/", response_model=DwgEntityGroupResponse, status_code=201)
async def create_entity_group(
    data: DwgEntityGroupCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("dwg_takeoff.create")),
    service: DwgTakeoffService = Depends(_get_service),
) -> DwgEntityGroupResponse:
    """Create a saved group of DWG entities.

    Audit B-DWG-IDOR - was IDOR-on-write. Anyone could attach a saved
    group to another tenant's drawing.
    """
    await _gate_by_drawing(data.drawing_id, user_id, service, session)
    try:
        item = await service.create_entity_group(data, user_id)
        return _group_to_response(item)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to create entity group")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create entity group - please try again",
        )


@router.get("/groups/", response_model=list[DwgEntityGroupResponse])
async def list_entity_groups(
    drawing_id: uuid.UUID = Query(...),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.read")),
    service: DwgTakeoffService = Depends(_get_service),
) -> list[DwgEntityGroupResponse]:
    """List saved entity groups for a drawing.

    Audit B-DWG-IDOR - was IDOR.
    """
    await _gate_by_drawing(drawing_id, user_id, service, session)
    items, _ = await service.list_entity_groups(drawing_id, offset=offset, limit=limit)
    return [_group_to_response(i) for i in items]


@router.delete("/groups/{group_id}", status_code=204)
async def delete_entity_group(
    group_id: uuid.UUID,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    session: SessionDep = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("dwg_takeoff.delete")),
    service: DwgTakeoffService = Depends(_get_service),
) -> None:
    """Delete an entity group.

    Audit B-DWG-IDOR - was IDOR-on-write.
    """
    await _gate_by_group(group_id, user_id, service, session)
    await service.delete_entity_group(group_id)


# ── Offline Readiness (R3 #9) ────────────────────────────────────────────────


def _request_is_loopback(request: Request) -> bool:
    """Return True when the caller reached us over the loopback interface.

    Used to gate the "your files never leave your computer" trust claim: it
    is only literally true when the browser and the backend run on the same
    machine. We read the immediate socket peer (``request.client.host``)
    rather than any ``X-Forwarded-For`` header, because a forwarded value is
    attacker-controllable and a reverse proxy in front of a hosted demo
    would itself connect from loopback - which is exactly the case we must
    NOT treat as local-only.
    """
    client = request.client
    if client is None or not client.host:
        return False
    try:
        return ipaddress.ip_address(client.host).is_loopback
    except ValueError:
        # Non-IP peer (e.g. a UNIX socket name) - treat as not loopback.
        return False


@router.get("/offline-readiness/", response_model=DwgOfflineReadinessResponse)
async def offline_readiness(request: Request) -> DwgOfflineReadinessResponse:
    """Probe local-converter availability for the DWG takeoff page.

    The backend runs fully offline; this endpoint surfaces whether the
    optional DWG-to-data binary is present so the UI can show an
    "Offline Ready" vs "Install converter" badge.

    ``local_only`` is set True only when the request arrived over loopback
    AND the server is not a hosted/production deployment, so the strong
    "files never leave your computer" copy is shown only when it is true.
    On the hosted demo the UI falls back to honest "processed on your
    OpenConstructionERP server" wording.
    """
    payload = DwgTakeoffService.get_offline_readiness()
    settings = get_settings()
    payload["local_only"] = _request_is_loopback(request) and not settings.is_production
    return DwgOfflineReadinessResponse(**payload)
