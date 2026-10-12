# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Project governance service: reads rows, asks the evaluator, writes the outcome.

The rules live in :mod:`evaluator` and are pure. This layer only loads what a
rule needs, locks what a decision changes, and writes the result together with
its audit trail (``log_activity`` in the same transaction), events (published
after commit, because every subscriber opens its own session) and
notifications.

Who may decide a gate is answered by the approval route of the gate
(``approval_routes``, target kind ``phase_gate``), never by a role alone:

* a pending instance at its final step: the deciders ``entitled_deciders``
  names for that step, or, for a role-based step, a caller whose role meets it;
* an instance someone already approved in the approval screen: exactly the
  user who approved its final step;
* no route configured: nobody, and the API says so.

Concurrency: a decision locks the gate row (``SELECT ... FOR UPDATE``), the
gate carries a version column, and one decision per attempt is a unique
constraint. Whichever of two simultaneous deciders commits second finds the
gate no longer in review and gets a 409.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.project_governance import evaluator as ev
from app.modules.project_governance.catalogue import Catalogue
from app.modules.project_governance.catalogue_store import CatalogueStore, resolve_catalogue
from app.modules.project_governance.errors import GovernanceError, conflict, forbidden, not_found
from app.modules.project_governance.evidence import CollectedEvidence, GateAttempt, collect_evidence
from app.modules.project_governance.fsm import DOCUMENT_FSM, GATE_FSM
from app.modules.project_governance.models import (
    GovernanceArea,
    GovernanceChangeRequest,
    GovernanceCheck,
    GovernanceCondition,
    GovernanceDecision,
    GovernanceDocument,
    GovernanceGate,
    GovernanceModel,
)
from app.modules.project_governance.repository import GovernanceRepository

logger = logging.getLogger(__name__)

MODULE = "project_governance"
GATE_TARGET_KIND = "phase_gate"
CHANGE_TARGET_KIND = "frame_change"
_MANAGER_ROLES = frozenset({"admin", "manager"})
_UNDECIDED = ("not_started", "in_preparation", "in_review", "on_hold")


def catalogue_key(source: str, catalogue_id: str, version: int) -> str:
    """The value gates store to say which pinned catalogue they belong to."""
    return f"{source}:{catalogue_id}@{version}"


