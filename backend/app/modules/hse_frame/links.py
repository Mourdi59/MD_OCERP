# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Resolvers for link kinds: read another module's row, never copy it.

One entry per kind in ``vocab.LINK_KINDS``. A resolver loads the row by id,
checks it belongs to the project (a row of another project resolves to
``None`` and the caller answers 404), and reads a few display facts. The
owning module is imported lazily: a module that is not installed resolves to
``None`` for its kinds, so a link to it is refused instead of stored unchecked.
"""

from __future__ import annotations

import importlib
import uuid
from typing import Any

from sqlalchemy import select

# kind -> (module path, class name, number attribute, title attribute or None, date attribute or None)
_KINDS: dict[str, tuple[str, str, str | None, str | None, str | None]] = {
    "permit_condition": ("app.modules.permits.models", "PermitCondition", "number", "text", "due_date"),
    "safety_incident": ("app.modules.safety.models", "SafetyIncident", "incident_number", "title", "incident_date"),
    "safety_observation": (
        "app.modules.safety.models",
        "SafetyObservation",
        "observation_number",
        "description",
        None,
    ),
    "hse_ptw": ("app.modules.hse_advanced.models", "PermitToWork", "permit_number", "description", "work_end"),
    "hse_jsa": ("app.modules.hse_advanced.models", "JobSafetyAnalysis", None, "task_description", "work_date"),
    "hse_audit": ("app.modules.hse_advanced.models", "SafetyAudit", "audit_type", None, "conducted_at"),
    "hse_capa": ("app.modules.hse_advanced.models", "CorrectiveAction", None, "title", "target_date"),
    "quality_inspection": (
        "app.modules.inspections.models",
        "QualityInspection",
        "inspection_number",
        None,
        None,
    ),
    "cc_inspection": ("app.modules.construction_control.models", "Inspection", "inspection_number", None, None),
}


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _model(kind: str) -> Any | None:
    spec = _KINDS.get(kind)
    if spec is None:
        return None
    try:
        return getattr(importlib.import_module(spec[0]), spec[1])
    except (ImportError, AttributeError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = value.isoformat() if hasattr(value, "isoformat") else str(value)
    return text if len(text) <= 160 else text[:157] + "..."


def fact_of(kind: str, row: Any) -> dict[str, Any]:
    """The display facts of a resolved row: number, title, status, date."""
    _module, _cls, number, title, day = _KINDS[kind]
    return {
        "kind": kind,
        "number": _text(getattr(row, number, None)) if number else None,
        "title": _text(getattr(row, title, None)) if title else None,
        "status": _text(getattr(row, "status", None)),
        "date": _text(getattr(row, day, None)) if day else None,
        "severity": _text(getattr(row, "severity", None)),
    }


async def resolve(session: Any, project_id: uuid.UUID, kind: str, link_id: str) -> dict[str, Any] | None:
    """The facts of a linked row, or ``None`` when it does not exist in this project."""
    model = _model(kind)
    rid = _uuid(link_id)
    if model is None or rid is None:
        return None
    row = await session.get(model, rid)
    if row is None or getattr(row, "project_id", None) != project_id:
        return None
    return fact_of(kind, row)


def known_kinds() -> tuple[str, ...]:
    """The link kinds whose owning module is installed."""
    return tuple(k for k in _KINDS if _model(k) is not None)


async def candidates(
    session: Any, project_id: uuid.UUID, kind: str, query: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """The project's rows of ``kind`` a link can point at, newest first, optionally narrowed by text."""

    model = _model(kind)
    if model is None:
        return []
    stmt = select(model).where(model.project_id == project_id).order_by(model.created_at.desc()).limit(500)
    out = []
    needle = query.strip().lower()
    for row in (await session.execute(stmt)).scalars():
        fact = fact_of(kind, row)
        text = " ".join(str(v) for v in (fact["number"], fact["title"], fact["status"]) if v).lower()
        if needle and needle not in text:
            continue
        out.append({"id": str(row.id), **fact})
        if len(out) >= limit:
            break
    return out
