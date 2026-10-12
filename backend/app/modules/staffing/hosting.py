# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where staffing lives in a project's governance model, read from catalogue tags.

Governance models name their phases, gates, areas and documents differently,
so this module never matches one by its code. The catalogue says it as data:
an area or a document type lists what it hosts (``hosts: ["staffing"]``) and a
phase lists what entering it enables (``enables: ["construction_start"]``).
Everything is resolved when it is read; no resolved code is stored.

A catalogue that carries no tag answers ``None`` / empty, and the callers say
so (an ``unknown`` evidence item, a refused submission) instead of guessing.
"""

from __future__ import annotations

import uuid
from typing import Any

STAFFING_TAG = "staffing"


def _tags(entry: Any, field: str) -> tuple[str, ...]:
    value = entry.get(field) if isinstance(entry, dict) else getattr(entry, field, None)
    return tuple(value or ())


def _code(entry: Any) -> str:
    return str(entry.get("code") if isinstance(entry, dict) else entry.code)


def _group(catalogue: Any, name: str) -> list[Any]:
    if catalogue is None:
        return []
    value = catalogue.get(name) if isinstance(catalogue, dict) else getattr(catalogue, name, None)
    return list(value or [])


def hosting_area_code(catalogue: Any) -> str | None:
    """The code of the area tagged for staffing, or ``None`` when the catalogue tags none."""
    return next((_code(a) for a in _group(catalogue, "areas") if STAFFING_TAG in _tags(a, "hosts")), None)


def frame_document_types(catalogue: Any) -> tuple[str, ...]:
    """Document types tagged for staffing: the frame document whose binding approves the plan."""
    return tuple(_code(d) for d in _group(catalogue, "document_types") if STAFFING_TAG in _tags(d, "hosts"))


def phases_enabling(catalogue: Any, tag: str) -> frozenset[str]:
    """Codes of the phases whose entry enables ``tag``."""
    return frozenset(_code(p) for p in _group(catalogue, "phases") if tag in _tags(p, "enables"))


def enabled_by(catalogue: Any, phase_code: str | None) -> frozenset[str]:
    """What entering the phase ``phase_code`` enables: the tags a gate into it stands for."""
    return frozenset(t for p in _group(catalogue, "phases") if _code(p) == phase_code for t in _tags(p, "enables"))


def enabled_tags(catalogue: Any) -> frozenset[str]:
    """Every tag some phase of the catalogue enables."""
    return frozenset(t for p in _group(catalogue, "phases") for t in _tags(p, "enables"))


async def project_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue, or ``None`` without a governance model."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)
