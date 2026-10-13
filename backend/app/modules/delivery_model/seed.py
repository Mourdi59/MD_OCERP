# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Demo delivery model for the demo estate, run by ``app.core.demo_enrichment``.

Each demo project gets the catalogue its country (or the active pack) resolves
to and the decision an owner would actually work through: three forms of that
catalogue compared on its default scores, the leading form proposed with a
rationale, the allocation matrix confirmed from the catalogue defaults with one
reasoned deviation (ground conditions shared on a geotechnical baseline), three
risks seeded into the register, the package plan of the leading form derived
and linked to the project's first contract when there is one, and two
owner-furnished items, each with its procurement route.

Nothing here assumes a form, a risk category or a party the pinned catalogue
may lack: the forms compared are taken from the catalogue, and a step whose
codes are missing is left out.

The decision is proposed last, so its record carries the matrix and the plan,
and it stays ``proposed``: approval happens at the governance gate, never in a
seeder. A project that cannot take a proposal (its governance model names no
frame document for the decision, or its catalogue has fewer than two forms)
gets everything but the proposal, and the result says so: ``ok`` is false and
``no_decision`` lists the project with the reason, so an integration seed can
fail on it. A project without a governance model is listed too, but it is a
legal state of the product and not this module's failure: it is logged at info
and leaves ``ok`` alone. The governance seed owns that verdict.

Dates. A project still before the gate that starts construction (read through
the governance port, never from a catalogue id or a name) is told as a
pre-construction story: nothing delivered, owner-furnished items needed after
the start of construction, the main package needed at award. Any other project
keeps the running-project story. Offsets are days from the seed day.

The plant register seeds after this module, because its routes read the
package plan. So the owner-furnished item that is also a plant item is linked
in a second step, :func:`link_demo_plant_items`, which the demo run calls after
the plant register has seeded. Without the register it links nothing.

Only projects carrying the demo marker are touched; a project whose model
already compares forms is skipped, so a re-run never duplicates. A model that
is pinned and still empty is filled on the catalogue it pins. Runs after the governance,
contracts and risk seeders, whose rows it reads and links.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Preferred forms to compare, where the pinned catalogue has them; topped up from the catalogue's own order.
DEMO_FORMS = ("design_bid_build_single", "design_build", "cm_at_risk")
COMPARED = 3
CHOSEN = "design_build"
SEEDED_RISKS = ("design_errors", "ground_conditions", "price_escalation")

# Milestones of the pre-construction story, in days from the seed day (the shared demo timeline).
AWARD = 165
START = 190

# Reasons a project has no proposal that are a legal state of the product, not a failure of this seed.
NOT_OURS = frozenset({"governance_model_missing"})

# Seeded owner-furnished item -> code of the demo plant item that is the same thing. The furniture is no plant.
DEMO_PLANT_LINKS = {"OFI-01": "PL-010"}

RATIONALE_CHOSEN = (
    "Design and build scores highest: the owner has no in-house design team, wants one point of "
    "responsibility and a fixed price at award, and accepts less control over design detail."
)
RATIONALE_LEADING = (
    "This form scores highest on the owner's weighted criteria. The comparison, the risk allocation "
    "and the package plan it leads to are part of this record."
)


def forms_to_compare(available: Iterable[str]) -> list[str]:
    """Up to three forms of the pinned catalogue: the preferred ones it has, then its own order."""
    have = list(available)
    picked = [code for code in DEMO_FORMS if code in have]
    picked += [code for code in have if code not in picked]
    return picked[:COMPARED]


def item_dates(today: date, *, pre_construction: bool) -> dict[str, date]:
    """Dates of the seeded package and items for the story the project is in."""
    if pre_construction:
        return {
            "package_need": today + timedelta(days=AWARD),
            "switchboard_delivery": today + timedelta(days=START + 60),
            "switchboard_need": today + timedelta(days=START + 70),
            "furniture_need": today + timedelta(days=START + 300),
        }
    return {
        "package_need": today + timedelta(days=120),
        "switchboard_delivery": today + timedelta(days=100),
        "switchboard_need": today + timedelta(days=110),
        "furniture_need": today + timedelta(days=200),
    }


