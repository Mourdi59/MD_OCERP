# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where permits live in a project's governance model, read from catalogue tags at read time.

Governance models name their areas and phases differently, so this module never
matches a code. The pinned governance catalogue says which area hosts the permit
roadmap (``hosts: ["permits"]``) and which hosts the condition register
(``hosts: ["permit_conditions"]``, falling back to the roadmap area when no area
carries that tag), and each phase says what entering it enables
(``enables: ["construction_start"]``, ``["handover"]``, ``["operation"]``).

Nothing resolved here is stored: a project that pins or re-pins its governance
model later is read correctly the next time a gate asks. A project may name its
areas itself (``roadmap_area_code`` / ``conditions_area_code`` on the roadmap);
that is project data and wins over the tag.

A catalogue without the tags resolves to ``None`` / no tags, and the callers
report ``unknown`` instead of staying silent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

ROADMAP_TAG = "permits"
CONDITIONS_TAG = "permit_conditions"


@dataclass(frozen=True)
class PhaseRole:
    """What a phase tag means for permits: the readiness check it calls for and the permit rights it needs."""

    gate: str  # start | handover
    enables: tuple[str, ...]


# Phase tag (module 1 vocabulary) -> the readiness gate and the ``enables`` values of permit types it needs.
PHASE_ROLES: dict[str, PhaseRole] = {
    "construction_start": PhaseRole("start", ("site_start", "construction")),
    "handover": PhaseRole("handover", ("occupation",)),
    "operation": PhaseRole("handover", ("operation",)),
}
# Without a governance phase the roadmap check asks for what the start of construction needs.
DEFAULT_ENABLES: tuple[str, ...] = PHASE_ROLES["construction_start"].enables


def _tags(obj: Any, name: str) -> tuple[str, ...]:
    """Tags of one catalogue area or phase. The one place that reads the tag off the catalogue object."""
    raw = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return tuple(raw or ())


def _items(catalogue: Any, name: str) -> tuple[Any, ...]:
    raw = catalogue.get(name) if isinstance(catalogue, dict) else getattr(catalogue, name, None)
    return tuple(raw or ())


def _code(obj: Any) -> str:
    return str(obj.get("code") if isinstance(obj, dict) else getattr(obj, "code", ""))


def area_hosting(catalogue: Any, tag: str) -> str | None:
    """The code of the area tagged ``hosts: [tag]``, or ``None`` when the catalogue tags none."""
    if catalogue is None:
        return None
    return next((_code(a) for a in _items(catalogue, "areas") if tag in _tags(a, "hosts")), None)


def phase_tags(catalogue: Any) -> dict[str, tuple[str, ...]]:
    """Per phase code, the ``enables`` tags this module understands."""
    if catalogue is None:
        return {}
    return {_code(p): tuple(t for t in _tags(p, "enables") if t in PHASE_ROLES) for p in _items(catalogue, "phases")}


@dataclass(frozen=True)
class Hosting:
    """The resolved place of permits in one project's governance model."""

    roadmap_area: str | None = None
    conditions_area: str | None = None
    phases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    has_model: bool = False

    @property
    def phases_tagged(self) -> bool:
        """Whether any phase of the model says what it enables; if none does, no gate can be matched."""
        return any(self.phases.values())

    def roles(self, phase_code: str | None) -> tuple[PhaseRole, ...]:
        return tuple(PHASE_ROLES[t] for t in self.phases.get(phase_code or "", ()))

    def gates(self, phase_code: str | None) -> tuple[str, ...]:
        """Readiness checks (``start`` / ``handover``) the gate into ``phase_code`` calls for, in a fixed order."""
        wanted = {r.gate for r in self.roles(phase_code)}
        return tuple(g for g in ("start", "handover") if g in wanted)

    def enables(self, phase_code: str | None) -> tuple[str, ...]:
        """``enables`` values a permit type must carry to matter for the gate into ``phase_code``."""
        out: list[str] = []
        for r in self.roles(phase_code):
            out += [e for e in r.enables if e not in out]
        return tuple(out)


def resolve(catalogue: Any, roadmap_override: str = "", conditions_override: str = "") -> Hosting:
    """Pure resolution from one governance catalogue and the project's own overrides."""
    road = roadmap_override or area_hosting(catalogue, ROADMAP_TAG)
    cond = conditions_override or area_hosting(catalogue, CONDITIONS_TAG) or road
    return Hosting(road or None, cond or None, phase_tags(catalogue), catalogue is not None)


async def governance_catalogue(session: Any, project_id: uuid.UUID) -> Any | None:
    """The project's pinned governance catalogue, or ``None`` when the project has no governance model."""
    from app.modules.project_governance.repository import GovernanceRepository
    from app.modules.project_governance.service import GovernanceService

    model = await GovernanceRepository(session).get_model(project_id)
    if model is None:
        return None
    return await GovernanceService(session).catalogue_for(model)


async def project_hosting(session: Any, project_id: uuid.UUID, roadmap: Any = None) -> Hosting:
    """Resolve now, from the catalogue pinned now. Never cached on a row."""
    catalogue = await governance_catalogue(session, project_id)
    return resolve(
        catalogue,
        getattr(roadmap, "roadmap_area_code", "") or "",
        getattr(roadmap, "conditions_area_code", "") or "",
    )
