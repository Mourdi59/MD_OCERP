# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Logistics plan service (framework module 6): areas, media, transports, customs, neighbourhood.

Every method takes the ``project_id`` the router verified with
``verify_project_access`` and looks every child row up by ``(project_id, id)``,
so an id of another project answers 404 exactly like a missing one (rule 20).
Soft links into other modules (schedule activity, takt schedule and location,
purchase order, geo overlay, correspondence) are checked against the project
too before they are stored.

A read never writes: the concept row (the catalogue pin), ``stage_0`` and the
neighbourhood row are created by the first WRITE of a plan (:meth:`_start`).
Until then the reads answer with the defaults a fresh project would get.

The rules live in :mod:`app.modules.site_logistics.planning`; this layer loads
the rows, calls them, writes, audits (``log_activity``) and publishes after
commit. The service flushes; the request's session dependency commits.
"""

from __future__ import annotations

import inspect
import logging
import math
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.modules.site_logistics import events as ev
from app.modules.site_logistics import hosting, links
from app.modules.site_logistics import planning as pl
from app.modules.site_logistics.catalogue import (
    SITE_LOGISTICS_KIND,
    SiteLogisticsCatalogue,
    default_catalogue_id,
    merged,
    register_kind,
    shipped_catalogues,
)
from app.modules.site_logistics.errors import LogisticsError, conflict, not_found
from app.modules.site_logistics.geometry import (
    GeometryError,
    polygon_area_m2,
    validate_point,
    validate_polygon,
    validate_route,
)
from app.modules.site_logistics.models import (
    AreaAllocation,
    CoordinationEntry,
    CustomsCase,
    CustomsDocument,
    CustomsLine,
    DeliveryBooking,
    ExpansionStage,
    Gate,
    LaydownZone,
    LogisticsConcept,
    MediaConnection,
    MediaDemand,
    NeighbourhoodPlan,
    NeighbourIssue,
    PermitTransportLink,
    SiteArea,
    Transport,
    TransportPermit,
)

logger = logging.getLogger(__name__)

MODULE = "site_logistics"
_ONWARD = ("in_transit", "arrived", "closed")
# What stays editable on a transport that is under way: none of it feeds a rule.
_TRANSPORT_FREE_FIELDS = ("title", "carrier_name", "route_notes", "waste_record_ref")
# A permit may be reworked only while it is still a draft or an application.
_PERMIT_OPEN_STATES = ("draft", "applied")
# What a permit's coverage is made of; frozen once the authority has decided.
_PERMIT_FROZEN_FIELDS = ("transport_id", "permit_kind", "valid_from", "valid_to", "allowed_windows")
# A customs case takes lines, documents and checklist changes only before it is declared.
_CUSTOMS_OPEN_STATES = ("open", "documents_complete")
# What decides the document checklist of a case (rule 15).
_CUSTOMS_CHECKLIST_FIELDS = ("direction", "incoterm", "transport_mode")


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _dec(value: Any) -> str | None:
    return None if value is None else str(value)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _parse_day(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _finding(rule: str, code: str, severity: str, ref: Any, **params: Any) -> dict[str, Any]:
    return {
        "rule": rule,
        "code": code,
        "severity": severity,
        "ref": _s(ref),
        "params": pl.json_safe(params),
    }


# Columns a client may set per entity. Everything else is service-owned.
_STAGE_FIELDS = (
    "code",
    "title",
    "ordinal",
    "from_activity_id",
    "to_activity_id",
    "from_date",
    "to_date",
    "plan_document_id",
    "plan_metres_per_pixel",
    "plan_origin_px",
)
_AREA_FIELDS = (
    "code",
    "name",
    "area_kind",
    "geometry",
    "frame",
    "area_m2_declared",
    "geo_overlay_id",
    "takt_location_id",
    "owner_party",
)
_MEDIA_FIELDS = (
    "media_kind",
    "phase",
    "provider_name",
    "provider_vendor_id",
    "connection_point",
    "connection_point_geometry",
    "capacity_unit",
    "available_capacity",
    "contracted_capacity",
    "application_ref",
    "applied_on",
    "promised_on",
    "connected_on",
    "document_ref",
)
_DEMAND_FIELDS = ("media_connection_id", "media_kind", "stage_id", "consumer", "plant_item_id", "peak_demand")
_TRANSPORT_FIELDS = (
    "direction",
    "transport_kind",
    "title",
    "carrier_name",
    "origin",
    "destination",
    "gate_id",
    "planned_window_start",
    "planned_window_end",
    "po_id",
    "plant_item_id",
    "waste_record_ref",
    "customs_case_id",
    "axle_load_t",
    "gross_weight_t",
    "height_m",
    "width_m",
    "length_m",
    "turning_radius_m",
    "route_geojson",
    "route_notes",
    "escort_required",
    "load_class",
)
_PERMIT_FIELDS = (
    "transport_id",
    "permit_kind",
    "authority",
    "reference",
    "applied_on",
    "valid_from",
    "valid_to",
    "allowed_windows",
    "conditions",
    "route_geojson",
    "document_ref",
    "authority_permit_id",
)
_CUSTOMS_FIELDS = (
    "direction",
    "title",
    "incoterm",
    "named_place",
    "transport_mode",
    "country_of_origin",
    "country_of_destination",
    "declarant_party",
    "broker_name",
    "customs_value",
    "currency",
    "declaration_ref",
    "cleared_on",
    "po_id",
)
_CUSTOMS_VALUE_FIELDS = ("customs_value", "currency")
_LINE_FIELDS = (
    "description",
    "hs_code",
    "commodity_code_id",
    "quantity",
    "unit",
    "net_mass_kg",
    "value",
    "currency",
    "origin_country",
    "preferential_origin",
    "sort_order",
)
_NEIGHBOURHOOD_FIELDS = (
    "zone_type",
    "noise_limit_source",
    "day_dba",
    "night_dba",
    "quiet_hours",
    "site_traffic_routes",
    "parking_note",
    "municipality_contact",
    "correspondence_thread_id",
)
_COMPLAINT_FIELDS = (
    "kind",
    "reported_on",
    "reporter",
    "location",
    "description",
    "transport_id",
    "delivery_id",
    "response",
    "response_due",
    "owner_user_id",
)
_COORD_FIELDS = ("entry_date", "body", "topic", "outcome", "next_action_due", "correspondence_id")
_JSON_FIELDS = (
    "geometry",
    "connection_point_geometry",
    "route_geojson",
    "allowed_windows",
    "quiet_hours",
    "site_traffic_routes",
    "location",
    "strategy",
)


# The permission an action on a plan record needs, where it is not ``write``. It is the
# permission its route requires; a test walks the routes and holds the two together.
_CAN_PERMISSION: dict[tuple[str, str], str] = {
    ("transport", "transition"): "approve",
    ("concept", "pin_catalogue"): "approve",
}
_UNSET: Any = object()


def merge_flow(stored: dict[str, Any] | None, sent: dict[str, Any]) -> dict[str, Any]:
    """A flow of the concept as a save leaves it: what the request names, and the stored value of the rest.

    The flows are saved as one list, so a form that does not show a field (the
    takt schedule of a just-in-time flow) would otherwise erase it with every
    save. A field sent as ``null`` is cleared; a field not sent is kept.
    """
    return {**(stored or {}), **sent}


def can_permission(kind: str, action: str) -> str:
    """The permission the route behind ``action`` on a ``kind`` record requires."""
    return f"site_logistics.{_CAN_PERMISSION.get((kind, action), 'write')}"


@dataclass(frozen=True)
class PlanPerms:
    """What the caller may do on the plan, read the way the routes read it."""

    write: bool = False
    approve: bool = False
    customs: bool = False

    def has(self, kind: str, action: str) -> bool:
        return bool(getattr(self, _CAN_PERMISSION.get((kind, action), "write")))


def _flag(permitted: bool, reason: str | None = None, *, applies: bool = True) -> dict[str, Any]:
    """One allowed move: whether the action exists for the record now, whether it would pass, and why not."""
    if not permitted:
        # What the route answers first, whatever the record would say.
        return {"allowed": False, "applies": applies, "reason": "permission_denied"}
    if not applies:
        return {"allowed": False, "applies": False, "reason": reason}
    return {"allowed": reason is None, "applies": True, "reason": reason}


async def _why_not(guard: Callable[[], Any]) -> str | None:
    """The code the guard refuses with, ``None`` when it lets the write through."""
    try:
        out = guard()
        if inspect.isawaitable(out):
            await out
    except LogisticsError as exc:
        return exc.code
    return None


class LogisticsPlanService:
    """Orchestrates the logistics plan of one project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        register_kind()

    # ── infrastructure ─────────────────────────────────────────────────────

    async def _audit(self, actor_id: Any, entity_type: str, entity_id: Any, action: str, **kw: Any) -> None:
        for key in ("metadata", "before_state", "after_state"):
            if kw.get(key) is not None:
                kw[key] = pl.json_safe(kw[key])
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
        publish_after_commit(self.session, name, pl.json_safe(data), source_module=MODULE)

    async def _notify(self, user_id: Any, kind: str, entity_type: str, entity_id: Any, ctx: dict[str, Any]) -> None:
        """Best effort, inside a savepoint so a failure never poisons the write."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            safe = pl.json_safe(ctx)
            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"site_logistics_{kind}",
                    title_key=f"notifications.site_logistics.{kind}.title",
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    body_key=f"notifications.site_logistics.{kind}.body",
                    body_context=safe,
                    action_url=f"/projects/{safe.get('project_id')}/logistics",
                    metadata=safe,
                )
        except Exception:
            logger.debug("site_logistics: notification %s failed", kind, exc_info=True)

    async def governance_target(self, project_id: uuid.UUID) -> hosting.GovernanceTarget:
        """Where logistics sits in the project's governance model, resolved from catalogue tags now."""
        return await hosting.project_target(self.session, project_id)

    async def _area_owner(self, project_id: uuid.UUID) -> uuid.UUID | None:
        """The owner of the governance area that hosts logistics, the addressee of logistics notifications."""
        target = await self.governance_target(project_id)
        return await hosting.area_owner(self.session, project_id, target.area_code)

    async def _get(
        self, model: Any, project_id: uuid.UUID, row_id: Any, code: str = "not_found", *, lock: bool = False
    ) -> Any:
        """One row of this project, 404 otherwise. ``lock`` takes the row lock a state change needs."""
        rid = _uuid(row_id)
        if rid is None:
            raise not_found(code)
        stmt = select(model).where(model.id == rid, model.project_id == project_id)
        if lock:
            # Two writers of one state machine queue on the row instead of both
            # checking the state they read before the other committed.
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise not_found(code)
        return row

    async def _list(self, model: Any, project_id: uuid.UUID, *order: Any, **where: Any) -> list[Any]:
        stmt = select(model).where(model.project_id == project_id)
        for key, value in where.items():
            if value is not None:
                stmt = stmt.where(getattr(model, key) == value)
        if order:
            stmt = stmt.order_by(*order)
        return list((await self.session.execute(stmt)).scalars().all())

    def _apply(self, row: Any, data: dict[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
        """Set the allowed keys ``data`` carries. An explicit null on a NOT NULL column is a 422."""
        changed: dict[str, Any] = {}
        columns = type(row).__table__.c
        for key in allowed:
            if key not in data:
                continue
            value = data[key]
            if value is None and key in columns and not columns[key].nullable:
                raise LogisticsError("field_required", 422, detail=key)
            if key in _JSON_FIELDS and value is not None:
                value = pl.json_safe(value)
            if key.endswith("_id") and value is not None:
                value = _uuid(value)
            setattr(row, key, value)
            changed[key] = value
        return changed

    @staticmethod
    def _require(data: dict[str, Any], *keys: str) -> None:
        """A create body has to carry these; a missing one is a 422, never a NOT NULL violation."""
        for key in keys:
            if data.get(key) is None or data.get(key) == "":
                raise LogisticsError("field_required", 422, detail=key)

    async def _insert(self, row: Any, taken: str) -> None:
        """Insert inside a savepoint: losing a race on a unique constraint answers 409 ``taken``."""
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError as exc:
            raise conflict(taken) from exc

    async def _soft(self, kind: str, value: Any, project_id: uuid.UUID) -> None:
        """404 unless a soft link names a row of this project (rule 20)."""
        rid = _uuid(value)
        if rid is None:
            return
        owner = await self._owner_of(kind, rid)
        if owner != project_id:
            raise not_found(f"{kind}_not_found")

    async def _port(self, kind: str, value: Any, project_id: uuid.UUID, current: Any = None) -> None:
        """A soft link into a module that plugs its resolver in (plant register, authority permits).

        Without a resolver nothing can say whose row the id names, so the link is
        refused rather than stored unchecked. ``current`` is the stored value on
        an update: sending it again is not a new link and is not checked again.
        """
        rid = _uuid(value)
        if rid is None or (current is not None and rid == current):
            return
        resolver = links.resolver(kind)
        if resolver is None:
            raise LogisticsError("link_target_unavailable", 422, detail=kind)
        if await resolver(self.session, rid) != project_id:
            raise not_found(f"{kind}_not_found")

    async def _master(self, kind: str, value: Any) -> None:
        """404 unless an id names a row of a tenant-wide master table (vendor, commodity code)."""
        rid = _uuid(value)
        if rid is None:
            return
        from app.modules.supplier_catalogs.models import CommodityCode, Vendor

        model = {"vendor": Vendor, "commodity_code": CommodityCode}[kind]
        if (await self.session.execute(select(model.id).where(model.id == rid))).scalar_one_or_none() is None:
            raise not_found(f"{kind}_not_found")

    async def _owner_of(self, kind: str, rid: uuid.UUID) -> uuid.UUID | None:
        if kind == "activity":
            from app.modules.schedule.models import Activity, Schedule

            stmt = select(Schedule.project_id).join(Activity, Activity.schedule_id == Schedule.id)
            return (await self.session.execute(stmt.where(Activity.id == rid))).scalar_one_or_none()
        if kind in ("takt_schedule", "takt_location"):
            from app.modules.schedule_advanced.models import Location, MasterSchedule, TaktSchedule

            stmt = select(MasterSchedule.project_id).join(
                TaktSchedule, TaktSchedule.master_schedule_id == MasterSchedule.id
            )
            if kind == "takt_location":
                stmt = stmt.join(Location, Location.takt_schedule_id == TaktSchedule.id).where(Location.id == rid)
            else:
                stmt = stmt.where(TaktSchedule.id == rid)
            return (await self.session.execute(stmt)).scalar_one_or_none()
        if kind == "plan_document":
            from app.modules.documents.models import Document

            return (
                await self.session.execute(select(Document.project_id).where(Document.id == rid))
            ).scalar_one_or_none()
        if kind == "po":
            from app.modules.procurement.models import PurchaseOrder

            return (
                await self.session.execute(select(PurchaseOrder.project_id).where(PurchaseOrder.id == rid))
            ).scalar_one_or_none()
        if kind == "geo_overlay":
            from app.modules.geo_hub.models import GeoOverlay

            return (
                await self.session.execute(select(GeoOverlay.project_id).where(GeoOverlay.id == rid))
            ).scalar_one_or_none()
        if kind in ("correspondence", "correspondence_thread"):
            from app.modules.correspondence.models import Correspondence

            return (
                await self.session.execute(select(Correspondence.project_id).where(Correspondence.id == rid))
            ).scalar_one_or_none()
        local = {
            "stage": ExpansionStage,
            "area": SiteArea,
            "media": MediaConnection,
            "transport": Transport,
            "permit": TransportPermit,
            "customs_case": CustomsCase,
            "gate": Gate,
            "zone": LaydownZone,
            "delivery": DeliveryBooking,
        }[kind]
        return (await self.session.execute(select(local.project_id).where(local.id == rid))).scalar_one_or_none()

    async def link_options(
        self, project_id: uuid.UUID, kind: str, *, search: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        """The rows of this project a link field of the plan can point at, as ``{id, label, detail}``.

        The project filter is the join :meth:`_owner_of` checks a stored link
        with, so the list never offers what a write would refuse.
        """
        if kind == "activity":
            from app.modules.schedule.models import Activity, Schedule

            label, detail = Activity.name, Activity.wbs_code
            stmt = (
                select(Activity.id, label, detail, Activity.start_date, Activity.end_date)
                .join(Schedule, Activity.schedule_id == Schedule.id)
                .where(Schedule.project_id == project_id)
                .order_by(Activity.sort_order, Activity.name)
            )
        elif kind in ("takt_schedule", "takt_location"):
            from app.modules.schedule_advanced.models import Location, MasterSchedule, TaktSchedule

            base = select(TaktSchedule.id, TaktSchedule.name, MasterSchedule.name).select_from(TaktSchedule)
            label, detail = TaktSchedule.name, MasterSchedule.name
            if kind == "takt_location":
                label, detail = Location.name, TaktSchedule.name
                base = (
                    select(Location.id, label, detail, TaktSchedule.id)
                    .select_from(Location)
                    .join(TaktSchedule, Location.takt_schedule_id == TaktSchedule.id)
                )
            stmt = (
                base.join(MasterSchedule, TaktSchedule.master_schedule_id == MasterSchedule.id)
                .where(MasterSchedule.project_id == project_id)
                .order_by(TaktSchedule.name, *((Location.sequence_order,) if kind == "takt_location" else ()))
            )
        elif kind == "purchase_order":
            from app.modules.procurement.models import PurchaseOrder

            label, detail = PurchaseOrder.po_number, PurchaseOrder.status
            stmt = (
                select(PurchaseOrder.id, label, detail, PurchaseOrder.delivery_date)
                .where(PurchaseOrder.project_id == project_id)
                .order_by(PurchaseOrder.po_number)
            )
        elif kind == "document":
            from app.modules.documents.models import Document

            label, detail = Document.name, Document.drawing_number
            stmt = (
                select(Document.id, label, detail, Document.mime_type)
                .where(Document.project_id == project_id)
                .order_by(Document.name)
            )
        else:
            raise LogisticsError("unknown_link_kind", 422, detail=kind)
        if search and search.strip():
            # The caller's text is matched literally: its wildcards are not ours to run.
            needle = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(label.ilike(f"%{needle}%", escape="\\"))
        extra = {
            "activity": ("start_date", "end_date"),
            "takt_location": ("takt_schedule_id",),
            "purchase_order": ("delivery_date",),
            "document": ("mime_type",),
        }.get(kind, ())
        out = []
        for row in (await self.session.execute(stmt.limit(limit))).all():
            item = {"id": str(row[0]), "label": row[1] or "", "detail": row[2] or ""}
            item.update({name: _iso(value) for name, value in zip(extra, row[3:], strict=True)})
            out.append(item)
        return out

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    # ── site time ──────────────────────────────────────────────────────────

    async def site_tz(self, project_id: uuid.UUID) -> tzinfo | None:
        """The site's time zone from the concept, ``None`` while nobody has set one.

        Every time-of-day, weekday and date rule needs it. Without one the rules
        report ``site_timezone_missing``; they never fall back to UTC or to the
        offset a client happened to send.
        """
        name = (
            await self.session.execute(
                select(LogisticsConcept.site_timezone).where(LogisticsConcept.project_id == project_id)
            )
        ).scalar_one_or_none()
        return pl.site_zone(name)

    @staticmethod
    def _today(tz: tzinfo | None) -> date:
        """The server's date on the site clock (UTC while the site has no zone). Never a client value."""
        return datetime.now(tz or UTC).date()

    async def site_today(self, project_id: uuid.UUID) -> date:
        return self._today(await self.site_tz(project_id))

    # ── catalogue and concept (the pin) ────────────────────────────────────

    async def concept(self, project_id: uuid.UUID) -> LogisticsConcept | None:
        """The project's concept row, ``None`` until the plan's first write. Reads never create it."""
        return (
            await self.session.execute(select(LogisticsConcept).where(LogisticsConcept.project_id == project_id))
        ).scalar_one_or_none()

    async def _default_pin(self, project_id: uuid.UUID) -> tuple[str, str, int]:
        from app.modules.project_governance.public import default_catalogue_pin

        project = await self._project(project_id)
        country = getattr(project, "country_code", None)
        # The active pack may name the catalogue new projects plan with; ours is the fallback.
        pin = default_catalogue_pin(SITE_LOGISTICS_KIND, country)
        if pin is not None:
            return pin.source, pin.catalogue_id, pin.version
        cid = default_catalogue_id(country)
        return "shipped", cid, shipped_catalogues()[cid].version

    async def _ensure_concept(self, project_id: uuid.UUID) -> LogisticsConcept:
        """The concept row for a WRITE, created with the country's default pin when missing.

        Two first writes race on ``uq_oe_site_concept_project``; the loser's insert
        is rolled back to its savepoint and it reads the winner's row.
        """
        row = await self.concept(project_id)
        if row is not None:
            return row
        source, cid, version = await self._default_pin(project_id)
        try:
            async with self.session.begin_nested():
                row = LogisticsConcept(
                    project_id=project_id,
                    catalogue_source=source,
                    catalogue_id=cid,
                    catalogue_version=version,
                    strategy=[],
                )
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            row = await self.concept(project_id)
            if row is None:
                raise
        return row

    async def _start(self, project_id: uuid.UUID) -> LogisticsConcept:
        """What the first write of a plan creates: the concept row and ``stage_0``."""
        concept = await self._ensure_concept(project_id)
        if not await self._list(ExpansionStage, project_id):
            try:
                async with self.session.begin_nested():
                    self.session.add(
                        ExpansionStage(project_id=project_id, code="stage_0", title="", ordinal=0, state="planned")
                    )
                    await self.session.flush()
            except IntegrityError:
                # Another first write created it between the read and the insert.
                logger.debug("site_logistics: stage_0 of %s already exists", project_id)
        return concept

    async def plan_started(self, project_id: uuid.UUID) -> bool:
        """True once the plan carries real content, not merely the rows a first write creates.

        This is what arms the blocking gate evidence: an area, a utility, a
        transport, a permit, a customs case, a complaint, a noise limit source or a
        saved concept. Opening the tab, or a concept row holding only its catalogue
        pin, is not a plan.
        """
        for model in (SiteArea, MediaConnection, Transport, TransportPermit, CustomsCase, NeighbourIssue):
            if (
                await self.session.execute(select(model.id).where(model.project_id == project_id).limit(1))
            ).first() is not None:
                return True
        concept = await self.concept(project_id)
        if concept is not None and (concept.strategy or concept.rules_text.strip() or concept.document_ref):
            return True
        plan = await self.neighbourhood(project_id)
        return bool(plan is not None and plan.noise_limit_source)

    async def catalogue(self, project_id: uuid.UUID) -> SiteLogisticsCatalogue:
        """The pinned catalogue with its ``extends`` chain resolved; the country default before any pin."""
        from app.modules.project_governance.catalogue import InvalidCatalogueError
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        concept = await self.concept(project_id)
        if concept is None:
            source, cid, version = await self._default_pin(project_id)
        else:
            source, cid, version = concept.catalogue_source, concept.catalogue_id, concept.catalogue_version
        try:
            # A pin this module stored (or its shipped default): it was checked when it was
            # written (pin_catalogue) and has to keep resolving for every project member.
            obj = await resolve_catalogue(self.session, source, cid, version, kind=SITE_LOGISTICS_KIND, from_pin=True)
        except GovernanceError as exc:
            raise LogisticsError(exc.code, exc.status_code) from exc
        except InvalidCatalogueError as exc:
            # A pinned pack catalogue whose file no longer loads. The rule faults are the
            # detail; the message of the exception carries a server path and is not shown.
            raise LogisticsError("catalogue_invalid", 422, detail="; ".join(exc.errors)) from exc
        shipped = shipped_catalogues()
        try:
            return merged(obj, shipped.__getitem__)
        except (KeyError, ValueError) as exc:
            raise LogisticsError("catalogue_invalid", 422, detail=str(exc)) from exc

    async def concept_view(self, project_id: uuid.UUID) -> dict[str, Any]:
        """The concept as the API shows it; a project without one reads its defaults and ``id`` null."""
        row = await self.concept(project_id)
        if row is not None:
            return concept_out(row)
        source, cid, version = await self._default_pin(project_id)
        return {
            "id": None,
            "catalogue_source": source,
            "catalogue_id": cid,
            "catalogue_version": version,
            "strategy": [],
            "delivery_open": None,
            "delivery_close": None,
            "max_deliveries_per_hour": None,
            "rules_text": "",
            "document_ref": None,
            "site_timezone": None,
            "updated_at": None,
        }

    async def pin_catalogue(
        self,
        project_id: uuid.UUID,
        *,
        tenant_id: str | None,
        source: str,
        catalogue_id: str,
        version: int | None,
        actor_id: Any,
    ) -> LogisticsConcept:
        """Re-pin the project's catalogue: shipped, of the active pack, or a tenant's published version."""
        from app.modules.project_governance.catalogue_store import CatalogueStore
        from app.modules.project_governance.errors import GovernanceError

        concept = await self._start(project_id)
        try:
            pinned = await CatalogueStore(self.session).assert_pinnable(
                tenant_id, source, catalogue_id, version, kind=SITE_LOGISTICS_KIND
            )
        except GovernanceError as exc:
            raise LogisticsError(exc.code, exc.status_code) from exc
        before = f"{concept.catalogue_source}:{concept.catalogue_id}@{concept.catalogue_version}"
        concept.catalogue_source, concept.catalogue_id, concept.catalogue_version = source, catalogue_id, pinned
        await self.session.flush()
        await self.catalogue(project_id)
        await self._audit(
            actor_id, "logistics_concept", concept.id, "catalogue_pinned", metadata={"before": before, "after": pinned}
        )
        return concept

    def _need(self, cat: SiteLogisticsCatalogue, group: str, code: Any, error: str) -> None:
        if code is None or code not in cat.codes(group):
            raise LogisticsError(error, 422, detail=str(code))

    # ── stages ─────────────────────────────────────────────────────────────

    async def stages(self, project_id: uuid.UUID) -> list[ExpansionStage]:
        """Every stage in order. Empty until the plan's first write creates ``stage_0``."""
        return await self._list(ExpansionStage, project_id, ExpansionStage.ordinal, ExpansionStage.code)

    async def create_stage(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> ExpansionStage:
        await self._start(project_id)
        row = ExpansionStage(project_id=project_id, state="planned", title="", ordinal=0)
        data = dict(data)
        await self._stage_links(project_id, data)
        self._apply(row, data, _STAGE_FIELDS)
        self._plan_backdrop_order(row)
        await self._unique_code(ExpansionStage, project_id, row.code, None)
        await self._insert(row, "code_taken")
        await self._audit(actor_id, "logistics_stage", row.id, "stage_created", metadata={"code": row.code})
        return row

    async def update_stage(
        self, project_id: uuid.UUID, stage_id: Any, data: dict[str, Any], actor_id: Any
    ) -> ExpansionStage:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found", lock=True)
        data = dict(data)
        await self._stage_links(project_id, data)
        if "code" in data:
            await self._unique_code(ExpansionStage, project_id, data["code"], row.id)
        changed = await self._apply_unique(row, data, _STAGE_FIELDS)
        self._plan_backdrop_order(row)
        await self._audit(actor_id, "logistics_stage", row.id, "stage_updated", metadata=changed)
        return row

    async def _apply_unique(self, row: Any, data: dict[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
        """Apply and flush inside a savepoint, so a code taken meanwhile answers 409 and not 500."""
        try:
            async with self.session.begin_nested():
                changed = self._apply(row, data, allowed)
                await self.session.flush()
        except IntegrityError as exc:
            raise conflict("code_taken") from exc
        return changed

    async def transition_stage(self, project_id: uuid.UUID, stage_id: Any, target: str, actor_id: Any) -> Any:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found", lock=True)
        self._move(pl.STAGE_FSM, row, target)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, f"stage_{target}", to_status=target)
        return row

    async def delete_stage(self, project_id: uuid.UUID, stage_id: Any, actor_id: Any) -> None:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found", lock=True)
        await self._guard_stage_delete(project_id, row)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, "stage_deleted")
        self._publish(ev.AREA_BALANCE_CHANGED, {"project_id": project_id, "stage_id": row.id})

    async def _stage_links(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        for key in ("from_activity_id", "to_activity_id"):
            await self._soft("activity", data.get(key), project_id)
        await self._soft("plan_document", data.get("plan_document_id"), project_id)
        origin = data.get("plan_origin_px")
        if origin is not None:
            ok = (
                isinstance(origin, list | tuple)
                and len(origin) == 2
                and all(isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) for v in origin)
            )
            if not ok:
                raise LogisticsError("plan_origin_invalid", 422)
            data["plan_origin_px"] = [float(origin[0]), float(origin[1])]
        scale = data.get("plan_metres_per_pixel")
        if scale is not None and not Decimal(str(scale)) > 0:
            raise LogisticsError("plan_scale_invalid", 422)

    @staticmethod
    def _plan_backdrop_order(row: ExpansionStage) -> None:
        """A calibration belongs to an image: without the document there is nothing it calibrates."""
        if row.plan_document_id is None and (row.plan_metres_per_pixel is not None or row.plan_origin_px is not None):
            raise LogisticsError("plan_calibration_without_image", 422)

    @staticmethod
    def _route_check(data: dict[str, Any]) -> None:
        """A route drawn on the site plan is a line in the local metre frame (rule 20 of inputs: nothing unchecked)."""
        if data.get("route_geojson") is not None:
            try:
                validate_route(data["route_geojson"])
            except GeometryError as exc:
                raise LogisticsError("route_invalid", 422, detail=str(exc)) from exc

    @staticmethod
    def _connection_point_check(data: dict[str, Any]) -> None:
        if data.get("connection_point_geometry") is not None:
            try:
                validate_point(data["connection_point_geometry"])
            except GeometryError as exc:
                raise LogisticsError("connection_point_invalid", 422, detail=str(exc)) from exc

    async def _unique_code(self, model: Any, project_id: uuid.UUID, code: Any, own_id: Any) -> None:
        if not code:
            raise LogisticsError("code_required", 422)
        other = (
            await self.session.execute(select(model.id).where(model.project_id == project_id, model.code == code))
        ).scalar_one_or_none()
        if other is not None and other != own_id:
            raise conflict("code_taken")

    async def stage_dates(self, stage: ExpansionStage) -> tuple[date | None, date | None]:
        """Stage start and end READ from the linked schedule activities, fixed dates as fallback."""
        from app.modules.schedule.models import Activity

        start, end = stage.from_date, stage.to_date
        for attr, pick in (("from_activity_id", "start_date"), ("to_activity_id", "end_date")):
            aid = getattr(stage, attr)
            if aid is None:
                continue
            value = (
                await self.session.execute(select(getattr(Activity, pick)).where(Activity.id == aid))
            ).scalar_one_or_none()
            day = _parse_day(value)
            if day is None:
                continue
            if attr == "from_activity_id":
                start = day
            else:
                end = day
        return start, end

    @staticmethod
    def _guard_move(fsm: dict[str, tuple[str, ...]], row: Any, target: str) -> None:
        if not pl.can_move(fsm, row.state, target):
            raise conflict("invalid_transition", detail=f"{row.state}->{target}")

    def _move(self, fsm: dict[str, tuple[str, ...]], row: Any, target: str) -> str:
        current = row.state
        self._guard_move(fsm, row, target)
        row.state = target
        return current

    # ── guards: what a write refuses, without changing anything ────────────
    #
    # Each write calls its guard before it touches the row, and ``can`` calls the
    # same guard to say what the write would answer. Nothing here mutates.

    async def _guard_stage_delete(self, project_id: uuid.UUID, row: Any, count: int | None = None) -> None:
        if row.state == "active":
            # Its allocations and demands are what the site runs on today; they are
            # not removed by a delete that cascades.
            raise conflict("stage_active")
        if count is None:
            count = len(await self._list(ExpansionStage, project_id))
        if count <= 1:
            raise conflict("last_stage")

    @classmethod
    def _guard_media_transition(cls, row: Any, target: str) -> None:
        if target == "contracted" and row.contracted_capacity is None:
            raise LogisticsError("contracted_capacity_required", 422)
        cls._guard_move(pl.MEDIA_FSM, row, target)

    @staticmethod
    def _demand_frozen(row: Any) -> tuple[str, ...]:
        """Rule 9: the plant position is the one number; it is changed there."""
        return ("peak_demand",) if row.site_plant_position_id is not None else ()

    @staticmethod
    def _transport_frozen(row: Any) -> tuple[str, ...]:
        """The fields an edit may no longer change; refuses the edit once the transport is over."""
        if row.state in ("closed", "cancelled"):
            raise conflict("transport_closed")
        if row.state in _ONWARD:
            # Under way, what the rules were checked against no longer moves.
            return tuple(k for k in _TRANSPORT_FIELDS if k not in _TRANSPORT_FREE_FIELDS)
        return ()

    @staticmethod
    def _guard_transport_delete(row: Any) -> None:
        if row.state in _ONWARD:
            raise conflict("transport_under_way")

    async def _guard_transport_transition(
        self,
        project_id: uuid.UUID,
        cat: SiteLogisticsCatalogue,
        row: Any,
        target: str,
        *,
        view: dict[str, Any] | None = None,
        quiet: Any = _UNSET,
    ) -> date | None:
        """Refuse a move the rules do not allow. Returns the goods receipt date an arrival is read from."""
        if target not in pl.TRANSPORT_STATES:
            raise LogisticsError("invalid_transition", 422)
        self._guard_move(pl.TRANSPORT_FSM, row, target)
        if target == "scheduled":
            await self._assert_schedulable(project_id, cat, row, view=view, quiet=quiet)
        if target == "arrived" and row.direction == "inbound" and row.po_id is not None:
            # Rule 19: arrival of PO goods is read from the goods receipt, never recorded twice.
            received = await self._goods_receipt_date(row.po_id, row.in_transit_on)
            if received is None:
                raise conflict("goods_receipt_missing")
            return received
        return None

    @staticmethod
    def _permit_frozen(row: Any) -> tuple[str, ...]:
        """What a permit's coverage is made of, frozen once the authority has decided."""
        return () if row.state in _PERMIT_OPEN_STATES else (*_PERMIT_FROZEN_FIELDS, "covers_transport_ids")

    @classmethod
    def _guard_permit_transition(cls, row: Any, target: str) -> None:
        cls._guard_move(pl.PERMIT_FSM, row, target)
        if target == "granted" and (row.valid_from is None or row.valid_to is None):
            raise LogisticsError("validity_required", 422)

    @staticmethod
    def _guard_permit_delete(row: Any) -> None:
        if row.state == "granted":
            # Deleting it would silently withdraw what its transports were scheduled on.
            raise conflict("permit_frozen")

    @staticmethod
    def _customs_frozen(row: Any) -> tuple[str, ...]:
        """The checklist fields a declared case no longer changes; refuses the edit once it is cleared."""
        if row.state in ("cleared", "closed"):
            raise conflict("customs_closed")
        return () if row.state in _CUSTOMS_OPEN_STATES else _CUSTOMS_CHECKLIST_FIELDS

    @staticmethod
    def _guard_customs_delete(row: Any) -> None:
        if row.state not in _CUSTOMS_OPEN_STATES:
            raise conflict("customs_declared")

    @staticmethod
    def _guard_case_open(case: Any, also: tuple[str, ...] = ()) -> None:
        """A change to a case's lines or documents: 409 once it is declared."""
        if case.state in ("cleared", "closed"):
            raise conflict("customs_closed")
        if case.state not in (*_CUSTOMS_OPEN_STATES, *also):
            raise conflict("customs_declared")

    async def _guard_customs_transition(
        self,
        project_id: uuid.UUID,
        cat: SiteLogisticsCatalogue,
        row: Any,
        target: str,
        *,
        docs: list[dict[str, Any]] | None = None,
        line_count: int | None = None,
    ) -> None:
        self._guard_move(pl.CUSTOMS_FSM, row, target)
        if target in ("documents_complete", "declared"):
            if docs is None:
                docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=row.id)]
            missing = pl.missing_required(docs)
            if missing:
                raise LogisticsError("required_document_missing", 422, violations=[{"code": k} for k in missing])
            if line_count is None:
                line_count = len(await self._list(CustomsLine, project_id, customs_case_id=row.id))
            if not line_count:
                raise LogisticsError("customs_without_lines", 422)
        if target == "declared" and self.incoterm_of(cat, row) is None:
            raise LogisticsError("incoterm_unknown", 422)

    @classmethod
    def _guard_document_move(cls, case: Any, row: Any, target: str) -> None:
        if not pl.can_move(pl.CUSTOMS_DOCUMENT_FSM, row.state, target):
            raise conflict("invalid_transition")
        if case.state == "held" and target == "missing" and row.required:
            raise conflict("customs_declared")

    @staticmethod
    def _guard_complaint_edit(row: Any) -> None:
        if row.state == "closed":
            raise conflict("complaint_closed")

    @classmethod
    def _guard_complaint_transition(cls, row: Any, target: str) -> None:
        cls._guard_move(pl.COMPLAINT_FSM, row, target)
        if target in ("action_taken", "closed") and not row.response.strip():
            raise LogisticsError("response_required", 422)

    # ── allowed moves ──────────────────────────────────────────────────────

    @staticmethod
    async def _transitions(
        fsm: dict[str, tuple[str, ...]], row: Any, permitted: bool, guard: Callable[[str], Any]
    ) -> dict[str, dict[str, Any]]:
        """One flag per other state: a state the record cannot reach from here does not apply."""
        out: dict[str, dict[str, Any]] = {}
        for target in fsm:
            if target == row.state:
                continue
            if not pl.can_move(fsm, row.state, target):
                out[target] = _flag(permitted, "invalid_transition", applies=False)
            else:
                out[target] = _flag(permitted, await _why_not(lambda t=target: guard(t)))
        return out

    @staticmethod
    def _edit(permitted: bool, frozen_of: Callable[[], tuple[str, ...]]) -> tuple[dict[str, Any], list[str]]:
        try:
            frozen = frozen_of()
        except LogisticsError as exc:
            return _flag(permitted, exc.code), []
        return _flag(permitted), sorted(frozen)

    def can_create(self, kind: str, perms: PlanPerms) -> dict[str, Any]:
        """The ``can`` of a list: whether the caller may add a record of this kind."""
        return {"create": _flag(perms.has(kind, "create"))}

    async def can_in_case(self, project_id: uuid.UUID, case_id: Any, perms: PlanPerms) -> dict[str, dict[str, Any]]:
        """Whether a line or a document can be added to a customs case in its present state."""
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        return {
            "line": _flag(perms.has("line", "create"), await _why_not(lambda: self._guard_case_open(case))),
            "document": _flag(
                perms.has("document", "create"), await _why_not(lambda: self._guard_case_open(case, ("held",)))
            ),
        }

    async def can(
        self,
        project_id: uuid.UUID,
        kind: str,
        row: Any,
        perms: PlanPerms,
        *,
        count: int | None = None,
        cat: SiteLogisticsCatalogue | None = None,
        view: dict[str, Any] | None = None,
        quiet: Any = _UNSET,
        case: Any = None,
        docs: list[dict[str, Any]] | None = None,
        line_count: int | None = None,
    ) -> dict[str, Any]:
        """What the caller may do with one plan record right now.

        Every flag is ``{"allowed", "applies", "reason"}``. ``reason`` is the error
        code the write would answer with, or ``permission_denied``; the guards asked
        are the ones the writes call, so a flag cannot disagree with its write. The
        keyword arguments are what a list already loaded, so a page of records does
        not query once per row.
        """
        edit, delete, move = perms.has(kind, "edit"), perms.has(kind, "delete"), perms.has(kind, "transition")
        if kind == "concept":
            return {"edit": _flag(edit), "pin_catalogue": _flag(perms.has(kind, "pin_catalogue"))}
        if kind == "neighbourhood":
            return {"edit": _flag(edit)}
        if kind in ("area", "coordination"):
            return {"edit": _flag(edit), "delete": _flag(delete)}
        if kind == "stage":
            return {
                "edit": _flag(edit),
                "delete": _flag(delete, await _why_not(lambda: self._guard_stage_delete(project_id, row, count))),
                "transitions": await self._transitions(
                    pl.STAGE_FSM, row, move, lambda t: self._guard_move(pl.STAGE_FSM, row, t)
                ),
            }
        if kind == "media":
            return {
                "edit": _flag(edit),
                "delete": _flag(delete),
                "transitions": await self._transitions(
                    pl.MEDIA_FSM, row, move, lambda t: self._guard_media_transition(row, t)
                ),
            }
        if kind == "demand":
            return {"edit": _flag(edit), "frozen_fields": list(self._demand_frozen(row)), "delete": _flag(delete)}
        if kind == "transport":
            if cat is None:
                cat = await self.catalogue(project_id)
            flag, frozen = self._edit(edit, lambda: self._transport_frozen(row))
            return {
                "edit": flag,
                "frozen_fields": frozen,
                "delete": _flag(delete, await _why_not(lambda: self._guard_transport_delete(row))),
                "transitions": await self._transitions(
                    pl.TRANSPORT_FSM,
                    row,
                    move,
                    lambda t: self._guard_transport_transition(project_id, cat, row, t, view=view, quiet=quiet),
                ),
            }
        if kind == "permit":
            return {
                "edit": _flag(edit),
                "frozen_fields": sorted(self._permit_frozen(row)),
                "delete": _flag(delete, await _why_not(lambda: self._guard_permit_delete(row))),
                "transitions": await self._transitions(
                    pl.PERMIT_FSM, row, move, lambda t: self._guard_permit_transition(row, t)
                ),
            }
        if kind == "customs":
            if cat is None:
                cat = await self.catalogue(project_id)
            if docs is None:
                docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=row.id)]
            if line_count is None:
                line_count = len(await self._list(CustomsLine, project_id, customs_case_id=row.id))
            flag, frozen = self._edit(edit, lambda: self._customs_frozen(row))
            return {
                "edit": flag,
                "frozen_fields": frozen,
                "delete": _flag(delete, await _why_not(lambda: self._guard_customs_delete(row))),
                "transitions": await self._transitions(
                    pl.CUSTOMS_FSM,
                    row,
                    move,
                    lambda t: self._guard_customs_transition(project_id, cat, row, t, docs=docs, line_count=line_count),
                ),
                "add_line": _flag(perms.has("line", "create"), await _why_not(lambda: self._guard_case_open(row))),
                "add_document": _flag(
                    perms.has("document", "create"), await _why_not(lambda: self._guard_case_open(row, ("held",)))
                ),
            }
        if kind in ("line", "document"):
            if case is None:
                case = await self._get(CustomsCase, project_id, row.customs_case_id, "customs_not_found")
            if kind == "line":
                why = await _why_not(lambda: self._guard_case_open(case))
                return {"edit": _flag(edit, why), "delete": _flag(delete, why)}
            # A held case may still receive what customs asked for.
            why = await _why_not(lambda: self._guard_case_open(case, ("held",)))
            if why is not None:
                closed = {t: _flag(edit, why) for t in pl.CUSTOMS_DOCUMENT_FSM if t != row.state}
                return {"edit": _flag(edit, why), "transitions": closed}
            return {
                "edit": _flag(edit),
                "transitions": await self._transitions(
                    pl.CUSTOMS_DOCUMENT_FSM, row, edit, lambda t: self._guard_document_move(case, row, t)
                ),
            }
        if kind == "complaint":
            return {
                "edit": _flag(edit, await _why_not(lambda: self._guard_complaint_edit(row))),
                "delete": _flag(delete),
                "transitions": await self._transitions(
                    pl.COMPLAINT_FSM, row, move, lambda t: self._guard_complaint_transition(row, t)
                ),
            }
        raise KeyError(kind)

    # ── areas and allocations (rules 1 to 4) ───────────────────────────────

    async def create_area(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> SiteArea:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        self._need(cat, "area_kinds", data.get("area_kind"), "unknown_area_kind")
        row = SiteArea(project_id=project_id, frame="local", name="", owner_party="")
        await self._area_checks(project_id, cat, data, row.frame)
        self._apply(row, data, _AREA_FIELDS)
        await self._unique_code(SiteArea, project_id, row.code, None)
        self._compute_area(row)
        await self._insert(row, "code_taken")
        await self._audit(actor_id, "logistics_area", row.id, "area_created", metadata={"code": row.code})
        return row

    async def update_area(self, project_id: uuid.UUID, area_id: Any, data: dict[str, Any], actor_id: Any) -> SiteArea:
        cat = await self.catalogue(project_id)
        row = await self._get(SiteArea, project_id, area_id, "area_not_found", lock=True)
        await self._area_checks(project_id, cat, data, row.frame)
        if "code" in data:
            await self._unique_code(SiteArea, project_id, data["code"], row.id)
        changed = await self._apply_unique(row, data, _AREA_FIELDS)
        self._compute_area(row)
        allocs = await self._list(AreaAllocation, project_id, site_area_id=row.id)
        for a in allocs:
            if pl.allocation_exceeds_area(a.allocated_m2, row.effective_m2):
                raise LogisticsError("allocation_exceeds_area", 422, detail=str(a.stage_id))
        await self.session.flush()
        await self._audit(actor_id, "logistics_area", row.id, "area_updated", metadata=changed)
        self._publish(ev.AREA_BALANCE_CHANGED, {"project_id": project_id, "area_id": row.id})
        return row

    async def delete_area(self, project_id: uuid.UUID, area_id: Any, actor_id: Any) -> None:
        row = await self._get(SiteArea, project_id, area_id, "area_not_found", lock=True)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_area", row.id, "area_deleted")
        self._publish(ev.AREA_BALANCE_CHANGED, {"project_id": project_id, "area_id": row.id})

    async def _area_checks(
        self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any], current_frame: str
    ) -> None:
        if "area_kind" in data:
            self._need(cat, "area_kinds", data["area_kind"], "unknown_area_kind")
        if data.get("frame") is not None and data["frame"] not in ("local", "wgs84"):
            raise LogisticsError("frame_invalid", 422)
        if data.get("geometry") is not None:
            try:
                validate_polygon(data["geometry"], data.get("frame") or current_frame)
            except GeometryError as exc:
                raise LogisticsError("geometry_invalid", 422, detail=str(exc)) from exc
        await self._soft("geo_overlay", data.get("geo_overlay_id"), project_id)
        await self._soft("takt_location", data.get("takt_location_id"), project_id)

    @staticmethod
    def _compute_area(row: SiteArea) -> None:
        """``area_m2`` from the polygon in the row's frame; a frame change re-reads the same coordinates."""
        try:
            row.area_m2 = polygon_area_m2(row.geometry, row.frame) if row.geometry else None
        except GeometryError as exc:
            raise LogisticsError("geometry_invalid", 422, detail=str(exc)) from exc

    async def put_allocations(
        self, project_id: uuid.UUID, area_id: Any, items: list[dict[str, Any]], actor_id: Any
    ) -> list[AreaAllocation]:
        """Replace the allocations of one area, one row per stage (rule 2: never above the area).

        The area row is locked, so two replacements of one area queue; the one that
        still loses on ``uq_oe_site_alloc_area_stage`` answers 409.
        """
        cat = await self.catalogue(project_id)
        area = await self._get(SiteArea, project_id, area_id, "area_not_found", lock=True)
        seen: set[uuid.UUID] = set()
        rows = []
        for item in items:
            stage = await self._get(ExpansionStage, project_id, item.get("stage_id"), "stage_not_found")
            if stage.id in seen:
                raise LogisticsError("duplicate_stage", 422)
            seen.add(stage.id)
            kind = item.get("area_kind") or area.area_kind
            self._need(cat, "area_kinds", kind, "unknown_area_kind")
            raw = item.get("allocated_m2")
            m2 = Decimal(str(raw if raw is not None else (area.effective_m2 or 0)))
            if m2 < 0:
                raise LogisticsError("allocation_negative", 422)
            if pl.allocation_exceeds_area(m2, area.effective_m2):
                raise LogisticsError("allocation_exceeds_area", 422, detail=str(stage.id))
            rows.append(
                AreaAllocation(
                    project_id=project_id,
                    site_area_id=area.id,
                    stage_id=stage.id,
                    area_kind=kind,
                    allocated_m2=m2,
                    use_note=str(item.get("use_note") or ""),
                )
            )
        try:
            async with self.session.begin_nested():
                await self.session.execute(
                    delete(AreaAllocation).where(
                        AreaAllocation.project_id == project_id, AreaAllocation.site_area_id == area.id
                    )
                )
                self.session.add_all(rows)
                await self.session.flush()
        except IntegrityError as exc:
            raise conflict("allocations_changed") from exc
        await self._audit(actor_id, "logistics_area", area.id, "allocations_set", metadata={"count": len(rows)})
        self._publish(ev.AREA_BALANCE_CHANGED, {"project_id": project_id, "area_id": area.id})
        return rows

    async def _facts(self, project_id: uuid.UUID, stage_id: uuid.UUID) -> list[pl.AllocationFact]:
        stmt = (
            select(AreaAllocation, SiteArea)
            .join(SiteArea, SiteArea.id == AreaAllocation.site_area_id)
            .where(AreaAllocation.project_id == project_id, AreaAllocation.stage_id == stage_id)
        )
        return [
            pl.AllocationFact(
                site_area_id=str(area.id),
                area_kind=alloc.area_kind,
                allocated_m2=alloc.allocated_m2,
                area_m2=area.effective_m2,
                geometry=area.geometry,
                frame=area.frame,
            )
            for alloc, area in (await self.session.execute(stmt)).all()
        ]

    async def _site_total_fallback(self, project_id: uuid.UUID) -> Decimal | None:
        areas = await self._list(SiteArea, project_id, area_kind="site_total")
        values = [a.effective_m2 for a in areas if a.effective_m2 is not None]
        return sum(values, Decimal("0")) if values else None

    # ── media (rules 8 to 10) ──────────────────────────────────────────────

    async def create_media(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> MediaConnection:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        self._need(cat, "media_kinds", data.get("media_kind"), "unknown_media_kind")
        await self._master("vendor", data.get("provider_vendor_id"))
        self._connection_point_check(data)
        row = MediaConnection(project_id=project_id, state="identified")
        self._apply(row, data, _MEDIA_FIELDS)
        if not row.capacity_unit:
            row.capacity_unit = cat.entry("media_kinds", row.media_kind).capacity_unit
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_created", metadata={"kind": row.media_kind})
        return row

    async def update_media(
        self, project_id: uuid.UUID, media_id: Any, data: dict[str, Any], actor_id: Any
    ) -> MediaConnection:
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found", lock=True)
        if "media_kind" in data:
            self._need(await self.catalogue(project_id), "media_kinds", data["media_kind"], "unknown_media_kind")
        await self._master("vendor", data.get("provider_vendor_id"))
        self._connection_point_check(data)
        changed = self._apply(row, data, _MEDIA_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_updated", metadata=changed)
        await self._publish_media_short(project_id)
        return row

    async def transition_media(self, project_id: uuid.UUID, media_id: Any, target: str, actor_id: Any) -> Any:
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found", lock=True)
        self._guard_media_transition(row, target)
        before = self._move(pl.MEDIA_FSM, row, target)
        if target == "connected" and row.connected_on is None:
            row.connected_on = await self.site_today(project_id)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_transition", from_status=before, to_status=target)
        await self._publish_media_short(project_id)
        return row

    async def delete_media(self, project_id: uuid.UUID, media_id: Any, actor_id: Any) -> None:
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found", lock=True)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_deleted")
        await self._publish_media_short(project_id)

    async def demands(self, project_id: uuid.UUID, media_id: Any) -> list[MediaDemand]:
        media = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        return await self._list(MediaDemand, project_id, MediaDemand.consumer, media_connection_id=media.id)

    async def create_demand(
        self, project_id: uuid.UUID, media_id: Any, data: dict[str, Any], actor_id: Any
    ) -> MediaDemand:
        media = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        self._require(data, "stage_id")
        await self._get(ExpansionStage, project_id, data.get("stage_id"), "stage_not_found")
        await self._port("plant_item", data.get("plant_item_id"), project_id)
        row = MediaDemand(project_id=project_id, media_connection_id=media.id, media_kind=media.media_kind)
        self._apply(
            row, {k: v for k, v in data.items() if k not in ("media_connection_id", "media_kind")}, _DEMAND_FIELDS
        )
        raw_factor = data.get("simultaneity_factor")
        row.simultaneity_factor = self._factor("1" if raw_factor is None else raw_factor)
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", media.id, "demand_created", metadata={"demand": row.id})
        await self._publish_media_short(project_id)
        return row

    async def update_demand(
        self, project_id: uuid.UUID, demand_id: Any, data: dict[str, Any], actor_id: Any
    ) -> MediaDemand:
        row = await self._get(MediaDemand, project_id, demand_id, "demand_not_found", lock=True)
        if any(k in data for k in self._demand_frozen(row)):
            raise conflict("demand_owned_by_plant_position")
        if "stage_id" in data:
            self._require(data, "stage_id")
            await self._get(ExpansionStage, project_id, data["stage_id"], "stage_not_found")
        await self._port("plant_item", data.get("plant_item_id"), project_id, row.plant_item_id)
        if data.get("media_connection_id") is not None:
            media = await self._get(MediaConnection, project_id, data["media_connection_id"], "media_not_found")
            data = {**data, "media_kind": media.media_kind}
        changed = self._apply(row, data, _DEMAND_FIELDS)
        if "simultaneity_factor" in data:
            self._require(data, "simultaneity_factor")
            row.simultaneity_factor = self._factor(data["simultaneity_factor"])
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.media_connection_id, "demand_updated", metadata=changed)
        await self._publish_media_short(project_id)
        return row

    async def delete_demand(self, project_id: uuid.UUID, demand_id: Any, actor_id: Any) -> None:
        row = await self._get(MediaDemand, project_id, demand_id, "demand_not_found", lock=True)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.media_connection_id, "demand_deleted")

    async def _publish_media_short(self, project_id: uuid.UUID) -> None:
        """Publish ``media.short`` for every stage and utility that needs more than is contracted now."""
        cat = await self.catalogue(project_id)
        today = await self.site_today(project_id)
        for stage in await self.stages(project_id):
            if stage.state == "closed":
                continue
            for m in await self.media_balance(project_id, stage, cat, today):
                if m["short"]:
                    self._publish(
                        ev.MEDIA_SHORT,
                        {
                            "project_id": project_id,
                            "stage_id": stage.id,
                            "media_kind": m["media_kind"],
                            "required": m["required"],
                            "contracted": m["contracted"],
                        },
                    )

    @staticmethod
    def _factor(value: Any) -> Decimal:
        factor = Decimal(str(value))
        if not Decimal("0") <= factor <= Decimal("1"):
            raise LogisticsError("simultaneity_factor_range", 422)
        return factor

    async def sync_plant_power_demand(
        self,
        project_id: uuid.UUID,
        *,
        site_plant_position_id: Any,
        power_demand_kva: Decimal | None,
        stage_id: Any,
        consumer: str,
        actor_id: Any = None,
        trusted: bool = False,
    ) -> MediaDemand | None:
        """Rule 9: a plant position's power demand IS its media demand row, idempotent on the position.

        Called by the plant position save path (module 5) with ``trusted=True``: it
        just saved the position it names. Any other caller (the HTTP route) has the
        position checked against the project through the plant register's resolver.
        A position without power or without a stage removes its demand row. The row
        joins the project's power connection when there is exactly one; otherwise it
        stays unsourced until the planner picks one.

        ``uq_oe_site_demand_plant_position`` keeps it one row: two saves of one
        position that both find none race on the index, and the loser updates the
        winner's row.
        """
        pid = _uuid(site_plant_position_id)
        if pid is None:
            raise LogisticsError("plant_position_required", 422)
        if not trusted:
            await self._port("plant_position", pid, project_id)
        existing = await self._plant_demand(project_id, pid, lock=True)
        if power_demand_kva is None or stage_id is None or Decimal(str(power_demand_kva)) <= 0:
            if existing is not None:
                await self.session.delete(existing)
                await self.session.flush()
            return None
        await self._start(project_id)
        stage = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")
        power = await self._list(MediaConnection, project_id, media_kind="power")
        values = {
            "stage_id": stage.id,
            "consumer": consumer,
            "peak_demand": Decimal(str(power_demand_kva)),
        }
        row = existing
        if row is None:
            try:
                async with self.session.begin_nested():
                    row = MediaDemand(
                        project_id=project_id,
                        site_plant_position_id=pid,
                        media_kind="power",
                        simultaneity_factor=Decimal("1"),
                        media_connection_id=power[0].id if len(power) == 1 else None,
                        **values,
                    )
                    self.session.add(row)
                    await self.session.flush()
            except IntegrityError:
                row = await self._plant_demand(project_id, pid, lock=True)
                if row is None:
                    raise
        for key, value in values.items():
            setattr(row, key, value)
        if row.media_connection_id is None and len(power) == 1:
            row.media_connection_id = power[0].id
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_media", row.media_connection_id, "plant_demand_synced", metadata={"position": pid}
        )
        await self._publish_media_short(project_id)
        return row

    async def _plant_demand(self, project_id: uuid.UUID, position_id: uuid.UUID, *, lock: bool) -> MediaDemand | None:
        stmt = select(MediaDemand).where(
            MediaDemand.project_id == project_id, MediaDemand.site_plant_position_id == position_id
        )
        if lock:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def media_balance(
        self, project_id: uuid.UUID, stage: ExpansionStage, cat: SiteLogisticsCatalogue, today: date
    ) -> list[dict[str, Any]]:
        """Rule 8 and 10 per media kind of one stage."""
        reserve = cat.resolved_thresholds().media_reserve_pct
        demands = await self._list(MediaDemand, project_id, stage_id=stage.id)
        media = {m.id: m for m in await self._list(MediaConnection, project_id)}
        start, _end = await self.stage_dates(stage)
        out = []
        for kind in sorted({d.media_kind for d in demands}):
            rows = [d for d in demands if d.media_kind == kind]
            sourced = [d for d in rows if d.media_connection_id in media]
            connections = [media[i] for i in {d.media_connection_id for d in sourced}]
            required = pl.media_required([(d.peak_demand, d.simultaneity_factor) for d in rows], reserve)
            contracted = sum(
                (c.contracted_capacity or Decimal("0") for c in connections if c.state in ("contracted", "connected")),
                Decimal("0"),
            )
            out.append(
                {
                    "media_kind": kind,
                    "stage_id": str(stage.id),
                    "capacity_unit": (connections[0].capacity_unit if connections else "")
                    or getattr(cat.entry("media_kinds", kind), "capacity_unit", ""),
                    "demand_count": len(rows),
                    "required": str(required),
                    "contracted": str(contracted),
                    "reserve_pct": str(reserve),
                    "short": pl.media_short(required, contracted),
                    "unsourced": [str(d.id) for d in rows if d.media_connection_id not in media],
                    "late": [str(c.id) for c in connections if pl.media_late(c.state, c.promised_on, start, today)],
                }
            )
        return out

    # ── balance read model ─────────────────────────────────────────────────

    async def balance(self, project_id: uuid.UUID, stage_id: Any = None, today: date | None = None) -> dict[str, Any]:
        """Area and media balance per stage (all stages, or one)."""
        cat = await self.catalogue(project_id)
        today = today or await self.site_today(project_id)
        tolerance = cat.resolved_thresholds().area_balance_tolerance_pct
        kinds = {k.code: k for k in cat.area_kinds}
        fallback = await self._site_total_fallback(project_id)
        stages = await self.stages(project_id)
        if stage_id is not None:
            stages = [await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")]
        out = []
        for stage in stages:
            facts = await self._facts(project_id, stage.id)
            bal = pl.area_balance(facts, kinds, tolerance, fallback)
            start, end = await self.stage_dates(stage)
            out.append(
                {
                    "stage": stage_out(stage, start, end),
                    "area": bal.as_dict(),
                    "tolerance_pct": str(tolerance),
                    "overlaps": [list(p) for p in pl.overlapping_pairs(facts)],
                    "gaps": pl.stage_gaps(f.area_kind for f in facts) if stage.state == "active" else [],
                    "exceeding": [
                        f.site_area_id for f in facts if pl.allocation_exceeds_area(f.allocated_m2, f.area_m2)
                    ],
                    "media": await self.media_balance(project_id, stage, cat, today),
                }
            )
        return {"items": out, "total": len(out), "offset": 0, "limit": len(out)}

    # ── concept (rules 11, 12) ─────────────────────────────────────────────

    async def put_concept(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> LogisticsConcept:
        row = await self._start(project_id)
        if "strategy" in data:
            flows = []
            codes: set[str] = set()
            stored = {str(f.get("flow_code")): f for f in (row.strategy or [])}
            for raw in data["strategy"] or []:
                code = str(raw.get("flow_code") or "").strip()
                if not code or code in codes:
                    raise LogisticsError("flow_code_invalid", 422, detail=code)
                codes.add(code)
                flow = merge_flow(stored.get(code), raw)
                mode = flow.get("mode") or "stock"
                if mode not in pl.FLOW_MODES:
                    raise LogisticsError("flow_mode_invalid", 422, detail=str(mode))
                await self._soft("area", flow.get("storage_area_id"), project_id)
                await self._soft("takt_schedule", flow.get("takt_schedule_id"), project_id)
                if mode == "just_in_time" and not flow.get("takt_schedule_id"):
                    raise LogisticsError("jit_without_takt", 422, detail=code)
                buffer_days = int(flow.get("buffer_days") or 0)
                if buffer_days < 0:
                    raise LogisticsError("buffer_days_negative", 422)
                flows.append(
                    {
                        "flow_code": code,
                        "description": str(flow.get("description") or ""),
                        "mode": mode,
                        "storage_area_id": _s(_uuid(flow.get("storage_area_id"))),
                        "takt_schedule_id": _s(_uuid(flow.get("takt_schedule_id"))),
                        "buffer_days": buffer_days,
                    }
                )
            row.strategy = flows
        for key in ("delivery_open", "delivery_close"):
            if key in data:
                value = data[key]
                if value is not None and pl.hhmm(value) is None:
                    raise LogisticsError("hours_invalid", 422)
                setattr(row, key, value)
        if row.delivery_open and row.delivery_close and pl.hhmm(row.delivery_close) <= pl.hhmm(row.delivery_open):  # type: ignore[operator]
            raise LogisticsError("hours_invalid", 422)
        if "site_timezone" in data:
            name = data["site_timezone"]
            if name is not None and pl.site_zone(name) is None:
                raise LogisticsError("timezone_invalid", 422, detail=str(name))
            row.site_timezone = name
        for key in ("max_deliveries_per_hour", "rules_text", "document_ref"):
            if key in data:
                value = data[key]
                setattr(row, key, "" if key == "rules_text" and value is None else value)
        row.saved_by = _uuid(actor_id)
        await self.session.flush()
        await self._audit(actor_id, "logistics_concept", row.id, "concept_saved", metadata={"flows": len(row.strategy)})
        return row

    async def assert_delivery_links(
        self,
        project_id: uuid.UUID,
        *,
        takt_location_id: Any = None,
        plant_item_id: Any = None,
        flow_code: str | None = None,
        current_plant_item_id: Any = None,
    ) -> None:
        """The soft links of a delivery booking belong to its project (rule 20) and its flow exists."""
        await self._soft("takt_location", takt_location_id, project_id)
        await self._port("plant_item", plant_item_id, project_id, current_plant_item_id)
        if flow_code is not None and flow_code not in await self.flow_codes(project_id):
            raise LogisticsError("flow_code_unknown", 422, detail=flow_code)

    async def flow_codes(self, project_id: uuid.UUID) -> set[str]:
        """The flow codes of the concept, what a delivery's ``flow_code`` may name."""
        concept = await self.concept(project_id)
        return {str(f.get("flow_code")) for f in (concept.strategy or [])} if concept is not None else set()

    async def takt_schedule_of(self, location_id: uuid.UUID) -> uuid.UUID | None:
        from app.modules.schedule_advanced.models import Location

        return (
            await self.session.execute(select(Location.takt_schedule_id).where(Location.id == location_id))
        ).scalar_one_or_none()

    async def takt_location_start(self, location_id: uuid.UUID) -> date | None:
        """Rule 11: the first day of work at a takt location, READ from ``schedule_advanced``.

        The line of balance is computed by that module's own pure function; the
        location's earliest bar start is offset from its master schedule start.
        """
        from app.modules.schedule_advanced.models import Location, MasterSchedule, TaktActivity, TaktSchedule
        from app.modules.schedule_advanced.service import compute_line_of_balance_geometry

        loc = await self.session.get(Location, location_id)
        if loc is None:
            return None
        takt = await self.session.get(TaktSchedule, loc.takt_schedule_id)
        master = await self.session.get(MasterSchedule, takt.master_schedule_id) if takt else None
        if takt is None or master is None or master.planned_start is None:
            return None
        locs = (await self.session.execute(select(Location).where(Location.takt_schedule_id == takt.id))).scalars()
        acts = (
            await self.session.execute(select(TaktActivity).where(TaktActivity.takt_schedule_id == takt.id))
        ).scalars()
        geometry = compute_line_of_balance_geometry(
            [{"id": str(x.id), "name": x.name, "sequence_order": x.sequence_order} for x in locs],
            [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "sequence_order": a.sequence_order,
                    "planned_cycle_duration_days": a.planned_cycle_duration_days,
                    "buffer_days_before": a.buffer_days_before,
                    "crew_size": a.crew_size,
                }
                for a in acts
            ],
        )
        starts = [b["start_day"] for b in geometry["bars"] if b["location_id"] == str(location_id)]
        if not starts:
            return None
        return master.planned_start + timedelta(days=min(starts))

    # ── transports (rules 5, 6, 13, 19) ────────────────────────────────────

    @staticmethod
    def _class_limits(cat: SiteLogisticsCatalogue) -> dict[str, dict[str, Any]]:
        return {c.code: pl.limits_from_class(c) for c in cat.load_classes}

    @staticmethod
    def _gate_limits(gate: Gate) -> dict[str, Any]:
        return {limit: getattr(gate, limit, None) for _v, limit in pl.LOAD_FIELDS}

    @staticmethod
    def _vehicle(t: Transport) -> dict[str, Any]:
        return {v: getattr(t, v) for v, _limit in pl.LOAD_FIELDS}

    async def gate_load(
        self,
        project_id: uuid.UUID,
        cat: SiteLogisticsCatalogue,
        tz: tzinfo | None,
        *,
        gate: Gate | None,
        vehicle: dict[str, Any],
        transport_id: uuid.UUID | None,
        start: datetime | None,
        end: datetime | None,
    ) -> dict[str, Any]:
        """Rule 5, the one place it is decided, for a transport and for a delivery booking alike.

        A load above the gate's limits is blocked unless a granted permit of the
        catalogue role ``gate_load`` (an oversize permit) covers the transport and
        this window: the authority approved exactly this movement, so the permit
        lifts the gate limit for it. A delivery reaches such a permit through its
        ``transport_id``. Without the site time zone the window cannot be tested
        against a permit, so nothing is lifted and ``needs_timezone`` says why.
        """
        exceeded = pl.exceeded_limits(vehicle, self._gate_limits(gate)) if gate is not None else []
        out: dict[str, Any] = {"exceeded": exceeded, "lifted_by": None, "blocked": False, "needs_timezone": False}
        if not exceeded:
            return out
        kinds = cat.permit_kinds_for("gate_load")
        permits = await self._permits_of(project_id, transport_id) if transport_id is not None else []
        granted = [p for p in permits if p["permit_kind"] in kinds and p["state"] == "granted"]
        if start is None or end is None:
            # No window, nothing a permit could cover.
            pass
        elif granted and tz is None:
            out["needs_timezone"] = True
        elif tz is not None:
            out["lifted_by"] = pl.covering_permit(granted, start, end, kinds, tz)
        out["blocked"] = out["lifted_by"] is None
        return out

    async def assert_gate_load(
        self,
        project_id: uuid.UUID,
        *,
        gate: Gate | None,
        vehicle: dict[str, Any],
        transport_id: uuid.UUID | None,
        start: datetime | None,
        end: datetime | None,
    ) -> None:
        """Refuse a load the gate cannot take. Every path that approves a delivery calls this."""
        cat = await self.catalogue(project_id)
        check = await self.gate_load(
            project_id,
            cat,
            await self.site_tz(project_id),
            gate=gate,
            vehicle=vehicle,
            transport_id=transport_id,
            start=_aware(start),
            end=_aware(end),
        )
        if check["blocked"]:
            violations = [{"code": "gate_load_exceeded", "fields": check["exceeded"]}]
            if check["needs_timezone"]:
                violations.append({"code": "site_timezone_missing"})
            raise LogisticsError("gate_load_exceeded", 422, violations=violations, detail=",".join(check["exceeded"]))

    async def transport_view(self, t: Transport, cat: SiteLogisticsCatalogue, tz: tzinfo | None) -> dict[str, Any]:
        """A transport with its derived ``is_heavy``, gate check and permit coverage."""
        gate = await self.session.get(Gate, t.gate_id) if t.gate_id else None
        kind = cat.entry("transport_kinds", t.transport_kind)
        heavy = pl.is_heavy(
            self._vehicle(t),
            self._class_limits(cat),
            chosen=t.load_class,
            always_heavy=bool(getattr(kind, "always_heavy", False)),
        )
        permits = await self._permits_of(t.project_id, t.id)
        start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
        load = await self.gate_load(
            t.project_id, cat, tz, gate=gate, vehicle=self._vehicle(t), transport_id=t.id, start=start, end=end
        )
        finding = None
        if heavy:
            kinds = cat.permit_kinds_for("heavy_transport")
            if not any(p["permit_kind"] in kinds and p["state"] == "granted" for p in permits):
                finding = "heavy_without_permit"
            elif start is None or end is None:
                finding = "window_outside_permit"
            elif tz is None:
                finding = "site_timezone_missing"
            else:
                finding = pl.heavy_permit_finding(permits, start, end, kinds, tz)
        lifted = load["lifted_by"]
        out = transport_out(t)
        out["is_heavy"] = heavy
        out["gate_exceeded"] = load["exceeded"]
        out["gate_blocked"] = load["blocked"]
        out["gate_needs_timezone"] = load["needs_timezone"]
        # The limit is exceeded and that is allowed: this permit covers the movement.
        out["gate_passed_by_permit"] = (
            None
            if lifted is None
            else {"id": str(lifted["id"]), "permit_kind": lifted["permit_kind"], "reference": lifted["reference"]}
        )
        out["permit_finding"] = finding
        out["permits"] = [
            {
                "id": str(p["id"]),
                "permit_kind": p["permit_kind"],
                "state": p["state"],
                "reference": p["reference"],
                "valid_to": _iso(p["valid_to"]),
            }
            for p in permits
        ]
        return out

    async def _permits_of(self, project_id: uuid.UUID, transport_id: uuid.UUID) -> list[dict[str, Any]]:
        linked = select(PermitTransportLink.permit_id).where(
            PermitTransportLink.project_id == project_id, PermitTransportLink.transport_id == transport_id
        )
        rows = (
            await self.session.execute(
                select(TransportPermit)
                .where(
                    TransportPermit.project_id == project_id,
                    (TransportPermit.transport_id == transport_id) | TransportPermit.id.in_(linked),
                )
                .order_by(TransportPermit.created_at, TransportPermit.id)
            )
        ).scalars()
        return [permit_facts(p) for p in rows]

    async def _transport_checks(
        self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any], row: Transport | None = None
    ) -> None:
        if "transport_kind" in data:
            self._need(cat, "transport_kinds", data["transport_kind"], "unknown_transport_kind")
        if data.get("direction") is not None and data["direction"] not in pl_directions():
            raise LogisticsError("direction_invalid", 422)
        if data.get("load_class") is not None:
            self._need(cat, "load_classes", data["load_class"], "unknown_load_class")
        self._route_check(data)
        await self._soft("gate", data.get("gate_id"), project_id)
        await self._soft("po", data.get("po_id"), project_id)
        await self._soft("customs_case", data.get("customs_case_id"), project_id)
        await self._port("plant_item", data.get("plant_item_id"), project_id, row.plant_item_id if row else None)
        for key in ("planned_window_start", "planned_window_end"):
            if data.get(key) is not None:
                data[key] = _aware(data[key])

    async def create_transport(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> Transport:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        data = dict(data)
        self._need(cat, "transport_kinds", data.get("transport_kind"), "unknown_transport_kind")
        await self._transport_checks(project_id, cat, data)
        row = Transport(project_id=project_id, state="planned", direction="inbound")
        self._apply(row, data, _TRANSPORT_FIELDS)
        self._window_order(row)
        self.session.add(row)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_transport", row.id, "transport_created", metadata={"kind": row.transport_kind}
        )
        return row

    async def update_transport(
        self, project_id: uuid.UUID, transport_id: Any, data: dict[str, Any], actor_id: Any
    ) -> Transport:
        cat = await self.catalogue(project_id)
        row = await self._get(Transport, project_id, transport_id, "transport_not_found", lock=True)
        locked = self._transport_frozen(row)
        data = dict(data)
        await self._transport_checks(project_id, cat, data, row)
        frozen = sorted(k for k in locked if k in data and not _same(getattr(row, k), data[k]))
        if frozen:
            raise conflict("transport_under_way", detail=",".join(frozen))
        changed = self._apply(row, data, _TRANSPORT_FIELDS)
        self._window_order(row)
        if row.state == "scheduled" and changed:
            # A scheduled transport keeps its slot only while it still satisfies the rules.
            await self.session.flush()
            await self._assert_schedulable(project_id, cat, row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_transport", row.id, "transport_updated", metadata=changed)
        return row

    @staticmethod
    def _window_order(row: Transport) -> None:
        if row.planned_window_start and row.planned_window_end and row.planned_window_end <= row.planned_window_start:
            raise LogisticsError("window_invalid", 422)

    async def delete_transport(self, project_id: uuid.UUID, transport_id: Any, actor_id: Any) -> None:
        row = await self._get(Transport, project_id, transport_id, "transport_not_found", lock=True)
        self._guard_transport_delete(row)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_transport", row.id, "transport_deleted")

    async def _assert_schedulable(
        self,
        project_id: uuid.UUID,
        cat: SiteLogisticsCatalogue,
        t: Transport,
        *,
        view: dict[str, Any] | None = None,
        quiet: Any = _UNSET,
    ) -> None:
        """Rules 5, 6 and 13 at the moment a transport takes its slot.

        ``view`` and ``quiet`` are the transport's view and the neighbourhood plan
        when the caller has just read them; they are read here otherwise.
        """
        tz = await self.site_tz(project_id)
        if view is None:
            view = await self.transport_view(t, cat, tz)
        codes: list[str] = []
        violations: list[dict[str, Any]] = []

        def add(code: str, **extra: Any) -> None:
            if code not in codes:
                codes.append(code)
                violations.append({"code": code, **extra})

        if view["gate_blocked"]:
            add("gate_load_exceeded", fields=view["gate_exceeded"])
            if view["gate_needs_timezone"]:
                add("site_timezone_missing")
        if view["permit_finding"]:
            add(view["permit_finding"])
        start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
        plan = await self.neighbourhood(project_id) if quiet is _UNSET else quiet
        if plan is not None and plan.quiet_hours and start and end:
            if tz is None:
                add("site_timezone_missing")
            elif pl.quiet_hours_conflict(plan.quiet_hours, start, end, tz):
                permits = await self._permits_of(project_id, t.id)
                if pl.covering_permit(permits, start, end, cat.permit_kinds_for("quiet_hours"), tz) is None:
                    add("quiet_hours_conflict")
        if violations:
            raise LogisticsError(violations[0]["code"], 422, violations=violations)

    async def transition_transport(
        self, project_id: uuid.UUID, transport_id: Any, target: str, actor_id: Any
    ) -> Transport:
        cat = await self.catalogue(project_id)
        row = await self._get(Transport, project_id, transport_id, "transport_not_found", lock=True)
        received = await self._guard_transport_transition(project_id, cat, row, target)
        today = await self.site_today(project_id)
        if target == "in_transit":
            row.in_transit_on = today
        if target == "arrived":
            row.arrived_on = received if received is not None else today
        before = self._move(pl.TRANSPORT_FSM, row, target)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_transport", row.id, "transport_transition", from_status=before, to_status=target
        )
        self._publish(
            ev.TRANSPORT_STATE_CHANGED,
            {"project_id": project_id, "transport_id": row.id, "from": before, "to": target},
        )
        return row

    async def _goods_receipt_date(self, po_id: uuid.UUID, since: date | None) -> date | None:
        """The first confirmed receipt of the order dated on or after the transport left.

        A receipt from before ``since`` belongs to an earlier shipment of the same
        order, so it is never this transport's arrival. A transport with no
        departure date has none to compare with and reads no receipt.
        """
        from app.modules.procurement.models import GoodsReceipt

        if since is None:
            return None
        rows = (
            await self.session.execute(
                select(GoodsReceipt.receipt_date).where(GoodsReceipt.po_id == po_id, GoodsReceipt.status == "confirmed")
            )
        ).scalars()
        days = [d for d in (_parse_day(r) for r in rows) if d is not None and d >= since]
        return min(days) if days else None

    async def sync_arrivals(self, project_id: uuid.UUID, actor_id: Any = None) -> int:
        """Rule 19 the other way round: in-transit PO transports whose goods receipt is confirmed arrive."""
        moved = 0
        ids = [
            t.id
            for t in await self._list(Transport, project_id, state="in_transit", direction="inbound")
            if t.po_id is not None
        ]
        for tid in ids:
            t = await self._get(Transport, project_id, tid, "transport_not_found", lock=True)
            if t.state != "in_transit" or t.po_id is None:
                continue
            received = await self._goods_receipt_date(t.po_id, t.in_transit_on)
            if received is None:
                continue
            t.arrived_on = received
            before = self._move(pl.TRANSPORT_FSM, t, "arrived")
            moved += 1
            await self._audit(
                actor_id,
                "logistics_transport",
                t.id,
                "transport_arrived_from_receipt",
                from_status=before,
                to_status="arrived",
            )
            self._publish(
                ev.TRANSPORT_STATE_CHANGED,
                {"project_id": project_id, "transport_id": t.id, "from": before, "to": "arrived"},
            )
        await self.session.flush()
        return moved

    # ── transport permits (rules 6, 7) ─────────────────────────────────────

    async def _permit_checks(
        self,
        project_id: uuid.UUID,
        cat: SiteLogisticsCatalogue,
        data: dict[str, Any],
        row: TransportPermit | None = None,
    ) -> None:
        if "permit_kind" in data:
            self._need(cat, "permit_kinds", data["permit_kind"], "unknown_permit_kind")
        self._route_check(data)
        await self._soft("transport", data.get("transport_id"), project_id)
        await self._port(
            "authority_permit", data.get("authority_permit_id"), project_id, row.authority_permit_id if row else None
        )
        if "allowed_windows" in data:
            self._require(data, "allowed_windows")
            data["allowed_windows"] = _windows(data["allowed_windows"])

    @staticmethod
    def _validity_order(row: TransportPermit) -> None:
        """Checked on the row, so a PATCH of one date is compared with the stored other one."""
        if row.valid_from and row.valid_to and row.valid_to < row.valid_from:
            raise LogisticsError("validity_invalid", 422)

    async def create_permit(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> TransportPermit:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        data = dict(data)
        self._need(cat, "permit_kinds", data.get("permit_kind"), "unknown_permit_kind")
        await self._permit_checks(project_id, cat, data)
        row = TransportPermit(project_id=project_id, state="draft", allowed_windows=[])
        self._apply(row, data, _PERMIT_FIELDS)
        self._validity_order(row)
        self.session.add(row)
        await self.session.flush()
        await self._set_links(project_id, row, data.get("covers_transport_ids"))
        await self._audit(actor_id, "logistics_permit", row.id, "permit_created", metadata={"kind": row.permit_kind})
        return row

    async def update_permit(
        self, project_id: uuid.UUID, permit_id: Any, data: dict[str, Any], actor_id: Any
    ) -> TransportPermit:
        """Edit a permit. Its validity, windows, kind and links are frozen once it left draft or applied.

        A granted permit is what the authority signed: it is what lets a heavy
        transport be scheduled and lifts a gate limit, so nobody extends or
        re-points it afterwards. Sending the stored value again is not a change.
        """
        cat = await self.catalogue(project_id)
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found", lock=True)
        data = dict(data)
        await self._permit_checks(project_id, cat, data, row)
        if self._permit_frozen(row):
            frozen = [k for k in _PERMIT_FROZEN_FIELDS if k in data and not _same(getattr(row, k), data[k])]
            if "covers_transport_ids" in data:
                wanted = {str(_uuid(x)) for x in (data["covers_transport_ids"] or [])}
                if wanted != set(await self.permit_links(project_id, row.id)):
                    frozen.append("covers_transport_ids")
            if frozen:
                raise conflict("permit_frozen", detail=",".join(sorted(frozen)))
        changed = self._apply(row, data, _PERMIT_FIELDS)
        self._validity_order(row)
        if row.state in _PERMIT_OPEN_STATES and "covers_transport_ids" in data:
            await self._set_links(project_id, row, data["covers_transport_ids"])
        await self.session.flush()
        await self._audit(actor_id, "logistics_permit", row.id, "permit_updated", metadata=changed)
        return row

    async def _set_links(self, project_id: uuid.UUID, permit: TransportPermit, ids: Any) -> None:
        if ids is None:
            return
        wanted = []
        for raw in ids:
            t = await self._get(Transport, project_id, raw, "transport_not_found")
            if t.id not in wanted:
                wanted.append(t.id)
        await self.session.execute(
            delete(PermitTransportLink).where(
                PermitTransportLink.project_id == project_id, PermitTransportLink.permit_id == permit.id
            )
        )
        self.session.add_all(
            PermitTransportLink(project_id=project_id, permit_id=permit.id, transport_id=tid) for tid in wanted
        )
        await self.session.flush()

    async def permit_links(self, project_id: uuid.UUID, permit_id: uuid.UUID) -> list[str]:
        rows = await self._list(PermitTransportLink, project_id, permit_id=permit_id)
        return [str(r.transport_id) for r in rows]

    async def transition_permit(
        self, project_id: uuid.UUID, permit_id: Any, target: str, actor_id: Any
    ) -> TransportPermit:
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found", lock=True)
        self._guard_permit_transition(row, target)
        if target == "applied" and row.applied_on is None:
            row.applied_on = await self.site_today(project_id)
        before = self._move(pl.PERMIT_FSM, row, target)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_permit", row.id, "permit_transition", from_status=before, to_status=target
        )
        return row

    async def delete_permit(self, project_id: uuid.UUID, permit_id: Any, actor_id: Any) -> None:
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found", lock=True)
        self._guard_permit_delete(row)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_permit", row.id, "permit_deleted")

    async def _open_transports_of(self, project_id: uuid.UUID, permit: TransportPermit) -> list[Transport]:
        ids = set(await self.permit_links(project_id, permit.id))
        if permit.transport_id:
            ids.add(str(permit.transport_id))
        out = []
        for tid in sorted(ids):
            t = await self.session.get(Transport, uuid.UUID(tid))
            if t is not None and t.project_id == project_id and t.state not in ("arrived", "closed", "cancelled"):
                out.append(t)
        return out

    async def sweep_permit(self, project_id: uuid.UUID, permit_id: Any, actor_id: Any = None) -> str | None:
        """Rule 7 for one granted permit on the server's site date: ``expired``, ``expiring`` or ``None``.

        The date is never a caller's: expiry is terminal, so a client-chosen
        "today" could expire every permit of a project.
        """
        p = await self._get(TransportPermit, project_id, permit_id, "permit_not_found", lock=True)
        if p.state != "granted":
            return None
        cat = await self.catalogue(project_id)
        today = await self.site_today(project_id)
        status = pl.permit_expiry(p.valid_to, today, cat.resolved_thresholds().permit_warn_days)
        remaining = await self._open_transports_of(project_id, p)
        ctx = {"project_id": project_id, "permit_id": p.id, "reference": p.reference, "valid_to": p.valid_to}
        if status == "expired":
            p.state = "expired"
            await self.session.flush()
            await self._audit(actor_id, "logistics_permit", p.id, "permit_expired", to_status="expired")
            self._publish(ev.PERMIT_EXPIRED, {**ctx, "transports": [t.id for t in remaining]})
            await self._notify(await self._area_owner(project_id), "permit_expired", "logistics_permit", p.id, ctx)
            return "expired"
        if status == "expiring" and remaining and p.expiry_notified_on is None:
            p.expiry_notified_on = today
            await self.session.flush()
            self._publish(ev.PERMIT_EXPIRING, ctx)
            await self._notify(await self._area_owner(project_id), "permit_expiring", "logistics_permit", p.id, ctx)
            return "expiring"
        return None

    async def sweep_permits(self, project_id: uuid.UUID, actor_id: Any = None) -> dict[str, int]:
        """Rule 7 over every granted permit of the project."""
        counts = {"expired": 0, "expiring": 0}
        for pid in [p.id for p in await self._list(TransportPermit, project_id, state="granted")]:
            outcome = await self.sweep_permit(project_id, pid, actor_id)
            if outcome is not None:
                counts[outcome] += 1
        return counts

    # ── customs (rules 14 to 17) ───────────────────────────────────────────

    async def _customs_checks(self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any]) -> None:
        if "incoterm" in data:
            code = str(data["incoterm"] or "").upper()
            data["incoterm"] = code
            if code not in cat.codes("incoterms"):
                raise LogisticsError("incoterm_unknown", 422, detail=code)
        if data.get("direction") is not None and data["direction"] not in ("import", "export"):
            raise LogisticsError("direction_invalid", 422)
        if data.get("transport_mode") is not None and data["transport_mode"] not in pl_modes():
            raise LogisticsError("transport_mode_invalid", 422)
        if data.get("declarant_party") is not None and data["declarant_party"] not in ("buyer", "seller"):
            raise LogisticsError("declarant_invalid", 422)
        for key in ("country_of_origin", "country_of_destination"):
            if data.get(key) is not None:
                data[key] = _country(data[key])
        if data.get("currency") is not None:
            data["currency"] = _currency(data["currency"])
        if data.get("customs_value") is not None:
            data["customs_value"] = _money(data["customs_value"])
        await self._soft("po", data.get("po_id"), project_id)

    @staticmethod
    def _amount_has_currency(amount: Any, currency: Any) -> None:
        """Rule 17: an amount never travels without its currency."""
        if amount is not None and not currency:
            raise LogisticsError("currency_required", 422)

    async def create_customs(
        self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsCase:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        data = dict(data)
        if not can_see_values:
            data = {k: v for k, v in data.items() if k not in _CUSTOMS_VALUE_FIELDS}
        if not data.get("incoterm"):
            raise LogisticsError("incoterm_unknown", 422)
        await self._customs_checks(project_id, cat, data)
        row = CustomsCase(project_id=project_id, state="open", incoterm_version=cat.incoterm_version)
        self._apply(row, data, _CUSTOMS_FIELDS)
        self._amount_has_currency(row.customs_value, row.currency)
        self.session.add(row)
        await self.session.flush()
        await self.refresh_documents(project_id, row, cat)
        await self._audit(actor_id, "logistics_customs", row.id, "customs_created", metadata={"incoterm": row.incoterm})
        return row

    async def update_customs(
        self, project_id: uuid.UUID, case_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsCase:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found", lock=True)
        locked = self._customs_frozen(row)
        data = dict(data)
        if not can_see_values:
            data = {k: v for k, v in data.items() if k not in _CUSTOMS_VALUE_FIELDS}
        await self._customs_checks(project_id, cat, data)
        # Declared: the checklist it was declared on no longer changes under it.
        frozen = sorted(k for k in locked if k in data and not _same(getattr(row, k), data[k]))
        if frozen:
            raise conflict("customs_declared", detail=",".join(frozen))
        changed = self._apply(row, data, _CUSTOMS_FIELDS)
        self._amount_has_currency(row.customs_value, row.currency)
        if "incoterm" in changed:
            # The case is now under the pinned catalogue's revision of the rules.
            row.incoterm_version = cat.incoterm_version
        await self.session.flush()
        if row.state in _CUSTOMS_OPEN_STATES:
            await self.refresh_documents(project_id, row, cat)
            await self._reopen_if_incomplete(project_id, row, actor_id)
        await self._audit(
            actor_id,
            "logistics_customs",
            row.id,
            "customs_updated",
            metadata={k: v for k, v in changed.items() if k not in _CUSTOMS_VALUE_FIELDS},
        )
        return row

    async def delete_customs(self, project_id: uuid.UUID, case_id: Any, actor_id: Any) -> None:
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found", lock=True)
        self._guard_customs_delete(row)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_customs", row.id, "customs_deleted")

    def incoterm_of(self, cat: SiteLogisticsCatalogue, case: CustomsCase) -> Any:
        """The incoterm of a case under the revision of the rules it was opened with (Decision 6).

        The pinned catalogue answers when it carries that revision. After a re-pin
        to a catalogue of another revision the case keeps its own: it is read from
        the shipped catalogue of the case's revision. ``None`` only when no
        catalogue knows that revision and code.
        """
        if case.incoterm_version == cat.incoterm_version:
            return cat.entry("incoterms", case.incoterm)
        for other in shipped_catalogues().values():
            if other.incoterm_version == case.incoterm_version:
                hit = other.entry("incoterms", case.incoterm)
                if hit is not None:
                    return hit
        return None

    async def _open_case(self, project_id: uuid.UUID, case_id: Any, *, also: tuple[str, ...] = ()) -> CustomsCase:
        """The case, locked, for a change to its lines or documents; 409 once it is declared."""
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found", lock=True)
        self._guard_case_open(case, also)
        return case

    async def _reopen_if_incomplete(self, project_id: uuid.UUID, case: CustomsCase, actor_id: Any) -> None:
        """A case marked complete that lost a required document or its last line is open again."""
        if case.state != "documents_complete":
            return
        docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)]
        lines = await self._list(CustomsLine, project_id, customs_case_id=case.id)
        if pl.missing_required(docs) or not lines:
            case.state = "open"
            await self.session.flush()
            await self._audit(
                actor_id,
                "logistics_customs",
                case.id,
                "customs_reopened",
                from_status="documents_complete",
                to_status="open",
            )

    async def refresh_documents(self, project_id: uuid.UUID, case: CustomsCase, cat: SiteLogisticsCatalogue) -> None:
        """Rule 15: the checklist follows direction, incoterm, mode and preferential lines.

        The template is the catalogue's ``document_rules``. Required documents are
        added as ``missing``; a document no longer required stays on the list (with
        what was received) but turns optional. Two requests that add the same
        document race on ``uq_oe_site_cdoc_case_kind``; the loser keeps the winner's.
        """
        lines = await self._list(CustomsLine, project_id, customs_case_id=case.id)
        incoterm = self.incoterm_of(cat, case)
        required = set(
            pl.required_documents(
                case.direction,
                incoterm,
                cat.document_rules,
                case.transport_mode,
                any(x.preferential_origin for x in lines),
            )
        )
        docs = {d.kind: d for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)}
        for kind, doc in docs.items():
            doc.required = kind in required
        await self.session.flush()
        for kind in sorted(required - set(docs)):
            try:
                async with self.session.begin_nested():
                    self.session.add(
                        CustomsDocument(
                            project_id=project_id, customs_case_id=case.id, kind=kind, required=True, state="missing"
                        )
                    )
                    await self.session.flush()
            except IntegrityError:
                logger.debug("site_logistics: document %s of case %s already on the checklist", kind, case.id)

    async def lines(self, project_id: uuid.UUID, case_id: Any) -> list[CustomsLine]:
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        return await self._list(CustomsLine, project_id, CustomsLine.sort_order, customs_case_id=case.id)

    async def create_line(
        self, project_id: uuid.UUID, case_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsLine:
        cat = await self.catalogue(project_id)
        case = await self._open_case(project_id, case_id)
        self._require(data, "hs_code")
        data = await self._line_checks(project_id, cat, data, can_see_values)
        row = CustomsLine(project_id=project_id, customs_case_id=case.id)
        self._apply(row, data, _LINE_FIELDS)
        self._line_currency(row, case)
        self.session.add(row)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._reopen_if_incomplete(project_id, case, actor_id)
        await self._audit(actor_id, "logistics_customs", case.id, "line_created", metadata={"hs_code": row.hs_code})
        return row

    async def update_line(
        self, project_id: uuid.UUID, line_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsLine:
        cat = await self.catalogue(project_id)
        found = await self._get(CustomsLine, project_id, line_id, "line_not_found")
        case = await self._open_case(project_id, found.customs_case_id)
        row = await self._get(CustomsLine, project_id, line_id, "line_not_found", lock=True)
        data = await self._line_checks(project_id, cat, data, can_see_values)
        changed = self._apply(row, data, _LINE_FIELDS)
        self._line_currency(row, case)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._reopen_if_incomplete(project_id, case, actor_id)
        await self._audit(
            actor_id,
            "logistics_customs",
            case.id,
            "line_updated",
            metadata={k: v for k, v in changed.items() if k not in ("value", "currency")},
        )
        return row

    async def delete_line(self, project_id: uuid.UUID, line_id: Any, actor_id: Any) -> None:
        cat = await self.catalogue(project_id)
        found = await self._get(CustomsLine, project_id, line_id, "line_not_found")
        case = await self._open_case(project_id, found.customs_case_id)
        row = await self._get(CustomsLine, project_id, line_id, "line_not_found", lock=True)
        await self.session.delete(row)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._reopen_if_incomplete(project_id, case, actor_id)
        await self._audit(actor_id, "logistics_customs", case.id, "line_deleted")

    def _line_currency(self, row: CustomsLine, case: CustomsCase) -> None:
        """A line value is in the line's own currency, else in the case's; with neither it is refused."""
        if row.value is None:
            return
        if not row.currency:
            row.currency = case.currency
        self._amount_has_currency(row.value, row.currency)

    async def _line_checks(
        self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any], can_see_values: bool
    ) -> dict[str, Any]:
        data = dict(data)
        if not can_see_values:
            data.pop("value", None)
            data.pop("currency", None)
        if "hs_code" in data:
            code = str(data["hs_code"] or "").replace(".", "").replace(" ", "")
            if not pl.hs_code_valid(code, cat.resolved_thresholds().customs_hs_digits_min):
                raise LogisticsError("hs_code_invalid", 422, detail=code)
            data["hs_code"] = code
        await self._master("commodity_code", data.get("commodity_code_id"))
        if data.get("origin_country") is not None:
            data["origin_country"] = _country(data["origin_country"])
        if data.get("currency") is not None:
            data["currency"] = _currency(data["currency"])
        if data.get("value") is not None:
            data["value"] = _money(data["value"])
        return data

    async def documents(self, project_id: uuid.UUID, case_id: Any) -> list[CustomsDocument]:
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        return await self._list(CustomsDocument, project_id, CustomsDocument.kind, customs_case_id=case.id)

    async def update_document(
        self, project_id: uuid.UUID, document_id: Any, data: dict[str, Any], actor_id: Any
    ) -> CustomsDocument:
        found = await self._get(CustomsDocument, project_id, document_id, "document_not_found")
        # A held case may still receive what customs asked for; a declared one changes nothing.
        case = await self._open_case(project_id, found.customs_case_id, also=("held",))
        row = await self._get(CustomsDocument, project_id, document_id, "document_not_found", lock=True)
        if "document_ref" in data:
            row.document_ref = data["document_ref"]
        if data.get("state") and data["state"] != row.state:
            self._guard_document_move(case, row, data["state"])
            row.state = data["state"]
        if row.state in ("received", "verified") and not row.document_ref:
            raise LogisticsError("document_ref_required", 422)
        await self.session.flush()
        await self._reopen_if_incomplete(project_id, case, actor_id)
        await self._audit(
            actor_id,
            "logistics_customs",
            row.customs_case_id,
            "document_updated",
            metadata={"kind": row.kind, "state": row.state},
        )
        return row

    async def add_document(self, project_id: uuid.UUID, case_id: Any, kind: str, actor_id: Any) -> CustomsDocument:
        """Add an optional document (an ATA carnet, a dual-use licence) to a case's checklist."""
        cat = await self.catalogue(project_id)
        case = await self._open_case(project_id, case_id, also=("held",))
        self._need(cat, "customs_document_kinds", kind, "unknown_document_kind")
        if any(d.kind == kind for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)):
            raise conflict("document_exists")
        row = CustomsDocument(
            project_id=project_id, customs_case_id=case.id, kind=kind, required=False, state="missing"
        )
        await self._insert(row, "document_exists")
        await self._audit(actor_id, "logistics_customs", case.id, "document_added", metadata={"kind": kind})
        return row

    async def transition_customs(self, project_id: uuid.UUID, case_id: Any, target: str, actor_id: Any) -> CustomsCase:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found", lock=True)
        await self._guard_customs_transition(project_id, cat, row, target)
        if target == "cleared":
            row.cleared_on = row.cleared_on or await self.site_today(project_id)
        before = self._move(pl.CUSTOMS_FSM, row, target)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_customs", row.id, "customs_transition", from_status=before, to_status=target
        )
        if target in ("cleared", "held"):
            name = ev.CUSTOMS_CLEARED if target == "cleared" else ev.CUSTOMS_HELD
            self._publish(name, {"project_id": project_id, "customs_case_id": row.id})
        return row

    # ── neighbourhood (rules 13, 18) ───────────────────────────────────────

    async def neighbourhood(self, project_id: uuid.UUID) -> NeighbourhoodPlan | None:
        """The neighbourhood plan, ``None`` until it is first saved. Reads never create it."""
        return (
            await self.session.execute(select(NeighbourhoodPlan).where(NeighbourhoodPlan.project_id == project_id))
        ).scalar_one_or_none()

    async def neighbourhood_view(self, project_id: uuid.UUID) -> dict[str, Any]:
        """The plan as the API shows it; a project without one reads the defaults and ``id`` null."""
        row = await self.neighbourhood(project_id)
        if row is not None:
            return neighbourhood_out(row)
        return {
            "id": None,
            "zone_type": "mixed",
            "noise_limit_source": "",
            "day_dba": None,
            "night_dba": None,
            "quiet_hours": [],
            "site_traffic_routes": None,
            "parking_note": "",
            "municipality_contact": "",
            "correspondence_thread_id": None,
        }

    async def _ensure_neighbourhood(self, project_id: uuid.UUID) -> NeighbourhoodPlan:
        row = await self.neighbourhood(project_id)
        if row is not None:
            return row
        try:
            async with self.session.begin_nested():
                row = NeighbourhoodPlan(project_id=project_id, quiet_hours=[])
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            row = await self.neighbourhood(project_id)
            if row is None:
                raise
        return row

    async def put_neighbourhood(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> NeighbourhoodPlan:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        row = await self._ensure_neighbourhood(project_id)
        data = dict(data)
        if data.get("zone_type") is not None and data["zone_type"] not in ("residential", "mixed", "industrial"):
            raise LogisticsError("zone_type_invalid", 422)
        source = data.get("noise_limit_source")
        if source and source != "project":
            limit = cat.entry("noise_limits", source)
            if limit is None:
                raise LogisticsError("unknown_noise_limit", 422, detail=source)
            if limit.project_value_required:
                raise LogisticsError("noise_limit_needs_project_value", 422, detail=source)
            # The catalogue entry is the one number: its values are copied as the source says.
            data.setdefault("day_dba", limit.day_dba)
            data.setdefault("night_dba", limit.night_dba)
            if limit.quiet_hours and not data.get("quiet_hours"):
                data["quiet_hours"] = list(limit.quiet_hours)
        if "quiet_hours" in data and data["quiet_hours"] is None:
            data["quiet_hours"] = []
        if data.get("quiet_hours"):
            q = list(data["quiet_hours"])
            if len(q) != 2 or pl.hhmm(q[0]) is None or pl.hhmm(q[1]) is None:
                raise LogisticsError("hours_invalid", 422)
        await self._soft("correspondence_thread", data.get("correspondence_thread_id"), project_id)
        changed = self._apply(row, data, _NEIGHBOURHOOD_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_neighbourhood", row.id, "neighbourhood_saved", metadata=changed)
        return row

    async def create_complaint(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> NeighbourIssue:
        await self._start(project_id)
        cat = await self.catalogue(project_id)
        self._need(cat, "neighbour_issue_kinds", data.get("kind"), "unknown_issue_kind")
        await self._soft("transport", data.get("transport_id"), project_id)
        await self._soft("delivery", data.get("delivery_id"), project_id)
        await self._assert_owner(project_id, data.get("owner_user_id"))
        row = NeighbourIssue(project_id=project_id, state="received")
        self._apply(row, data, _COMPLAINT_FIELDS)
        if row.owner_user_id is None:
            row.owner_user_id = await self._area_owner(project_id)
        if row.reported_on is None:
            row.reported_on = await self.site_today(project_id)
        if row.response_due is None:
            row.response_due = row.reported_on + timedelta(days=cat.resolved_thresholds().neighbour_response_days)
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_complaint", row.id, "complaint_received", metadata={"kind": row.kind})
        return row

    async def update_complaint(
        self, project_id: uuid.UUID, complaint_id: Any, data: dict[str, Any], actor_id: Any
    ) -> NeighbourIssue:
        row = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found", lock=True)
        self._guard_complaint_edit(row)
        if "kind" in data:
            self._need(await self.catalogue(project_id), "neighbour_issue_kinds", data["kind"], "unknown_issue_kind")
        await self._soft("transport", data.get("transport_id"), project_id)
        await self._soft("delivery", data.get("delivery_id"), project_id)
        await self._assert_owner(project_id, data.get("owner_user_id"))
        changed = self._apply(row, data, _COMPLAINT_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_complaint", row.id, "complaint_updated", metadata=changed)
        return row

    async def transition_complaint(
        self, project_id: uuid.UUID, complaint_id: Any, target: str, actor_id: Any
    ) -> NeighbourIssue:
        row = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found", lock=True)
        self._guard_complaint_transition(row, target)
        before = self._move(pl.COMPLAINT_FSM, row, target)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_complaint", row.id, "complaint_transition", from_status=before, to_status=target
        )
        return row

    async def _assert_owner(self, project_id: uuid.UUID, owner_user_id: Any) -> None:
        """An owner has to be someone who can open the project, or the issue is unanswerable."""
        from fastapi import HTTPException

        from app.dependencies import verify_project_access

        uid = _uuid(owner_user_id)
        if uid is None:
            return
        try:
            await verify_project_access(project_id, str(uid), self.session)
        except HTTPException as exc:
            raise LogisticsError("owner_not_member", 422) from exc

    async def delete_complaint(self, project_id: uuid.UUID, complaint_id: Any, actor_id: Any) -> None:
        row = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_complaint", row.id, "complaint_deleted")

    async def sweep_complaint(self, project_id: uuid.UUID, complaint_id: Any, actor_id: Any = None) -> bool:
        """Rule 18 for one complaint on the server's site date: notify its owner once when it is overdue."""
        c = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found", lock=True)
        today = await self.site_today(project_id)
        if not pl.complaint_overdue(c.state, c.response_due, today) or c.overdue_notified_on is not None:
            return False
        c.overdue_notified_on = today
        await self.session.flush()
        ctx = {"project_id": project_id, "complaint_id": c.id, "kind": c.kind, "due": c.response_due}
        self._publish(ev.NEIGHBOUR_ISSUE_OVERDUE, ctx)
        await self._notify(
            c.owner_user_id or await self._area_owner(project_id),
            "neighbour_issue_overdue",
            "logistics_complaint",
            c.id,
            ctx,
        )
        return True

    async def sweep_complaints(self, project_id: uuid.UUID, actor_id: Any = None) -> int:
        """Rule 18 over every complaint still waiting for its acknowledgement."""
        count = 0
        for cid in [c.id for c in await self._list(NeighbourIssue, project_id, state="received")]:
            if await self.sweep_complaint(project_id, cid, actor_id):
                count += 1
        return count

    async def create_coordination(
        self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any
    ) -> CoordinationEntry:
        await self._start(project_id)
        await self._soft("correspondence", data.get("correspondence_id"), project_id)
        row = CoordinationEntry(project_id=project_id)
        self._apply(row, data, _COORD_FIELDS)
        if row.entry_date is None:
            row.entry_date = await self.site_today(project_id)
        self.session.add(row)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_coordination", row.id, "coordination_logged", metadata={"body": row.body}
        )
        return row

    async def update_coordination(
        self, project_id: uuid.UUID, entry_id: Any, data: dict[str, Any], actor_id: Any
    ) -> CoordinationEntry:
        row = await self._get(CoordinationEntry, project_id, entry_id, "entry_not_found")
        await self._soft("correspondence", data.get("correspondence_id"), project_id)
        changed = self._apply(row, data, _COORD_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_coordination", row.id, "coordination_updated", metadata=changed)
        return row

    async def delete_coordination(self, project_id: uuid.UUID, entry_id: Any, actor_id: Any) -> None:
        row = await self._get(CoordinationEntry, project_id, entry_id, "entry_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_coordination", row.id, "coordination_deleted")

    # ── findings, readiness, frame summary ─────────────────────────────────

    async def _flow_of(
        self, d: DeliveryBooking, flows: dict[str, dict[str, Any]], cache: dict[uuid.UUID, uuid.UUID | None]
    ) -> dict[str, Any] | None:
        """The material flow a delivery belongs to (rule 11).

        Its own ``flow_code`` when it names one. Otherwise a delivery to a takt
        location belongs to the just-in-time flow of that location's takt schedule
        (the one with the tightest buffer when several share it). ``None`` when
        neither says anything.
        """
        if d.flow_code and d.flow_code in flows:
            return flows[d.flow_code]
        if d.takt_location_id is None:
            return None
        if d.takt_location_id not in cache:
            cache[d.takt_location_id] = await self.takt_schedule_of(d.takt_location_id)
        takt = cache[d.takt_location_id]
        mine = [
            f
            for f in flows.values()
            if f.get("mode") == "just_in_time" and takt is not None and f.get("takt_schedule_id") == str(takt)
        ]
        return min(mine, key=lambda f: (int(f.get("buffer_days") or 0), str(f.get("flow_code")))) if mine else None

    async def delivery_rate_violation(
        self, project_id: uuid.UUID, start: datetime, *, exclude_id: uuid.UUID | None = None
    ) -> dict[str, Any] | None:
        """Rule 12: would one more approved delivery starting at ``start`` exceed the concept's hourly limit?"""
        concept = await self.concept(project_id)
        limit = concept.max_deliveries_per_hour if concept is not None else None
        if not limit:
            return None
        tz = pl.site_zone(concept.site_timezone)  # type: ignore[union-attr]
        if tz is None:
            return {"code": "site_timezone_missing"}
        approved = [
            _aware(d.window_start)
            for d in await self._list(DeliveryBooking, project_id, status="approved")
            if d.id != exclude_id and d.window_start is not None
        ]
        counts = pl.starts_per_hour([*approved, _aware(start)], tz)  # type: ignore[list-item]
        hour = pl.local(_aware(start), tz).replace(minute=0, second=0, microsecond=0)  # type: ignore[arg-type]
        if counts[hour] > limit:
            return {"code": "delivery_rate_exceeded", "hour": hour.isoformat(), "count": counts[hour], "limit": limit}
        return None

    async def findings(self, project_id: uuid.UUID, today: date | None = None) -> list[dict[str, Any]]:
        """Every rule finding of the plan, the input of the rule set and of gate readiness.

        Time-of-day, weekday and site-date rules run on the site clock. While the
        site has no time zone they are not evaluated at all and the plan carries
        one ``site_timezone_missing`` error instead. The opening hours of a gate
        are the exception: unchecked hours are one ``gate_hours_unchecked``
        warning, because deliveries were booked before a site could state a zone.
        """
        tz = await self.site_tz(project_id)
        today = today or self._today(tz)
        cat = await self.catalogue(project_id)
        th = cat.resolved_thresholds()
        out: list[dict[str, Any]] = []
        needs_tz = False
        hours_unchecked = False
        balance = await self.balance(project_id, today=today)
        for item in balance["items"]:
            stage = item["stage"]
            area = item["area"]
            if not area["closed"]:
                out.append(
                    _finding(
                        "area_balance_closed",
                        "area_balance_not_closed",
                        "warning",
                        stage["id"],
                        stage=stage["code"],
                        difference_m2=area["difference_m2"],
                    )
                )
            for a_id in item["exceeding"]:
                out.append(
                    _finding("allocation_within_area", "allocation_exceeds_area", "error", a_id, stage=stage["code"])
                )
            for a, b in item["overlaps"]:
                out.append(_finding("area_overlap", "area_overlap", "warning", a, other=b, stage=stage["code"]))
            for gap in item["gaps"]:
                rule = "stage_has_storage" if gap == "stage_without_storage" else "stage_has_site_setup"
                out.append(_finding(rule, gap, "error", stage["id"], stage=stage["code"]))
            for m in item["media"]:
                if m["short"]:
                    out.append(
                        _finding(
                            "media_capacity_sufficient",
                            "media_capacity_short",
                            "error",
                            stage["id"],
                            stage=stage["code"],
                            media=m["media_kind"],
                            required=m["required"],
                            contracted=m["contracted"],
                        )
                    )
                for d_id in m["unsourced"]:
                    out.append(_finding("media_sourced", "media_unsourced", "warning", d_id, media=m["media_kind"]))
                for c_id in m["late"]:
                    out.append(
                        _finding(
                            "media_on_time", "media_late", "error", c_id, stage=stage["code"], media=m["media_kind"]
                        )
                    )
        for zone in await self._list(LaydownZone, project_id):
            if zone.site_area_id is None:
                out.append(_finding("zone_mapped", "zone_not_mapped", "warning", zone.id, zone=zone.name))
        gates = await self._list(Gate, project_id)
        for gate in gates:
            if pl.limits_unknown(self._gate_limits(gate)):
                out.append(_finding("gate_limits_known", "gate_limits_unknown", "warning", gate.id, gate=gate.name))
        gate_by_id = {g.id: g for g in gates}
        plan = await self.neighbourhood(project_id)
        quiet = (plan.quiet_hours or []) if plan is not None else []
        concept = await self.concept(project_id)
        flows = {str(f.get("flow_code")): f for f in ((concept.strategy or []) if concept is not None else [])}
        night_kinds = cat.permit_kinds_for("quiet_hours")
        concept_hours = None
        if concept is not None and concept.delivery_open and concept.delivery_close:
            concept_hours = (concept.delivery_open, concept.delivery_close)
        takt_of: dict[uuid.UUID, uuid.UUID | None] = {}
        deliveries = await self._list(DeliveryBooking, project_id, DeliveryBooking.window_start)
        for d in deliveries:
            if d.status not in ("requested", "approved"):
                continue
            gate = gate_by_id.get(d.gate_id) if d.gate_id else None
            start, end = _aware(d.window_start), _aware(d.window_end)
            if tz is None and gate is not None:
                # Gate hours are a site clock rule (see validators.delivery_within_gate_hours).
                o, c = pl.narrower_hours((gate.open_time, gate.close_time), concept_hours)
                hours_unchecked = hours_unchecked or (pl.hhmm(o) is not None and pl.hhmm(c) is not None)
            load = await self.gate_load(
                project_id,
                cat,
                tz,
                gate=gate,
                vehicle={"gross_weight_t": d.gross_weight_t},
                transport_id=d.transport_id,
                start=start,
                end=end,
            )
            needs_tz = needs_tz or load["needs_timezone"]
            if load["blocked"]:
                out.append(_finding("gate_load_respected", "gate_load_exceeded", "error", d.id, title=d.supplier_name))
            if d.status == "approved" and quiet and start and end:
                if tz is None:
                    needs_tz = True
                elif pl.quiet_hours_conflict(quiet, start, end, tz):
                    # Rule 13: the night-work permit of the delivery's transport covers it.
                    permits = await self._permits_of(project_id, d.transport_id) if d.transport_id else []
                    if pl.covering_permit(permits, start, end, night_kinds, tz) is None:
                        out.append(
                            _finding(
                                "quiet_hours_respected", "quiet_hours_conflict", "error", d.id, title=d.supplier_name
                            )
                        )
            flow = await self._flow_of(d, flows, takt_of)
            if flow is not None and flow.get("mode") == "just_in_time":
                if d.takt_location_id is None:
                    out.append(
                        _finding(
                            "jit_aligned_to_takt",
                            "jit_without_location",
                            "error",
                            d.id,
                            title=d.supplier_name,
                            flow=flow.get("flow_code"),
                        )
                    )
                elif start is not None and tz is None:
                    needs_tz = True
                elif start is not None:
                    code = pl.jit_finding(
                        pl.local(start, tz).date(),  # type: ignore[arg-type]
                        await self.takt_location_start(d.takt_location_id),
                        int(flow.get("buffer_days") or 0),
                    )
                    if code:
                        out.append(
                            _finding(
                                "jit_aligned_to_takt",
                                code,
                                "warning" if code == "jit_too_early" else "error",
                                d.id,
                                title=d.supplier_name,
                                flow=flow.get("flow_code"),
                            )
                        )
        limit = concept.max_deliveries_per_hour if concept is not None else None
        approved_starts = [_aware(d.window_start) for d in deliveries if d.status == "approved" and d.window_start]
        if limit and approved_starts:
            if tz is None:
                needs_tz = True
            else:
                for hour, count in sorted(pl.starts_per_hour(approved_starts, tz).items()):  # type: ignore[arg-type]
                    if count > limit:
                        out.append(
                            _finding(
                                "delivery_rate_respected",
                                "delivery_rate_exceeded",
                                "error",
                                None,
                                hour=hour.isoformat(),
                                count=count,
                                limit=limit,
                            )
                        )
        for t in await self._list(Transport, project_id, Transport.created_at):
            if t.state in ("closed", "cancelled"):
                continue
            view = await self.transport_view(t, cat, tz)
            needs_tz = needs_tz or view["gate_needs_timezone"]
            if view["gate_blocked"]:
                out.append(_finding("gate_load_respected", "gate_load_exceeded", "error", t.id, title=t.title))
            if view["permit_finding"] and t.state in ("scheduled", *_ONWARD):
                if view["permit_finding"] == "site_timezone_missing":
                    needs_tz = True
                else:
                    out.append(
                        _finding("heavy_transport_permitted", view["permit_finding"], "error", t.id, title=t.title)
                    )
            start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
            if t.state == "scheduled" and quiet and start and end:
                if tz is None:
                    needs_tz = True
                elif pl.quiet_hours_conflict(quiet, start, end, tz):
                    permits = await self._permits_of(project_id, t.id)
                    if pl.covering_permit(permits, start, end, night_kinds, tz) is None:
                        out.append(
                            _finding("quiet_hours_respected", "quiet_hours_conflict", "error", t.id, title=t.title)
                        )
        for p in await self._list(TransportPermit, project_id, TransportPermit.created_at):
            status = pl.permit_expiry(p.valid_to, today, th.permit_warn_days)
            if p.state == "granted" and status != "ok" and await self._open_transports_of(project_id, p):
                sev = "error" if status == "expired" else "warning"
                out.append(_finding("permit_not_expiring", f"permit_{status}", sev, p.id, reference=p.reference))
        for case in await self._list(CustomsCase, project_id, CustomsCase.created_at):
            incoterm = self.incoterm_of(cat, case)
            if incoterm is None:
                out.append(_finding("incoterm_known", "incoterm_unknown", "error", case.id, incoterm=case.incoterm))
            elif pl.sea_only_mismatch(incoterm, case.transport_mode):
                out.append(_finding("incoterm_known", "incoterm_sea_only", "warning", case.id, incoterm=case.incoterm))
            if not pl.declarant_matches(case.direction, incoterm, case.declarant_party):
                out.append(_finding("declarant_matches_incoterm", "declarant_mismatch_incoterm", "warning", case.id))
            for line in await self._list(CustomsLine, project_id, customs_case_id=case.id):
                if not pl.hs_code_valid(line.hs_code, th.customs_hs_digits_min):
                    out.append(_finding("hs_code_valid", "hs_code_invalid", "error", line.id, hs_code=line.hs_code))
            if case.state in _CUSTOMS_OPEN_STATES:
                docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)]
                for kind in pl.missing_required(docs):
                    out.append(
                        _finding(
                            "customs_documents_complete", "required_document_missing", "warning", case.id, kind=kind
                        )
                    )
        for c in await self._list(NeighbourIssue, project_id, NeighbourIssue.created_at):
            if pl.complaint_overdue(c.state, c.response_due, today):
                out.append(
                    _finding("neighbour_issue_on_time", "neighbour_issue_overdue", "error", c.id, due=c.response_due)
                )
        if hours_unchecked:
            # Deliveries were booked on this site before it had a zone and keep being booked:
            # the opening hours are simply not compared, and the plan says so.
            out.insert(0, _finding("gate_hours_checked", "gate_hours_unchecked", "warning", None))
        if needs_tz:
            out.insert(0, _finding("site_timezone_set", "site_timezone_missing", "error", None))
        return out

    async def validation_payload(self, project_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
        """What the ``site_logistics`` rule set reads (see ``validators.py``).

        ``findings`` feeds the plan rules. ``deliveries``, ``gates``,
        ``concept_hours`` and ``site_timezone`` feed the delivery rules, so the
        gate-hours rule reads the concept's narrower hours on the site clock.
        """
        concept = await self.concept(project_id)
        hours = None
        if concept is not None and concept.delivery_open and concept.delivery_close:
            hours = [concept.delivery_open, concept.delivery_close]
        gates = await self._list(Gate, project_id)
        deliveries = await self._list(DeliveryBooking, project_id, DeliveryBooking.window_start)
        return {
            "findings": await self.findings(project_id, today),
            "site_timezone": concept.site_timezone if concept is not None else None,
            "concept_hours": hours,
            "gates": {str(g.id): {"name": g.name, "open_time": g.open_time, "close_time": g.close_time} for g in gates},
            "deliveries": [
                {
                    "id": str(d.id),
                    "gate_id": _s(d.gate_id),
                    "supplier_name": d.supplier_name,
                    "status": d.status,
                    "window_start": _iso(_aware(d.window_start)),
                    "window_end": _iso(_aware(d.window_end)),
                }
                for d in deliveries
            ],
        }

    async def validate(self, project_id: uuid.UUID, *, locale: str = "en", actor_id: Any = None) -> dict[str, Any]:
        """Run the ``site_logistics`` rule set over the plan and return the report as the API shows it."""
        from app.core.validation.engine import validation_engine

        payload = await self.validation_payload(project_id)
        report = await validation_engine.validate(
            data=payload,
            rule_sets=[MODULE],
            target_type="site_logistics_plan",
            target_id=str(project_id),
            project_id=str(project_id),
            metadata={"locale": locale, "user_id": _s(actor_id)},
        )
        return {
            "project_id": str(project_id),
            "status": report.status.value,
            "score": report.score,
            "rules_run": sorted({r.rule_id for r in report.results}),
            "counts": {
                "passed": len(report.passed_rules),
                "errors": len(report.errors),
                "warnings": len(report.warnings),
            },
            "results": [
                {
                    "rule_id": r.rule_id,
                    "rule_name": r.rule_name,
                    "severity": r.severity.value,
                    "passed": r.passed,
                    "message": r.message,
                    "element_ref": r.element_ref,
                    "suggestion": r.suggestion,
                }
                for r in report.results
            ],
        }

    async def readiness(self, project_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
        """Readiness of the plan for the gate into construction (SPEC section 7).

        The area and the gates it is evidence for are resolved from the governance
        catalogue's tags now and reported with it; nothing here names one.
        """
        target = await self.governance_target(project_id)
        tz = await self.site_tz(project_id)
        today = today or self._today(tz)
        cat = await self.catalogue(project_id)
        findings = await self.findings(project_id, today)
        errors = [f for f in findings if f["severity"] == "error"]
        items: list[dict[str, Any]] = [_item("no_errors", not errors, ",".join(sorted({f["code"] for f in errors})))]
        balance = await self.balance(project_id, today=today)
        open_stages = [b for b in balance["items"] if b["stage"]["state"] != "closed"]
        unbalanced = [b["stage"]["code"] for b in open_stages if not b["area"]["closed"]]
        items.append(
            _item("balance_closed", bool(open_stages) and not unbalanced, ",".join(unbalanced) or _none(open_stages))
        )
        # The first stage is the first one still to be built: a closed stage needs no media any more.
        first = open_stages[0] if open_stages else None
        first_short = []
        if first is not None:
            media = {m.id: m for m in await self._list(MediaConnection, project_id)}
            for d in await self._list(MediaDemand, project_id, stage_id=uuid.UUID(first["stage"]["id"])):
                conn = media.get(d.media_connection_id)
                if conn is None or conn.state not in ("contracted", "connected"):
                    first_short.append(d.media_kind)
        items.append(_item("first_stage_media_contracted", not first_short, ",".join(sorted(set(first_short)))))
        concept = await self.concept(project_id)
        saved = bool(concept and (concept.strategy or concept.rules_text.strip()))
        if not saved:
            items.append(_item("concept_saved_and_exported", False, "concept_empty"))
        elif target.frame_doc_type is None:
            # No frame document in this governance model: nothing can prove the export.
            items.append({"code": "concept_saved_and_exported", "state": "unknown", "detail": "no_frame_document"})
        else:
            exported = await hosting.frame_document_bound(self.session, project_id, target.frame_doc_type)
            if exported is None:
                # The model names the document, this project has no row for it yet.
                items.append({"code": "concept_saved_and_exported", "state": "unknown", "detail": "no_frame_document"})
            else:
                items.append(_item("concept_saved_and_exported", exported, "" if exported else "not_exported"))
        heavy_kinds = cat.permit_kinds_for("heavy_transport")
        # A heavy transport is ready for the gate with a granted permit only. An applied one
        # is in progress and a missing one is not started; the detail says which.
        waiting: dict[str, list[str]] = {"permit_applied": [], "permit_missing": []}
        blocked = []
        passed_by_permit = []
        for t in await self._list(Transport, project_id, Transport.created_at):
            if t.state in ("cancelled", "closed"):
                continue
            view = await self.transport_view(t, cat, tz)
            name = t.title or str(t.id)
            if view["is_heavy"]:
                standing = pl.heavy_permit_standing(view["permits"], heavy_kinds)
                if standing != "granted":
                    waiting[f"permit_{standing}"].append(name)
            if view["gate_blocked"]:
                blocked.append(name)
            elif view["gate_passed_by_permit"] is not None:
                passed_by_permit.append({"transport_id": str(t.id), "title": name, **view["gate_passed_by_permit"]})
        items.append(
            _item(
                "heavy_transports_permitted",
                not any(waiting.values()),
                "; ".join(f"{reason}: {','.join(names)}" for reason, names in waiting.items() if names),
            )
        )
        # Met while no load is refused by its gate; a load above the limit that an
        # oversize permit covers passes, and the detail names the permit it passes on.
        items.append(
            _item(
                "gate_loads_admitted",
                not blocked,
                ",".join(blocked)
                or ",".join(f"{x['title']}: {x['permit_kind']} {x['reference']}".strip() for x in passed_by_permit),
            )
        )
        plan = await self.neighbourhood(project_id)
        items.append(_item("neighbourhood_limit_source", bool(plan and plan.noise_limit_source), ""))
        return {
            "area": target.area_code,
            "gates": list(target.gate_codes),
            "frame_doc_type": target.frame_doc_type,
            # Why the plan cannot be placed in the governance model, else null.
            "governance": target.reason,
            "ready": all(i["state"] == "met" for i in items),
            "items": items,
            "passed_by_permit": passed_by_permit,
            "findings": findings,
        }

    async def frame_summary(
        self, project_id: uuid.UUID, today: date | None = None, *, can_see_values: bool = False
    ) -> dict[str, Any]:
        """The content of the governance frame document for logistics as one read model."""
        tz = await self.site_tz(project_id)
        today = today or self._today(tz)
        cat = await self.catalogue(project_id)
        concept = await self.concept_view(project_id)
        readiness = await self.readiness(project_id, today)
        transports = [
            await self.transport_view(t, cat, tz) for t in await self._list(Transport, project_id, Transport.created_at)
        ]
        return {
            "project_id": str(project_id),
            "as_of": today.isoformat(),
            "doc_type": readiness["frame_doc_type"],
            "catalogue": {
                "source": concept["catalogue_source"],
                "id": concept["catalogue_id"],
                "version": concept["catalogue_version"],
                "jurisdiction": cat.jurisdiction,
            },
            "balance": (await self.balance(project_id, today=today))["items"],
            "concept": concept,
            "transports": transports,
            "permits": [
                permit_out(p) for p in await self._list(TransportPermit, project_id, TransportPermit.created_at)
            ],
            "customs": [
                customs_out(c, can_see_values)
                for c in await self._list(CustomsCase, project_id, CustomsCase.created_at)
            ],
            "neighbourhood": await self.neighbourhood_view(project_id),
            "readiness": readiness,
        }


# ── helpers ────────────────────────────────────────────────────────────────


def pl_directions() -> tuple[str, ...]:
    return ("inbound", "outbound")


def pl_modes() -> tuple[str, ...]:
    from app.modules.site_logistics.catalogue import TRANSPORT_MODES

    return TRANSPORT_MODES


def _item(code: str, met: bool, detail: str) -> dict[str, Any]:
    return {"code": code, "state": "met" if met else "not_met", "detail": detail}


def _none(rows: Sequence[Any]) -> str:
    return "" if rows else "no_open_stage"


def _same(current: Any, new: Any) -> bool:
    """True when ``new`` (as a request sends it) is the value already stored."""
    if current is None or new is None:
        return current is None and new is None
    if isinstance(current, uuid.UUID):
        return current == _uuid(new)
    if isinstance(current, datetime):
        return isinstance(new, datetime) and _aware(current) == _aware(new)
    if isinstance(current, Decimal):
        try:
            return current == Decimal(str(new))
        except ArithmeticError:
            return False
    return bool(current == new)


def _country(value: Any) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        raise LogisticsError("country_invalid", 422, detail=code)
    return code


def _currency(value: Any) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise LogisticsError("currency_invalid", 422, detail=code)
    return code


def _money(value: Any) -> Decimal:
    """Rule 17: money is Decimal, never float."""
    if isinstance(value, float):
        raise LogisticsError("money_not_decimal", 422)
    try:
        amount = Decimal(str(value))
    except Exception as exc:
        raise LogisticsError("money_not_decimal", 422) from exc
    if not amount.is_finite() or amount < 0:
        raise LogisticsError("money_not_decimal", 422)
    if amount != amount.quantize(Decimal("0.01")) or amount >= Decimal("1e16"):
        # What MoneyType(18, 2) stores exactly; nothing is rounded on the way in.
        raise LogisticsError("money_out_of_range", 422)
    return amount


def _windows(raw: Any) -> list[dict[str, Any]]:
    out = []
    for w in raw or []:
        days = [int(d) for d in (w.get("weekdays") or [])]
        if any(d < 0 or d > 6 for d in days) or pl.hhmm(w.get("from")) is None or pl.hhmm(w.get("to")) is None:
            raise LogisticsError("window_invalid", 422)
        out.append({"weekdays": sorted(set(days)), "from": w["from"], "to": w["to"]})
    return out


def permit_facts(p: TransportPermit) -> dict[str, Any]:
    return {
        "id": p.id,
        "permit_kind": p.permit_kind,
        "reference": p.reference,
        "state": p.state,
        "valid_from": p.valid_from,
        "valid_to": p.valid_to,
        "allowed_windows": p.allowed_windows or [],
    }


def stage_out(s: ExpansionStage, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "code": s.code,
        "title": s.title,
        "ordinal": s.ordinal,
        "state": s.state,
        "from_activity_id": _s(s.from_activity_id),
        "to_activity_id": _s(s.to_activity_id),
        "from_date": _iso(s.from_date),
        "to_date": _iso(s.to_date),
        "start": _iso(start if start is not None else s.from_date),
        "end": _iso(end if end is not None else s.to_date),
        "plan_document_id": _s(s.plan_document_id),
        "plan_metres_per_pixel": _dec(s.plan_metres_per_pixel),
        "plan_origin_px": s.plan_origin_px,
    }


def area_out(a: SiteArea) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "code": a.code,
        "name": a.name,
        "area_kind": a.area_kind,
        "geometry": a.geometry,
        "frame": a.frame,
        "area_m2": _dec(a.area_m2),
        "area_m2_declared": _dec(a.area_m2_declared),
        "effective_m2": _dec(a.effective_m2),
        "geo_overlay_id": _s(a.geo_overlay_id),
        "takt_location_id": _s(a.takt_location_id),
        "owner_party": a.owner_party,
    }


def allocation_out(a: AreaAllocation) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "site_area_id": str(a.site_area_id),
        "stage_id": str(a.stage_id),
        "area_kind": a.area_kind,
        "allocated_m2": _dec(a.allocated_m2),
        "use_note": a.use_note,
    }


def media_out(m: MediaConnection) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "media_kind": m.media_kind,
        "phase": m.phase,
        "provider_name": m.provider_name,
        "provider_vendor_id": _s(m.provider_vendor_id),
        "connection_point": m.connection_point,
        "connection_point_geometry": m.connection_point_geometry,
        "capacity_unit": m.capacity_unit,
        "available_capacity": _dec(m.available_capacity),
        "contracted_capacity": _dec(m.contracted_capacity),
        "application_ref": m.application_ref,
        "applied_on": _iso(m.applied_on),
        "promised_on": _iso(m.promised_on),
        "connected_on": _iso(m.connected_on),
        "document_ref": m.document_ref,
        "state": m.state,
    }


