# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Procurement concept service: every write and every computed view.

Ownership of data (SPEC section 6, INTEGRATION section 6):

* package identity and execution link: module 3 ``ContractPackage`` via :mod:`plan_source`;
* bids, bidders and awards: ``bid_management`` / ``rfq_bidding`` (created here once, read back by events);
* company prequalification status, certificates, ratings: ``subcontractors`` (read as evidence);
* award milestones: ``schedule`` activities (proposed here, created only on confirm);
* thresholds and procedures: the pinned catalogue (kind ``procurement_procedures``).

Locks: the concept is "plan locked" once approved or binding; plan fields
(jurisdiction, procedures, values, split, advance, frameworks) then refuse
with 409. Binding is derived on every read from governance: the m08 frame
document is binding and no change request on it is open (rule 14). The
operational parts (candidates, scores, soundings, schedule confirmation,
execution) stay writable, because they are how the binding concept is carried out.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.modules.procurement_concept import evaluator as ev
from app.modules.procurement_concept import plan_source as plan
from app.modules.procurement_concept.catalogue import (
    CONTRACT_PACKAGE_KIND_MAP,
    DEFAULT_CATALOGUE_ID,
    PROCUREMENT_KIND,
    ProcurementCatalogue,
    register_kind,
)
from app.modules.procurement_concept.errors import ProcurementError, conflict, forbidden, not_found
from app.modules.procurement_concept.fsm import (
    CONCEPT_FSM,
    FRAMEWORK_FSM,
    can_set_package_state_by_hand,
    can_transition,
    read_back_target,
)
from app.modules.procurement_concept.models import (
    AwardPackage,
    BidderCandidate,
    CandidateScore,
    FrameworkAgreement,
    MarketSounding,
    PrequalProfile,
    ProcurementConcept,
    ProjectReference,
)

logger = logging.getLogger(__name__)

MODULE = "procurement_concept"
PROCUREMENT_AREA_CODES = ("m08_procurement", "contracts_procurement")
FRAME_DOCUMENT_TYPE = "m08_procurement_frame"
MANAGER_ROLES = ("manager", "admin")
SUPPLY_KINDS = ("supply", "supply_and_install")
_PLAN_LOCKED = ("approved", "binding", "in_review")


def _s(v: Any) -> str | None:
    return None if v is None else str(v)


def _day(v: str | None) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _iso(v: date | None) -> str | None:
    return v.isoformat() if v else None


