# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo delivery model for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the catalogue its country resolves to and the decision
an owner would actually work through: three forms compared on the catalogue's
default scores (single main contractor, design and build, construction manager
at risk), design and build proposed with a rationale, the allocation matrix
confirmed from the catalogue defaults with one reasoned deviation (ground
conditions shared on a geotechnical baseline), three risks seeded into the
register, the design and build package plan derived and linked to the
project's first contract when there is one, and two owner-furnished items, one
with its procurement route and one still waiting for it.

The decision is proposed last, so its record carries the matrix and the plan,
and it stays ``proposed``: approval happens at the governance gate, never in a
seeder. A project whose governance model names no frame document for the
decision gets everything but the proposal. Only projects carrying the demo marker are
touched; a project that already has a model is skipped, so a re-run never
duplicates. Runs after the contracts and risk seeders, whose rows it links.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEMO_FORMS = ("design_bid_build_single", "design_build", "cm_at_risk")
CHOSEN = "design_build"
SEEDED_RISKS = ["design_errors", "ground_conditions", "price_escalation"]


async def seed_delivery_model_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, int]:
    """Seed the delivery model of every demo project in ``project_ids`` that has none. The caller commits."""
    from app.core.demo_marker import demo_id_of
    from app.modules.delivery_model.models import DeliveryModel
    from app.modules.projects.models import Project

    totals = {"projects": 0, "packages": 0, "risks": 0, "ofis": 0, "decisions": 0}
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (
            await session.execute(select(DeliveryModel.id).where(DeliveryModel.project_id == pid))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception:
            logger.warning("delivery_model demo seed skipped for %s", pid, exc_info=True)
            continue
        totals["projects"] += 1
        for k, v in counts.items():
            totals[k] += v
    return totals


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, int]:
    from app.modules.contracts.models import Contract
    from app.modules.delivery_model import hosting
    from app.modules.delivery_model.errors import DeliveryModelError
    from app.modules.delivery_model.service import DeliveryModelService
    from app.modules.projects.models import Project

    project = await session.get(Project, project_id)
    actor = project.owner_id
    svc = DeliveryModelService(session)
    await svc.set_model(project_id, actor_id=actor, tenant_id=None)
    options = {}
    for code in DEMO_FORMS:
        row = await svc.add_option(project_id, code, overrides={}, notes="", actor_id=actor)
        options[code] = row.id
    await svc.prefill_scores(project_id, actor)
    await svc.patch_model(
        project_id,
        actor_id=actor,
        owner_capability={
            "owner_has_design_team": False,
            "owner_has_cm_capacity": False,
            "public_client": False,
            "funding_source": "equity and bank loan",
        },
    )
    # Before a proposal the matrix and the plan follow the form leading the comparison; the story below
    # (rationale, packages, shared ground risk) is written for CHOSEN, so it has to be the one leading.
    leading = await svc._leading_form(project_id)
    if leading != CHOSEN:
        raise RuntimeError(f"demo delivery model expects {CHOSEN} to lead the comparison, got {leading}")
    await svc.confirm_allocations(project_id, None, actor)
    await svc.put_allocation(
        project_id,
        "ground_conditions",
        {
            "party": "shared",
            "basis": "ground_baseline",
            "shares": {"owner": "60", "contractor": "40"},
            "rationale": "Shared on a geotechnical baseline report: the owner carries ground worse than the baseline.",
        },
        actor,
    )
    await svc.confirm_allocations(project_id, ["ground_conditions"], actor)
    risks = await svc.seed_risks(project_id, SEEDED_RISKS, preview=False, actor_id=actor, locale="en")
    packages = await svc.derive_packages(project_id, actor)
    contract_id = (
        await session.execute(
            select(Contract.id).where(Contract.project_id == project_id).order_by(Contract.created_at).limit(1)
        )
    ).scalar_one_or_none()
    db = next((p for p in packages if p.kind == "design_and_construction"), None)
    if contract_id is not None and db is not None:
        await svc.link_package(project_id, db.id, "contract", contract_id, actor)
    today = datetime.now(UTC).date()
    if db is not None:
        await svc.update_package(project_id, db.id, {"need_date": (today + timedelta(days=120)).isoformat()}, actor)
    switchboard = await svc.create_ofi(
        project_id,
        {
            "code": "OFI-01",
            "description": "Main low-voltage switchboard and transformer, owner's framework supplier",
            "item_kind": "equipment",
            "install_by": "package",
            "package_id": db.id if db else None,
            "need_by_date": (today + timedelta(days=110)).isoformat(),
            "expected_delivery_date": (today + timedelta(days=100)).isoformat(),
            "lead_time_days": 90,
            "enquiry_date": today.isoformat(),
        },
        actor,
    )
    await svc.set_ofi_route(project_id, switchboard.id, route="framework", link_kind=None, link_id=None, actor_id=actor)
    await svc.create_ofi(
        project_id,
        {
            "code": "OFI-02",
            "description": "Loose furniture and reception fit-out items, supplied and installed by the owner",
            "item_kind": "material",
            "install_by": "owner",
            "need_by_date": (today + timedelta(days=200)).isoformat(),
        },
        actor,
    )
    # Proposed last, so the decision record carries the allocations and the package plan it was made with.
    # A project whose governance model names no frame document for the decision cannot propose one: the
    # comparison, matrix, plan and items are still seeded, and the decision is left for the user.
    decisions = 0
    try:
        await svc.propose(
            project_id,
            option_id=options[CHOSEN],
            rationale=(
                "Design and build scores highest: the owner has no in-house design team, wants one point of "
                "responsibility and a fixed price at award, and accepts less control over design detail."
            ),
            owner_capability=None,
            dispositions={},
            actor_id=actor,
        )
        decisions = 1
    except DeliveryModelError as exc:
        if exc.code not in (hosting.NO_CARRIER, hosting.NO_GOVERNANCE_MODEL):
            raise
        logger.warning("delivery_model demo: no decision proposed for %s (%s)", project_id, exc.code)
    return {
        "packages": len(packages),
        "risks": len([r for r in risks if r.get("risk_id")]),
        "ofis": 2,
        "decisions": decisions,
    }
