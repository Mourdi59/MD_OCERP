# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Permits service: roadmap, applications and clocks, decisions, permits and the condition register.

Every write runs in the caller's transaction with its audit entry
(``log_activity``) and its events (``publish_after_commit``). Requirement state,
forecasts, conflicts, overdue flags and readiness are derived on read; only
what an authority or a person decided is stored.

Decision flow (rules 7, 8, 10, 13, 14)::

    record_decision -- lock the application, refuse a second decision (409),
                       check the outcome's own rules, write the immutable
                       decision, then by application kind:
                         new / early_start      -> permit + its conditions
                         variation / amendment  -> new permit, parent superseded,
                                                   conditions carried forward
                         extension_of_validity  -> parent permit's lapse date moved
                         discharge_of_conditions-> listed conditions discharged
                       partially_granted adds a follow-up requirement for the rest.

Dates the authority sets are calendar dates; the platform keeps no project
time zone, so the date recorded is the date that counts. Timestamps are UTC.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.permits import conditions as cnd
from app.modules.permits import roadmap as rm
from app.modules.permits.catalogue import (
    APPLICANT_ROLES,
    CONDITION_KINDS,
    CONDITION_TRIGGERS,
    PERMIT_TYPE_KIND,
    PermitType,
    PermitTypeCatalogue,
    default_catalogue_id,
    merged,
    register_kind,
    shipped_catalogues,
)
from app.modules.permits.clock import ClockError, ClockEvent, ClockSpec, check_extension, check_stop
from app.modules.permits.clock import deemed_proposal as clock_deemed
from app.modules.permits.clock import duration_days as clock_duration
from app.modules.permits.clock import forecast as clock_forecast
from app.modules.permits.errors import PermitError, conflict, forbidden, not_found
from app.modules.permits.fsm import (
    APPLICATION_FSM,
    APPLICATION_KINDS,
    CONDITION_FSM,
    DECISION_OUTCOMES,
    PERMIT_FSM,
    USER_TARGETS,
)
from app.modules.permits.models import (
    ClockEvent as ClockEventRow,
)
from app.modules.permits.models import (
    ConditionDischarge,
    ConditionEvidence,
    Permit,
    PermitApplication,
    PermitCondition,
    PermitDecision,
    PermitRequirement,
    PermitRoadmap,
    RequirementDependency,
)
from app.modules.permits.repository import PermitRepository

logger = logging.getLogger(__name__)

MODULE = "permits"
TARGET_KIND = "permit_application"
_MANAGER_ROLES = frozenset({"admin", "manager"})
DECIDABLE = ("submitted", "validated", "under_review", "info_requested")
NOT_REFUSED = ("granted", "granted_with_conditions", "partially_granted", "deemed_granted")
PERMIT_KINDS = ("new", "early_start", "variation", "amendment_non_material")
CHILD_KINDS = ("variation", "amendment_non_material", "extension_of_validity", "discharge_of_conditions")
EVIDENCE_KINDS = (
    "cde_revision",
    "inspection",
    "commissioning_item",
    "report",
    "photo",
    "external_url",
    "discharge_decision",
)
BREACH_REF_KINDS = ("safety_observation", "inspection", "manual")
ROADMAP_DOC = "dev_permit_roadmap"
# Governance area codes the roadmap and the register report to, first match wins.
ROADMAP_AREAS = ("m02_contract_management", "contracts_procurement")
CONDITION_AREAS = ("m11_hse", "scope_quality")

# Default applicant resolvers (rule 2). A delivery-model module registers
# ``(session, project_id, allocation_category) -> applicant role | None``.
ApplicantResolver = Callable[[AsyncSession, uuid.UUID, str], Any]
_APPLICANT_RESOLVERS: dict[str, ApplicantResolver] = {}


def register_applicant_resolver(name: str, resolver: ApplicantResolver) -> None:
    """Register (or replace by name) a source of default applicants, e.g. the delivery model's allocations."""
    _APPLICANT_RESOLVERS[name] = resolver


def unregister_applicant_resolver(name: str) -> None:
    _APPLICANT_RESOLVERS.pop(name, None)


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _is_manager(role: str | None) -> bool:
    return (role or "") in _MANAGER_ROLES


