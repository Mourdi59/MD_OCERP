"""Bordereau de prix API routes.

Endpoints:
    POST   /bordereaux/                              — Create a bordereau
    GET    /bordereaux/?project_id=xxx               — List bordereaux for a project
    GET    /bordereaux/{id}                          — Get bordereau with lines
    PATCH  /bordereaux/{id}                          — Update bordereau metadata
    DELETE /bordereaux/{id}                          — Delete bordereau

    POST   /boqs/{boq_id}/bordereau                  — Attach a bordereau to a BOQ
    DELETE /boqs/{boq_id}/bordereau                  — Detach bordereau from a BOQ

    GET    /bordereaux/{id}/lines                    — List lines
    POST   /bordereaux/{id}/lines                    — Create a line
    PATCH  /bordereaux/{id}/lines/{line_id}          — Update a line (propagates price)
    DELETE /bordereaux/{id}/lines/{line_id}          — Delete a line

    GET    /bordereaux/{id}/lines/{line_id}/components  — List components
    PUT    /bordereaux/{id}/lines/{line_id}/components  — Replace components

    POST   /bordereaux/{id}/resolve                  — Find-or-create a line (dedup)

    POST   /positions/{position_id}/bordereau-link   — Link position to a bordereau line
    DELETE /positions/{position_id}/bordereau-link   — Unlink position
"""

import uuid
from typing import Any

from fastapi import APIRouter, Query, status
from pydantic import BaseModel

from app.dependencies import CurrentUserId, SessionDep
from app.modules.bordereau.schemas import (
    AttachBordereauRequest,
    AttachBordereauResponse,
    BordereauComponentCreate,
    BordereauComponentResponse,
    BordereauCreate,
    BordereauLineCreate,
    BordereauLineResponse,
    BordereauLineUpdate,
    BordereauResponse,
    BordereauUpdate,
    BordereauWithLines,
    PropagationResult,
    ResolveLineRequest,
    ResolveLineResponse,
)
from app.modules.bordereau.service import BordereauService

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────────

def _svc(session: SessionDep) -> BordereauService:
    return BordereauService(session)


def _comp_to_resp(c: Any) -> BordereauComponentResponse:
    return BordereauComponentResponse(
        id=c.id,
        line_id=c.line_id,
        cost_item_id=getattr(c, "cost_item_id", None),
        description=c.description,
        resource_type=getattr(c, "resource_type", None),
        factor=float(c.factor or "1.0"),
        quantity=float(c.quantity or "1.0"),
        unit=c.unit,
        unit_cost=float(c.unit_cost or "0"),
        total=float(c.total or "0"),
        sort_order=c.sort_order,
    )


def _line_to_resp(line: Any, position_count: int = 0) -> BordereauLineResponse:
    return BordereauLineResponse(
        id=line.id,
        bordereau_id=line.bordereau_id,
        reference_code=line.reference_code,
        designation=line.designation,
        unit=line.unit,
        unit_rate=float(line.unit_rate or "0"),
        is_assembly=line.is_assembly,
        source=line.source,
        version=line.version,
        sort_order=line.sort_order,
        position_count=position_count,
        components=[_comp_to_resp(c) for c in (getattr(line, "components", None) or [])],
    )


def _bordereau_to_resp(
    b: Any, line_count: int = 0, attached_boq_count: int = 0,
) -> BordereauResponse:
    return BordereauResponse(
        id=b.id,
        project_id=b.project_id,
        name=b.name,
        description=b.description,
        currency=b.currency,
        status=b.status,
        is_locked=b.is_locked,
        created_at=b.created_at.isoformat() if hasattr(b.created_at, "isoformat") else str(b.created_at),
        updated_at=b.updated_at.isoformat() if hasattr(b.updated_at, "isoformat") else str(b.updated_at),
        line_count=line_count,
        attached_boq_count=attached_boq_count,
    )


# ── Bordereau CRUD ──────────────────────────────────────────────────────────

