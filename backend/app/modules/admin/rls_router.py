# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Admin - row-level-security readiness report.

``GET /api/v1/admin/rls/readiness`` tells an administrator what stands between
this database and a strict tenant policy, so ``OE_RLS_ENFORCE=1`` is switched
on only once the report is clean. Read-only and admin-only; it changes nothing
and works whether enforcement is on or off.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.dependencies import RequireRole

router = APIRouter()


@router.get(
    "/rls/readiness",
    summary="What blocks strict row-level security on this database",
    dependencies=[Depends(RequireRole("admin"))],
)
async def rls_readiness() -> dict[str, Any]:
    """Measure the tenant tables and list the blockers, see ``rls_readiness_report``.

    On its own connection rather than the request session: with enforcement on,
    the request session runs as the policied role and would count only the
    caller's own rows, which is not the census an administrator asked for.
    """
    from app.core.rls_setup import rls_readiness_report, tenant_tables
    from app.database import Base, engine

    async with engine.connect() as conn:
        return await rls_readiness_report(conn, tenant_tables(Base))