def demand_out(d: MediaDemand) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "media_connection_id": _s(d.media_connection_id),
        "media_kind": d.media_kind,
        "stage_id": str(d.stage_id),
        "consumer": d.consumer,
        "site_plant_position_id": _s(d.site_plant_position_id),
        "plant_item_id": _s(d.plant_item_id),
        "peak_demand": _dec(d.peak_demand),
        "simultaneity_factor": _dec(d.simultaneity_factor),
        "from_plant_position": d.site_plant_position_id is not None,
    }


def concept_out(c: LogisticsConcept) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "catalogue_source": c.catalogue_source,
        "catalogue_id": c.catalogue_id,
        "catalogue_version": c.catalogue_version,
        "strategy": c.strategy or [],
        "delivery_open": c.delivery_open,
        "delivery_close": c.delivery_close,
        "max_deliveries_per_hour": c.max_deliveries_per_hour,
        "rules_text": c.rules_text,
        "document_ref": c.document_ref,
        "site_timezone": c.site_timezone,
        "updated_at": _iso(getattr(c, "updated_at", None)),
    }


def transport_out(t: Transport) -> dict[str, Any]:
    out = {
        "id": str(t.id),
        "direction": t.direction,
        "transport_kind": t.transport_kind,
        "title": t.title,
        "carrier_name": t.carrier_name,
        "origin": t.origin,
        "destination": t.destination,
        "gate_id": _s(t.gate_id),
        "planned_window_start": _iso(t.planned_window_start),
        "planned_window_end": _iso(t.planned_window_end),
        "po_id": _s(t.po_id),
        "plant_item_id": _s(t.plant_item_id),
        "waste_record_ref": t.waste_record_ref,
        "customs_case_id": _s(t.customs_case_id),
        "route_geojson": t.route_geojson,
        "route_notes": t.route_notes,
        "escort_required": t.escort_required,
        "load_class": t.load_class,
        "state": t.state,
        "in_transit_on": _iso(t.in_transit_on),
        "arrived_on": _iso(t.arrived_on),
    }
    for v, _limit in pl.LOAD_FIELDS:
        out[v] = _dec(getattr(t, v))
    return out