@router.post(
    "/bordereaux/",
    response_model=BordereauResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bordereau(
    data: BordereauCreate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> BordereauResponse:
    svc = _svc(session)
    bordereau = await svc.create_bordereau(
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        currency=data.currency,
    )
    return _bordereau_to_resp(bordereau)


@router.get("/bordereaux/", response_model=list[BordereauResponse])
async def list_bordereaux(
    session: SessionDep,
    current_user_id: CurrentUserId,
    project_id: uuid.UUID = Query(...),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[BordereauResponse]:
    svc = _svc(session)
    bordereaux, _ = await svc.list_for_project(project_id, offset=offset, limit=limit)
    result = []
    for b in bordereaux:
        lines = await svc.line_repo.list_for_bordereau(b.id)
        attached_count = await svc.repo.count_attached_boqs(b.id)
        result.append(_bordereau_to_resp(b, line_count=len(lines), attached_boq_count=attached_count))
    return result


@router.get("/bordereaux/{bordereau_id}", response_model=BordereauWithLines)
async def get_bordereau(
    bordereau_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> BordereauWithLines:
    svc = _svc(session)
    bordereau = await svc.get_bordereau(bordereau_id)
    lines = await svc.line_repo.list_for_bordereau(bordereau_id)
    attached_count = await svc.repo.count_attached_boqs(bordereau_id)

    line_responses = []
    for line in lines:
        pos_count = await svc.line_repo.count_linked_positions(line.id)
        line_responses.append(_line_to_resp(line, position_count=pos_count))

    resp = _bordereau_to_resp(bordereau, line_count=len(lines), attached_boq_count=attached_count)
    return BordereauWithLines(**resp.model_dump(), lines=line_responses)


@router.patch("/bordereaux/{bordereau_id}", response_model=BordereauResponse)
async def update_bordereau(
    bordereau_id: uuid.UUID,
    data: BordereauUpdate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> BordereauResponse:
    svc = _svc(session)
    fields = data.model_dump(exclude_none=True)
    bordereau = await svc.update_bordereau(bordereau_id, **fields)
    lines = await svc.line_repo.list_for_bordereau(bordereau_id)
    attached_count = await svc.repo.count_attached_boqs(bordereau_id)
    return _bordereau_to_resp(bordereau, line_count=len(lines), attached_boq_count=attached_count)


@router.delete("/bordereaux/{bordereau_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bordereau(
    bordereau_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> None:
    svc = _svc(session)
    await svc.delete_bordereau(bordereau_id)


# ── Attach / Detach ─────────────────────────────────────────────────────────

@router.post(
    "/boqs/{boq_id}/bordereau",
    response_model=AttachBordereauResponse,
    status_code=status.HTTP_200_OK,
)
async def attach_bordereau(
    boq_id: uuid.UUID,
    data: AttachBordereauRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> AttachBordereauResponse:
    svc = _svc(session)
    positions_linked = await svc.attach_to_boq(boq_id, data.bordereau_id)
    return AttachBordereauResponse(
        boq_id=boq_id,
        bordereau_id=data.bordereau_id,
        attached=True,
        positions_linked=positions_linked,
    )


@router.delete("/boqs/{boq_id}/bordereau", status_code=status.HTTP_204_NO_CONTENT)
async def detach_bordereau(
    boq_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> None:
    svc = _svc(session)
    await svc.detach_from_boq(boq_id)


# ── Lines ───────────────────────────────────────────────────────────────────

@router.get("/bordereaux/{bordereau_id}/lines", response_model=list[BordereauLineResponse])
async def list_lines(
    bordereau_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[BordereauLineResponse]:
    svc = _svc(session)
    lines = await svc.list_lines(bordereau_id)
    result = []
    for line in lines:
        pos_count = await svc.line_repo.count_linked_positions(line.id)
        result.append(_line_to_resp(line, position_count=pos_count))
    return result


@router.post(
    "/bordereaux/{bordereau_id}/lines",
    response_model=BordereauLineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_line(
    bordereau_id: uuid.UUID,
    data: BordereauLineCreate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> BordereauLineResponse:
    svc = _svc(session)
    line = await svc.create_line(
        bordereau_id,
        reference_code=data.reference_code,
        designation=data.designation,
        unit=data.unit,
        unit_rate=data.unit_rate,
        is_assembly=data.is_assembly,
        source=data.source,
        metadata=data.metadata,
    )
    return _line_to_resp(line)


@router.patch(
    "/bordereaux/{bordereau_id}/lines/{line_id}",
    response_model=PropagationResult,
)
async def update_line(
    bordereau_id: uuid.UUID,
    line_id: uuid.UUID,
    data: BordereauLineUpdate,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> PropagationResult:
    svc = _svc(session)
    line, affected_boq_ids, positions_updated, locked_skipped = await svc.update_line(
        line_id,
        designation=data.designation,
        unit=data.unit,
        unit_rate=data.unit_rate,
        reference_code=data.reference_code,
        is_assembly=data.is_assembly,
        version=data.version,
        metadata=data.metadata,
    )
    return PropagationResult(
        line_id=line.id,
        affected_boq_ids=affected_boq_ids,
        positions_updated=positions_updated,
        locked_boqs_skipped=locked_skipped,
    )


@router.delete(
    "/bordereaux/{bordereau_id}/lines/{line_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_line(
    bordereau_id: uuid.UUID,
    line_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> None:
    svc = _svc(session)
    await svc.delete_line(line_id)


# ── Components ──────────────────────────────────────────────────────────────

@router.get(
    "/bordereaux/{bordereau_id}/lines/{line_id}/components",
    response_model=list[BordereauComponentResponse],
)
async def list_components(
    bordereau_id: uuid.UUID,
    line_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> list[BordereauComponentResponse]:
    svc = _svc(session)
    comps = await svc.list_components(line_id)
    return [_comp_to_resp(c) for c in comps]


@router.put(
    "/bordereaux/{bordereau_id}/lines/{line_id}/components",
    response_model=PropagationResult,
)
async def replace_components(
    bordereau_id: uuid.UUID,
    line_id: uuid.UUID,
    data: list[BordereauComponentCreate],
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> PropagationResult:
    svc = _svc(session)
    components_data = [c.model_dump() for c in data]
    line, affected_boq_ids, positions_updated, locked_skipped = await svc.replace_components(
        line_id, components_data,
    )
    return PropagationResult(
        line_id=line.id,
        affected_boq_ids=affected_boq_ids,
        positions_updated=positions_updated,
        locked_boqs_skipped=locked_skipped,
    )


# ── Resolve (dedup) ─────────────────────────────────────────────────────────

@router.post("/bordereaux/{bordereau_id}/resolve", response_model=ResolveLineResponse)
async def resolve_line(
    bordereau_id: uuid.UUID,
    data: ResolveLineRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> ResolveLineResponse:
    svc = _svc(session)
    line, created = await svc.resolve_line(
        bordereau_id,
        reference_code=data.reference_code,
        designation=data.designation,
        unit=data.unit,
    )
    return ResolveLineResponse(line=_line_to_resp(line), created=created)


# ── Position link / unlink ──────────────────────────────────────────────────

class LinkPositionRequest(BaseModel):
    line_id: uuid.UUID


@router.post("/positions/{position_id}/bordereau-link", status_code=status.HTTP_200_OK)
async def link_position(
    position_id: uuid.UUID,
    data: LinkPositionRequest,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> dict:
    svc = _svc(session)
    position = await svc.link_position_to_line(position_id, data.line_id)
    return {
        "position_id": str(position.id),
        "bordereau_line_id": str(position.bordereau_line_id),
        "unit_rate": float(position.unit_rate or "0"),
    }


@router.delete("/positions/{position_id}/bordereau-link", status_code=status.HTTP_200_OK)
async def unlink_position(
    position_id: uuid.UUID,
    session: SessionDep,
    current_user_id: CurrentUserId,
) -> dict:
    svc = _svc(session)
    position = await svc.unlink_position(position_id)
    return {
        "position_id": str(position.id),
        "bordereau_line_id": None,
        "unit_rate": float(position.unit_rate or "0"),
    }
