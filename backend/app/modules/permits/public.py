# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The read interface other modules use (SPEC rules 2, 20, 21, 22). Import lazily and guard.

Modules are plugins: a caller imports this inside a function and treats
``ImportError`` as "permits not installed". Every function is read only and
answers for one project the caller has already checked access to.

* ``start_readiness``   -- site_prep's computed item in ``permits_consents`` (rule 20)
* ``closeout_entries``  -- the generated closeout slot ``permits_and_conditions`` (rule 21)
* ``requirement_state`` -- commitment_release precondition kind ``permit`` (rule 22)
* ``register_applicant_resolver`` -- delivery_model's allocation answers the default applicant (rule 2)
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.permits.service import register_applicant_resolver, unregister_applicant_resolver

__all__ = [
    "closeout_entries",
    "register_applicant_resolver",
    "requirement_state",
    "start_readiness",
    "unregister_applicant_resolver",
]


async def start_readiness(session: AsyncSession, project_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
    """``{gate: "start", status: ready|at_risk|not_ready|no_roadmap, items[], activities{}}``."""
    from app.modules.permits.service import PermitService

    return await PermitService(session).readiness(project_id, "start", today or datetime.now(UTC).date())


async def requirement_state(session: AsyncSession, project_id: uuid.UUID, requirement_id: uuid.UUID) -> str | None:
    """Derived state of one roadmap requirement (``granted``, ``partially_granted``, ...); ``None`` if absent."""
    from app.modules.permits.service import PermitService

    return await PermitService(session).requirement_state(project_id, requirement_id)


async def closeout_entries(session: AsyncSession, project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every permit plus its before-occupation and after-completion conditions, with discharge evidence."""
    from app.modules.permits.service import PermitService, condition_out, discharge_out, permit_out

    svc = PermitService(session)
    discharges: dict[str, list[dict[str, Any]]] = {}
    for d in await svc.repo.list_discharges(project_id):
        discharges.setdefault(str(d.condition_id), []).append(discharge_out(d))
    out: list[dict[str, Any]] = []
    conds = await svc.repo.list_conditions(project_id)
    for p in await svc.repo.list_permits(project_id):
        out.append(
            {
                "kind": "permit",
                **permit_out(p),
                "conditions": [
                    {**condition_out(c), "discharges": discharges.get(str(c.id), [])}
                    for c in conds
                    if c.permit_id == p.id
                    and c.confirmed
                    and c.trigger in ("before_occupation", "after_completion")
                    and c.status != "superseded"
                ],
            }
        )
    return out