def permit_out(p: TransportPermit, covers: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "transport_id": _s(p.transport_id),
        "covers_transport_ids": covers or [],
        "permit_kind": p.permit_kind,
        "authority": p.authority,
        "reference": p.reference,
        "applied_on": _iso(p.applied_on),
        "valid_from": _iso(p.valid_from),
        "valid_to": _iso(p.valid_to),
        "allowed_windows": p.allowed_windows or [],
        "conditions": p.conditions,
        "route_geojson": p.route_geojson,
        "document_ref": p.document_ref,
        "authority_permit_id": _s(p.authority_permit_id),
        "state": p.state,
    }


def customs_out(c: CustomsCase, can_see_values: bool) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "direction": c.direction,
        "title": c.title,
        "incoterm": c.incoterm,
        "incoterm_version": c.incoterm_version,
        "named_place": c.named_place,
        "transport_mode": c.transport_mode,
        "country_of_origin": c.country_of_origin,
        "country_of_destination": c.country_of_destination,
        "declarant_party": c.declarant_party,
        "broker_name": c.broker_name,
        # Decision 12: commercial values only with ``site_logistics.customs``.
        "customs_value": _dec(c.customs_value) if can_see_values else None,
        "currency": c.currency if can_see_values else None,
        "values_hidden": not can_see_values,
        "declaration_ref": c.declaration_ref,
        "cleared_on": _iso(c.cleared_on),
        "po_id": _s(c.po_id),
        "state": c.state,
    }


