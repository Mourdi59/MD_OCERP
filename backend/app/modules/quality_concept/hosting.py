# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where quality lives in a project's governance model, read from catalogue tags.

Governance models name their phases, gates, areas and documents differently,
so this module never matches one by its code. The catalogue says it as data:
an area or a document type lists what it hosts (``hosts: ["quality"]``) and a
phase lists what entering it enables (``enables: ["construction_start"]``).
Everything is resolved when it is read; no resolved code is stored.

A catalogue that carries no tag answers ``None`` / empty, and the callers say
so (an ``unknown`` evidence item) instead of guessing a code.
"""

from __future__ import annotations

import uuid
from typing import Any

QUALITY_TAG = "quality"
CONSTRUCTION_START = "construction_start"


def _tags(entry: Any, field: str) -> tuple[str, ...]:
    value = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
    return tuple(value or ())


def _code(entry: Any) -> str:
    return str(entry.get("code") if isinstance(entry, dict) else entry.code)


def _group(catalogue: Any, name: str) -> list[Any]:
    value = catalogue.get(name) if isinstance(catalogue, dict) else getattr(catalogue, name, None)
    return list(value or [])


def hosting_area_code(catalogue: Any) -> str | None:
    """The code of the area tagged for quality, or ``None`` when the catalogue tags none."""
    return next((_code(a) for a in _group(catalogue, "areas") if QUALITY_TAG in _tags(a, "hosts")), None)


def frame_document_types(catalogue: Any) -> tuple[str, ...]:
    """Document types tagged for quality: the frame document whose binding binds the concept."""
    return tuple(_code(d) for d in _group(catalogue, "document_types") if QUALITY_TAG in _tags(d, "hosts"))


def phases_enabling(catalogue: Any, tag: str) -> frozenset[str]:
    """Codes of the phases whose entry enables ``tag``."""
    return frozenset(_code(p) for p in _group(catalogue, "phases") if tag in _tags(p, "enables"))


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue, or ``None`` without a governance model."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)
