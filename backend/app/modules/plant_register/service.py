# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Plant register service: the one long-lead list of a project and everything hung on it.

Writes:
    pin_catalogue, create_item, update_item, transition_item, sync_item_state
    add_quote, set_basis                        (rules 2, 4)
    set_route                                   (rules 10, 11; OFI through the port)
    create_slot, update_slot, transition_slot, expire_slots      (rule 13)
    create_paper, update_paper, submit_paper, apply_paper_verdict (rule 9)
    put_limits                                   (rule 14)
    create_spare, update_spare, transition_spare (rule 15)
    create_it_service, update_it_service, transition_it_service (rule 18)
    handover                                     (rule 16)
    escalate                                     (rules 7, 13 notifications)

Reads compute every date on the fly (``item_views``): effective lead, need
date, latest order date, float, long-lead. Nothing derived is stored.

Who may write: a manager, or the owner or deputy of the equipment area
``m04_equipment`` of the project's governance model (``require_editor``).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.plant_register import calc
from app.modules.plant_register.catalogue import DEFAULT_CATALOGUE_ID, PLANT_KIND, PlantCatalogue, register_plant_kind
from app.modules.plant_register.errors import PlantError, blocked, conflict, forbidden, not_found
from app.modules.plant_register.fsm import IT_FSM, ITEM_FSM, MANUAL_TARGETS, PAPER_FSM, SLOT_FSM, SPARE_FSM
from app.modules.plant_register.models import (
    DecisionPaper,
    DeliveryLimit,
    ItService,
    LeadTimeQuote,
    PlantItem,
    PlantSettings,
    SlotReservation,
    SparePartRequirement,
)
from app.modules.plant_register.ports import OwnerFurnishedRef, PackagePlan, package_plan_provider
from app.modules.plant_register.repository import PlantRepository

logger = logging.getLogger(__name__)

MODULE = "plant_register"
EVENT_PREFIX = "plant"
AREA_CODE = "m04_equipment"
GATE_CODE = "development_to_execution"
PAPER_TARGET_KIND = "plant_decision_paper"
EDIT_ROLES = ("admin", "manager")
VENDOR_BOUND_REASONS = ("standardisation", "existing_estate", "warranty", "sole_source")
ITEM_FIELDS = (
    "title",
    "description",
    "component_class_code",
    "quantity",
    "unit",
    "tag",
    "wbs_id",
    "boq_position_id",
    "bim_element_ids",
    "cx_system_id",
    "space_ref",
    "performance",
    "redundancy_scheme",
    "maintainability",
    "vendor_policy",
    "vendor_bound_reason",
    "vendor_id",
    "critical_override",
    "critical_reason",
    "need_activity_id",
    "need_date_fixed",
    "order_buffers",
    "purchase_order_id",
    "submittal_id",
    "maintenance_strategy",
    "no_strategic_spare_reason",
    "long_lead_override",
    "long_lead_override_reason",
    "owner_user_id",
)
# Item states that may still change the specification freely.
_OPEN_SPEC = ("identified", "specified", "enquired")
PO_ORDERED = ("issued", "partially_received", "completed")
PO_DELIVERED = ("completed",)


def _s(value: Any) -> str | None:
    return str(value) if value is not None else None


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _quote_view(q: LeadTimeQuote) -> calc.QuoteView:
    return calc.QuoteView(
        id=q.id,
        source=q.source,
        enquiry_date=q.enquiry_date,
        response_date=q.response_date,
        lead_weeks_min=q.lead_weeks_min,
        lead_weeks_max=q.lead_weeks_max,
        lead_basis=q.lead_basis,
        is_basis=q.is_basis,
        superseded=q.superseded_by is not None,
    )


