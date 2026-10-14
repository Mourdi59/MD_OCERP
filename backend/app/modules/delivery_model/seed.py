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
and it stays ``proposed``: approval happens at the governance gate, or by hand
on a project without gates, never in a seeder. A project that cannot take a
proposal (it uses gates and its governance model names no frame document for
the decision, or its catalogue has fewer than two forms) gets everything but
the proposal, and the result says so: ``ok`` is false and ``no_decision``
lists the project with the reason, so an integration seed can fail on it. A
project without a governance model uses no gates and takes the proposal like
any other.

Dates. A project still before the gate that starts construction (read through
the governance port, never from a catalogue id or a name) is told as a
pre-construction story: nothing delivered, owner-furnished items needed after
the start of construction, the main package needed at award. Any other project
keeps the running-project story. Offsets are days from the seed day.

The plant register seeds after this module, because its routes read the
package plan. So the one demo item that both lists hold comes in a second
step, :func:`link_demo_plant_items`, which the demo run calls after the plant
register has seeded: it has the register record that the owner supplies one of
its plant items, and the register asks this module for the owner-furnished
item. The link is never written from here, so the two lists cannot disagree.
Without the register, or where the register refuses, nothing is linked. The
two items seeded here stay unlinked and show their own figures.

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

# The demo plant item the owner supplies (the register's seed code): medium voltage switchgear, still
# before its order when the register has seeded, so its route can be set.
DEMO_PLANT_ITEM = "PL-002"
DEMO_PLANT_ROUTE = "framework"