def _dec(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


class ProcurementConceptService:
    """All operations of the module; the router is a thin mapping onto these."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── plumbing ─────────────────────────────────────────────────────────

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

    async def catalogue_of(self, concept: ProcurementConcept) -> ProcurementCatalogue:
        from app.modules.project_governance.catalogue_store import resolve_catalogue
        from app.modules.project_governance.errors import GovernanceError

        register_kind()
        try:
            return await resolve_catalogue(
                self.session,
                concept.catalogue_source,
                concept.catalogue_id,
                concept.catalogue_version,
                kind=PROCUREMENT_KIND,
            )
        except GovernanceError as exc:
            raise not_found("unknown_catalogue") from exc

    # ── governance reads ─────────────────────────────────────────────────

    async def _procurement_area(self, project_id: uuid.UUID) -> Any:
        from app.modules.project_governance.models import GovernanceArea

        rows = (
            (
                await self.session.execute(
                    select(GovernanceArea).where(
                        GovernanceArea.project_id == project_id,
                        GovernanceArea.code.in_(PROCUREMENT_AREA_CODES),
                        GovernanceArea.retired.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        return rows[0] if rows else None

    async def can_steer(self, project_id: uuid.UUID, actor_id: uuid.UUID, role: str | None) -> bool:
        """Manager, or owner / deputy of the procurement area in governance (SPEC section 5)."""
        if (role or "") in MANAGER_ROLES:
            return True
        area = await self._procurement_area(project_id)
        return area is not None and actor_id in (area.owner_user_id, area.deputy_user_id)

    async def _require_steer(self, project_id: uuid.UUID, actor_id: uuid.UUID, role: str | None) -> None:
        if not await self.can_steer(project_id, actor_id, role):
            raise forbidden("not_procurement_owner")

    async def _frame_document(self, project_id: uuid.UUID, concept: ProcurementConcept) -> Any:
        from app.modules.project_governance.models import GovernanceDocument

        q = select(GovernanceDocument).where(GovernanceDocument.project_id == project_id)
        if concept.governance_document_id is not None:
            q = q.where(GovernanceDocument.id == concept.governance_document_id)
        else:
            q = q.where(GovernanceDocument.doc_type == FRAME_DOCUMENT_TYPE)
        return (await self.session.execute(q)).scalars().first()

    async def effective_state(self, concept: ProcurementConcept) -> str:
        """The stored state, or ``binding`` while governance holds the frame document binding.

        A submitted change request on the document lifts the lock: the concept
        reads ``reopened`` until governance decides it (rule 14).
        """
        from app.modules.project_governance.models import GovernanceChangeRequest

        doc = await self._frame_document(concept.project_id, concept)
        if doc is None or doc.status != "binding":
            return concept.state
        open_cr = (
            await self.session.execute(
                select(func.count())
                .select_from(GovernanceChangeRequest)
                .where(GovernanceChangeRequest.document_id == doc.id, GovernanceChangeRequest.status == "submitted")
            )
        ).scalar_one()
        return "reopened" if open_cr else "binding"

    async def _release_date(self, project_id: uuid.UUID, gate_code: str) -> date | None:
        """Date procurement is released: the go decision of the release gate, else its target date."""
        from app.modules.project_governance.models import GovernanceDecision, GovernanceGate

        gate = (
            (
                await self.session.execute(
                    select(GovernanceGate).where(
                        GovernanceGate.project_id == project_id,
                        GovernanceGate.code == gate_code,
                        GovernanceGate.historic.is_(False),
                    )
                )
            )
            .scalars()
            .first()
        )
        if gate is None:
            return None
        decided = (
            await self.session.execute(
                select(GovernanceDecision.decided_at)
                .where(
                    GovernanceDecision.gate_id == gate.id,
                    GovernanceDecision.outcome.in_(("go", "go_with_conditions")),
                )
                .order_by(GovernanceDecision.decided_at.desc())
            )
        ).scalar()
        if decided is not None:
            return decided.date()
        return _day(gate.target_date)

    async def _advance_released(self, project_id: uuid.UUID, row: AwardPackage) -> bool:
        from app.modules.project_governance.models import GovernanceCondition, GovernanceDecision

        if row.advance_release_id is None:
            return False
        if row.advance_release_kind == "gate_decision":
            d = await self.session.get(GovernanceDecision, row.advance_release_id)
            return d is not None and d.project_id == project_id and d.outcome in ("go", "go_with_conditions")
        if row.advance_release_kind == "condition":
            c = await self.session.get(GovernanceCondition, row.advance_release_id)
            return c is not None and c.project_id == project_id and c.status != "waived"
        return False

    # ── concept ──────────────────────────────────────────────────────────

    async def find_concept(self, project_id: uuid.UUID, *, lock: bool = False) -> ProcurementConcept | None:
        q = select(ProcurementConcept).where(ProcurementConcept.project_id == project_id)
        if lock:
            q = q.with_for_update()
        return (await self.session.execute(q)).scalars().first()

    async def get_concept(self, project_id: uuid.UUID, *, lock: bool = False) -> ProcurementConcept:
        row = await self.find_concept(project_id, lock=lock)
        if row is None:
            raise not_found("concept_missing")
        return row

    async def _require_plan_editable(self, concept: ProcurementConcept) -> None:
        state = await self.effective_state(concept)
        if state == "binding":
            raise conflict("binding_requires_change_request")
        if state in _PLAN_LOCKED:
            raise conflict("concept_locked", detail=state)

    async def set_concept(
        self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID, role: str | None
    ) -> ProcurementConcept:
        await self._require_steer(project_id, actor_id, role)
        concept = await self.find_concept(project_id, lock=True)
        created = concept is None
        if concept is None:
            _form, mod3_public = await plan.delivery_form(self.session, project_id)
            public = data.get("public_client")
            if public is None:
                public = bool(mod3_public)
            concept = ProcurementConcept(
                project_id=project_id,
                catalogue_source="shipped",
                catalogue_id=DEFAULT_CATALOGUE_ID,
                catalogue_version=1,
                jurisdiction="none",
                client_type="private",
                public_client=public,
                vat_rate_pct=Decimal("0"),
                state="draft",
                created_by=actor_id,
            )
        else:
            await self._require_plan_editable(concept)
        pin = {k: data[k] for k in ("catalogue_source", "catalogue_id", "catalogue_version") if data.get(k) is not None}
        if pin:
            concept.catalogue_source = pin.get("catalogue_source", concept.catalogue_source)
            concept.catalogue_id = pin.get("catalogue_id", concept.catalogue_id)
            concept.catalogue_version = pin.get("catalogue_version") or await self._latest_version(concept)
        for key in ("jurisdiction", "client_type", "vat_rate_pct", "release_gate_code"):
            if data.get(key) is not None:
                setattr(concept, key, data[key])
        if data.get("public_client") is not None:
            concept.public_client = data["public_client"]
        if "governance_document_id" in data and data["governance_document_id"] is not None:
            await self._require_document_in_project(project_id, data["governance_document_id"])
            concept.governance_document_id = data["governance_document_id"]
        if data.get("default_profile_id") is not None:
            await self._profile(project_id, data["default_profile_id"])
            concept.default_profile_id = data["default_profile_id"]
        if not concept.public_client and concept.jurisdiction != "none":
            # Private clients keep the jurisdiction for reference but no thresholds apply (Decision 9).
            concept.client_type = "private"
        cat = await self.catalogue_of(concept)
        if cat.jurisdiction(concept.jurisdiction) is None:
            raise ProcurementError("jurisdiction_not_in_catalogue", 422, detail=concept.jurisdiction)
        if created:
            self.session.add(concept)
        await self.session.flush()
        await self._audit(actor_id, "procurement_concept", concept.id, "created" if created else "updated")
        self._publish("concept.updated", {"project_id": str(project_id), "concept_id": str(concept.id)})
        return concept

    async def _latest_version(self, concept: ProcurementConcept) -> int:
        from app.modules.project_governance.catalogue_store import resolve_catalogue

        register_kind()
        try:
            cat = await resolve_catalogue(
                self.session, concept.catalogue_source, concept.catalogue_id, None, kind=PROCUREMENT_KIND
            )
        except Exception as exc:
            raise not_found("unknown_catalogue") from exc
        return int(cat.version)

    async def _require_document_in_project(self, project_id: uuid.UUID, document_id: uuid.UUID) -> None:
        from app.modules.project_governance.models import GovernanceDocument

        doc = await self.session.get(GovernanceDocument, document_id)
        if doc is None or doc.project_id != project_id:
            raise not_found("document_not_found")

    async def transition(
        self, project_id: uuid.UUID, target: str, *, actor_id: uuid.UUID, role: str | None, rationale: str = ""
    ) -> ProcurementConcept:
        """submit (-> in_review), return (-> draft), approve (-> approved), reopen (-> reopened)."""
        await self._require_steer(project_id, actor_id, role)
        concept = await self.get_concept(project_id, lock=True)
        current = await self.effective_state(concept)
        if current == "binding":
            raise conflict("binding_requires_change_request")
        if current == "reopened" and concept.state != "reopened":
            # A change request on the binding document opened the concept again.
            concept.state = "reopened"
        if not can_transition(CONCEPT_FSM, concept.state, target):
            raise conflict("invalid_transition", detail=f"{concept.state}->{target}")
        if target == "in_review":
            plan_findings = await self._plan_findings(project_id)
            if plan_findings:
                raise ProcurementError("package_without_procedure_plan", 422, violations=plan_findings)
            concept.submitted_by = actor_id
        if target == "approved":
            blocking = [f for f in (await self.findings(project_id)) if f["blocks_approval"]]
            if blocking:
                raise ProcurementError("concept_has_blocking_findings", 422, violations=blocking)
            concept.approved_by = actor_id
            concept.approved_at = datetime.now(UTC)
        if target == "reopened" and not rationale.strip():
            raise ProcurementError("rationale_required", 422)
        before = concept.state
        concept.state = target
        await self.session.flush()
        await self._audit(actor_id, "procurement_concept", concept.id, target, from_status=before, to_status=target)
        self._publish("concept.state_changed", {"project_id": str(project_id), "from": before, "to": target})
        return concept

    # ── facts ────────────────────────────────────────────────────────────

    async def _award_rows(self, project_id: uuid.UUID) -> list[AwardPackage]:
        return list(
            (await self.session.execute(select(AwardPackage).where(AwardPackage.project_id == project_id)))
            .scalars()
            .all()
        )

    async def _concept_facts(self, concept: ProcurementConcept) -> ev.ConceptFacts:
        form, _ = await plan.delivery_form(self.session, concept.project_id)
        return ev.ConceptFacts(
            jurisdiction=concept.jurisdiction,
            client_type=concept.client_type,
            public_client=concept.public_client,
            vat_rate_pct=Decimal(concept.vat_rate_pct or 0),
            delivery_form=form,
        )

    async def _package_facts(
        self, project_id: uuid.UUID
    ) -> tuple[list[plan.PlanPackage], dict[str, AwardPackage], list[ev.PackageFacts]]:
        cps = await plan.list_packages(self.session, project_id)
        rows = {str(r.id): r for r in await self._award_rows(project_id)}
        facts = []
        for cp in cps:
            r = rows.get(str(cp.id))
            if r is None:
                continue
            facts.append(await self._facts_of(project_id, cp, r))
        return cps, rows, facts

    async def _facts_of(self, project_id: uuid.UUID, cp: plan.PlanPackage, r: AwardPackage) -> ev.PackageFacts:
        return ev.PackageFacts(
            id=str(r.id),
            code=cp.code,
            cp_kind=cp.kind,
            parent_id=str(cp.parent_id) if cp.parent_id else None,
            estimated_value=r.estimated_value,
            currency=r.currency,
            lot_group=r.lot_group,
            small_lot_exemption=r.small_lot_exemption,
            procedure_code=r.procedure_code,
            tender_basis=r.tender_basis,
            is_advance=r.is_advance,
            advance_reason=r.advance_reason,
            advance_released=await self._advance_released(project_id, r) if r.is_advance else False,
            framework_agreement_id=str(r.framework_agreement_id) if r.framework_agreement_id else None,
            need_date=_day(r.need_date) or _day(cp.need_date),
            lead_time_days=r.lead_time_days,
            procedure_days=r.procedure_days,
            planned_start=_day(r.planned_start),
            state=r.state,
        )

    @staticmethod
    def _check_day(p: ev.PackageFacts, cat: ProcurementCatalogue, today: date) -> date:
        """The planned procedure start the threshold must be valid on (rule 4)."""
        if p.planned_start:
            return p.planned_start
        bp = ev.backward_pass(cat, p)
        return bp.start_date if bp else today

    async def _plan_findings(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        cps = await plan.list_packages(self.session, project_id)
        ids = {str(r.id) for r in await self._award_rows(project_id)}
        return ev.plan_findings([{"id": str(c.id), "code": c.code, "kind": c.kind} for c in cps], ids)

    async def findings(self, project_id: uuid.UUID, *, today: date | None = None) -> list[dict[str, Any]]:
        """Every finding of every rule for the project (the one source for validation, approval, readiness)."""
        today = today or datetime.now(UTC).date()
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        facts = await self._concept_facts(concept)
        cps, rows, pkgs = await self._package_facts(project_id)
        out = ev.plan_findings([{"id": str(c.id), "code": c.code, "kind": c.kind} for c in cps], set(rows))
        release = await self._release_date(project_id, concept.release_gate_code)
        for p in pkgs:
            if p.state == "cancelled" or p.package_kind is None:
                continue
            out += ev.package_findings(cat, p)
            out += ev.procedure_findings(cat, facts, p, pkgs, self._check_day(p, cat, today))
            out += ev.schedule_findings(cat, p, today=today, release_date=release)
            fw = await self._framework_facts(p.framework_agreement_id)
            bp = ev.backward_pass(cat, p)
            out += ev.framework_findings(
                p,
                fw,
                award_date=bp.award_date if bp else None,
                remaining=fw["remaining_excluding"](p.id) if fw else None,
            )
            out += await self._prequal_findings(project_id, cat, p, rows[p.id], bp.award_date if bp else None)
        out += ev.consistency_findings(cat, facts.delivery_form, pkgs)
        soundings = (
            (await self.session.execute(select(MarketSounding).where(MarketSounding.project_id == project_id)))
            .scalars()
            .all()
        )
        out += ev.capacity_findings(
            [
                {"id": s.id, "capacity_signal": s.capacity_signal, "mitigation": s.mitigation, "resplit": s.resplit}
                for s in soundings
            ]
        )
        for f in out:
            f.setdefault("message_key", f"procurement_concept.findings.{f['code']}")
        return out

    # ── packages ─────────────────────────────────────────────────────────

    async def _award(self, project_id: uuid.UUID, package_id: uuid.UUID, *, lock: bool = False) -> AwardPackage:
        q = select(AwardPackage).where(AwardPackage.id == package_id, AwardPackage.project_id == project_id)
        if lock:
            q = q.with_for_update()
        row = (await self.session.execute(q)).scalars().first()
        if row is None:
            raise not_found("package_not_found")
        return row

    async def package_views(self, project_id: uuid.UUID, *, today: date | None = None) -> list[dict[str, Any]]:
        """The package board (screen 1): every ContractPackage joined with its award package."""
        today = today or datetime.now(UTC).date()
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        facts = await self._concept_facts(concept)
        cps, rows, pkgs = await self._package_facts(project_id)
        by_id = {p.id: p for p in pkgs}
        aggregated = ev.aggregated_values(cat, pkgs)
        out = []
        for cp in cps:
            row = rows.get(str(cp.id))
            p = by_id.get(str(cp.id))
            view: dict[str, Any] = {
                "contract_package": cp.as_dict(),
                "package_kind": CONTRACT_PACKAGE_KIND_MAP.get(cp.kind),
                "award": None,
                "threshold": None,
                "schedule": None,
            }
            if row is not None and p is not None:
                tv = ev.threshold_view(cat, facts, p, pkgs, self._check_day(p, cat, today))
                bp = ev.backward_pass(cat, p)
                view["award"] = self._award_out(row)
                view["award"]["aggregated_value"] = _dec(aggregated.get(p.id))
                view["threshold"] = {
                    "status": tv.status,
                    "allowed": tv.allowed,
                    "thresholds": tv.thresholds,
                    "small_lot_exempt": tv.small_lot_exempt,
                    "aggregated_value": _dec(tv.aggregated_value),
                }
                view["schedule"] = (
                    {
                        "award_date": _iso(bp.award_date),
                        "start_date": _iso(bp.start_date),
                        "procedure_days": bp.procedure_days,
                    }
                    if bp
                    else None
                )
            out.append(view)
        return out

    @staticmethod
    def _award_out(r: AwardPackage) -> dict[str, Any]:
        return {
            "id": str(r.id),
            "split_basis": r.split_basis,
            "is_advance": r.is_advance,
            "advance_reason": r.advance_reason,
            "advance_release_kind": r.advance_release_kind,
            "advance_release_id": _s(r.advance_release_id),
            "estimated_value": _dec(r.estimated_value),
            "currency": r.currency,
            "cost_ref_kind": r.cost_ref_kind,
            "cost_ref_id": _s(r.cost_ref_id),
            "lot_group": r.lot_group,
            "small_lot_exemption": r.small_lot_exemption,
            "procedure_code": r.procedure_code,
            "tender_basis": r.tender_basis,
            "framework_agreement_id": _s(r.framework_agreement_id),
            "evaluation_method": r.evaluation_method,
            "evaluation_weights": r.evaluation_weights or {},
            "need_activity_id": _s(r.need_activity_id),
            "need_date": r.need_date,
            "lead_time_days": r.lead_time_days,
            "procedure_days": r.procedure_days,
            "planned_start": r.planned_start,
            "prequal_profile_id": _s(r.prequal_profile_id),
            "start_activity_id": _s(r.start_activity_id),
            "award_activity_id": _s(r.award_activity_id),
            "state": r.state,
            "notes": r.notes,
        }

    async def put_package(
        self,
        project_id: uuid.UUID,
        package_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        role: str | None,
        tenant_id: str | None,
    ) -> AwardPackage:
        """Create (first call) or change the procurement attributes of one ContractPackage."""
        await self._require_steer(project_id, actor_id, role)
        concept = await self.get_concept(project_id)
        await self._require_plan_editable(concept)
        cp = await plan.get_package(self.session, project_id, package_id)
        if cp is None:
            raise not_found("package_not_found")
        if CONTRACT_PACKAGE_KIND_MAP.get(cp.kind) is None:
            raise ProcurementError("package_kind_not_procured", 422, detail=cp.kind)
        q = select(AwardPackage).where(AwardPackage.id == package_id).with_for_update()
        row = (await self.session.execute(q)).scalars().first()
        created = row is None
        if row is None:
            row = AwardPackage(id=package_id, project_id=project_id, created_by=actor_id, state="planned")
            self.session.add(row)
        elif row.project_id != project_id:
            raise not_found("package_not_found")
        if row.state in ("in_tender", "awarded", "cancelled"):
            raise conflict("package_closed", detail=row.state)
        cat = await self.catalogue_of(concept)
        for key, value in data.items():
            if key in ("need_date", "planned_start"):
                setattr(row, key, _iso(value))
            else:
                setattr(row, key, value)
        if "procedure_code" in data and row.procedure_code and cat.procedure(row.procedure_code) is None:
            raise ProcurementError("procedure_unknown", 422, detail=row.procedure_code)
        if row.is_advance and not (row.advance_reason or "").strip():
            # Rule 12: an advance package without a reason is rejected outright.
            raise ProcurementError("advance_without_reason", 422)
        if row.advance_release_id is not None:
            if not row.advance_release_kind:
                raise ProcurementError("advance_release_kind_required", 422)
            if not await self._advance_released(project_id, row):
                raise not_found("advance_release_not_found")
        if row.prequal_profile_id is not None:
            await self._profile(project_id, row.prequal_profile_id)
        if "framework_agreement_id" in data and row.framework_agreement_id is not None:
            await self._link_framework(row, tenant_id)
        if row.state in ("planned", "procedure_set"):
            row.state = "procedure_set" if row.procedure_code else "planned"
        await self.session.flush()
        await self._audit(actor_id, "procurement_award_package", row.id, "created" if created else "updated")
        return row

    async def set_package_state(
        self, project_id: uuid.UUID, package_id: uuid.UUID, action: str, *, actor_id: uuid.UUID, role: str | None
    ) -> AwardPackage:
        await self._require_steer(project_id, actor_id, role)
        row = await self._award(project_id, package_id, lock=True)
        if action == "hold":
            target = "on_hold"
        elif action == "cancel":
            target = "cancelled"
        else:
            if row.state != "on_hold" or not row.state_before:
                raise conflict("package_not_on_hold")
            target = row.state_before
        if not can_set_package_state_by_hand(row.state, target):
            raise conflict("invalid_transition", detail=f"{row.state}->{target}")
        if target == "on_hold":
            row.state_before = row.state
        elif row.state == "on_hold":
            row.state_before = None
        before = row.state
        row.state = target
        await self.session.flush()
        await self._audit(actor_id, "procurement_award_package", row.id, action, from_status=before, to_status=target)
        return row

    async def threshold_check(
        self, project_id: uuid.UUID, package_id: uuid.UUID, *, today: date | None = None
    ) -> dict[str, Any]:
        """Screen 2: threshold explanation with sources and the procedure picker with reasons."""
        today = today or datetime.now(UTC).date()
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        facts = await self._concept_facts(concept)
        _cps, _rows, pkgs = await self._package_facts(project_id)
        p = next((x for x in pkgs if x.id == str(package_id)), None)
        if p is None:
            raise not_found("package_not_found")
        day = self._check_day(p, cat, today)
        tv = ev.threshold_view(cat, facts, p, pkgs, day)
        return {
            "package_id": str(package_id),
            "checked_on": day.isoformat(),
            "status": tv.status,
            "single_value": _dec(tv.single_value),
            "aggregated_value": _dec(tv.aggregated_value),
            "small_lot_exempt": tv.small_lot_exempt,
            "thresholds": tv.thresholds,
            "procedures": ev.allowed_procedures(cat, facts, p, pkgs, day),
            "findings": ev.procedure_findings(cat, facts, p, pkgs, day),
        }

    async def consistency_report(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        facts = await self._concept_facts(concept)
        _cps, _rows, pkgs = await self._package_facts(project_id)
        return ev.consistency_findings(cat, facts.delivery_form, pkgs)

    # ── prequalification ─────────────────────────────────────────────────

    async def _profile(self, project_id: uuid.UUID, profile_id: uuid.UUID) -> PrequalProfile:
        row = await self.session.get(PrequalProfile, profile_id)
        if row is None or row.project_id != project_id:
            raise not_found("profile_not_found")
        return row

    async def list_profiles(self, project_id: uuid.UUID) -> list[PrequalProfile]:
        return list(
            (await self.session.execute(select(PrequalProfile).where(PrequalProfile.project_id == project_id)))
            .scalars()
            .all()
        )

    async def save_profile(
        self,
        project_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        role: str | None,
        profile_id: uuid.UUID | None = None,
    ) -> PrequalProfile:
        await self._require_steer(project_id, actor_id, role)
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        criteria = []
        for c in data.get("criteria") or []:
            known = cat.criterion(c["code"])
            if known is None:
                raise ProcurementError("criterion_unknown", 422, detail=c["code"])
            weight = Decimal(c.get("weight") or 0) if known.kind == "scored" else Decimal("0")
            criteria.append({"code": known.code, "kind": known.kind, "weight": format(weight, "f")})
        bad = ev.weights_findings(criteria, "profile")
        if bad:
            raise ProcurementError("prequal_weights_not_100", 422, violations=bad)
        if data.get("package_id") is not None:
            await self._award(project_id, data["package_id"])
        row = await self._profile(project_id, profile_id) if profile_id else PrequalProfile(project_id=project_id)
        row.package_id = data.get("package_id")
        row.name = data.get("name") or ""
        row.criteria = criteria
        row.pass_mark = Decimal(data.get("pass_mark") or 0)
        row.validity_months = int(data.get("validity_months") or 12)
        if profile_id is None:
            self.session.add(row)
        await self.session.flush()
        return row

    async def delete_profile(
        self, project_id: uuid.UUID, profile_id: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> None:
        await self._require_steer(project_id, actor_id, role)
        row = await self._profile(project_id, profile_id)
        await self.session.delete(row)
        await self.session.flush()

    async def profile_for(self, project_id: uuid.UUID, award: AwardPackage) -> PrequalProfile | None:
        if award.prequal_profile_id:
            return await self.session.get(PrequalProfile, award.prequal_profile_id)
        own = (
            (
                await self.session.execute(
                    select(PrequalProfile).where(
                        PrequalProfile.project_id == project_id, PrequalProfile.package_id == award.id
                    )
                )
            )
            .scalars()
            .first()
        )
        if own is not None:
            return own
        concept = await self.find_concept(project_id)
        if concept and concept.default_profile_id:
            return await self.session.get(PrequalProfile, concept.default_profile_id)
        return None

    async def _candidate(self, project_id: uuid.UUID, candidate_id: uuid.UUID) -> BidderCandidate:
        row = await self.session.get(BidderCandidate, candidate_id)
        if row is None or row.project_id != project_id:
            raise not_found("candidate_not_found")
        return row

    async def _require_company(self, data: dict[str, Any]) -> None:
        from app.modules.subcontractors.models import Subcontractor
        from app.modules.supplier_catalogs.models import Vendor

        if data.get("subcontractor_id") and await self.session.get(Subcontractor, data["subcontractor_id"]) is None:
            raise not_found("company_not_found")
        if data.get("vendor_id") and await self.session.get(Vendor, data["vendor_id"]) is None:
            raise not_found("company_not_found")

    @staticmethod
    def _registered(c: BidderCandidate) -> bool:
        return c.subcontractor_id is not None or c.vendor_id is not None

    def _check_list_change(self, row: BidderCandidate) -> None:
        if row.list_kind == "excluded" and not (row.decision_rationale or "").strip():
            raise ProcurementError("excluded_candidate_without_rationale", 422)
        if row.list_kind == "short" and not self._registered(row):
            raise ProcurementError("candidate_not_registered", 422)
        if not self._registered(row) and not (row.free_name or "").strip():
            raise ProcurementError("candidate_needs_company", 422)

    async def add_candidate(
        self, project_id: uuid.UUID, package_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> BidderCandidate:
        await self._award(project_id, package_id)
        await self._require_company(data)
        row = BidderCandidate(
            project_id=project_id,
            package_id=package_id,
            subcontractor_id=data.get("subcontractor_id"),
            vendor_id=data.get("vendor_id"),
            free_name=data.get("free_name") or "",
            source=data.get("source") or "own_list",
            list_kind=data.get("list") or "long",
            decision_rationale=data.get("decision_rationale") or "",
            conflict_of_interest_declared=bool(data.get("conflict_of_interest_declared")),
            conflict_note=data.get("conflict_note") or "",
        )
        self._check_list_change(row)
        self.session.add(row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except Exception as exc:
            raise conflict("candidate_exists") from exc
        await self._audit(actor_id, "procurement_candidate", row.id, "created")
        return row

    async def patch_candidate(
        self, project_id: uuid.UUID, candidate_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> BidderCandidate:
        row = await self._candidate(project_id, candidate_id)
        await self._require_company(data)
        for key, value in data.items():
            setattr(row, "list_kind" if key == "list" else key, value)
        self._check_list_change(row)
        await self.session.flush()
        await self._audit(actor_id, "procurement_candidate", row.id, "updated")
        return row

    async def delete_candidate(self, project_id: uuid.UUID, candidate_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self._candidate(project_id, candidate_id)
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "procurement_candidate", candidate_id, "deleted")

    async def put_scores(
        self, project_id: uuid.UUID, candidate_id: uuid.UUID, scores: list[dict[str, Any]], *, actor_id: uuid.UUID
    ) -> list[CandidateScore]:
        cand = await self._candidate(project_id, candidate_id)
        award = await self._award(project_id, cand.package_id)
        profile = await self.profile_for(project_id, award)
        allowed = {c["code"]: c["kind"] for c in (profile.criteria if profile else [])}
        existing = {
            s.criterion_code: s
            for s in (await self.session.execute(select(CandidateScore).where(CandidateScore.candidate_id == cand.id)))
            .scalars()
            .all()
        }
        out = []
        for s in scores:
            kind = allowed.get(s["criterion_code"])
            if kind is None:
                raise ProcurementError("criterion_not_in_profile", 422, detail=s["criterion_code"])
            if kind == "pass_fail" and s.get("score") is not None:
                raise ProcurementError("pass_fail_takes_no_score", 422, detail=s["criterion_code"])
            row = existing.get(s["criterion_code"]) or CandidateScore(
                candidate_id=cand.id, criterion_code=s["criterion_code"]
            )
            row.passed = s.get("passed")
            row.score = s.get("score")
            row.evidence = [dict(e) for e in s.get("evidence") or []]
            row.note = s.get("note") or ""
            row.scored_by = actor_id
            if row.id is None or s["criterion_code"] not in existing:
                self.session.add(row)
            out.append(row)
        await self.session.flush()
        return out

    async def add_reference(
        self, project_id: uuid.UUID, candidate_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> ProjectReference:
        cand = await self._candidate(project_id, candidate_id)
        verified = data.pop("verified", False)
        row = ProjectReference(candidate_id=cand.id, **data)
        if verified:
            row.verified_by = actor_id
            row.verified_at = datetime.now(UTC)
        self.session.add(row)
        await self.session.flush()
        return row

    async def delete_reference(self, project_id: uuid.UUID, candidate_id: uuid.UUID, reference_id: uuid.UUID) -> None:
        cand = await self._candidate(project_id, candidate_id)
        row = await self.session.get(ProjectReference, reference_id)
        if row is None or row.candidate_id != cand.id:
            raise not_found("reference_not_found")
        await self.session.delete(row)
        await self.session.flush()

    async def _evidence_of(self, cand: BidderCandidate) -> list[dict[str, Any]]:
        """Evidence chips read from subcontractors (Decision 5): certificates with expiry, prequal status, rating."""
        if cand.subcontractor_id is None:
            return []
        from app.modules.subcontractors.models import Certificate, Subcontractor

        out: list[dict[str, Any]] = []
        sub = await self.session.get(Subcontractor, cand.subcontractor_id)
        if sub is not None:
            out.append(
                {
                    "kind": "prequal_status",
                    "ref": f"subcontractor:{sub.id}",
                    "status": sub.prequalification_status,
                    "expires": getattr(sub, "insurance_expiry_date", None),
                    "rating": _dec(getattr(sub, "rating_score", None)),
                }
            )
        certs = (
            (
                await self.session.execute(
                    select(Certificate).where(Certificate.subcontractor_id == cand.subcontractor_id)
                )
            )
            .scalars()
            .all()
        )
        for c in certs:
            if c.revoked:
                continue
            out.append(
                {"kind": "certificate", "ref": f"certificate:{c.id}", "type": c.cert_type, "expires": c.valid_until}
            )
        return out

    async def candidate_views(self, project_id: uuid.UUID, package_id: uuid.UUID) -> dict[str, Any]:
        """Screen 3: the candidate matrix of one package with totals, evidence and the shortlist findings."""
        award = await self._award(project_id, package_id)
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        profile = await self.profile_for(project_id, award)
        criteria = list(profile.criteria) if profile else []
        pass_mark = Decimal(profile.pass_mark) if profile else Decimal("0")
        cands = list(
            (
                await self.session.execute(
                    select(BidderCandidate)
                    .where(BidderCandidate.project_id == project_id, BidderCandidate.package_id == package_id)
                    .order_by(BidderCandidate.created_at)
                )
            )
            .scalars()
            .all()
        )
        ids = [c.id for c in cands]
        scores: dict[uuid.UUID, list[CandidateScore]] = {}
        refs: dict[uuid.UUID, list[ProjectReference]] = {}
        if ids:
            for s in (
                await self.session.execute(select(CandidateScore).where(CandidateScore.candidate_id.in_(ids)))
            ).scalars():
                scores.setdefault(s.candidate_id, []).append(s)
            for r in (
                await self.session.execute(select(ProjectReference).where(ProjectReference.candidate_id.in_(ids)))
            ).scalars():
                refs.setdefault(r.candidate_id, []).append(r)
        cp = await plan.get_package(self.session, project_id, package_id)
        pf = await self._facts_of(project_id, cp, award) if cp else None
        bp = ev.backward_pass(cat, pf) if pf else None
        items = []
        rule_rows = []
        findings: list[dict[str, Any]] = []
        for c in cands:
            sc = {
                s.criterion_code: {"passed": s.passed, "score": None if s.score is None else str(s.score)}
                for s in scores.get(c.id, [])
            }
            total = ev.candidate_score(criteria, sc)
            evidence = await self._evidence_of(c)
            if c.list_kind == "short":
                findings += ev.evidence_findings(str(c.id), evidence, bp.award_date if bp else None)
            name = await self._company_name(c)
            items.append(
                {
                    "id": str(c.id),
                    "package_id": str(c.package_id),
                    "subcontractor_id": _s(c.subcontractor_id),
                    "vendor_id": _s(c.vendor_id),
                    "name": name,
                    "registered": self._registered(c),
                    "source": c.source,
                    "list": c.list_kind,
                    "decision_rationale": c.decision_rationale,
                    "conflict_of_interest_declared": c.conflict_of_interest_declared,
                    "conflict_note": c.conflict_note,
                    "scores": [
                        {
                            "criterion_code": s.criterion_code,
                            "passed": s.passed,
                            "score": None if s.score is None else str(s.score),
                            "evidence": s.evidence,
                            "note": s.note,
                        }
                        for s in scores.get(c.id, [])
                    ],
                    "total_score": str(total["total"]),
                    "passed_all": total["passed_all"],
                    "missing_criteria": total["missing"],
                    "evidence": [{**e, "expires": _iso(e.get("expires"))} for e in evidence],
                    "references": [
                        {
                            "id": str(r.id),
                            "project_name": r.project_name,
                            "client": r.client,
                            "value": _dec(r.value),
                            "currency": r.currency,
                            "year": r.year,
                            "role": r.role,
                            "contact": r.contact,
                            "verified": r.verified_at is not None,
                        }
                        for r in refs.get(c.id, [])
                    ],
                }
            )
            rule_rows.append(
                {
                    "id": c.id,
                    "list": c.list_kind,
                    "registered": self._registered(c),
                    "rationale": c.decision_rationale,
                    "scores": sc,
                }
            )
        if pf is not None:
            findings = ev.shortlist_findings(cat, pf, criteria, pass_mark, rule_rows) + findings
        return {
            "package_id": str(package_id),
            "profile": None
            if profile is None
            else {"id": str(profile.id), "criteria": criteria, "pass_mark": str(profile.pass_mark)},
            "min_bidders": ev.min_bidders_of(cat, award.procedure_code),
            "items": items,
            "total": len(items),
            "findings": findings,
        }

    async def _company_name(self, c: BidderCandidate) -> str:
        if c.subcontractor_id:
            from app.modules.subcontractors.models import Subcontractor

            sub = await self.session.get(Subcontractor, c.subcontractor_id)
            if sub is not None:
                return sub.trade_name or sub.legal_name
        if c.vendor_id:
            from app.modules.supplier_catalogs.models import Vendor

            v = await self.session.get(Vendor, c.vendor_id)
            if v is not None:
                return v.name
        return c.free_name

    async def confirm_shortlist(
        self, project_id: uuid.UUID, package_id: uuid.UUID, *, actor_id: uuid.UUID, role: str | None
    ) -> AwardPackage:
        """Rule 8: the package becomes ``shortlisted`` only with a valid short list."""
        await self._require_steer(project_id, actor_id, role)
        award = await self._award(project_id, package_id, lock=True)
        if award.state != "procedure_set":
            raise conflict("invalid_transition", detail=f"{award.state}->shortlisted")
        view = await self.candidate_views(project_id, package_id)
        errors = [f for f in view["findings"] if f["severity"] == "error"]
        if errors:
            raise ProcurementError("shortlist_invalid", 422, violations=errors)
        award.state = "shortlisted"
        await self.session.flush()
        await self._audit(actor_id, "procurement_award_package", award.id, "shortlisted", to_status="shortlisted")
        self._publish("package.shortlisted", {"project_id": str(project_id), "package_id": str(package_id)})
        return award

    # ── market sounding ──────────────────────────────────────────────────

    async def _sounding(self, project_id: uuid.UUID, sounding_id: uuid.UUID) -> MarketSounding:
        row = await self.session.get(MarketSounding, sounding_id)
        if row is None or row.project_id != project_id:
            raise not_found("sounding_not_found")
        return row

    async def _check_sounding_refs(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        for pid in data.get("package_ids") or []:
            await self._award(project_id, pid)
        for cid in data.get("participant_candidate_ids") or []:
            await self._candidate(project_id, cid)

    async def list_soundings(self, project_id: uuid.UUID) -> list[MarketSounding]:
        return list(
            (
                await self.session.execute(
                    select(MarketSounding)
                    .where(MarketSounding.project_id == project_id)
                    .order_by(MarketSounding.held_on.desc())
                )
            )
            .scalars()
            .all()
        )

    async def save_sounding(
        self,
        project_id: uuid.UUID,
        data: dict[str, Any],
        *,
        actor_id: uuid.UUID,
        sounding_id: uuid.UUID | None = None,
    ) -> MarketSounding:
        await self.get_concept(project_id)
        await self._check_sounding_refs(project_id, data)
        row = (
            await self._sounding(project_id, sounding_id)
            if sounding_id
            else MarketSounding(project_id=project_id, created_by=actor_id)
        )
        for key, value in data.items():
            if key in ("package_ids", "participant_candidate_ids"):
                value = [str(v) for v in value]
            elif key == "held_on":
                value = _iso(value)
            setattr(row, key, value)
        if sounding_id is None:
            self.session.add(row)
        await self.session.flush()
        await self._audit(actor_id, "procurement_sounding", row.id, "updated" if sounding_id else "created")
        return row

    async def delete_sounding(self, project_id: uuid.UUID, sounding_id: uuid.UUID, *, actor_id: uuid.UUID) -> None:
        row = await self._sounding(project_id, sounding_id)
        await self.session.delete(row)
        await self.session.flush()

    # ── award schedule (rule 11, Decision 7) ─────────────────────────────

    async def schedule_view(self, project_id: uuid.UUID, *, today: date | None = None) -> dict[str, Any]:
        today = today or datetime.now(UTC).date()
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        cps, _rows, pkgs = await self._package_facts(project_id)
        codes = {str(c.id): c for c in cps}
        release = await self._release_date(project_id, concept.release_gate_code)
        rows = []
        for p in pkgs:
            if p.state == "cancelled":
                continue
            bp = ev.backward_pass(cat, p)
            award_row = await self.session.get(AwardPackage, uuid.UUID(p.id))
            rows.append(
                {
                    "package_id": p.id,
                    "code": p.code,
                    "title": codes[p.id].title if p.id in codes else "",
                    "need_date": _iso(p.need_date),
                    "lead_time_days": p.lead_time_days,
                    "procedure_code": p.procedure_code,
                    "procedure_days": bp.procedure_days if bp else ev.procedure_days(cat, p),
                    "proposed_award_date": _iso(bp.award_date) if bp else None,
                    "proposed_start_date": _iso(bp.start_date) if bp else None,
                    "is_advance": p.is_advance,
                    "start_activity_id": _s(award_row.start_activity_id) if award_row else None,
                    "award_activity_id": _s(award_row.award_activity_id) if award_row else None,
                    "findings": ev.schedule_findings(cat, p, today=today, release_date=release),
                }
            )
        return {"release_date": _iso(release), "release_gate_code": concept.release_gate_code, "items": rows}

    async def confirm_schedule(
        self, project_id: uuid.UUID, package_ids: list[uuid.UUID], *, actor_id: uuid.UUID, role: str | None
    ) -> list[dict[str, Any]]:
        """Write the confirmed proposals as schedule activities (idempotent: re-confirm updates the dates)."""
        from app.modules.schedule.models import Activity, Schedule

        await self._require_steer(project_id, actor_id, role)
        concept = await self.get_concept(project_id)
        cat = await self.catalogue_of(concept)
        schedule = (
            (
                await self.session.execute(
                    select(Schedule).where(Schedule.project_id == project_id).order_by(Schedule.created_at)
                )
            )
            .scalars()
            .first()
        )
        if schedule is None:
            raise conflict("no_schedule")
        cps = {str(c.id): c for c in await plan.list_packages(self.session, project_id)}
        out = []
        for pid in package_ids:
            row = await self._award(project_id, pid, lock=True)
            cp = cps.get(str(pid))
            if cp is None:
                raise not_found("package_not_found")
            facts = await self._facts_of(project_id, cp, row)
            bp = ev.backward_pass(cat, facts)
            if bp is None:
                raise ProcurementError("schedule_needs_need_date_and_procedure", 422, detail=cp.code)
            for slot, day, label in (
                ("start_activity_id", bp.start_date, "start"),
                ("award_activity_id", bp.award_date, "award"),
            ):
                act_id = getattr(row, slot)
                act = await self.session.get(Activity, act_id) if act_id else None
                if act is None or act.schedule_id != schedule.id:
                    act = Activity(
                        schedule_id=schedule.id,
                        name=f"{cp.code} {label}",
                        start_date=day.isoformat(),
                        end_date=day.isoformat(),
                        duration_days=0,
                        activity_type="milestone",
                        metadata_={"award_package_id": str(pid), "procurement_milestone": label},
                    )
                    self.session.add(act)
                    await self.session.flush()
                    setattr(row, slot, act.id)
                else:
                    act.start_date = day.isoformat()
                    act.end_date = day.isoformat()
            out.append(
                {
                    "package_id": str(pid),
                    "start_activity_id": str(row.start_activity_id),
                    "award_activity_id": str(row.award_activity_id),
                    "start_date": bp.start_date.isoformat(),
                    "award_date": bp.award_date.isoformat(),
                }
            )
        await self.session.flush()
        await self._audit(actor_id, "procurement_concept", concept.id, "schedule_confirmed")
        return out

    # ── execution (rules 15, 16) ─────────────────────────────────────────

    async def _scope_lines(self, project_id: uuid.UUID, row: AwardPackage) -> list[dict[str, Any]]:
        """Scope lines from the BOQ section the package points at (positions under that section)."""
        if row.cost_ref_kind != "boq_section" or row.cost_ref_id is None:
            return []
        from app.modules.boq.models import BOQ, Position

        head = await self.session.get(Position, row.cost_ref_id)
        if head is None:
            return []
        boq = await self.session.get(BOQ, head.boq_id)
        if boq is None or boq.project_id != project_id:
            return []
        children = (
            (
                await self.session.execute(
                    select(Position).where(Position.parent_id == head.id).order_by(Position.sort_order)
                )
            )
            .scalars()
            .all()
        )
        return [
            {"code": p.ordinal, "description": p.description, "unit": p.unit or "lsum", "quantity": p.quantity or "0"}
            for p in children
            if (p.description or "").strip()
        ]

    async def create_execution(
        self,
        project_id: uuid.UUID,
        package_id: uuid.UUID,
        *,
        vehicle: str | None,
        submission_deadline: date | None,
        actor_id: uuid.UUID,
        role: str | None,
    ) -> dict[str, Any]:
        """Create ONE BidPackage (works, design, services) or ONE RFQ (supply) and link it (rule 15)."""
        await self._require_steer(project_id, actor_id, role)
        award = await self._award(project_id, package_id, lock=True)
        cp = await plan.get_package(self.session, project_id, package_id)
        if cp is None:
            raise not_found("package_not_found")
        if cp.link_id is not None:
            raise conflict("execution_exists", detail=f"{cp.link_kind}:{cp.link_id}")
        if award.state not in ("procedure_set", "shortlisted"):
            raise conflict("package_not_ready_for_execution", detail=award.state)
        kind = CONTRACT_PACKAGE_KIND_MAP.get(cp.kind)
        chosen = vehicle or ("rfq" if kind in SUPPLY_KINDS else "bid_package")
        if chosen == "rfq" and kind not in SUPPLY_KINDS:
            raise ProcurementError("vehicle_not_allowed_for_kind", 422, detail=kind)
        lines = await self._scope_lines(project_id, award)
        currency = award.currency or await self._project_currency(project_id)
        meta = {"award_package_id": str(package_id), "contract_package_id": str(package_id), "source": MODULE}
        if chosen == "rfq":
            from app.modules.rfq_bidding.schemas import RFQCreate, RFQLineCreate
            from app.modules.rfq_bidding.service import RFQService

            rfq = await RFQService(self.session).create_rfq(
                RFQCreate(
                    project_id=project_id,
                    title=cp.title or cp.code,
                    scope_of_work=cp.scope or None,
                    submission_deadline=_iso(submission_deadline),
                    currency_code=currency or "EUR",
                    evaluation_method="lowest_price" if award.evaluation_method == "lowest_price" else "best_value",
                    lines=[
                        RFQLineCreate(
                            code=ln["code"],
                            description=ln["description"],
                            unit=ln["unit"],
                            quantity=Decimal(str(ln["quantity"])),
                        )
                        for ln in lines
                    ],
                    metadata=meta,
                ),
                user_id=str(actor_id),
            )
            link_kind, link_id = plan.LINK_RFQ, rfq.id
        else:
            from app.modules.bid_management.models import BidPackageLineItem
            from app.modules.bid_management.schemas import BidPackageCreate
            from app.modules.bid_management.service import BidManagementService

            code = f"{cp.code}-{uuid.uuid4().hex[:6].upper()}"[:64]
            bp = await BidManagementService(self.session).create_package(
                BidPackageCreate(
                    project_id=project_id,
                    code=code,
                    title=cp.title or cp.code,
                    scope_description=cp.scope,
                    submission_deadline=_iso(submission_deadline),
                    currency=currency or "EUR",
                    total_budget_estimate=award.estimated_value or Decimal("0"),
                    metadata=meta,
                ),
                user_id=str(actor_id),
            )
            for i, ln in enumerate(lines):
                self.session.add(
                    BidPackageLineItem(
                        package_id=bp.id,
                        code=ln["code"],
                        description=ln["description"],
                        unit=ln["unit"],
                        quantity=str(ln["quantity"]),
                        order_index=i,
                    )
                )
            link_kind, link_id = plan.LINK_BID_PACKAGE, bp.id
        try:
            linked = await plan.set_link_once(self.session, project_id, package_id, link_kind, link_id)
        except plan.PlanUnavailableError as exc:
            raise conflict("package_plan_unavailable") from exc
        if not linked:
            # A concurrent creation won the link; the caller's transaction (and this vehicle) rolls back.
            raise conflict("execution_exists")
        await self.session.flush()
        await self._audit(
            actor_id,
            "procurement_award_package",
            package_id,
            "execution_created",
            details={"kind": link_kind, "id": str(link_id)},
        )
        self._publish(
            "execution.created",
            {"project_id": str(project_id), "package_id": str(package_id), "kind": link_kind, "id": str(link_id)},
        )
        return {"package_id": str(package_id), "kind": link_kind, "id": str(link_id), "lines": len(lines)}

    async def _project_currency(self, project_id: uuid.UUID) -> str:
        from app.modules.projects.models import Project

        p = await self.session.get(Project, project_id)
        return (getattr(p, "currency", "") or "") if p else ""

    async def read_back(self, link_kind: str, link_id: uuid.UUID, target: str) -> AwardPackage | None:
        """Rule 16: move the award package of a linked vehicle to ``in_tender`` / ``awarded``, idempotently."""
        cp = await plan.find_by_link(self.session, link_kind, link_id)
        if cp is None:
            return None
        q = select(AwardPackage).where(AwardPackage.id == cp.id).with_for_update()
        row = (await self.session.execute(q)).scalars().first()
        if row is None:
            return None
        nxt = read_back_target(row.state, target)
        if nxt is None:
            return row
        before = row.state
        row.state = nxt
        row.state_before = None
        await self.session.flush()
        await self._audit(
            None, "procurement_award_package", row.id, f"read_back_{nxt}", from_status=before, to_status=nxt
        )
        return row

    # ── frameworks (rule 13, Decision 6) ─────────────────────────────────

    async def _framework(
        self, tenant_id: str | None, framework_id: uuid.UUID, *, lock: bool = False
    ) -> FrameworkAgreement:
        q = select(FrameworkAgreement).where(FrameworkAgreement.id == framework_id)
        if lock:
            q = q.with_for_update()
        row = (await self.session.execute(q)).scalars().first()
        if row is None or not tenant_id or row.tenant_id != tenant_id:
            raise not_found("framework_not_found")
        return row

    async def list_frameworks(self, tenant_id: str | None) -> list[FrameworkAgreement]:
        if not tenant_id:
            return []
        return list(
            (
                await self.session.execute(
                    select(FrameworkAgreement)
                    .where(FrameworkAgreement.tenant_id == tenant_id)
                    .order_by(FrameworkAgreement.code)
                )
            )
            .scalars()
            .all()
        )

    async def create_framework(
        self, tenant_id: str | None, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> FrameworkAgreement:
        if not tenant_id:
            raise forbidden("no_tenant")
        if data["end_date"] < data["start_date"]:
            raise ProcurementError("framework_dates_inverted", 422)
        await self._require_company(data)
        row = FrameworkAgreement(
            tenant_id=tenant_id,
            created_by=actor_id,
            state="draft",
            **{**data, "start_date": _iso(data["start_date"]), "end_date": _iso(data["end_date"])},
        )
        self.session.add(row)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except Exception as exc:
            raise conflict("framework_code_exists") from exc
        await self._audit(actor_id, "procurement_framework", row.id, "created")
        return row

    async def patch_framework(
        self, tenant_id: str | None, framework_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID
    ) -> FrameworkAgreement:
        row = await self._framework(tenant_id, framework_id, lock=True)
        if row.state in ("expired", "terminated"):
            raise conflict("framework_closed")
        for key, value in data.items():
            setattr(row, key, _iso(value) if key == "end_date" else value)
        await self.session.flush()
        return row

    async def transition_framework(
        self, tenant_id: str | None, framework_id: uuid.UUID, target: str, *, actor_id: uuid.UUID
    ) -> FrameworkAgreement:
        row = await self._framework(tenant_id, framework_id, lock=True)
        if not can_transition(FRAMEWORK_FSM, row.state, target):
            raise conflict("invalid_transition", detail=f"{row.state}->{target}")
        before = row.state
        row.state = target
        await self.session.flush()
        await self._audit(actor_id, "procurement_framework", row.id, target, from_status=before, to_status=target)
        return row

    async def ledger(self, tenant_id: str | None, framework_id: uuid.UUID) -> dict[str, Any]:
        """Call-off ledger: linked award packages (estimates, all projects of the tenant) and tagged POs."""
        row = await self._framework(tenant_id, framework_id)
        return await self._ledger_of(row)

    async def _ledger_of(self, row: FrameworkAgreement) -> dict[str, Any]:
        from app.modules.procurement.models import PurchaseOrder

        pkgs = (
            (
                await self.session.execute(
                    select(AwardPackage).where(
                        AwardPackage.framework_agreement_id == row.id, AwardPackage.state != "cancelled"
                    )
                )
            )
            .scalars()
            .all()
        )
        entries = [
            {
                "kind": "award_package",
                "id": str(p.id),
                "project_id": str(p.project_id),
                "amount": _dec(p.estimated_value or Decimal("0")),
                "currency": p.currency,
                "state": p.state,
            }
            for p in pkgs
        ]
        pos: list[Any] = []
        try:
            async with self.session.begin_nested():
                res = await self.session.execute(
                    select(PurchaseOrder).where(
                        PurchaseOrder.metadata_["framework_agreement_id"].as_string() == str(row.id)
                    )
                )
                pos = list(res.scalars().all())
        except Exception:
            logger.debug("framework ledger: PO lookup failed", exc_info=True)
        pkg_ids = {str(p.id) for p in pkgs}
        for po in pos:
            meta = po.metadata_ or {}
            if str(meta.get("award_package_id") or "") in pkg_ids:
                continue  # counted through its package already
            entries.append(
                {
                    "kind": "purchase_order",
                    "id": str(po.id),
                    "project_id": str(po.project_id),
                    "amount": format(Decimal(str(po.amount_subtotal or "0")), "f"),
                    "currency": po.currency_code,
                    "state": po.status,
                }
            )
        same = [
            Decimal(e["amount"]) for e in entries if (e["currency"] or row.currency).upper() == row.currency.upper()
        ]
        other = [e for e in entries if (e["currency"] or row.currency).upper() != row.currency.upper()]
        call_off = sum(same, Decimal("0"))
        return {
            "framework_id": str(row.id),
            "max_value": _dec(row.max_value),
            "currency": row.currency,
            "call_off_value": _dec(call_off),
            "remaining_value": _dec(row.max_value - call_off),
            "unconverted_entries": len(other),
            "items": entries,
            "total": len(entries),
        }

    async def _framework_facts(self, framework_id: str | None) -> dict[str, Any] | None:
        if not framework_id:
            return None
        row = await self.session.get(FrameworkAgreement, uuid.UUID(framework_id))
        if row is None:
            return None
        ledger = await self._ledger_of(row)
        items = ledger["items"]

        def remaining_excluding(pkg_id: str) -> Decimal:
            used = sum(
                (
                    Decimal(e["amount"])
                    for e in items
                    if e["id"] != pkg_id and (e["currency"] or row.currency).upper() == row.currency.upper()
                ),
                Decimal("0"),
            )
            return row.max_value - used

        return {
            "state": row.state,
            "package_kinds": row.package_kinds,
            "end_date": _day(row.end_date),
            "remaining_excluding": remaining_excluding,
        }

    async def _link_framework(self, award: AwardPackage, tenant_id: str | None) -> None:
        """Calling off: the framework of the caller's company, active, with value left (locked, rule 13)."""
        fw = await self._framework(tenant_id, award.framework_agreement_id, lock=True)
        if fw.state != "active":
            raise conflict("framework_not_active", detail=fw.state)
        facts = await self._framework_facts(str(fw.id))
        remaining = facts["remaining_excluding"](str(award.id)) if facts else fw.max_value
        if award.estimated_value is not None and remaining < award.estimated_value:
            raise ProcurementError("framework_exhausted", 422, detail=format(remaining, "f"))

    async def _prequal_findings(
        self,
        project_id: uuid.UUID,
        cat: ProcurementCatalogue,
        p: ev.PackageFacts,
        row: AwardPackage,
        award_date: date | None,
    ) -> list[dict[str, Any]]:
        if row.state not in ("shortlisted",):
            return []
        view = await self.candidate_views(project_id, row.id)
        return view["findings"]

    # ── readiness ────────────────────────────────────────────────────────

    async def readiness(self, project_id: uuid.UUID) -> dict[str, Any]:
        concept = await self.find_concept(project_id)
        if concept is None:
            return {"state": None, "approved": False, "blocking": 0}
        state = await self.effective_state(concept)
        blocking = [f for f in await self.findings(project_id) if f["blocks_approval"]]
        return {"state": state, "approved": state in ("approved", "binding"), "blocking": len(blocking)}