class PermitService:
    """Orchestrates the permits of one project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PermitRepository(session)
        register_kind()

    # ── infrastructure ─────────────────────────────────────────────────────

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
        publish_after_commit(self.session, f"{MODULE}.{name}", data, source_module=MODULE)

    async def _fsm(self, fsm: Any, row: Any, target: str, actor_id: Any, reason: str | None = None) -> None:
        try:
            await fsm.apply(
                self.session,
                row,
                target,
                actor_id=_s(actor_id),
                reason=reason,
                extra_metadata={"project_id": _s(row.project_id)},
                entity_type=fsm.name,
            )
        except FSMError as exc:
            raise conflict("invalid_transition", detail=str(exc)) from exc

    async def _notify(self, user_id: Any, kind: str, entity_type: str, entity_id: Any, ctx: dict[str, Any]) -> None:
        """Best effort, inside a savepoint so a failure never poisons the write."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"permits_{kind}",
                    title_key=f"notifications.permits.{kind}.title",
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    body_key=f"notifications.permits.{kind}.body",
                    body_context=ctx,
                    action_url=f"/projects/{ctx.get('project_id')}/permits",
                    metadata=ctx,
                )
        except Exception:
            logger.debug("permits: notification %s failed", kind, exc_info=True)

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    # ── soft links (rule 24: anything of another project is 404) ───────────

    async def _check_link(self, kind: str, ref_id: Any, project_id: uuid.UUID) -> None:
        rid = _uuid(ref_id)
        if rid is None:
            return
        owner = await self._link_project(kind, rid)
        if owner != project_id:
            raise not_found(f"{kind}_not_found")

    async def _link_project(self, kind: str, rid: uuid.UUID) -> uuid.UUID | None:
        if kind == "activity":
            from app.modules.schedule.models import Activity, Schedule

            stmt = select(Schedule.project_id).join(Activity, Activity.schedule_id == Schedule.id)
            return (await self.session.execute(stmt.where(Activity.id == rid))).scalar_one_or_none()
        if kind in ("cde_revision", "document_revision"):
            from app.modules.cde.models import DocumentContainer, DocumentRevision

            stmt = select(DocumentContainer.project_id).join(
                DocumentRevision, DocumentRevision.container_id == DocumentContainer.id
            )
            return (await self.session.execute(stmt.where(DocumentRevision.id == rid))).scalar_one_or_none()
        simple: dict[str, tuple[str, str]] = {
            "cde_container": ("app.modules.cde.models", "DocumentContainer"),
            "review_cycle": ("app.modules.review_authority.models", "ReviewCycle"),
            "submission": ("app.modules.authority_submission.models", "Submission"),
            "inspection": ("app.modules.inspections.models", "QualityInspection"),
            "safety_observation": ("app.modules.safety.models", "SafetyObservation"),
            "route_assessment": ("app.modules.project_route.models", "RouteAssessment"),
            "gate_condition": ("app.modules.project_governance.models", "GovernanceCondition"),
        }
        if kind == "commissioning_item":
            from app.modules.commissioning.models import CxChecklist, CxChecklistItem, CxSystem

            stmt = (
                select(CxSystem.project_id)
                .join(CxChecklist, CxChecklist.system_id == CxSystem.id)
                .join(CxChecklistItem, CxChecklistItem.checklist_id == CxChecklist.id)
                .where(CxChecklistItem.id == rid)
            )
            return (await self.session.execute(stmt)).scalar_one_or_none()
        if kind not in simple:
            return None
        import importlib

        module, name = simple[kind]
        model = getattr(importlib.import_module(module), name)
        return (await self.session.execute(select(model.project_id).where(model.id == rid))).scalar_one_or_none()

    # ── catalogue ──────────────────────────────────────────────────────────

    async def catalogue_for(self, roadmap: PermitRoadmap) -> PermitTypeCatalogue:
        """The pinned catalogue with its ``extends`` chain resolved."""
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        try:
            obj = await resolve_catalogue(
                self.session,
                roadmap.catalogue_source,
                roadmap.catalogue_id,
                roadmap.catalogue_version,
                kind=PERMIT_TYPE_KIND,
            )
        except GovernanceError as exc:
            raise PermitError(exc.code, exc.status_code) from exc
        shipped = shipped_catalogues()
        try:
            return merged(obj, lambda cid: shipped[cid])
        except (KeyError, ValueError) as exc:
            raise PermitError("catalogue_invalid", 422, detail=str(exc)) from exc

    async def _types(self, roadmap: PermitRoadmap) -> dict[str, PermitType]:
        return (await self.catalogue_for(roadmap)).type_map()

    def _type(self, types: dict[str, PermitType], code: str) -> PermitType:
        t = types.get(code)
        if t is None:
            raise PermitError("unknown_permit_type", 422)
        return t

    # ── calendar ───────────────────────────────────────────────────────────

    async def working_day(self, project_id: uuid.UUID) -> Callable[[date], bool]:
        """The project's working-day calendar, resolved the way the schedule resolves it."""
        from app.modules.schedule.service import ScheduleService, get_work_calendar

        svc = ScheduleService(self.session)
        try:
            region = await svc.resolve_project_region(project_id)
            sub = await svc.resolve_project_subdivision(project_id)
        except Exception:
            region, sub = None, None
        cal = get_work_calendar(region, sub)
        work_days = set(cal.get("work_days") or ())
        holidays_of = cal.get("holidays")
        cache: dict[int, frozenset[date]] = {}

        def is_working(d: date) -> bool:
            if d.weekday() not in work_days:
                return False
            if callable(holidays_of):
                if d.year not in cache:
                    cache[d.year] = frozenset(holidays_of(d.year))
                return d not in cache[d.year]
            return True

        return is_working

    # ── roadmap ────────────────────────────────────────────────────────────

    async def get_roadmap(self, project_id: uuid.UUID) -> PermitRoadmap:
        roadmap = await self.repo.get_roadmap(project_id)
        if roadmap is None:
            raise not_found("roadmap_missing")
        await self._mirror_binding(roadmap)
        return roadmap

    async def _roadmap_document(self, project_id: uuid.UUID) -> Any:
        from app.modules.project_governance.models import GovernanceDocument

        stmt = select(GovernanceDocument).where(
            GovernanceDocument.project_id == project_id, GovernanceDocument.doc_type == ROADMAP_DOC
        )
        return (await self.session.execute(stmt)).scalars().first()

    async def _mirror_binding(self, roadmap: PermitRoadmap) -> None:
        """Rule 18: ``agreed`` mirrors the governance binding state of the roadmap frame document."""
        doc = await self._roadmap_document(roadmap.project_id)
        status = "agreed" if doc is not None and doc.status == "binding" else "draft"
        if doc is not None and roadmap.governance_document_id != doc.id:
            roadmap.governance_document_id = doc.id
        if roadmap.status != status:
            roadmap.status = status
            await self.session.flush()

    async def _structural_guard(self, roadmap: PermitRoadmap, change_request_id: Any) -> None:
        """Rule 18: after binding, structural roadmap changes need an approved frame change request."""
        await self._mirror_binding(roadmap)
        if roadmap.status != "agreed":
            return
        from app.modules.project_governance.models import GovernanceChangeRequest

        crid = _uuid(change_request_id)
        if crid is not None:
            cr = await self.session.get(GovernanceChangeRequest, crid)
            if (
                cr is not None
                and cr.project_id == roadmap.project_id
                and cr.document_id == roadmap.governance_document_id
                and cr.status == "approved"
            ):
                return
        raise conflict("roadmap_binding_change_request_required")

    async def _area_codes(self, project_id: uuid.UUID) -> tuple[str, str]:
        from app.modules.project_governance.models import GovernanceArea

        rows = (
            (await self.session.execute(select(GovernanceArea.code).where(GovernanceArea.project_id == project_id)))
            .scalars()
            .all()
        )
        codes = set(rows)
        road = next((c for c in ROADMAP_AREAS if c in codes), "")
        cond = next((c for c in CONDITION_AREAS if c in codes), road)
        return road, cond

    async def set_roadmap(
        self,
        project_id: uuid.UUID,
        *,
        tenant_id: str | None,
        actor_id: uuid.UUID,
        catalogue_source: str | None = None,
        catalogue_id: str | None = None,
        catalogue_version: int | None = None,
        jurisdiction: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> PermitRoadmap:
        """Create the roadmap (country default catalogue) or re-pin / change its settings."""
        from app.modules.project_governance.catalogue_store import CatalogueStore
        from app.modules.project_governance.errors import GovernanceError

        project = await self._project(project_id)
        roadmap = await self.repo.get_roadmap(project_id, lock=True)
        country = getattr(project, "country_code", None)
        juris = (jurisdiction or (roadmap.jurisdiction if roadmap else "") or (country or "")).upper()
        source = catalogue_source or (roadmap.catalogue_source if roadmap else "shipped")
        cid = catalogue_id or (roadmap.catalogue_id if roadmap else default_catalogue_id(country, juris))
        repin = roadmap is None or any(v is not None for v in (catalogue_source, catalogue_id, catalogue_version))
        if repin:
            try:
                version = await CatalogueStore(self.session).assert_pinnable(
                    tenant_id, source, cid, catalogue_version, kind=PERMIT_TYPE_KIND
                )
            except GovernanceError as exc:
                raise PermitError(exc.code, exc.status_code) from exc
        else:
            version = roadmap.catalogue_version
        before = None
        if roadmap is None:
            road_area, cond_area = await self._area_codes(project_id)
            roadmap = await self.repo.add(
                PermitRoadmap(
                    project_id=project_id,
                    catalogue_source=source,
                    catalogue_id=cid,
                    catalogue_version=version,
                    jurisdiction=juris,
                    roadmap_area_code=road_area,
                    conditions_area_code=cond_area,
                    created_by=actor_id,
                )
            )
            action = "roadmap_created"
        else:
            before = {"catalogue": f"{roadmap.catalogue_source}:{roadmap.catalogue_id}@{roadmap.catalogue_version}"}
            roadmap.catalogue_source, roadmap.catalogue_id, roadmap.catalogue_version = source, cid, version
            roadmap.jurisdiction = juris
            action = "roadmap_updated"
        for key, value in (settings or {}).items():
            if value is None:
                continue
            if key in ("route_assessment_id", "approval_route_id"):
                if key == "route_assessment_id":
                    await self._check_link("route_assessment", value, project_id)
                setattr(roadmap, key, _uuid(value))
            elif key == "delivery_model_id":
                roadmap.delivery_model_id = _uuid(value)
            elif key in ("internal_review", "escalation_days", "buffer_days", "roadmap_area_code"):
                setattr(roadmap, key, value)
            elif key == "conditions_area_code":
                roadmap.conditions_area_code = value
        await self.catalogue_for(roadmap)  # a pinned catalogue whose parent is gone is refused now
        await self.session.flush()
        after = {"catalogue": f"{roadmap.catalogue_source}:{roadmap.catalogue_id}@{roadmap.catalogue_version}"}
        await self._audit(actor_id, "permit_roadmap", roadmap.id, action, before_state=before, metadata=after)
        return roadmap

    async def require_roadmap(self, project_id: uuid.UUID, *, lock: bool = False) -> PermitRoadmap:
        roadmap = await self.repo.get_roadmap(project_id, lock=lock)
        if roadmap is None:
            raise not_found("roadmap_missing")
        return roadmap

    # ── default applicant (rule 2) ─────────────────────────────────────────

    async def default_applicant(self, project_id: uuid.UUID, ptype: PermitType) -> tuple[str, str]:
        """``(role, source)``: the delivery model's allocation when one answers, else the catalogue default."""
        for name, resolver in list(_APPLICANT_RESOLVERS.items()):
            try:
                async with self.session.begin_nested():
                    role = await resolver(self.session, project_id, ptype.allocation_category)
            except Exception:
                logger.debug("permits: applicant resolver %s failed", name, exc_info=True)
                continue
            if role in APPLICANT_ROLES:
                return role, "allocation"
        return ptype.default_applicant_role, "catalogue"

    # ── route proposals (rule 1) ───────────────────────────────────────────

    async def _assessment(self, project_id: uuid.UUID, assessment_id: Any) -> Any:
        from app.modules.project_route.models import RouteAssessment

        aid = _uuid(assessment_id)
        stmt = select(RouteAssessment).where(RouteAssessment.project_id == project_id)
        if aid is not None:
            stmt = stmt.where(RouteAssessment.id == aid)
        else:
            stmt = stmt.where(RouteAssessment.status == "confirmed").order_by(RouteAssessment.created_at.desc())
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            raise not_found("route_assessment_not_found")
        if row.status != "confirmed":
            raise conflict("route_assessment_not_confirmed")
        return row

    async def propose(self, project_id: uuid.UUID, assessment_id: Any = None) -> dict[str, Any]:
        """Requirements the confirmed route implies. Proposals only: nothing is written (principle 7)."""
        roadmap = await self.require_roadmap(project_id)
        assessment = await self._assessment(project_id, assessment_id)
        route = assessment.determined_route
        out: dict[str, Any] = {"route": route, "route_assessment_id": str(assessment.id), "proposals": []}
        if route == "exempt":
            out["reason"] = "route_exempt"
            return out
        if route == "undetermined":
            out["reason"] = "route_undetermined"
            return out
        types = await self._types(roadmap)
        present = {r.permit_type_code for r in await self.repo.list_requirements(project_id)}
        wanted: list[str] = [t.code for t in types.values() if route in t.triggered_by_route]
        # Prerequisites typed ``granted`` come along: the main permit cannot be filed without them.
        i = 0
        while i < len(wanted):
            for r in types[wanted[i]].requires:
                if r.code not in wanted and r.code in types:
                    wanted.append(r.code)
            i += 1
        for code in wanted:
            t = types[code]
            role, source = await self.default_applicant(project_id, t)
            out["proposals"].append(
                {
                    "permit_type_code": code,
                    "name_key": t.name_key,
                    "category": t.category,
                    "applicant_role": role,
                    "applicant_source": source,
                    "already_present": code in present,
                    "requires": [{"code": r.code, "on": r.on} for r in t.requires],
                }
            )
        if not out["proposals"]:
            out["reason"] = "no_types_for_route"
        return out

    async def accept_proposals(
        self,
        project_id: uuid.UUID,
        codes: list[str],
        *,
        actor_id: uuid.UUID,
        assessment_id: Any = None,
        change_request_id: Any = None,
    ) -> list[PermitRequirement]:
        """A human accepts proposals one by one (codes); each becomes a requirement with catalogue dependencies."""
        roadmap = await self.require_roadmap(project_id, lock=True)
        await self._structural_guard(roadmap, change_request_id)
        proposal = await self.propose(project_id, assessment_id)
        offered = {p["permit_type_code"]: p for p in proposal["proposals"]}
        unknown = [c for c in codes if c not in offered]
        if unknown:
            raise PermitError("proposal_not_offered", 422, detail=",".join(unknown))
        types = await self._types(roadmap)
        existing = {r.permit_type_code: r for r in await self.repo.list_requirements(project_id)}
        created: list[PermitRequirement] = []
        for code in codes:
            if code in existing:
                continue
            p = offered[code]
            req = await self.repo.add(
                PermitRequirement(
                    project_id=project_id,
                    permit_type_code=code,
                    applicant_role=p["applicant_role"],
                    applicant_source=p["applicant_source"],
                    governance_area_code=roadmap.roadmap_area_code,
                    proposed_from_route=proposal["route"],
                    sort_order=len(existing) + len(created),
                )
            )
            created.append(req)
            existing[code] = req
        for req in created:
            for r in types[req.permit_type_code].requires:
                dep = existing.get(r.code)
                if dep is not None:
                    await self.repo.add(
                        RequirementDependency(
                            project_id=project_id, requirement_id=req.id, depends_on_id=dep.id, dep_type=r.on
                        )
                    )
        if proposal.get("route_assessment_id"):
            roadmap.route_assessment_id = _uuid(proposal["route_assessment_id"])
        await self.session.flush()
        for req in created:
            await self._audit(actor_id, "permit_requirement", req.id, "requirement_accepted_from_route")
        return created

    # ── requirements ───────────────────────────────────────────────────────

    async def create_requirement(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PermitRequirement:
        roadmap = await self.require_roadmap(project_id, lock=True)
        await self._structural_guard(roadmap, data.pop("change_request_id", None))
        ptype = self._type(await self._types(roadmap), data["permit_type_code"])
        role, source = await self.default_applicant(project_id, ptype)
        if data.get("applicant_role") and data["applicant_role"] != role:
            if not (data.get("applicant_rationale") or "").strip():
                raise PermitError("applicant_override_needs_rationale", 422)
            role, source = data["applicant_role"], "override"
        await self._check_requirement_links(project_id, data)
        count = len(await self.repo.list_requirements(project_id))
        req = await self.repo.add(
            PermitRequirement(
                project_id=project_id,
                permit_type_code=ptype.code,
                title=data.get("title") or "",
                applicable=data.get("applicable", True),
                applicability_rationale=data.get("applicability_rationale") or "",
                applicant_role=role,
                applicant_source=source,
                applicant_rationale=data.get("applicant_rationale") or "",
                applicant_party=data.get("applicant_party") or "",
                applicant_contact_id=_uuid(data.get("applicant_contact_id")),
                responsible_user_id=_uuid(data.get("responsible_user_id")),
                planned_submit_date=data.get("planned_submit_date"),
                needed_by_activity_id=_uuid(data.get("needed_by_activity_id")),
                needed_by_date=data.get("needed_by_date"),
                clock_variant=data.get("clock_variant") or "",
                expected_decision_date=data.get("expected_decision_date"),
                schedule_activity_id=_uuid(data.get("schedule_activity_id")),
                governance_area_code=data.get("governance_area_code") or roadmap.roadmap_area_code,
                sort_order=count,
            )
        )
        if req.clock_variant:
            self._spec(ptype, req.clock_variant)
        if not req.applicable and not req.applicability_rationale.strip():
            raise PermitError("not_applicable_needs_rationale", 422)
        await self._audit(actor_id, "permit_requirement", req.id, "requirement_created")
        return req

    async def _check_requirement_links(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        for key in ("needed_by_activity_id", "schedule_activity_id"):
            if data.get(key):
                await self._check_link("activity", data[key], project_id)

    async def update_requirement(
        self, project_id: uuid.UUID, rid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PermitRequirement:
        """Operational fields; ``applicable`` is structural (rule 18) and needs rationale when false."""
        roadmap = await self.require_roadmap(project_id)
        req = await self.repo.get_requirement(project_id, rid, lock=True)
        if req is None:
            raise not_found("requirement_not_found")
        change_request_id = data.pop("change_request_id", None)
        if "applicable" in data and data["applicable"] is not None and data["applicable"] != req.applicable:
            await self._structural_guard(roadmap, change_request_id)
        await self._check_requirement_links(project_id, data)
        if "applicant_role" in data and data["applicant_role"] and data["applicant_role"] != req.applicant_role:
            if not (data.get("applicant_rationale") or "").strip():
                raise PermitError("applicant_override_needs_rationale", 422)
            req.applicant_source = "override"
        for key, value in data.items():
            if key.endswith("_id") and key not in ("permit_type_code",):
                value = _uuid(value)
            setattr(req, key, value)
        if req.clock_variant:
            self._spec(self._type(await self._types(roadmap), req.permit_type_code), req.clock_variant)
        if not req.applicable and not (req.applicability_rationale or "").strip():
            raise PermitError("not_applicable_needs_rationale", 422)
        await self.session.flush()
        await self._audit(actor_id, "permit_requirement", req.id, "requirement_updated", metadata=_jsonable(data))
        return req

    async def delete_requirement(
        self, project_id: uuid.UUID, rid: uuid.UUID, *, actor_id: uuid.UUID, change_request_id: Any = None
    ) -> None:
        roadmap = await self.require_roadmap(project_id, lock=True)
        await self._structural_guard(roadmap, change_request_id)
        req = await self.repo.get_requirement(project_id, rid, lock=True)
        if req is None:
            raise not_found("requirement_not_found")
        apps = [a for a in await self.repo.list_applications(project_id) if a.requirement_id == rid]
        if any(a.status not in ("planned", "withdrawn") for a in apps):
            raise conflict("requirement_has_applications")
        await self.session.delete(req)
        await self.session.flush()
        await self._audit(actor_id, "permit_requirement", rid, "requirement_deleted")

    async def set_dependencies(
        self,
        project_id: uuid.UUID,
        rid: uuid.UUID,
        deps: list[dict[str, Any]],
        *,
        actor_id: uuid.UUID,
        change_request_id: Any = None,
    ) -> list[RequirementDependency]:
        """Replace one requirement's dependencies; a cycle is refused (rule 3)."""
        roadmap = await self.require_roadmap(project_id, lock=True)
        await self._structural_guard(roadmap, change_request_id)
        req = await self.repo.get_requirement(project_id, rid, lock=True)
        if req is None:
            raise not_found("requirement_not_found")
        ids = {r.id for r in await self.repo.list_requirements(project_id)}
        new_edges = []
        for d in deps:
            target = _uuid(d["depends_on_id"])
            if target not in ids:
                raise not_found("requirement_not_found")
            if d.get("on", "granted") not in ("granted", "submitted"):
                raise PermitError("dependency_type_invalid", 422)
            new_edges.append(rm.Edge(str(rid), str(target), d.get("on", "granted")))
        existing = [e for e in await self.repo.list_dependencies(project_id) if e.requirement_id != rid]
        graph = [rm.Edge(str(e.requirement_id), str(e.depends_on_id), e.dep_type) for e in existing] + new_edges
        cycle = rm.find_cycle(graph)
        if cycle is not None:
            raise PermitError("dependency_cycle", 422, detail=" -> ".join(cycle))
        for e in await self.repo.list_dependencies(project_id):
            if e.requirement_id == rid:
                await self.session.delete(e)
        await self.session.flush()
        rows = [
            await self.repo.add(
                RequirementDependency(
                    project_id=project_id, requirement_id=rid, depends_on_id=_uuid(e.depends_on), dep_type=e.on
                )
            )
            for e in new_edges
        ]
        await self._audit(actor_id, "permit_requirement", rid, "dependencies_set", metadata={"count": len(rows)})
        return rows

    # ── derived state ──────────────────────────────────────────────────────

    async def state_snapshot(self, project_id: uuid.UUID) -> dict[str, Any]:
        """Everything derived about the roadmap in one pass: per requirement state, latest application."""
        reqs = await self.repo.list_requirements(project_id)
        apps = await self.repo.list_applications(project_id)
        decisions = await self.repo.list_decisions(project_id)
        edges = [
            rm.Edge(str(e.requirement_id), str(e.depends_on_id), e.dep_type)
            for e in await self.repo.list_dependencies(project_id)
        ]
        current = _current_decisions(decisions)
        latest: dict[str, PermitApplication] = {}
        for a in apps:
            if a.kind not in ("new", "early_start"):
                continue
            k = str(a.requirement_id)
            if k not in latest or a.attempt > latest[k].attempt:
                latest[k] = a
        submitted = {k: a.status in rm.SUBMITTED_STATES for k, a in latest.items()}
        states: dict[str, str] = {}
        # Two passes: a dependency's own state must be known before its dependant's.
        order = _topo([str(r.id) for r in reqs], edges)
        req_by = {str(r.id): r for r in reqs}
        for rid in order:
            r = req_by[rid]
            a = latest.get(rid)
            dec = current.get(str(a.id)) if a else None
            view = rm.AttemptView(a.status, dec.outcome if dec else None) if a else None
            unmet = rm.unmet_dependencies(rid, edges, states, submitted)
            states[rid] = rm.derive_state(r.applicable, view, not unmet)
        pending = {str(d.application_id) for d in current.values() if d.conditions_pending}
        return {
            "requirements": reqs,
            "applications": apps,
            "decisions": current,
            "edges": edges,
            "latest": latest,
            "states": states,
            "submitted": submitted,
            "conditions_pending": {k for k, a in latest.items() if str(a.id) in pending},
        }

    async def requirement_state(self, project_id: uuid.UUID, rid: uuid.UUID) -> str | None:
        snap = await self.state_snapshot(project_id)
        return snap["states"].get(str(rid))

    # ── clocks and timeline (rules 4, 5, 6) ────────────────────────────────

    def _spec(self, ptype: PermitType, variant: str | None) -> ClockSpec:
        try:
            return ClockSpec.from_catalogue(ptype.clock, variant or None)
        except ClockError as exc:
            raise PermitError(exc.code, 422) from exc

    async def clock_of(
        self,
        app: PermitApplication,
        ptype: PermitType,
        variant: str,
        today: date,
        working_day: Callable[[date], bool],
        expected: date | None = None,
    ) -> dict[str, Any]:
        spec = self._spec(ptype, variant)
        events = [
            ClockEvent(e.kind, e.event_date, e.period, e.unit, e.reason)
            for e in await self.repo.list_clock_events(app.project_id, app.id)
        ]
        result = clock_forecast(
            spec,
            received_at=app.received_at,
            validated_at=app.validated_at,
            events=events,
            today=today,
            working_day=working_day,
            expected_date=expected,
        )
        out = result.as_dict()
        out["deemed_proposal"] = clock_deemed(spec, result, today=today, decided=app.status == "decided")
        out["deemed_requires_notice"] = spec.deemed_requires_notice
        out["period"] = spec.period
        out["unit"] = spec.unit
        out["start_event"] = spec.start_event
        return out

    async def timeline(self, project_id: uuid.UUID, today: date) -> dict[str, Any]:
        """Rule 6: needed-by, latest submit, forecast decision and conflicts per requirement."""
        roadmap = await self.require_roadmap(project_id)
        types = await self._types(roadmap)
        snap = await self.state_snapshot(project_id)
        wd = await self.working_day(project_id)
        activities = await self._activities(project_id, [r.needed_by_activity_id for r in snap["requirements"]])
        inputs = []
        clocks: dict[str, dict[str, Any]] = {}
        for r in snap["requirements"]:
            rid = str(r.id)
            ptype = types.get(r.permit_type_code)
            spec = self._spec(ptype, r.clock_variant) if ptype else ClockSpec(None, None)
            act = activities.get(str(r.needed_by_activity_id)) if r.needed_by_activity_id else None
            need, basis = rm.needed_by(act, r.needed_by_date)
            fc, reason = None, None
            a = snap["latest"].get(rid)
            if a is not None and ptype is not None and a.status not in ("planned", "preparing", "internal_review"):
                clocks[rid] = await self.clock_of(a, ptype, r.clock_variant, today, wd, r.expected_decision_date)
                fc = date.fromisoformat(clocks[rid]["forecast"]) if clocks[rid]["forecast"] else None
                reason = clocks[rid]["reason"]
            elif spec.period is None:
                fc = r.expected_decision_date
                reason = "no_statutory_period"
            inputs.append(
                rm.TimelineInput(
                    rid,
                    need,
                    basis,
                    clock_duration(spec, today, wd) if spec.period else None,
                    roadmap.buffer_days,
                    fc,
                    reason,
                    r.planned_submit_date,
                    r.conflict_accepted,
                )
            )
        rows = rm.timeline(inputs, snap["edges"])
        out = []
        for row, r in zip(rows, snap["requirements"], strict=True):
            d = row.as_dict()
            d["state"] = snap["states"].get(str(r.id))
            d["estimate"] = bool(clocks.get(str(r.id), {}).get("estimate")) or (
                d["forecast_reason"] == "no_statutory_period" and d["forecast_decision"] is not None
            )
            d["clock"] = clocks.get(str(r.id))
            out.append(d)
        return {"items": out, "edges": [e.__dict__ for e in snap["edges"]]}

    async def _activities(self, project_id: uuid.UUID, ids: list[Any]) -> dict[str, dict[str, Any]]:
        wanted = [i for i in ids if i]
        if not wanted:
            return {}
        from app.modules.schedule.models import Activity, Schedule

        stmt = (
            select(Activity)
            .join(Schedule, Schedule.id == Activity.schedule_id)
            .where(Schedule.project_id == project_id, Activity.id.in_(wanted))
        )
        return {
            str(a.id): {
                "id": str(a.id),
                "name": a.name,
                "late_start": a.late_start,
                "early_start": a.early_start,
                "constraint_date": a.constraint_date,
            }
            for a in (await self.session.execute(stmt)).scalars().all()
        }

    async def push_milestone(
        self, project_id: uuid.UUID, rid: uuid.UUID, *, actor_id: uuid.UUID, today: date
    ) -> dict[str, Any]:
        """Rule 6, explicit user action only: write the forecast decision as a schedule milestone."""
        from app.modules.schedule.schemas import ActivityCreate, ActivityUpdate
        from app.modules.schedule.service import ScheduleService

        req = await self.repo.get_requirement(project_id, rid, lock=True)
        if req is None:
            raise not_found("requirement_not_found")
        row = next(r for r in (await self.timeline(project_id, today))["items"] if r["requirement_id"] == str(rid))
        when = row["forecast_decision"] or row["latest_decision"]
        if when is None:
            raise PermitError("no_forecast_to_push", 422)
        svc = ScheduleService(self.session)
        if req.schedule_activity_id is not None:
            await self._check_link("activity", req.schedule_activity_id, project_id)
            await svc.update_activity(
                req.schedule_activity_id, ActivityUpdate(start_date=when, end_date=when), actor_id=str(actor_id)
            )
            action = "milestone_updated"
        else:
            listed = await svc.list_schedules_for_project(project_id)
            schedules = listed[0] if isinstance(listed, tuple) else listed
            if not schedules:
                raise PermitError("no_schedule", 422)
            act = await svc.create_activity(
                ActivityCreate(
                    schedule_id=schedules[0].id,
                    name=(req.title or req.permit_type_code)[:255],
                    start_date=when,
                    end_date=when,
                    activity_type="milestone",
                ),
                actor_id=str(actor_id),
            )
            req.schedule_activity_id = act.id
            action = "milestone_created"
        await self.session.flush()
        await self._audit(actor_id, "permit_requirement", rid, action, metadata={"date": when})
        return {"requirement_id": str(rid), "schedule_activity_id": str(req.schedule_activity_id), "date": when}

    # ── applications ───────────────────────────────────────────────────────

    async def create_application(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PermitApplication:
        roadmap = await self.require_roadmap(project_id)
        rid = _uuid(data["requirement_id"])
        req = await self.repo.get_requirement(project_id, rid, lock=True)
        if req is None:
            raise not_found("requirement_not_found")
        kind = data.get("kind") or "new"
        if kind not in APPLICATION_KINDS:
            raise PermitError("application_kind_invalid", 422)
        types = await self._types(roadmap)
        ptype = self._type(types, req.permit_type_code)
        if kind == "early_start" and ptype.scope != "early_start":
            raise PermitError("early_start_needs_early_start_type", 422)
        parent = None
        if kind in CHILD_KINDS:
            parent = await self.repo.get_permit(project_id, _uuid(data.get("parent_permit_id")) or uuid.uuid4())
            if parent is None:
                raise not_found("permit_not_found")
        cond_ids: list[str] = []
        if kind == "discharge_of_conditions":
            for raw in data.get("discharges_condition_ids") or []:
                c = await self.repo.get_condition(project_id, _uuid(raw))
                if c is None or c.permit_id != parent.id:
                    raise not_found("condition_not_found")
                if c.status not in ("open", "evidence_submitted"):
                    raise conflict("condition_not_open")
                cond_ids.append(str(c.id))
            if not cond_ids:
                raise PermitError("discharge_needs_conditions", 422)
        same = [a for a in await self.repo.list_applications(project_id) if a.requirement_id == rid and a.kind == kind]
        if kind in ("new", "early_start") and any(a.status not in ("decided", "withdrawn") for a in same):
            raise conflict("application_open")
        for key in ("review_cycle_ids",):
            for v in data.get(key) or []:
                await self._check_link("review_cycle", v, project_id)
        await self._check_link("submission", data.get("submission_id"), project_id)
        await self._check_link("cde_container", data.get("cde_container_id"), project_id)
        app = PermitApplication(
            project_id=project_id,
            requirement_id=rid,
            attempt=max((a.attempt for a in same), default=0) + 1,
            kind=kind,
            parent_permit_id=parent.id if parent else None,
            discharges_condition_ids=cond_ids,
            authority_name=data.get("authority_name") or "",
            authority_reference=data.get("authority_reference") or "",
            review_cycle_ids=[str(v) for v in data.get("review_cycle_ids") or []],
            submission_id=_uuid(data.get("submission_id")),
            cde_container_id=_uuid(data.get("cde_container_id")),
            created_by=actor_id,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(app)
        except IntegrityError as exc:
            raise conflict("concurrent_application") from exc
        await self._audit(actor_id, "permit_application", app.id, "application_created", metadata={"kind": kind})
        return app

    async def update_application(
        self, project_id: uuid.UUID, aid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PermitApplication:
        app = await self.repo.get_application(project_id, aid, lock=True)
        if app is None:
            raise not_found("application_not_found")
        if app.status in ("decided", "withdrawn") and set(data) - {"appeal_note"}:
            raise conflict("application_closed")
        for v in data.get("review_cycle_ids") or []:
            await self._check_link("review_cycle", v, project_id)
        await self._check_link("submission", data.get("submission_id"), project_id)
        await self._check_link("cde_container", data.get("cde_container_id"), project_id)
        for key, value in data.items():
            if key == "review_cycle_ids":
                value = [str(v) for v in value or []]
            elif key in ("submission_id", "cde_container_id"):
                value = _uuid(value)
            setattr(app, key, value)
        await self.session.flush()
        await self._audit(actor_id, "permit_application", app.id, "application_updated", metadata=_jsonable(data))
        return app

    async def transition_application(
        self,
        project_id: uuid.UUID,
        aid: uuid.UUID,
        target: str,
        *,
        actor_id: uuid.UUID,
        actor_role: str | None,
        on_date: date | None,
        today: date,
        reason: str | None = None,
    ) -> PermitApplication:
        """User transitions; ``decided`` only by recording a decision."""
        if target not in USER_TARGETS:
            raise PermitError("transition_not_allowed", 422)
        roadmap = await self.require_roadmap(project_id)
        app = await self.repo.get_application(project_id, aid, lock=True)
        if app is None:
            raise not_found("application_not_found")
        when = on_date or today
        if target == "submitted":
            await self._admit_submit(roadmap, app, actor_role)
            app.submitted_at = app.submitted_at or when
            app.received_at = app.received_at or when
        if target == "validated":
            app.validated_at = when
        if target == "internal_review" and roadmap.approval_route_id is not None:
            await self._start_internal_release(roadmap, app, actor_id)
        previous = app.status
        await self._fsm(APPLICATION_FSM, app, target, actor_id, reason)
        if app.kind == "discharge_of_conditions":
            await self._discharge_app_moved(app, previous, target, actor_id)
        await self.session.flush()
        if target == "submitted":
            self._publish(
                "application.submitted",
                {
                    "project_id": str(project_id),
                    "application_id": str(app.id),
                    "requirement_id": str(app.requirement_id),
                },
            )
        return app

    async def _admit_submit(self, roadmap: PermitRoadmap, app: PermitApplication, actor_role: str | None) -> None:
        """Rule 3 (dependencies) and lead decision k (optional internal release)."""
        if app.kind in ("new", "early_start"):
            snap = await self.state_snapshot(app.project_id)
            unmet = rm.unmet_dependencies(str(app.requirement_id), snap["edges"], snap["states"], snap["submitted"])
            if unmet:
                raise PermitError("dependency_not_met", 422, detail=",".join(unmet))
        if roadmap.internal_review and app.status == "preparing":
            raise conflict("internal_review_required")
        if app.status == "internal_review" and app.approval_instance_id is not None:
            from app.modules.approval_routes.models import Instance

            inst = await self.session.get(Instance, app.approval_instance_id)
            if inst is None or inst.status != "approved":
                raise conflict("internal_release_pending")
        elif app.status == "internal_review" and not _is_manager(actor_role):
            raise forbidden("release_needs_manager")

    async def _start_internal_release(self, roadmap: PermitRoadmap, app: PermitApplication, actor_id: Any) -> None:
        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        inst = await ApprovalRouteService(self.session).start_instance(
            InstanceCreate(route_id=roadmap.approval_route_id, target_kind=TARGET_KIND, target_id=app.id),
            started_by=_uuid(actor_id),
        )
        app.approval_instance_id = inst.id

    async def apply_route_verdict(self, aid: uuid.UUID, *, instance_id: Any, verdict: str) -> None:
        """An internal release rejected or cancelled sends the application back to preparation."""
        app = (
            await self.session.execute(select(PermitApplication).where(PermitApplication.id == aid).with_for_update())
        ).scalar_one_or_none()
        if app is None or app.status != "internal_review" or _s(app.approval_instance_id) != _s(instance_id):
            return
        if verdict in ("rejected", "cancelled"):
            await self._fsm(APPLICATION_FSM, app, "preparing", None, f"internal release {verdict}")
            app.approval_instance_id = None
            await self.session.flush()

    async def _discharge_app_moved(self, app: PermitApplication, previous: str, target: str, actor_id: Any) -> None:
        conds = [
            await self.repo.get_condition(app.project_id, _uuid(c), lock=True) for c in app.discharges_condition_ids
        ]
        for c in conds:
            if c is None:
                continue
            if target == "submitted" and c.status in ("open", "evidence_submitted"):
                await self._fsm(CONDITION_FSM, c, "discharge_applied", actor_id, "discharge applied for")
            elif target == "withdrawn" and c.status == "discharge_applied":
                await self._fsm(CONDITION_FSM, c, "open", actor_id, "discharge application withdrawn")

    async def add_clock_event(
        self, project_id: uuid.UUID, aid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> ClockEventRow:
        roadmap = await self.require_roadmap(project_id)
        app = await self.repo.get_application(project_id, aid, lock=True)
        if app is None:
            raise not_found("application_not_found")
        if app.status in ("planned", "preparing", "internal_review", "decided", "withdrawn"):
            raise conflict("clock_not_running")
        req = await self.repo.get_requirement(project_id, app.requirement_id)
        ptype = self._type(await self._types(roadmap), req.permit_type_code)
        spec = self._spec(ptype, req.clock_variant)
        existing = [
            ClockEvent(e.kind, e.event_date, e.period, e.unit, e.reason)
            for e in await self.repo.list_clock_events(project_id, aid)
        ]
        new = ClockEvent(data["kind"], data["at"], data.get("period"), data.get("unit"), data.get("reason") or "")
        try:
            check_stop(spec, existing, new)
            check_extension(spec, existing, new)
        except ClockError as exc:
            raise PermitError(exc.code, 422) from exc
        row = await self.repo.add(
            ClockEventRow(
                project_id=project_id,
                application_id=aid,
                kind=new.kind,
                event_date=new.at,
                period=new.period,
                unit=new.unit,
                reason=new.reason,
                created_by=actor_id,
            )
        )
        if new.kind == "stop" and app.status in ("submitted", "validated", "under_review"):
            await self._fsm(APPLICATION_FSM, app, "info_requested", actor_id, new.reason or "clock stopped")
        elif new.kind == "resume" and app.status == "info_requested":
            await self._fsm(APPLICATION_FSM, app, "under_review", actor_id, "clock resumed")
        await self._audit(actor_id, "permit_application", aid, f"clock_{new.kind}", metadata=_jsonable(data))
        return row

    # ── decisions (rules 7, 8, 10, 13, 14) ─────────────────────────────────

    async def record_decision(
        self, project_id: uuid.UUID, aid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID, today: date
    ) -> dict[str, Any]:
        roadmap = await self.require_roadmap(project_id)
        app = await self.repo.get_application(project_id, aid, lock=True)
        if app is None:
            raise not_found("application_not_found")
        if app.status == "decided":
            raise conflict("already_decided")
        if app.status not in DECIDABLE:
            raise conflict("application_not_decidable")
        outcome = data["outcome"]
        if outcome not in DECISION_OUTCOMES:
            raise PermitError("outcome_invalid", 422)
        req = await self.repo.get_requirement(project_id, app.requirement_id, lock=True)
        types = await self._types(roadmap)
        ptype = self._type(types, req.permit_type_code)
        conds_in = list(data.get("conditions") or [])
        await self._check_link("cde_revision", data.get("document_revision_id"), project_id)
        for raw in data.get("scope_activity_ids") or []:
            await self._check_link("activity", raw, project_id)
        if outcome == "granted_with_conditions" and not conds_in and not data.get("conditions_pending"):
            raise PermitError("conditional_grant_needs_conditions", 422)
        if outcome == "partially_granted" and not (data.get("scope_note") or "").strip():
            raise PermitError("partial_grant_needs_scope", 422)
        if outcome == "deemed_granted":
            wd = await self.working_day(project_id)
            clock = await self.clock_of(app, ptype, req.clock_variant, today, wd)
            if clock["deemed_proposal"] is None:
                raise PermitError("deemed_not_available", 422)
            if clock["deemed_requires_notice"] and not data.get("document_revision_id"):
                raise PermitError("deemed_needs_notice", 422)
        early = app.kind == "early_start" or ptype.scope == "early_start"
        if early and outcome in NOT_REFUSED and not data.get("conditions_pending"):
            purposes = {c.get("purpose") for c in conds_in if c.get("kind") == "obligation"}
            needed = {"restoration", "security"} if ptype.security_possible else {"restoration"}
            if not needed <= purposes:
                raise PermitError("early_start_needs_restoration_and_security", 422, detail=",".join(sorted(needed)))
        for c in conds_in:
            _validate_condition_input(c)
        snapshot = {
            "outcome": outcome,
            "decision_date": data["decision_date"],
            "reference": data.get("reference") or "",
            "scope_note": data.get("scope_note") or "",
            "conditions": [{"number": c["number"], "text": c["text"]} for c in conds_in],
        }
        decision = PermitDecision(
            project_id=project_id,
            application_id=aid,
            revision=1,
            outcome=outcome,
            decision_date=data["decision_date"],
            served_date=data.get("served_date"),
            reference=data.get("reference") or "",
            scope_note=data.get("scope_note") or "",
            scope_activity_ids=[str(v) for v in data.get("scope_activity_ids") or []],
            conditions_pending=bool(data.get("conditions_pending")),
            appeal_deadline=data.get("appeal_deadline"),
            document_revision_id=_uuid(data.get("document_revision_id")),
            content_hash=_hash(snapshot),
            deemed=outcome == "deemed_granted",
            decided_by=actor_id,
            snapshot=snapshot,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(decision)
        except IntegrityError as exc:
            raise conflict("concurrent_decision") from exc
        await self._fsm(APPLICATION_FSM, app, "decided", actor_id, f"decision {outcome}")
        result: dict[str, Any] = {"decision": decision, "permit": None, "follow_up_requirement": None}
        if outcome in NOT_REFUSED and app.kind in PERMIT_KINDS:
            result["permit"] = await self._grant(app, req, ptype, decision, conds_in, data, actor_id)
        elif outcome in NOT_REFUSED and app.kind == "extension_of_validity":
            await self._extend(app, ptype, actor_id)
        if app.kind == "discharge_of_conditions":
            await self._apply_discharge_decision(app, decision, data, actor_id)
        if outcome == "partially_granted" and app.kind in ("new", "early_start"):
            result["follow_up_requirement"] = await self.repo.add(
                PermitRequirement(
                    project_id=project_id,
                    permit_type_code=req.permit_type_code,
                    title=f"{req.title or req.permit_type_code} (remaining scope)"[:255],
                    applicant_role=req.applicant_role,
                    applicant_source=req.applicant_source,
                    responsible_user_id=req.responsible_user_id,
                    governance_area_code=req.governance_area_code,
                    follow_up_of_id=req.id,
                    sort_order=req.sort_order + 1,
                )
            )
        if outcome == "refused":
            result["next"] = ["resubmit", "appeal_note"]
        await self.session.flush()
        await self._audit(
            actor_id,
            "permit_application",
            aid,
            "decision_recorded",
            metadata={"outcome": outcome, "decision_id": str(decision.id)},
        )
        self._publish(
            "decision.recorded",
            {"project_id": str(project_id), "application_id": str(aid), "outcome": outcome},
        )
        return result

    async def _grant(
        self,
        app: PermitApplication,
        req: PermitRequirement,
        ptype: PermitType,
        decision: PermitDecision,
        conds_in: list[dict[str, Any]],
        data: dict[str, Any],
        actor_id: Any,
    ) -> Permit:
        served = decision.served_date or decision.decision_date
        security = data.get("security_amount")
        permit = await self.repo.add(
            Permit(
                project_id=app.project_id,
                requirement_id=req.id,
                application_id=app.id,
                decision_id=decision.id,
                permit_type_code=req.permit_type_code,
                scope="partial" if decision.outcome == "partially_granted" else ptype.scope,
                status="in_force",
                reference=decision.reference,
                revocable=ptype.revocable,
                security_amount=Decimal(str(security)) if security not in (None, "") else None,
                security_currency=(data.get("security_currency") or "").upper(),
                valid_until=cnd.valid_until(served, None, ptype.validity),
            )
        )
        if app.kind in ("variation", "amendment_non_material") and app.parent_permit_id is not None:
            await self._vary(app, permit, conds_in, data.get("removed_condition_numbers") or [], actor_id)
        else:
            for c in conds_in:
                await self._add_condition(permit, c, decision_id=decision.id, actor_id=actor_id)
        self._publish(
            "permit.state_changed",
            {"project_id": str(app.project_id), "permit_id": str(permit.id), "state": "in_force"},
        )
        return permit

    async def _vary(
        self, app: PermitApplication, permit: Permit, conds_in: list[dict[str, Any]], removed: list[str], actor_id: Any
    ) -> None:
        """Rule 14: supersede the parent permit and its conditions, carry forward the rest."""
        parent = await self.repo.get_permit(app.project_id, app.parent_permit_id, lock=True)
        old_rows = await self.repo.conditions_of_permit(app.project_id, parent.id)
        old = [cnd.OldCondition(str(c.id), c.number, c.text, c.kind, c.trigger, c.status) for c in old_rows]
        new = [cnd.NewCondition(c["number"], c["text"], c["kind"], c["trigger"]) for c in conds_in]
        by_number = {c["number"]: c for c in conds_in}
        old_by_id = {str(c.id): c for c in old_rows}
        for carried in cnd.carry_forward(old, new, removed):
            src = old_by_id.get(carried.original_id or "")
            base = by_number.get(carried.number) or (_condition_payload(src) if src is not None else {})
            row = await self._add_condition(
                permit,
                {
                    **base,
                    "number": carried.number,
                    "text": carried.text,
                    "kind": carried.kind,
                    "trigger": carried.trigger,
                },
                decision_id=permit.decision_id,
                actor_id=actor_id,
                original_id=_uuid(carried.original_id),
            )
            if carried.keep_state and src is not None:
                row.status = carried.keep_state
                for ev in await self.repo.list_evidence(app.project_id, src.id):
                    await self.repo.add(
                        ConditionEvidence(
                            project_id=app.project_id,
                            condition_id=row.id,
                            kind=ev.kind,
                            ref_id=ev.ref_id,
                            content_hash=ev.content_hash,
                            note=ev.note,
                            added_by=ev.added_by,
                        )
                    )
        for c in old_rows:
            if c.status != "superseded" and c.status != "waived":
                await self._fsm(CONDITION_FSM, c, "superseded", actor_id, "permit varied")
        if parent.status in ("in_force", "suspended"):
            await self._fsm(PERMIT_FSM, parent, "superseded", actor_id, "varied")
        parent.superseded_by_id = permit.id
        permit.valid_until = parent.valid_until
        permit.start_notified_at = parent.start_notified_at

    async def _extend(self, app: PermitApplication, ptype: PermitType, actor_id: Any) -> None:
        parent = await self.repo.get_permit(app.project_id, app.parent_permit_id, lock=True)
        if parent.valid_until is None:
            return
        new_until = cnd.extended_until(parent.valid_until, ptype.validity)
        if new_until is None:
            raise PermitError("validity_extension_not_in_catalogue", 422)
        parent.valid_until = new_until
        if parent.status == "lapsed":
            await self._fsm(PERMIT_FSM, parent, "in_force", actor_id, "validity extended")
        await self._audit(
            actor_id, "authority_permit", parent.id, "validity_extended", metadata={"until": str(new_until)}
        )

    async def _apply_discharge_decision(
        self, app: PermitApplication, decision: PermitDecision, data: dict[str, Any], actor_id: Any
    ) -> None:
        """Rule 13: a decided discharge application discharges each listed condition it names."""
        listed = list(app.discharges_condition_ids)
        granted = decision.outcome in NOT_REFUSED
        chosen = {str(c) for c in (data.get("discharged_condition_ids") or listed)} if granted else set()
        if chosen - set(listed):
            raise PermitError("condition_not_in_application", 422)
        mode = "deemed_discharged" if decision.deemed else "authority_discharged"
        for raw in listed:
            c = await self.repo.get_condition(app.project_id, _uuid(raw), lock=True)
            if c is None or c.status != "discharge_applied":
                continue
            if raw in chosen:
                await self._fsm(CONDITION_FSM, c, "discharged", actor_id, mode)
                await self.repo.add(
                    ConditionDischarge(
                        project_id=app.project_id,
                        condition_id=c.id,
                        mode=mode,
                        decided_by=actor_id,
                        discharge_application_id=app.id,
                        discharged_on=decision.decision_date,
                        document_revision_id=decision.document_revision_id,
                        evidence_snapshot=await self._evidence_snapshot(c),
                    )
                )
                self._publish(
                    "condition.discharged",
                    {"project_id": str(app.project_id), "condition_id": str(c.id), "mode": mode},
                )
            else:
                await self._fsm(CONDITION_FSM, c, "open", actor_id, "discharge refused")

    async def deemed_status(self, project_id: uuid.UUID, aid: uuid.UUID, today: date) -> dict[str, Any]:
        """Rule 7: the deemed outcome the module PROPOSES; it takes effect only through ``record_decision``."""
        roadmap = await self.require_roadmap(project_id)
        app = await self.repo.get_application(project_id, aid)
        if app is None:
            raise not_found("application_not_found")
        req = await self.repo.get_requirement(project_id, app.requirement_id)
        ptype = self._type(await self._types(roadmap), req.permit_type_code)
        clock = await self.clock_of(app, ptype, req.clock_variant, today, await self.working_day(project_id))
        return {
            "application_id": str(aid),
            "proposal": clock["deemed_proposal"],
            "requires_notice": clock["deemed_requires_notice"],
            "clock": clock,
        }

    # ── permits ────────────────────────────────────────────────────────────

    async def notify_start(
        self, project_id: uuid.UUID, pid: uuid.UUID, on_date: date, *, actor_id: uuid.UUID
    ) -> Permit:
        """Rule 9: a start notice ends the not-started lapse clock."""
        permit = await self.repo.get_permit(project_id, pid, lock=True)
        if permit is None:
            raise not_found("permit_not_found")
        if permit.status != "in_force":
            raise conflict("permit_not_in_force")
        permit.start_notified_at = on_date
        permit.valid_until = None
        await self.session.flush()
        await self._audit(actor_id, "authority_permit", pid, "start_notified", metadata={"date": on_date.isoformat()})
        return permit

    async def transition_permit(
        self, project_id: uuid.UUID, pid: uuid.UUID, target: str, *, actor_id: uuid.UUID, reason: str | None
    ) -> Permit:
        if target not in ("suspended", "in_force", "revoked", "expired", "lapsed"):
            raise PermitError("transition_not_allowed", 422)
        permit = await self.repo.get_permit(project_id, pid, lock=True)
        if permit is None:
            raise not_found("permit_not_found")
        if target == "in_force" and permit.status == "lapsed":
            raise PermitError("lapsed_needs_extension_decision", 422)
        await self._fsm(PERMIT_FSM, permit, target, actor_id, reason)
        await self.session.flush()
        self._publish("permit.state_changed", {"project_id": str(project_id), "permit_id": str(pid), "state": target})
        return permit

    # ── conditions ─────────────────────────────────────────────────────────

    async def _add_condition(
        self,
        permit: Permit,
        c: dict[str, Any],
        *,
        decision_id: Any,
        actor_id: Any,
        source: str = "manual",
        confirmed: bool = True,
        original_id: uuid.UUID | None = None,
    ) -> PermitCondition:
        _validate_condition_input(c)
        await self._check_link("gate_condition", c.get("gate_condition_id"), permit.project_id)
        row = PermitCondition(
            project_id=permit.project_id,
            permit_id=permit.id,
            number=str(c["number"]).strip(),
            text=c["text"],
            text_hash=cnd.text_hash(c["text"]),
            kind=c["kind"],
            national_kind=c.get("national_kind") or "",
            trigger=c.get("trigger") or "",
            stage_ref=c.get("stage_ref") or "",
            event_text=c.get("event_text") or "",
            due_date=c.get("due_date"),
            topic=c.get("topic") or "other",
            purpose=c.get("purpose") or "",
            owner_user_id=_uuid(c.get("owner_user_id")),
            responsible_party=c.get("responsible_party") or "",
            requires_authority_approval=bool(c.get("requires_authority_approval")),
            evidence_required=c.get("evidence_required") or "",
            hse_override=c.get("hse_relevant"),
            source=source,
            confidence=Decimal(str(c["confidence"])) if c.get("confidence") is not None else None,
            text_span=c.get("text_span") or "",
            confirmed=confirmed,
            gate_condition_id=_uuid(c.get("gate_condition_id")),
            original_id=original_id,
            decision_id=_uuid(decision_id),
            created_by=_uuid(actor_id),
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(row)
        except IntegrityError as exc:
            raise conflict("condition_number_taken") from exc
        if confirmed:
            self._publish(
                "condition.created",
                {"project_id": str(permit.project_id), "condition_id": str(row.id), "permit_id": str(permit.id)},
            )
            await self._notify(
                row.owner_user_id,
                "condition_assigned",
                "permit_condition",
                row.id,
                {"project_id": str(permit.project_id), "number": row.number},
            )
        return row

    async def create_condition(
        self, project_id: uuid.UUID, pid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> PermitCondition:
        permit = await self.repo.get_permit(project_id, pid)
        if permit is None:
            raise not_found("permit_not_found")
        row = await self._add_condition(permit, data, decision_id=permit.decision_id, actor_id=actor_id)
        await self._audit(actor_id, "permit_condition", row.id, "condition_created")
        return row

    async def complete_register(self, project_id: uuid.UUID, did: uuid.UUID, *, actor_id: uuid.UUID) -> PermitDecision:
        """Conditions announced as "to follow" are all entered: the register is complete again (rule 8)."""
        dec = await self.repo.get_decision(project_id, did)
        if dec is None:
            raise not_found("decision_not_found")
        if not dec.conditions_pending:
            return dec
        permit = (await self.session.execute(select(Permit).where(Permit.decision_id == dec.id))).scalar_one_or_none()
        if permit is not None and dec.outcome == "granted_with_conditions":
            conds = await self.repo.conditions_of_permit(project_id, permit.id)
            if not [c for c in conds if c.confirmed]:
                raise PermitError("conditional_grant_needs_conditions", 422)
        # The decision row stays immutable in substance; only the register flag is cleared.
        dec.conditions_pending = False
        await self.session.flush()
        await self._audit(actor_id, "permit_decision", did, "register_completed")
        return dec

    async def _owned_condition(
        self, project_id: uuid.UUID, cid: uuid.UUID, actor_id: uuid.UUID, role: str | None, *, lock: bool = True
    ) -> PermitCondition:
        c = await self.repo.get_condition(project_id, cid, lock=lock)
        if c is None:
            raise not_found("condition_not_found")
        if not _is_manager(role) and c.owner_user_id not in (None, actor_id):
            raise forbidden("not_condition_owner")
        return c

    async def update_condition(
        self,
        project_id: uuid.UUID,
        cid: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> PermitCondition:
        c = await self._owned_condition(project_id, cid, actor_id, role)
        if c.status in ("superseded", "waived"):
            raise conflict("condition_closed")
        if "text" in data and c.status not in ("open",):
            raise conflict("condition_text_frozen")
        if data.get("gate_condition_id"):
            await self._check_link("gate_condition", data["gate_condition_id"], project_id)
        merged_input = {**_condition_payload(c), **{k: v for k, v in data.items() if v is not None}}
        _validate_condition_input(merged_input)
        before = _condition_payload(c)
        for key, value in data.items():
            if key in ("owner_user_id", "gate_condition_id"):
                value = _uuid(value)
            if key == "hse_relevant":
                key = "hse_override"
            setattr(c, key, value)
        if "text" in data:
            c.text_hash = cnd.text_hash(c.text)
        await self.session.flush()
        await self._audit(
            actor_id,
            "permit_condition",
            cid,
            "condition_updated",
            before_state=_jsonable(before),
            metadata=_jsonable(data),
        )
        if "owner_user_id" in data and data["owner_user_id"]:
            await self._notify(
                c.owner_user_id,
                "condition_assigned",
                "permit_condition",
                c.id,
                {"project_id": str(project_id), "number": c.number},
            )
        return c

    async def assign_owner(
        self, project_id: uuid.UUID, ids: list[uuid.UUID], owner: uuid.UUID, *, actor_id: uuid.UUID
    ) -> list[PermitCondition]:
        out = []
        for cid in ids:
            out.append(
                await self.update_condition(
                    project_id, cid, {"owner_user_id": owner}, actor_id=actor_id, role="manager"
                )
            )
        return out

    async def add_evidence(
        self,
        project_id: uuid.UUID,
        cid: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> ConditionEvidence:
        c = await self._owned_condition(project_id, cid, actor_id, role)
        kind = data["kind"]
        if kind not in EVIDENCE_KINDS:
            raise PermitError("evidence_kind_invalid", 422)
        if c.status in ("superseded", "waived", "discharged"):
            raise conflict("condition_closed")
        ref = str(data.get("ref_id") or "")
        content_hash = ""
        if kind in ("cde_revision", "inspection", "commissioning_item"):
            await self._check_link(kind, ref, project_id)
            if kind == "cde_revision":
                from app.modules.cde.models import DocumentRevision

                rev = await self.session.get(DocumentRevision, _uuid(ref))
                content_hash = (rev.content_hash or "") if rev else ""
        elif kind == "discharge_decision":
            dec = await self.repo.get_decision(project_id, _uuid(ref))
            if dec is None:
                raise not_found("decision_not_found")
            content_hash = dec.content_hash
        elif not ref and not (data.get("note") or "").strip():
            raise PermitError("evidence_empty", 422)
        row = await self.repo.add(
            ConditionEvidence(
                project_id=project_id,
                condition_id=cid,
                kind=kind,
                ref_id=ref,
                content_hash=content_hash,
                note=data.get("note") or "",
                added_by=actor_id,
            )
        )
        await self._audit(actor_id, "permit_condition", cid, "evidence_added", metadata={"kind": kind, "ref": ref})
        return row

    async def remove_evidence(
        self, project_id: uuid.UUID, cid: uuid.UUID, eid: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> None:
        c = await self._owned_condition(project_id, cid, actor_id, role)
        if c.status == "discharged":
            raise conflict("condition_closed")
        ev = await self.repo.get_evidence(project_id, eid)
        if ev is None or ev.condition_id != cid:
            raise not_found("evidence_not_found")
        await self.session.delete(ev)
        await self.session.flush()
        if c.status == "evidence_submitted" and not await self.repo.list_evidence(project_id, cid):
            await self._fsm(CONDITION_FSM, c, "open", actor_id, "evidence withdrawn")
        await self._audit(actor_id, "permit_condition", cid, "evidence_removed", metadata={"evidence_id": str(eid)})

    async def submit_evidence(
        self, project_id: uuid.UUID, cid: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> PermitCondition:
        c = await self._owned_condition(project_id, cid, actor_id, role)
        if not await self.repo.list_evidence(project_id, cid):
            raise PermitError("evidence_required", 422)
        await self._fsm(CONDITION_FSM, c, "evidence_submitted", actor_id, "evidence submitted")
        await self.session.flush()
        return c

    async def _evidence_snapshot(self, c: PermitCondition) -> list[dict[str, Any]]:
        return [
            {"id": str(e.id), "kind": e.kind, "ref_id": e.ref_id, "content_hash": e.content_hash}
            for e in await self.repo.list_evidence(c.project_id, c.id)
        ]

    async def discharge(
        self,
        project_id: uuid.UUID,
        cid: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        today: date,
    ) -> ConditionDischarge:
        """Rule 13 and lead decision j. ``self_certified`` is always four-eyes: owner != verifier."""
        c = await self.repo.get_condition(project_id, cid, lock=True)
        if c is None:
            raise not_found("condition_not_found")
        if not c.confirmed:
            raise conflict("condition_not_confirmed")
        mode = data["mode"]
        when = data.get("on_date") or today
        doc = _uuid(data.get("document_revision_id"))
        if mode == "self_certified":
            if c.requires_authority_approval:
                raise PermitError("authority_discharge_required", 422)
            if c.owner_user_id is None:
                raise PermitError("condition_needs_owner", 422)
            if c.owner_user_id == actor_id:
                raise forbidden("verifier_is_owner")
            if c.status != "evidence_submitted":
                raise conflict("evidence_not_submitted")
            target = "discharged"
        elif mode in ("not_triggered", "waived_by_authority"):
            if mode == "waived_by_authority" and doc is None:
                raise PermitError("waiver_needs_document", 422)
            if c.owner_user_id == actor_id:
                raise forbidden("verifier_is_owner")
            target = "not_triggered" if mode == "not_triggered" else "waived"
        else:
            # authority_discharged / deemed_discharged come only from a decided discharge application.
            raise PermitError("discharge_needs_application", 422)
        await self._check_link("cde_revision", doc, project_id)
        await self._fsm(CONDITION_FSM, c, target, actor_id, mode)
        row = await self.repo.add(
            ConditionDischarge(
                project_id=project_id,
                condition_id=cid,
                mode=mode,
                decided_by=c.owner_user_id if mode == "self_certified" else actor_id,
                verifier_user_id=actor_id,
                discharged_on=when,
                document_revision_id=doc,
                note=data.get("note") or "",
                evidence_snapshot=await self._evidence_snapshot(c),
            )
        )
        await self._audit(actor_id, "permit_condition", cid, "condition_discharged", metadata={"mode": mode})
        self._publish("condition.discharged", {"project_id": str(project_id), "condition_id": str(cid), "mode": mode})
        self._publish("readiness.changed", {"project_id": str(project_id)})
        return row

    async def ongoing(
        self,
        project_id: uuid.UUID,
        cid: uuid.UUID,
        target: str,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> PermitCondition:
        """Rule 16: an ongoing condition is in compliance or in breach; a breach never closes itself."""
        c = await self._owned_condition(project_id, cid, actor_id, role) if target != "breach" else None
        if c is None:
            c = await self.repo.get_condition(project_id, cid, lock=True)
            if c is None:
                raise not_found("condition_not_found")
        if c.trigger != "ongoing":
            raise PermitError("condition_not_ongoing", 422)
        if target == "breach":
            kind = data.get("ref_kind") or "manual"
            if kind not in BREACH_REF_KINDS:
                raise PermitError("breach_ref_invalid", 422)
            if kind != "manual":
                await self._check_link(kind, data.get("ref_id"), project_id)
            c.breach_ref_kind, c.breach_ref_id = kind, _uuid(data.get("ref_id"))
            c.breach_note = data.get("note") or ""
        await self._fsm(CONDITION_FSM, c, target, actor_id, data.get("note"))
        await self.session.flush()
        await self._audit(actor_id, "permit_condition", cid, f"condition_{target}", metadata=_jsonable(data))
        if target == "breach":
            self._publish("condition.breach", {"project_id": str(project_id), "condition_id": str(cid)})
            await self._notify(
                c.owner_user_id, "condition_breach", "permit_condition", cid, {"project_id": str(project_id)}
            )
        return c

    async def propose_conditions(
        self,
        project_id: uuid.UUID,
        pid: uuid.UUID,
        proposals: list[dict[str, Any]],
        *,
        actor_id: uuid.UUID,
    ) -> list[PermitCondition]:
        """Rule 15: AI-extracted proposals, stored unconfirmed; they count nowhere until a human confirms."""
        permit = await self.repo.get_permit(project_id, pid)
        if permit is None:
            raise not_found("permit_not_found")
        out = []
        for p in proposals:
            if p.get("confidence") is None:
                raise PermitError("proposal_needs_confidence", 422)
            out.append(
                await self._add_condition(
                    permit, p, decision_id=permit.decision_id, actor_id=actor_id, source="ai_extracted", confirmed=False
                )
            )
        await self._audit(actor_id, "authority_permit", pid, "conditions_proposed", metadata={"count": len(out)})
        return out

    async def confirm_proposal(
        self, project_id: uuid.UUID, cid: uuid.UUID, accept: bool, *, actor_id: uuid.UUID
    ) -> PermitCondition | None:
        c = await self.repo.get_condition(project_id, cid, lock=True)
        if c is None:
            raise not_found("condition_not_found")
        if c.confirmed:
            raise conflict("condition_already_confirmed")
        if not accept:
            await self.session.delete(c)
            await self.session.flush()
            await self._audit(actor_id, "permit_condition", cid, "proposal_rejected")
            return None
        c.confirmed = True
        await self.session.flush()
        await self._audit(actor_id, "permit_condition", cid, "proposal_confirmed")
        self._publish("condition.created", {"project_id": str(project_id), "condition_id": str(cid)})
        return c

    async def condition_to_requirement(
        self, project_id: uuid.UUID, cid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> dict[str, Any]:
        """Rule 23: a measurable limit becomes a ``requirements`` row; the condition keeps a soft link."""
        from app.modules.requirements.models import RequirementSet
        from app.modules.requirements.schemas import RequirementCreate, RequirementSetCreate
        from app.modules.requirements.service import RequirementsService

        c = await self.repo.get_condition(project_id, cid, lock=True)
        if c is None:
            raise not_found("condition_not_found")
        if c.requirement_id is not None:
            raise conflict("condition_already_linked")
        permit = await self.repo.get_permit(project_id, c.permit_id)
        svc = RequirementsService(self.session)
        set_name = "Permit conditions"
        existing = (
            (
                await self.session.execute(
                    select(RequirementSet).where(
                        RequirementSet.project_id == project_id, RequirementSet.name == set_name
                    )
                )
            )
            .scalars()
            .first()
        )
        rset = existing or await svc.create_set(
            RequirementSetCreate(project_id=project_id, name=set_name, source_type="manual"), user_id=str(actor_id)
        )
        phase = {"before_occupation": "handover", "after_completion": "operation", "ongoing": "construction"}.get(
            c.trigger, "construction"
        )
        req = await svc.add_requirement(
            rset.id,
            RequirementCreate(
                entity=data["entity"],
                attribute=data["attribute"],
                constraint_type=data.get("constraint_type") or "equals",
                constraint_value=str(data.get("constraint_value") or ""),
                unit=data.get("unit") or "",
                source_ref=f"{permit.reference or permit.permit_type_code} / {c.number}"[:500],
                originator_role="authority",
                phase=phase,
            ),
            user_id=str(actor_id),
        )
        c.requirement_id = req.id
        await self.session.flush()
        await self._audit(
            actor_id, "permit_condition", cid, "requirement_created", metadata={"requirement": str(req.id)}
        )
        return {"condition_id": str(cid), "requirement_id": str(req.id), "requirement_set_id": str(rset.id)}

    # ── readiness (rules 11, 12, 19, 20) ───────────────────────────────────

    async def views(self, project_id: uuid.UUID, today: date) -> dict[str, Any]:
        """Pure-function inputs built once from the rows."""
        roadmap = await self.repo.get_roadmap(project_id)
        types = await self._types(roadmap) if roadmap else {}
        snap = await self.state_snapshot(project_id)
        tl = {r["requirement_id"]: r for r in (await self.timeline(project_id, today))["items"]} if roadmap else {}
        reqs = []
        for r in snap["requirements"]:
            t = types.get(r.permit_type_code)
            row = tl.get(str(r.id), {})
            reqs.append(
                cnd.ReqView(
                    str(r.id),
                    r.permit_type_code,
                    t.category if t else "other",
                    t.scope if t else "full",
                    tuple(t.enables) if t else (),
                    snap["states"].get(str(r.id), "not_started"),
                    r.applicable,
                    bool(row.get("schedule_conflict")),
                    r.conflict_accepted,
                    str(r.id) in snap["conditions_pending"],
                    r.title,
                )
            )
        permits_rows = await self.repo.list_permits(project_id)
        decisions = {str(d.id): d for d in snap["decisions"].values()}
        permits = []
        for p in permits_rows:
            t = types.get(p.permit_type_code)
            dec = decisions.get(str(p.decision_id))
            permits.append(
                cnd.PermitView(
                    str(p.id),
                    str(p.requirement_id),
                    p.permit_type_code,
                    t.category if t else "other",
                    p.scope,
                    p.status,
                    tuple(t.enables) if t else (),
                    tuple(dec.scope_activity_ids) if dec else (),
                )
            )
        conds = [_cond_view(c) for c in await self.repo.list_conditions(project_id)]
        return {"roadmap": roadmap, "reqs": reqs, "permits": permits, "conds": conds, "snap": snap}

    async def readiness(self, project_id: uuid.UUID, gate: str, today: date) -> dict[str, Any]:
        v = await self.views(project_id, today)
        if v["roadmap"] is None:
            return {"gate": gate, "status": "no_roadmap", "items": []}
        if gate == "start":
            out = cnd.start_readiness(v["reqs"], v["permits"], v["conds"]).as_dict()
            needing = {
                str(r.needed_by_activity_id): str(r.id) for r in v["snap"]["requirements"] if r.needed_by_activity_id
            }
            scopes = {p.requirement_id: p.scope_activity_ids for p in v["permits"] if p.scope == "partial"}
            for p in v["permits"]:
                if p.scope == "partial":
                    for a in p.scope_activity_ids:
                        needing.setdefault(a, p.requirement_id)
            out["activities"] = cnd.blocked_activities(needing, scopes, v["snap"]["states"])
            return out
        if gate == "handover":
            return cnd.handover_readiness(v["reqs"], v["permits"], v["conds"]).as_dict()
        if gate == "register":
            return cnd.register_readiness(v["reqs"], v["conds"]).as_dict()
        if gate in cnd.PHASE_ENABLES or gate == "roadmap":
            return cnd.roadmap_readiness(v["reqs"], "construction" if gate == "roadmap" else gate).as_dict()
        raise PermitError("gate_invalid", 422)

    # ── overdue and lapse sweep (rules 9, 17) ──────────────────────────────

    async def escalate(self, project_id: uuid.UUID, *, today: date, actor_id: uuid.UUID | None) -> dict[str, Any]:
        """Notify owners of newly overdue conditions, escalate to the area owner, lapse unstarted permits."""
        from app.modules.project_governance.models import GovernanceArea
        from app.modules.projects.models import Project

        roadmap = await self.require_roadmap(project_id)
        project = await self.session.get(Project, project_id)
        pm = getattr(project, "owner_id", None)
        now = datetime.now(UTC)
        notified, escalated, lapsed = [], [], []
        for c in await self.repo.list_conditions(project_id):
            view = _cond_view(c)
            if not cnd.is_overdue(view, today):
                continue
            ctx = {"project_id": str(project_id), "number": c.number, "due_date": _iso(c.due_date)}
            if c.overdue_notified_at is None:
                c.overdue_notified_at = now
                for uid in {c.owner_user_id, pm} - {None}:
                    await self._notify(uid, "condition_overdue", "permit_condition", c.id, ctx)
                self._publish("condition.overdue", {"project_id": str(project_id), "condition_id": str(c.id)})
                notified.append(str(c.id))
            if c.escalated_at is None and cnd.escalation_due(c.due_date, today, roadmap.escalation_days):
                # HSE topics escalate to the conditions area (m11), everything else to the roadmap area (m02).
                hse = cnd.hse_relevant(c.topic, c.hse_override)
                area_code = (roadmap.conditions_area_code if hse else "") or roadmap.roadmap_area_code
                area = (
                    (
                        await self.session.execute(
                            select(GovernanceArea).where(
                                GovernanceArea.project_id == project_id, GovernanceArea.code == area_code
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if area is not None and area.owner_user_id:
                    await self._notify(area.owner_user_id, "condition_escalated", "permit_condition", c.id, ctx)
                c.escalated_at = now
                escalated.append(str(c.id))
        for p in await self.repo.list_permits(project_id):
            if p.status == "in_force" and p.valid_until is not None and p.start_notified_at is None:
                if p.valid_until < today:
                    await self._fsm(PERMIT_FSM, p, "lapsed", actor_id, "not started within validity")
                    lapsed.append(str(p.id))
                    self._publish("permit.state_changed", {"project_id": str(project_id), "permit_id": str(p.id)})
        await self.session.flush()
        return {"notified": notified, "escalated": escalated, "lapsed": lapsed}

    # ── read models ────────────────────────────────────────────────────────

    async def condition_rows(self, project_id: uuid.UUID, today: date) -> list[dict[str, Any]]:
        permits = {str(p.id): p for p in await self.repo.list_permits(project_id)}
        evidence: dict[str, int] = {}
        for e in await self.repo.list_evidence(project_id):
            evidence[str(e.condition_id)] = evidence.get(str(e.condition_id), 0) + 1
        out = []
        for c in await self.repo.list_conditions(project_id):
            v = _cond_view(c)
            p = permits.get(str(c.permit_id))
            out.append(
                {
                    **condition_out(c),
                    "permit_reference": p.reference if p else "",
                    "permit_type_code": p.permit_type_code if p else "",
                    "overdue": cnd.is_overdue(v, today),
                    "breach_risk": cnd.breach_risk(v, today),
                    "evidence_count": evidence.get(str(c.id), 0),
                }
            )
        return out

    async def permit_rows(self, project_id: uuid.UUID, today: date) -> list[dict[str, Any]]:
        out = []
        for p in await self.repo.list_permits(project_id):
            d = permit_out(p)
            d["lapse_warning"] = cnd.lapse_warning(p.valid_until, today) if p.status in ("in_force", "lapsed") else None
            out.append(d)
        return out

    async def validation_payload(self, project_id: uuid.UUID, today: date) -> dict[str, Any]:
        roadmap = await self.repo.get_roadmap(project_id)
        tl = (await self.timeline(project_id, today))["items"] if roadmap else []
        catalogue = (await self.catalogue_for(roadmap)).model_dump(mode="json") if roadmap else None
        snap = await self.state_snapshot(project_id)
        apps = [application_out(a) for a in snap["applications"]]
        decisions = [decision_out(d) for d in snap["decisions"].values()]
        return {
            "today": today.isoformat(),
            "catalogue": catalogue,
            "requirements": [
                {**requirement_out(r), "state": snap["states"].get(str(r.id))} for r in snap["requirements"]
            ],
            "edges": [e.__dict__ for e in snap["edges"]],
            "timeline": tl,
            "applications": apps,
            "decisions": decisions,
            "permits": await self.permit_rows(project_id, today),
            "conditions": await self.condition_rows(project_id, today),
            "discharges": [discharge_out(d) for d in await self.repo.list_discharges(project_id)],
        }


# ── helpers ─────────────────────────────────────────────────────────────────


def _topo(nodes: list[str], edges: list[rm.Edge]) -> list[str]:
    deps: dict[str, list[str]] = {n: [] for n in nodes}
    for e in edges:
        if e.requirement in deps:
            deps[e.requirement].append(e.depends_on)
    out: list[str] = []
    seen: set[str] = set()

    def visit(n: str) -> None:
        if n in seen or n not in deps:
            return
        seen.add(n)
        for m in deps[n]:
            visit(m)
        out.append(n)

    for n in nodes:
        visit(n)
    return out


def _current_decisions(decisions: list[PermitDecision]) -> dict[str, PermitDecision]:
    """Per application, the newest revision (a correction supersedes)."""
    out: dict[str, PermitDecision] = {}
    for d in decisions:
        k = str(d.application_id)
        if k not in out or d.revision > out[k].revision:
            out[k] = d
    return out


def _validate_condition_input(c: dict[str, Any]) -> None:
    if not str(c.get("number") or "").strip():
        raise PermitError("condition_needs_number", 422)
    if not (c.get("text") or "").strip():
        raise PermitError("condition_needs_text", 422)
    if c.get("kind") not in CONDITION_KINDS:
        raise PermitError("condition_kind_invalid", 422)
    trigger = c.get("trigger") or ""
    if trigger and trigger not in CONDITION_TRIGGERS:
        raise PermitError("condition_trigger_invalid", 422)
    if trigger == "before_stage" and not (c.get("stage_ref") or "").strip():
        raise PermitError("stage_trigger_needs_stage", 422)
    if trigger == "by_date" and not c.get("due_date"):
        raise PermitError("date_trigger_needs_due_date", 422)
    if trigger == "on_event" and not (c.get("event_text") or "").strip():
        raise PermitError("event_trigger_needs_text", 422)
    if (c.get("topic") or "other") not in cnd.TOPICS:
        raise PermitError("condition_topic_invalid", 422)
    if (c.get("purpose") or "") not in ("", "restoration", "security"):
        raise PermitError("condition_purpose_invalid", 422)


def _cond_view(c: PermitCondition) -> cnd.CondView:
    return cnd.CondView(
        str(c.id),
        c.number,
        str(c.permit_id),
        c.kind,
        c.trigger,
        c.status,
        _s(c.owner_user_id),
        c.confirmed,
        c.due_date,
        c.topic,
        _s(c.gate_condition_id),
        c.purpose,
    )


def _condition_payload(c: PermitCondition) -> dict[str, Any]:
    return {
        "number": c.number,
        "text": c.text,
        "kind": c.kind,
        "national_kind": c.national_kind,
        "trigger": c.trigger,
        "stage_ref": c.stage_ref,
        "event_text": c.event_text,
        "due_date": c.due_date,
        "topic": c.topic,
        "purpose": c.purpose,
        "owner_user_id": c.owner_user_id,
        "responsible_party": c.responsible_party,
        "requires_authority_approval": c.requires_authority_approval,
        "evidence_required": c.evidence_required,
    }


def _jsonable(data: Any) -> Any:
    return json.loads(json.dumps(data, default=str)) if data is not None else None


def requirement_out(r: PermitRequirement) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "permit_type_code": r.permit_type_code,
        "title": r.title,
        "applicable": r.applicable,
        "applicability_rationale": r.applicability_rationale,
        "applicant_role": r.applicant_role,
        "applicant_source": r.applicant_source,
        "applicant_rationale": r.applicant_rationale,
        "applicant_party": r.applicant_party,
        "applicant_contact_id": _s(r.applicant_contact_id),
        "responsible_user_id": _s(r.responsible_user_id),
        "planned_submit_date": _iso(r.planned_submit_date),
        "needed_by_activity_id": _s(r.needed_by_activity_id),
        "needed_by_date": _iso(r.needed_by_date),
        "clock_variant": r.clock_variant,
        "expected_decision_date": _iso(r.expected_decision_date),
        "schedule_activity_id": _s(r.schedule_activity_id),
        "governance_area_code": r.governance_area_code,
        "conflict_accepted": r.conflict_accepted,
        "follow_up_of_id": _s(r.follow_up_of_id),
        "proposed_from_route": r.proposed_from_route,
        "sort_order": r.sort_order,
    }


def application_out(a: PermitApplication) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "requirement_id": str(a.requirement_id),
        "attempt": a.attempt,
        "kind": a.kind,
        "parent_permit_id": _s(a.parent_permit_id),
        "discharges_condition_ids": list(a.discharges_condition_ids or []),
        "authority_name": a.authority_name,
        "authority_reference": a.authority_reference,
        "submitted_at": _iso(a.submitted_at),
        "received_at": _iso(a.received_at),
        "validated_at": _iso(a.validated_at),
        "review_cycle_ids": list(a.review_cycle_ids or []),
        "submission_id": _s(a.submission_id),
        "cde_container_id": _s(a.cde_container_id),
        "approval_instance_id": _s(a.approval_instance_id),
        "state": a.status,
        "appeal_note": a.appeal_note,
    }


def clock_event_out(e: ClockEventRow) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "application_id": str(e.application_id),
        "kind": e.kind,
        "at": _iso(e.event_date),
        "period": e.period,
        "unit": e.unit,
        "reason": e.reason,
    }


def decision_out(d: PermitDecision) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "application_id": str(d.application_id),
        "revision": d.revision,
        "supersedes_id": _s(d.supersedes_id),
        "outcome": d.outcome,
        "decision_date": _iso(d.decision_date),
        "served_date": _iso(d.served_date),
        "reference": d.reference,
        "scope_note": d.scope_note,
        "scope_activity_ids": list(d.scope_activity_ids or []),
        "conditions_pending": d.conditions_pending,
        "appeal_deadline": _iso(d.appeal_deadline),
        "document_revision_id": _s(d.document_revision_id),
        "content_hash": d.content_hash,
        "deemed": d.deemed,
        "decided_by": _s(d.decided_by),
    }


def permit_out(p: Permit) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "requirement_id": str(p.requirement_id),
        "application_id": str(p.application_id),
        "decision_id": str(p.decision_id),
        "permit_type_code": p.permit_type_code,
        "scope": p.scope,
        "state": p.status,
        "reference": p.reference,
        "revocable": p.revocable,
        "security_amount": None if p.security_amount is None else str(p.security_amount),
        "security_currency": p.security_currency,
        "start_notified_at": _iso(p.start_notified_at),
        "valid_until": _iso(p.valid_until),
        "superseded_by_id": _s(p.superseded_by_id),
    }


def condition_out(c: PermitCondition) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "permit_id": str(c.permit_id),
        "number": c.number,
        "text": c.text,
        "kind": c.kind,
        "national_kind": c.national_kind,
        "trigger": c.trigger,
        "stage_ref": c.stage_ref,
        "event_text": c.event_text,
        "due_date": _iso(c.due_date),
        "topic": c.topic,
        "purpose": c.purpose,
        "owner_user_id": _s(c.owner_user_id),
        "responsible_party": c.responsible_party,
        "requires_authority_approval": c.requires_authority_approval,
        "evidence_required": c.evidence_required,
        "requirement_id": _s(c.requirement_id),
        "hse_relevant": cnd.hse_relevant(c.topic, c.hse_override),
        "state": c.status,
        "source": c.source,
        "confidence": None if c.confidence is None else str(c.confidence),
        "text_span": c.text_span,
        "confirmed": c.confirmed,
        "gate_condition_id": _s(c.gate_condition_id),
        "original_id": _s(c.original_id),
        "breach_ref_kind": c.breach_ref_kind,
        "breach_ref_id": _s(c.breach_ref_id),
        "breach_note": c.breach_note,
    }


def evidence_out(e: ConditionEvidence) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "condition_id": str(e.condition_id),
        "kind": e.kind,
        "ref_id": e.ref_id,
        "content_hash": e.content_hash,
        "note": e.note,
        "added_by": _s(e.added_by),
        "added_at": e.created_at.isoformat() if e.created_at else None,
    }


def discharge_out(d: ConditionDischarge) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "condition_id": str(d.condition_id),
        "mode": d.mode,
        "decided_by": _s(d.decided_by),
        "discharge_application_id": _s(d.discharge_application_id),
        "verifier_user_id": _s(d.verifier_user_id),
        "date": _iso(d.discharged_on),
        "document_revision_id": _s(d.document_revision_id),
        "note": d.note,
        "evidence_snapshot": d.evidence_snapshot,
    }


def roadmap_out(r: PermitRoadmap) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "project_id": str(r.project_id),
        "catalogue_source": r.catalogue_source,
        "catalogue_id": r.catalogue_id,
        "catalogue_version": r.catalogue_version,
        "jurisdiction": r.jurisdiction,
        "route_assessment_id": _s(r.route_assessment_id),
        "delivery_model_id": _s(r.delivery_model_id),
        "governance_document_id": _s(r.governance_document_id),
        "state": r.status,
        "roadmap_area_code": r.roadmap_area_code,
        "conditions_area_code": r.conditions_area_code,
        "internal_review": r.internal_review,
        "approval_route_id": _s(r.approval_route_id),
        "escalation_days": r.escalation_days,
        "buffer_days": r.buffer_days,
    }
