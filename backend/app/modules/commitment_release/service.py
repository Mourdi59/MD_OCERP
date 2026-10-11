# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Commitment release service: matrix, items, releases, recompute, guard check and exposure.

Every write runs in the caller's transaction with its audit entry
(``log_activity``) and its events (``publish_after_commit``). Amounts are
derived on read (``figures``); the only figures frozen are the ones a release
decision captures at request time (amount, FX rate and date, tier, schedule
version), because a decision must keep saying what it decided on.

Release flow (SPEC rules 2, 4, 5, 11, 12, 19)::

    request_release  -- lock item, refuse a second pending request (409),
                        evaluate DoA on the cumulative amount in the schedule
                        currency, start an approval instance on the tier route
    apply_route_verdict (from the approval_routes subscriber)
                     -- completed: released / partially_released
                        rejected: back to the state before, attempt + 1
    withdraw         -- the requester cancels the instance, attempt + 1
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.commitment_release import evaluator as ev
from app.modules.commitment_release import figures
from app.modules.commitment_release.catalogue import (
    ABORT_BASIS_KIND,
    AUTHORITY_SCHEDULE_KIND,
    AbortBasis,
    AuthoritySchedule,
    default_schedule_id_for_country,
    parse_amount,
    register_kinds,
)
from app.modules.commitment_release.errors import CommitmentError, conflict, forbidden, not_found
from app.modules.commitment_release.exposure import ScheduleEntry, TermsInput, compute_exposure
from app.modules.commitment_release.fsm import ITEM_FSM, REQUESTABLE, WORKING
from app.modules.commitment_release.fx import FxQuote, FxRateMissing, norm, resolve_quote
from app.modules.commitment_release.models import (
    AbortScenario,
    AbortTerms,
    AuthorityAssignment,
    CommitmentItem,
    CommitmentLink,
    CommitmentMatrix,
    CommitmentPrecondition,
    ReleaseDecision,
)
from app.modules.commitment_release.repository import CommitmentRepository

logger = logging.getLogger(__name__)

MODULE = "commitment_release"
TARGET_KIND = "commitment_release"
ZERO = Decimal("0")
ENFORCEMENT = ("off", "warn", "block")
FX_POLICIES = ("fx_service_rate_set", "project_rates")
PLANNED_SOURCES = ("budget_line", "cost_line", "boq_position", "manual")
PRECONDITION_KINDS = (
    "manual",
    "gate_decided",
    "frame_document_binding",
    "funding_approved",
    "permit",
    "budget_available",
    "public_commitment_appropriation",
)
STORED_PRECONDITIONS = ("manual", "permit", "public_commitment_appropriation")
_MANAGER_ROLES = frozenset({"admin", "manager"})
_RELEASED_OR_LATER = ("released", "partially_released", "committed", "closed", "re_release_required")


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _money_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _amount(value: Any, code: str = "amount_invalid") -> Decimal:
    try:
        return parse_amount(value)
    except ValueError as exc:
        raise CommitmentError(code, 422) from exc


