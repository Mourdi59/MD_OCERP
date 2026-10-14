# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The data room: the governance folder tree materialised into the documents module's folders.

The phase model of a project lists working folders per management area and phase. Until they are
materialised they are catalogue data nobody can file a document into. ``materialise`` writes them as rows
of ``oe_documents_folder`` (one root folder per area, the catalogue's folders below it), keyed by
``<area>/<code>`` so running it twice finds what it made before: nothing is duplicated, a changed name or
position is updated, a folder a user added by hand is never touched, and a folder the catalogue dropped
stays with its documents.

``place_document`` files a document into the folder of the area that hosts its subject, so the documents
of each module land in the right folder without the module knowing the tree.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, DocumentFolder
from app.modules.project_governance import public as governance
from app.modules.project_handbook.errors import HandbookError, not_found

logger = logging.getLogger(__name__)

AREA_PREFIX = "area"
CATALOGUE = "catalogue"


def area_code_of(area: str) -> str:
    """Folder code of an area's root folder."""
    return f"{AREA_PREFIX}/{area}"


def folder_code_of(area: str, code: str) -> str:
    """Folder code of a catalogue folder; folder codes repeat across areas, so the area is part of the key."""
    return f"{area}/{code}"


def _name(labels: dict[str, str] | None, fallback: str) -> str:
    return (labels or {}).get("en") or next(iter((labels or {}).values()), "") or fallback.replace("_", " ")


async def materialise(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    """Create or update the project's folders from its pinned phase model; idempotent.

    Returns:
        ``{"created": n, "updated": n, "unchanged": n, "folders": total}``.

    Raises:
        HandbookError: ``no_governance_model`` when the project pinned no phase model.
    """
    catalogue = await governance.project_catalogue(session, project_id)
    if catalogue is None:
        raise HandbookError("no_governance_model", 409)
    existing = {
        f.code: f
        for f in (
            await session.execute(select(DocumentFolder).where(DocumentFolder.project_id == project_id))
        ).scalars()
    }
    desired: list[dict[str, Any]] = []
    order = 0
    for area in sorted(catalogue.areas, key=lambda a: (a.order, a.code)):
        order += 1
        desired.append(
            {
                "code": area_code_of(area.code),
                "parent": None,
                "name": _name(area.labels, area.code),
                "name_key": area.name_key if not area.labels else "",
                "area_code": area.code,
                "phase_code": "",
                "sort_order": order,
            }
        )
    for folder in catalogue.folders:
        order += 1
        desired.append(
            {
                "code": folder_code_of(folder.area, folder.code),
                "parent": folder_code_of(folder.area, folder.parent) if folder.parent else area_code_of(folder.area),
                "name": _name(folder.labels, folder.code),
                "name_key": folder.name_key if not folder.labels else "",
                "area_code": folder.area,
                "phase_code": folder.phase,
                "sort_order": order,
            }
        )
    created = updated = unchanged = 0
    rows: dict[str, DocumentFolder] = {}
    for spec in desired:
        row = existing.get(spec["code"])
        if row is None:
            row = DocumentFolder(
                project_id=project_id, source=CATALOGUE, **{k: v for k, v in spec.items() if k != "parent"}
            )
            session.add(row)
            created += 1
        elif row.source == CATALOGUE:
            changed = False
            for key in ("name", "name_key", "area_code", "phase_code", "sort_order"):
                if getattr(row, key) != spec[key]:
                    setattr(row, key, spec[key])
                    changed = True
            updated += 1 if changed else 0
            unchanged += 0 if changed else 1
        else:
            # A folder a user made under a catalogue code is theirs; the catalogue never rewrites it.
            unchanged += 1
        rows[spec["code"]] = row
    await session.flush()
    for spec in desired:
        row = rows[spec["code"]]
        if row.source != CATALOGUE:
            continue
        parent = rows.get(spec["parent"]) if spec["parent"] else None
        wanted = parent.id if parent is not None else None
        if row.parent_id != wanted:
            row.parent_id = wanted
            updated += 1
    await session.flush()
    total = (
        await session.execute(
            select(func.count()).select_from(DocumentFolder).where(DocumentFolder.project_id == project_id)
        )
    ).scalar_one()
    return {"created": created, "updated": updated, "unchanged": unchanged, "folders": int(total)}


async def _category_filter(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID | None) -> Any:
    """``None`` when the caller reads every document; else the set of readable categories.

    The same decision the document register takes: owners and admins read everything, a member reads the
    categories whose folder carries no grant, or whose grant covers them.
    """
    if user_id is None:
        return None
    from app.modules.documents.folder_permissions_service import (
        effective_permissions_for,
        is_project_owner,
        readable_document_scopes,
        restricted_scopes_for_project,
    )

    if await is_project_owner(session, project_id, user_id):
        return None
    from app.modules.users.repository import UserRepository

    user = await UserRepository(session).get_by_id(user_id)
    if user is not None and getattr(user, "role", "") == "admin":
        return None
    grants = await effective_permissions_for(session, project_id=project_id, user_id=user_id)
    restricted = await restricted_scopes_for_project(session, project_id)
    return frozenset(readable_document_scopes(grants=grants, restricted=restricted))


def _readable(category: str | None, readable: Any) -> bool:
    if readable is None:
        return True
    from app.modules.documents.folder_permissions_models import FOLDER_SCOPED_CATEGORIES

    return (category if category in FOLDER_SCOPED_CATEGORIES else None) in readable


async def tree(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    """The folder tree with the number of documents the caller may read in each folder.

    ``documents`` counts the folder itself, ``documents_total`` the folder and everything below it.
    """
    folders = list(
        (
            await session.execute(
                select(DocumentFolder)
                .where(DocumentFolder.project_id == project_id)
                .order_by(DocumentFolder.sort_order, DocumentFolder.code)
            )
        ).scalars()
    )
    readable = await _category_filter(session, project_id, user_id)
    docs = (
        await session.execute(select(Document.folder_id, Document.category).where(Document.project_id == project_id))
    ).all()
    direct: dict[uuid.UUID | None, int] = {}
    for folder_id, category in docs:
        if _readable(category, readable):
            direct[folder_id] = direct.get(folder_id, 0) + 1
    known = {f.id for f in folders}
    by_parent: dict[uuid.UUID | None, list[DocumentFolder]] = {}
    for f in folders:
        by_parent.setdefault(f.parent_id if f.parent_id in known else None, []).append(f)
    totals: dict[uuid.UUID, int] = {}

    def total(folder: DocumentFolder) -> int:
        if folder.id not in totals:
            totals[folder.id] = direct.get(folder.id, 0) + sum(total(c) for c in by_parent.get(folder.id, []))
        return totals[folder.id]

    items = [
        {
            "id": str(f.id),
            "code": f.code,
            "parent_id": str(f.parent_id) if f.parent_id in known else None,
            "name": f.name,
            "name_key": f.name_key or None,
            "area_code": f.area_code,
            "phase_code": f.phase_code,
            "source": f.source,
            "sort_order": f.sort_order,
            "documents": direct.get(f.id, 0),
            "documents_total": total(f),
        }
        for f in folders
    ]
    unfiled = sum(n for fid, n in direct.items() if fid is None or fid not in known)
    return {"folders": items, "unfiled": unfiled, "documents": sum(direct.values())}


async def area_summary(session: AsyncSession, project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Per applicable area: how many folders it has in the data room and how many documents are filed in them."""
    areas = await governance.project_areas(session, project_id)
    rows = (
        await session.execute(
            select(DocumentFolder.id, DocumentFolder.area_code).where(DocumentFolder.project_id == project_id)
        )
    ).all()
    folder_area = {fid: area for fid, area in rows}
    folders_per: dict[str, int] = {}
    for area in folder_area.values():
        folders_per[area] = folders_per.get(area, 0) + 1
    counts: dict[str, int] = {}
    if folder_area:
        filed = (
            await session.execute(
                select(Document.folder_id, func.count())
                .where(Document.project_id == project_id, Document.folder_id.in_(list(folder_area)))
                .group_by(Document.folder_id)
            )
        ).all()
        for fid, n in filed:
            counts[folder_area[fid]] = counts.get(folder_area[fid], 0) + int(n)
    return [
        {
            "area_code": a.code,
            "label": a.label,
            "name_override": a.name_override,
            "folders": max(folders_per.get(a.code, 0) - 1, 0),
            "documents": counts.get(a.code, 0),
        }
        for a in areas
        if a.status == "applicable"
    ]


async def folder_for(
    session: AsyncSession, project_id: uuid.UUID, *, subject: str | None = None, area_code: str | None = None
) -> DocumentFolder | None:
    """The folder documents of an area (or of the area that hosts ``subject``) are filed in.

    The folder of the area's first handbook chapter that names one, else the area's root folder; ``None``
    when the data room was not materialised or no area hosts the subject.
    """
    from app.modules.project_handbook.models import HandbookChapter

    area = area_code
    if area is None and subject:
        host = await governance.host_for(session, project_id, subject)
        area = host.area_code if host is not None else None
    if not area:
        return None
    chapter_folder = (
        await session.execute(
            select(HandbookChapter.folder_code)
            .where(HandbookChapter.project_id == project_id, HandbookChapter.area_code == area)
            .where(HandbookChapter.folder_code != "")
            .order_by(HandbookChapter.sort_order)
            .limit(1)
        )
    ).scalar_one_or_none()
    codes = [folder_code_of(area, chapter_folder)] if chapter_folder else []
    codes.append(area_code_of(area))
    rows = {
        f.code: f
        for f in (
            await session.execute(
                select(DocumentFolder).where(DocumentFolder.project_id == project_id, DocumentFolder.code.in_(codes))
            )
        ).scalars()
    }
    return next((rows[c] for c in codes if c in rows), None)


async def place_document(
    session: AsyncSession,
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    folder_code: str | None = None,
    subject: str | None = None,
    area_code: str | None = None,
) -> DocumentFolder:
    """File a document of the project into a folder, named by code or found by subject or area.

    Raises:
        HandbookError: 404 for a document or folder of another project, 409 when no folder fits.
    """
    document = (
        await session.execute(select(Document).where(Document.id == document_id, Document.project_id == project_id))
    ).scalar_one_or_none()
    if document is None:
        raise not_found("document_not_found")
    if folder_code:
        folder = (
            await session.execute(
                select(DocumentFolder).where(
                    DocumentFolder.project_id == project_id, DocumentFolder.code == folder_code
                )
            )
        ).scalar_one_or_none()
        if folder is None:
            raise not_found("folder_not_found")
    else:
        folder = await folder_for(session, project_id, subject=subject, area_code=area_code)
        if folder is None:
            raise HandbookError("no_folder_for_subject", 409)
    document.folder_id = folder.id
    await session.flush()
    return folder