RATIONALE_CHOSEN = (
    "Planen und Bauen erreicht die höchste Punktzahl: Der Bauherr hat kein eigenes Planungsteam, will einen "
    "einzigen Verantwortlichen und einen Festpreis bei Vergabe und nimmt weniger Einfluss auf Planungsdetails in Kauf."
)
RATIONALE_LEADING = (
    "Diese Form erreicht bei den gewichteten Kriterien des Bauherrn die höchste Punktzahl. Der Vergleich, die "
    "Risikoverteilung und der daraus folgende Paketplan sind Teil dieses Protokolls."
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
    (projects whose seed raised and was rolled back) and ``ok`` (both lists empty).
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.delivery_model.models import DeliveryOption
    from app.modules.projects.models import Project

    totals: dict[str, Any] = {
        "projects": 0,
        "packages": 0,
        "risks": 0,
        "ofis": 0,
        "contract_items": 0,
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
    totals["ok"] = not totals["failed"] and not totals["no_decision"]
    return totals


async def link_demo_plant_items(session: AsyncSession, project_ids: Iterable[uuid.UUID]) -> dict[str, Any]:
    """Have the plant register record that the owner supplies the demo switchgear; the caller commits.

    Runs after the plant register's demo seed. Per demo project it asks the
    register to set an owner-furnished route on :data:`DEMO_PLANT_ITEM`, with
    the package that builds as installer; the register then asks this module
    for the owner-furnished item, which is how the link comes to exist. The
    item gets a procurement route like every seeded item.

    Nothing is asked that is known to be refused: a project is skipped, at
    info, when there is no register, no such plant item, the item is ordered
    or cancelled (its route is frozen), or it is already owner-furnished.
    Returns ``{"linked": n, "skipped": [{project_id, reason}]}``.
    """
    from app.core.demo_marker import demo_id_of
    from app.modules.delivery_model.repository import DeliveryModelRepository
    from app.modules.delivery_model.service import DeliveryModelService
    from app.modules.projects.models import Project

    out: dict[str, Any] = {"linked": 0, "skipped": []}
    ids = list(project_ids)
    if not ids:
        return out
    rows = (
        await session.execute(select(Project.id, Project.owner_id, Project.metadata_).where(Project.id.in_(ids)))
    ).all()
    for pid, owner, meta in rows:
        if not demo_id_of(meta):
            continue
        reason = await _link_demo_plant_item(session, pid, owner)
        if reason is None:
            item = next(i for i in await DeliveryModelRepository(session).ofis(pid) if i.plant_item_id is not None)
            if item.procurement_route == "none_yet":
                await DeliveryModelService(session).set_ofi_route(
                    pid, item.id, route=DEMO_PLANT_ROUTE, link_kind=None, link_id=None, actor_id=owner
                )
            out["linked"] += 1
        else:
            logger.info("delivery_model demo: plant item not linked for project %s (%s)", pid, reason)
            out["skipped"].append({"project_id": str(pid), "reason": reason})
    return out


async def _link_demo_plant_item(session: AsyncSession, project_id: uuid.UUID, owner: uuid.UUID) -> str | None:
    """``None`` when the register recorded the owner-furnished route, else why nothing was asked or done."""
    from app.modules.delivery_model import plant
    from app.modules.delivery_model.repository import DeliveryModelRepository

    if not plant.installed():
        return "plant_register_unavailable"
    repo = DeliveryModelRepository(session)
    if await repo.get_model(project_id) is None:
        return "delivery_model_missing"
    plant_item_id = await plant.plant_item_id_by_code(session, project_id, DEMO_PLANT_ITEM)
    dates = await plant.plant_item_dates(session, project_id, plant_item_id) if plant_item_id is not None else None
    if dates is None:
        return "plant_item_missing"
    if plant.keeps_owner_furnished_item(dates):
        return "already_owner_furnished"
    if not plant.route_open(dates):
        return "plant_item_route_frozen"
    # The package that builds installs what the owner supplies; without one the owner installs.
    installer = next((p.id for p in await repo.packages(project_id) if p.builds and p.status != "cancelled"), None)
    return await plant.set_owner_furnished_route(
        session, project_id, plant_item_id, installer_package_id=installer, actor_id=owner
    )


# The contract side of the demo project: (group, preferred kinds in order, code, title, counterparty, status,
# days from the seed day to the start, share). The first preferred kind the pinned catalogue has is used;
# a group the catalogue has no kind for is left out, as everything else here.
DEMO_CONTRACT_ITEMS: tuple[tuple[str, tuple[str, ...], str, str, str, str, int, str | None], ...] = (
    (
        "contract_form",
        ("design_build_contract", "construction_contract"),
        "CF-01",
        "Bauvertrag für die Hauptleistung, Pauschalpreis bei Vergabe",
        "Generalunternehmer, Vergabe steht aus",
        "negotiating",
        AWARD,
        None,
    ),
    (
        "land_tenure",
        ("leasehold", "purchase"),
        "LT-01",
        "Grundstück im Erbbaurecht der Stadt",
        "Stadt",
        "signed",
        -120,
        None,
    ),
    (
        "utility_contract",
        ("power_connection", "water_sewer_connection"),
        "UC-01",
        "Mittelspannungsanschluss des Neubaus",
        "Regionaler Netzbetreiber",
        "agreed",
        30,
        None,
    ),
    (
        "user_agreement",
        ("lease_to_user", "service_level_agreement"),
        "UA-01",
        "Mietvertrag mit dem künftigen Betreiber, Übergabekriterien als Anlage",
        "Künftiger Betreiber",
        "draft",
        START,
        None,
    ),
    (
        "partner_structure",
        ("project_company", "joint_venture"),
        "PS-01",
        "Gesellschafteranteil des Bauherrn an der Projektgesellschaft",
        "Bauherr Beteiligungs GmbH",
        "agreed",
        -90,
        "70",
    ),
    (
        "partner_structure",
        ("co_investment", "consortium"),
        "PS-02",
        "Gesellschafteranteil des Mitinvestors an der Projektgesellschaft",
        "Mitinvestor",
        "agreed",
        -90,
        "30",
    ),
)


async def _seed_contract_items(
    svc: Any, project_id: uuid.UUID, catalogue: Any, package: Any, today: date, actor: Any
) -> int:
    """The contract-side items of the demo project; the caller's catalogue decides which kinds exist."""
    form = None
    model = await svc.require_model(project_id)
    if model.selected_form_code:
        form = catalogue.form(model.selected_form_code)
    made = 0
    for group, kinds, code, title, counterparty, status, offset, share in DEMO_CONTRACT_ITEMS:
        kind = next((k for k in kinds if catalogue.contract_kind(group, k) is not None), None)
        if kind is None:
            continue
        data: dict[str, Any] = {
            "code": code,
            "group_code": group,
            "kind_code": kind,
            "title": title,
            "counterparty": counterparty,
            "status": status,
            "start_date": (today + timedelta(days=offset)).isoformat(),
        }
        if group == "contract_form":
            data["package_id"] = package.id if package else None
            data["price_basis"] = form.price_basis_at_award if form else "lump_sum"
        if share is not None:
            data["share_percent"] = share
        await svc.create_contract_item(project_id, data, actor)
        made += 1
    return made


async def _seed_project(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Any]:
    from app.modules.contracts.models import Contract
    from app.modules.delivery_model import hosting
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
            "funding_source": "Eigenkapital und Bankdarlehen",
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
                    "Geteilt auf Grundlage eines Baugrund-Basisgutachtens: Der Bauherr trägt Baugrund, der schlechter ist als die Baseline."
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
            "description": "Niederspannungshauptverteilung und Transformator, Lieferant aus dem Rahmenvertrag des Bauherrn",
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
            "description": "Empfangsmöbel aus dem vorhandenen Bestand des Bauherrn, vom Bauherrn selbst montiert",
            "item_kind": "material",
            "install_by": "owner",
            "need_by_date": dates["furniture_need"].isoformat(),
        },
        actor,
    )
    await svc.set_ofi_route(
        project_id, furniture.id, route="existing_stock", link_kind=None, link_id=None, actor_id=actor
    )
    contract_items = await _seed_contract_items(svc, project_id, catalogue, db, today, actor)
    # Proposed last, so the decision record carries the allocations and the package plan it was made with.
    decisions, reason = 0, ""
    if leading is None or len(options) < 2:
        reason = "too_few_forms"
    else:
        # Asked first, not tried: a project that uses gates and has no frame document for the decision
        # would refuse the proposal.
        blocked = (await svc._action_blocks(await svc.require_model(project_id)))["propose"]
        if blocked in (hosting.NO_CARRIER, hosting.NO_GOVERNANCE_MODEL):
            reason = blocked
        else:
            await svc.propose(
                project_id,
                option_id=options[leading],
                rationale=RATIONALE_CHOSEN if leading == CHOSEN else RATIONALE_LEADING,
                owner_capability=None,
                dispositions={},
                actor_id=actor,
            )
            decisions = 1
    if reason:
        # Loud on purpose: a demo project without a proposed decision shows an empty decision screen.
        logger.error("delivery_model demo: no decision proposed for project %s (%s)", project_id, reason)
    return {
        "packages": len(packages),
        "risks": len([r for r in risks if r.get("risk_id")]),
        "ofis": 2,
        "contract_items": contract_items,
        "decisions": decisions,
        "no_decision_reason": reason,
    }