def _uuid(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


class GovernanceService:
    """Orchestrates models, gates, documents, checks, decisions and change requests."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = GovernanceRepository(session)
        self.last_evidence: list[CollectedEvidence] = []

    # ── helpers ────────────────────────────────────────────────────────────

    async def require_model(self, project_id: uuid.UUID, *, lock: bool = False) -> GovernanceModel:
        model = await self.repo.get_model(project_id, lock=lock)
        if model is None:
            raise not_found("model_missing")
        return model

    async def catalogue_for(self, model: GovernanceModel) -> Catalogue:
        return await resolve_catalogue(
            self.session, model.catalogue_source, model.catalogue_id, model.catalogue_version, from_pin=True
        )

    async def _fsm(self, fsm: Any, entity: Any, target: str, actor_id: Any, reason: str | None = None, **meta: Any):
        try:
            await fsm.apply(
                self.session,
                entity,
                target,
                actor_id=_s(actor_id),
                reason=reason,
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
        publish_after_commit(self.session, f"{MODULE}.{name}", data, source_module=MODULE)

    async def _notify(self, user_id: Any, kind: str, entity_type: str, entity_id: Any, ctx: dict[str, Any]) -> None:
        """Best effort, inside a savepoint so a failure never poisons the decision."""
        if not user_id:
            return
        try:
            from app.modules.notifications.service import NotificationService

            async with self.session.begin_nested():
                await NotificationService(self.session).create(
                    user_id=user_id,
                    notification_type=f"governance_{kind}",
                    title_key=f"notifications.governance.{kind}.title",
                    entity_type=entity_type,
                    entity_id=str(entity_id),
                    body_key=f"notifications.governance.{kind}.body",
                    body_context=ctx,
                    action_url=f"/projects/{ctx.get('project_id')}/governance",
                    metadata=ctx,
                )
        except Exception:
            logger.debug("governance notification %s skipped", kind, exc_info=True)

    async def _mirror_project_phase(self, project_id: uuid.UUID, catalogue: Catalogue, phase_code: str | None) -> None:
        """``Project.phase`` is a mirror and this module is its only writer."""
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None or not phase_code:
            return
        spine = catalogue.phase(phase_code).spine_key
        if project.phase != spine:
            before = project.phase
            project.phase = spine
            await self._audit(
                None,
                "project",
                project_id,
                "phase_mirrored",
                from_status=before,
                to_status=spine,
                metadata={"governance_phase": phase_code},
            )

    async def user_can_access_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        """Owner, team member or admin: who may be named an area owner."""
        from app.modules.projects.models import Project
        from app.modules.teams.access import is_project_member
        from app.modules.users.models import User

        project = await self.session.get(Project, project_id)
        if project is None:
            return False
        if project.owner_id == user_id:
            return True
        user = await self.session.get(User, user_id)
        if user is not None and (user.role or "") == "admin":
            return True
        return await is_project_member(self.session, project_id, user_id)

    async def _revision_facts(self, container_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str | None, str | None]]:
        """``container_id -> (current_revision_id, content_hash)`` read from CDE."""
        from app.modules.cde.models import DocumentContainer, DocumentRevision

        ids = [c for c in container_ids if c]
        if not ids:
            return {}
        rows = (
            await self.session.execute(
                select(DocumentContainer.id, DocumentContainer.current_revision_id).where(DocumentContainer.id.in_(ids))
            )
        ).all()
        rev_ids = [r[1] for r in rows if r[1]]
        hashes: dict[str, str | None] = {}
        if rev_ids:
            for rid, h in (
                await self.session.execute(
                    select(DocumentRevision.id, DocumentRevision.content_hash).where(DocumentRevision.id.in_(rev_ids))
                )
            ).all():
                hashes[str(rid)] = h
        return {cid: (_s(rev), hashes.get(str(rev)) if rev else None) for cid, rev in rows}

    async def _revision_hash(self, revision_id: Any) -> str | None:
        from app.modules.cde.models import DocumentRevision

        if not revision_id:
            return None
        rev = await self.session.get(DocumentRevision, _uuid(revision_id))
        return rev.content_hash if rev is not None else None

    async def _container_in_project(self, project_id: uuid.UUID, container_id: uuid.UUID) -> bool:
        from app.modules.cde.models import DocumentContainer

        row = await self.session.get(DocumentContainer, container_id)
        return row is not None and row.project_id == project_id

    # ── context for the evaluator ──────────────────────────────────────────

    async def gate_context(
        self, model: GovernanceModel, gate: GovernanceGate, today: date
    ) -> tuple[ev.GateContext, dict[str, GovernanceArea], list[GovernanceDocument]]:
        areas = await self.repo.list_areas(model.project_id)
        by_id = {a.id: a for a in areas}
        docs = [d for d in await self.repo.list_documents(model.project_id) if d.area_id in by_id]
        facts = await self._revision_facts([d.container_id for d in docs if d.container_id])
        checks = await self.repo.list_checks(gate.id, gate.attempt_no)
        prior, _ = await self.repo.list_conditions(model.project_id)
        collected = await collect_evidence(
            self.session,
            model.project_id,
            GateAttempt(gate_id=gate.id, gate_code=gate.code, attempt_no=gate.attempt_no),
            list(areas),
        )
        ctx = ev.GateContext(
            gate_code=gate.code,
            gate_status=gate.status,
            areas=tuple(
                ev.AreaState(
                    code=a.code,
                    owner_user_id=_s(a.owner_user_id),
                    deputy_user_id=_s(a.deputy_user_id),
                    applicable=a.applicable,
                    na_rationale=a.na_rationale,
                )
                for a in areas
            ),
            documents=tuple(
                ev.DocumentState(
                    id=str(d.id),
                    area_code=by_id[d.area_id].code,
                    doc_type=d.doc_type,
                    required=gate.code in (d.required_at_gates or []),
                    status=d.status,
                    container_id=_s(d.container_id),
                    current_revision_id=facts.get(d.container_id, (None, None))[0] if d.container_id else None,
                    current_content_hash=facts.get(d.container_id, (None, None))[1] if d.container_id else None,
                    bound_revision_id=_s(d.bound_revision_id),
                    bound_content_hash=d.bound_content_hash,
                    read_only=d.read_only,
                )
                for d in docs
            ),
            checks=tuple(
                ev.CheckState(
                    area_code=by_id[c.area_id].code,
                    status=c.status,
                    confirmed_by=_s(c.confirmed_by),
                    confirmed_revisions=dict(c.confirmed_revisions or {}),
                    stale=c.stale,
                    na_rationale=c.na_rationale,
                    rag=c.rag,
                    note=c.note,
                    confirmed_at=c.confirmed_at.isoformat() if c.confirmed_at else None,
                )
                for c in checks
                if c.area_id in by_id
            ),
            prior_conditions=tuple(
                ev.ConditionState(
                    id=str(c.id),
                    gate_code=c.gate_code,
                    area_code=c.area_code,
                    status="open" if c.status == "overdue" else c.status,
                    due_date=_parse_day(c.due_date),
                    severity=c.severity,
                    document_type=c.document_type,
                )
                for c in prior
                if c.gate_id != gate.id and c.status in ("open", "overdue")
            ),
            today=today,
            model_stopped=model.stopped,
            four_eyes=model.four_eyes,
            evidence=tuple(
                ev.EvidenceState(
                    area_code=e.area_code,
                    code=e.item.code,
                    state=e.item.state,
                    blocking=e.blocking,
                    provider=e.provider,
                )
                for e in collected
            ),
        )
        self.last_evidence = collected
        return ctx, {a.code: a for a in areas}, docs

    # ── model ──────────────────────────────────────────────────────────────

    async def set_model(
        self,
        project_id: uuid.UUID,
        *,
        source: str,
        catalogue_id: str,
        version: int | None,
        four_eyes: bool,
        actor_id: uuid.UUID,
        tenant_id: str | None,
    ) -> GovernanceModel:
        """Pin a catalogue on a project and build its areas, gates and documents."""
        if await self.repo.get_model(project_id) is not None:
            raise conflict("model_exists")
        pinned = await CatalogueStore(self.session).assert_pinnable(tenant_id, source, catalogue_id, version)
        catalogue = await resolve_catalogue(self.session, source, catalogue_id, pinned, tenant_id=tenant_id)
        model = await self.repo.add(
            GovernanceModel(
                project_id=project_id,
                catalogue_source=source,
                catalogue_id=catalogue_id,
                catalogue_version=pinned,
                current_phase=catalogue.first_phase.code,
                four_eyes=four_eyes,
                created_by=actor_id,
            )
        )
        await self._materialise(model, catalogue, existing_areas={}, existing_docs={})
        await self._mirror_project_phase(project_id, catalogue, model.current_phase)
        await self._audit(
            actor_id,
            "governance_model",
            model.id,
            "created",
            metadata={"catalogue": catalogue_key(source, catalogue_id, pinned)},
        )
        self._publish("model.set", {"project_id": str(project_id), "catalogue_id": catalogue_id, "version": pinned})
        return model

    async def _materialise(
        self,
        model: GovernanceModel,
        catalogue: Catalogue,
        *,
        existing_areas: dict[str, GovernanceArea],
        existing_docs: dict[tuple[str, str], GovernanceDocument],
    ) -> None:
        key = catalogue_key(model.catalogue_source, model.catalogue_id, model.catalogue_version)
        area_rows: dict[str, GovernanceArea] = {}
        codes = {a.code for a in catalogue.areas}
        for area in catalogue.areas:
            row = existing_areas.get(area.code)
            if row is None:
                row = await self.repo.add(
                    GovernanceArea(project_id=model.project_id, code=area.code, sort_order=area.order)
                )
            else:
                row.retired = False
                row.sort_order = area.order
            area_rows[area.code] = row
        for code, row in existing_areas.items():
            if code not in codes:
                row.retired = True
        order = {p.code: p.order for p in catalogue.phases}
        for gate in sorted(catalogue.gates, key=lambda g: order.get(g.from_phase, 0)):
            await self.repo.add(
                GovernanceGate(
                    project_id=model.project_id,
                    catalogue_id=key,
                    code=gate.code,
                    from_phase=gate.from_phase,
                    to_phase=gate.to_phase,
                    sort_order=order.get(gate.from_phase, 0),
                )
            )
        seen: set[tuple[str, str]] = set()
        for dt in catalogue.document_types:
            area_row = area_rows.get(dt.area)
            if area_row is None:
                continue
            seen.add((dt.area, dt.code))
            doc = existing_docs.get((dt.area, dt.code))
            if doc is None:
                await self.repo.add(
                    GovernanceDocument(
                        project_id=model.project_id,
                        area_id=area_row.id,
                        doc_type=dt.code,
                        required_at_gates=list(dt.required_at_gates),
                    )
                )
            else:
                doc.required_at_gates = list(dt.required_at_gates)
        for k, doc in existing_docs.items():
            if k not in seen:
                doc.required_at_gates = []
        await self.session.flush()

    async def change_model(
        self,
        project_id: uuid.UUID,
        *,
        source: str,
        catalogue_id: str,
        version: int | None,
        mapping: dict[str, str],
        actor_id: uuid.UUID,
        tenant_id: str | None,
    ) -> GovernanceModel:
        """Move a project to another catalogue (or version) with an explicit phase mapping."""
        model = await self.require_model(project_id, lock=True)
        pinned = await CatalogueStore(self.session).assert_pinnable(tenant_id, source, catalogue_id, version)
        new = await resolve_catalogue(self.session, source, catalogue_id, pinned, tenant_id=tenant_id)
        gates = await self.repo.list_gates(project_id)
        counts = await self.repo.decision_counts(project_id)
        violations = ev.validate_phase_mapping(
            new_phase_codes=[p.code for p in new.phases],
            mapping=mapping,
            current_phase=model.current_phase,
            phases_with_decisions=[g.from_phase for g in gates if counts.get(g.id)],
        )
        if violations:
            raise GovernanceError("phase_mapping_missing", 422, violations=[v.as_dict() for v in violations])
        kept = ev.gates_kept_on_model_change({str(g.id): counts.get(g.id, 0) for g in gates})
        for gate in gates:
            if str(gate.id) in kept:
                gate.historic = True
            else:
                await self.repo.delete(gate)
        await self.session.flush()
        before = catalogue_key(model.catalogue_source, model.catalogue_id, model.catalogue_version)
        old_phase = model.current_phase
        model.catalogue_source = source
        model.catalogue_id = catalogue_id
        model.catalogue_version = pinned
        model.current_phase = mapping.get(old_phase or "", new.first_phase.code)
        areas = {a.code: a for a in await self.repo.list_areas(project_id, include_retired=True)}
        by_id = {a.id: a for a in areas.values()}
        docs = {(by_id[d.area_id].code, d.doc_type): d for d in await self.repo.list_documents(project_id)}
        await self._materialise(model, new, existing_areas=areas, existing_docs=docs)
        await self._mirror_project_phase(project_id, new, model.current_phase)
        await self._audit(
            actor_id,
            "governance_model",
            model.id,
            "catalogue_changed",
            from_status=before,
            to_status=catalogue_key(source, catalogue_id, pinned),
            metadata={"mapping": mapping, "kept_gates": sorted(kept)},
        )
        self._publish("model.changed", {"project_id": str(project_id), "mapping": mapping})
        return model

    async def update_settings(
        self,
        project_id: uuid.UUID,
        *,
        four_eyes: bool | None,
        decision_route_id: uuid.UUID | None,
        change_route_id: uuid.UUID | None,
        fields_set: set[str],
        actor_id: uuid.UUID,
    ) -> GovernanceModel:
        model = await self.require_model(project_id, lock=True)
        before = {"four_eyes": model.four_eyes}
        if four_eyes is not None:
            model.four_eyes = four_eyes
        if "decision_route_id" in fields_set:
            model.decision_route_id = decision_route_id
        if "change_route_id" in fields_set:
            model.change_route_id = change_route_id
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_model",
            model.id,
            "settings_changed",
            before_state=before,
            after_state={"four_eyes": model.four_eyes},
        )
        return model

    # ── areas ──────────────────────────────────────────────────────────────

    async def update_area(
        self,
        project_id: uuid.UUID,
        area_id: uuid.UUID,
        *,
        changes: dict[str, Any],
        actor_id: uuid.UUID,
    ) -> GovernanceArea:
        """Owner, deputy, applicability and name override; owner change resets readiness."""
        await self.require_model(project_id)
        area = await self.repo.get_area(project_id, area_id)
        if area is None:
            raise not_found("area_not_found")
        before = {
            "owner_user_id": _s(area.owner_user_id),
            "deputy_user_id": _s(area.deputy_user_id),
            "applicable": area.applicable,
        }
        for field in ("owner_user_id", "deputy_user_id"):
            if field in changes and changes[field] is not None:
                if not await self.user_can_access_project(project_id, changes[field]):
                    raise GovernanceError("owner_not_project_member", 422)
        if changes.get("applicable") is False:
            reason = changes.get("na_rationale", area.na_rationale)
            code = ev.not_applicable_violation(reason)
            if code:
                raise GovernanceError(code, 422)
        owner_changed = "owner_user_id" in changes and changes["owner_user_id"] != area.owner_user_id
        for field in ("owner_user_id", "deputy_user_id", "applicable", "na_rationale", "name_override"):
            if field in changes:
                setattr(area, field, changes[field] if changes[field] is not None or "user_id" in field else "")
        if owner_changed:
            for check in await self.repo.list_open_checks_for_area(project_id, area.id):
                await self._audit(
                    actor_id,
                    "governance_check",
                    check.id,
                    "reset_on_owner_change",
                    from_status=check.status,
                    to_status="not_assessed",
                    before_state={"confirmed_by": _s(check.confirmed_by), "status": check.status},
                )
                check.status = "not_assessed"
                check.confirmed_by = None
                check.confirmed_at = None
                check.confirmed_revisions = {}
                check.stale = False
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_area",
            area.id,
            "updated",
            before_state=before,
            after_state={k: _s(v) if "user_id" in k else v for k, v in changes.items()},
        )
        if owner_changed:
            await self._notify(
                area.owner_user_id,
                "area_owner",
                "governance_area",
                area.id,
                {"project_id": str(project_id), "area": area.code},
            )
        return area

    # ── gates ──────────────────────────────────────────────────────────────

    async def _resolve_route(self, model: GovernanceModel, kind: str) -> Any:
        from app.modules.approval_routes.service import ApprovalRouteService

        svc = ApprovalRouteService(self.session)
        pinned = model.decision_route_id if kind == GATE_TARGET_KIND else model.change_route_id
        if pinned is not None:
            try:
                route = await svc.get_route(pinned)
            except Exception:
                route = None
            if (
                route is not None
                and route.is_active
                and route.target_kind == kind
                and route.project_id in (None, model.project_id)
            ):
                return route
            return None
        routes = await svc.list_routes(project_id=model.project_id, target_kind=kind, include_inactive=False)
        routes = [r for r in routes if r.project_id in (None, model.project_id)]
        routes.sort(key=lambda r: (r.project_id is None, r.created_at))
        return routes[0] if routes else None

    async def _ensure_checks(self, gate: GovernanceGate, areas: list[GovernanceArea]) -> None:
        have = {c.area_id for c in await self.repo.list_checks(gate.id, gate.attempt_no)}
        for area in areas:
            if area.id not in have:
                self.session.add(
                    GovernanceCheck(
                        project_id=gate.project_id, gate_id=gate.id, attempt_no=gate.attempt_no, area_id=area.id
                    )
                )
        await self.session.flush()

    async def get_gate(self, project_id: uuid.UUID, gate_id: uuid.UUID, *, lock: bool = False) -> GovernanceGate:
        gate = await self.repo.get_gate(project_id, gate_id, lock=lock)
        if gate is None:
            raise not_found("gate_not_found")
        return gate

    async def submit_gate(self, project_id: uuid.UUID, gate_id: uuid.UUID, *, actor_id: uuid.UUID) -> GovernanceGate:
        """Start the gate's review: an approval route instance against the gate."""
        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        model = await self.require_model(project_id)
        gate = await self.get_gate(project_id, gate_id, lock=True)
        if model.stopped:
            raise conflict("project_stopped")
        if gate.historic or gate.status not in ("not_started", "in_preparation"):
            raise conflict("invalid_transition")
        if model.current_phase != gate.from_phase:
            raise conflict("gate_out_of_order")
        route = await self._resolve_route(model, GATE_TARGET_KIND)
        if route is None:
            raise GovernanceError("no_decision_route", 422)
        if gate.status == "not_started":
            await self._fsm(GATE_FSM, gate, "in_preparation", actor_id)
        await self._ensure_checks(gate, await self.repo.list_areas(project_id))
        instance = await ApprovalRouteService(self.session).start_instance(
            InstanceCreate(route_id=route.id, target_kind=GATE_TARGET_KIND, target_id=gate.id),
            started_by=actor_id,
        )
        gate.approval_instance_id = instance.id
        await self._fsm(GATE_FSM, gate, "in_review", actor_id, attempt_no=gate.attempt_no)
        self._publish("gate.submitted", {"project_id": str(project_id), "gate_id": str(gate.id)})
        return gate

    async def start_preparation(
        self, project_id: uuid.UUID, gate_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> GovernanceGate:
        gate = await self.get_gate(project_id, gate_id, lock=True)
        await self._fsm(GATE_FSM, gate, "in_preparation", actor_id)
        await self._ensure_checks(gate, await self.repo.list_areas(project_id))
        return gate

    async def _entitlement(
        self, gate: GovernanceGate, outcome: str, decider_id: uuid.UUID, role: str | None
    ) -> tuple[Any, Any, str | None]:
        """Return ``(instance, final_step, violation_code)`` for this decider."""
        from app.modules.approval_routes.service import ApprovalRouteService, _caller_role_satisfies

        if gate.approval_instance_id is None:
            raise GovernanceError("no_decision_route", 422)
        svc = ApprovalRouteService(self.session)
        instance = await svc.get_instance(gate.approval_instance_id)
        steps = sorted(await svc.list_steps(instance.route_id), key=lambda s: s.ordinal)
        if not steps:
            raise GovernanceError("no_decision_route", 422)
        final = steps[-1]
        if instance.status == "pending":
            if instance.current_step_ordinal != final.ordinal:
                raise conflict("route_not_at_final_step")
            entitled = await svc.entitled_deciders(instance, final, now=datetime.now(UTC))
            ids = frozenset(str(u) for u in entitled) if entitled is not None else None
            role_ok = bool(final.approver_role) and _caller_role_satisfies(role, final.approver_role or "")
        elif instance.status == "approved":
            if outcome not in ("go", "go_with_conditions"):
                raise conflict("route_not_pending")
            states = await svc.list_step_states(instance.id)
            ids = frozenset(
                str(s.approver_user_id) for s in states if s.step_id == final.id and s.decision == "approved"
            )
            role_ok = False
        else:
            raise conflict("route_not_pending")
        return instance, final, ev.entitlement_violation(str(decider_id), entitled_user_ids=ids, role_satisfies=role_ok)

    async def _admit_decision(
        self,
        model: GovernanceModel,
        gate: GovernanceGate,
        *,
        request: ev.DecisionRequest,
        decider_id: uuid.UUID,
        role: str | None,
        today: date,
    ) -> tuple[Any, Any, ev.GateContext, dict[str, GovernanceArea], list[GovernanceDocument]]:
        """Every check that refuses a decision, in the order ``decide`` applies them.

        The single source for both :meth:`decide` and :meth:`decide_capability`,
        so what the screen offers cannot drift from what the endpoint accepts.
        """
        if gate.status != "in_review":
            existing = [
                d for d in await self.repo.list_decisions(model.project_id, gate.id) if d.attempt_no == gate.attempt_no
            ]
            raise conflict("concurrent_decision" if existing or gate.status == "decided" else "gate_not_in_review")
        instance, final_step, entitlement = await self._entitlement(gate, request.outcome, decider_id, role)
        if entitlement:
            raise forbidden(entitlement)
        ctx, areas, docs = await self.gate_context(model, gate, today)
        violations = ev.validate_decision(ctx, request)
        if violations:
            owner = any(v.code == "decider_is_area_owner" for v in violations)
            code = "decider_is_area_owner" if owner else violations[0].code
            raise GovernanceError(code, 403 if owner else 422, violations=[v.as_dict() for v in violations])
        return instance, final_step, ctx, areas, docs

    async def decide_capability(
        self, project_id: uuid.UUID, gate_id: uuid.UUID, *, decider_id: uuid.UUID, role: str | None, today: date
    ) -> dict[str, Any]:
        """Whether this caller could decide the gate now, run through :meth:`_admit_decision`.

        ``decide`` probes a ``stop`` (the outcome with the fewest content rules), so
        it answers state, route entitlement and four-eyes; ``go`` probes a plain go,
        so it also answers every readiness blocker. Nothing is written.
        """
        model = await self.require_model(project_id)
        gate = await self.get_gate(project_id, gate_id)
        out: dict[str, Any] = {}
        for key, outcome in (("decide", "stop"), ("go", "go")):
            probe = ev.DecisionRequest(
                outcome=outcome, rationale="" if outcome == "go" else "probe", decider_id=str(decider_id)
            )
            try:
                await self._admit_decision(model, gate, request=probe, decider_id=decider_id, role=role, today=today)
            except GovernanceError as exc:
                out[key] = False
                out[f"{key}_reason"] = exc.code
            else:
                out[key] = True
        return out

    async def matrix(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """Areas x gates of the current attempts, plus the next gate and its blocker count.

        A fixed set of queries whatever the number of areas, gates or documents.
        """
        model = await self.require_model(project_id)
        catalogue = await self.catalogue_for(model)
        gates = await self.repo.list_gates(project_id)
        area_rows = await self.repo.list_areas(project_id)
        docs = await self.repo.list_documents(project_id)
        checks = {(c.gate_id, c.area_id): c for c in await self.repo.list_current_checks(project_id)}
        next_gate = next((g for g in gates if g.status != "decided"), None)
        blocker_count = 0
        if next_gate is not None:
            ctx, _, _ = await self.gate_context(model, next_gate, today)
            blocker_count = len(ev.gate_blockers(ctx))
        return {
            "catalogue": catalogue,
            "gates": gates,
            "next_gate": next_gate,
            "blocker_count": blocker_count,
            "areas": [
                {
                    "area": a,
                    "cells": {
                        g.code: {
                            "check_status": checks[(g.id, a.id)].status if (g.id, a.id) in checks else None,
                            "rag": checks[(g.id, a.id)].rag if (g.id, a.id) in checks else "",
                            "stale": checks[(g.id, a.id)].stale if (g.id, a.id) in checks else False,
                            "documents": [
                                {"document_id": str(d.id), "doc_type": d.doc_type, "status": d.status, "required": True}
                                for d in docs
                                if d.area_id == a.id and g.code in (d.required_at_gates or [])
                            ],
                        }
                        for g in gates
                    },
                }
                for a in area_rows
            ],
        }

    async def decide(
        self,
        project_id: uuid.UUID,
        gate_id: uuid.UUID,
        *,
        request: ev.DecisionRequest,
        decider_id: uuid.UUID,
        role: str | None,
        today: date,
    ) -> GovernanceDecision:
        """Record an immutable decision on the gate's current attempt."""
        from app.modules.approval_routes.schemas import DecisionSubmit
        from app.modules.approval_routes.service import ApprovalRouteService

        model = await self.require_model(project_id, lock=True)
        gate = await self.get_gate(project_id, gate_id, lock=True)
        instance, final_step, ctx, areas, docs = await self._admit_decision(
            model, gate, request=request, decider_id=decider_id, role=role, today=today
        )

        effects = ev.decision_effects(request.outcome)
        now = datetime.now(UTC)
        decision = GovernanceDecision(
            project_id=project_id,
            gate_id=gate.id,
            gate_code=gate.code,
            attempt_no=gate.attempt_no,
            outcome=request.outcome,
            rationale=request.rationale or "",
            decided_by=decider_id,
            decided_at=now,
            snapshot=ev.build_snapshot(ctx, request),
            proceed_at_risk_areas=list(request.proceed_at_risk_areas),
            accepted_not_applicable=list(request.accepted_not_applicable),
            hold_resume_date=request.hold_resume_date.isoformat() if request.hold_resume_date else "",
            approval_instance_id=instance.id,
        )
        self.session.add(decision)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise conflict("concurrent_decision") from exc

        for cond in request.conditions:
            self.session.add(
                GovernanceCondition(
                    project_id=project_id,
                    decision_id=decision.id,
                    gate_id=gate.id,
                    gate_code=gate.code,
                    area_code=cond.area_code,
                    document_type=cond.document_type,
                    text=cond.text.strip(),
                    owner_user_id=_uuid(cond.owner_user_id),
                    due_date=cond.due_date.isoformat() if cond.due_date else "",
                    severity=cond.severity,
                )
            )

        # Route: close the instance in the same transaction, as the decider.
        routes = ApprovalRouteService(self.session)
        if instance.status == "pending":
            if effects.route_action in ("approved", "rejected"):
                await routes.submit_decision(
                    instance.id,
                    DecisionSubmit(
                        step_id=final_step.id, decision=effects.route_action, comment=request.rationale[:2000] or None
                    ),
                    approver_id=decider_id,
                    caller_role=role,
                )
            elif effects.route_action == "cancel":
                await routes.cancel_instance(instance.id, actor_id=decider_id, reason=request.rationale)

        catalogue = await self.catalogue_for(model)
        if effects.approve_documents:
            for doc in docs:
                if gate.code in (doc.required_at_gates or []) and doc.status == "in_review" and doc.container_id:
                    facts = (await self._revision_facts([doc.container_id])).get(doc.container_id, (None, None))
                    doc.bound_revision_id = _uuid(facts[0])
                    doc.bound_content_hash = facts[1]
                    doc.approved_gate_id = gate.id
                    await self._fsm(DOCUMENT_FSM, doc, "approved_at_gate", decider_id, gate_id=str(gate.id))
                    await self._fsm(DOCUMENT_FSM, doc, "binding", decider_id, gate_id=str(gate.id))
                    self._publish(
                        "frame_document.state_changed",
                        {"project_id": str(project_id), "document_id": str(doc.id), "status": "binding"},
                    )
        if effects.advance_phase:
            before = model.current_phase
            model.current_phase = gate.to_phase
            await self._mirror_project_phase(project_id, catalogue, gate.to_phase)
            self._publish(
                "phase.changed",
                {"project_id": str(project_id), "from_phase": before, "to_phase": gate.to_phase},
            )
        if effects.stop_project:
            model.stopped = True
            model.stopped_at = now
            frozen = set(ev.documents_to_freeze(ctx.documents))
            for doc in docs:
                if str(doc.id) in frozen:
                    doc.read_only = True

        gate.last_outcome = request.outcome
        gate.hold_resume_date = decision.hold_resume_date
        if effects.new_attempt:
            await self._fsm(
                GATE_FSM, gate, effects.next_gate_status, decider_id, reason=request.rationale, outcome=request.outcome
            )
            await self._next_attempt(gate, carry_stale=effects.mark_checks_stale)
        else:
            await self._fsm(
                GATE_FSM, gate, effects.next_gate_status, decider_id, reason=request.rationale, outcome=request.outcome
            )
        await self.session.flush()
        await self._audit(
            decider_id,
            "governance_decision",
            decision.id,
            "decided",
            to_status=request.outcome,
            reason=request.rationale,
            parent_entity_type="governance_gate",
            parent_entity_id=gate.id,
            metadata={"attempt_no": decision.attempt_no, "proceed_at_risk_areas": list(request.proceed_at_risk_areas)},
        )
        self._publish(
            "gate.decided",
            {
                "project_id": str(project_id),
                "gate_id": str(gate.id),
                "decision_id": str(decision.id),
                "outcome": request.outcome,
                "attempt_no": decision.attempt_no,
            },
        )
        for cond in request.conditions:
            await self._notify(
                cond.owner_user_id,
                "condition_assigned",
                "governance_gate",
                gate.id,
                {"project_id": str(project_id), "gate": gate.code},
            )
        return decision

    async def _next_attempt(self, gate: GovernanceGate, *, carry_stale: bool) -> None:
        old = await self.repo.list_checks(gate.id, gate.attempt_no)
        gate.attempt_no = ev.next_attempt_number(gate.attempt_no)
        gate.approval_instance_id = None
        for c in old:
            self.session.add(
                GovernanceCheck(
                    project_id=c.project_id,
                    gate_id=c.gate_id,
                    attempt_no=gate.attempt_no,
                    area_id=c.area_id,
                    status=c.status,
                    rag=c.rag,
                    note=c.note,
                    confirmed_by=c.confirmed_by,
                    confirmed_at=c.confirmed_at,
                    confirmed_revisions=dict(c.confirmed_revisions or {}),
                    stale=True if carry_stale else c.stale,
                    na_rationale=c.na_rationale,
                )
            )
        await self.session.flush()

    async def reopen(
        self, project_id: uuid.UUID, gate_id: uuid.UUID, *, rationale: str, rewind_phase: bool, actor_id: uuid.UUID
    ) -> GovernanceGate:
        """Start attempt n+1 of a decided gate; the earlier decision stays as recorded."""
        model = await self.require_model(project_id, lock=True)
        gate = await self.get_gate(project_id, gate_id, lock=True)
        code = ev.reopen_violation(gate.status, rationale)
        if code:
            raise GovernanceError(code, 409 if code == "gate_not_decided" else 422)
        if gate.last_outcome == "stop":
            model.stopped = False
            model.stopped_at = None
            for doc in await self.repo.list_documents(project_id):
                doc.read_only = False
        if rewind_phase:
            model.current_phase = gate.from_phase
            await self._mirror_project_phase(project_id, await self.catalogue_for(model), gate.from_phase)
        await self._fsm(GATE_FSM, gate, "in_preparation", actor_id, reason=rationale, reopened=True)
        await self._next_attempt(gate, carry_stale=True)
        self._publish(
            "gate.reopened", {"project_id": str(project_id), "gate_id": str(gate.id), "attempt_no": gate.attempt_no}
        )
        return gate

    async def resume(self, project_id: uuid.UUID, gate_id: uuid.UUID, *, actor_id: uuid.UUID) -> GovernanceGate:
        """A held gate continues as a new attempt in preparation."""
        gate = await self.get_gate(project_id, gate_id, lock=True)
        await self._fsm(GATE_FSM, gate, "in_preparation", actor_id, resumed=True)
        await self._next_attempt(gate, carry_stale=False)
        return gate

    async def apply_gate_route_rejection(self, gate_id: uuid.UUID, instance_id: uuid.UUID) -> bool:
        """Route rejected outside a decision: the review goes back to preparation.

        Locks the gate and acts only when it is still in review on exactly this
        instance, so a stop or recycle decided through :meth:`decide` (which
        also rejects the instance) is never overwritten.
        """
        gate = await self.repo.get_gate_by_id(gate_id, lock=True)
        if gate is None or gate.status != "in_review" or gate.approval_instance_id != instance_id:
            return False
        await self._fsm(GATE_FSM, gate, "in_preparation", None, reason="approval route rejected")
        gate.approval_instance_id = None
        await self.session.flush()
        return True

    # ── checks ─────────────────────────────────────────────────────────────

    async def _current_check(self, gate: GovernanceGate, area: GovernanceArea) -> GovernanceCheck:
        for c in await self.repo.list_checks(gate.id, gate.attempt_no):
            if c.area_id == area.id:
                return c
        check = GovernanceCheck(
            project_id=gate.project_id, gate_id=gate.id, attempt_no=gate.attempt_no, area_id=area.id
        )
        return await self.repo.add(check)

    async def _area_for_owner(self, project_id: uuid.UUID, area_id: uuid.UUID, user_id: uuid.UUID) -> GovernanceArea:
        area = await self.repo.get_area(project_id, area_id)
        if area is None:
            raise not_found("area_not_found")
        if not area.owner_user_id:
            raise conflict("area_without_owner")
        if user_id not in (area.owner_user_id, area.deputy_user_id):
            raise forbidden("not_area_owner")
        return area

    async def confirm_check(
        self,
        project_id: uuid.UUID,
        gate_id: uuid.UUID,
        area_id: uuid.UUID,
        *,
        status: str,
        rag: str,
        note: str,
        actor_id: uuid.UUID,
    ) -> GovernanceCheck:
        """The area owner (or deputy) attests readiness; the revisions it saw are recorded."""
        if status not in ("ready", "ready_with_risks", "not_ready", "not_assessed"):
            raise GovernanceError("invalid_status", 422)
        await self.require_model(project_id)
        gate = await self.get_gate(project_id, gate_id, lock=True)
        if gate.status not in _UNDECIDED or gate.historic:
            raise conflict("invalid_transition")
        area = await self._area_for_owner(project_id, area_id, actor_id)
        docs = [d for d in await self.repo.list_documents(project_id) if d.area_id == area.id]
        facts = await self._revision_facts([d.container_id for d in docs if d.container_id])
        confirmed: dict[str, str] = {}
        for d in docs:
            in_force = (
                _s(d.bound_revision_id)
                if d.status in ("approved_at_gate", "binding", "superseded") and d.bound_revision_id
                else facts.get(d.container_id, (None, None))[0]
                if d.container_id
                else None
            )
            if in_force:
                confirmed[str(d.id)] = in_force
        check = await self._current_check(gate, area)
        before = check.status
        check.status = status
        check.rag = rag
        check.note = note
        check.confirmed_by = actor_id
        check.confirmed_at = datetime.now(UTC)
        check.confirmed_revisions = confirmed
        check.stale = False
        check.na_rationale = ""
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_check",
            check.id,
            "confirmed",
            from_status=before,
            to_status=status,
            metadata={"gate": gate.code, "area": area.code, "revisions": confirmed},
        )
        return check

    async def mark_check_not_applicable(
        self, project_id: uuid.UUID, gate_id: uuid.UUID, area_id: uuid.UUID, *, rationale: str, actor_id: uuid.UUID
    ) -> GovernanceCheck:
        code = ev.not_applicable_violation(rationale)
        if code:
            raise GovernanceError(code, 422)
        gate = await self.get_gate(project_id, gate_id, lock=True)
        if gate.status not in _UNDECIDED or gate.historic:
            raise conflict("invalid_transition")
        area = await self._area_for_owner(project_id, area_id, actor_id)
        check = await self._current_check(gate, area)
        before = check.status
        check.status = "not_applicable"
        check.na_rationale = rationale.strip()
        check.confirmed_by = actor_id
        check.confirmed_at = datetime.now(UTC)
        check.stale = False
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_check",
            check.id,
            "not_applicable",
            from_status=before,
            to_status="not_applicable",
            reason=rationale,
        )
        return check

    # ── documents ──────────────────────────────────────────────────────────

    async def _document_for_edit(
        self, project_id: uuid.UUID, document_id: uuid.UUID, user_id: uuid.UUID, role: str | None, action: str
    ) -> tuple[GovernanceDocument, GovernanceArea]:
        doc = await self.repo.get_document(project_id, document_id, lock=True)
        if doc is None:
            raise not_found("document_not_found")
        area = await self.repo.get_area(project_id, doc.area_id)
        assert area is not None
        if (role or "") not in _MANAGER_ROLES and user_id not in (area.owner_user_id, area.deputy_user_id):
            raise forbidden("not_area_owner")
        state = ev.DocumentState(
            id=str(doc.id),
            area_code=area.code,
            doc_type=doc.doc_type,
            required=False,
            status=doc.status,
            container_id=_s(doc.container_id),
            current_revision_id=None,
            bound_revision_id=_s(doc.bound_revision_id),
            read_only=doc.read_only,
        )
        code = ev.document_edit_violation(state, action)
        if code:
            raise conflict(code)
        return doc, area

    async def create_document(
        self, project_id: uuid.UUID, *, area_id: uuid.UUID, doc_type: str, actor_id: uuid.UUID
    ) -> GovernanceDocument:
        """Add an optional frame document of a catalogue type the project does not track yet."""
        model = await self.require_model(project_id)
        area = await self.repo.get_area(project_id, area_id)
        if area is None:
            raise not_found("area_not_found")
        catalogue = await self.catalogue_for(model)
        known = {d.code: d for d in catalogue.document_types if d.area == area.code}
        if doc_type not in known:
            raise GovernanceError("unknown_document_type", 422)
        for d in await self.repo.list_documents(project_id):
            if d.area_id == area.id and d.doc_type == doc_type:
                raise conflict("document_exists")
        doc = await self.repo.add(
            GovernanceDocument(
                project_id=project_id,
                area_id=area.id,
                doc_type=doc_type,
                required_at_gates=list(known[doc_type].required_at_gates),
            )
        )
        await self._audit(actor_id, "governance_document", doc.id, "created")
        return doc

    async def attach_container(
        self,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        container_id: uuid.UUID,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> GovernanceDocument:
        doc, _ = await self._document_for_edit(project_id, document_id, actor_id, role, "attach")
        if not await self._container_in_project(project_id, container_id):
            raise GovernanceError("container_not_in_project", 422)
        before = _s(doc.container_id)
        doc.container_id = container_id
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_document",
            doc.id,
            "container_attached",
            before_state={"container_id": before},
            after_state={"container_id": str(container_id)},
        )
        return doc

    async def submit_document(
        self, project_id: uuid.UUID, document_id: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> GovernanceDocument:
        doc, _ = await self._document_for_edit(project_id, document_id, actor_id, role, "submit")
        if (
            not doc.container_id
            or not (await self._revision_facts([doc.container_id])).get(doc.container_id, (None,))[0]
        ):
            raise GovernanceError("no_pending_revision", 422)
        await self._fsm(DOCUMENT_FSM, doc, "in_review", actor_id)
        self._publish(
            "frame_document.state_changed",
            {"project_id": str(project_id), "document_id": str(doc.id), "status": doc.status},
        )
        return doc

    async def return_document(
        self, project_id: uuid.UUID, document_id: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> GovernanceDocument:
        doc, _ = await self._document_for_edit(project_id, document_id, actor_id, role, "return")
        await self._fsm(DOCUMENT_FSM, doc, "draft", actor_id)
        return doc

    async def document_history(self, project_id: uuid.UUID, document_id: uuid.UUID) -> dict[str, Any]:
        """CDE revisions of the container, which revision is in force, and change requests."""
        from app.modules.cde.models import DocumentRevision

        doc = await self.repo.get_document(project_id, document_id)
        if doc is None:
            raise not_found("document_not_found")
        revisions: list[dict[str, Any]] = []
        if doc.container_id:
            rows = (
                await self.session.execute(
                    select(DocumentRevision)
                    .where(DocumentRevision.container_id == doc.container_id)
                    .order_by(DocumentRevision.revision_number)
                )
            ).scalars()
            revisions = [
                {
                    "id": str(r.id),
                    "revision_code": r.revision_code,
                    "revision_number": r.revision_number,
                    "content_hash": r.content_hash,
                    "file_name": r.file_name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "in_force": doc.bound_revision_id is not None and r.id == doc.bound_revision_id,
                }
                for r in rows
            ]
        crs = await self.repo.list_change_requests(project_id, doc.id)
        return {"document_id": str(doc.id), "revisions": revisions, "change_requests": crs}

    # ── conditions ─────────────────────────────────────────────────────────

    async def add_condition(
        self, project_id: uuid.UUID, gate_id: uuid.UUID, *, cond: ev.ProposedCondition, actor_id: uuid.UUID
    ) -> GovernanceCondition:
        """Attach a further condition to the gate's latest go-with-conditions decision."""
        gate = await self.get_gate(project_id, gate_id)
        decisions = [
            d for d in await self.repo.list_decisions(project_id, gate.id) if d.outcome == "go_with_conditions"
        ]
        if not decisions:
            raise conflict("conditions_not_allowed")
        if not cond.text.strip():
            raise GovernanceError("condition_text_required", 422)
        areas = {a.code for a in await self.repo.list_areas(project_id)}
        if cond.area_code is not None and cond.area_code not in areas:
            raise GovernanceError("condition_unknown_area", 422)
        row = await self.repo.add(
            GovernanceCondition(
                project_id=project_id,
                decision_id=decisions[-1].id,
                gate_id=gate.id,
                gate_code=gate.code,
                area_code=cond.area_code,
                document_type=cond.document_type,
                text=cond.text.strip(),
                owner_user_id=_uuid(cond.owner_user_id),
                due_date=cond.due_date.isoformat() if cond.due_date else "",
                severity=cond.severity,
            )
        )
        await self._audit(actor_id, "governance_condition", row.id, "created", to_status="open")
        return row

    async def clear_condition(
        self, project_id: uuid.UUID, condition_id: uuid.UUID, *, evidence: str, actor_id: uuid.UUID, role: str | None
    ) -> GovernanceCondition:
        cond = await self.repo.get_condition(project_id, condition_id, lock=True)
        if cond is None:
            raise not_found("condition_not_found")
        if cond.status not in ("open", "overdue"):
            raise conflict("condition_not_open")
        if (role or "") not in _MANAGER_ROLES and actor_id != cond.owner_user_id:
            raise forbidden("not_area_owner")
        before = cond.status
        cond.status = "cleared"
        cond.evidence = evidence or ""
        cond.cleared_by = actor_id
        cond.cleared_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(actor_id, "governance_condition", cond.id, "cleared", from_status=before, to_status="cleared")
        return cond

    async def waive_condition(
        self, project_id: uuid.UUID, condition_id: uuid.UUID, *, rationale: str, actor_id: uuid.UUID
    ) -> GovernanceCondition:
        code = ev.waiver_violation(rationale)
        if code:
            raise GovernanceError(code, 422)
        cond = await self.repo.get_condition(project_id, condition_id, lock=True)
        if cond is None:
            raise not_found("condition_not_found")
        if cond.status not in ("open", "overdue"):
            raise conflict("condition_not_open")
        before = cond.status
        cond.status = "waived"
        cond.waiver_rationale = rationale.strip()
        cond.waived_by = actor_id
        cond.waived_at = datetime.now(UTC)
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_condition",
            cond.id,
            "waived",
            from_status=before,
            to_status="waived",
            reason=rationale,
        )
        return cond

    async def escalate_overdue(self, project_id: uuid.UUID, *, today: date) -> list[GovernanceCondition]:
        """Mark overdue conditions and tell the decider of the gate that set them."""
        rows, _ = await self.repo.list_conditions(project_id, status="open")
        states = [
            ev.ConditionState(
                id=str(c.id),
                gate_code=c.gate_code,
                area_code=c.area_code,
                status=c.status,
                due_date=_parse_day(c.due_date),
            )
            for c in rows
        ]
        late_ids = {s.id for s in ev.conditions_to_escalate(states, today)}
        out: list[GovernanceCondition] = []
        decisions = {d.id: d for d in await self.repo.list_decisions(project_id)}
        for c in rows:
            if str(c.id) not in late_ids:
                continue
            c.status = "overdue"
            c.escalated_at = datetime.now(UTC)
            out.append(c)
            await self._audit(None, "governance_condition", c.id, "escalated", from_status="open", to_status="overdue")
            decider = decisions.get(c.decision_id)
            await self._notify(
                decider.decided_by if decider else None,
                "condition_overdue",
                "governance_condition",
                c.id,
                {"project_id": str(project_id), "gate": c.gate_code},
            )
            self._publish("condition.overdue", {"project_id": str(project_id), "condition_id": str(c.id)})
        await self.session.flush()
        return out

    # ── change requests ────────────────────────────────────────────────────

    async def create_change_request(
        self,
        project_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        reason: str,
        impact: str,
        proposed_revision_id: uuid.UUID | None,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> GovernanceChangeRequest:
        """Ask to make a newer revision binding; starts the ``frame_change`` route."""
        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        model = await self.require_model(project_id)
        doc = await self.repo.get_document(project_id, document_id, lock=True)
        if doc is None:
            raise not_found("document_not_found")
        area = await self.repo.get_area(project_id, doc.area_id)
        if (
            (role or "") not in _MANAGER_ROLES
            and area is not None
            and actor_id not in (area.owner_user_id, area.deputy_user_id)
        ):
            raise forbidden("not_area_owner")
        if doc.read_only:
            raise conflict("document_read_only")
        if doc.status != "binding":
            raise conflict("document_not_binding")
        if not (reason or "").strip():
            raise GovernanceError("rationale_required", 422)
        current = (
            (await self._revision_facts([doc.container_id])).get(doc.container_id, (None, None))[0]
            if (doc.container_id)
            else None
        )
        proposed = proposed_revision_id or _uuid(current)
        if proposed is None or proposed == doc.bound_revision_id:
            raise GovernanceError("no_pending_revision", 422)
        from app.modules.cde.models import DocumentRevision

        rev = await self.session.get(DocumentRevision, proposed)
        if rev is None or rev.container_id != doc.container_id:
            raise GovernanceError("no_pending_revision", 422)
        for open_cr in await self.repo.list_change_requests(project_id, doc.id):
            if open_cr.status == "submitted":
                raise conflict("change_request_not_open")
        route = await self._resolve_route(model, CHANGE_TARGET_KIND)
        if route is None:
            raise GovernanceError("no_decision_route", 422)
        cr = await self.repo.add(
            GovernanceChangeRequest(
                project_id=project_id,
                document_id=doc.id,
                previous_revision_id=doc.bound_revision_id,
                proposed_revision_id=proposed,
                proposed_content_hash=rev.content_hash,
                reason=reason.strip(),
                impact=impact or "",
                requested_by=actor_id,
            )
        )
        instance = await ApprovalRouteService(self.session).start_instance(
            InstanceCreate(route_id=route.id, target_kind=CHANGE_TARGET_KIND, target_id=cr.id), started_by=actor_id
        )
        cr.approval_instance_id = instance.id
        await self.session.flush()
        await self._audit(
            actor_id,
            "governance_change_request",
            cr.id,
            "submitted",
            to_status="submitted",
            reason=reason,
            parent_entity_type="governance_document",
            parent_entity_id=doc.id,
        )
        return cr

    async def apply_change_decision(
        self, cr_id: uuid.UUID, *, decision: str, decided_by: Any = None
    ) -> GovernanceChangeRequest | None:
        """Idempotent: the route's verdict on a change request, applied once."""
        cr = await self.repo.get_change_request_by_id(cr_id, lock=True)
        if cr is None or cr.status != "submitted":
            return None
        doc = await self.repo.get_document(cr.project_id, cr.document_id, lock=True)
        now = datetime.now(UTC)
        cr.decided_by = _uuid(decided_by) if decided_by else None
        cr.decided_at = now
        if decision == "approved" and doc is not None and doc.status == "binding" and not doc.read_only:
            before = _s(doc.bound_revision_id)
            doc.bound_revision_id = cr.proposed_revision_id
            doc.bound_content_hash = cr.proposed_content_hash
            cr.status = "approved"
            await self._audit(
                decided_by,
                "governance_document",
                doc.id,
                "binding_revision_changed",
                before_state={"bound_revision_id": before},
                after_state={"bound_revision_id": str(cr.proposed_revision_id)},
            )
            self._publish(
                "frame_document.state_changed",
                {
                    "project_id": str(cr.project_id),
                    "document_id": str(doc.id),
                    "status": "binding",
                    "bound_revision_id": str(cr.proposed_revision_id),
                },
            )
        else:
            cr.status = "rejected"
        await self.session.flush()
        await self._audit(
            decided_by, "governance_change_request", cr.id, cr.status, from_status="submitted", to_status=cr.status
        )
        return cr

    # ── reads ──────────────────────────────────────────────────────────────

    async def gate_detail(self, project_id: uuid.UUID, gate_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """The readiness matrix of one gate: blockers, per-area check and documents, attempts."""
        model = await self.require_model(project_id)
        gate = await self.get_gate(project_id, gate_id)
        ctx, areas, docs = await self.gate_context(model, gate, today)
        decisions = await self.repo.list_decisions(project_id, gate.id)
        checks = {c.area_code: c for c in ctx.checks}
        doc_states = {d.id: d for d in ctx.documents}
        return {
            "gate": gate,
            "blockers": [b.as_dict() for b in ev.gate_blockers(ctx)],
            "areas": [
                {
                    "area_id": str(a.id),
                    "code": a.code,
                    "owner_user_id": _s(a.owner_user_id),
                    "deputy_user_id": _s(a.deputy_user_id),
                    "applicable": a.applicable,
                    "evidence": [e.as_dict() for e in self.last_evidence if e.area_code == a.code],
                    "check": (
                        {
                            "status": checks[a.code].status,
                            "rag": checks[a.code].rag,
                            "note": checks[a.code].note,
                            "confirmed_by": checks[a.code].confirmed_by,
                            "confirmed_at": checks[a.code].confirmed_at,
                            "stale": ev.check_is_stale(checks[a.code], ctx.documents),
                            "na_rationale": checks[a.code].na_rationale,
                        }
                        if a.code in checks
                        else None
                    ),
                    "documents": [
                        {
                            "document_id": str(d.id),
                            "doc_type": d.doc_type,
                            "status": d.status,
                            "required": gate.code in (d.required_at_gates or []),
                            "container_id": _s(d.container_id),
                            "revision_in_force": ev.revision_in_force(doc_states[str(d.id)]),
                            "pending_revision": ev.pending_revision(doc_states[str(d.id)]),
                            "read_only": d.read_only,
                        }
                        for d in docs
                        if d.area_id == a.id
                    ],
                }
                for a in areas.values()
            ],
            "decisions": decisions,
        }

    async def validation_payload(self, project_id: uuid.UUID, *, today: date) -> dict[str, Any]:
        """The payload the ``project_governance`` rule set reads (see ``validators.py``)."""
        await self.require_model(project_id)
        areas = await self.repo.list_areas(project_id)
        by_id = {a.id: a for a in areas}
        docs = [d for d in await self.repo.list_documents(project_id) if d.area_id in by_id]
        facts = await self._revision_facts([d.container_id for d in docs if d.container_id])
        conditions, _ = await self.repo.list_conditions(project_id)
        decisions = await self.repo.list_decisions(project_id)
        return {
            "today": today.isoformat(),
            "areas": [
                {
                    "code": a.code,
                    "owner_user_id": _s(a.owner_user_id),
                    "applicable": a.applicable,
                    "na_rationale": a.na_rationale,
                }
                for a in areas
            ],
            "gates": [
                {
                    "code": g.code,
                    "status": g.status,
                    "target_date": g.target_date,
                    "sort_order": g.sort_order,
                    "historic": g.historic,
                }
                for g in await self.repo.list_gates(project_id)
            ],
            "documents": [
                {
                    "id": str(d.id),
                    "doc_type": d.doc_type,
                    "area_code": by_id[d.area_id].code,
                    "status": d.status,
                    "required_at_gates": list(d.required_at_gates or []),
                    "bound_revision_id": _s(d.bound_revision_id),
                    "current_revision_id": facts.get(d.container_id, (None, None))[0] if d.container_id else None,
                }
                for d in docs
            ],
            "conditions": [{"id": str(c.id), "status": c.status, "due_date": c.due_date} for c in conditions],
            "decisions": [
                {
                    "gate_code": d.gate_code,
                    "decided_by": str(d.decided_by),
                    "four_eyes": bool((d.snapshot or {}).get("four_eyes")),
                    "owner_ids": sorted(
                        {
                            str(x)
                            for a in (d.snapshot or {}).get("areas", [])
                            if a.get("applicable", True)
                            for x in (a.get("owner_user_id"), a.get("deputy_user_id"))
                            if x
                        }
                    ),
                }
                for d in decisions
            ],
        }

    async def trail(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Every decision with its conditions, oldest first: the exportable record."""
        decisions = await self.repo.list_decisions(project_id)
        conditions, _ = await self.repo.list_conditions(project_id)
        by_decision: dict[uuid.UUID, list[GovernanceCondition]] = {}
        for c in conditions:
            by_decision.setdefault(c.decision_id, []).append(c)
        return [
            {
                "gate_code": d.gate_code,
                "attempt_no": d.attempt_no,
                "outcome": d.outcome,
                "decided_by": str(d.decided_by),
                "decided_at": d.decided_at.isoformat(),
                "rationale": d.rationale,
                "proceed_at_risk_areas": d.proceed_at_risk_areas or [],
                "conditions": [{"text": c.text, "status": c.status} for c in by_decision.get(d.id, [])],
            }
            for d in decisions
        ]
