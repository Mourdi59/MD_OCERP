# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Where permits live in a project's governance model, asked of module 1's read port at read time.

Governance models name their areas, documents and phases differently, so this
module never matches a code. The port (:mod:`app.modules.project_governance.public`)
answers two questions from the tags of the pinned catalogue:

* which frame document hosts the subject ``permits`` (and with it which area);
* which phases, once entered, enable a capability: ``construction_start``,
  ``handover``, ``operation``.

The capability names are governance vocabulary. What a permit type enables
(``site_start``, ``construction``, ``occupation``, ``operation``) is the permit
catalogue's own vocabulary; :data:`PHASE_ROLES` maps the one to the other
explicitly and nothing assumes the strings match.

Nothing resolved here is stored: a project that pins or re-pins its governance
model later is read correctly the next time a gate asks. A project may name its
areas itself (``roadmap_area_code`` / ``conditions_area_code`` on the roadmap);
that is project data and wins over the tag. The condition register lives in the
roadmap's area unless the project says otherwise.

A model that hosts permits nowhere resolves to ``None``, one that tags no phase
to no gates, and the callers report ``unknown`` instead of staying silent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

SUBJECT = "permits"


@dataclass(frozen=True)
class PhaseRole:
    """What a phase capability means for permits: the readiness check and the permit rights it needs."""

    gate: str  # start | handover
    enables: tuple[str, ...]


# Governance phase capability -> the readiness gate and the ``enables`` values of permit types it needs.
PHASE_ROLES: dict[str, PhaseRole] = {
    "construction_start": PhaseRole("start", ("site_start", "construction")),
    "handover": PhaseRole("handover", ("occupation",)),
    "operation": PhaseRole("handover", ("operation",)),
}
# Without a governance phase the roadmap check asks for what the start of construction needs.
DEFAULT_ENABLES: tuple[str, ...] = PHASE_ROLES["construction_start"].enables


@dataclass(frozen=True)
class Hosting:
    """The resolved place of permits in one project's governance model."""

    roadmap_area: str | None = None
    conditions_area: str | None = None
    # The frame document type the roadmap is written into; ``None`` when the model hosts permits nowhere.
    doc_type: str | None = None
    # Phase code -> the capabilities entering it enables (only those this module understands).
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


def _build(
    host: Any,
    by_capability: dict[str, tuple[str, ...]],
    has_model: bool,
    roadmap_override: str,
    conditions_override: str,
) -> Hosting:
    phases: dict[str, tuple[str, ...]] = {}
    for capability in PHASE_ROLES:
        for code in by_capability.get(capability, ()):
            phases[code] = (*phases.get(code, ()), capability)
    road = roadmap_override or (host.area_code if host is not None else "")
    return Hosting(
        roadmap_area=road or None,
        conditions_area=(conditions_override or road) or None,
        doc_type=host.doc_type if host is not None else None,
        phases=phases,
        has_model=has_model,
    )


def resolve(catalogue: Any, roadmap_override: str = "", conditions_override: str = "") -> Hosting:
    """Pure resolution from one parsed governance catalogue and the project's own overrides."""
    from app.modules.project_governance import public

    if catalogue is None:
        return _build(None, {}, False, roadmap_override, conditions_override)
    return _build(
        public.host_in(catalogue, SUBJECT),
        {c: public.phases_enabling_in(catalogue, c) for c in PHASE_ROLES},
        True,
        roadmap_override,
        conditions_override,
    )


async def project_hosting(session: Any, project_id: uuid.UUID, roadmap: Any = None) -> Hosting:
    """Resolve now, from the catalogue pinned now. Never cached on a row."""
    from app.modules.project_governance import public

    return resolve(
        await public.project_catalogue(session, project_id),
        getattr(roadmap, "roadmap_area_code", "") or "",
        getattr(roadmap, "conditions_area_code", "") or "",
    )
