# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Stakeholders service: register, assessments, plan, events, commitments, roles, bodies, mandates.

Every write runs in the caller's transaction with its audit entry
(``log_activity``, or the FSM's own entry for a state change) and its events
(``publish_after_commit``). The pure rules live in ``analysis``,
``recurrence`` and ``mandates``; this class feeds them rows and enforces
what has to hold at write time.

Links into other modules are checked on write and answer 404 when the row is
missing or belongs to another project or tenant (rule 22): contacts through
``contacts.lookup.assignable_contact`` (tenant scoped), roster entries,
meetings, correspondence, risks and CDE containers by ``project_id``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.stakeholders import analysis as an
from app.modules.stakeholders import mandates as md
from app.modules.stakeholders import recurrence as rc
from app.modules.stakeholders.authority import authority_evaluator, release_item_checker
from app.modules.stakeholders.catalogue import (
    DEFAULT_FRAMEWORK_ID,
    FRAMEWORK_KIND,
    StakeholderFramework,
    default_framework_id_for_country,
    register_kind,
)
from app.modules.stakeholders.errors import StakeholderError, conflict, forbidden, not_found
from app.modules.stakeholders.fsm import (
    COMMITMENT_FSM,
    COMMITMENT_OPEN,
    EVENT_FSM,
    MANDATE_TARGETS,
    PLAN_FSM,
)
from app.modules.stakeholders.models import (
    CommunicationPlanItem,
    EngagementEvent,
    GovernanceBody,
    GovernanceBodyMember,
    Mandate,
    ProjectRole,
    Stakeholder,
    StakeholderAssessment,
    StakeholderCommitment,
    StakeholderSettings,
)
from app.modules.stakeholders.repository import StakeholderRepository

logger = logging.getLogger(__name__)

MODULE = "stakeholders"
TARGET_KIND = "stakeholder_commitment"
COMMITMENT_DECISION = "stakeholder_commitment"
COMMITMENT_CATEGORIES: tuple[str, ...] = (
    "noise",
    "traffic",
    "working_hours",
    "information",
    "compensation",
    "design_change",
    "access",
    "environment",
    "other",
)
SOURCE_KINDS: tuple[str, ...] = ("event", "meeting", "correspondence", "permit_condition", "manual")
STAKEHOLDER_STATUSES: tuple[str, ...] = ("active", "dormant", "archived")
TRIGGER_KINDS: tuple[str, ...] = ("gate", "event")
# Event names a plan item with ``trigger_kind: event`` may listen to (subscribed in ``events``).
EVENT_TRIGGERS: tuple[str, ...] = (
    "project_governance.gate.decided",
    "project_governance.phase.changed",
    "stakeholders.commitment.fulfilled",
)
QUORUM_KINDS: tuple[str, ...] = ("min_members", "majority", "unanimous")
LIVE_PLAN: tuple[str, ...] = ("planned", "active")
_OVERDUE_OPEN: tuple[str, ...] = ("proposed", "agreed", "in_progress")


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _day(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _amount(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float) or isinstance(value, bool):
        raise StakeholderError("invalid_amount")
    try:
        out = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise StakeholderError("invalid_amount") from exc
    if not out.is_finite():
        raise StakeholderError("invalid_amount")
    return out


class StakeholderService:
    """Orchestrates the stakeholder register and the project organisation of one project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = StakeholderRepository(session)
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
        publish_after_commit(self.session, f"{MODULE}.{name}", an.jsonable(data), source_module=MODULE)

    async def _fsm(
        self, fsm: Any, row: Any, target: str, actor_id: Any, reason: str | None = None, **meta: Any
    ) -> None:
        try:
            await fsm.apply(
                self.session,
                row,
                target,
                actor_id=_s(actor_id),
                reason=reason,
                extra_metadata=an.jsonable({"project_id": row.project_id, **meta}),
                entity_type=fsm.name,
            )
        except FSMError as exc:
            raise conflict("invalid_transition", detail=str(exc)) from exc

    async def _notify(self, user_id: Any, kind: str, entity_type: str, entity_id: Any, url: str, ctx: dict) -> None:
        """Best effort, inside a savepoint so a failure never poisons the write."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"stakeholders_{kind}",
                    title_key=f"notifications.stakeholders.{kind}.title",
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    body_key=f"notifications.stakeholders.{kind}.body",
                    body_context=an.jsonable(ctx),
                    action_url=url,
                    metadata=an.jsonable(ctx),
                )
        except Exception:
            logger.debug("stakeholders notification %s skipped", kind, exc_info=True)

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    async def is_member(self, project_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
        """Owner, team member or admin (the same answer module 1 uses for area owners)."""
        if user_id is None:
            return False
        from app.modules.teams.access import is_project_member
        from app.modules.users.models import User

        project = await self._project(project_id)
        if project.owner_id == user_id:
            return True
        user = await self.session.get(User, user_id)
        if user is None:
            return False
        if (user.role or "") == "admin":
            return True
        return await is_project_member(self.session, project_id, user_id)

    async def _require_member(self, project_id: uuid.UUID, user_id: Any) -> uuid.UUID | None:
        uid = _uuid(user_id)
        if user_id not in (None, "") and uid is None:
            raise StakeholderError("user_not_project_member")
        if uid is not None and not await self.is_member(project_id, uid):
            raise StakeholderError("user_not_project_member")
        return uid

    # ── links into other modules (rule 22) ─────────────────────────────────

    async def _contact(self, contact_id: Any, actor_id: Any) -> Any:
        from fastapi import HTTPException

        from app.modules.contacts.lookup import assignable_contact

        cid = _uuid(contact_id)
        if cid is None:
            raise not_found("contact_not_found")
        try:
            return await assignable_contact(self.session, cid, _s(actor_id))
        except HTTPException as exc:
            raise not_found("contact_not_found") from exc

    async def _in_project(self, model: Any, project_id: uuid.UUID, row_id: Any, code: str) -> Any:
        rid = _uuid(row_id)
        row = await self.session.get(model, rid) if rid is not None else None
        if row is None or getattr(row, "project_id", None) != project_id:
            raise not_found(code)
        return row

    async def _meeting(self, project_id: uuid.UUID, meeting_id: Any) -> Any:
        from app.modules.meetings.models import Meeting

        return await self._in_project(Meeting, project_id, meeting_id, "meeting_not_found")

    async def _correspondence(self, project_id: uuid.UUID, cid: Any) -> Any:
        from app.modules.correspondence.models import Correspondence

        return await self._in_project(Correspondence, project_id, cid, "correspondence_not_found")

    async def _risk(self, project_id: uuid.UUID, risk_id: Any) -> Any:
        from app.modules.risk.models import RiskItem

        return await self._in_project(RiskItem, project_id, risk_id, "risk_not_found")

    async def _roster(self, project_id: uuid.UUID, roster_id: Any) -> Any:
        from app.modules.teams.models import RosterMember

        return await self._in_project(RosterMember, project_id, roster_id, "roster_member_not_found")

    async def _container(self, project_id: uuid.UUID, container_id: Any) -> Any:
        from app.modules.cde.models import DocumentContainer

        return await self._in_project(DocumentContainer, project_id, container_id, "container_not_found")

    async def _stakeholder_ids(self, project_id: uuid.UUID, ids: list[Any] | None) -> list[str]:
        out: list[str] = []
        for raw in ids or []:
            row = await self.repo.get_in_project(Stakeholder, project_id, _uuid(raw) or uuid.uuid4())
            if row is None:
                raise not_found("stakeholder_not_found")
            if str(row.id) not in out:
                out.append(str(row.id))
        return out

    # ── settings and framework ─────────────────────────────────────────────

    async def framework(self, source: str, fid: str, version: int | None) -> StakeholderFramework:
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        try:
            return await resolve_catalogue(self.session, source, fid, version, kind=FRAMEWORK_KIND)
        except GovernanceError as exc:
            raise not_found("unknown_catalogue") from exc

    async def get_settings(self, project_id: uuid.UUID) -> StakeholderSettings | None:
        return await self.repo.get_settings(project_id)

    async def require_settings(self, project_id: uuid.UUID, *, lock: bool = False) -> StakeholderSettings:
        settings = await self.repo.get_settings(project_id, lock=lock)
        if settings is None:
            raise not_found("settings_missing")
        return settings

    async def context(self, project_id: uuid.UUID) -> tuple[StakeholderSettings, StakeholderFramework]:
        settings = await self.require_settings(project_id)
        fw = await self.framework(settings.framework_source, settings.framework_id, settings.framework_version)
        return settings, fw

    async def put_settings(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> StakeholderSettings:
        """Pin a framework (default by the project's country) and set register options.

        The first pin copies the framework's mandate template into the project
        when the project has no mandate rows yet.
        """
        project = await self._project(project_id)
        settings = await self.repo.get_settings(project_id, lock=True)
        source = data.get("framework_source") or (settings.framework_source if settings else "shipped")
        fid = data.get("framework_id") or (
            settings.framework_id
            if settings
            else default_framework_id_for_country(getattr(project, "country_code", None))
        )
        version = data.get("framework_version")
        if settings is not None and fid == settings.framework_id and version is None and not data.get("framework_id"):
            version = settings.framework_version
        fw = await self.framework(source, fid or DEFAULT_FRAMEWORK_ID, version)
        method = data.get("analysis_method") or (settings.analysis_method if settings else fw.default_method)
        if fw.method(method) is None:
            raise StakeholderError("unknown_method")
        route_id = data.get("commitment_route_id", settings.commitment_route_id if settings else None)
        if route_id is not None:
            await self._check_route(project_id, route_id)
        created = settings is None
        if settings is None:
            settings = StakeholderSettings(project_id=project_id, created_by=actor_id)
            self.session.add(settings)
        settings.framework_source = source
        settings.framework_id = fw.id
        settings.framework_version = fw.version
        settings.analysis_method = method
        settings.review_interval_days = int(data.get("review_interval_days") or settings.review_interval_days or 90)
        settings.owner_area_code = data.get("owner_area_code") or settings.owner_area_code or "m01_project_management"
        settings.commitment_route_id = _uuid(route_id)
        await self.session.flush()
        if created and not await self.repo.mandates(project_id):
            for row in fw.mandate_template:
                self.session.add(
                    Mandate(
                        project_id=project_id,
                        decision_type=row.decision_type,
                        scope="",
                        holder_kind=row.holder_kind,
                        holder_code=row.holder_code,
                        letter=row.letter,
                        limit_ref=self._limit_ref(fw, row.decision_type),
                    )
                )
            await self.session.flush()
        await self._audit(
            actor_id,
            "stakeholder_settings",
            settings.id,
            "pinned" if created else "updated",
            details=an.jsonable({"framework": f"{source}:{fw.id}@{fw.version}", "method": method}),
        )
        return settings

    async def _check_route(self, project_id: uuid.UUID, route_id: Any) -> None:
        from app.modules.approval_routes.models import Route

        route = await self.session.get(Route, _uuid(route_id)) if _uuid(route_id) else None
        if route is None or route.target_kind != TARGET_KIND or route.project_id not in (None, project_id):
            raise not_found("no_commitment_route")

    @staticmethod
    def _limit_ref(fw: StakeholderFramework, decision_type: str) -> dict[str, Any] | None:
        dt = fw.decision_type(decision_type)
        if dt is None or not dt.commitment_type:
            return None
        return {"authority_schedule": "pinned", "commitment_type": dt.commitment_type}

    # ── stakeholders ───────────────────────────────────────────────────────

    async def get_stakeholder(self, project_id: uuid.UUID, sid: uuid.UUID, *, lock: bool = False) -> Stakeholder:
        row = await self.repo.get_in_project(Stakeholder, project_id, sid, lock=lock)
        if row is None:
            raise not_found("stakeholder_not_found")
        return row

    async def _stakeholder_fields(
        self,
        project_id: uuid.UUID,
        fw: StakeholderFramework,
        data: dict[str, Any],
        actor_id: Any,
        row: Stakeholder | None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "category" in data:
            if fw.category(data["category"]) is None:
                raise StakeholderError("unknown_category")
            out["category"] = data["category"]
        if data.get("contact_id"):
            await self._contact(data["contact_id"], actor_id)
            out["contact_id"] = _uuid(data["contact_id"])
        elif "contact_id" in data:
            out["contact_id"] = None
        if data.get("parent_stakeholder_id"):
            parent = await self.get_stakeholder(project_id, _uuid(data["parent_stakeholder_id"]) or uuid.uuid4())
            if row is not None and parent.id == row.id:
                raise StakeholderError("invalid_parent")
            out["parent_stakeholder_id"] = parent.id
        elif "parent_stakeholder_id" in data:
            out["parent_stakeholder_id"] = None
        for key in ("user_id", "relationship_owner_user_id"):
            if key in data:
                out[key] = await self._require_member(project_id, data[key])
        if data.get("risk_id"):
            out["risk_id"] = (await self._risk(project_id, data["risk_id"])).id
        elif "risk_id" in data:
            out["risk_id"] = None
        for key in ("display_name", "interests", "expectations", "concerns"):
            if key in data and data[key] is not None:
                out[key] = str(data[key]).strip()
        for key in ("is_group", "is_confidential"):
            if key in data and data[key] is not None:
                out[key] = bool(data[key])
        if "group_size_estimate" in data:
            out["group_size_estimate"] = data["group_size_estimate"]
        if "geo" in data:
            out["geo"] = an.jsonable(data["geo"]) if data["geo"] else None
        if "status" in data and data["status"] is not None:
            if data["status"] not in STAKEHOLDER_STATUSES:
                raise StakeholderError("invalid_status")
            out["status"] = data["status"]
        return out

    async def create_stakeholder(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> Stakeholder:
        """Rule 1 (category from the pinned framework) and rule 17 (private persons confidential)."""
        _settings, fw = await self.context(project_id)
        if "category" not in data:
            raise StakeholderError("unknown_category")
        fields = await self._stakeholder_fields(project_id, fw, data, actor_id, None)
        category = fw.category(fields["category"])
        assert category is not None
        if not fields.get("contact_id") and not fields.get("display_name"):
            raise StakeholderError("display_name_required")
        if category.private_person and fields.get("contact_id") and not fields.get("is_group"):
            # The name of a private person lives in contacts only, so erasing the contact erases it here too.
            fields["display_name"] = ""
        if "is_confidential" not in fields:
            fields["is_confidential"] = category.private_person
        code = (data.get("code") or "").strip() or await self.repo.next_code(Stakeholder, project_id, "S-")
        if await self.repo.stakeholder_by_code(project_id, code) is not None:
            raise conflict("duplicate_code")
        row = Stakeholder(project_id=project_id, code=code, created_by=actor_id, **fields)
        try:
            async with self.session.begin_nested():
                await self.repo.add(row)
        except IntegrityError as exc:
            raise conflict("duplicate_code") from exc
        await self._audit(actor_id, "stakeholder", row.id, "created", details={"code": code, "category": row.category})
        self._publish(
            "stakeholder.created", {"project_id": project_id, "stakeholder_id": row.id, "category": row.category}
        )
        return row

    async def update_stakeholder(
        self, project_id: uuid.UUID, sid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> Stakeholder:
        _settings, fw = await self.context(project_id)
        row = await self.get_stakeholder(project_id, sid, lock=True)
        fields = await self._stakeholder_fields(project_id, fw, data, actor_id, row)
        if "code" in data and data["code"] and data["code"] != row.code:
            if await self.repo.stakeholder_by_code(project_id, data["code"]) is not None:
                raise conflict("duplicate_code")
            fields["code"] = data["code"]
        contact = fields.get("contact_id", row.contact_id)
        if not contact and not fields.get("display_name", row.display_name):
            raise StakeholderError("display_name_required")
        before = {k: _s(getattr(row, k)) for k in fields}
        for k, v in fields.items():
            setattr(row, k, v)
        await self.session.flush()
        await self._audit(
            actor_id,
            "stakeholder",
            row.id,
            "updated",
            details=an.jsonable({"before": before, "after": {k: _s(v) for k, v in fields.items()}}),
        )
        return row

    async def archive_stakeholder(self, project_id: uuid.UUID, sid: uuid.UUID, *, actor_id: uuid.UUID) -> Stakeholder:
        """DELETE keeps history: the stakeholder is archived, its assessments and commitments stay."""
        row = await self.get_stakeholder(project_id, sid, lock=True)
        if row.status != "archived":
            row.status = "archived"
            await self.session.flush()
            await self._audit(actor_id, "stakeholder", row.id, "archived")
        return row

    async def _contacts(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, Any]:
        if not ids:
            return {}
        from app.modules.contacts.models import Contact

        rows = (await self.session.execute(select(Contact).where(Contact.id.in_(ids)))).scalars().all()
        return {r.id: r for r in rows}

    @staticmethod
    def _contact_name(contact: Any) -> str:
        from app.modules.contacts.lookup import contact_display_name

        return contact_display_name(contact)

    async def stakeholder_views(
        self, project_id: uuid.UUID, *, can_read_personal: bool, today: date, method: str | None = None
    ) -> list[dict[str, Any]]:
        """Register rows with name resolution, masking (rule 17) and the computed flags (rules 3, 4)."""
        settings, fw = await self.context(project_id)
        method_code = method or settings.analysis_method
        rows = await self.repo.stakeholders(project_id)
        assessments = await self.repo.assessments(project_id)
        views = [self._assessment_view(a) for a in assessments]
        latest_any = an.latest_by_stakeholder(views)
        contacts = await self._contacts({r.contact_id for r in rows if r.contact_id})
        commitments = await self.repo.commitments(project_id)
        open_by: dict[str, int] = {}
        for c in commitments:
            if c.status in COMMITMENT_OPEN:
                for sid in c.stakeholder_ids or []:
                    open_by[sid] = open_by.get(sid, 0) + 1
        out = []
        for r in rows:
            sid = str(r.id)
            current = an.current_classification(views, sid, method_code)
            latest = latest_any.get(sid)
            category = fw.category(r.category)
            external = bool(category and category.kind == "external")
            name = self._resolve_name(r, contacts, can_read_personal)
            out.append(
                {
                    **self.stakeholder_out(r),
                    **name,
                    "classification": current.classification if current else an.NOT_ASSESSED,
                    "method_code": method_code,
                    "engagement_current": latest.engagement_current if latest else None,
                    "engagement_desired": latest.engagement_desired if latest else None,
                    "engagement_gap": an.engagement_gap(
                        fw, latest.engagement_current if latest else None, latest.engagement_desired if latest else None
                    ),
                    "attitude": None,
                    "last_assessed_at": latest.assessed_at.isoformat() if latest else None,
                    "review_due": r.status == "active"
                    and an.review_due(
                        latest_at=latest.assessed_at if latest else None,
                        external=external,
                        interval_days=settings.review_interval_days,
                        today=today,
                    ),
                    "external": external,
                    "open_commitments": open_by.get(sid, 0),
                }
            )
        att = {
            a.stakeholder_id: a.attitude
            for a in sorted(assessments, key=lambda a: _aware(a.assessed_at))
            if a.attitude is not None
        }
        for v in out:
            v["attitude"] = att.get(uuid.UUID(v["id"]))
        return out

    def _resolve_name(
        self, row: Stakeholder, contacts: dict[uuid.UUID, Any], can_read_personal: bool
    ) -> dict[str, Any]:
        anonymised = False
        if row.contact_id:
            contact = contacts.get(row.contact_id)
            name = self._contact_name(contact) if contact is not None else ""
            anonymised = not name
            name = name or None
            if row.display_name and not anonymised:
                name = f"{row.display_name} ({name})" if row.is_group else name
        else:
            name = row.display_name or None
        masked = bool(row.is_confidential and not can_read_personal and not anonymised)
        return {"name": None if masked else name, "masked": masked, "anonymised": anonymised}

    @staticmethod
    def stakeholder_out(r: Stakeholder) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "project_id": str(r.project_id),
            "code": r.code,
            "display_name": r.display_name,
            "category": r.category,
            "contact_id": _s(r.contact_id),
            "is_group": r.is_group,
            "group_size_estimate": r.group_size_estimate,
            "parent_stakeholder_id": _s(r.parent_stakeholder_id),
            "user_id": _s(r.user_id),
            "interests": r.interests,
            "expectations": r.expectations,
            "concerns": r.concerns,
            "relationship_owner_user_id": _s(r.relationship_owner_user_id),
            "geo": r.geo,
            "is_confidential": r.is_confidential,
            "status": r.status,
            "risk_id": _s(r.risk_id),
        }

    # ── assessments ────────────────────────────────────────────────────────

    @staticmethod
    def _assessment_view(a: StakeholderAssessment) -> an.AssessmentView:
        return an.AssessmentView(
            str(a.stakeholder_id),
            a.method_code,
            a.classification,
            a.engagement_current,
            a.engagement_desired,
            _aware(a.assessed_at) or _now(),
        )

    async def assess(
        self,
        project_id: uuid.UUID,
        sid: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        now: datetime | None = None,
    ) -> StakeholderAssessment:
        """Append one assessment (rule 2: scores validated, classification derived, never accepted)."""
        settings, fw = await self.context(project_id)
        stakeholder = await self.get_stakeholder(project_id, sid)
        code = data.get("method_code") or settings.analysis_method
        method = fw.method(code)
        if method is None:
            raise StakeholderError("unknown_method")
        try:
            scores = an.validate_scores(method, dict(data.get("scores") or {}))
        except an.ScoreError as exc:
            raise StakeholderError(
                "invalid_scores",
                violations=[{"code": c, "dimension": d} for d, c in exc.problems],
            ) from exc
        levels = fw.engagement_order()
        for key in ("engagement_current", "engagement_desired"):
            if data.get(key) is not None and data[key] not in levels:
                raise StakeholderError("unknown_engagement_level")
        attitude = data.get("attitude")
        if attitude is not None and (
            isinstance(attitude, bool) or not isinstance(attitude, int) or not -2 <= attitude <= 2
        ):
            raise StakeholderError("invalid_scores", violations=[{"code": "out_of_range", "dimension": "attitude"}])
        row = StakeholderAssessment(
            project_id=project_id,
            stakeholder_id=stakeholder.id,
            method_code=method.code,
            method_version=method.version,
            scores=an.jsonable(scores),
            classification=an.classify(method, scores),
            engagement_current=data.get("engagement_current"),
            engagement_desired=data.get("engagement_desired"),
            attitude=attitude,
            rationale=(data.get("rationale") or "").strip(),
            assessed_by=actor_id,
            assessed_at=now or _now(),
        )
        await self.repo.add(row)
        stakeholder.review_notified_at = None
        await self.session.flush()
        await self._audit(
            actor_id,
            "stakeholder",
            stakeholder.id,
            "assessed",
            details=an.jsonable({"method": method.code, "classification": row.classification, "scores": scores}),
        )
        self._publish(
            "stakeholder.assessed",
            {
                "project_id": project_id,
                "stakeholder_id": stakeholder.id,
                "assessment_id": row.id,
                "classification": row.classification,
            },
        )
        return row

    async def list_assessments(self, project_id: uuid.UUID, sid: uuid.UUID) -> list[StakeholderAssessment]:
        await self.get_stakeholder(project_id, sid)
        return await self.repo.assessments(project_id, sid)

    @staticmethod
    def assessment_out(a: StakeholderAssessment) -> dict[str, Any]:
        return {
            "id": str(a.id),
            "stakeholder_id": str(a.stakeholder_id),
            "method_code": a.method_code,
            "method_version": a.method_version,
            "scores": a.scores,
            "classification": a.classification,
            "engagement_current": a.engagement_current,
            "engagement_desired": a.engagement_desired,
            "attitude": a.attitude,
            "rationale": a.rationale,
            "assessed_by": _s(a.assessed_by),
            "assessed_at": _aware(a.assessed_at).isoformat() if a.assessed_at else None,
        }

    async def grid(
        self, project_id: uuid.UUID, *, method: str | None, can_read_personal: bool, today: date
    ) -> dict[str, Any]:
        """Computed grid positions under one method (rule 3): stakeholders without one are ``not_assessed``."""
        settings, fw = await self.context(project_id)
        code = method or settings.analysis_method
        m = fw.method(code)
        if m is None:
            raise StakeholderError("unknown_method")
        views = await self.stakeholder_views(project_id, can_read_personal=can_read_personal, today=today, method=code)
        latest: dict[str, StakeholderAssessment] = {}
        for a in await self.repo.assessments(project_id):
            if a.method_code == code and str(a.stakeholder_id) not in latest:
                latest[str(a.stakeholder_id)] = a  # repository orders newest first
        items = []
        for v in views:
            if v["status"] == "archived":
                continue
            a = latest.get(v["id"])
            items.append(
                {
                    "stakeholder_id": v["id"],
                    "code": v["code"],
                    "name": v["name"],
                    "masked": v["masked"],
                    "anonymised": v["anonymised"],
                    "category": v["category"],
                    "classification": a.classification if a else an.NOT_ASSESSED,
                    "position": an.grid_position(m, a.scores) if a else None,
                    "scores": a.scores if a else None,
                    "assessment_id": str(a.id) if a else None,
                }
            )
        return {
            "method_code": m.code,
            "method_version": m.version,
            "dimensions": [d.model_dump() for d in m.dimensions],
            "classes": [c.model_dump() for c in m.classes],
            "items": items,
        }

    # ── communication plan ────────────────────────────────────────────────

    async def get_plan_item(
        self, project_id: uuid.UUID, pid: uuid.UUID, *, lock: bool = False
    ) -> CommunicationPlanItem:
        row = await self.repo.get_in_project(CommunicationPlanItem, project_id, pid, lock=lock)
        if row is None:
            raise not_found("plan_item_not_found")
        return row

    async def _plan_fields(
        self, project_id: uuid.UUID, fw: StakeholderFramework, data: dict[str, Any], row: CommunicationPlanItem | None
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "audience_stakeholder_ids" in data:
            out["audience_stakeholder_ids"] = await self._stakeholder_ids(project_id, data["audience_stakeholder_ids"])
        if "audience_categories" in data:
            cats = list(dict.fromkeys(data["audience_categories"] or []))
            if any(fw.category(c) is None for c in cats):
                raise StakeholderError("unknown_category")
            out["audience_categories"] = cats
        if "audience_body_id" in data:
            if data["audience_body_id"]:
                out["audience_body_id"] = (
                    await self.get_body(project_id, _uuid(data["audience_body_id"]) or uuid.uuid4())
                ).id
            else:
                out["audience_body_id"] = None
        if "participation_level" in data and data["participation_level"] is not None:
            if data["participation_level"] not in fw.level_order():
                raise StakeholderError("unknown_participation_level")
            out["participation_level"] = data["participation_level"]
        if "channel" in data and data["channel"] is not None:
            if data["channel"] not in {c.code for c in fw.channels}:
                raise StakeholderError("unknown_channel")
            out["channel"] = data["channel"]
        if "format_code" in data:
            if data["format_code"] and fw.format(data["format_code"]) is None:
                raise StakeholderError("unknown_format")
            out["format_code"] = data["format_code"] or None
        if "frequency" in data:
            try:
                out["frequency"] = rc.normalise(data["frequency"])
            except rc.RecurrenceError as exc:
                raise StakeholderError("invalid_frequency", detail=str(exc)) from exc
        if "trigger_kind" in data:
            if data["trigger_kind"] not in (None, *TRIGGER_KINDS):
                raise StakeholderError("schedule_or_trigger")
            out["trigger_kind"] = data["trigger_kind"]
        if "trigger_ref" in data:
            out["trigger_ref"] = (data["trigger_ref"] or "").strip()
        if "owner_user_id" in data:
            out["owner_user_id"] = await self._require_member(project_id, data["owner_user_id"])
        for key in ("starts_on", "ends_on"):
            if key in data:
                out[key] = _day(data[key])
        for key in ("title", "purpose", "key_message"):
            if key in data and data[key] is not None:
                out[key] = str(data[key]).strip()
        merged = {
            k: out.get(k, getattr(row, k, None) if row is not None else None)
            for k in (
                "audience_stakeholder_ids",
                "audience_categories",
                "audience_body_id",
                "trigger_kind",
                "trigger_ref",
                "starts_on",
                "ends_on",
            )
        }
        if not (merged["audience_stakeholder_ids"] or merged["audience_categories"] or merged["audience_body_id"]):
            raise StakeholderError("audience_required")
        if merged["trigger_kind"] is None and merged["starts_on"] is None:
            raise StakeholderError("schedule_or_trigger")
        if merged["trigger_kind"] == "event" and merged["trigger_ref"] not in EVENT_TRIGGERS:
            raise StakeholderError("schedule_or_trigger")
        if merged["starts_on"] and merged["ends_on"] and merged["ends_on"] < merged["starts_on"]:
            raise StakeholderError("invalid_validity")
        return out

    async def _done_occurrences(self, item: CommunicationPlanItem) -> list[date]:
        return [
            e.occurrence_date or e.held_on
            for e in await self.repo.plan_events(item.id)
            if e.status == "held" and (e.occurrence_date or e.held_on) is not None
        ]

    async def _recompute_next_due(self, item: CommunicationPlanItem) -> None:
        if item.status not in LIVE_PLAN:
            item.next_due = None
            return
        item.next_due = rc.next_due(
            frequency=item.frequency,
            trigger_kind=item.trigger_kind,
            starts_on=item.starts_on,
            ends_on=item.ends_on,
            done=await self._done_occurrences(item),
            triggered_on=item.triggered_on,
        )

    async def create_plan_item(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> CommunicationPlanItem:
        _settings, fw = await self.context(project_id)
        if data.get("format_code") and not data.get("participation_level"):
            fmt = fw.format(data["format_code"])
            if fmt is not None:
                data = {**data, "participation_level": fmt.default_level}
                if not data.get("channel") and fmt.default_channels:
                    data["channel"] = fmt.default_channels[0]
        for key in ("participation_level", "channel", "title"):
            if not data.get(key):
                raise StakeholderError(
                    {"participation_level": "unknown_participation_level", "channel": "unknown_channel"}.get(
                        key, "title_required"
                    )
                )
        fields = await self._plan_fields(project_id, fw, data, None)
        status = data.get("status") or "planned"
        if status not in LIVE_PLAN:
            raise StakeholderError("invalid_transition")
        row = CommunicationPlanItem(project_id=project_id, created_by=actor_id, status=status, **fields)
        if row.trigger_kind:
            row.frequency = rc.ONCE
        await self.repo.add(row)
        await self._recompute_next_due(row)
        await self.session.flush()
        await self._audit(actor_id, "stakeholder_plan_item", row.id, "created", details={"title": row.title})
        return row

    async def update_plan_item(
        self, project_id: uuid.UUID, pid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> CommunicationPlanItem:
        _settings, fw = await self.context(project_id)
        row = await self.get_plan_item(project_id, pid, lock=True)
        fields = await self._plan_fields(project_id, fw, data, row)
        for k, v in fields.items():
            setattr(row, k, v)
        target = data.get("status")
        if target and target != row.status:
            await self._fsm(PLAN_FSM, row, target, actor_id)
        await self._recompute_next_due(row)
        await self.session.flush()
        await self._audit(actor_id, "stakeholder_plan_item", row.id, "updated", details=an.jsonable(fields))
        return row

    async def delete_plan_item(self, project_id: uuid.UUID, pid: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self.get_plan_item(project_id, pid, lock=True)
        await self._audit(actor_id, "stakeholder_plan_item", row.id, "deleted", details={"title": row.title})
        await self.repo.delete(row)

    @staticmethod
    def plan_overdue(item: CommunicationPlanItem, today: date) -> bool:
        """Rule 6: due date passed and no occurrence recorded for it (recording advances ``next_due``)."""
        return item.status in LIVE_PLAN and item.next_due is not None and item.next_due < today

    def plan_out(self, r: CommunicationPlanItem, today: date) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "title": r.title,
            "purpose": r.purpose,
            "key_message": r.key_message,
            "audience_stakeholder_ids": list(r.audience_stakeholder_ids or []),
            "audience_categories": list(r.audience_categories or []),
            "audience_body_id": _s(r.audience_body_id),
            "participation_level": r.participation_level,
            "channel": r.channel,
            "format_code": r.format_code,
            "frequency": r.frequency,
            "trigger_kind": r.trigger_kind,
            "trigger_ref": r.trigger_ref,
            "triggered_on": _s(r.triggered_on),
            "owner_user_id": _s(r.owner_user_id),
            "starts_on": _s(r.starts_on),
            "ends_on": _s(r.ends_on),
            "status": r.status,
            "next_due": _s(r.next_due),
            "overdue": self.plan_overdue(r, today),
        }

    async def due(self, project_id: uuid.UUID, *, start: date, end: date, today: date) -> list[dict[str, Any]]:
        """The communication calendar: computed occurrences in ``[start, end]`` plus overdue items."""
        out: list[dict[str, Any]] = []
        for item in await self.repo.plan_items(project_id):
            if item.status not in LIVE_PLAN:
                continue
            done = set(await self._done_occurrences(item))
            dates: list[date] = []
            if item.trigger_kind:
                if item.next_due and start <= item.next_due <= end:
                    dates = [item.next_due]
            elif item.starts_on is not None:
                dates = [
                    d
                    for d in rc.occurrences_between(item.frequency, item.starts_on, start, end)
                    if item.ends_on is None or d <= item.ends_on
                ]
            if self.plan_overdue(item, today) and item.next_due not in dates and item.next_due is not None:
                dates.insert(0, item.next_due)
            for d in dates:
                out.append(
                    {
                        "plan_item_id": str(item.id),
                        "title": item.title,
                        "date": d.isoformat(),
                        "done": d in done,
                        "overdue": d < today and d not in done and item.next_due is not None and d >= item.next_due,
                        "participation_level": item.participation_level,
                        "channel": item.channel,
                        "owner_user_id": _s(item.owner_user_id),
                    }
                )
        out.sort(key=lambda r: (r["date"], r["title"]))
        return out

    # ── engagement events ─────────────────────────────────────────────────

    async def get_event(self, project_id: uuid.UUID, eid: uuid.UUID, *, lock: bool = False) -> EngagementEvent:
        row = await self.repo.get_in_project(EngagementEvent, project_id, eid, lock=lock)
        if row is None or row.deleted_at is not None:
            raise not_found("event_not_found")
        return row

    async def _event_fields(
        self, project_id: uuid.UUID, fw: StakeholderFramework, data: dict[str, Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "participation_level" in data and data["participation_level"] is not None:
            if data["participation_level"] not in fw.level_order():
                raise StakeholderError("unknown_participation_level")
            out["participation_level"] = data["participation_level"]
        if "format_code" in data:
            if data["format_code"] and fw.format(data["format_code"]) is None:
                raise StakeholderError("unknown_format")
            out["format_code"] = data["format_code"] or None
        if "stakeholder_ids" in data:
            out["stakeholder_ids"] = await self._stakeholder_ids(project_id, data["stakeholder_ids"])
        if "meeting_id" in data:
            out["meeting_id"] = (await self._meeting(project_id, data["meeting_id"])).id if data["meeting_id"] else None
        if "correspondence_ids" in data:
            out["correspondence_ids"] = [
                str((await self._correspondence(project_id, c)).id)
                for c in dict.fromkeys(data["correspondence_ids"] or [])
            ]
        if "cde_container_ids" in data:
            out["cde_container_ids"] = [
                str((await self._container(project_id, c)).id) for c in dict.fromkeys(data["cde_container_ids"] or [])
            ]
        for key in ("held_on", "occurrence_date"):
            if key in data:
                out[key] = _day(data[key])
        for key in ("title", "location", "outcome", "feedback_summary"):
            if key in data and data[key] is not None:
                out[key] = str(data[key]).strip()
        if "attendance_count" in data:
            out["attendance_count"] = data["attendance_count"]
        return out

    async def create_event(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> EngagementEvent:
        """An event, ad hoc or against a plan item; a held one advances the item's ``next_due`` (rule 7)."""
        _settings, fw = await self.context(project_id)
        item = None
        if data.get("plan_item_id"):
            item = await self.get_plan_item(project_id, _uuid(data["plan_item_id"]) or uuid.uuid4(), lock=True)
            data = {
                "participation_level": item.participation_level,
                "format_code": item.format_code,
                "title": item.title,
                **{k: v for k, v in data.items() if v is not None},
            }
            if not data.get("occurrence_date"):
                data["occurrence_date"] = item.next_due or data.get("held_on")
        elif data.get("format_code") and not data.get("participation_level"):
            fmt = fw.format(data["format_code"])
            if fmt is not None:
                data = {**data, "participation_level": fmt.default_level}
        if not data.get("title"):
            raise StakeholderError("title_required")
        if not data.get("participation_level"):
            raise StakeholderError("unknown_participation_level")
        status = data.get("status") or ("held" if data.get("held_on") else "planned")
        if status not in ("planned", "held"):
            raise StakeholderError("invalid_transition")
        if status == "held" and not data.get("held_on"):
            raise StakeholderError("held_on_required")
        fields = await self._event_fields(project_id, fw, data)
        row = EngagementEvent(
            project_id=project_id, plan_item_id=item.id if item else None, status=status, created_by=actor_id, **fields
        )
        await self.repo.add(row)
        if item is not None:
            await self._recompute_next_due(item)
            await self.session.flush()
        await self._audit(actor_id, "stakeholder_event", row.id, f"created_{status}", details={"title": row.title})
        return row

    async def update_event(
        self, project_id: uuid.UUID, eid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> EngagementEvent:
        _settings, fw = await self.context(project_id)
        row = await self.get_event(project_id, eid, lock=True)
        target = data.get("status")
        fields = await self._event_fields(project_id, fw, {k: v for k, v in data.items() if k != "status"})
        for k, v in fields.items():
            setattr(row, k, v)
        if target and target != row.status:
            if target == "held" and row.held_on is None:
                raise StakeholderError("held_on_required")
            await self._fsm(EVENT_FSM, row, target, actor_id)
        await self.session.flush()
        if row.plan_item_id:
            item = await self.get_plan_item(project_id, row.plan_item_id, lock=True)
            await self._recompute_next_due(item)
            await self.session.flush()
        await self._audit(actor_id, "stakeholder_event", row.id, "updated", details=an.jsonable(fields))
        return row

    async def delete_event(self, project_id: uuid.UUID, eid: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        """Soft delete (rule 9): commitments keep their source link and snapshot."""
        row = await self.get_event(project_id, eid, lock=True)
        row.deleted_at = _now()
        await self.session.flush()
        if row.plan_item_id:
            item = await self.get_plan_item(project_id, row.plan_item_id, lock=True)
            await self._recompute_next_due(item)
            await self.session.flush()
        await self._audit(actor_id, "stakeholder_event", row.id, "deleted", details={"title": row.title})

    def event_out(self, r: EngagementEvent, fw: StakeholderFramework | None, today: date) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "plan_item_id": _s(r.plan_item_id),
            "occurrence_date": _s(r.occurrence_date),
            "format_code": r.format_code,
            "participation_level": r.participation_level,
            "title": r.title,
            "held_on": _s(r.held_on),
            "location": r.location,
            "stakeholder_ids": list(r.stakeholder_ids or []),
            "attendance_count": r.attendance_count,
            "outcome": r.outcome,
            "feedback_summary": r.feedback_summary,
            "meeting_id": _s(r.meeting_id),
            "correspondence_ids": list(r.correspondence_ids or []),
            "cde_container_ids": list(r.cde_container_ids or []),
            "status": r.status,
            "feedback_not_reported": bool(
                fw
                and an.feedback_not_reported(
                    fw,
                    level=r.participation_level,
                    status=r.status,
                    held_on=r.held_on,
                    feedback_summary=r.feedback_summary,
                    today=today,
                )
            ),
            "feedback_due_on": _s(an.feedback_due_on(r.held_on, fw.feedback_due_days)) if fw and r.held_on else None,
        }

    # ── commitments ───────────────────────────────────────────────────────

    async def get_commitment(
        self, project_id: uuid.UUID, cid: uuid.UUID, *, lock: bool = False
    ) -> StakeholderCommitment:
        row = await self.repo.get_in_project(StakeholderCommitment, project_id, cid, lock=lock)
        if row is None:
            raise not_found("commitment_not_found")
        return row

    async def _source(self, project_id: uuid.UUID, kind: str, ref: Any) -> tuple[str, dict[str, Any]]:
        """Resolve a commitment source and freeze its title and date (rule 9)."""
        if kind not in SOURCE_KINDS:
            raise StakeholderError("invalid_source")
        if kind == "event":
            ev = await self.get_event(project_id, _uuid(ref) or uuid.uuid4())
            return str(ev.id), {"title": ev.title, "date": _s(ev.held_on or ev.occurrence_date)}
        if kind == "meeting":
            m = await self._meeting(project_id, ref)
            return str(m.id), {"title": m.title, "date": (m.meeting_date or "")[:10] or None}
        if kind == "correspondence":
            c = await self._correspondence(project_id, ref)
            day = c.date_received or (c.created_at.date().isoformat() if c.created_at else None)
            return str(c.id), {"title": c.subject, "date": day}
        if kind == "permit_condition":
            text = str(ref or "").strip()
            if not text:
                raise StakeholderError("invalid_source")
            return text[:255], {"title": text[:255], "date": None}
        return "", {"title": "", "date": None}

    async def _commitment_fields(self, project_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "stakeholder_ids" in data:
            ids = await self._stakeholder_ids(project_id, data["stakeholder_ids"])
            if not ids:
                raise StakeholderError("audience_required")
            out["stakeholder_ids"] = ids
        if "category" in data and data["category"] is not None:
            if data["category"] not in COMMITMENT_CATEGORIES:
                raise StakeholderError("invalid_category")
            out["category"] = data["category"]
        if "owner_user_id" in data:
            out["owner_user_id"] = await self._require_member(project_id, data["owner_user_id"])
        if "due_date" in data:
            out["due_date"] = _day(data["due_date"])
        for key in ("text", "verification"):
            if key in data and data[key] is not None:
                out[key] = str(data[key]).strip()
        if "cost_estimate" in data:
            out["cost_estimate"] = _amount(data["cost_estimate"])
        if "currency" in data and data["currency"] is not None:
            out["currency"] = str(data["currency"]).strip().upper()[:3]
        if "risk_id" in data:
            out["risk_id"] = (await self._risk(project_id, data["risk_id"])).id if data["risk_id"] else None
        for key in ("task_id", "requirement_id", "release_item_id"):
            if key in data:
                out[key] = _uuid(data[key])
        return out

    async def create_commitment(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> StakeholderCommitment:
        await self.context(project_id)
        if not (data.get("text") or "").strip():
            raise StakeholderError("text_required")
        if not data.get("stakeholder_ids"):
            raise StakeholderError("audience_required")
        kind = data.get("source_kind") or "manual"
        ref, snapshot = await self._source(project_id, kind, data.get("source_ref"))
        fields = await self._commitment_fields(project_id, data)
        if fields.get("cost_estimate") is not None and not fields.get("currency"):
            project = await self._project(project_id)
            fields["currency"] = (getattr(project, "currency", "") or "")[:3]
        code = await self.repo.next_code(StakeholderCommitment, project_id, "C-")
        row = StakeholderCommitment(
            project_id=project_id,
            code=code,
            source_kind=kind,
            source_ref=ref,
            source_snapshot=an.jsonable(snapshot),
            created_by=actor_id,
            **fields,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(row)
        except IntegrityError as exc:
            raise conflict("concurrent_change") from exc
        await self._audit(actor_id, "stakeholder_commitment", row.id, "created", details={"code": code, "source": kind})
        return row

    async def update_commitment(
        self, project_id: uuid.UUID, cid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> StakeholderCommitment:
        row = await self.get_commitment(project_id, cid, lock=True)
        if COMMITMENT_FSM.is_terminal(row.status):
            raise conflict("invalid_transition")
        fields = await self._commitment_fields(project_id, data)
        if row.status != "proposed" and ("text" in fields or "cost_estimate" in fields):
            # What was agreed is what the decider saw; a new promise is a new commitment.
            raise conflict("invalid_transition")
        for k, v in fields.items():
            setattr(row, k, v)
        await self.session.flush()
        await self._audit(actor_id, "stakeholder_commitment", row.id, "updated", details=an.jsonable(fields))
        return row

    @staticmethod
    def commitment_overdue(c: StakeholderCommitment, today: date) -> bool:
        """Rule 18 flag: an open commitment past its due date."""
        return c.status in _OVERDUE_OPEN and c.due_date is not None and c.due_date < today

    async def transition_commitment(
        self,
        project_id: uuid.UUID,
        cid: uuid.UUID,
        target: str,
        *,
        actor_id: uuid.UUID,
        rationale: str = "",
        communicated_back_at: datetime | None = None,
        loop_not_required_rationale: str = "",
        create_risk: bool = False,
        today: date,
    ) -> tuple[StakeholderCommitment, list[str]]:
        """Move a commitment. Returns the row and warnings.

        ``agreed`` / ``withdrawn`` are mandate decisions (rule 10): the decider of
        ``stakeholder_commitment`` confirms directly, or, when the framework names
        an approval target kind, an approval instance is started and the
        transition waits for it. ``breached`` needs a rationale and may open a
        risk (rule 18). ``verified`` needs the loop closed (rule 19).
        """
        settings, fw = await self.context(project_id)
        row = await self.get_commitment(project_id, cid, lock=True)
        if row.pending_target:
            raise conflict("approval_pending")
        if not COMMITMENT_FSM.has_transition(row.status, target):
            raise conflict("invalid_transition", detail=f"{row.status} -> {target}")
        warnings: list[str] = []
        rationale = (rationale or "").strip()
        if target == "withdrawn" and not rationale:
            raise StakeholderError("rationale_required")
        if target == "agreed":
            if row.owner_user_id is None or row.due_date is None:
                raise StakeholderError("owner_and_due_required")
            warnings += await self._check_release_item(project_id, row)
        if target == "breached":
            if not rationale:
                raise StakeholderError("rationale_required")
            row.breach_rationale = rationale
            if create_risk and row.risk_id is None:
                row.risk_id = await self._open_risk(project_id, row, actor_id)
        if target == "verified":
            loop = (loop_not_required_rationale or "").strip()
            if communicated_back_at is not None:
                row.communicated_back_at = _aware(communicated_back_at)
            if loop:
                row.loop_not_required_rationale = loop
            if row.communicated_back_at is None and not row.loop_not_required_rationale:
                raise StakeholderError("verification_needs_loop_closed")
        if target in MANDATE_TARGETS:
            resolution = await self.who_decides(project_id, COMMITMENT_DECISION, "", today=today)
            if "mandate_missing" in resolution["flags"]:
                raise StakeholderError("mandate_missing")
            dt = fw.decision_type(COMMITMENT_DECISION)
            if dt is not None and dt.approval_target_kind == TARGET_KIND:
                await self._start_commitment_approval(settings, row, target, rationale, actor_id)
                return row, warnings
            if str(actor_id) not in resolution["user_ids"]:
                raise forbidden("not_decider")
            row.decision_ref = an.jsonable(
                {
                    "mode": "direct",
                    "decision_type": COMMITMENT_DECISION,
                    "holder_kind": resolution["holder_kind"],
                    "holder_code": resolution["holder_code"],
                    "decided_by": actor_id,
                    "decided_at": _now(),
                    "target": target,
                }
            )
        if target == "withdrawn":
            row.withdraw_rationale = rationale
        await self._fsm(COMMITMENT_FSM, row, target, actor_id, reason=rationale or None)
        await self.session.flush()
        self._after_commitment_transition(row, target)
        return row, warnings

    def _after_commitment_transition(self, row: StakeholderCommitment, target: str) -> None:
        if target in ("agreed", "fulfilled", "breached", "withdrawn", "verified"):
            self._publish(
                f"commitment.{target}",
                {
                    "project_id": row.project_id,
                    "commitment_id": row.id,
                    "stakeholder_ids": row.stakeholder_ids,
                    "risk_id": row.risk_id,
                },
            )

    async def _check_release_item(self, project_id: uuid.UUID, row: StakeholderCommitment) -> list[str]:
        """Rule 10: a commitment with a cost needs a module 2 release item when a matrix exists."""
        if row.cost_estimate is None:
            return []
        checker = release_item_checker()
        if checker is None:
            return ["release_item_not_checked"]
        answer = await checker(self.session, project_id, row.release_item_id)
        if not answer.has_matrix:
            return ["no_commitment_matrix"]
        if row.release_item_id is None or not answer.item_valid:
            raise StakeholderError("release_item_required")
        return []

    async def _start_commitment_approval(
        self,
        settings: StakeholderSettings,
        row: StakeholderCommitment,
        target: str,
        rationale: str,
        actor_id: uuid.UUID,
    ) -> None:
        from fastapi import HTTPException

        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        if settings.commitment_route_id is None:
            raise StakeholderError("no_commitment_route")
        try:
            async with self.session.begin_nested():
                instance = await ApprovalRouteService(self.session).start_instance(
                    InstanceCreate(route_id=settings.commitment_route_id, target_kind=TARGET_KIND, target_id=row.id),
                    started_by=actor_id,
                )
        except HTTPException as exc:
            code = "approval_pending" if exc.status_code == 409 else "no_commitment_route"
            raise StakeholderError(code, 409 if code == "approval_pending" else 422) from exc
        row.approval_instance_id = instance.id
        row.pending_target = target
        row.pending_rationale = rationale
        await self.session.flush()
        await self._audit(
            actor_id,
            "stakeholder_commitment",
            row.id,
            "approval_requested",
            details=an.jsonable({"target": target, "instance_id": instance.id}),
        )

    async def apply_route_verdict(self, instance_id: uuid.UUID, *, verdict: str, decided_by: Any) -> bool:
        """Terminal approval verdict: approved applies the pending transition, anything else clears it."""
        row = await self.repo.commitment_by_instance(instance_id)
        if row is None or not row.pending_target:
            return False
        target = row.pending_target
        rationale = row.pending_rationale
        row.pending_target = None
        row.pending_rationale = ""
        if verdict != "approved":
            await self._audit(decided_by, "stakeholder_commitment", row.id, f"approval_{verdict}")
            await self.session.flush()
            return True
        row.decision_ref = an.jsonable(
            {
                "mode": "approval",
                "decision_type": COMMITMENT_DECISION,
                "approval_instance_id": instance_id,
                "decided_by": _s(decided_by),
                "decided_at": _now(),
                "target": target,
            }
        )
        if target == "withdrawn":
            row.withdraw_rationale = rationale
        await self._fsm(
            COMMITMENT_FSM, row, target, decided_by, reason=rationale or None, approval_instance_id=instance_id
        )
        await self.session.flush()
        self._after_commitment_transition(row, target)
        return True

    async def _open_risk(
        self, project_id: uuid.UUID, row: StakeholderCommitment, actor_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Rule 18 option: a confirmed breach opens a risk through the risk service (risk owns the record)."""
        from app.modules.risk.schemas import RiskCreate
        from app.modules.risk.service import RiskService

        risk = await RiskService(self.session).create_risk(
            RiskCreate(
                project_id=project_id,
                title=f"{row.code}: breached commitment to stakeholders"[:255],
                description=f"{row.text}\n\n{row.breach_rationale}"[:5000],
                category="regulatory",
                owner_user_id=row.owner_user_id,
            ),
            user_id=_s(actor_id),
        )
        return risk.id

    def commitment_out(self, r: StakeholderCommitment, today: date) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "code": r.code,
            "stakeholder_ids": list(r.stakeholder_ids or []),
            "source_kind": r.source_kind,
            "source_ref": r.source_ref,
            "source_snapshot": r.source_snapshot or {},
            "text": r.text,
            "category": r.category,
            "owner_user_id": _s(r.owner_user_id),
            "due_date": _s(r.due_date),
            "verification": r.verification,
            "cost_estimate": None if r.cost_estimate is None else str(r.cost_estimate),
            "currency": r.currency,
            "release_item_id": _s(r.release_item_id),
            "task_id": _s(r.task_id),
            "risk_id": _s(r.risk_id),
            "requirement_id": _s(r.requirement_id),
            "status": r.status,
            "overdue": self.commitment_overdue(r, today),
            "decision_ref": r.decision_ref or {},
            "approval_instance_id": _s(r.approval_instance_id),
            "pending_target": r.pending_target,
            "withdraw_rationale": r.withdraw_rationale,
            "breach_rationale": r.breach_rationale,
            "communicated_back_at": _aware(r.communicated_back_at).isoformat() if r.communicated_back_at else None,
            "loop_not_required_rationale": r.loop_not_required_rationale,
        }

    # ── daily sweep (rules 4, 6, 18) ──────────────────────────────────────

    async def sweep(self, project_id: uuid.UUID, *, today: date) -> dict[str, int]:
        """Notify once: review due (per interval), plan overdue (per occurrence), commitment overdue (once)."""
        settings, fw = await self.context(project_id)
        counts = {"review_due": 0, "plan_overdue": 0, "commitment_overdue": 0}
        latest = an.latest_by_stakeholder(self._assessment_view(a) for a in await self.repo.assessments(project_id))
        owners: dict[str, uuid.UUID | None] = {}
        for s in await self.repo.stakeholders(project_id):
            owners[str(s.id)] = s.relationship_owner_user_id
            if s.status != "active":
                continue
            cat = fw.category(s.category)
            last = latest.get(str(s.id))
            if not an.review_due(
                latest_at=last.assessed_at if last else None,
                external=bool(cat and cat.kind == "external"),
                interval_days=settings.review_interval_days,
                today=today,
            ):
                continue
            notified = _aware(s.review_notified_at)
            if notified is not None and (today - notified.date()).days <= settings.review_interval_days:
                continue
            s.review_notified_at = _now()
            counts["review_due"] += 1
            await self._notify(
                s.relationship_owner_user_id,
                "review_due",
                "stakeholder",
                s.id,
                f"/projects/{project_id}/stakeholders?stakeholder={s.id}",
                {"code": s.code},
            )
        for item in await self.repo.plan_items(project_id):
            if not self.plan_overdue(item, today) or item.overdue_notified_for == item.next_due:
                continue
            item.overdue_notified_for = item.next_due
            counts["plan_overdue"] += 1
            await self._notify(
                item.owner_user_id,
                "plan_overdue",
                "stakeholder_plan_item",
                item.id,
                f"/projects/{project_id}/stakeholders/communication?item={item.id}",
                {"title": item.title, "due": item.next_due},
            )
        for c in await self.repo.commitments(project_id):
            if not self.commitment_overdue(c, today) or c.breach_notified_on is not None:
                continue
            c.breach_notified_on = today
            counts["commitment_overdue"] += 1
            ctx = {"code": c.code, "due": c.due_date}
            url = f"/projects/{project_id}/stakeholders/commitments?commitment={c.id}"
            recipients = {c.owner_user_id, *(owners.get(sid) for sid in c.stakeholder_ids or [])}
            for uid in sorted((u for u in recipients if u), key=str):
                await self._notify(uid, "commitment_overdue", "stakeholder_commitment", c.id, url, ctx)
        await self.session.flush()
        return counts

    # ── plan triggers (rule 6) ────────────────────────────────────────────

    async def fire_trigger(self, project_id: uuid.UUID, kind: str, ref: str, *, on: date) -> int:
        """A gate moved to review (``gate``, ref = gate code) or a listened event fired (``event``)."""
        fired = 0
        for item in await self.repo.plan_items(project_id):
            if item.status not in LIVE_PLAN or item.trigger_kind != kind:
                continue
            if item.trigger_ref and item.trigger_ref != ref:
                continue
            item.triggered_on = on
            await self._recompute_next_due(item)
            fired += 1
        await self.session.flush()
        return fired

    # ── roles ─────────────────────────────────────────────────────────────

    async def _holders(self, project_id: uuid.UUID) -> tuple[list[ProjectRole], list[md.Holder], dict[uuid.UUID, Any]]:
        from app.modules.teams.models import RosterMember

        roles = await self.repo.roles(project_id)
        roster_ids = {r.roster_member_id for r in roles if r.roster_member_id} | {
            r.deputy_roster_member_id for r in roles if r.deputy_roster_member_id
        }
        roster: dict[uuid.UUID, Any] = {}
        if roster_ids:
            rows = (await self.session.execute(select(RosterMember).where(RosterMember.id.in_(roster_ids)))).scalars()
            roster = {r.id: r for r in rows}
        holders = []
        for r in roles:
            member = roster.get(r.roster_member_id) if r.roster_member_id else None
            holders.append(
                md.Holder(
                    role_code=r.role_code,
                    user_id=_s(member.user_id) if member is not None and member.user_id else None,
                    contact_id=_s(r.holder_contact_id)
                    or (_s(member.contact_id) if member is not None and member.contact_id else None),
                    roster_member_id=_s(r.roster_member_id),
                    valid_from=r.valid_from,
                    valid_to=r.valid_to,
                    conflict_rationale=r.conflict_rationale or "",
                )
            )
        return roles, holders, roster

    async def _bodies(self, project_id: uuid.UUID) -> tuple[list[GovernanceBody], list[md.Body]]:
        bodies = await self.repo.bodies(project_id)
        members = await self.repo.body_members(project_id)
        by_body: dict[uuid.UUID, list[GovernanceBodyMember]] = {}
        for m in members:
            by_body.setdefault(m.body_id, []).append(m)
        out = [
            md.Body(
                code=b.code,
                quorum_kind=b.quorum_kind,
                quorum_min=b.quorum_min,
                decision_level=b.decision_level,
                members=tuple(
                    md.Member(
                        role_code=m.role_code,
                        user_id=_s(m.user_id),
                        contact_id=_s(m.contact_id),
                        voting=m.voting,
                        valid_from=m.valid_from,
                        valid_to=m.valid_to,
                    )
                    for m in by_body.get(b.id, [])
                ),
            )
            for b in bodies
        ]
        return bodies, out

    @staticmethod
    def _mandate_rows(rows: list[Mandate]) -> list[md.MandateRow]:
        return [md.MandateRow(r.decision_type, r.holder_kind, r.holder_code, r.letter, r.scope or "") for r in rows]

    async def roles_view(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        _settings, fw = await self.context(project_id)
        roles, holders, roster = await self._holders(project_id)
        contacts = await self._contacts({r.holder_contact_id for r in roles if r.holder_contact_id})
        items = []
        for r, h in zip(roles, holders, strict=True):
            member = roster.get(r.roster_member_id) if r.roster_member_id else None
            contact = contacts.get(r.holder_contact_id) if r.holder_contact_id else None
            items.append(
                {
                    "id": str(r.id),
                    "role_code": r.role_code,
                    "custom_label": r.custom_label,
                    "roster_member_id": _s(r.roster_member_id),
                    "holder_contact_id": _s(r.holder_contact_id),
                    "deputy_roster_member_id": _s(r.deputy_roster_member_id),
                    "holder_name": (member.display_name if member is not None else None)
                    or (self._contact_name(contact) if contact is not None else None),
                    "user_id": h.user_id,
                    "valid_from": _s(r.valid_from),
                    "valid_to": _s(r.valid_to),
                    "valid_today": h.valid_on(today),
                    "conflict_rationale": r.conflict_rationale,
                }
            )
        defined = [
            {
                "code": r.code,
                "name_key": r.name_key,
                "holder_kind": r.holder_kind,
                "multi": r.multi,
                "required": r.required,
            }
            for r in fw.roles
        ]
        return {
            "roles": defined,
            "holders": items,
            "vacant": md.vacant_roles(fw, holders, today, required_only=False),
            "vacant_required": md.vacant_roles(fw, holders, today, required_only=True),
        }

    async def put_role_holders(
        self,
        project_id: uuid.UUID,
        role_code: str,
        holders_in: list[dict[str, Any]],
        *,
        actor_id: uuid.UUID,
        custom_label: str = "",
        today: date,
    ) -> dict[str, Any]:
        """Replace the holders of one role (rule 14) and publish ``stakeholders.role.changed`` (rule 16)."""
        _settings, fw = await self.context(project_id)
        role = fw.role(role_code)
        existing_custom = [r for r in await self.repo.roles(project_id) if r.role_code == role_code and r.custom_label]
        if role is None and not (custom_label.strip() or existing_custom):
            raise StakeholderError("unknown_role")
        label = custom_label.strip() or (existing_custom[0].custom_label if existing_custom else "")
        _roles_before, holders_before, _roster = await self._holders(project_id)
        old_users = sorted(
            {h.user_id for h in holders_before if h.role_code == role_code and h.user_id and h.valid_on(today)}
        )
        new_rows: list[ProjectRole] = []
        for h in holders_in:
            roster_id, contact_id = h.get("roster_member_id"), h.get("holder_contact_id")
            if bool(roster_id) == bool(contact_id):
                raise StakeholderError("holder_required")
            vf, vt = _day(h.get("valid_from")), _day(h.get("valid_to"))
            if vf and vt and vt < vf:
                raise StakeholderError("invalid_validity")
            if roster_id:
                member = await self._roster(project_id, roster_id)
                if member.user_id is not None and not await self.is_member(project_id, member.user_id):
                    raise StakeholderError("user_not_project_member")
            else:
                await self._contact(contact_id, actor_id)
            deputy = h.get("deputy_roster_member_id")
            if deputy:
                await self._roster(project_id, deputy)
            new_rows.append(
                ProjectRole(
                    project_id=project_id,
                    role_code=role_code,
                    custom_label=label if role is None else "",
                    roster_member_id=_uuid(roster_id),
                    holder_contact_id=_uuid(contact_id),
                    deputy_roster_member_id=_uuid(deputy),
                    valid_from=vf,
                    valid_to=vt,
                    conflict_rationale=(h.get("conflict_rationale") or "").strip(),
                    created_by=actor_id,
                )
            )
        if role is not None and not role.multi and _overlapping([(r.valid_from, r.valid_to) for r in new_rows]):
            raise StakeholderError("role_not_multi")
        for old in [r for r in await self.repo.roles(project_id) if r.role_code == role_code]:
            await self.session.delete(old)
        await self.session.flush()
        for r in new_rows:
            self.session.add(r)
        await self.session.flush()
        conflicts = await self._enforce_conflicts(project_id, fw, today)
        _roles_after, holders_after, _r2 = await self._holders(project_id)
        new_users = sorted(
            {h.user_id for h in holders_after if h.role_code == role_code and h.user_id and h.valid_on(today)}
        )
        hints = await self._area_owner_hints(project_id, set(old_users) - set(new_users))
        await self._audit(
            actor_id,
            "stakeholder_role",
            role_code,
            "holders_set",
            details=an.jsonable({"role_code": role_code, "before": old_users, "after": new_users}),
        )
        self._publish(
            "role.changed",
            {
                "project_id": project_id,
                "role_code": role_code,
                "previous_user_ids": old_users,
                "user_ids": new_users,
            },
        )
        return {
            "conflicts": [_conflict_out(c) for c in conflicts],
            "hints": hints,
            "warnings": await self._frame_warnings(project_id),
        }

    async def _enforce_conflicts(
        self, project_id: uuid.UUID, fw: StakeholderFramework, today: date
    ) -> list[md.Conflict]:
        """Rule 12 at write time: an error-severity conflict refuses the write, warnings are returned."""
        _roles, holders, _roster = await self._holders(project_id)
        _bodies, bodies = await self._bodies(project_id)
        found = md.conflicts(fw, self._mandate_rows(await self.repo.mandates(project_id)), holders, bodies, today)
        errors = [c for c in found if c.severity == "error"]
        if errors:
            raise StakeholderError("self_approval_forbidden", violations=[_conflict_out(c) for c in errors])
        return found

    async def _area_owner_hints(self, project_id: uuid.UUID, removed_users: set[str]) -> list[dict[str, Any]]:
        """Rule 16: module 1 area owners are not changed, but a hint names areas the old holder owns."""
        if not removed_users:
            return []
        from app.modules.project_governance.models import GovernanceArea

        rows = (
            await self.session.execute(select(GovernanceArea).where(GovernanceArea.project_id == project_id))
        ).scalars()
        return [
            {"code": "area_owner_was_previous_holder", "area_code": a.code, "owner_user_id": str(a.owner_user_id)}
            for a in rows
            if a.owner_user_id is not None and str(a.owner_user_id) in removed_users
        ]

    async def _frame_warnings(self, project_id: uuid.UUID) -> list[str]:
        """Rule 21 / decision n: editing the organisation after the gate warns that the frame document is binding."""
        from app.modules.project_governance.models import GovernanceArea, GovernanceDocument

        settings = await self.repo.get_settings(project_id)
        area_code = settings.owner_area_code if settings else "m01_project_management"
        stmt = (
            select(GovernanceDocument.status)
            .join(GovernanceArea, GovernanceArea.id == GovernanceDocument.area_id)
            .where(GovernanceDocument.project_id == project_id, GovernanceArea.code == area_code)
        )
        statuses = set((await self.session.execute(stmt)).scalars().all())
        return ["frame_document_binding"] if "binding" in statuses else []

    # ── bodies ────────────────────────────────────────────────────────────

    async def get_body(self, project_id: uuid.UUID, bid: uuid.UUID, *, lock: bool = False) -> GovernanceBody:
        row = await self.repo.get_in_project(GovernanceBody, project_id, bid, lock=lock)
        if row is None:
            raise not_found("body_not_found")
        return row

    async def _body_fields(
        self, project_id: uuid.UUID, fw: StakeholderFramework, data: dict[str, Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "body_type" in data and data["body_type"] is not None:
            if data["body_type"] not in {b.code for b in fw.body_types}:
                raise StakeholderError("unknown_body_type")
            out["body_type"] = data["body_type"]
        if "chair_role_code" in data:
            if data["chair_role_code"] and fw.role(data["chair_role_code"]) is None:
                raise StakeholderError("unknown_role")
            out["chair_role_code"] = data["chair_role_code"] or None
        if "quorum_kind" in data and data["quorum_kind"] is not None:
            if data["quorum_kind"] not in QUORUM_KINDS:
                raise StakeholderError("invalid_quorum")
            out["quorum_kind"] = data["quorum_kind"]
        if "quorum_min" in data:
            out["quorum_min"] = data["quorum_min"]
        if "terms_container_id" in data:
            out["terms_container_id"] = (
                (await self._container(project_id, data["terms_container_id"])).id
                if data["terms_container_id"]
                else None
            )
        for key in ("name", "meeting_series_ref"):
            if key in data and data[key] is not None:
                out[key] = str(data[key]).strip()
        if "decision_level" in data and data["decision_level"] is not None:
            out["decision_level"] = int(data["decision_level"])
        return out

    async def create_body(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> GovernanceBody:
        _settings, fw = await self.context(project_id)
        fields = await self._body_fields(project_id, fw, data)
        if "body_type" not in fields:
            raise StakeholderError("unknown_body_type")
        code = (data.get("code") or fields["body_type"]).strip()
        if not fields.get("name"):
            fields["name"] = code
        if "decision_level" not in fields:
            bt = next(b for b in fw.body_types if b.code == fields["body_type"])
            fields["decision_level"] = bt.default_decision_level
        if fields.get("quorum_kind") == "min_members" and not fields.get("quorum_min"):
            raise StakeholderError("invalid_quorum")
        row = GovernanceBody(project_id=project_id, code=code, **fields)
        try:
            async with self.session.begin_nested():
                await self.repo.add(row)
        except IntegrityError as exc:
            raise conflict("duplicate_code") from exc
        await self._audit(actor_id, "stakeholder_body", row.id, "created", details={"code": code})
        return row

    async def update_body(
        self, project_id: uuid.UUID, bid: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> GovernanceBody:
        _settings, fw = await self.context(project_id)
        row = await self.get_body(project_id, bid, lock=True)
        fields = await self._body_fields(project_id, fw, data)
        for k, v in fields.items():
            setattr(row, k, v)
        if row.quorum_kind == "min_members" and not row.quorum_min:
            raise StakeholderError("invalid_quorum")
        await self.session.flush()
        await self._audit(actor_id, "stakeholder_body", row.id, "updated", details=an.jsonable(fields))
        return row

    async def delete_body(self, project_id: uuid.UUID, bid: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self.get_body(project_id, bid, lock=True)
        if any(m.holder_kind == "body" and m.holder_code == row.code for m in await self.repo.mandates(project_id)):
            raise conflict("body_in_use")
        await self._audit(actor_id, "stakeholder_body", row.id, "deleted", details={"code": row.code})
        await self.repo.delete(row)

    async def put_members(
        self, project_id: uuid.UUID, bid: uuid.UUID, members: list[dict[str, Any]], *, actor_id: uuid.UUID, today: date
    ) -> list[GovernanceBodyMember]:
        _settings, fw = await self.context(project_id)
        body = await self.get_body(project_id, bid, lock=True)
        rows: list[GovernanceBodyMember] = []
        custom_roles = {r.role_code for r in await self.repo.roles(project_id)}
        for m in members:
            given = [k for k in ("role_code", "user_id", "contact_id") if m.get(k)]
            if len(given) != 1:
                raise StakeholderError("invalid_member")
            if m.get("role_code") and fw.role(m["role_code"]) is None and m["role_code"] not in custom_roles:
                raise StakeholderError("unknown_role")
            if m.get("user_id"):
                await self._require_member(project_id, m["user_id"])
            if m.get("contact_id"):
                await self._contact(m["contact_id"], actor_id)
            vf, vt = _day(m.get("valid_from")), _day(m.get("valid_to"))
            if vf and vt and vt < vf:
                raise StakeholderError("invalid_validity")
            rows.append(
                GovernanceBodyMember(
                    project_id=project_id,
                    body_id=body.id,
                    role_code=m.get("role_code") or None,
                    user_id=_uuid(m.get("user_id")),
                    contact_id=_uuid(m.get("contact_id")),
                    voting=bool(m.get("voting", True)),
                    valid_from=vf,
                    valid_to=vt,
                )
            )
        for old in [x for x in await self.repo.body_members(project_id) if x.body_id == body.id]:
            await self.session.delete(old)
        await self.session.flush()
        for r in rows:
            self.session.add(r)
        await self.session.flush()
        await self._enforce_conflicts(project_id, fw, today)
        await self._audit(actor_id, "stakeholder_body", body.id, "members_set", details={"count": len(rows)})
        return rows

    async def bodies_view(self, project_id: uuid.UUID, *, today: date) -> list[dict[str, Any]]:
        bodies, parsed = await self._bodies(project_id)
        _roles, holders, _roster = await self._holders(project_id)
        members = await self.repo.body_members(project_id)
        out = []
        for b, p in zip(bodies, parsed, strict=True):
            needed, present = md.quorum_needed(p), md.body_present(p, holders, today)
            out.append(
                {
                    "id": str(b.id),
                    "code": b.code,
                    "body_type": b.body_type,
                    "name": b.name,
                    "chair_role_code": b.chair_role_code,
                    "quorum_kind": b.quorum_kind,
                    "quorum_min": b.quorum_min,
                    "decision_level": b.decision_level,
                    "meeting_series_ref": b.meeting_series_ref,
                    "terms_container_id": _s(b.terms_container_id),
                    "members": [
                        {
                            "id": str(m.id),
                            "role_code": m.role_code,
                            "user_id": _s(m.user_id),
                            "contact_id": _s(m.contact_id),
                            "voting": m.voting,
                            "valid_from": _s(m.valid_from),
                            "valid_to": _s(m.valid_to),
                            "valid_today": md.Member(valid_from=m.valid_from, valid_to=m.valid_to).valid_on(today),
                        }
                        for m in members
                        if m.body_id == b.id
                    ],
                    "quorum_needed": needed,
                    "quorum_present": present,
                    "inquorate": present < needed,
                }
            )
        return out

    # ── mandates ──────────────────────────────────────────────────────────

    async def matrix(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        _settings, fw = await self.context(project_id)
        rows = await self.repo.mandates(project_id)
        _roles, holders, _roster = await self._holders(project_id)
        _bodies_rows, bodies = await self._bodies(project_id)
        parsed = self._mandate_rows(rows)
        return {
            "decision_types": [d.model_dump() for d in fw.decision_types],
            "roles": sorted({*(r.code for r in fw.roles), *(h.role_code for h in holders)}),
            "bodies": [b.code for b in bodies],
            "rows": [
                {
                    "id": str(r.id),
                    "decision_type": r.decision_type,
                    "scope": r.scope,
                    "holder_kind": r.holder_kind,
                    "holder_code": r.holder_code,
                    "letter": r.letter,
                    "scope_note": r.scope_note,
                    "limit_ref": r.limit_ref,
                }
                for r in rows
            ],
            "missing": md.missing_deciders(fw, parsed),
            "conflicts": [_conflict_out(c) for c in md.conflicts(fw, parsed, holders, bodies, today)],
        }

    async def put_mandates(
        self, project_id: uuid.UUID, rows_in: list[dict[str, Any]], *, actor_id: uuid.UUID, today: date
    ) -> dict[str, Any]:
        """Replace the matrix. Two deciders for one type and scope is refused (rule 13)."""
        _settings, fw = await self.context(project_id)
        await self.require_settings(project_id, lock=True)  # serialises concurrent matrix writes
        role_codes = {r.code for r in fw.roles} | {r.role_code for r in await self.repo.roles(project_id)}
        body_codes = {b.code for b in await self.repo.bodies(project_id)}
        parsed: list[md.MandateRow] = []
        seen: set[tuple[str, str, str, str]] = set()
        for r in rows_in:
            dt = r.get("decision_type")
            if fw.decision_type(dt or "") is None:
                raise StakeholderError("unknown_decision_type")
            kind, code, letter = r.get("holder_kind"), r.get("holder_code"), r.get("letter")
            if letter not in ("P", "D", "A", "C", "I"):
                raise StakeholderError("invalid_letter")
            if kind == "role" and code not in role_codes:
                raise StakeholderError("unknown_role")
            if kind == "body" and code not in body_codes:
                raise not_found("unknown_body")
            if kind not in ("role", "body"):
                raise StakeholderError("unknown_role")
            scope = (r.get("scope") or "").strip()
            key = (dt, scope, kind, code)
            if key in seen:
                raise StakeholderError("duplicate_code")
            seen.add(key)
            parsed.append(md.MandateRow(dt, kind, code, letter, scope))
        twice = [{"decision_type": dt, "scope": sc} for (dt, sc), n in md.decider_counts(parsed).items() if n > 1]
        if twice:
            raise StakeholderError("two_deciders", violations=twice)
        for old in await self.repo.mandates(project_id, lock=True):
            await self.session.delete(old)
        await self.session.flush()
        notes = {
            (r.get("decision_type"), (r.get("scope") or "").strip(), r.get("holder_kind"), r.get("holder_code")): r
            for r in rows_in
        }
        for p in parsed:
            src = notes[(p.decision_type, p.scope, p.holder_kind, p.holder_code)]
            self.session.add(
                Mandate(
                    project_id=project_id,
                    decision_type=p.decision_type,
                    scope=p.scope,
                    holder_kind=p.holder_kind,
                    holder_code=p.holder_code,
                    letter=p.letter,
                    scope_note=(src.get("scope_note") or "").strip(),
                    limit_ref=self._limit_ref(fw, p.decision_type),
                )
            )
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise conflict("concurrent_change") from exc
        conflicts = await self._enforce_conflicts(project_id, fw, today)
        await self._audit(actor_id, "stakeholder_mandate", project_id, "matrix_set", details={"rows": len(parsed)})
        self._publish("mandate.changed", {"project_id": project_id, "rows": len(parsed)})
        return {
            "conflicts": [_conflict_out(c) for c in conflicts],
            "missing": md.missing_deciders(fw, parsed),
            "warnings": await self._frame_warnings(project_id),
        }

    async def who_decides(
        self,
        project_id: uuid.UUID,
        decision_type: str,
        scope: str,
        *,
        today: date,
        amount: Any = None,
        currency: str | None = None,
    ) -> dict[str, Any]:
        """Rule 11: the deciding role or body resolved to people; money tier delegated to module 2."""
        _settings, fw = await self.context(project_id)
        dt = fw.decision_type(decision_type)
        if dt is None:
            raise StakeholderError("unknown_decision_type")
        _roles, holders, _roster = await self._holders(project_id)
        _b, bodies = await self._bodies(project_id)
        res = md.who_decides(
            self._mandate_rows(await self.repo.mandates(project_id)), decision_type, scope, holders, bodies, today
        )
        out: dict[str, Any] = {
            "decision_type": decision_type,
            "scope": scope,
            "holder_kind": res.holder_kind,
            "holder_code": res.holder_code,
            "user_ids": res.user_ids,
            "parties": [
                {
                    "user_id": p.user_id,
                    "contact_id": p.contact_id,
                    "roster_member_id": p.roster_member_id,
                    "role_code": p.via_role,
                    "voting": p.voting,
                }
                for p in res.parties
            ],
            "quorum_needed": res.quorum_needed,
            "quorum_present": res.quorum_present,
            "flags": list(res.flags),
            "approval_target_kind": dt.approval_target_kind,
            "commitment_type": dt.commitment_type,
            "authority": None,
        }
        value = _amount(amount)
        if dt.commitment_type and value is not None:
            evaluator = authority_evaluator()
            if evaluator is None:
                out["flags"].append("authority_not_evaluated")
            else:
                project = await self._project(project_id)
                ccy = (currency or getattr(project, "currency", "") or "").upper()
                answer = await evaluator(self.session, project_id, dt.commitment_type, value, ccy, today)
                out["authority"] = {
                    "tier_code": answer.tier_code,
                    "approver_user_ids": list(answer.approver_user_ids),
                    "escalate_outside": answer.escalate_outside,
                    "schedule": answer.schedule,
                    "amount": str(value),
                    "currency": ccy,
                    "flags": list(answer.flags),
                }
        return out

    async def conflicts(self, project_id: uuid.UUID, *, today: date) -> list[dict[str, Any]]:
        _settings, fw = await self.context(project_id)
        _roles, holders, _roster = await self._holders(project_id)
        _b, bodies = await self._bodies(project_id)
        rows = self._mandate_rows(await self.repo.mandates(project_id))
        return [_conflict_out(c) for c in md.conflicts(fw, rows, holders, bodies, today)]

    # ── frame documents (rule 21) ─────────────────────────────────────────

    async def file_frame_document(
        self, project_id: uuid.UUID, *, content: bytes, file_name: str, mime_type: str, actor_id: uuid.UUID
    ) -> dict[str, Any]:
        """File a generated export as a new CDE revision of the owner area's frame document.

        The binding version is whatever module 1 makes binding at the gate; this
        only adds the pending revision to the frame document's container.
        """
        from fastapi import HTTPException

        from app.core.storage import get_storage_backend
        from app.modules.cde.schemas import RevisionCreate
        from app.modules.cde.service import CDEService
        from app.modules.project_governance.models import GovernanceArea, GovernanceDocument

        settings = await self.require_settings(project_id)
        stmt = (
            select(GovernanceDocument)
            .join(GovernanceArea, GovernanceArea.id == GovernanceDocument.area_id)
            .where(
                GovernanceDocument.project_id == project_id,
                GovernanceArea.code == settings.owner_area_code,
                GovernanceDocument.container_id.is_not(None),
            )
            .order_by(GovernanceDocument.created_at)
        )
        doc = (await self.session.execute(stmt)).scalars().first()
        if doc is None:
            raise conflict("frame_document_missing")
        key = f"stakeholders/{project_id}/{uuid.uuid4().hex}_{file_name}"
        await get_storage_backend().put(key, content)
        try:
            revision = await CDEService(self.session).create_revision(
                doc.container_id,
                RevisionCreate(file_name=file_name, file_size=str(len(content)), mime_type=mime_type, storage_key=key),
                user_id=str(actor_id),
            )
        except HTTPException as exc:
            raise conflict("frame_document_missing", detail=str(exc.detail)) from exc
        warnings = ["frame_document_binding"] if doc.status == "binding" else []
        await self._audit(
            actor_id,
            "stakeholder_frame_document",
            doc.id,
            "filed",
            details=an.jsonable({"revision_id": revision.id, "file_name": file_name}),
        )
        return {
            "document_id": str(doc.id),
            "container_id": str(doc.container_id),
            "revision_id": str(revision.id),
            "warnings": warnings,
        }

    # ── readiness (rule 20) and validation payload ────────────────────────

    async def readiness(self, project_id: uuid.UUID, *, today: date) -> dict[str, dict[str, Any]]:
        """The five governance evidence checks, each ``{status, counts}``."""
        settings, fw = await self.context(project_id)
        stakeholders = [s for s in await self.repo.stakeholders(project_id) if s.status == "active"]
        assessments = await self.repo.assessments(project_id)
        assessed = {str(a.stakeholder_id) for a in assessments}
        external = [s for s in stakeholders if (c := fw.category(s.category)) and c.kind == "external"]
        external_assessed = [s for s in external if str(s.id) in assessed]
        gaps = await self.key_stakeholders_without_plan(project_id, settings, fw)
        rows = self._mandate_rows(await self.repo.mandates(project_id))
        missing = md.missing_deciders(fw, rows)
        _roles, holders, _roster = await self._holders(project_id)
        vacant = md.vacant_roles(fw, holders, today, required_only=True)
        commitments = await self.repo.commitments(project_id)
        unexplained = [
            c.code
            for c in commitments
            if (c.status == "breached" and not c.breach_rationale.strip()) or self.commitment_overdue(c, today)
        ]

        def check(ok: bool, **counts: Any) -> dict[str, Any]:
            return {"status": "met" if ok else "not_met", **counts}

        return {
            "register_present": check(bool(external_assessed), external=len(external), assessed=len(external_assessed)),
            "key_stakeholders_planned": check(not gaps, without_plan=len(gaps), refs=gaps),
            "mandates_complete": check(not missing, missing=len(missing), refs=missing),
            "roles_filled": check(not vacant, vacant=len(vacant), refs=vacant),
            "commitments_tracked": check(not unexplained, breached=len(unexplained), refs=unexplained),
        }

    async def key_stakeholders_without_plan(
        self, project_id: uuid.UUID, settings: StakeholderSettings, fw: StakeholderFramework
    ) -> list[str]:
        """Rule 5: ``manage_closely`` (current method) with a positive gap and no live plan item covering them."""
        stakeholders = {str(s.id): s for s in await self.repo.stakeholders(project_id) if s.status == "active"}
        views = [self._assessment_view(a) for a in await self.repo.assessments(project_id)]
        latest = an.latest_by_stakeholder(views)
        plans = [p for p in await self.repo.plan_items(project_id) if p.status in LIVE_PLAN]
        out = []
        for sid, s in stakeholders.items():
            current = an.current_classification(views, sid, settings.analysis_method)
            if current is None or current.classification != "manage_closely":
                continue
            last = latest.get(sid)
            gap = an.engagement_gap(
                fw, last.engagement_current if last else None, last.engagement_desired if last else None
            )
            if gap is None or gap <= 0:
                continue
            covered = any(
                sid in (p.audience_stakeholder_ids or []) or s.category in (p.audience_categories or []) for p in plans
            )
            if not covered:
                out.append(s.code)
        return sorted(out)

    async def validation_payload(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """Everything the ``stakeholders`` rule set reads, as JSON values."""
        settings, fw = await self.context(project_id)
        views = await self.stakeholder_views(project_id, can_read_personal=False, today=today)
        events = await self.repo.events(project_id)
        _roles, holders, _roster = await self._holders(project_id)
        _b, bodies = await self._bodies(project_id)
        rows = self._mandate_rows(await self.repo.mandates(project_id))
        return an.jsonable(
            {
                "today": today,
                "framework": fw.model_dump(mode="json"),
                "stakeholders": [
                    {"code": v["code"], "category": v["category"], "status": v["status"], "review_due": v["review_due"]}
                    for v in views
                ],
                "key_without_plan": await self.key_stakeholders_without_plan(project_id, settings, fw),
                "events": [
                    {
                        "title": e.title,
                        "id": e.id,
                        "feedback_not_reported": an.feedback_not_reported(
                            fw,
                            level=e.participation_level,
                            status=e.status,
                            held_on=e.held_on,
                            feedback_summary=e.feedback_summary,
                            today=today,
                        ),
                    }
                    for e in events
                ],
                "commitments": [
                    {
                        "code": c.code,
                        "status": c.status,
                        "owner": c.owner_user_id,
                        "due_date": c.due_date,
                        "overdue": self.commitment_overdue(c, today),
                        "breach_rationale": c.breach_rationale,
                    }
                    for c in await self.repo.commitments(project_id)
                ],
                "missing_deciders": md.missing_deciders(fw, rows),
                "conflicts": [_conflict_out(c) for c in md.conflicts(fw, rows, holders, bodies, today)],
                "vacant_required": md.vacant_roles(fw, holders, today, required_only=True),
                "bodies": [
                    {"code": b.code, "needed": md.quorum_needed(b), "present": md.body_present(b, holders, today)}
                    for b in bodies
                    if b.members
                ],
            }
        )


def _overlapping(windows: list[tuple[date | None, date | None]]) -> bool:
    lo, hi = date.min, date.max
    spans = sorted(((a or lo), (b or hi)) for a, b in windows)
    return any(spans[i + 1][0] <= spans[i][1] for i in range(len(spans) - 1))


def _conflict_out(c: md.Conflict) -> dict[str, Any]:
    return {
        "decision_type": c.decision_type,
        "scope": c.scope,
        "user_id": c.user_id,
        "letters": list(c.letters),
        "roles": list(c.roles),
        "severity": c.severity,
        "acknowledged": c.acknowledged,
    }