async def seed_delivery_model_demo(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, Any]:
    """Seed the delivery model of every demo project in ``project_ids`` that has none. The caller commits.

    Returns counts plus ``no_decision`` (projects seeded without a proposal, with the reason), ``failed``
    (projects whose seed raised and was rolled back) and ``ok``: nothing failed, and every project that
    has a governance model got its proposal.
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.delivery_model.models import DeliveryOption
    from app.modules.projects.models import Project

    totals: dict[str, Any] = {
        "projects": 0,
        "packages": 0,
        "risks": 0,
        "ofis": 0,
        "decisions": 0,
        "no_decision": [],
        "failed": [],
        "ok": True,
    }
    ids = list(project_ids)
    if not ids:
        return totals
    rows = (await session.execute(select(Project.id, Project.metadata_).where(Project.id.in_(ids)))).all()
    for pid in [pid for pid, meta in rows if demo_id_of(meta)]:
        has = (
            await session.execute(select(DeliveryOption.id).where(DeliveryOption.project_id == pid).limit(1))
        ).scalar_one_or_none()
        if has is not None:
            continue
        try:
            async with session.begin_nested():
                counts = await _seed_project(session, pid)
        except Exception as exc:
            logger.error("delivery_model demo seed failed for %s and was rolled back", pid, exc_info=True)
            totals["failed"].append({"project_id": str(pid), "reason": type(exc).__name__})
            continue
        totals["projects"] += 1
        reason = counts.pop("no_decision_reason")
        if reason:
            totals["no_decision"].append({"project_id": str(pid), "reason": reason})
        for k, v in counts.items():
            totals[k] += v
    totals["ok"] = not totals["failed"] and all(r["reason"] in NOT_OURS for r in totals["no_decision"])
    return totals


async def link_demo_plant_items(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, Any]:
    """Link the seeded owner-furnished items to the demo plant items that are the same thing.

    Runs after the plant register's demo seed; the caller commits. An item is
    linked once: a run that finds it linked, finds no such plant item, or finds
    no plant register changes nothing. Returns ``{"linked": n}``.
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.delivery_model import plant
    from app.modules.delivery_model.repository import DeliveryModelRepository
    from app.modules.delivery_model.service import DeliveryModelService
    from app.modules.projects.models import Project

    linked = 0
    ids = list(project_ids)
    if not ids or not plant.installed():
        return {"linked": linked}
    rows = (
        await session.execute(select(Project.id, Project.owner_id, Project.metadata_).where(Project.id.in_(ids)))
    ).all()
    for pid, owner, meta in rows:
        if not demo_id_of(meta):
            continue
        items = await DeliveryModelRepository(session).ofis(pid)
        taken = {i.plant_item_id for i in items if i.plant_item_id is not None}
        for item in items:
            code = DEMO_PLANT_LINKS.get(item.code)
            if code is None or item.plant_item_id is not None:
                continue
            plant_item_id = await plant.plant_item_id_by_code(session, pid, code)
            if plant_item_id is None or plant_item_id in taken:
                continue
            await DeliveryModelService(session).update_ofi(pid, item.id, {"plant_item_id": plant_item_id}, owner)
            taken.add(plant_item_id)
            linked += 1
    return {"linked": linked}


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    from app.modules.contracts.models import Contract
    from app.modules.delivery_model import hosting
    from app.modules.delivery_model.errors import DeliveryModelError
    from app.modules.delivery_model.service import DeliveryModelService
    from app.modules.projects.models import Project

    project = await session.get(Project, project_id)
    actor = project.owner_id
    svc = DeliveryModelService(session)
    model = await svc.get_model(project_id) or await svc.set_model(project_id, actor_id=actor, tenant_id=None)
    catalogue = await svc.catalogue_for(model)
    options = {}
    for code in forms_to_compare(f.code for f in catalogue.forms):
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
    # Before a proposal the matrix and the plan follow the form leading the comparison, whichever it is.
    leading = await svc._leading_form(project_id)
    await svc.confirm_allocations(project_id, None, actor)
    parties = {p.code for p in catalogue.parties}
    if catalogue.category("ground_conditions") is not None and {"shared", "owner", "contractor"} <= parties:
        await svc.put_allocation(
            project_id,
            "ground_conditions",
            {
                "party": "shared",
                "basis": "ground_baseline",
                "shares": {"owner": "60", "contractor": "40"},
                "rationale": (
                    "Shared on a geotechnical baseline report: the owner carries ground worse than the baseline."
                ),
            },
            actor,
        )
        await svc.confirm_allocations(project_id, ["ground_conditions"], actor)
    seeded = [code for code in SEEDED_RISKS if catalogue.category(code) is not None]
    risks = await svc.seed_risks(project_id, seeded, preview=False, actor_id=actor, locale="en") if seeded else []
    packages = await svc.derive_packages(project_id, actor) if leading else []
    contract_id = (
        await session.execute(
            select(Contract.id).where(Contract.project_id == project_id).order_by(Contract.created_at).limit(1)
        )
    ).scalar_one_or_none()
    db = next((p for p in packages if p.kind == "design_and_construction"), None)
    if contract_id is not None and db is not None:
        await svc.link_package(project_id, db.id, "contract", contract_id, actor)
    today = datetime.now(UTC).date()
    dates = item_dates(today, pre_construction=await hosting.construction_not_released(session, project_id))
    if db is not None:
        await svc.update_package(project_id, db.id, {"need_date": dates["package_need"].isoformat()}, actor)
    # Every item gets a route: where procurement is released from the first phase a missing one is an error.
    switchboard = await svc.create_ofi(
        project_id,
        {
            "code": "OFI-01",
            "description": "Main low-voltage switchboard and transformer, owner's framework supplier",
            "item_kind": "equipment",
            "install_by": "package" if db else "owner",
            "package_id": db.id if db else None,
            "need_by_date": dates["switchboard_need"].isoformat(),
            "expected_delivery_date": dates["switchboard_delivery"].isoformat(),
            "lead_time_days": 90,
            "enquiry_date": today.isoformat(),
        },
        actor,
    )
    await svc.set_ofi_route(project_id, switchboard.id, route="framework", link_kind=None, link_id=None, actor_id=actor)
    furniture = await svc.create_ofi(
        project_id,
        {
            "code": "OFI-02",
            "description": "Reception furniture from the owner's existing stock, installed by the owner",
            "item_kind": "material",
            "install_by": "owner",
            "need_by_date": dates["furniture_need"].isoformat(),
        },
        actor,
    )
    await svc.set_ofi_route(
        project_id, furniture.id, route="existing_stock", link_kind=None, link_id=None, actor_id=actor
    )
    # Proposed last, so the decision record carries the allocations and the package plan it was made with.
    decisions, reason = 0, ""
    if leading is None or len(options) < 2:
        reason = "too_few_forms"
    else:
        try:
            await svc.propose(
                project_id,
                option_id=options[leading],
                rationale=RATIONALE_CHOSEN if leading == CHOSEN else RATIONALE_LEADING,
                owner_capability=None,
                dispositions={},
                actor_id=actor,
            )
            decisions = 1
        except DeliveryModelError as exc:
            if exc.code not in (hosting.NO_CARRIER, hosting.NO_GOVERNANCE_MODEL):
                raise
            reason = exc.code
    if reason in NOT_OURS:
        logger.info("delivery_model demo: no decision proposed for project %s (%s)", project_id, reason)
    elif reason:
        # Loud on purpose: a demo project that has a governance model and still no proposed decision
        # shows an empty decision screen.
        logger.error("delivery_model demo: no decision proposed for project %s (%s)", project_id, reason)
    return {
        "packages": len(packages),
        "risks": len([r for r in risks if r.get("risk_id")]),
        "ofis": 2,
        "decisions": decisions,
        "no_decision_reason": reason,
    }