class PlantService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PlantRepository(session)

    # ── plumbing ──────────────────────────────────────────────────────────

    async def _fsm(self, fsm: Any, entity: Any, target: str, actor_id: Any, **meta: Any) -> None:
        try:
            await fsm.apply(
                self.session,
                entity,
                target,
                actor_id=_s(actor_id),
                extra_metadata={"project_id": _s(getattr(entity, "project_id", None)), **meta},
                entity_type=fsm.name,
            )
        except FSMError as exc:
            raise conflict("invalid_transition", detail=str(exc)) from exc

    async def _audit(self, actor_id: Any, entity_type: str, entity_id: Any, action: str, **kw: Any) -> None:
        await log_activity(
            self.session,
            actor_id=_s(actor_id),
            entity_type=entity_type,
            entity_id=_s(entity_id),
            action=action,
            module=MODULE,
            **kw,
        )

    def _publish(self, name: str, data: dict[str, Any]) -> None:
        publish_after_commit(self.session, f"{EVENT_PREFIX}.{name}", data, source_module=MODULE)

    async def _notify(self, user_id: Any, kind: str, entity_id: Any, ctx: dict[str, Any]) -> None:
        """Best effort, in a savepoint so a failure never poisons the write."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"plant_{kind}",
                    title_key=f"notifications.plant.{kind}.title",
                    entity_type="plant_item",
                    entity_id=str(entity_id),
                    body_key=f"notifications.plant.{kind}.body",
                    body_context=ctx,
                    action_url=f"/projects/{ctx.get('project_id')}/plant",
                    metadata=ctx,
                )
        except Exception:
            logger.debug("plant notification %s skipped", kind, exc_info=True)

    async def _area(self, project_id: uuid.UUID) -> Any:
        from app.modules.project_governance.models import GovernanceArea

        stmt = select(GovernanceArea).where(GovernanceArea.project_id == project_id, GovernanceArea.code == AREA_CODE)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def require_editor(self, project_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:
        """A manager, or the m04 equipment area owner or deputy."""
        if role in EDIT_ROLES:
            return
        area = await self._area(project_id)
        if area is not None and user_id in (area.owner_user_id, area.deputy_user_id):
            return
        raise forbidden("not_equipment_owner")

    # ── catalogue ─────────────────────────────────────────────────────────

    async def settings(self, project_id: uuid.UUID) -> PlantSettings | None:
        return await self.repo.settings(project_id)

    async def catalogue(self, project_id: uuid.UUID) -> PlantCatalogue:
        """The pinned catalogue; the shipped neutral one when the project pinned nothing yet."""
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        register_plant_kind()
        row = await self.repo.settings(project_id)
        source, cid, version = (
            (row.catalogue_source, row.catalogue_id, row.catalogue_version)
            if row
            else ("shipped", DEFAULT_CATALOGUE_ID, None)
        )
        try:
            return await resolve_catalogue(self.session, source, cid, version, kind=PLANT_KIND)
        except GovernanceError as exc:
            raise not_found("unknown_catalogue") from exc

    async def pin_catalogue(
        self, project_id: uuid.UUID, *, source: str, catalogue_id: str, version: int | None, actor_id: uuid.UUID
    ) -> PlantSettings:
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        register_plant_kind()
        try:
            cat = await resolve_catalogue(self.session, source, catalogue_id, version, kind=PLANT_KIND)
        except GovernanceError as exc:
            raise not_found("unknown_catalogue") from exc
        row = await self.repo.settings(project_id)
        if row is None:
            row = PlantSettings(project_id=project_id, created_by=actor_id)
            self.session.add(row)
        row.catalogue_source, row.catalogue_id, row.catalogue_version = source, catalogue_id, cat.version
        await self.session.flush()
        await self._audit(
            actor_id, "plant_settings", row.id, "catalogue_pinned", catalogue=f"{source}:{catalogue_id}@{cat.version}"
        )
        return row

    # ── items ─────────────────────────────────────────────────────────────

    async def get_item(self, project_id: uuid.UUID, item_id: uuid.UUID, *, lock: bool = False) -> PlantItem:
        item = await self.repo.get_scoped(PlantItem, project_id, item_id, lock=lock)
        if item is None:
            raise not_found("item_not_found")
        return item

    async def _check_links(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        """Soft links must point into this project (IDOR); a foreign id is 404 ``link_not_found``."""
        checks: list[tuple[str, Any]] = []
        if data.get("need_activity_id"):
            from app.modules.schedule.models import Activity, Schedule

            stmt = (
                select(Activity.id)
                .join(Schedule, Schedule.id == Activity.schedule_id)
                .where(Activity.id == data["need_activity_id"], Schedule.project_id == project_id)
            )
            checks.append(("need_activity_id", stmt))
        for key, path, attr in (
            ("purchase_order_id", "app.modules.procurement.models", "PurchaseOrder"),
            ("submittal_id", "app.modules.submittals.models", "Submittal"),
            ("cx_system_id", "app.modules.commissioning.models", "CxSystem"),
        ):
            if data.get(key):
                import importlib

                model = getattr(importlib.import_module(path), attr)
                checks.append((key, select(model.id).where(model.id == data[key], model.project_id == project_id)))
        for key, stmt in checks:
            if (await self.session.execute(stmt)).scalar_one_or_none() is None:
                raise PlantError("link_not_found", 404, detail=key)

    def _check_item_fields(self, cat: PlantCatalogue, item: PlantItem) -> None:
        cls = cat.component_class(item.component_class_code)
        if cls is None:
            raise PlantError("unknown_component_class")
        item.item_class = cls.item_class
        if item.redundancy_scheme and cat.scheme(item.redundancy_scheme) is None:
            raise PlantError("unknown_redundancy_scheme")
        if item.maintenance_strategy and item.maintenance_strategy not in cat.codes("maintenance_strategies"):
            raise PlantError("unknown_maintenance_strategy")
        if item.vendor_policy not in ("neutral", "bound"):
            raise PlantError("unknown_vendor_policy")
        if item.vendor_policy == "bound":
            if not item.vendor_bound_reason:
                raise PlantError("vendor_bound_needs_reason")
            if item.vendor_bound_reason not in VENDOR_BOUND_REASONS:
                raise PlantError("unknown_vendor_bound_reason")
        elif item.vendor_bound_reason:
            item.vendor_bound_reason = ""
        if item.critical_override is not None and not (item.critical_reason or "").strip():
            raise PlantError("critical_override_needs_reason")
        if item.long_lead_override is not None and not (item.long_lead_override_reason or "").strip():
            raise PlantError("long_lead_override_needs_reason")
        if item.quantity is None or Decimal(item.quantity) <= 0:
            raise PlantError("quantity_not_positive")

    async def create_item(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> PlantItem:
        cat = await self.catalogue(project_id)
        await self._check_links(project_id, data)
        cls = cat.component_class(data.get("component_class_code") or "")
        if cls is None:
            raise PlantError("unknown_component_class")
        item = PlantItem(project_id=project_id, code=data["code"], created_by=actor_id, status="identified")
        for key in ITEM_FIELDS:
            if key in data:
                setattr(item, key, data[key])
        for key, default in (
            ("bim_element_ids", []),
            ("performance", []),
            ("maintainability", {}),
            ("order_buffers", {}),
            ("quantity", Decimal(1)),
            ("unit", "pcs"),
            ("vendor_policy", "neutral"),
            ("vendor_bound_reason", ""),
            ("critical_reason", ""),
            ("long_lead_override_reason", ""),
            ("no_strategic_spare_reason", ""),
            ("description", ""),
            ("tag", ""),
            ("space_ref", ""),
            ("redundancy_scheme", ""),
        ):
            if getattr(item, key, None) is None:
                setattr(item, key, default)
        if not item.maintenance_strategy:
            item.maintenance_strategy = cls.default_maintenance_strategy
        if item.owner_user_id is None:
            item.owner_user_id = actor_id
        self._check_item_fields(cat, item)
        try:
            async with self.session.begin_nested():
                await self.repo.add(item)
        except IntegrityError as exc:
            raise conflict("item_code_taken") from exc
        await self._audit(actor_id, "plant_item", item.id, "created", to_status=item.status)
        self._publish("item.created", {"project_id": str(project_id), "item_id": str(item.id), "code": item.code})
        return item

    async def update_item(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PlantItem:
        item = await self.get_item(project_id, item_id, lock=True)
        if item.status in ("handed_over", "cancelled"):
            raise conflict("item_closed")
        spec_keys = {"component_class_code", "performance", "redundancy_scheme", "vendor_policy", "vendor_id"}
        if spec_keys & set(data) and item.status not in _OPEN_SPEC:
            # After the route is set, the specification is what the package was let on.
            raise conflict("specification_frozen")
        await self._check_links(project_id, data)
        for key in ITEM_FIELDS:
            if key in data:
                setattr(item, key, data[key])
        self._check_item_fields(await self.catalogue(project_id), item)
        await self.session.flush()
        await self._audit(actor_id, "plant_item", item.id, "updated", fields=sorted(data))
        self._publish("item.updated", {"project_id": str(project_id), "item_id": str(item.id)})
        return item

    async def transition_item(
        self, project_id: uuid.UUID, item_id: uuid.UUID, target: str, *, actor_id: uuid.UUID, today: date
    ) -> PlantItem:
        """A transition by hand. ``ordered`` onward is read from its owner (rule 11), except ``manufactured``."""
        if target not in MANUAL_TARGETS:
            raise conflict("state_read_from_source")
        item = await self.get_item(project_id, item_id, lock=True)
        if not ITEM_FSM.has_transition(item.status, target):
            raise conflict("invalid_transition")
        if target in ("enquired", "route_set") and calc.state_rank(target) > calc.state_rank(item.status):
            views = await self.item_views(project_id, today=today, only=[item.id])
            blockers = await self.transition_blockers(project_id, item, views[0], target)
            if blockers:
                raise blocked(blockers)
        before = item.status
        await self._fsm(ITEM_FSM, item, target, actor_id)
        await self._audit(actor_id, "plant_item", item.id, "state_changed", from_status=before, to_status=target)
        self._publish(
            "item.state_changed",
            {"project_id": str(project_id), "item_id": str(item.id), "from": before, "to": target},
        )
        return item

    async def transition_blockers(
        self, project_id: uuid.UUID, item: PlantItem, view: dict[str, Any], target: str
    ) -> list[str]:
        """Every rule that stops ``target``; empty when it may happen."""
        if target == "enquired":
            # Rule 4: from enquired on, exactly one basis quote.
            return [] if view["basis_quote_id"] else ["basis_quote_required"]
        if target != "route_set":
            return []
        out: list[str] = []
        if not view["basis_quote_id"]:
            out.append("basis_quote_required")
        if view["critical"]:
            if not view["market_evidence"]:
                out.append("critical_without_market_evidence")  # rule 6
            if view["paper_status"] != "approved":
                out.append("critical_without_decision")  # rule 9
            if view["quote_stale"]:
                out.append("lead_time_stale")  # rule 3 at the gate that releases procurement
        if item.item_class in ("main_component", "user_equipment") and view["delivery_limit_gaps"]:
            out.append("delivery_limit_gap")  # rule 14
        out += await self.route_findings(project_id, item)  # rule 10
        return out

    # ── route (rules 10, 11) ──────────────────────────────────────────────

    # Three states of the delivery-model port (lead decision 2026-10-11, modules are plugins):
    #   not installed  -> degrade: the route is recorded unchecked, owner-furnished info is "not available",
    #                     never a refusal and never a blocker;
    #   installed, ok  -> rule 10 / 11 apply in full;
    #   installed, the call raised -> ``package_plan_failed``, an error finding and a blocker, like a raising
    #                     governance evidence provider.

    async def _port(self, call: Any) -> Any:
        """Await a port call in a savepoint; any failure becomes ``package_plan_failed`` (422)."""
        try:
            async with self.session.begin_nested():
                return await call
        except PlantError:
            raise
        except Exception as exc:
            logger.exception("plant_register: delivery model port failed")
            raise PlantError("package_plan_failed") from exc

    async def _plan(self, project_id: uuid.UUID) -> PackagePlan | None:
        provider = package_plan_provider()
        return None if provider is None else await self._port(provider.package_plan(self.session, project_id))

    async def _ofi(self, project_id: uuid.UUID, ofi_id: uuid.UUID | None) -> OwnerFurnishedRef | None:
        provider = package_plan_provider()
        if provider is None or ofi_id is None:
            return None
        return await self._port(provider.get_owner_furnished_item(self.session, project_id, ofi_id))

    @staticmethod
    def port_state() -> str:
        """``not_installed`` or ``installed`` (a failing call shows per item as ``package_plan_failed``)."""
        return "not_installed" if package_plan_provider() is None else "installed"

    async def route_findings(self, project_id: uuid.UUID, item: PlantItem) -> list[str]:
        if item.procurement_route is None:
            return ["route_missing"]
        if package_plan_provider() is None:
            return []
        try:
            plan = await self._plan(project_id)
            ofi = await self._ofi(project_id, item.owner_furnished_item_id)
        except PlantError as exc:
            return [exc.code]
        return calc.route_errors(item.procurement_route, item.contract_package_id, ofi, plan)

    async def set_route(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        route: str,
        contract_package_id: uuid.UUID | None,
        actor_id: uuid.UUID,
    ) -> PlantItem:
        """Record the procurement route; an owner-furnished route creates or attaches the OFI (rule 11)."""
        item = await self.get_item(project_id, item_id, lock=True)
        if calc.is_ordered(item.status) or item.status == "cancelled":
            raise conflict("route_frozen")
        cat = await self.catalogue(project_id)
        if cat.route(route) is None:
            raise PlantError("unknown_route")
        provider = package_plan_provider()
        ofi: OwnerFurnishedRef | None = None
        if provider is not None:
            plan = await self._plan(project_id)
            if plan is None:
                raise PlantError("package_plan_unavailable")
            if contract_package_id is not None and plan.package(contract_package_id) is None:
                raise PlantError("package_not_found", 404)
            if calc.needs_ofi(route):
                installer = None if route == "owner_furnished_owner_installed" else contract_package_id
                ofi = await self._port(
                    provider.ensure_owner_furnished_item(
                        self.session,
                        project_id,
                        plant_item_id=item.id,
                        title=item.title,
                        installer_package_id=installer,
                        actor_id=actor_id,
                    )
                )
            errors = calc.route_errors(route, contract_package_id, ofi, plan)
            if errors:
                raise blocked(errors)
        # Without the delivery-model module the route is recorded unchecked and no OFI exists.
        item.procurement_route = route
        item.contract_package_id = contract_package_id
        item.owner_furnished_item_id = ofi.id if ofi else None
        await self.session.flush()
        await self._audit(actor_id, "plant_item", item.id, "route_set", route=route, package=_s(contract_package_id))
        self._publish("item.updated", {"project_id": str(project_id), "item_id": str(item.id), "route": route})
        return item

    async def sync_item_state(
        self, project_id: uuid.UUID, item_id: uuid.UUID, *, actor_id: uuid.UUID | None
    ) -> PlantItem:
        """Rule 11: move ``ordered`` / ``delivered`` / ``installed`` / ``commissioned`` from their owners."""
        item = await self.get_item(project_id, item_id, lock=True)
        target = await self._external_target(project_id, item)
        if (
            target
            and calc.state_rank(target) > calc.state_rank(item.status)
            and calc.at_least(item.status, "route_set")
        ):
            before = item.status
            if ITEM_FSM.has_transition(before, target):
                await self._fsm(ITEM_FSM, item, target, actor_id, source="external")
            else:
                item.status = target
            await self._audit(actor_id, "plant_item", item.id, "state_read", from_status=before, to_status=target)
            self._publish(
                "item.state_changed",
                {"project_id": str(project_id), "item_id": str(item.id), "from": before, "to": target},
            )
        return item

    async def _external_target(self, project_id: uuid.UUID, item: PlantItem) -> str | None:
        best: str | None = None

        def bump(state: str) -> None:
            nonlocal best
            if best is None or calc.state_rank(state) > calc.state_rank(best):
                best = state

        if item.purchase_order_id is not None:
            from app.modules.procurement.models import PurchaseOrder

            po = await self.repo.get_scoped(PurchaseOrder, project_id, item.purchase_order_id)
            if po is not None and po.status in PO_ORDERED:
                bump("delivered" if po.status in PO_DELIVERED else "ordered")
        if item.owner_furnished_item_id is not None:
            ofi = await self._ofi(project_id, item.owner_furnished_item_id)
            if ofi is not None and ofi.progress in ("ordered", "delivered", "installed"):
                bump(ofi.progress)
        if item.cx_system_id is not None and calc.at_least(item.status, "installed"):
            from app.modules.commissioning.models import CxSystem

            cx = await self.repo.get_scoped(CxSystem, project_id, item.cx_system_id)
            if cx is not None and cx.status == "commissioned":
                bump("commissioned")
        return best

    # ── quotes (rules 2, 3, 4) ────────────────────────────────────────────

    async def add_quote(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID, today: date
    ) -> LeadTimeQuote:
        item = await self.get_item(project_id, item_id, lock=True)
        if item.status in ("handed_over", "cancelled"):
            raise conflict("item_closed")
        cat = await self.catalogue(project_id)
        if cat.source(data.get("source") or "") is None:
            raise PlantError("unknown_lead_time_source")
        if data.get("lead_basis", "from_order") not in calc.LEAD_BASES:
            raise PlantError("unknown_lead_basis")
        errors = calc.quote_errors(
            enquiry_date=data.get("enquiry_date"),
            response_date=data.get("response_date"),
            lead_min=int(data.get("lead_weeks_min", 0)),
            lead_max=int(data.get("lead_weeks_max", 0)),
            today=today,
        )
        if errors:
            raise blocked(errors)
        if data.get("source") == "supplier_catalogue" and not data.get("catalogue_entry_id"):
            raise PlantError("catalogue_entry_required")
        quote = LeadTimeQuote(
            project_id=project_id,
            plant_item_id=item.id,
            source=data["source"],
            vendor_id=data.get("vendor_id"),
            source_name=data.get("source_name") or "",
            enquiry_date=data["enquiry_date"],
            response_date=data.get("response_date"),
            lead_weeks_min=int(data["lead_weeks_min"]),
            lead_weeks_max=int(data["lead_weeks_max"]),
            lead_basis=data.get("lead_basis") or "from_order",
            valid_until=data.get("valid_until"),
            document_ref=data.get("document_ref") or "",
            catalogue_entry_id=data.get("catalogue_entry_id"),
            note=data.get("note") or "",
            is_basis=False,
            created_by=actor_id,
        )
        await self.repo.add(quote)
        current = [q for q in await self.repo.quotes(project_id, item.id) if q.is_basis]
        if data.get("set_basis") or not current:
            await self._make_basis(item, quote, current, actor_id)
        await self._audit(actor_id, "plant_lead_time_quote", quote.id, "created", item=str(item.id))
        return quote

    async def _make_basis(
        self, item: PlantItem, quote: LeadTimeQuote, current: Iterable[LeadTimeQuote], actor_id: uuid.UUID
    ) -> None:
        for old in current:
            if old.id == quote.id:
                continue
            old.is_basis = False
            old.superseded_by = quote.id
        await self.session.flush()
        quote.is_basis = True
        quote.superseded_by = None
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise conflict("concurrent_basis_change") from exc
        self._publish(
            "item.updated",
            {"project_id": str(item.project_id), "item_id": str(item.id), "basis_quote_id": str(quote.id)},
        )

    async def set_basis(
        self, project_id: uuid.UUID, item_id: uuid.UUID, quote_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> LeadTimeQuote:
        item = await self.get_item(project_id, item_id, lock=True)
        quote = await self.repo.get_scoped(LeadTimeQuote, project_id, quote_id)
        if quote is None or quote.plant_item_id != item.id:
            raise not_found("quote_not_found")
        current = [q for q in await self.repo.quotes(project_id, item.id) if q.is_basis]
        await self._make_basis(item, quote, current, actor_id)
        await self._audit(actor_id, "plant_lead_time_quote", quote.id, "basis_set", item=str(item.id))
        return quote

    # ── slot reservation (rule 13) ────────────────────────────────────────

    _SLOT_FIELDS = (
        "vendor_id",
        "vendor_name",
        "slot_from",
        "slot_to",
        "reservation_fee",
        "currency",
        "fee_refundable",
        "fee_credited_to_order",
        "convert_by_date",
        "terms",
        "commitment_item_id",
        "document_ref",
    )

    async def get_slot(
        self, project_id: uuid.UUID, item_id: uuid.UUID, slot_id: uuid.UUID, *, lock: bool = False
    ) -> SlotReservation:
        slot = await self.repo.get_scoped(SlotReservation, project_id, slot_id, lock=lock)
        if slot is None or slot.plant_item_id != item_id:
            raise not_found("slot_not_found")
        return slot

    async def create_slot(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> SlotReservation:
        item = await self.get_item(project_id, item_id, lock=True)
        if calc.is_ordered(item.status) or item.status == "cancelled":
            raise conflict("item_already_ordered")
        live = [s for s in await self.repo.slots(project_id, item.id) if s.status in ("requested", "held")]
        if live:
            raise conflict("slot_exists")
        slot = SlotReservation(project_id=project_id, plant_item_id=item.id, created_by=actor_id, status="requested")
        self._apply(slot, data, self._SLOT_FIELDS)
        self._check_slot(slot)
        await self.repo.add(slot)
        await self._audit(actor_id, "plant_slot_reservation", slot.id, "created", item=str(item.id))
        return slot

    @staticmethod
    def _apply(row: Any, data: dict[str, Any], fields: Iterable[str]) -> None:
        for key in fields:
            if key in data:
                value = data[key]
                setattr(row, key, value.strip() if isinstance(value, str) and key != "terms" else value)
        for key in ("vendor_name", "currency", "fee_refundable", "terms", "document_ref"):
            if hasattr(row, key) and getattr(row, key) is None:
                setattr(row, key, "")

    @staticmethod
    def _check_slot(slot: SlotReservation) -> None:
        if slot.fee_refundable and slot.fee_refundable not in ("none", "partial", "full"):
            raise PlantError("unknown_fee_refundable")
        if slot.reservation_fee is not None and Decimal(slot.reservation_fee) < 0:
            raise PlantError("fee_negative")
        if slot.slot_from and slot.slot_to and slot.slot_to < slot.slot_from:
            raise PlantError("slot_range_invalid")

    async def update_slot(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        slot_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
    ) -> SlotReservation:
        slot = await self.get_slot(project_id, item_id, slot_id, lock=True)
        if slot.status not in ("requested", "held"):
            raise conflict("slot_closed")
        self._apply(slot, data, self._SLOT_FIELDS)
        self._check_slot(slot)
        if slot.status == "held":
            missing = self.slot_hold_blockers(slot)
            if missing:
                raise blocked(missing)
        await self.session.flush()
        await self._audit(actor_id, "plant_slot_reservation", slot.id, "updated", fields=sorted(data))
        return slot

    @staticmethod
    def slot_hold_blockers(slot: SlotReservation) -> list[str]:
        """Rule 13: held needs fee, refund terms and a conversion deadline; a fee binds money via mod2."""
        out: list[str] = []
        if slot.reservation_fee is None or not slot.fee_refundable or slot.convert_by_date is None:
            out.append("slot_terms_incomplete")
        if slot.reservation_fee is not None and Decimal(slot.reservation_fee) > 0:
            if not slot.currency:
                out.append("slot_terms_incomplete:currency")
            if slot.commitment_item_id is None:
                out.append("slot_fee_needs_commitment")
        return out

    async def transition_slot(
        self, project_id: uuid.UUID, item_id: uuid.UUID, slot_id: uuid.UUID, target: str, *, actor_id: uuid.UUID
    ) -> SlotReservation:
        if target == "expired":
            raise conflict("state_read_from_source")
        slot = await self.get_slot(project_id, item_id, slot_id, lock=True)
        if not SLOT_FSM.has_transition(slot.status, target):
            raise conflict("invalid_transition")
        if target == "held":
            missing = self.slot_hold_blockers(slot)
            if missing:
                raise blocked(missing)
        before = slot.status
        await self._fsm(SLOT_FSM, slot, target, actor_id)
        await self._audit(
            actor_id, "plant_slot_reservation", slot.id, "state_changed", from_status=before, to_status=target
        )
        return slot

    async def expire_slots(self, project_id: uuid.UUID | None, *, today: date) -> list[SlotReservation]:
        """Rule 13: a held slot past ``convert_by_date`` expires and its item owner is told."""
        expired: list[SlotReservation] = []
        for slot in await self.repo.held_slots_due(project_id):
            if slot.convert_by_date is None or slot.convert_by_date >= today:
                continue
            await self._fsm(SLOT_FSM, slot, "expired", None, reason="convert_by_date passed")
            await self._audit(
                None, "plant_slot_reservation", slot.id, "expired", from_status="held", to_status="expired"
            )
            item = await self.repo.get_scoped(PlantItem, slot.project_id, slot.plant_item_id)
            ctx = {
                "project_id": str(slot.project_id),
                "item_code": getattr(item, "code", ""),
                "convert_by_date": slot.convert_by_date.isoformat(),
            }
            for uid in await self._recipients(slot.project_id, item):
                await self._notify(uid, "slot_expired", slot.plant_item_id, ctx)
            self._publish("slot.expired", {**ctx, "slot_id": str(slot.id), "item_id": str(slot.plant_item_id)})
            expired.append(slot)
        return expired

    async def _recipients(self, project_id: uuid.UUID, item: PlantItem | None) -> list[uuid.UUID]:
        area = await self._area(project_id)
        out = [getattr(item, "owner_user_id", None), getattr(area, "owner_user_id", None)]
        return list(dict.fromkeys(u for u in out if u))

    # ── decision paper (rule 9) ───────────────────────────────────────────

    async def get_paper(
        self, project_id: uuid.UUID, item_id: uuid.UUID, paper_id: uuid.UUID, *, lock: bool = False
    ) -> DecisionPaper:
        paper = await self.repo.get_scoped(DecisionPaper, project_id, paper_id, lock=lock)
        if paper is None or paper.plant_item_id != item_id:
            raise not_found("paper_not_found")
        return paper

    @staticmethod
    def _check_paper_body(paper: DecisionPaper) -> None:
        codes = [str(o.get("code") or "") for o in paper.options]
        if any(not c for c in codes) or len(set(codes)) != len(codes):
            raise PlantError("paper_option_codes_invalid")
        if paper.recommendation and paper.recommendation not in codes:
            raise PlantError("paper_recommendation_unknown")
        try:
            calc.weighted_scores(paper.options, paper.criteria)
        except (ValueError, ArithmeticError) as exc:
            raise PlantError("paper_scores_invalid") from exc

    async def create_paper(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> DecisionPaper:
        item = await self.get_item(project_id, item_id, lock=True)
        papers = await self.repo.papers(project_id, item.id)
        if any(p.status in ("draft", "submitted") for p in papers):
            raise conflict("paper_open")
        latest = papers[-1] if papers else None
        paper = DecisionPaper(
            project_id=project_id,
            plant_item_id=item.id,
            question=data.get("question") or "",
            options=list(data.get("options") or []),
            criteria=list(data.get("criteria") or []),
            recommendation=data.get("recommendation") or "",
            rationale=data.get("rationale") or "",
            supersedes_id=latest.id if latest else None,
            status="draft",
            created_by=actor_id,
        )
        self._check_paper_body(paper)
        await self.repo.add(paper)
        await self._audit(actor_id, "plant_decision_paper", paper.id, "created", item=str(item.id))
        return paper

    async def update_paper(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        paper_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
    ) -> DecisionPaper:
        paper = await self.get_paper(project_id, item_id, paper_id, lock=True)
        if paper.status != "draft":
            raise conflict("paper_not_draft")
        for key in ("question", "options", "criteria", "recommendation", "rationale"):
            if key in data and data[key] is not None:
                setattr(paper, key, list(data[key]) if key in ("options", "criteria") else data[key])
        self._check_paper_body(paper)
        await self.session.flush()
        await self._audit(actor_id, "plant_decision_paper", paper.id, "updated", fields=sorted(data))
        return paper

    async def submit_paper(
        self, project_id: uuid.UUID, item_id: uuid.UUID, paper_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> DecisionPaper:
        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        item = await self.get_item(project_id, item_id)
        paper = await self.get_paper(project_id, item_id, paper_id, lock=True)
        if paper.status != "draft":
            raise conflict("paper_not_draft")
        errors = calc.paper_errors(paper.options, item.vendor_bound_reason)
        if not paper.recommendation:
            errors.append("paper_needs_recommendation")
        if not (paper.rationale or "").strip():
            errors.append("paper_needs_rationale")
        if errors:
            raise blocked(errors)
        svc = ApprovalRouteService(self.session)
        routes = [
            r
            for r in await svc.list_routes(project_id=project_id, target_kind=PAPER_TARGET_KIND, include_inactive=False)
            if r.project_id == project_id
        ]
        if not routes:
            raise PlantError("no_decision_route")
        instance = await svc.start_instance(
            InstanceCreate(route_id=routes[0].id, target_kind=PAPER_TARGET_KIND, target_id=paper.id),
            started_by=actor_id,
        )
        paper.approval_instance_id = instance.id
        paper.submitted_by = actor_id
        await self._fsm(PAPER_FSM, paper, "submitted", actor_id)
        await self._audit(actor_id, "plant_decision_paper", paper.id, "submitted", instance=str(instance.id))
        return paper

    async def apply_paper_verdict(self, paper_id: uuid.UUID, instance_id: uuid.UUID | None, *, decision: str) -> None:
        """The approval route decided. Acts once, only on the instance the paper started."""
        paper = await self.session.get(DecisionPaper, paper_id, with_for_update=True)
        if paper is None or paper.status != "submitted":
            return
        if instance_id is not None and paper.approval_instance_id != instance_id:
            return
        target = "approved" if decision == "approved" else "rejected"
        if target == "approved":
            scores = calc.weighted_scores(paper.options, paper.criteria)
            paper.snapshot = {
                "question": paper.question,
                "options": paper.options,
                "criteria": paper.criteria,
                "scores": {k: str(v) for k, v in scores.items()},
                "recommendation": paper.recommendation,
                "rationale": paper.rationale,
            }
        paper.decided_at = datetime.now(UTC)
        await self._fsm(PAPER_FSM, paper, target, None, source="approval_route")
        await self._audit(None, "plant_decision_paper", paper.id, target, instance=_s(instance_id))
        if target == "approved":
            self._publish(
                "paper.approved",
                {"project_id": str(paper.project_id), "item_id": str(paper.plant_item_id), "paper_id": str(paper.id)},
            )

    # ── delivery limits (rule 14) ─────────────────────────────────────────

    async def put_limits(
        self, project_id: uuid.UUID, item_id: uuid.UUID, rows: list[dict[str, Any]], *, actor_id: uuid.UUID
    ) -> list[DeliveryLimit]:
        """Replace the item's delivery-limit row. One party per step (unique), steps from the catalogue."""
        item = await self.get_item(project_id, item_id, lock=True)
        cat = await self.catalogue(project_id)
        steps = set(cat.step_codes())
        parties = cat.codes("parties")
        seen: set[str] = set()
        for r in rows:
            step = r.get("step")
            if step not in steps:
                raise PlantError("unknown_step")
            if step in seen:
                raise conflict("two_parties_on_one_step")
            seen.add(step)
            if not r.get("party") and not r.get("contract_package_id"):
                raise PlantError("limit_needs_party")
            if r.get("party") and r["party"] not in parties:
                raise PlantError("unknown_party")
        # Package ids are checked only when the delivery-model module is installed.
        if package_plan_provider() is not None and any(r.get("contract_package_id") for r in rows):
            plan = await self._plan(project_id)
            if plan is None:
                raise PlantError("package_plan_unavailable")
            for r in rows:
                if r.get("contract_package_id") and plan.package(_uuid(r["contract_package_id"])) is None:
                    raise PlantError("package_not_found", 404)
        for old in await self.repo.limits(project_id, item.id):
            await self.session.delete(old)
        await self.session.flush()
        out = [
            DeliveryLimit(
                project_id=project_id,
                plant_item_id=item.id,
                step=r["step"],
                party=r.get("party") or "",
                contract_package_id=_uuid(r.get("contract_package_id")),
                note=r.get("note") or "",
            )
            for r in rows
        ]
        self.session.add_all(out)
        await self.session.flush()
        await self._audit(actor_id, "plant_item", item.id, "delivery_limits_set", steps=sorted(seen))
        return out

    # ── spares (rule 15) ──────────────────────────────────────────────────

    _SPARE_FIELDS = ("category", "description", "quantity", "unit", "supply_by", "supply_package_id", "handover_target")

    async def get_spare(self, project_id: uuid.UUID, item_id: uuid.UUID, spare_id: uuid.UUID) -> SparePartRequirement:
        row = await self.repo.get_scoped(SparePartRequirement, project_id, spare_id, lock=True)
        if row is None or row.plant_item_id != item_id:
            raise not_found("spare_not_found")
        return row

    async def create_spare(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> SparePartRequirement:
        item = await self.get_item(project_id, item_id)
        cat = await self.catalogue(project_id)
        if data.get("category") not in cat.codes("spare_categories"):
            raise PlantError("unknown_spare_category")
        row = SparePartRequirement(project_id=project_id, plant_item_id=item.id, status="required")
        self._apply(row, data, self._SPARE_FIELDS)
        for key, default in (
            ("description", ""),
            ("unit", "pcs"),
            ("supply_by", ""),
            ("handover_target", ""),
            ("waiver_reason", ""),
        ):
            if getattr(row, key, None) is None:
                setattr(row, key, default)
        if row.quantity is None:
            row.quantity = Decimal(1)
        await self.repo.add(row)
        await self._audit(actor_id, "plant_spare_part", row.id, "created", item=str(item.id))
        return row

    async def update_spare(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        spare_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
    ) -> SparePartRequirement:
        row = await self.get_spare(project_id, item_id, spare_id)
        if row.status in ("handed_over", "waived"):
            raise conflict("spare_closed")
        if "category" in data and data["category"] not in (await self.catalogue(project_id)).codes("spare_categories"):
            raise PlantError("unknown_spare_category")
        self._apply(row, data, self._SPARE_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "plant_spare_part", row.id, "updated", fields=sorted(data))
        return row

    async def transition_spare(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        spare_id: uuid.UUID,
        target: str,
        *,
        reason: str,
        actor_id: uuid.UUID,
    ) -> SparePartRequirement:
        row = await self.get_spare(project_id, item_id, spare_id)
        if not SPARE_FSM.has_transition(row.status, target):
            raise conflict("invalid_transition")
        if target == "waived":
            if not (reason or "").strip():
                raise PlantError("waiver_needs_reason")
            row.waiver_reason = reason.strip()
        before = row.status
        await self._fsm(SPARE_FSM, row, target, actor_id)
        await self._audit(actor_id, "plant_spare_part", row.id, "state_changed", from_status=before, to_status=target)
        return row

    async def delete_spare(
        self, project_id: uuid.UUID, item_id: uuid.UUID, spare_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        row = await self.get_spare(project_id, item_id, spare_id)
        if row.status != "required":
            raise conflict("spare_not_deletable")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "plant_spare_part", spare_id, "deleted")

    # ── IT services (rule 18) ─────────────────────────────────────────────

    _IT_FIELDS = (
        "kind",
        "description",
        "responsible_party",
        "needed_from",
        "needed_until",
        "needed_from_activity_id",
        "access_roles",
        "cde_container_id",
    )

    async def _check_container(self, project_id: uuid.UUID, container_id: uuid.UUID | None) -> None:
        if container_id is None:
            return
        from app.modules.cde.models import DocumentContainer

        if await self.repo.get_scoped(DocumentContainer, project_id, container_id) is None:
            raise PlantError("link_not_found", 404, detail="cde_container_id")

    async def get_it_service(self, project_id: uuid.UUID, service_id: uuid.UUID) -> ItService:
        row = await self.repo.get_scoped(ItService, project_id, service_id, lock=True)
        if row is None:
            raise not_found("it_service_not_found")
        return row

    async def create_it_service(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> ItService:
        cat = await self.catalogue(project_id)
        kind = next((k for k in cat.it_service_kinds if k.code == data.get("kind")), None)
        if kind is None:
            raise PlantError("unknown_it_service_kind")
        await self._check_container(project_id, _uuid(data.get("cde_container_id")))
        row = ItService(project_id=project_id, status="planned")
        self._apply(row, data, self._IT_FIELDS)
        row.description = row.description or ""
        row.responsible_party = row.responsible_party or kind.responsible_party
        row.access_roles = list(row.access_roles or [])
        await self.repo.add(row)
        await self._audit(actor_id, "plant_it_service", row.id, "created")
        return row

    async def update_it_service(
        self, project_id: uuid.UUID, service_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> ItService:
        row = await self.get_it_service(project_id, service_id)
        if "kind" in data and data["kind"] not in (await self.catalogue(project_id)).codes("it_service_kinds"):
            raise PlantError("unknown_it_service_kind")
        await self._check_container(project_id, _uuid(data.get("cde_container_id")))
        self._apply(row, data, self._IT_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "plant_it_service", row.id, "updated", fields=sorted(data))
        return row

    async def transition_it_service(
        self, project_id: uuid.UUID, service_id: uuid.UUID, target: str, *, actor_id: uuid.UUID
    ) -> ItService:
        row = await self.get_it_service(project_id, service_id)
        if not IT_FSM.has_transition(row.status, target):
            raise conflict("invalid_transition")
        if target == "provisioned" and row.kind == "cde_access" and row.cde_container_id is None:
            raise blocked(["it_cde_not_linked"])
        before = row.status
        await self._fsm(IT_FSM, row, target, actor_id)
        await self._audit(actor_id, "plant_it_service", row.id, "state_changed", from_status=before, to_status=target)
        return row

    async def delete_it_service(self, project_id: uuid.UUID, service_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self.get_it_service(project_id, service_id)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "plant_it_service", service_id, "deleted")

    # ── handover (rule 16) ────────────────────────────────────────────────

    async def handover(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        confirm: bool,
        service_contract_id: uuid.UUID | None,
        actor_id: uuid.UUID,
    ) -> PlantItem:
        """Hand the item over to operation. Creates the service asset only on explicit confirmation."""
        item = await self.get_item(project_id, item_id, lock=True)
        if item.status != "commissioned":
            raise conflict("handover_needs_commissioned")
        open_spares = [
            s.id for s in await self.repo.spares(project_id, item.id) if s.status not in ("handed_over", "waived")
        ]
        if open_spares:
            raise blocked(["spares_not_handed_over"])
        if not confirm:
            raise PlantError("handover_needs_confirmation")
        if service_contract_id is not None:
            from app.modules.service.models import ServiceContract
            from app.modules.service.schemas import ServiceAssetCreate
            from app.modules.service.service import ServiceService

            contract = await self.session.get(ServiceContract, service_contract_id)
            if contract is None or getattr(contract, "project_id", None) != project_id:
                raise PlantError("link_not_found", 404, detail="service_contract_id")
            cat = await self.catalogue(project_id)
            cls = cat.component_class(item.component_class_code)
            asset = await ServiceService(self.session).create_asset(
                ServiceAssetCreate(
                    contract_id=service_contract_id,
                    asset_tag=item.tag or None,
                    asset_type=(cls.code if cls else item.component_class_code)[:64],
                    name=item.title[:255],
                    location=item.space_ref or None,
                    metadata={"plant_item_id": str(item.id), "maintenance_strategy": item.maintenance_strategy},
                )
            )
            item.service_asset_id = asset.id
        before = item.status
        await self._fsm(ITEM_FSM, item, "handed_over", actor_id)
        await self._audit(actor_id, "plant_item", item.id, "handed_over", from_status=before, to_status="handed_over")
        self._publish(
            "item.state_changed",
            {"project_id": str(project_id), "item_id": str(item.id), "from": before, "to": "handed_over"},
        )
        return item

    # ── computed reads ────────────────────────────────────────────────────

    async def _activities(self, project_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
        if not ids:
            return {}
        from app.modules.schedule.models import Activity, Schedule

        stmt = (
            select(Activity.id, Activity.late_start, Activity.start_date)
            .join(Schedule, Schedule.id == Activity.schedule_id)
            .where(Activity.id.in_(ids), Schedule.project_id == project_id)
        )
        return {r.id: r for r in (await self.session.execute(stmt)).all()}

    async def _review_days(self, project_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, int | None]:
        if not ids:
            return {}
        from app.modules.submittals.models import Submittal

        stmt = select(Submittal.id, Submittal.review_period_days).where(
            Submittal.id.in_(ids), Submittal.project_id == project_id
        )
        return {r.id: r.review_period_days for r in (await self.session.execute(stmt)).all()}

    async def item_views(
        self, project_id: uuid.UUID, *, today: date, only: list[uuid.UUID] | None = None
    ) -> list[dict[str, Any]]:
        """Every item with its derived dates and rule inputs, in code order."""
        cat = await self.catalogue(project_id)
        items = [i for i in await self.repo.items(project_id) if only is None or i.id in only]
        quotes = await self.repo.quotes(project_id)
        papers = await self.repo.papers(project_id)
        slots = await self.repo.slots(project_id)
        limits = await self.repo.limits(project_id)
        spares = await self.repo.spares(project_id)
        acts = await self._activities(project_id, {i.need_activity_id for i in items if i.need_activity_id})
        reviews = await self._review_days(project_id, {i.submittal_id for i in items if i.submittal_id})
        steps = cat.step_codes()
        market = {s.code for s in cat.lead_time_sources if s.market_evidence}
        return [
            self._view(
                i,
                cat,
                today=today,
                quotes=[q for q in quotes if q.plant_item_id == i.id],
                papers=[p for p in papers if p.plant_item_id == i.id],
                slots=[s for s in slots if s.plant_item_id == i.id],
                limits={x.step: (x.party or _s(x.contract_package_id)) for x in limits if x.plant_item_id == i.id},
                spares=[s for s in spares if s.plant_item_id == i.id],
                activity=acts.get(i.need_activity_id) if i.need_activity_id else None,
                review_days=reviews.get(i.submittal_id) if i.submittal_id else None,
                steps=steps,
                market=market,
            )
            for i in items
        ]

    def _view(
        self,
        item: PlantItem,
        cat: PlantCatalogue,
        *,
        today: date,
        quotes: list[LeadTimeQuote],
        papers: list[DecisionPaper],
        slots: list[SlotReservation],
        limits: dict[str, Any],
        spares: list[SparePartRequirement],
        activity: Any,
        review_days: int | None,
        steps: tuple[str, ...],
        market: set[str],
    ) -> dict[str, Any]:
        cls = cat.component_class(item.component_class_code)
        qviews = [_quote_view(q) for q in quotes]
        basis = calc.basis_quote(qviews)
        weeks, lead_source = calc.effective_lead(basis, cls.typical_lead_weeks.max if cls else None)
        need, date_basis = calc.need_date(
            activity_late_start=getattr(activity, "late_start", None),
            activity_start=getattr(activity, "start_date", None),
            fixed=item.need_date_fixed,
        )
        buffers = calc.Buffers.merged(cat.order_buffer_days, item.order_buffers)
        lead_basis = basis.lead_basis if basis else "from_order"
        latest = calc.latest_order_date(need, weeks, lead_basis, buffers, review_period_days=review_days)
        ordered = calc.is_ordered(item.status)
        age = calc.quote_age_days(basis, today)
        max_age = cls.quote_max_age_days if cls else 90
        critical = (
            item.critical_override if item.critical_override is not None else bool(cls and cls.critical_by_default)
        )
        paper = papers[-1] if papers else None
        slot = next((s for s in reversed(slots) if s.status in ("requested", "held")), slots[-1] if slots else None)
        scheme = cat.scheme(item.redundancy_scheme) if item.redundancy_scheme else None
        return {
            "item": item,
            "id": item.id,
            "code": item.code,
            "critical": critical,
            "critical_default": bool(cls and cls.critical_by_default),
            "effective_lead_weeks": weeks,
            "lead_source": lead_source,
            "lead_basis": lead_basis,
            "market_evidence": calc.has_market_evidence(lead_source, market),
            "basis_quote_id": basis.id if basis else None,
            "basis_enquiry_date": basis.enquiry_date if basis else None,
            "basis_count": calc.basis_count(qviews),
            "quote_count": len(quotes),
            "quote_age_days": age,
            "quote_max_age_days": max_age,
            "quote_stale": calc.is_stale(age, max_age),
            "need_date": need,
            "date_basis": date_basis,
            "buffers": buffers,
            "review_period_days": review_days,
            "latest_order_date": latest,
            "float_days": (latest - today).days if latest else None,
            "order_status": calc.order_status(latest, today, ordered, cat.warn_days),
            "long_lead": calc.is_long_lead(weeks, cat.long_lead_threshold_weeks, item.long_lead_override),
            "long_lead_threshold_weeks": cat.long_lead_threshold_weeks,
            "needs_slot": bool(
                cls
                and cls.needs_slot_reservation_above_weeks is not None
                and weeks is not None
                and weeks > cls.needs_slot_reservation_above_weeks
            ),
            "paper_id": paper.id if paper else None,
            "paper_status": paper.status if paper else None,
            "paper_options": len(paper.options) if paper else 0,
            "slot_id": slot.id if slot else None,
            "slot_status": slot.status if slot else None,
            "slot_convert_by_date": slot.convert_by_date if slot else None,
            "slot_after_order_date": bool(slot and slot.convert_by_date and latest and slot.convert_by_date > latest),
            "delivery_limit_gaps": calc.delivery_limit_gaps(steps, limits),
            "spare_categories": sorted({s.category for s in spares}),
            "strategic_spares_ok": calc.strategic_spares_ok(
                critical, (s.category for s in spares), item.no_strategic_spare_reason
            ),
            "redundancy_ok": calc.redundancy_ok(scheme.min_quantity if scheme else None, Decimal(item.quantity)),
            # not_installed: owner-furnished info is not available (the module is absent), not a defect.
            "delivery_model": self.port_state(),
            "vendor_findings": calc.vendor_findings(item.vendor_policy, item.vendor_bound_reason, item.vendor_id),
        }

    async def long_lead(self, project_id: uuid.UUID, *, today: date) -> list[dict[str, Any]]:
        """Long-lead items with computed dates, least float first (no date last)."""
        views = [
            v
            for v in await self.item_views(project_id, today=today)
            if v["long_lead"] and v["item"].status != "cancelled"
        ]
        return sorted(views, key=lambda v: (v["float_days"] is None, v["float_days"] or 0, v["code"]))

    # ── validation, readiness, escalation ─────────────────────────────────

    async def validation_payload(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """The input of rule set ``plant_register`` (see ``validators.py``)."""
        views = [v for v in await self.item_views(project_id, today=today) if v["item"].status != "cancelled"]
        route_findings: dict[str, list[str]] = {}
        for v in views:
            item = v["item"]
            if item.procurement_route is not None:
                route_findings[item.code] = await self.route_findings(project_id, item)
        gate_date = await self._gate_date(project_id)
        slots = [s for s in await self.repo.slots(project_id) if s.status in ("requested", "held")]
        codes = {v["id"]: v["code"] for v in views}
        return {
            "today": today.isoformat(),
            "gate_date": gate_date.isoformat() if gate_date else None,
            "items": [self.view_payload(v) for v in views],
            "route_findings": route_findings,
            "slots": [
                {
                    "item": codes.get(s.plant_item_id, ""),
                    "status": s.status,
                    "terms_blockers": self.slot_hold_blockers(s) if s.status == "held" else [],
                    "convert_by_date": s.convert_by_date.isoformat() if s.convert_by_date else None,
                }
                for s in slots
                if s.plant_item_id in codes
            ],
            "it_services": [
                {
                    "id": str(r.id),
                    "kind": r.kind,
                    "needed_from": r.needed_from.isoformat() if r.needed_from else None,
                    "cde_container_id": _s(r.cde_container_id),
                    "status": r.status,
                }
                for r in await self.repo.it_services(project_id)
            ],
        }

    @staticmethod
    def view_payload(v: dict[str, Any]) -> dict[str, Any]:
        item: PlantItem = v["item"]
        return {
            "code": item.code,
            "status": item.status,
            "item_class": item.item_class,
            "critical": v["critical"],
            "long_lead": v["long_lead"],
            "procurement_route": item.procurement_route,
            "basis_count": v["basis_count"],
            "quote_count": v["quote_count"],
            "quote_stale": v["quote_stale"],
            "market_evidence": v["market_evidence"],
            "lead_source": v["lead_source"],
            "order_status": v["order_status"],
            "latest_order_date": v["latest_order_date"].isoformat() if v["latest_order_date"] else None,
            "paper_status": v["paper_status"],
            "delivery_limit_gaps": v["delivery_limit_gaps"],
            "strategic_spares_ok": v["strategic_spares_ok"],
            "redundancy_ok": v["redundancy_ok"],
            "vendor_findings": v["vendor_findings"],
            "slot_after_order_date": v["slot_after_order_date"],
        }

    async def _gate_date(self, project_id: uuid.UUID) -> date | None:
        from app.modules.project_governance.models import GovernanceGate

        stmt = select(GovernanceGate.target_date).where(
            GovernanceGate.project_id == project_id, GovernanceGate.code == GATE_CODE
        )
        return calc.parse_day((await self.session.execute(stmt)).scalars().first())

    async def readiness(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """SPEC 7: the m04 readiness at the gate to execution, item by item."""
        from app.modules.plant_register.validators import run_rules

        payload = await self.validation_payload(project_id, today=today)
        errors = [r for r in await run_rules(payload, "en") if not r["passed"] and r["severity"] == "error"]
        items = payload["items"]
        critical_open = [
            i["code"]
            for i in items
            if i["critical"] and (not calc.at_least(i["status"], "route_set") or i["paper_status"] != "approved")
        ]
        long_lead_open = [
            i["code"]
            for i in items
            if i["long_lead"]
            and (
                i["basis_count"] != 1
                or i["quote_stale"]
                or not (calc.is_ordered(i["status"]) or i["order_status"] != "overdue")
            )
        ]
        frame = await self._frame_document(project_id)
        frame_ok = bool(frame is not None and frame.container_id is not None)
        return {
            "ready": not errors and not critical_open and not long_lead_open and frame_ok,
            "error_findings": [{"rule_id": e["rule_id"], "element_ref": e["element_ref"]} for e in errors],
            "critical_open": critical_open,
            "long_lead_open": long_lead_open,
            "frame_document_attached": frame_ok,
        }

    async def _frame_document(self, project_id: uuid.UUID) -> Any:
        from app.modules.project_governance.models import GovernanceArea, GovernanceDocument

        stmt = (
            select(GovernanceDocument)
            .join(GovernanceArea, GovernanceArea.id == GovernanceDocument.area_id)
            .where(GovernanceDocument.project_id == project_id, GovernanceArea.code == AREA_CODE)
            .where(GovernanceDocument.doc_type == "m04_equipment_frame")
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def escalate(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """Rules 7 and 13: notify overdue order dates, expire slots past their deadline."""
        overdue = [v for v in await self.item_views(project_id, today=today) if v["order_status"] == "overdue"]
        for v in overdue:
            item = v["item"]
            ctx = {
                "project_id": str(project_id),
                "item_code": item.code,
                "latest_order_date": v["latest_order_date"].isoformat(),
            }
            for uid in await self._recipients(project_id, item):
                await self._notify(uid, "order_overdue", item.id, ctx)
            self._publish("order.overdue", {**ctx, "item_id": str(item.id)})
        expired = await self.expire_slots(project_id, today=today)
        return {"overdue": [v["code"] for v in overdue], "expired_slots": [str(s.id) for s in expired]}

    async def frame_summary(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """What the governance frame document ``m04_equipment_frame`` shows."""
        from app.modules.site_logistics.models import SitePlantPosition

        views = [v for v in await self.item_views(project_id, today=today) if v["item"].status != "cancelled"]
        positions = list(
            (
                await self.session.execute(
                    select(SitePlantPosition)
                    .where(SitePlantPosition.project_id == project_id)
                    .order_by(SitePlantPosition.kind)
                )
            ).scalars()
        )
        by_class: dict[str, int] = {}
        by_route: dict[str, int] = {}
        for v in views:
            by_class[v["item"].item_class] = by_class.get(v["item"].item_class, 0) + 1
            key = v["item"].procurement_route or "unset"
            by_route[key] = by_route.get(key, 0) + 1
        settings = await self.repo.settings(project_id)
        return {
            "catalogue": (
                f"{settings.catalogue_source}:{settings.catalogue_id}@{settings.catalogue_version}"
                if settings
                else f"shipped:{DEFAULT_CATALOGUE_ID}"
            ),
            "item_count": len(views),
            "critical_count": sum(1 for v in views if v["critical"]),
            "long_lead_count": sum(1 for v in views if v["long_lead"]),
            "overdue_count": sum(1 for v in views if v["order_status"] == "overdue"),
            "by_item_class": by_class,
            "by_route": by_route,
            "long_lead": [
                {
                    "code": v["code"],
                    "title": v["item"].title,
                    "effective_lead_weeks": v["effective_lead_weeks"],
                    "lead_source": v["lead_source"],
                    "latest_order_date": v["latest_order_date"],
                    "float_days": v["float_days"],
                    "procurement_route": v["item"].procurement_route,
                }
                for v in sorted(views, key=lambda v: (v["float_days"] is None, v["float_days"] or 0))
                if v["long_lead"]
            ],
            "site_plant": [
                {
                    "id": p.id,
                    "kind": p.kind,
                    "name": p.name,
                    "reach_m": p.reach_m,
                    "max_load_t": p.max_load_t,
                    "from_date": p.from_date,
                    "to_date": p.to_date,
                }
                for p in positions
            ],
            "it_services": [
                {"id": r.id, "kind": r.kind, "responsible_party": r.responsible_party, "status": r.status}
                for r in await self.repo.it_services(project_id)
            ],
        }