class CommitmentService:
    """Orchestrates the matrix of one project."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CommitmentRepository(session)
        register_kinds()

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

    async def _fsm(self, item: CommitmentItem, target: str, actor_id: Any, reason: str | None = None, **meta: Any):
        try:
            await ITEM_FSM.apply(
                self.session,
                item,
                target,
                actor_id=_s(actor_id),
                reason=reason,
                extra_metadata={"project_id": _s(item.project_id), **meta},
                entity_type=ITEM_FSM.name,
            )
        except FSMError as exc:
            raise conflict("invalid_transition", detail=str(exc)) from exc

    async def _notify(self, user_id: Any, kind: str, item: CommitmentItem, ctx: dict[str, Any]) -> None:
        """Best effort, inside a savepoint so a failure never poisons the write."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"commitment_{kind}",
                    title_key=f"notifications.commitment.{kind}.title",
                    entity_type="commitment_item",
                    entity_id=str(item.id),
                    body_key=f"notifications.commitment.{kind}.body",
                    body_context=ctx,
                    action_url=f"/projects/{item.project_id}/commitments?item={item.id}",
                    metadata=ctx,
                )
        except Exception:
            logger.debug("commitment notification %s skipped", kind, exc_info=True)

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    @staticmethod
    def _project_rates(project: Any) -> tuple[str, dict[str, str]]:
        base = norm(getattr(project, "currency", "") or "")
        rates: dict[str, str] = {}
        raw = getattr(project, "fx_rates", None)
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and entry.get("code") and entry.get("rate"):
                    rates[norm(str(entry["code"]))] = str(entry["rate"]).strip()
        return base, rates

    async def quote(self, matrix: CommitmentMatrix, project: Any, from_ccy: str, to_ccy: str, on_date: date) -> FxQuote:
        base, rates = self._project_rates(project)
        return await resolve_quote(
            self.session,
            from_currency=from_ccy or base,
            to_currency=to_ccy or base,
            on_date=on_date,
            project_id=matrix.project_id,
            base=base,
            project_rates=rates,
            policy=matrix.fx_policy,
        )

    # ── matrix ─────────────────────────────────────────────────────────────

    async def get_matrix(self, project_id: uuid.UUID, *, lock: bool = False) -> CommitmentMatrix | None:
        return await self.repo.get_matrix(project_id, lock=lock)

    async def require_matrix(self, project_id: uuid.UUID, *, lock: bool = False) -> CommitmentMatrix:
        matrix = await self.repo.get_matrix(project_id, lock=lock)
        if matrix is None:
            raise not_found("matrix_missing")
        return matrix

    async def schedule_for(self, matrix: CommitmentMatrix) -> AuthoritySchedule:
        from app.modules.project_governance.catalogue_store import resolve_catalogue

        return await resolve_catalogue(
            self.session,
            matrix.schedule_source,
            matrix.schedule_id,
            matrix.schedule_version,
            kind=AUTHORITY_SCHEDULE_KIND,
        )

    async def abort_basis(self, source: str, code: str, version: int | None) -> AbortBasis:
        from app.modules.project_governance.catalogue_store import resolve_catalogue

        return await resolve_catalogue(self.session, source, code, version, kind=ABORT_BASIS_KIND)

    def schedule_currency(self, schedule: AuthoritySchedule, project: Any) -> str:
        return norm(schedule.currency) or norm(getattr(project, "currency", "") or "")

    async def set_matrix(
        self,
        project_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        tenant_id: str | None,
        schedule_source: str | None = None,
        schedule_id: str | None = None,
        schedule_version: int | None = None,
        enforcement: str | None = None,
        fx_policy: str | None = None,
        require_link: bool | None = None,
        legal_entity_id: uuid.UUID | None = None,
    ) -> CommitmentMatrix:
        """Create the matrix or change its settings. Pinning a new schedule version keeps decided releases as they are."""
        from app.modules.project_governance.catalogue_store import CatalogueStore
        from app.modules.project_governance.errors import GovernanceError

        project = await self._project(project_id)
        matrix = await self.repo.get_matrix(project_id, lock=True)
        if enforcement is not None and enforcement not in ENFORCEMENT:
            raise CommitmentError("enforcement_invalid", 422)
        if fx_policy is not None and fx_policy not in FX_POLICIES:
            raise CommitmentError("fx_policy_invalid", 422)
        source = schedule_source or (matrix.schedule_source if matrix else "shipped")
        sid = schedule_id or (
            matrix.schedule_id if matrix else default_schedule_id_for_country(getattr(project, "country_code", None))
        )
        before: dict[str, Any] = {}
        if matrix is None or schedule_id is not None or schedule_version is not None or schedule_source is not None:
            try:
                version = await CatalogueStore(self.session).assert_pinnable(
                    tenant_id, source, sid, schedule_version, kind=AUTHORITY_SCHEDULE_KIND
                )
            except GovernanceError as exc:
                raise CommitmentError(exc.code, exc.status_code) from exc
        else:
            version = matrix.schedule_version
        if matrix is None:
            matrix = await self.repo.add(
                CommitmentMatrix(
                    project_id=project_id,
                    schedule_source=source,
                    schedule_id=sid,
                    schedule_version=version,
                    enforcement=enforcement or "warn",
                    fx_policy=fx_policy or "fx_service_rate_set",
                    require_link=bool(require_link),
                    tier_routes={},
                    generated_routes={},
                    legal_entity_id=legal_entity_id,
                    created_by=actor_id,
                )
            )
            action = "matrix_created"
        else:
            before = {
                "schedule": f"{matrix.schedule_source}:{matrix.schedule_id}@{matrix.schedule_version}",
                "enforcement": matrix.enforcement,
                "fx_policy": matrix.fx_policy,
            }
            matrix.schedule_source, matrix.schedule_id, matrix.schedule_version = source, sid, version
            if enforcement is not None:
                matrix.enforcement = enforcement
            if fx_policy is not None:
                matrix.fx_policy = fx_policy
            if require_link is not None:
                matrix.require_link = require_link
            if legal_entity_id is not None:
                matrix.legal_entity_id = legal_entity_id
            action = "matrix_updated"
        await self.session.flush()
        after = {
            "schedule": f"{matrix.schedule_source}:{matrix.schedule_id}@{matrix.schedule_version}",
            "enforcement": matrix.enforcement,
            "fx_policy": matrix.fx_policy,
        }
        await self._audit(actor_id, "commitment_matrix", matrix.id, action, before_state=before or None, metadata=after)
        self._publish("matrix.set", {"project_id": str(project_id), **after})
        return matrix

    # ── authority assignments and generated tier routes ────────────────────

    async def put_assignments(
        self, project_id: uuid.UUID, rows: list[dict[str, Any]], *, actor_id: uuid.UUID, today: date
    ) -> list[AuthorityAssignment]:
        """Replace the project's assignments; then regenerate untouched tier routes."""
        from app.modules.project_governance.service import GovernanceService

        await self.require_matrix(project_id, lock=True)
        gov = GovernanceService(self.session)
        for r in rows:
            for key in ("user_id", "deputy_user_id"):
                if r.get(key) and not await gov.user_can_access_project(project_id, _uuid(r[key])):
                    raise CommitmentError("assignee_not_project_member", 422)
            vf, vt = _day(r.get("valid_from")), _day(r.get("valid_to"))
            if vf and vt and vt < vf:
                raise CommitmentError("assignment_window_inverted", 422)
        existing = await self.repo.list_assignments(project_id)
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()
        out = []
        for r in rows:
            out.append(
                await self.repo.add(
                    AuthorityAssignment(
                        project_id=project_id,
                        project_role=str(r["project_role"]),
                        user_id=_uuid(r["user_id"]),
                        deputy_user_id=_uuid(r.get("deputy_user_id")),
                        valid_from=_s(r.get("valid_from")),
                        valid_to=_s(r.get("valid_to")),
                    )
                )
            )
        await self._audit(
            actor_id, "commitment_matrix", project_id, "assignments_replaced", metadata={"count": len(out)}
        )
        await self.generate_routes(project_id, actor_id=actor_id, today=today, force=False)
        return out

    @staticmethod
    def _active(a: AuthorityAssignment, today: date) -> bool:
        vf, vt = _day(a.valid_from), _day(a.valid_to)
        return (vf is None or vf <= today) and (vt is None or today <= vt)

    async def _tier_users(self, project_id: uuid.UUID, schedule: AuthoritySchedule, today: date) -> dict[str, list]:
        assignments = [a for a in await self.repo.list_assignments(project_id) if self._active(a, today)]
        out: dict[str, list] = {}
        for t in schedule.tiers:
            if t.approver.kind == "project_role":
                out[t.code] = [a.user_id for a in assignments if a.project_role == t.approver.ref]
            elif t.approver.kind == "user":
                out[t.code] = [_uuid(t.approver.ref)]
            else:
                out[t.code] = [t.approver.ref]
        return out

    @staticmethod
    def _fingerprint(steps: list[Any]) -> str:
        parts = [
            (s.ordinal, _s(s.approver_user_id), s.approver_role, s.mode, s.sla_hours)
            for s in sorted(steps, key=lambda x: x.ordinal)
        ]
        return hashlib.sha256(json.dumps(parts, default=str).encode()).hexdigest()

    async def generate_routes(
        self, project_id: uuid.UUID, *, actor_id: uuid.UUID, today: date, force: bool
    ) -> dict[str, str]:
        """One approval route per tier from the schedule and the assignments (lead decision g).

        A route this module generated and nobody edited since is replaced; an
        edited one is kept and reported as ``edited`` unless ``force``. A tier
        nobody fills yet gets no route (``unfilled``). ``all`` tiers become one
        user step per assignee in order; ``any`` tiers one step for the first
        assignee (a stand-in is an approval_routes delegation).
        """
        from app.modules.approval_routes.schemas import RouteCreate, StepCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        matrix = await self.require_matrix(project_id, lock=True)
        schedule = await self.schedule_for(matrix)
        users = await self._tier_users(project_id, schedule, today)
        svc = ApprovalRouteService(self.session)
        report: dict[str, str] = {}
        tier_routes = dict(matrix.tier_routes or {})
        generated = dict(matrix.generated_routes or {})
        for tier in schedule.tiers:
            approvers = [u for u in users.get(tier.code, []) if u]
            if not approvers:
                report[tier.code] = "unfilled"
                continue
            if tier.approver.kind == "role":
                steps = [
                    StepCreate(
                        ordinal=1, approver_role=str(approvers[0]), mode=tier.steps_mode, sla_hours=tier.sla_hours
                    )
                ]
            else:
                chosen = approvers if tier.steps_mode == "all" else approvers[:1]
                steps = [
                    StepCreate(ordinal=i + 1, approver_user_id=u, mode="any", sla_hours=tier.sla_hours)
                    for i, u in enumerate(chosen)
                ]
            prev = generated.get(tier.code) or {}
            prev_id = _uuid(prev.get("route_id"))
            if prev_id is not None:
                try:
                    prev_route = await svc.get_route(prev_id)
                    prev_steps = await svc.list_steps(prev_id)
                except Exception:
                    prev_route, prev_steps = None, []
                if prev_route is not None:
                    edited = self._fingerprint(prev_steps) != prev.get("fingerprint") or prev_route.name != prev.get(
                        "name"
                    )
                    if edited and not force:
                        report[tier.code] = "edited"
                        continue
                    wanted = [(s.ordinal, _s(s.approver_user_id), s.approver_role) for s in steps]
                    have = [(s.ordinal, _s(s.approver_user_id), s.approver_role) for s in prev_steps]
                    if not edited and wanted == sorted(have) and prev_route.is_active:
                        report[tier.code] = "unchanged"
                        continue
                    prev_route.is_active = False
            name = f"commitment release: {tier.code}"
            route = await svc.create_route(
                RouteCreate(project_id=project_id, name=name, target_kind=TARGET_KIND, steps=steps),
                created_by=actor_id,
            )
            # No ``system_key``: it is unique across all projects and marks a
            # locked preset. The matrix tracks its routes in ``tier_routes``.
            new_steps = await svc.list_steps(route.id)
            generated[tier.code] = {
                "route_id": str(route.id),
                "fingerprint": self._fingerprint(new_steps),
                "name": name,
            }
            tier_routes[tier.code] = str(route.id)
            report[tier.code] = "replaced" if prev_id else "created"
        matrix.tier_routes = tier_routes
        matrix.generated_routes = generated
        await self.session.flush()
        await self._audit(actor_id, "commitment_matrix", matrix.id, "tier_routes_generated", metadata=report)
        return report

    async def pin_tier_route(
        self, project_id: uuid.UUID, tier_code: str, route_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> CommitmentMatrix:
        """A manager pins a hand-built route for one tier instead of the generated one."""
        from app.modules.approval_routes.service import ApprovalRouteService

        matrix = await self.require_matrix(project_id, lock=True)
        schedule = await self.schedule_for(matrix)
        if tier_code not in schedule.tier_order():
            raise CommitmentError("tier_unknown", 422)
        try:
            route = await ApprovalRouteService(self.session).get_route(route_id)
        except Exception as exc:
            raise not_found("route_not_found") from exc
        if route.target_kind != TARGET_KIND or route.project_id not in (None, project_id):
            raise not_found("route_not_found")
        routes = dict(matrix.tier_routes or {})
        routes[tier_code] = str(route_id)
        matrix.tier_routes = routes
        await self.session.flush()
        await self._audit(
            actor_id, "commitment_matrix", matrix.id, "tier_route_pinned", metadata={tier_code: str(route_id)}
        )
        return matrix

    # ── items ──────────────────────────────────────────────────────────────

    async def get_item(self, project_id: uuid.UUID, item_id: uuid.UUID, *, lock: bool = False) -> CommitmentItem:
        item = await self.repo.get_item(project_id, item_id, lock=lock)
        if item is None:
            raise not_found("item_not_found")
        return item

    def _may_edit(self, item: CommitmentItem, actor_id: uuid.UUID, role: str) -> bool:
        return role in _MANAGER_ROLES or item.owner_user_id in (None, actor_id) or item.created_by == actor_id

    async def _check_item_fields(
        self, project_id: uuid.UUID, data: dict[str, Any], schedule: AuthoritySchedule
    ) -> None:
        ctype = data.get("commitment_type")
        if ctype is not None and ctype not in schedule.type_codes():
            raise CommitmentError("commitment_type_unknown", 422)
        src = data.get("planned_source")
        if src is not None:
            if src not in PLANNED_SOURCES:
                raise CommitmentError("planned_source_invalid", 422)
            if src == "manual":
                if data.get("planned_manual_amount") in (None, "") or not data.get("currency"):
                    raise CommitmentError("manual_amount_needs_currency", 422)
                if _amount(data["planned_manual_amount"]) < 0:
                    raise CommitmentError("amount_invalid", 422)
            else:
                sid = _uuid(data.get("planned_source_id"))
                if sid is None or not await figures.planned_source_in_project(self.session, project_id, src, sid):
                    raise not_found("planned_source_not_found")
        if data.get("need_activity_id"):
            _ls, _sd, found = await figures.activity_dates(self.session, project_id, _uuid(data["need_activity_id"]))
            if not found:
                raise not_found("activity_not_found")
        if data.get("requisition_id"):
            if await figures.requisition_lead_time(self.session, project_id, _uuid(data["requisition_id"])) is None:
                raise not_found("requisition_not_found")
        for flag in data.get("flags") or []:
            if flag not in {f.code for f in schedule.novelty_flags}:
                raise CommitmentError("flag_unknown", 422)

    async def create_item(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> CommitmentItem:
        matrix = await self.require_matrix(project_id)
        schedule = await self.schedule_for(matrix)
        await self._check_item_fields(project_id, data, schedule)
        if data.get("planned_source") != "manual":
            data = {**data, "planned_manual_amount": None}
        fields = {
            k: v for k, v in data.items() if hasattr(CommitmentItem, k) and k not in ("id", "status", "project_id")
        }
        if fields.get("planned_manual_amount") is not None:
            fields["planned_manual_amount"] = _amount(fields["planned_manual_amount"])
        if fields.get("currency"):
            fields["currency"] = norm(fields["currency"])
        item = CommitmentItem(
            project_id=project_id,
            status="planned",
            attempt_no=1,
            owner_user_id=fields.pop("owner_user_id", None) or actor_id,
            created_by=actor_id,
            flags=list(fields.pop("flags", None) or []),
            **fields,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(item)
        except IntegrityError as exc:
            raise conflict("item_code_taken") from exc
        await self._audit(
            actor_id, "commitment_item", item.id, "created", to_status="planned", metadata={"code": item.code}
        )
        self._publish("item.created", {"project_id": str(project_id), "item_id": str(item.id)})
        return item

    _PATCHABLE = (
        "title",
        "commitment_type",
        "cost_line_id",
        "control_account_id",
        "cost_bearer_legal_entity_id",
        "funding_application_id",
        "risk_id",
        "governance_area_code",
        "gate_code",
        "deferred",
        "deferred_reason",
        "split_group",
        "owner_user_id",
        "planned_source",
        "planned_source_id",
        "planned_manual_amount",
        "currency",
        "need_activity_id",
        "requisition_id",
        "lead_time_days",
        "decision_buffer_days",
        "latest_decision_date_fixed",
        "flags",
    )

    async def update_item(
        self, project_id: uuid.UUID, item_id: uuid.UUID, changes: dict[str, Any], *, actor_id: uuid.UUID, role: str
    ) -> CommitmentItem:
        item = await self.get_item(project_id, item_id, lock=True)
        if not self._may_edit(item, actor_id, role):
            raise forbidden("not_item_owner")
        if item.status in ("aborted", "transferred"):
            raise conflict("item_closed")
        if "commitment_type" in changes and item.status != "planned":
            raise conflict("type_fixed_after_release")
        merged = {**changes}
        if "planned_source" in changes or "planned_manual_amount" in changes or "currency" in changes:
            merged.setdefault("planned_source", item.planned_source)
            merged.setdefault("planned_manual_amount", item.planned_manual_amount)
            merged.setdefault("currency", item.currency)
            merged.setdefault("planned_source_id", item.planned_source_id)
        matrix = await self.require_matrix(project_id)
        await self._check_item_fields(project_id, merged, await self.schedule_for(matrix))
        if changes.get("deferred") and not str(changes.get("deferred_reason") or item.deferred_reason).strip():
            raise CommitmentError("deferral_needs_reason", 422)
        before = {k: _s(getattr(item, k)) for k in changes if k in self._PATCHABLE}
        for k, v in changes.items():
            if k not in self._PATCHABLE:
                continue
            if k == "planned_manual_amount" and v is not None:
                v = _amount(v)
            if k == "currency" and v:
                v = norm(v)
            setattr(item, k, v)
        if item.planned_source != "manual":
            item.planned_manual_amount = None
        await self.session.flush()
        await self._audit(
            actor_id,
            "commitment_item",
            item.id,
            "updated",
            before_state=before,
            metadata={k: _s(getattr(item, k)) for k in before},
        )
        return item

    async def set_hold(
        self, project_id: uuid.UUID, item_id: uuid.UUID, *, hold: bool, actor_id: uuid.UUID, reason: str
    ) -> CommitmentItem:
        item = await self.get_item(project_id, item_id, lock=True)
        if hold:
            if item.status not in WORKING:
                raise conflict("invalid_transition")
            item.status_before = item.status
            await self._fsm(item, "on_hold", actor_id, reason)
        else:
            if item.status != "on_hold":
                raise conflict("invalid_transition")
            target = item.status_before or "planned"
            item.status_before = None
            await self._fsm(item, target, actor_id, reason)
        return item

    # ── links ──────────────────────────────────────────────────────────────

    async def add_link(
        self, project_id: uuid.UUID, item_id: uuid.UUID, kind: str, document_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> CommitmentLink:
        """Count a document in this item. Another project's document is 404; a document counts once (409)."""
        item = await self.get_item(project_id, item_id, lock=True)
        if kind not in figures.LINK_KINDS:
            raise CommitmentError("link_kind_invalid", 422)
        if kind == "contingency_drawdown":
            raise CommitmentError("link_kind_not_supported", 422)
        if not await figures.document_in_project(self.session, project_id, kind, document_id):
            raise not_found("document_not_found")
        if item.status in ("aborted", "transferred", "closed"):
            raise conflict("item_closed")
        if await self.repo.find_link(project_id, kind, document_id) is not None:
            raise conflict("document_linked_elsewhere")
        if kind in ("change_order", "variation_order") and item.commitment_type != "change":
            await self._refuse_change_double_count(project_id, item, kind, document_id)
        link = CommitmentLink(
            project_id=project_id, item_id=item.id, kind=kind, document_id=document_id, created_by=actor_id
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(link)
        except IntegrityError as exc:
            raise conflict("document_linked_elsewhere") from exc
        await self._audit(
            actor_id, "commitment_item", item.id, "link_added", metadata={"kind": kind, "document_id": str(document_id)}
        )
        await self.recompute_item(project_id, item.id, actor_id=actor_id)
        return link

    async def _refuse_change_double_count(
        self, project_id: uuid.UUID, item: CommitmentItem, kind: str, document_id: uuid.UUID
    ) -> None:
        """A change linked as a delta must sit on the item of its own contract (rule 7)."""
        figs = await figures.link_figures(
            self.session,
            project_id,
            [CommitmentLink(id=uuid.uuid4(), item_id=item.id, kind=kind, document_id=document_id)],
            basis="net",
        )
        contract_id = figs[0].contract_id if figs else None
        if contract_id is None:
            return
        host = await self.repo.find_link(project_id, "contract", contract_id)
        if host is not None and host.item_id != item.id:
            raise conflict("change_belongs_to_contract_item")

    async def remove_link(
        self, project_id: uuid.UUID, item_id: uuid.UUID, link_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        item = await self.get_item(project_id, item_id, lock=True)
        links = [lk for lk in await self.repo.list_links(project_id, [item.id]) if lk.id == link_id]
        if not links:
            raise not_found("link_not_found")
        await self.session.delete(links[0])
        await self.session.flush()
        await self._audit(
            actor_id,
            "commitment_item",
            item.id,
            "link_removed",
            metadata={"kind": links[0].kind, "document_id": str(links[0].document_id)},
        )
        await self.recompute_item(project_id, item.id, actor_id=actor_id)

    # ── preconditions ──────────────────────────────────────────────────────

    async def add_precondition(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        kind: str,
        ref_id: str | None,
        text: str,
        actor_id: uuid.UUID,
    ) -> CommitmentPrecondition:
        item = await self.get_item(project_id, item_id)
        if kind not in PRECONDITION_KINDS:
            raise CommitmentError("precondition_kind_invalid", 422)
        if kind in ("gate_decided", "frame_document_binding", "funding_approved") and not ref_id:
            raise CommitmentError("precondition_needs_ref", 422)
        row = await self.repo.add(
            CommitmentPrecondition(
                project_id=project_id, item_id=item.id, kind=kind, ref_id=ref_id, text=text, state="open"
            )
        )
        await self._audit(
            actor_id, "commitment_item", item.id, "precondition_added", metadata={"kind": kind, "ref": ref_id}
        )
        return row

    async def confirm_precondition(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        precondition_id: uuid.UUID,
        *,
        met: bool,
        evidence_ref: str,
        actor_id: uuid.UUID,
    ) -> CommitmentPrecondition:
        row = await self.repo.get_precondition(project_id, item_id, precondition_id)
        if row is None:
            raise not_found("precondition_not_found")
        if row.kind not in STORED_PRECONDITIONS:
            raise CommitmentError("precondition_is_computed", 422)
        if met and row.kind == "public_commitment_appropriation" and not evidence_ref.strip():
            raise CommitmentError("precondition_needs_evidence", 422)
        row.state = "met" if met else "open"
        row.evidence_ref = evidence_ref
        row.confirmed_by = actor_id if met else None
        row.confirmed_at = datetime.now(UTC) if met else None
        await self.session.flush()
        await self._audit(
            actor_id,
            "commitment_item",
            item_id,
            "precondition_confirmed" if met else "precondition_reopened",
            metadata={"precondition_id": str(row.id)},
        )
        return row

    async def precondition_states(
        self, project_id: uuid.UUID, rows: list[CommitmentPrecondition], *, planned: Decimal | None, cumulative: Decimal
    ) -> list[dict[str, Any]]:
        """Each precondition with its state; linked kinds are read from their modules now."""
        out = []
        for p in rows:
            state = p.state
            if p.kind == "gate_decided":
                state = await self._gate_state(project_id, p.ref_id)
            elif p.kind == "frame_document_binding":
                state = await self._document_state(project_id, p.ref_id)
            elif p.kind == "funding_approved":
                state = await self._funding_state(project_id, p.ref_id)
            elif p.kind == "budget_available":
                state = "met" if planned is not None and cumulative <= planned else "open"
            out.append(
                {
                    "id": str(p.id),
                    "kind": p.kind,
                    "ref_id": p.ref_id,
                    "text": p.text,
                    "state": state,
                    "evidence_ref": p.evidence_ref,
                    "confirmed_by": _s(p.confirmed_by),
                    "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
                }
            )
        return out

    async def _gate_state(self, project_id: uuid.UUID, gate_code: str | None) -> str:
        from app.modules.project_governance.models import GovernanceGate

        stmt = select(GovernanceGate).where(GovernanceGate.project_id == project_id, GovernanceGate.code == gate_code)
        gates = list((await self.session.execute(stmt)).scalars().all())
        ok = any(g.status == "decided" and (g.last_outcome or "").startswith("go") for g in gates if not g.historic)
        return "met" if ok else "open"

    async def _document_state(self, project_id: uuid.UUID, doc_id: str | None) -> str:
        from app.modules.project_governance.models import GovernanceDocument

        try:
            row = await self.session.get(GovernanceDocument, uuid.UUID(str(doc_id)))
        except (TypeError, ValueError):
            return "open"
        return "met" if row is not None and row.project_id == project_id and row.status == "binding" else "open"

    async def _funding_state(self, project_id: uuid.UUID, app_id: str | None) -> str:
        from app.modules.funding.models import FundingApplication

        try:
            row = await self.session.get(FundingApplication, uuid.UUID(str(app_id)))
        except (TypeError, ValueError):
            return "open"
        return "met" if row is not None and row.project_id == project_id and row.status == "approved" else "open"

    # ── derived figures ────────────────────────────────────────────────────

    async def committed_for_items(
        self, matrix: CommitmentMatrix, project: Any, schedule: AuthoritySchedule, *, on_date: date
    ) -> tuple[dict[uuid.UUID, list[figures.LinkFigure]], dict[uuid.UUID, Decimal | None], dict[uuid.UUID, str | None]]:
        """``(figures per item, committed in schedule currency or None, reason)`` over the whole project."""
        links = await self.repo.list_links(matrix.project_id)
        figs = await figures.link_figures(self.session, matrix.project_id, links, basis=schedule.basis)
        target = self.schedule_currency(schedule, project)
        per_item: dict[uuid.UUID, list[figures.LinkFigure]] = {}
        for f in figs:
            per_item.setdefault(f.item_id, []).append(f)
        committed: dict[uuid.UUID, Decimal | None] = {}
        reason: dict[uuid.UUID, str | None] = {}
        for item_id, fl in per_item.items():
            total = ZERO
            missing = None
            for f in fl:
                if not f.amount:
                    continue
                try:
                    total += (await self.quote(matrix, project, f.currency, target, on_date)).apply(f.amount)
                except FxRateMissing:
                    missing = "fx_rate_missing"
            committed[item_id] = None if missing else total
            reason[item_id] = missing
        return per_item, committed, reason

    @staticmethod
    def released_in_schedule_currency(releases: list[ReleaseDecision]) -> Decimal:
        return sum((r.amount_in_schedule_currency for r in releases if r.outcome == "released"), ZERO)

    async def item_views(
        self,
        project_id: uuid.UUID,
        *,
        today: date,
        item_ids: list[uuid.UUID] | None = None,
        with_exposure: bool = False,
    ) -> dict[str, Any]:
        """Items with every derived figure, flag and (optionally) abort exposure, plus base-currency totals."""
        matrix = await self.require_matrix(project_id)
        project = await self._project(project_id)
        schedule = await self.schedule_for(matrix)
        sched_ccy = self.schedule_currency(schedule, project)
        base = norm(project.currency)
        items = await self.repo.list_items(project_id)
        if item_ids is not None:
            items = [i for i in items if i.id in set(item_ids)]
        ids = [i.id for i in items]
        releases = await self.repo.list_releases(project_id, ids)
        pre = await self.repo.list_preconditions(project_id, ids)
        terms = await self.repo.list_abort_terms(project_id, ids) if with_exposure else []
        per_item, committed, committed_reason = await self.committed_for_items(matrix, project, schedule, on_date=today)
        tol = schedule.variation_tolerance
        views = []
        totals = {"planned": ZERO, "released": ZERO, "committed": ZERO}
        unconverted: set[str] = set()
        currencies: set[str] = set()
        for item in items:
            rel = [r for r in releases if r.item_id == item.id]
            released = self.released_in_schedule_currency(rel)
            planned, planned_ccy, planned_note = await figures.planned_amount(self.session, item, base)
            late, start, _found = await figures.activity_dates(self.session, project_id, item.need_activity_id)
            lead = item.lead_time_days
            if lead is None:
                lead = await figures.requisition_lead_time(self.session, project_id, item.requisition_id)
            dd = ev.latest_decision_date(
                late_start=late,
                start_date=start,
                fixed=item.latest_decision_date_fixed,
                lead_time_days=lead,
                decision_buffer_days=item.decision_buffer_days,
            )
            planned_sched = None
            if planned is not None:
                try:
                    planned_sched = (await self.quote(matrix, project, planned_ccy, sched_ccy, today)).apply(planned)
                except FxRateMissing:
                    planned_sched = None
            required_now = None
            if planned_sched is not None and planned_sched > 0 and item.commitment_type in schedule.type_codes():
                r = ev.required_tier(schedule, item.commitment_type, max(planned_sched, released), item.flags or [])
                required_now = r.tier_code or ev.ESCALATE_OUTSIDE
            comm = committed.get(item.id, ZERO)
            ceiling = ev.tolerance_ceiling(released, parse_amount(tol.absolute), parse_amount(tol.percent))
            pre_states = await self.precondition_states(
                project_id,
                [p for p in pre if p.item_id == item.id],
                planned=planned_sched,
                cumulative=released,
            )
            view = {
                "id": str(item.id),
                "code": item.code,
                "title": item.title,
                "commitment_type": item.commitment_type,
                "status": item.status,
                "attempt_no": item.attempt_no,
                "flags": list(item.flags or []),
                "cost_line_id": _s(item.cost_line_id),
                "control_account_id": _s(item.control_account_id),
                "cost_bearer_legal_entity_id": _s(item.cost_bearer_legal_entity_id or matrix.legal_entity_id),
                "funding_application_id": _s(item.funding_application_id),
                "risk_id": _s(item.risk_id),
                "governance_area_code": item.governance_area_code,
                "gate_code": item.gate_code,
                "deferred": item.deferred,
                "deferred_reason": item.deferred_reason,
                "split_group": item.split_group,
                "owner_user_id": _s(item.owner_user_id),
                "planned_source": item.planned_source,
                "planned_source_id": _s(item.planned_source_id),
                "need_activity_id": _s(item.need_activity_id),
                "requisition_id": _s(item.requisition_id),
                "lead_time_days": item.lead_time_days,
                "decision_buffer_days": item.decision_buffer_days,
                "latest_decision_date_fixed": item.latest_decision_date_fixed,
                "planned": {"amount": _money_str(planned), "currency": planned_ccy, "note": planned_note},
                "schedule_currency": sched_ccy,
                "planned_in_schedule_currency": _money_str(planned_sched),
                "released": _money_str(released),
                "committed": _money_str(comm),
                "committed_reason": committed_reason.get(item.id),
                "release_ceiling_with_tolerance": _money_str(ceiling),
                "over_release": comm is not None and comm > ceiling,
                "required_tier_for_planned": required_now,
                "latest_decision_date": dd.latest.isoformat() if dd.latest else None,
                "date_basis": dd.basis,
                "decision_overdue": ev.decision_overdue(dd.latest, today, item.status, released),
                "preconditions": pre_states,
                "open_preconditions": sum(1 for p in pre_states if p["state"] != "met"),
                "links": [f.as_dict() for f in per_item.get(item.id, [])],
                "pending_release_id": next((str(r.id) for r in rel if r.outcome == "pending"), None),
            }
            if with_exposure:
                view["exposure"] = await self._exposure_for(
                    item, per_item.get(item.id, []), [t for t in terms if t.item_id == item.id], matrix, project, today
                )
            views.append(view)
            currencies.add(sched_ccy)
            for key, value in (("planned", planned_sched), ("released", released), ("committed", comm)):
                if value is None:
                    unconverted.add(key)
                    continue
                try:
                    totals[key] += (await self.quote(matrix, project, sched_ccy, base, today)).apply(value)
                except FxRateMissing:
                    unconverted.add(key)
            currencies.add(planned_ccy)
        return {
            "items": views,
            "totals": {
                "currency": base,
                **{k: _money_str(v) for k, v in totals.items()},
                "mixed_currency": len({c for c in currencies if c}) > 1,
                "incomplete": sorted(unconverted),
            },
        }

    # ── abort exposure ─────────────────────────────────────────────────────

    async def _exposure_for(
        self,
        item: CommitmentItem,
        figs: list[figures.LinkFigure],
        terms_rows: list[AbortTerms],
        matrix: CommitmentMatrix,
        project: Any,
        as_of: date,
    ) -> dict[str, Any]:
        base = norm(project.currency)
        committed = ZERO
        try:
            for f in figs:
                if f.amount:
                    committed += (await self.quote(matrix, project, f.currency, base, as_of)).apply(f.amount)
            raw_sunk = await figures.sunk_parts(self.session, figs)
            ccy = next((f.currency for f in figs if f.kind == "contract" and f.found), base)
            q = await self.quote(matrix, project, ccy or base, base, as_of)
            sunk = {k: q.apply(v) for k, v in raw_sunk.items()}
        except FxRateMissing:
            return {"residual_loss": None, "reason": "fx_rate_missing", "currency": base}
        row = next((t for t in terms_rows if t.scope == "item"), None) or (terms_rows[0] if terms_rows else None)
        basis = None
        terms = None
        if row is not None:
            if row.basis_code:
                try:
                    basis = await self.abort_basis(row.basis_source, row.basis_code, row.basis_version)
                except CommitmentError:
                    basis = None
                except Exception:
                    basis = None
            terms = TermsInput(
                basis_code=row.basis_code,
                cancellation_schedule=tuple(_schedule_entry(e) for e in row.cancellation_schedule or []),
                transfer_value=row.transfer_value_estimate,
                salvage_value=row.salvage_value_estimate,
                saved_cost=row.saved_cost_estimate,
                other_charge=row.other_charge_estimate,
                parameters={k: str(v) for k, v in (row.parameters or {}).items()},
            )
        e = compute_exposure(
            committed=committed,
            sunk_parts=sunk,
            terms=terms,
            basis=basis,
            as_of=as_of,
            progress_pct=row.progress_pct if row is not None else None,
        )
        out = e.as_dict()
        out["currency"] = base
        out["as_of"] = as_of.isoformat()
        out["basis_code"] = row.basis_code if row is not None else None
        out["transferable"] = row.transferable if row is not None else None
        if item.status in ("planned", "release_requested") and not committed:
            out["note"] = "nothing_committed"
        return out

    async def exposure(self, project_id: uuid.UUID, *, as_of: date) -> dict[str, Any]:
        """Per-item exposure and the project total, with the count of items whose residual is unknown."""
        data = await self.item_views(project_id, today=as_of, with_exposure=True)
        total = ZERO
        unknown = 0
        rows = []
        for v in data["items"]:
            e = v["exposure"]
            if e.get("residual_loss") is None:
                unknown += 1
            else:
                total += Decimal(e["residual_loss"])
            rows.append({"item_id": v["id"], "code": v["code"], "status": v["status"], **e})
        return {
            "as_of": as_of.isoformat(),
            "currency": data["totals"]["currency"],
            "items": rows,
            "total_residual_loss": str(total),
            "unknown_count": unknown,
        }

    async def save_scenario(
        self, project_id: uuid.UUID, *, as_of: date, label: str, actor_id: uuid.UUID
    ) -> AbortScenario:
        payload = await self.exposure(project_id, as_of=as_of)
        row = await self.repo.add(
            AbortScenario(
                project_id=project_id, as_of=as_of.isoformat(), label=label, payload=payload, created_by=actor_id
            )
        )
        await self._audit(
            actor_id, "commitment_matrix", project_id, "abort_scenario_saved", metadata={"scenario_id": str(row.id)}
        )
        return row

    async def put_abort_terms(
        self, project_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID, role: str
    ) -> AbortTerms:
        item = await self.get_item(project_id, item_id, lock=True)
        if not self._may_edit(item, actor_id, role):
            raise forbidden("not_item_owner")
        scope = "item"
        if data.get("link_id"):
            link_id = _uuid(data["link_id"])
            if link_id not in {lk.id for lk in await self.repo.list_links(project_id, [item.id])}:
                raise not_found("link_not_found")
            scope = str(link_id)
        if data.get("basis_code"):
            try:
                basis = await self.abort_basis(
                    data.get("basis_source") or "shipped", data["basis_code"], data.get("basis_version")
                )
            except Exception as exc:
                raise CommitmentError("abort_basis_unknown", 422) from exc
            data = {**data, "basis_version": basis.version}
        for entry in data.get("cancellation_schedule") or []:
            try:
                _schedule_entry(entry)
            except (KeyError, ValueError, TypeError) as exc:
                raise CommitmentError("cancellation_schedule_invalid", 422) from exc
        if data.get("transferable", "no") not in ("no", "to_project", "resale"):
            raise CommitmentError("transferable_invalid", 422)
        row = await self.repo.get_abort_terms(item.id, scope)
        before = None
        if row is None:
            row = AbortTerms(project_id=project_id, item_id=item.id, scope=scope)
            self.session.add(row)
        else:
            before = {"basis_code": row.basis_code, "transferable": row.transferable}
        for key in (
            "basis_code",
            "basis_source",
            "basis_version",
            "cancellation_schedule",
            "parameters",
            "transferable",
            "notice_days",
            "source_note",
        ):
            if key in data:
                setattr(
                    row,
                    key,
                    data[key]
                    if data[key] is not None or key in ("basis_code", "basis_version", "notice_days")
                    else getattr(row, key),
                )
        for key in (
            "transfer_value_estimate",
            "salvage_value_estimate",
            "saved_cost_estimate",
            "other_charge_estimate",
            "progress_pct",
        ):
            if key in data:
                setattr(row, key, None if data[key] in (None, "") else _amount(data[key]))
        row.entered_by = actor_id
        row.entered_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(
            actor_id,
            "commitment_item",
            item.id,
            "abort_terms_set",
            before_state=before,
            metadata={"scope": scope, "basis_code": row.basis_code, "transferable": row.transferable},
        )
        return row

    # ── releases ───────────────────────────────────────────────────────────

    async def _group_released(self, item: CommitmentItem) -> Decimal:
        if not item.split_group:
            return ZERO
        others = [i.id for i in await self.repo.items_in_group(item.project_id, item.split_group) if i.id != item.id]
        return self.released_in_schedule_currency(await self.repo.list_releases(item.project_id, others))

    async def preview_release(
        self, project_id: uuid.UUID, item_id: uuid.UUID, amount: Any, currency: str | None, *, today: date
    ) -> dict[str, Any]:
        """What a release request would need, without writing: tier, approvers, FX, open preconditions."""
        item = await self.get_item(project_id, item_id)
        return await self._evaluate(item, _amount(amount), currency, today=today)

    async def _evaluate(
        self, item: CommitmentItem, amount: Decimal, currency: str | None, *, today: date
    ) -> dict[str, Any]:
        from app.modules.approval_routes.service import ApprovalRouteService

        if amount <= 0:
            raise CommitmentError("amount_not_positive", 422)
        matrix = await self.require_matrix(item.project_id)
        project = await self._project(item.project_id)
        schedule = await self.schedule_for(matrix)
        sched_ccy = self.schedule_currency(schedule, project)
        ccy = norm(currency) or norm(item.currency) or norm(project.currency)
        try:
            q = await self.quote(matrix, project, ccy, sched_ccy, today)
        except FxRateMissing as exc:
            raise CommitmentError("fx_rate_missing", 422, detail=f"{exc.from_currency}->{exc.to_currency}") from exc
        converted = q.apply(amount)
        releases = await self.repo.list_releases(item.project_id, [item.id])
        released = self.released_in_schedule_currency(releases)
        group = await self._group_released(item)
        evaluated = ev.evaluated_amount(
            request=converted,
            released_on_item=released,
            released_on_group_others=group,
            aggregation=schedule.aggregation,
        )
        tier = ev.required_tier(schedule, item.commitment_type, evaluated, item.flags or [])
        route_tier = tier.tier_code or (schedule.tiers[-1].code if tier.escalate_outside else None)
        route_id = _uuid((matrix.tier_routes or {}).get(route_tier)) if route_tier else None
        approvers: list[str] = []
        if route_id is not None:
            try:
                approvers = [
                    _s(s.approver_user_id) or f"role:{s.approver_role}"
                    for s in await ApprovalRouteService(self.session).list_steps(route_id)
                ]
            except Exception:
                route_id = None
        planned, planned_ccy, _note = await figures.planned_amount(self.session, item, norm(project.currency))
        planned_sched = None
        if planned is not None:
            try:
                planned_sched = (await self.quote(matrix, project, planned_ccy, sched_ccy, today)).apply(planned)
            except FxRateMissing:
                planned_sched = None
        pre = await self.precondition_states(
            item.project_id,
            await self.repo.list_preconditions(item.project_id, [item.id]),
            planned=planned_sched,
            cumulative=released + converted,
        )
        return {
            "matrix": matrix,
            "schedule": schedule,
            "quote": q,
            "amount": amount,
            "currency": ccy,
            "schedule_currency": sched_ccy,
            "converted": converted,
            "released_before": released,
            "group_released": group,
            "evaluated": evaluated,
            "tier": tier,
            "route_tier": route_tier,
            "route_id": route_id,
            "approvers": approvers,
            "planned_in_schedule_currency": planned_sched,
            "preconditions": pre,
            "open_preconditions": [p for p in pre if p["state"] != "met"],
        }

    @staticmethod
    def evaluation_out(e: dict[str, Any]) -> dict[str, Any]:
        t = e["tier"]
        return {
            "amount": str(e["amount"]),
            "currency": e["currency"],
            "schedule_currency": e["schedule_currency"],
            "amount_in_schedule_currency": str(e["converted"]),
            "fx": e["quote"].as_dict(),
            "released_before": str(e["released_before"]),
            "group_released": str(e["group_released"]),
            "evaluated_amount": str(e["evaluated"]),
            "required_tier": t.tier_code,
            "escalate_outside": t.escalate_outside,
            "band_code": t.band_code,
            "raised_by": list(t.raised_by),
            "route_tier": e["route_tier"],
            "route_id": _s(e["route_id"]),
            "approvers": e["approvers"],
            "schedule": f"{e['matrix'].schedule_source}:{e['matrix'].schedule_id}@{e['matrix'].schedule_version}",
            "open_preconditions": e["open_preconditions"],
        }

    async def _expired_assignment_in_route(
        self, matrix: CommitmentMatrix, schedule: AuthoritySchedule, tier_code: str, route_id: uuid.UUID, today: date
    ) -> bool:
        """Rule 9: a generated route whose pinned approver no longer holds a valid assignment."""
        from app.modules.approval_routes.service import ApprovalRouteService

        tier = schedule.tier(tier_code)
        if tier.approver.kind != "project_role":
            return False
        generated = (matrix.generated_routes or {}).get(tier_code) or {}
        if generated.get("route_id") != str(route_id):
            return False
        valid = {
            a.user_id
            for a in await self.repo.list_assignments(matrix.project_id)
            if a.project_role == tier.approver.ref and self._active(a, today)
        }
        steps = await ApprovalRouteService(self.session).list_steps(route_id)
        return any(s.approver_user_id is not None and s.approver_user_id not in valid for s in steps)

    async def request_release(
        self,
        project_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        amount: Any,
        currency: str | None,
        tranche_note: str,
        external_approval_ref: str,
        actor_id: uuid.UUID,
        today: date,
    ) -> ReleaseDecision:
        """Rule 2 with rules 4, 18 and 19: evaluate the authority and start the tier's approval."""
        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        item = await self.get_item(project_id, item_id, lock=True)
        if item.status == "release_requested":
            raise conflict("release_pending")
        if item.status not in REQUESTABLE:
            raise conflict("invalid_transition")
        pending = [r for r in await self.repo.list_releases(project_id, [item.id]) if r.outcome == "pending"]
        if pending:
            raise conflict("release_pending")
        e = await self._evaluate(item, _amount(amount), currency, today=today)
        matrix, schedule, tier = e["matrix"], e["schedule"], e["tier"]
        if tier.escalate_outside and not external_approval_ref.strip():
            raise CommitmentError("external_approval_required", 422)
        if e["open_preconditions"] and matrix.enforcement == "block":
            raise CommitmentError(
                "preconditions_open",
                422,
                violations=[
                    {"code": "precondition_open", "ref": p["id"], "kind": p["kind"]} for p in e["open_preconditions"]
                ],
            )
        if e["route_id"] is None:
            raise CommitmentError("no_route_for_tier", 422, detail=e["route_tier"])
        if await self._expired_assignment_in_route(matrix, schedule, e["route_tier"], e["route_id"], today):
            raise conflict("assignment_expired")
        route_tier = schedule.tier(e["route_tier"])
        if route_tier.four_eyes and str(actor_id) in set(e["approvers"]):
            raise forbidden("four_eyes_requester_is_approver")
        links = await self.repo.list_links(project_id, [item.id])
        snapshot = {
            "evaluation": self.evaluation_out(e),
            "links": [{"kind": lk.kind, "document_id": str(lk.document_id)} for lk in links],
            "preconditions": e["preconditions"],
            "four_eyes": route_tier.four_eyes,
            "requested_at": datetime.now(UTC).isoformat(),
        }
        decision = ReleaseDecision(
            project_id=project_id,
            item_id=item.id,
            attempt=item.attempt_no,
            requested_amount=e["amount"],
            currency=e["currency"],
            schedule_currency=e["schedule_currency"],
            amount_in_schedule_currency=e["converted"],
            fx_rate_used=str(e["quote"].rate),
            fx_rate_date=e["quote"].as_of.isoformat() if e["quote"].as_of else None,
            fx_source=e["quote"].source,
            evaluated_amount=e["evaluated"],
            cumulative_after=e["released_before"] + e["converted"],
            required_tier=tier.tier_code,
            escalate_outside=tier.escalate_outside,
            external_approval_ref=external_approval_ref,
            schedule_source=matrix.schedule_source,
            schedule_id=matrix.schedule_id,
            schedule_version=matrix.schedule_version,
            outcome="pending",
            requested_by=actor_id,
            snapshot=snapshot,
            tranche_note=tranche_note,
        )
        try:
            async with self.session.begin_nested():
                await self.repo.add(decision)
        except IntegrityError as exc:
            raise conflict("release_pending") from exc
        instance = await ApprovalRouteService(self.session).start_instance(
            InstanceCreate(route_id=e["route_id"], target_kind=TARGET_KIND, target_id=decision.id), started_by=actor_id
        )
        decision.approval_instance_id = instance.id
        item.status_before = item.status
        await self._fsm(item, "release_requested", actor_id, attempt=item.attempt_no, release_id=str(decision.id))
        await self._audit(
            actor_id,
            "commitment_release",
            decision.id,
            "requested",
            metadata={
                "item_id": str(item.id),
                "tier": tier.tier_code,
                "amount": str(e["converted"]),
                "warnings": [p["kind"] for p in e["open_preconditions"]],
            },
        )
        self._publish(
            "release.requested",
            {"project_id": str(project_id), "item_id": str(item.id), "release_id": str(decision.id)},
        )
        return decision

    async def withdraw_release(
        self, project_id: uuid.UUID, item_id: uuid.UUID, *, actor_id: uuid.UUID, role: str, reason: str
    ) -> ReleaseDecision:
        """Rule 12: the requester (or a manager) withdraws a pending request; the instance is cancelled."""
        from app.modules.approval_routes.service import ApprovalRouteService

        item = await self.get_item(project_id, item_id, lock=True)
        pending = [r for r in await self.repo.list_releases(project_id, [item.id]) if r.outcome == "pending"]
        if not pending:
            raise conflict("no_pending_release")
        decision = pending[0]
        if decision.requested_by != actor_id and role not in _MANAGER_ROLES:
            raise forbidden("not_requester")
        if decision.approval_instance_id is not None:
            try:
                await ApprovalRouteService(self.session).cancel_instance(
                    decision.approval_instance_id, actor_id=actor_id, reason=reason or "withdrawn"
                )
            except Exception:
                logger.debug("commitment: instance %s already closed", decision.approval_instance_id, exc_info=True)
        await self._close_decision(item, decision, "withdrawn", decided_by=actor_id, rationale=reason)
        return decision

    async def _close_decision(
        self,
        item: CommitmentItem,
        decision: ReleaseDecision,
        outcome: str,
        *,
        decided_by: uuid.UUID | None,
        rationale: str = "",
        on_behalf_of: uuid.UUID | None = None,
    ) -> None:
        if decision.outcome != "pending":
            raise conflict("release_decided")
        decision.outcome = outcome
        decision.decided_by = decided_by
        decision.on_behalf_of = on_behalf_of
        decision.decided_at = datetime.now(UTC)
        decision.rationale = rationale or ""
        if outcome == "released":
            target = await self._released_state(item, decision)
        else:
            target = item.status_before or "planned"
            item.attempt_no += 1
        item.status_before = None
        await self._fsm(item, target, decided_by, rationale or None, release_id=str(decision.id), outcome=outcome)
        await self._audit(
            decided_by,
            "commitment_release",
            decision.id,
            outcome,
            metadata={"item_id": str(item.id), "on_behalf_of": _s(on_behalf_of)},
        )
        self._publish(
            f"release.{outcome}",
            {"project_id": str(item.project_id), "item_id": str(item.id), "release_id": str(decision.id)},
        )
        if outcome in ("released", "rejected"):
            await self._notify(
                decision.requested_by,
                f"release_{outcome}",
                item,
                {"project_id": str(item.project_id), "code": item.code},
            )
        if outcome == "released":
            await self.recompute_item(item.project_id, item.id, actor_id=decided_by, locked=item)

    async def _released_state(self, item: CommitmentItem, decision: ReleaseDecision) -> str:
        """``released`` when the cumulative release covers the planned amount, else ``partially_released`` (rule 5)."""
        matrix = await self.require_matrix(item.project_id)
        project = await self._project(item.project_id)
        schedule = await self.schedule_for(matrix)
        planned, ccy, _n = await figures.planned_amount(self.session, item, norm(project.currency))
        if planned is None:
            return "released"
        try:
            on = _day(decision.fx_rate_date) or datetime.now(UTC).date()
            planned_sched = (
                await self.quote(matrix, project, ccy, self.schedule_currency(schedule, project), on)
            ).apply(planned)
        except FxRateMissing:
            return "released"
        return "released" if decision.cumulative_after >= planned_sched else "partially_released"

    async def apply_route_verdict(
        self,
        release_id: uuid.UUID,
        *,
        instance_id: uuid.UUID | None,
        verdict: str,
        decided_by: Any,
        comment: str | None = None,
    ) -> bool:
        """The approval route decided. Idempotent: acts once, only on the instance the request started.

        Returns True when the decision was applied.
        """
        decision = await self.repo.get_release(release_id)
        if decision is None:
            return False
        item = await self.get_item(decision.project_id, decision.item_id, lock=True)
        decision = await self.repo.get_release(release_id, lock=True)
        if decision is None or decision.outcome != "pending":
            return False
        if instance_id is not None and decision.approval_instance_id != instance_id:
            return False
        decider = _uuid(decided_by)
        if verdict == "approved":
            if decision.snapshot.get("four_eyes") and decider is not None and decider == decision.requested_by:
                await self._close_decision(
                    item, decision, "rejected", decided_by=decider, rationale="four_eyes_violation"
                )
                return True
            on_behalf = await self._on_behalf_of(decision, decider)
            await self._close_decision(
                item, decision, "released", decided_by=decider, on_behalf_of=on_behalf, rationale=comment or ""
            )
        elif verdict == "rejected":
            await self._close_decision(item, decision, "rejected", decided_by=decider, rationale=comment or "")
        elif verdict == "cancelled":
            await self._close_decision(
                item, decision, "withdrawn", decided_by=decider, rationale=comment or "cancelled"
            )
        else:
            return False
        return True

    async def _on_behalf_of(self, decision: ReleaseDecision, decider: uuid.UUID | None) -> uuid.UUID | None:
        """Rule 9: when a delegate decided, name the approver the step was pinned to."""
        from app.modules.approval_routes.service import ApprovalRouteService

        if decision.approval_instance_id is None or decider is None:
            return None
        try:
            svc = ApprovalRouteService(self.session)
            instance = await svc.get_instance(decision.approval_instance_id)
            steps = await svc.list_steps(instance.route_id)
        except Exception:
            return None
        pinned = {s.approver_user_id for s in steps if s.approver_user_id is not None}
        if not pinned or decider in pinned:
            return None
        return sorted(pinned, key=str)[0] if len(pinned) == 1 else None

    async def history(self, project_id: uuid.UUID, item_id: uuid.UUID) -> list[ReleaseDecision]:
        item = await self.get_item(project_id, item_id)
        return await self.repo.list_releases(project_id, [item.id])

    # ── recompute from linked documents (rule 6) ───────────────────────────

    async def recompute_item(
        self, project_id: uuid.UUID, item_id: uuid.UUID, *, actor_id: Any = None, locked: CommitmentItem | None = None
    ) -> CommitmentItem:
        """Move ``released / committed / closed / re_release_required`` from the linked documents. Only writer of those."""
        item = locked or await self.get_item(project_id, item_id, lock=True)
        if item.status not in ("released", "partially_released", "committed", "closed", "re_release_required"):
            return item
        matrix = await self.require_matrix(project_id)
        project = await self._project(project_id)
        schedule = await self.schedule_for(matrix)
        today = datetime.now(UTC).date()
        per_item, committed, reason = await self.committed_for_items(matrix, project, schedule, on_date=today)
        figs = per_item.get(item.id, [])
        comm = committed.get(item.id, ZERO)
        if comm is None:
            return item
        released = self.released_in_schedule_currency(await self.repo.list_releases(project_id, [item.id]))
        tol = schedule.variation_tolerance
        ceiling = ev.tolerance_ceiling(released, parse_amount(tol.absolute), parse_amount(tol.percent))
        counting = [f for f in figs if f.counts]
        if comm > ceiling:
            target = "re_release_required"
        elif counting and all(f.closed for f in counting):
            target = "closed"
        elif comm > 0:
            target = "committed"
        else:
            target = await self._released_state_from_amount(item, released, matrix, project, schedule, today)
        if target != item.status:
            before = item.status
            if before == "closed" and target == "released":
                return item
            await self._fsm(item, target, actor_id, "recomputed from linked documents", committed=str(comm))
            if target == "re_release_required":
                await self._notify(
                    item.owner_user_id,
                    "re_release_required",
                    item,
                    {
                        "project_id": str(project_id),
                        "code": item.code,
                        "committed": str(comm),
                        "released": str(released),
                    },
                )
                self._publish("item.re_release_required", {"project_id": str(project_id), "item_id": str(item.id)})
        return item

    async def _released_state_from_amount(self, item, released, matrix, project, schedule, today) -> str:
        planned, ccy, _n = await figures.planned_amount(self.session, item, norm(project.currency))
        if planned is None:
            return "released"
        try:
            p = (await self.quote(matrix, project, ccy, self.schedule_currency(schedule, project), today)).apply(
                planned
            )
        except FxRateMissing:
            return "released"
        return "released" if released >= p else "partially_released"

    async def recompute_documents(self, kind: str, document_ids: list[uuid.UUID]) -> int:
        """Recompute every item that links one of these documents (event subscribers)."""
        links = await self.repo.links_for_documents(kind, document_ids)
        for link in links:
            await self.recompute_item(link.project_id, link.item_id)
        return len(links)

    # ── guard check (rule 3) ───────────────────────────────────────────────

    async def check_document(
        self,
        project_id: uuid.UUID,
        *,
        kind: str,
        document_id: uuid.UUID | None,
        new_amount: Any,
        currency: str,
        actor_id: Any = None,
    ) -> dict[str, Any]:
        """Would binding ``new_amount`` on this document stay within its item's release (plus tolerance)?"""
        matrix = await self.repo.get_matrix(project_id)
        if matrix is None or matrix.enforcement == "off":
            return {"result": "ok", "reasons": [], "item_id": None}
        severity = "block" if matrix.enforcement == "block" else "warn"
        link = await self.repo.find_link(project_id, kind, document_id) if document_id else None
        if link is None:
            if matrix.require_link:
                out = {"result": severity, "reasons": [{"code": "commitment_not_in_matrix"}], "item_id": None}
                await self._audit(
                    actor_id, "commitment_guard", document_id, f"guard_{severity}", metadata={"kind": kind, **out}
                )
                return out
            return {"result": "ok", "reasons": [], "item_id": None}
        project = await self._project(project_id)
        schedule = await self.schedule_for(matrix)
        today = datetime.now(UTC).date()
        sched_ccy = self.schedule_currency(schedule, project)
        reasons: list[dict[str, Any]] = []
        try:
            new_sched = (await self.quote(matrix, project, currency, sched_ccy, today)).apply(_amount(new_amount))
            per_item, _committed, _r = await self.committed_for_items(matrix, project, schedule, on_date=today)
            others = ZERO
            for f in per_item.get(link.item_id, []):
                if f.link_id == link.id or not f.amount:
                    continue
                others += (await self.quote(matrix, project, f.currency, sched_ccy, today)).apply(f.amount)
        except FxRateMissing:
            reasons.append({"code": "fx_rate_missing"})
            out = {"result": severity, "reasons": reasons, "item_id": str(link.item_id)}
            await self._audit(
                actor_id, "commitment_guard", document_id, f"guard_{severity}", metadata={"kind": kind, **out}
            )
            return out
        released = self.released_in_schedule_currency(await self.repo.list_releases(project_id, [link.item_id]))
        tol = schedule.variation_tolerance
        ceiling = ev.tolerance_ceiling(released, parse_amount(tol.absolute), parse_amount(tol.percent))
        if released <= 0 or others + new_sched > ceiling:
            reasons.append(
                {
                    "code": "commitment_not_released",
                    "released": str(released),
                    "ceiling": str(ceiling),
                    "would_commit": str(others + new_sched),
                    "currency": sched_ccy,
                }
            )
        if not reasons:
            return {"result": "ok", "reasons": [], "item_id": str(link.item_id)}
        out = {"result": severity, "reasons": reasons, "item_id": str(link.item_id)}
        await self._audit(
            actor_id, "commitment_guard", document_id, f"guard_{severity}", metadata={"kind": kind, **out}
        )
        return out

    # ── gate evidence, validation payload, export rows ─────────────────────

    async def gate_items(self, project_id: uuid.UUID, gate_code: str, area_code: str | None) -> list[CommitmentItem]:
        items = [i for i in await self.repo.list_items(project_id) if i.gate_code == gate_code]
        return [i for i in items if area_code is None or i.governance_area_code == area_code]

    async def validation_payload(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        matrix = await self.require_matrix(project_id)
        schedule = await self.schedule_for(matrix)
        data = await self.item_views(project_id, today=today, with_exposure=True)
        releases = await self.repo.list_releases(project_id)
        links = await self.repo.list_links(project_id)
        groups: dict[str, list[dict[str, Any]]] = {}
        for v in data["items"]:
            if v["split_group"]:
                groups.setdefault(v["split_group"], []).append(v)
        return {
            "today": today.isoformat(),
            "schedule": schedule.model_dump(mode="json"),
            "items": data["items"],
            "releases": [
                {
                    "id": str(r.id),
                    "item_id": str(r.item_id),
                    "outcome": r.outcome,
                    "required_tier": r.required_tier,
                    "evaluated_amount": str(r.evaluated_amount),
                    "commitment_type": next(
                        (v["commitment_type"] for v in data["items"] if v["id"] == str(r.item_id)), None
                    ),
                    "flags": next((v["flags"] for v in data["items"] if v["id"] == str(r.item_id)), []),
                    "schedule_version": r.schedule_version,
                    "escalate_outside": r.escalate_outside,
                }
                for r in releases
            ],
            "links": [
                {"kind": lk.kind, "document_id": str(lk.document_id), "item_id": str(lk.item_id)} for lk in links
            ],
            "split_groups": {k: [x["id"] for x in v] for k, v in groups.items()},
        }


def _schedule_entry(raw: dict[str, Any]) -> ScheduleEntry:
    if not isinstance(raw, dict) or not raw.get("milestone"):
        raise ValueError("milestone required")
    from_date = _day(raw.get("from_date"))
    progress = parse_amount(raw["progress_pct"]) if raw.get("progress_pct") not in (None, "") else None
    if from_date is None and progress is None:
        raise ValueError("from_date or progress_pct required")
    amount = parse_amount(raw["charge_amount"]) if raw.get("charge_amount") not in (None, "") else None
    pct = parse_amount(raw["charge_pct"]) if raw.get("charge_pct") not in (None, "") else None
    if (amount is None) == (pct is None):
        raise ValueError("exactly one of charge_amount or charge_pct")
    return ScheduleEntry(str(raw["milestone"]), from_date, progress, amount, pct)