def line_out(x: CustomsLine, can_see_values: bool) -> dict[str, Any]:
    return {
        "id": str(x.id),
        "customs_case_id": str(x.customs_case_id),
        "description": x.description,
        "hs_code": x.hs_code,
        "commodity_code_id": _s(x.commodity_code_id),
        "quantity": _dec(x.quantity),
        "unit": x.unit,
        "net_mass_kg": _dec(x.net_mass_kg),
        "value": _dec(x.value) if can_see_values else None,
        "currency": x.currency if can_see_values else None,
        "origin_country": x.origin_country,
        "preferential_origin": x.preferential_origin,
        "sort_order": x.sort_order,
    }


def document_out(d: CustomsDocument) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "customs_case_id": str(d.customs_case_id),
        "kind": d.kind,
        "required": d.required,
        "document_ref": d.document_ref,
        "state": d.state,
    }


def neighbourhood_out(n: NeighbourhoodPlan) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "zone_type": n.zone_type,
        "noise_limit_source": n.noise_limit_source,
        "day_dba": _dec(n.day_dba),
        "night_dba": _dec(n.night_dba),
        "quiet_hours": n.quiet_hours or [],
        "site_traffic_routes": n.site_traffic_routes,
        "parking_note": n.parking_note,
        "municipality_contact": n.municipality_contact,
        "correspondence_thread_id": _s(n.correspondence_thread_id),
    }


def complaint_out(c: NeighbourIssue, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    return {
        "id": str(c.id),
        "kind": c.kind,
        "reported_on": _iso(c.reported_on),
        "reporter": c.reporter,
        "location": c.location,
        "description": c.description,
        "transport_id": _s(c.transport_id),
        "delivery_id": _s(c.delivery_id),
        "response": c.response,
        "response_due": _iso(c.response_due),
        "owner_user_id": _s(c.owner_user_id),
        "state": c.state,
        "overdue": pl.complaint_overdue(c.state, c.response_due, today),
        "created_at": _iso(c.created_at),
    }


def coordination_out(e: CoordinationEntry) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "entry_date": _iso(e.entry_date),
        "body": e.body,
        "topic": e.topic,
        "outcome": e.outcome,
        "next_action_due": _iso(e.next_action_due),
        "correspondence_id": _s(e.correspondence_id),
    }
