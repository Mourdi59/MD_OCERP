# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Logistics plan service (framework module 6): areas, media, transports, customs, neighbourhood.

Every method takes the ``project_id`` the router verified with
``verify_project_access`` and looks every child row up by ``(project_id, id)``,
so an id of another project answers 404 exactly like a missing one (rule 20).
Soft links into other modules (schedule activity, takt schedule and location,
purchase order, geo overlay, correspondence) are checked against the project
too before they are stored.

The rules live in :mod:`app.modules.site_logistics.planning`; this layer loads
the rows, calls them, writes, audits (``log_activity``) and publishes after
commit. The service flushes; the request's session dependency commits.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.modules.site_logistics import events as ev
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
from app.modules.site_logistics.geometry import GeometryError, polygon_area_m2, validate_polygon
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
AREA_CODE = "m06_logistics"
FRAME_DOC = "m06_logistics_frame"
READINESS_GATE = "development_to_execution"
_HEAVY_PERMIT_KINDS = ("oversize_permit", "escort_notification")
_ONWARD = ("in_transit", "arrived", "closed")


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
_STAGE_FIELDS = ("code", "title", "ordinal", "from_activity_id", "to_activity_id", "from_date", "to_date")
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

    async def _area_owner(self, project_id: uuid.UUID) -> uuid.UUID | None:
        """The owner of governance area ``m06_logistics``, the addressee of logistics notifications."""
        try:
            from app.modules.project_governance.models import GovernanceArea

            return (
                await self.session.execute(
                    select(GovernanceArea.owner_user_id).where(
                        GovernanceArea.project_id == project_id, GovernanceArea.code == AREA_CODE
                    )
                )
            ).scalar_one_or_none()
        except Exception:
            return None

    async def _get(self, model: Any, project_id: uuid.UUID, row_id: Any, code: str = "not_found") -> Any:
        rid = _uuid(row_id)
        if rid is None:
            raise not_found(code)
        row = (
            await self.session.execute(select(model).where(model.id == rid, model.project_id == project_id))
        ).scalar_one_or_none()
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
        changed: dict[str, Any] = {}
        for key in allowed:
            if key not in data:
                continue
            value = data[key]
            if key in _JSON_FIELDS and value is not None:
                value = pl.json_safe(value)
            if key.endswith("_id") and value is not None:
                value = _uuid(value)
            setattr(row, key, value)
            changed[key] = value
        return changed

    async def _soft(self, kind: str, value: Any, project_id: uuid.UUID) -> None:
        """404 unless a soft link names a row of this project (rule 20)."""
        rid = _uuid(value)
        if rid is None:
            return
        owner = await self._owner_of(kind, rid)
        if owner != project_id:
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

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    # ── catalogue and concept (the pin) ────────────────────────────────────

    async def concept(self, project_id: uuid.UUID, *, create: bool = True) -> LogisticsConcept | None:
        """The project's concept row; created with the country's default catalogue pin on first use."""
        row = (
            await self.session.execute(select(LogisticsConcept).where(LogisticsConcept.project_id == project_id))
        ).scalar_one_or_none()
        if row is None and create:
            project = await self._project(project_id)
            cid = default_catalogue_id(getattr(project, "country_code", None))
            row = LogisticsConcept(
                project_id=project_id,
                catalogue_source="shipped",
                catalogue_id=cid,
                catalogue_version=shipped_catalogues()[cid].version,
                strategy=[],
            )
            self.session.add(row)
            await self.session.flush()
        return row

    async def catalogue(self, project_id: uuid.UUID) -> SiteLogisticsCatalogue:
        """The pinned catalogue with its ``extends`` chain resolved."""
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        concept = await self.concept(project_id)
        assert concept is not None
        try:
            obj = await resolve_catalogue(
                self.session,
                concept.catalogue_source,
                concept.catalogue_id,
                concept.catalogue_version,
                kind=SITE_LOGISTICS_KIND,
            )
        except GovernanceError as exc:
            raise LogisticsError(exc.code, exc.status_code) from exc
        shipped = shipped_catalogues()
        try:
            return merged(obj, shipped.__getitem__)
        except (KeyError, ValueError) as exc:
            raise LogisticsError("catalogue_invalid", 422, detail=str(exc)) from exc

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
        """Re-pin the project's catalogue (shipped or a tenant's published version)."""
        from app.modules.project_governance.catalogue_store import CatalogueStore
        from app.modules.project_governance.errors import GovernanceError

        concept = await self.concept(project_id)
        assert concept is not None
        try:
            pinned = await CatalogueStore(self.session).assert_pinnable(
                tenant_id, source, catalogue_id, version, kind=SITE_LOGISTICS_KIND
            )
        except GovernanceError as exc:
            raise LogisticsError(exc.code, exc.status_code) from exc
        before = f"{concept.catalogue_source}:{concept.catalogue_id}@{concept.catalogue_version}"
        concept.catalogue_source, concept.catalogue_id, concept.catalogue_version = source, catalogue_id, pinned
        await self.catalogue(project_id)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_concept", concept.id, "catalogue_pinned", metadata={"before": before, "after": pinned}
        )
        return concept

    def _need(self, cat: SiteLogisticsCatalogue, group: str, code: Any, error: str) -> None:
        if code is None or code not in cat.codes(group):
            raise LogisticsError(error, 422, detail=str(code))

    # ── stages ─────────────────────────────────────────────────────────────

    async def stages(self, project_id: uuid.UUID) -> list[ExpansionStage]:
        """Every stage in order; ``stage_0`` is created on first use."""
        rows = await self._list(ExpansionStage, project_id, ExpansionStage.ordinal, ExpansionStage.code)
        if not rows:
            row = ExpansionStage(project_id=project_id, code="stage_0", title="", ordinal=0, state="planned")
            self.session.add(row)
            await self.session.flush()
            rows = [row]
        return rows

    async def create_stage(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> ExpansionStage:
        await self.stages(project_id)
        row = ExpansionStage(project_id=project_id, state="planned", title="", ordinal=0)
        await self._stage_links(project_id, data)
        self._apply(row, data, _STAGE_FIELDS)
        await self._unique_code(ExpansionStage, project_id, row.code, None)
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, "stage_created", metadata={"code": row.code})
        return row

    async def update_stage(
        self, project_id: uuid.UUID, stage_id: Any, data: dict[str, Any], actor_id: Any
    ) -> ExpansionStage:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")
        await self._stage_links(project_id, data)
        if "code" in data:
            await self._unique_code(ExpansionStage, project_id, data["code"], row.id)
        changed = self._apply(row, data, _STAGE_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, "stage_updated", metadata=changed)
        return row

    async def transition_stage(self, project_id: uuid.UUID, stage_id: Any, target: str, actor_id: Any) -> Any:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")
        self._move(pl.STAGE_FSM, row, target)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, f"stage_{target}", to_status=target)
        return row

    async def delete_stage(self, project_id: uuid.UUID, stage_id: Any, actor_id: Any) -> None:
        row = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")
        if len(await self._list(ExpansionStage, project_id)) <= 1:
            raise conflict("last_stage")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_stage", row.id, "stage_deleted")

    async def _stage_links(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        for key in ("from_activity_id", "to_activity_id"):
            await self._soft("activity", data.get(key), project_id)

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

    def _move(self, fsm: dict[str, tuple[str, ...]], row: Any, target: str) -> str:
        current = row.state
        if not pl.can_move(fsm, current, target):
            raise conflict("invalid_transition", detail=f"{current}->{target}")
        row.state = target
        return current

    # ── areas and allocations (rules 1 to 4) ───────────────────────────────

    async def create_area(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> SiteArea:
        cat = await self.catalogue(project_id)
        row = SiteArea(project_id=project_id, frame="local", name="", owner_party="")
        await self._area_checks(project_id, cat, data)
        self._apply(row, data, _AREA_FIELDS)
        await self._unique_code(SiteArea, project_id, row.code, None)
        self._compute_area(row)
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_area", row.id, "area_created", metadata={"code": row.code})
        return row

    async def update_area(self, project_id: uuid.UUID, area_id: Any, data: dict[str, Any], actor_id: Any) -> SiteArea:
        cat = await self.catalogue(project_id)
        row = await self._get(SiteArea, project_id, area_id, "area_not_found")
        await self._area_checks(project_id, cat, data)
        if "code" in data:
            await self._unique_code(SiteArea, project_id, data["code"], row.id)
        changed = self._apply(row, data, _AREA_FIELDS)
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
        row = await self._get(SiteArea, project_id, area_id, "area_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_area", row.id, "area_deleted")
        self._publish(ev.AREA_BALANCE_CHANGED, {"project_id": project_id, "area_id": row.id})

    async def _area_checks(self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any]) -> None:
        if "area_kind" in data:
            self._need(cat, "area_kinds", data["area_kind"], "unknown_area_kind")
        if data.get("geometry") is not None:
            try:
                validate_polygon(data["geometry"])
            except GeometryError as exc:
                raise LogisticsError("geometry_invalid", 422, detail=str(exc)) from exc
        if data.get("frame") is not None and data["frame"] not in ("local", "wgs84"):
            raise LogisticsError("frame_invalid", 422)
        await self._soft("geo_overlay", data.get("geo_overlay_id"), project_id)
        await self._soft("takt_location", data.get("takt_location_id"), project_id)

    @staticmethod
    def _compute_area(row: SiteArea) -> None:
        row.area_m2 = polygon_area_m2(row.geometry, row.frame) if row.geometry else None

    async def put_allocations(
        self, project_id: uuid.UUID, area_id: Any, items: list[dict[str, Any]], actor_id: Any
    ) -> list[AreaAllocation]:
        """Replace the allocations of one area, one row per stage (rule 2: never above the area)."""
        cat = await self.catalogue(project_id)
        area = await self._get(SiteArea, project_id, area_id, "area_not_found")
        seen: set[uuid.UUID] = set()
        rows = []
        for item in items:
            stage = await self._get(ExpansionStage, project_id, item.get("stage_id"), "stage_not_found")
            if stage.id in seen:
                raise LogisticsError("duplicate_stage", 422)
            seen.add(stage.id)
            kind = item.get("area_kind") or area.area_kind
            self._need(cat, "area_kinds", kind, "unknown_area_kind")
            m2 = Decimal(str(item.get("allocated_m2", area.effective_m2 or 0)))
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
        await self.session.execute(
            delete(AreaAllocation).where(
                AreaAllocation.project_id == project_id, AreaAllocation.site_area_id == area.id
            )
        )
        self.session.add_all(rows)
        await self.session.flush()
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
        cat = await self.catalogue(project_id)
        self._need(cat, "media_kinds", data.get("media_kind"), "unknown_media_kind")
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
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        if "media_kind" in data:
            self._need(await self.catalogue(project_id), "media_kinds", data["media_kind"], "unknown_media_kind")
        changed = self._apply(row, data, _MEDIA_FIELDS)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_updated", metadata=changed)
        return row

    async def transition_media(self, project_id: uuid.UUID, media_id: Any, target: str, actor_id: Any) -> Any:
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        if target == "contracted" and row.contracted_capacity is None:
            raise LogisticsError("contracted_capacity_required", 422)
        before = self._move(pl.MEDIA_FSM, row, target)
        if target == "connected" and row.connected_on is None:
            row.connected_on = datetime.now(UTC).date()
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_transition", from_status=before, to_status=target)
        return row

    async def delete_media(self, project_id: uuid.UUID, media_id: Any, actor_id: Any) -> None:
        row = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.id, "media_deleted")

    async def demands(self, project_id: uuid.UUID, media_id: Any) -> list[MediaDemand]:
        media = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        return await self._list(MediaDemand, project_id, MediaDemand.consumer, media_connection_id=media.id)

    async def create_demand(
        self, project_id: uuid.UUID, media_id: Any, data: dict[str, Any], actor_id: Any
    ) -> MediaDemand:
        media = await self._get(MediaConnection, project_id, media_id, "media_not_found")
        await self._get(ExpansionStage, project_id, data.get("stage_id"), "stage_not_found")
        row = MediaDemand(project_id=project_id, media_connection_id=media.id, media_kind=media.media_kind)
        self._apply(
            row, {k: v for k, v in data.items() if k not in ("media_connection_id", "media_kind")}, _DEMAND_FIELDS
        )
        row.simultaneity_factor = self._factor(data.get("simultaneity_factor", "1"))
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", media.id, "demand_created", metadata={"demand": row.id})
        return row

    async def update_demand(
        self, project_id: uuid.UUID, demand_id: Any, data: dict[str, Any], actor_id: Any
    ) -> MediaDemand:
        row = await self._get(MediaDemand, project_id, demand_id, "demand_not_found")
        if row.site_plant_position_id is not None and "peak_demand" in data:
            # Rule 9: the plant position is the one number; it is changed there.
            raise conflict("demand_owned_by_plant_position")
        if "stage_id" in data:
            await self._get(ExpansionStage, project_id, data["stage_id"], "stage_not_found")
        if data.get("media_connection_id") is not None:
            media = await self._get(MediaConnection, project_id, data["media_connection_id"], "media_not_found")
            data = {**data, "media_kind": media.media_kind}
        changed = self._apply(row, data, _DEMAND_FIELDS)
        if "simultaneity_factor" in data:
            row.simultaneity_factor = self._factor(data["simultaneity_factor"])
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.media_connection_id, "demand_updated", metadata=changed)
        return row

    async def delete_demand(self, project_id: uuid.UUID, demand_id: Any, actor_id: Any) -> None:
        row = await self._get(MediaDemand, project_id, demand_id, "demand_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_media", row.media_connection_id, "demand_deleted")

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
    ) -> MediaDemand | None:
        """Rule 9: a plant position's power demand IS its media demand row, idempotent on the position.

        Called by the plant position save path (module 5). A position without
        power or without a stage removes its demand row. The row joins the
        project's power connection when there is exactly one; otherwise it stays
        unsourced until the planner picks one.
        """
        pid = _uuid(site_plant_position_id)
        if pid is None:
            raise LogisticsError("plant_position_required", 422)
        existing = (
            await self.session.execute(
                select(MediaDemand).where(
                    MediaDemand.project_id == project_id, MediaDemand.site_plant_position_id == pid
                )
            )
        ).scalar_one_or_none()
        if power_demand_kva is None or stage_id is None or Decimal(str(power_demand_kva)) <= 0:
            if existing is not None:
                await self.session.delete(existing)
                await self.session.flush()
            return None
        stage = await self._get(ExpansionStage, project_id, stage_id, "stage_not_found")
        row = existing or MediaDemand(project_id=project_id, site_plant_position_id=pid, media_kind="power")
        if row.media_connection_id is None:
            power = await self._list(MediaConnection, project_id, media_kind="power")
            row.media_connection_id = power[0].id if len(power) == 1 else None
        row.stage_id = stage.id
        row.consumer = consumer
        row.peak_demand = Decimal(str(power_demand_kva))
        if existing is None:
            row.simultaneity_factor = Decimal("1")
            self.session.add(row)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_media", row.media_connection_id, "plant_demand_synced", metadata={"position": pid}
        )
        return row

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
        today = today or datetime.now(UTC).date()
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
        row = await self.concept(project_id)
        assert row is not None
        if "strategy" in data:
            flows = []
            codes: set[str] = set()
            for raw in data["strategy"] or []:
                flow = dict(raw)
                mode = flow.get("mode") or "stock"
                if mode not in pl.FLOW_MODES:
                    raise LogisticsError("flow_mode_invalid", 422, detail=str(mode))
                code = str(flow.get("flow_code") or "").strip()
                if not code or code in codes:
                    raise LogisticsError("flow_code_invalid", 422, detail=code)
                codes.add(code)
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
        for key in ("max_deliveries_per_hour", "rules_text", "document_ref"):
            if key in data:
                value = data[key]
                setattr(row, key, "" if key == "rules_text" and value is None else value)
        row.saved_by = _uuid(actor_id)
        await self.session.flush()
        await self._audit(actor_id, "logistics_concept", row.id, "concept_saved", metadata={"flows": len(row.strategy)})
        return row

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

    async def _limit_sets(self, cat: SiteLogisticsCatalogue, gate: Gate | None) -> list[dict[str, Any]]:
        sets = [pl.limits_from_class(c) for c in cat.load_classes]
        if gate is not None:
            sets.append({limit: getattr(gate, limit, None) for _v, limit in pl.LOAD_FIELDS})
        return sets

    @staticmethod
    def _vehicle(t: Transport) -> dict[str, Any]:
        return {v: getattr(t, v) for v, _limit in pl.LOAD_FIELDS}

    async def transport_view(self, t: Transport, cat: SiteLogisticsCatalogue) -> dict[str, Any]:
        """A transport with its derived ``is_heavy``, gate findings and permit coverage."""
        gate = await self.session.get(Gate, t.gate_id) if t.gate_id else None
        kind = cat.entry("transport_kinds", t.transport_kind)
        limit_sets = await self._limit_sets(cat, gate)
        heavy = pl.is_heavy(self._vehicle(t), limit_sets, always_heavy=bool(getattr(kind, "always_heavy", False)))
        permits = await self._permits_of(t.project_id, t.id)
        start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
        out = transport_out(t)
        out["is_heavy"] = heavy
        out["gate_exceeded"] = pl.exceeded_limits(self._vehicle(t), limit_sets[-1]) if gate is not None else []
        out["permit_finding"] = pl.heavy_permit_finding(permits, start, end, _HEAVY_PERMIT_KINDS) if heavy else None
        out["permits"] = [
            {"id": str(p["id"]), "permit_kind": p["permit_kind"], "state": p["state"], "valid_to": _iso(p["valid_to"])}
            for p in permits
        ]
        return out

    async def _permits_of(self, project_id: uuid.UUID, transport_id: uuid.UUID) -> list[dict[str, Any]]:
        linked = select(PermitTransportLink.permit_id).where(
            PermitTransportLink.project_id == project_id, PermitTransportLink.transport_id == transport_id
        )
        rows = (
            await self.session.execute(
                select(TransportPermit).where(
                    TransportPermit.project_id == project_id,
                    (TransportPermit.transport_id == transport_id) | TransportPermit.id.in_(linked),
                )
            )
        ).scalars()
        return [permit_facts(p) for p in rows]

    async def _transport_checks(self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any]) -> None:
        if "transport_kind" in data:
            self._need(cat, "transport_kinds", data["transport_kind"], "unknown_transport_kind")
        if data.get("direction") is not None and data["direction"] not in pl_directions():
            raise LogisticsError("direction_invalid", 422)
        await self._soft("gate", data.get("gate_id"), project_id)
        await self._soft("po", data.get("po_id"), project_id)
        await self._soft("customs_case", data.get("customs_case_id"), project_id)
        for key in ("planned_window_start", "planned_window_end"):
            if data.get(key) is not None:
                data[key] = _aware(data[key])

    async def create_transport(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> Transport:
        cat = await self.catalogue(project_id)
        data = dict(data)
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
        row = await self._get(Transport, project_id, transport_id, "transport_not_found")
        if row.state in ("closed", "cancelled"):
            raise conflict("transport_closed")
        data = dict(data)
        await self._transport_checks(project_id, cat, data)
        changed = self._apply(row, data, _TRANSPORT_FIELDS)
        self._window_order(row)
        if row.state == "scheduled" and changed:
            # A scheduled transport keeps its slot only while it still satisfies the rules.
            await self._assert_schedulable(project_id, cat, row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_transport", row.id, "transport_updated", metadata=changed)
        return row

    @staticmethod
    def _window_order(row: Transport) -> None:
        if row.planned_window_start and row.planned_window_end and row.planned_window_end <= row.planned_window_start:
            raise LogisticsError("window_invalid", 422)

    async def delete_transport(self, project_id: uuid.UUID, transport_id: Any, actor_id: Any) -> None:
        row = await self._get(Transport, project_id, transport_id, "transport_not_found")
        if row.state in _ONWARD:
            raise conflict("transport_under_way")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_transport", row.id, "transport_deleted")

    async def _assert_schedulable(self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, t: Transport) -> None:
        """Rules 5, 6 and 13 at the moment a transport takes its slot."""
        violations = []
        gate = await self.session.get(Gate, t.gate_id) if t.gate_id else None
        if gate is not None:
            exceeded = pl.exceeded_limits(self._vehicle(t), {lim: getattr(gate, lim) for _v, lim in pl.LOAD_FIELDS})
            if exceeded:
                violations.append({"code": "gate_load_exceeded", "fields": exceeded})
        view = await self.transport_view(t, cat)
        if view["is_heavy"] and view["permit_finding"]:
            violations.append({"code": view["permit_finding"]})
        start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
        plan = await self.neighbourhood(project_id, create=False)
        if plan is not None and start and end and pl.quiet_hours_conflict(plan.quiet_hours, start, end):
            permits = await self._permits_of(project_id, t.id)
            night = [p for p in permits if p["permit_kind"] == "night_work" and pl.permit_covers(p, start, end)]
            if not night:
                violations.append({"code": "quiet_hours_conflict"})
        if violations:
            raise LogisticsError(violations[0]["code"], 422, violations=violations)

    async def transition_transport(
        self, project_id: uuid.UUID, transport_id: Any, target: str, actor_id: Any, today: date | None = None
    ) -> Transport:
        cat = await self.catalogue(project_id)
        row = await self._get(Transport, project_id, transport_id, "transport_not_found")
        if target not in pl.TRANSPORT_STATES:
            raise LogisticsError("invalid_transition", 422)
        if target == "scheduled":
            await self._assert_schedulable(project_id, cat, row)
        if target == "arrived" and row.direction == "inbound" and row.po_id is not None:
            # Rule 19: arrival of PO goods is read from the goods receipt, never recorded twice.
            received = await self._goods_receipt_date(row.po_id)
            if received is None:
                raise conflict("goods_receipt_missing")
            row.arrived_on = received
        elif target == "arrived":
            row.arrived_on = today or datetime.now(UTC).date()
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

    async def _goods_receipt_date(self, po_id: uuid.UUID) -> date | None:
        from app.modules.procurement.models import GoodsReceipt

        rows = (
            await self.session.execute(
                select(GoodsReceipt.receipt_date).where(GoodsReceipt.po_id == po_id, GoodsReceipt.status == "confirmed")
            )
        ).scalars()
        days = [d for d in (_parse_day(r) for r in rows) if d is not None]
        return min(days) if days else None

    async def sync_arrivals(self, project_id: uuid.UUID, actor_id: Any = None) -> int:
        """Rule 19 the other way round: in-transit PO transports whose goods receipt is confirmed arrive."""
        moved = 0
        for t in await self._list(Transport, project_id, state="in_transit", direction="inbound"):
            if t.po_id is None:
                continue
            received = await self._goods_receipt_date(t.po_id)
            if received is not None:
                t.arrived_on = received
                t.state = "arrived"
                moved += 1
                await self._audit(actor_id, "logistics_transport", t.id, "transport_arrived_from_receipt")
        await self.session.flush()
        return moved

    # ── transport permits (rules 6, 7) ─────────────────────────────────────

    async def _permit_checks(self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any]) -> None:
        if "permit_kind" in data:
            self._need(cat, "permit_kinds", data["permit_kind"], "unknown_permit_kind")
        await self._soft("transport", data.get("transport_id"), project_id)
        if "allowed_windows" in data:
            data["allowed_windows"] = _windows(data["allowed_windows"])
        if data.get("valid_from") and data.get("valid_to") and data["valid_to"] < data["valid_from"]:
            raise LogisticsError("validity_invalid", 422)

    async def create_permit(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> TransportPermit:
        cat = await self.catalogue(project_id)
        data = dict(data)
        await self._permit_checks(project_id, cat, data)
        row = TransportPermit(project_id=project_id, state="draft", allowed_windows=[])
        self._apply(row, data, _PERMIT_FIELDS)
        self.session.add(row)
        await self.session.flush()
        await self._set_links(project_id, row, data.get("covers_transport_ids"))
        await self._audit(actor_id, "logistics_permit", row.id, "permit_created", metadata={"kind": row.permit_kind})
        return row

    async def update_permit(
        self, project_id: uuid.UUID, permit_id: Any, data: dict[str, Any], actor_id: Any
    ) -> TransportPermit:
        cat = await self.catalogue(project_id)
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found")
        data = dict(data)
        await self._permit_checks(project_id, cat, data)
        changed = self._apply(row, data, _PERMIT_FIELDS)
        if "covers_transport_ids" in data:
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
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found")
        if target == "applied" and row.applied_on is None:
            row.applied_on = datetime.now(UTC).date()
        if target == "granted" and (row.valid_from is None or row.valid_to is None):
            raise LogisticsError("validity_required", 422)
        before = self._move(pl.PERMIT_FSM, row, target)
        await self.session.flush()
        await self._audit(
            actor_id, "logistics_permit", row.id, "permit_transition", from_status=before, to_status=target
        )
        return row

    async def delete_permit(self, project_id: uuid.UUID, permit_id: Any, actor_id: Any) -> None:
        row = await self._get(TransportPermit, project_id, permit_id, "permit_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_permit", row.id, "permit_deleted")

    async def _open_transports_of(self, project_id: uuid.UUID, permit: TransportPermit) -> list[Transport]:
        ids = set(await self.permit_links(project_id, permit.id))
        if permit.transport_id:
            ids.add(str(permit.transport_id))
        out = []
        for tid in ids:
            t = await self.session.get(Transport, uuid.UUID(tid))
            if t is not None and t.state not in ("arrived", "closed", "cancelled"):
                out.append(t)
        return out

    async def sweep_permits(self, project_id: uuid.UUID, today: date, actor_id: Any = None) -> dict[str, int]:
        """Rule 7: expire passed permits, warn once about expiring ones with transports remaining."""
        cat = await self.catalogue(project_id)
        warn = cat.resolved_thresholds().permit_warn_days
        owner = await self._area_owner(project_id)
        counts = {"expired": 0, "expiring": 0}
        for p in await self._list(TransportPermit, project_id, state="granted"):
            status = pl.permit_expiry(p.valid_to, today, warn)
            remaining = await self._open_transports_of(project_id, p)
            ctx = {"project_id": project_id, "permit_id": p.id, "reference": p.reference, "valid_to": p.valid_to}
            if status == "expired":
                p.state = "expired"
                counts["expired"] += 1
                await self._audit(actor_id, "logistics_permit", p.id, "permit_expired", to_status="expired")
                self._publish(ev.PERMIT_EXPIRED, {**ctx, "transports": [t.id for t in remaining]})
                await self._notify(owner, "permit_expired", "logistics_permit", p.id, ctx)
            elif status == "expiring" and remaining and p.expiry_notified_on is None:
                p.expiry_notified_on = today
                counts["expiring"] += 1
                self._publish(ev.PERMIT_EXPIRING, ctx)
                await self._notify(owner, "permit_expiring", "logistics_permit", p.id, ctx)
        await self.session.flush()
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

    async def create_customs(
        self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsCase:
        cat = await self.catalogue(project_id)
        data = dict(data)
        if not can_see_values:
            data = {k: v for k, v in data.items() if k not in _CUSTOMS_VALUE_FIELDS}
        if not data.get("incoterm"):
            raise LogisticsError("incoterm_unknown", 422)
        await self._customs_checks(project_id, cat, data)
        row = CustomsCase(project_id=project_id, state="open", incoterm_version=cat.incoterm_version)
        self._apply(row, data, _CUSTOMS_FIELDS)
        self.session.add(row)
        await self.session.flush()
        await self.refresh_documents(project_id, row, cat)
        await self._audit(actor_id, "logistics_customs", row.id, "customs_created", metadata={"incoterm": row.incoterm})
        return row

    async def update_customs(
        self, project_id: uuid.UUID, case_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsCase:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        if row.state in ("cleared", "closed"):
            raise conflict("customs_closed")
        data = dict(data)
        if not can_see_values:
            data = {k: v for k, v in data.items() if k not in _CUSTOMS_VALUE_FIELDS}
        await self._customs_checks(project_id, cat, data)
        changed = self._apply(row, data, _CUSTOMS_FIELDS)
        if "incoterm" in changed:
            # The case is now under the pinned catalogue's revision of the rules.
            row.incoterm_version = cat.incoterm_version
        await self.session.flush()
        await self.refresh_documents(project_id, row, cat)
        await self._audit(
            actor_id,
            "logistics_customs",
            row.id,
            "customs_updated",
            metadata={k: v for k, v in changed.items() if k not in _CUSTOMS_VALUE_FIELDS},
        )
        return row

    async def delete_customs(self, project_id: uuid.UUID, case_id: Any, actor_id: Any) -> None:
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        if row.state not in ("open", "documents_complete"):
            raise conflict("customs_declared")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_customs", row.id, "customs_deleted")

    def incoterm_of(self, cat: SiteLogisticsCatalogue, case: CustomsCase) -> Any:
        return cat.entry("incoterms", case.incoterm) if case.incoterm_version == cat.incoterm_version else None

    async def refresh_documents(self, project_id: uuid.UUID, case: CustomsCase, cat: SiteLogisticsCatalogue) -> None:
        """Rule 15: the checklist follows direction, incoterm, mode and preferential lines.

        Required documents are added as ``missing``; a document no longer
        required stays on the list (with what was received) but turns optional.
        """
        lines = await self._list(CustomsLine, project_id, customs_case_id=case.id)
        incoterm = self.incoterm_of(cat, case)
        required = set(
            pl.required_documents(
                case.direction, incoterm, case.transport_mode, any(x.preferential_origin for x in lines)
            )
        )
        docs = {d.kind: d for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)}
        for kind, doc in docs.items():
            doc.required = kind in required
        for kind in required - set(docs):
            self.session.add(
                CustomsDocument(
                    project_id=project_id, customs_case_id=case.id, kind=kind, required=True, state="missing"
                )
            )
        await self.session.flush()

    async def lines(self, project_id: uuid.UUID, case_id: Any) -> list[CustomsLine]:
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        return await self._list(CustomsLine, project_id, CustomsLine.sort_order, customs_case_id=case.id)

    async def create_line(
        self, project_id: uuid.UUID, case_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsLine:
        cat = await self.catalogue(project_id)
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        data = await self._line_checks(project_id, cat, data, can_see_values)
        row = CustomsLine(project_id=project_id, customs_case_id=case.id)
        self._apply(row, data, _LINE_FIELDS)
        self.session.add(row)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._audit(actor_id, "logistics_customs", case.id, "line_created", metadata={"hs_code": row.hs_code})
        return row

    async def update_line(
        self, project_id: uuid.UUID, line_id: Any, data: dict[str, Any], actor_id: Any, *, can_see_values: bool
    ) -> CustomsLine:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsLine, project_id, line_id, "line_not_found")
        case = await self._get(CustomsCase, project_id, row.customs_case_id, "customs_not_found")
        data = await self._line_checks(project_id, cat, data, can_see_values)
        changed = self._apply(row, data, _LINE_FIELDS)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._audit(
            actor_id,
            "logistics_customs",
            case.id,
            "line_updated",
            metadata={k: v for k, v in changed.items() if k != "value"},
        )
        return row

    async def delete_line(self, project_id: uuid.UUID, line_id: Any, actor_id: Any) -> None:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsLine, project_id, line_id, "line_not_found")
        case = await self._get(CustomsCase, project_id, row.customs_case_id, "customs_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self.refresh_documents(project_id, case, cat)
        await self._audit(actor_id, "logistics_customs", case.id, "line_deleted")

    async def _line_checks(
        self, project_id: uuid.UUID, cat: SiteLogisticsCatalogue, data: dict[str, Any], can_see_values: bool
    ) -> dict[str, Any]:
        data = dict(data)
        if not can_see_values:
            data.pop("value", None)
        if "hs_code" in data:
            code = str(data["hs_code"] or "").replace(".", "").replace(" ", "")
            if not pl.hs_code_valid(code, cat.resolved_thresholds().customs_hs_digits_min):
                raise LogisticsError("hs_code_invalid", 422, detail=code)
            data["hs_code"] = code
        if data.get("origin_country") is not None:
            data["origin_country"] = _country(data["origin_country"])
        if data.get("value") is not None:
            data["value"] = _money(data["value"])
        return data

    async def documents(self, project_id: uuid.UUID, case_id: Any) -> list[CustomsDocument]:
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        return await self._list(CustomsDocument, project_id, CustomsDocument.kind, customs_case_id=case.id)

    async def update_document(
        self, project_id: uuid.UUID, document_id: Any, data: dict[str, Any], actor_id: Any
    ) -> CustomsDocument:
        row = await self._get(CustomsDocument, project_id, document_id, "document_not_found")
        if "document_ref" in data:
            row.document_ref = data["document_ref"]
        if data.get("state") and data["state"] != row.state:
            if not pl.can_move(pl.CUSTOMS_DOCUMENT_FSM, row.state, data["state"]):
                raise conflict("invalid_transition")
            if data["state"] in ("received", "verified") and not row.document_ref:
                raise LogisticsError("document_ref_required", 422)
            row.state = data["state"]
        await self.session.flush()
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
        case = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        self._need(cat, "customs_document_kinds", kind, "unknown_document_kind")
        if any(d.kind == kind for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)):
            raise conflict("document_exists")
        row = CustomsDocument(
            project_id=project_id, customs_case_id=case.id, kind=kind, required=False, state="missing"
        )
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_customs", case.id, "document_added", metadata={"kind": kind})
        return row

    async def transition_customs(
        self, project_id: uuid.UUID, case_id: Any, target: str, actor_id: Any, today: date | None = None
    ) -> CustomsCase:
        cat = await self.catalogue(project_id)
        row = await self._get(CustomsCase, project_id, case_id, "customs_not_found")
        docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=row.id)]
        missing = pl.missing_required(docs)
        if target in ("documents_complete", "declared") and missing:
            raise LogisticsError("required_document_missing", 422, violations=[{"code": k} for k in missing])
        if target in ("documents_complete", "declared"):
            lines = await self._list(CustomsLine, project_id, customs_case_id=row.id)
            if not lines:
                raise LogisticsError("customs_without_lines", 422)
        if target == "declared" and self.incoterm_of(cat, row) is None:
            raise LogisticsError("incoterm_unknown", 422)
        if target == "cleared":
            row.cleared_on = row.cleared_on or today or datetime.now(UTC).date()
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

    async def neighbourhood(self, project_id: uuid.UUID, *, create: bool = True) -> NeighbourhoodPlan | None:
        row = (
            await self.session.execute(select(NeighbourhoodPlan).where(NeighbourhoodPlan.project_id == project_id))
        ).scalar_one_or_none()
        if row is None and create:
            row = NeighbourhoodPlan(project_id=project_id, quiet_hours=[])
            self.session.add(row)
            await self.session.flush()
        return row

    async def put_neighbourhood(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any) -> NeighbourhoodPlan:
        cat = await self.catalogue(project_id)
        row = await self.neighbourhood(project_id)
        assert row is not None
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
            row.reported_on = datetime.now(UTC).date()
        if row.response_due is None:
            row.response_due = row.reported_on + timedelta(days=cat.resolved_thresholds().neighbour_response_days)
        self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "logistics_complaint", row.id, "complaint_received", metadata={"kind": row.kind})
        return row

    async def update_complaint(
        self, project_id: uuid.UUID, complaint_id: Any, data: dict[str, Any], actor_id: Any
    ) -> NeighbourIssue:
        row = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found")
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
        row = await self._get(NeighbourIssue, project_id, complaint_id, "complaint_not_found")
        if target in ("action_taken", "closed") and not row.response.strip():
            raise LogisticsError("response_required", 422)
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

    async def sweep_complaints(self, project_id: uuid.UUID, today: date, actor_id: Any = None) -> int:
        """Rule 18: notify the m06 owner once per complaint past its response date."""
        owner = await self._area_owner(project_id)
        count = 0
        for c in await self._list(NeighbourIssue, project_id, state="received"):
            if pl.complaint_overdue(c.state, c.response_due, today) and c.overdue_notified_on is None:
                c.overdue_notified_on = today
                count += 1
                ctx = {"project_id": project_id, "complaint_id": c.id, "kind": c.kind, "due": c.response_due}
                self._publish(ev.NEIGHBOUR_ISSUE_OVERDUE, ctx)
                await self._notify(
                    c.owner_user_id or owner, "neighbour_issue_overdue", "logistics_complaint", c.id, ctx
                )
        await self.session.flush()
        return count

    async def create_coordination(
        self, project_id: uuid.UUID, data: dict[str, Any], actor_id: Any
    ) -> CoordinationEntry:
        await self._soft("correspondence", data.get("correspondence_id"), project_id)
        row = CoordinationEntry(project_id=project_id)
        self._apply(row, data, _COORD_FIELDS)
        if row.entry_date is None:
            row.entry_date = datetime.now(UTC).date()
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

    async def findings(self, project_id: uuid.UUID, today: date | None = None) -> list[dict[str, Any]]:
        """Every rule finding of the plan, the input of the rule set and of gate readiness."""
        today = today or datetime.now(UTC).date()
        cat = await self.catalogue(project_id)
        th = cat.resolved_thresholds()
        out: list[dict[str, Any]] = []
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
                for d in m["unsourced"]:
                    out.append(_finding("media_sourced", "media_unsourced", "warning", d, media=m["media_kind"]))
                for c in m["late"]:
                    out.append(
                        _finding("media_on_time", "media_late", "error", c, stage=stage["code"], media=m["media_kind"])
                    )
        for zone in await self._list(LaydownZone, project_id):
            if zone.site_area_id is None:
                out.append(_finding("zone_mapped", "zone_not_mapped", "warning", zone.id, zone=zone.name))
        gates = await self._list(Gate, project_id)
        for gate in gates:
            if pl.limits_unknown({lim: getattr(gate, lim) for _v, lim in pl.LOAD_FIELDS}):
                out.append(_finding("gate_limits_known", "gate_limits_unknown", "warning", gate.id, gate=gate.name))
        gate_by_id = {g.id: g for g in gates}
        plan = await self.neighbourhood(project_id, create=False)
        quiet = plan.quiet_hours if plan is not None else []
        flows = {f["flow_code"]: f for f in ((await self.concept(project_id)).strategy or [])}  # type: ignore[union-attr]
        jit_buffer = min((int(f["buffer_days"]) for f in flows.values() if f["mode"] == "just_in_time"), default=None)
        for d in await self._list(DeliveryBooking, project_id):
            gate = gate_by_id.get(d.gate_id) if d.gate_id else None
            if gate is not None and d.status in ("requested", "approved"):
                if pl.exceeded_limits({"gross_weight_t": d.gross_weight_t}, {"max_gross_t": gate.max_gross_t}):
                    out.append(
                        _finding("gate_load_respected", "gate_load_exceeded", "error", d.id, title=d.supplier_name)
                    )
            start, end = _aware(d.window_start), _aware(d.window_end)
            if d.status == "approved" and start and end and pl.quiet_hours_conflict(quiet, start, end):
                out.append(
                    _finding("quiet_hours_respected", "quiet_hours_conflict", "error", d.id, title=d.supplier_name)
                )
            if jit_buffer is not None and d.takt_location_id and start and d.status in ("requested", "approved"):
                code = pl.jit_finding(start.date(), await self.takt_location_start(d.takt_location_id), jit_buffer)
                if code:
                    out.append(
                        _finding(
                            "jit_aligned_to_takt",
                            code,
                            "warning" if code == "jit_too_early" else "error",
                            d.id,
                            title=d.supplier_name,
                        )
                    )
        for t in await self._list(Transport, project_id):
            if t.state in ("closed", "cancelled"):
                continue
            view = await self.transport_view(t, cat)
            if view["gate_exceeded"]:
                out.append(_finding("gate_load_respected", "gate_load_exceeded", "error", t.id, title=t.title))
            if view["is_heavy"] and view["permit_finding"] and t.state in ("scheduled", *_ONWARD):
                out.append(_finding("heavy_transport_permitted", view["permit_finding"], "error", t.id, title=t.title))
            start, end = _aware(t.planned_window_start), _aware(t.planned_window_end)
            if t.state == "scheduled" and start and end and pl.quiet_hours_conflict(quiet, start, end):
                night = [
                    p
                    for p in await self._permits_of(project_id, t.id)
                    if p["permit_kind"] == "night_work" and pl.permit_covers(p, start, end)
                ]
                if not night:
                    out.append(_finding("quiet_hours_respected", "quiet_hours_conflict", "error", t.id, title=t.title))
        for p in await self._list(TransportPermit, project_id):
            status = pl.permit_expiry(p.valid_to, today, th.permit_warn_days)
            if p.state == "granted" and status != "ok" and await self._open_transports_of(project_id, p):
                sev = "error" if status == "expired" else "warning"
                out.append(_finding("permit_not_expiring", f"permit_{status}", sev, p.id, reference=p.reference))
        for case in await self._list(CustomsCase, project_id):
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
            if case.state in ("open", "documents_complete"):
                docs = [document_out(d) for d in await self._list(CustomsDocument, project_id, customs_case_id=case.id)]
                for kind in pl.missing_required(docs):
                    out.append(
                        _finding(
                            "customs_documents_complete", "required_document_missing", "warning", case.id, kind=kind
                        )
                    )
        for c in await self._list(NeighbourIssue, project_id):
            if pl.complaint_overdue(c.state, c.response_due, today):
                out.append(
                    _finding("neighbour_issue_on_time", "neighbour_issue_overdue", "error", c.id, due=c.response_due)
                )
        return out

    async def validation_payload(self, project_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
        """The payload the ``site_logistics`` rule set reads (see ``validators.py``)."""
        return {"findings": await self.findings(project_id, today)}

    async def readiness(self, project_id: uuid.UUID, today: date | None = None) -> dict[str, Any]:
        """Readiness of area ``m06_logistics`` for gate ``development_to_execution`` (SPEC section 7)."""
        today = today or datetime.now(UTC).date()
        cat = await self.catalogue(project_id)
        findings = await self.findings(project_id, today)
        errors = [f for f in findings if f["severity"] == "error"]
        items: list[dict[str, Any]] = [_item("no_errors", not errors, ",".join(sorted({f["code"] for f in errors})))]
        balance = await self.balance(project_id, today=today)
        open_stages = [b for b in balance["items"] if b["stage"]["state"] != "closed"]
        unbalanced = [b["stage"]["code"] for b in open_stages if not b["area"]["closed"]]
        items.append(_item("balance_closed", not unbalanced, ",".join(unbalanced)))
        first = balance["items"][0] if balance["items"] else None
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
        exported = bool(concept and concept.document_ref) or await self._frame_doc_bound(project_id)
        items.append(_item("concept_saved_and_exported", saved and exported, "" if saved else "concept_empty"))
        unpermitted = []
        for t in await self._list(Transport, project_id):
            if t.state == "cancelled":
                continue
            view = await self.transport_view(t, cat)
            if view["is_heavy"] and not any(p["state"] in ("applied", "granted") for p in view["permits"]):
                unpermitted.append(t.title or str(t.id))
        items.append(_item("heavy_transports_applied", not unpermitted, ",".join(unpermitted)))
        plan = await self.neighbourhood(project_id, create=False)
        items.append(_item("neighbourhood_limit_source", bool(plan and plan.noise_limit_source), ""))
        return {
            "area": AREA_CODE,
            "gate": READINESS_GATE,
            "ready": all(i["state"] == "met" for i in items),
            "items": items,
            "findings": findings,
        }

    async def _frame_doc_bound(self, project_id: uuid.UUID) -> bool:
        try:
            from app.modules.project_governance.models import GovernanceDocument

            row = (
                await self.session.execute(
                    select(GovernanceDocument.bound_revision_id, GovernanceDocument.container_id).where(
                        GovernanceDocument.project_id == project_id, GovernanceDocument.doc_type == FRAME_DOC
                    )
                )
            ).first()
        except Exception:
            return False
        return bool(row and (row[0] or row[1]))

    async def frame_summary(
        self, project_id: uuid.UUID, today: date | None = None, *, can_see_values: bool = False
    ) -> dict[str, Any]:
        """The content of governance frame document ``m06_logistics_frame`` as one read model."""
        today = today or datetime.now(UTC).date()
        cat = await self.catalogue(project_id)
        concept = await self.concept(project_id)
        plan = await self.neighbourhood(project_id, create=False)
        transports = [await self.transport_view(t, cat) for t in await self._list(Transport, project_id)]
        return {
            "project_id": str(project_id),
            "as_of": today.isoformat(),
            "doc_type": FRAME_DOC,
            "catalogue": {
                "source": concept.catalogue_source,  # type: ignore[union-attr]
                "id": concept.catalogue_id,  # type: ignore[union-attr]
                "version": concept.catalogue_version,  # type: ignore[union-attr]
                "jurisdiction": cat.jurisdiction,
            },
            "balance": (await self.balance(project_id, today=today))["items"],
            "concept": concept_out(concept) if concept else None,
            "transports": transports,
            "permits": [permit_out(p) for p in await self._list(TransportPermit, project_id)],
            "customs": [
                customs_out(c, can_see_values)
                for c in await self._list(CustomsCase, project_id, CustomsCase.created_at)
            ],
            "neighbourhood": neighbourhood_out(plan) if plan else None,
            "readiness": await self.readiness(project_id, today),
        }


# ── helpers ────────────────────────────────────────────────────────────────


def pl_directions() -> tuple[str, ...]:
    return ("inbound", "outbound")


def pl_modes() -> tuple[str, ...]:
    from app.modules.site_logistics.catalogue import TRANSPORT_MODES

    return TRANSPORT_MODES


def _item(code: str, met: bool, detail: str) -> dict[str, Any]:
    return {"code": code, "state": "met" if met else "not_met", "detail": detail}


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
        "state": t.state,
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
