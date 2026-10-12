# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Design management service: every write and every computed view of the module.

Sections, in SPEC build order:
    setup       -- pin a numbering scheme and a reports catalogue; scheme change with renumber (rule 9)
    wbs         -- the one PSP (``ProjectWBS``) with rules 1-4
    roles, approval points (rules 21, 22)
    deliverables (rule 15, computed state)
    numbering   -- preview, allocate under row lock, validate (rules 5-8, 10) and the CDE hook
    drawings    -- the register: a CDE container plus the 1:1 extension (rule 11)
    distribution and releases (rules 12-14)
    reviews, reports (rules 17, 18), permits (rules 19, 20)
    readiness   -- governance evidence (rule 16), frame documents (rule 23), validation payload

Callers pass ids already scoped to a project the caller may access (the router
runs ``verify_project_access``); every child row is looked up by
``(project_id, id)``, so an id from another project is 404.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log import log_activity
from app.core.events import publish_after_commit
from app.core.fsm import FSMError
from app.modules.design_management import fsm as dfsm
from app.modules.design_management import numbering as nb
from app.modules.design_management import rules as dr
from app.modules.design_management import wbs as wr
from app.modules.design_management import wbs_refs
from app.modules.design_management.catalogue import (
    DEFAULT_REPORTS_ID,
    NUMBERING_KIND,
    REPORTS_KIND,
    DesignReports,
    DrawingNumbering,
    default_scheme_id_for_country,
    register_kinds,
)
from app.modules.design_management.errors import DesignError, conflict, forbidden, not_found
from app.modules.design_management.models import (
    DesignApprovalPoint,
    DesignDeliverable,
    DesignDistributionRule,
    DesignDrawing,
    DesignNumberCounter,
    DesignPermit,
    DesignPermitItem,
    DesignRelease,
    DesignReport,
    DesignReview,
    DesignReviewComment,
    DesignRole,
    DesignSetup,
)

logger = logging.getLogger(__name__)

DESIGN_AREA_CODES: tuple[str, ...] = ("m07_design_management",)
FRAME_DOCUMENT_TYPES: tuple[str, ...] = ("m07_design_management_frame",)
_PART_COLUMNS = (
    "originator_code",
    "functional_breakdown",
    "spatial_breakdown",
    "form_code",
    "discipline_code",
    "sequence_number",
)
APPROVAL_TARGET_KIND = "design_approval_point"
RELEASE_TARGET_KIND = "design_release"
PARTY_KINDS = (
    "owner",
    "lead_designer",
    "discipline_designer",
    "specialist",
    "checker",
    "authority",
    "contractor_designer",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _uuid(value: Any) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError) as exc:
        raise DesignError("invalid_id", 422, detail=str(value)) from exc


def _uuids(values: Any) -> list[str]:
    return [str(_uuid(v)) for v in (values or [])]


class DesignService:
    """Business logic of design management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── plumbing ──────────────────────────────────────────────────────────

    async def _fsm(self, machine: Any, entity: Any, target: str, actor_id: Any, reason: str | None = None) -> None:
        try:
            await machine.apply(
                self.session,
                entity,
                target,
                actor_id=_s(actor_id),
                reason=reason,
                extra_metadata={"project_id": _s(getattr(entity, "project_id", None))},
                entity_type=machine.name,
            )
        except FSMError as exc:
            raise conflict("invalid_transition", detail=str(exc)) from exc

    async def _audit(self, actor_id: Any, entity_type: str, entity_id: Any, action: str, **meta: Any) -> None:
        await log_activity(
            self.session,
            actor_id=_s(actor_id),
            entity_type=entity_type,
            entity_id=_s(entity_id),
            action=action,
            metadata={k: _s(v) if isinstance(v, uuid.UUID) else v for k, v in meta.items()},
        )

    def _publish(self, name: str, **data: Any) -> None:
        payload = {k: _s(v) if isinstance(v, uuid.UUID) else v for k, v in data.items()}
        publish_after_commit(self.session, f"design_management.{name}", payload, source_module="oe_design_management")

    async def _get(self, model: Any, project_id: uuid.UUID, row_id: Any, code: str, *, lock: bool = False) -> Any:
        stmt = select(model).where(model.id == _uuid(row_id), model.project_id == project_id)
        if lock:
            stmt = stmt.with_for_update()
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise not_found(code)
        return row

    async def _list(self, model: Any, project_id: uuid.UUID, *order: Any) -> list[Any]:
        stmt = select(model).where(model.project_id == project_id)
        if order:
            stmt = stmt.order_by(*order)
        return list((await self.session.execute(stmt)).scalars().all())

    async def _add(self, row: Any) -> Any:
        self.session.add(row)
        await self.session.flush()
        return row

    async def _project(self, project_id: uuid.UUID) -> Any:
        from app.modules.projects.models import Project

        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("project_not_found")
        return project

    async def _next_code(self, model: Any, project_id: uuid.UUID, prefix: str) -> str:
        count = (
            await self.session.execute(select(func.count()).select_from(model).where(model.project_id == project_id))
        ).scalar_one()
        existing = {
            c for (c,) in (await self.session.execute(select(model.code).where(model.project_id == project_id)))
        }
        n = int(count) + 1
        while f"{prefix}-{n:03d}" in existing:
            n += 1
        return f"{prefix}-{n:03d}"

    # ── governance phase model ────────────────────────────────────────────

    async def phases(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """The phases of the project's pinned governance model (SPEC decision 12); empty when none is pinned."""
        from app.modules.project_governance.catalogue import label_of
        from app.modules.project_governance.repository import GovernanceRepository
        from app.modules.project_governance.service import GovernanceService

        model = await GovernanceRepository(self.session).get_model(project_id)
        if model is None:
            return []
        catalogue = await GovernanceService(self.session).catalogue_for(model)
        return [
            {"code": p.code, "order": p.order, "spine_key": p.spine_key, "name": label_of(p.name_key, p.labels)}
            for p in sorted(catalogue.phases, key=lambda p: p.order)
        ]

    async def _check_phase(self, project_id: uuid.UUID, phase_code: str | None) -> None:
        if not phase_code:
            return
        codes = {p["code"] for p in await self.phases(project_id)}
        if codes and phase_code not in codes:
            raise DesignError("phase_unknown", 422, detail=phase_code)

    # ── setup and catalogues ──────────────────────────────────────────────

    async def get_setup(self, project_id: uuid.UUID, *, lock: bool = False) -> DesignSetup | None:
        stmt = select(DesignSetup).where(DesignSetup.project_id == project_id)
        if lock:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def require_setup(self, project_id: uuid.UUID, *, lock: bool = False) -> DesignSetup:
        setup = await self.get_setup(project_id, lock=lock)
        if setup is None:
            raise not_found("setup_missing")
        return setup

    async def scheme(self, setup: DesignSetup) -> DrawingNumbering:
        from app.modules.project_governance.catalogue_store import resolve_catalogue

        register_kinds()
        return await resolve_catalogue(
            self.session, setup.scheme_source, setup.scheme_id, setup.scheme_version, kind=NUMBERING_KIND
        )

    async def reports_catalogue(self, setup: DesignSetup) -> DesignReports:
        from app.modules.project_governance.catalogue_store import resolve_catalogue

        register_kinds()
        return await resolve_catalogue(
            self.session, setup.reports_source, setup.reports_id, setup.reports_version, kind=REPORTS_KIND
        )

    async def _pinnable(self, tenant_id: str | None, source: str, cid: str, version: int | None, kind: str) -> int:
        from app.modules.project_governance.catalogue_store import CatalogueStore

        register_kinds()
        return await CatalogueStore(self.session).assert_pinnable(tenant_id, source, cid, version, kind=kind)

    async def assert_not_binding(self, project_id: uuid.UUID) -> None:
        """Rule 23: once the m07 frame document is binding, changes go through a governance change request."""
        from app.modules.project_governance.models import GovernanceArea, GovernanceDocument

        stmt = (
            select(GovernanceDocument.id)
            .join(GovernanceArea, GovernanceArea.id == GovernanceDocument.area_id)
            .where(
                GovernanceDocument.project_id == project_id,
                GovernanceArea.code.in_(DESIGN_AREA_CODES),
                GovernanceDocument.status == "binding",
            )
        )
        if (await self.session.execute(stmt)).first() is not None:
            raise conflict("binding_requires_change_request")

    async def set_setup(
        self,
        project_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        tenant_id: str | None,
        scheme_source: str = "shipped",
        scheme_id: str | None = None,
        scheme_version: int | None = None,
        reports_source: str = "shipped",
        reports_id: str | None = None,
        reports_version: int | None = None,
        four_eyes_release: bool = True,
    ) -> DesignSetup:
        """Pin a scheme and a reports catalogue on a project for the first time."""
        if await self.get_setup(project_id) is not None:
            raise conflict("setup_exists")
        project = await self._project(project_id)
        scheme_id = scheme_id or default_scheme_id_for_country(getattr(project, "country_code", None))
        reports_id = reports_id or DEFAULT_REPORTS_ID
        sv = await self._pinnable(tenant_id, scheme_source, scheme_id, scheme_version, NUMBERING_KIND)
        rv = await self._pinnable(tenant_id, reports_source, reports_id, reports_version, REPORTS_KIND)
        setup = await self._add(
            DesignSetup(
                project_id=project_id,
                scheme_source=scheme_source,
                scheme_id=scheme_id,
                scheme_version=sv,
                reports_source=reports_source,
                reports_id=reports_id,
                reports_version=rv,
                previous_schemes=[],
                four_eyes_release=four_eyes_release,
                target_suitability={},
                created_by=actor_id,
            )
        )
        await self._audit(actor_id, "design_setup", setup.id, "created", scheme=f"{scheme_source}:{scheme_id}@{sv}")
        self._publish("setup.pinned", project_id=project_id, scheme_id=scheme_id, version=sv)
        return setup

    async def update_setup(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> DesignSetup:
        setup = await self.require_setup(project_id, lock=True)
        if {"hierarchical_codes", "wbs_separator", "target_suitability"} & data.keys():
            await self.assert_not_binding(project_id)
        for key in (
            "four_eyes_release",
            "default_distribution_purpose",
            "hierarchical_codes",
            "wbs_separator",
            "target_suitability",
            "approval_route_id",
            "release_route_id",
            "lead_designer_role_id",
        ):
            if key in data:
                value = data[key]
                if key.endswith("_id"):
                    value = _uuid(value)
                    if key == "lead_designer_role_id" and value is not None:
                        await self._get(DesignRole, project_id, value, "role_not_found")
                setattr(setup, key, value)
        await self.session.flush()
        await self._audit(actor_id, "design_setup", setup.id, "updated", fields=sorted(data))
        return setup

    async def change_scheme(
        self,
        project_id: uuid.UUID,
        *,
        actor_id: uuid.UUID,
        tenant_id: str | None,
        source: str,
        scheme_id: str,
        version: int | None = None,
        reports: bool = False,
    ) -> dict[str, Any]:
        """Rule 9: pin another scheme (or reports catalogue); existing numbers are kept and flagged."""
        await self.assert_not_binding(project_id)
        setup = await self.require_setup(project_id, lock=True)
        if reports:
            setup.reports_version = await self._pinnable(tenant_id, source, scheme_id, version, REPORTS_KIND)
            setup.reports_source, setup.reports_id = source, scheme_id
            await self.session.flush()
            return {"setup": setup, "legacy": 0}
        pinned = await self._pinnable(tenant_id, source, scheme_id, version, NUMBERING_KIND)
        setup.previous_schemes = [
            *(setup.previous_schemes or []),
            {
                "source": setup.scheme_source,
                "id": setup.scheme_id,
                "version": setup.scheme_version,
                "until": _now().isoformat(),
            },
        ]
        setup.scheme_source, setup.scheme_id, setup.scheme_version = source, scheme_id, pinned
        scheme = await self.scheme(setup)
        legacy = 0
        for drawing, container in await self._drawings_with_containers(project_id):
            if not nb.validate(scheme, container.container_code).valid:
                drawing.legacy_scheme = True
                legacy += 1
        await self.session.flush()
        await self._audit(actor_id, "design_setup", setup.id, "scheme_changed", scheme=scheme_id, legacy=legacy)
        self._publish("setup.scheme_changed", project_id=project_id, scheme_id=scheme_id, legacy=legacy)
        return {"setup": setup, "legacy": legacy}

    # ── WBS (rules 1-4) ───────────────────────────────────────────────────

    async def wbs_rows(self, project_id: uuid.UUID) -> list[Any]:
        from app.modules.projects.models import ProjectWBS

        stmt = (
            select(ProjectWBS)
            .where(ProjectWBS.project_id == project_id)
            .order_by(ProjectWBS.level, ProjectWBS.sort_order, ProjectWBS.code)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def _node(row: Any) -> wr.Node:
        return wr.Node(row.id, row.parent_id, row.code, bool((row.metadata_ or {}).get("closed")))

    async def _wbs_settings(self, project_id: uuid.UUID) -> tuple[bool, str]:
        setup = await self.get_setup(project_id)
        return (setup.hierarchical_codes, setup.wbs_separator) if setup else (True, ".")

    async def wbs_tree(self, project_id: uuid.UUID) -> dict[str, Any]:
        rows = await self.wbs_rows(project_id)
        counts = await wbs_refs.reference_counts(self.session, project_id, rows)
        duplicates = wr.duplicate_codes(self._node(r) for r in rows)
        return {"rows": rows, "counts": counts, "duplicates": duplicates}

    async def _wbs_get(self, project_id: uuid.UUID, node_id: Any) -> Any:
        from app.modules.projects.models import ProjectWBS

        return await self._get(ProjectWBS, project_id, node_id, "wbs_node_not_found", lock=True)

    def _rule(self, exc: wr.WbsRuleError) -> DesignError:
        return DesignError(exc.code, 409 if exc.code == "wbs_code_duplicate" else 422, detail=exc.detail or None)

    async def _lock_wbs(self, project_id: uuid.UUID) -> None:
        """Serialise WBS writes of one project: the setup row (or project row) is the lock."""
        from app.modules.projects.models import Project

        await self.session.execute(select(Project.id).where(Project.id == project_id).with_for_update())

    async def create_wbs(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> Any:
        from app.modules.projects.models import ProjectWBS

        await self._lock_wbs(project_id)
        rows = await self.wbs_rows(project_id)
        parent_id = _uuid(data.get("parent_id"))
        hierarchical, sep = await self._wbs_settings(project_id)
        code = (data.get("code") or "").strip()
        try:
            wr.check_code(
                [self._node(r) for r in rows], code=code, parent_id=parent_id, hierarchical=hierarchical, separator=sep
            )
        except wr.WbsRuleError as exc:
            raise self._rule(exc) from exc
        parent = next((r for r in rows if r.id == parent_id), None)
        meta = {"kind": data.get("kind") or "package"}
        if data.get("discipline"):
            meta["discipline"] = data["discipline"]
        row = await self._add(
            ProjectWBS(
                project_id=project_id,
                parent_id=parent_id,
                code=code,
                name=data.get("name") or code,
                level=(parent.level + 1) if parent else 0,
                sort_order=int(data.get("sort_order") or 0),
                wbs_type=data.get("wbs_type") or "cost",
                metadata_=meta,
            )
        )
        await self._audit(actor_id, "projects_wbs", row.id, "created", code=code)
        return row

    async def patch_wbs(self, project_id: uuid.UUID, node_id: Any, data: dict[str, Any], *, actor_id: uuid.UUID) -> Any:
        """Rename, re-kind, move (``parent_id``) or renumber (``code``, the subtree follows)."""
        await self._lock_wbs(project_id)
        row = await self._wbs_get(project_id, node_id)
        rows = await self.wbs_rows(project_id)
        nodes = [self._node(r) for r in rows]
        hierarchical, sep = await self._wbs_settings(project_id)
        new_parent = _uuid(data["parent_id"]) if "parent_id" in data else row.parent_id
        new_code = (data.get("code") or row.code).strip()
        try:
            wr.check_code(
                nodes, code=new_code, parent_id=new_parent, node_id=row.id, hierarchical=hierarchical, separator=sep
            )
            plan = wr.renumber_plan(nodes, row.id, new_code, separator=sep) if new_code != row.code else {}
        except wr.WbsRuleError as exc:
            raise self._rule(exc) from exc
        by_id = {r.id: r for r in rows}
        for nid, code in plan.items():
            by_id[nid].code = code
        if new_parent != row.parent_id:
            parent = by_id.get(new_parent) if new_parent else None
            row.parent_id = new_parent
            delta = ((parent.level + 1) if parent else 0) - row.level
            row.level += delta
            for d in wr.descendants(nodes, row.id):
                by_id[d.id].level += delta
        meta = dict(row.metadata_ or {})
        for key in ("kind", "discipline"):
            if key in data:
                meta[key] = data[key]
        row.metadata_ = meta
        if "name" in data:
            row.name = data["name"]
        await self.session.flush()
        await self._audit(actor_id, "projects_wbs", row.id, "updated", renumbered=len(plan))
        return row

    async def renumber_preview(self, project_id: uuid.UUID, node_id: Any, new_code: str) -> list[dict[str, str]]:
        row = await self._wbs_get(project_id, node_id)
        rows = await self.wbs_rows(project_id)
        _h, sep = await self._wbs_settings(project_id)
        try:
            plan = wr.renumber_plan([self._node(r) for r in rows], row.id, new_code, separator=sep)
        except wr.WbsRuleError as exc:
            raise self._rule(exc) from exc
        by_id = {r.id: r for r in rows}
        return [{"id": str(k), "old": by_id[k].code, "new": v} for k, v in plan.items()]

    async def close_wbs(self, project_id: uuid.UUID, node_id: Any, *, closed: bool, actor_id: uuid.UUID) -> Any:
        row = await self._wbs_get(project_id, node_id)
        row.metadata_ = {**(row.metadata_ or {}), "closed": closed}
        await self.session.flush()
        await self._audit(actor_id, "projects_wbs", row.id, "closed" if closed else "reopened")
        return row

    async def delete_wbs(self, project_id: uuid.UUID, node_id: Any, *, actor_id: uuid.UUID) -> None:
        """Rule 3: refused while the node or any descendant is referenced anywhere."""
        await self._lock_wbs(project_id)
        row = await self._wbs_get(project_id, node_id)
        rows = await self.wbs_rows(project_id)
        counts = await wbs_refs.reference_counts(self.session, project_id, rows)
        referenced = {uuid.UUID(k) for k in counts}
        if not wr.deletable([self._node(r) for r in rows], row.id, referenced):
            raise conflict("wbs_node_referenced")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "projects_wbs", row.id, "deleted")

    async def assert_wbs_usable(self, project_id: uuid.UUID, node_id: Any) -> uuid.UUID | None:
        """A WBS reference from this module: the node exists in the project and is not closed (rule 3)."""
        nid = _uuid(node_id)
        if nid is None:
            return None
        row = await self._wbs_get(project_id, nid)
        if (row.metadata_ or {}).get("closed"):
            raise DesignError("wbs_node_closed", 422, detail=row.code)
        return nid

    async def unresolved_wbs(self, project_id: uuid.UUID) -> list[wbs_refs.Reference]:
        return await wbs_refs.unresolved_references(self.session, project_id, await self.wbs_rows(project_id))

    # ── roles (rule 21) ───────────────────────────────────────────────────

    async def _check_originator(self, project_id: uuid.UUID, role: DesignRole) -> None:
        if role.party_kind != "discipline_designer":
            return
        if not (role.originator_code or "").strip():
            raise DesignError("originator_required", 422)
        stmt = select(DesignRole.id).where(
            DesignRole.project_id == project_id,
            func.upper(DesignRole.originator_code) == role.originator_code.upper(),
            DesignRole.id != role.id,
            DesignRole.party_kind == "discipline_designer",
            DesignRole.status != "released",
        )
        if (await self.session.execute(stmt)).first() is not None:
            raise conflict("originator_duplicate")

    async def create_role(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID) -> DesignRole:
        if data.get("party_kind") not in PARTY_KINDS:
            raise DesignError("party_kind_invalid", 422)
        wbs_ids = [str(await self.assert_wbs_usable(project_id, w)) for w in data.get("responsible_wbs_ids") or []]
        role = DesignRole(
            id=uuid.uuid4(),
            project_id=project_id,
            code=(data.get("code") or await self._next_code(DesignRole, project_id, "ROLE")).strip(),
            title=data.get("title") or "",
            party_kind=data["party_kind"],
            discipline_code=(data.get("discipline_code") or None),
            contact_id=_uuid(data.get("contact_id")),
            user_id=_uuid(data.get("user_id")),
            originator_code=(data.get("originator_code") or "").strip().upper() or None,
            contract_package_id=_uuid(data.get("contract_package_id")),
            responsible_wbs_ids=wbs_ids,
            status="planned",
        )
        await self._check_originator(project_id, role)
        await self._unique_code(DesignRole, project_id, role.code)
        await self._add(role)
        await self._audit(actor_id, "design_role", role.id, "created", code=role.code)
        return role

    async def _unique_code(self, model: Any, project_id: uuid.UUID, code: str, row_id: Any = None) -> None:
        stmt = select(model.id).where(model.project_id == project_id, model.code == code)
        if row_id is not None:
            stmt = stmt.where(model.id != row_id)
        if (await self.session.execute(stmt)).first() is not None:
            raise conflict("code_duplicate")

    async def patch_role(self, project_id: uuid.UUID, role_id: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        role = await self._get(DesignRole, project_id, role_id, "role_not_found", lock=True)
        if "state" in data and data["state"] != role.status:
            await self._fsm(dfsm.ROLE_FSM, role, data["state"], actor_id)
        for key in ("title", "discipline_code", "party_kind"):
            if key in data:
                setattr(role, key, data[key])
        if role.party_kind not in PARTY_KINDS:
            raise DesignError("party_kind_invalid", 422)
        for key in ("contact_id", "user_id", "contract_package_id"):
            if key in data:
                setattr(role, key, _uuid(data[key]))
        if "originator_code" in data:
            role.originator_code = (data["originator_code"] or "").strip().upper() or None
        if "responsible_wbs_ids" in data:
            role.responsible_wbs_ids = [
                str(await self.assert_wbs_usable(project_id, w)) for w in data["responsible_wbs_ids"] or []
            ]
        if "code" in data:
            await self._unique_code(DesignRole, project_id, data["code"], role.id)
            role.code = data["code"]
        await self._check_originator(project_id, role)
        await self.session.flush()
        await self._audit(actor_id, "design_role", role.id, "updated")
        return role

    async def delete_role(self, project_id: uuid.UUID, role_id: Any, *, actor_id: uuid.UUID) -> None:
        role = await self._get(DesignRole, project_id, role_id, "role_not_found")
        used = (
            await self.session.execute(
                select(func.count()).select_from(DesignDrawing).where(DesignDrawing.role_id == role.id)
            )
        ).scalar_one()
        if used:
            raise conflict("role_in_use")
        await self.session.delete(role)
        await self.session.flush()
        await self._audit(actor_id, "design_role", role.id, "deleted")

    async def roles(self, project_id: uuid.UUID) -> list[DesignRole]:
        return await self._list(DesignRole, project_id, DesignRole.code)

    # ── approval points (rule 22) ─────────────────────────────────────────

    async def create_approval_point(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        await self._check_phase(project_id, data.get("phase_code"))
        if data.get("approver_role_id"):
            await self._get(DesignRole, project_id, data["approver_role_id"], "role_not_found")
        code = data.get("code") or await self._next_code(DesignApprovalPoint, project_id, "AP")
        await self._unique_code(DesignApprovalPoint, project_id, code)
        row = await self._add(
            DesignApprovalPoint(
                project_id=project_id,
                code=code,
                title=data.get("title") or "",
                phase_code=data.get("phase_code"),
                kind=data["kind"],
                governance_gate_id=_uuid(data.get("governance_gate_id")),
                approver_role_id=_uuid(data.get("approver_role_id")),
                status="open",
                note=data.get("note") or "",
            )
        )
        await self._audit(actor_id, "design_approval_point", row.id, "created", code=code)
        return row

    async def patch_approval_point(self, project_id: uuid.UUID, ap_id: Any, data: dict[str, Any], *, actor_id):
        row = await self._get(DesignApprovalPoint, project_id, ap_id, "approval_point_not_found", lock=True)
        if row.status not in ("open", "rejected"):
            raise conflict("approval_point_locked")
        if "phase_code" in data:
            await self._check_phase(project_id, data["phase_code"])
        for key in ("title", "phase_code", "kind", "note"):
            if key in data:
                setattr(row, key, data[key])
        for key in ("governance_gate_id", "approver_role_id"):
            if key in data:
                setattr(row, key, _uuid(data[key]))
        await self.session.flush()
        return row

    async def _route(self, project_id: uuid.UUID, kind: str, pinned: uuid.UUID | None) -> Any:
        from app.modules.approval_routes.service import ApprovalRouteService

        svc = ApprovalRouteService(self.session)
        if pinned is not None:
            try:
                route = await svc.get_route(pinned)
            except Exception:
                route = None
            ok = route is not None and route.is_active and route.target_kind == kind
            return route if ok and route.project_id in (None, project_id) else None
        routes = [
            r
            for r in await svc.list_routes(project_id=project_id, target_kind=kind, include_inactive=False)
            if r.project_id in (None, project_id)
        ]
        routes.sort(key=lambda r: (r.project_id is None, r.created_at))
        return routes[0] if routes else None

    async def _start_instance(self, route: Any, kind: str, target_id: uuid.UUID, actor_id: uuid.UUID) -> uuid.UUID:
        from fastapi import HTTPException

        from app.modules.approval_routes.schemas import InstanceCreate
        from app.modules.approval_routes.service import ApprovalRouteService

        try:
            instance = await ApprovalRouteService(self.session).start_instance(
                InstanceCreate(route_id=route.id, target_kind=kind, target_id=target_id), started_by=actor_id
            )
        except HTTPException as exc:
            raise DesignError("route_start_failed", exc.status_code, detail=str(exc.detail)) from exc
        return instance.id

    async def submit_approval_point(self, project_id: uuid.UUID, ap_id: Any, *, actor_id: uuid.UUID):
        row = await self._get(DesignApprovalPoint, project_id, ap_id, "approval_point_not_found", lock=True)
        setup = await self.get_setup(project_id)
        route = await self._route(project_id, APPROVAL_TARGET_KIND, setup.approval_route_id if setup else None)
        if route is None:
            raise DesignError("no_approval_route", 422)
        if row.status == "rejected":
            await self._fsm(dfsm.APPROVAL_POINT_FSM, row, "open", actor_id)
        await self._fsm(dfsm.APPROVAL_POINT_FSM, row, "in_review", actor_id)
        row.approval_instance_id = await self._start_instance(route, APPROVAL_TARGET_KIND, row.id, actor_id)
        row.submitted_by = actor_id
        await self.session.flush()
        self._publish("approval_point.submitted", project_id=project_id, approval_point_id=row.id)
        return row

    async def apply_approval_verdict(
        self, ap_id: uuid.UUID, instance_id: uuid.UUID | None, *, decision: str, decided_by: Any
    ) -> bool:
        """The route decided (rule 22: only the route entitles). Idempotent; four-eyes by submitter."""
        stmt = select(DesignApprovalPoint).where(DesignApprovalPoint.id == ap_id).with_for_update()
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None or row.status != "in_review":
            return False
        if instance_id is not None and row.approval_instance_id != instance_id:
            return False
        decider = _uuid(decided_by)
        setup = await self.get_setup(row.project_id)
        if decision == "approved" and setup and setup.four_eyes_release and decider and decider == row.submitted_by:
            # The route let the submitter approve their own point; four-eyes refuses it.
            decision = "rejected"
            row.note = (row.note + "\n" if row.note else "") + "four_eyes: approved by the submitter"
        await self._fsm(dfsm.APPROVAL_POINT_FSM, row, "approved" if decision == "approved" else "rejected", decider)
        row.decided_by, row.decided_at = decider, _now()
        await self.session.flush()
        self._publish(f"approval_point.{row.status}", project_id=row.project_id, approval_point_id=row.id)
        return True

    # ── deliverables (rule 15) ────────────────────────────────────────────

    async def create_deliverable(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        await self._check_phase(project_id, data.get("phase_code"))
        if data.get("role_id"):
            await self._get(DesignRole, project_id, data["role_id"], "role_not_found")
        code = data.get("code") or await self._next_code(DesignDeliverable, project_id, "DL")
        await self._unique_code(DesignDeliverable, project_id, code)
        row = await self._add(
            DesignDeliverable(
                project_id=project_id,
                code=code,
                title=data.get("title") or "",
                phase_code=data["phase_code"],
                role_id=_uuid(data.get("role_id")),
                discipline_code=data.get("discipline_code"),
                form_code=data.get("form_code"),
                wbs_node_id=await self.assert_wbs_usable(project_id, data.get("wbs_node_id")),
                planned_count=int(data.get("planned_count") or 1),
                schedule_activity_id=_uuid(data.get("schedule_activity_id")),
                required=bool(data.get("required", True)),
                required_for=_uuids(data.get("required_for")),
                target_suitability=data.get("target_suitability"),
                status="not_started",
            )
        )
        await self._audit(actor_id, "design_deliverable", row.id, "created", code=code)
        return row

    async def patch_deliverable(self, project_id: uuid.UUID, did: Any, data: dict[str, Any], *, actor_id):
        row = await self._get(DesignDeliverable, project_id, did, "deliverable_not_found", lock=True)
        if "planned_count" in data and int(data["planned_count"]) < row.planned_count:
            # Rule 15: a reduced count needs a reason, so "accepted" cannot be reached by shrinking the plan.
            if dr.rationale_error(data.get("planned_count_rationale")):
                raise DesignError("planned_count_reduction_needs_rationale", 422)
            row.planned_count_rationale = data["planned_count_rationale"]
        if "waived" in data:
            if data["waived"] and dr.rationale_error(data.get("waived_rationale")):
                raise DesignError("waiver_needs_rationale", 422)
            row.waived = bool(data["waived"])
            row.waived_rationale = data.get("waived_rationale") or ""
        if "phase_code" in data:
            await self._check_phase(project_id, data["phase_code"])
        if "wbs_node_id" in data:
            row.wbs_node_id = await self.assert_wbs_usable(project_id, data["wbs_node_id"])
        for key in ("title", "phase_code", "discipline_code", "form_code", "planned_count", "required"):
            if key in data:
                setattr(row, key, data[key])
        for key in ("role_id", "schedule_activity_id"):
            if key in data:
                setattr(row, key, _uuid(data[key]))
        if "target_suitability" in data:
            row.target_suitability = data["target_suitability"]
        if "required_for" in data:
            row.required_for = _uuids(data["required_for"])
        await self.refresh_deliverable(row)
        await self._audit(actor_id, "design_deliverable", row.id, "updated")
        return row

    async def refresh_deliverable(self, row: DesignDeliverable) -> str:
        """Recompute the state from the linked drawings' CDE states and cache it."""
        from app.modules.cde.models import DocumentContainer

        setup = await self.get_setup(row.project_id)
        stmt = (
            select(DocumentContainer)
            .join(DesignDrawing, DesignDrawing.container_id == DocumentContainer.id)
            .where(DesignDrawing.deliverable_id == row.id, DesignDrawing.project_id == row.project_id)
        )
        containers = list((await self.session.execute(stmt)).scalars().all())
        target = row.target_suitability or ((setup.target_suitability or {}).get(row.phase_code) if setup else None)
        state = dr.deliverable_state(
            [
                dr.DrawingState(c.id, c.cde_state, c.suitability_code, c.current_revision_id is not None)
                for c in containers
            ],
            planned_count=row.planned_count,
            target_suitability=target,
            waived=row.waived,
        )
        row.status = state
        await self.session.flush()
        return state

    async def deliverables(self, project_id: uuid.UUID, *, refresh: bool = True) -> list[DesignDeliverable]:
        rows = await self._list(DesignDeliverable, project_id, DesignDeliverable.phase_code, DesignDeliverable.code)
        if refresh:
            for row in rows:
                await self.refresh_deliverable(row)
        return rows

    async def delete_deliverable(self, project_id: uuid.UUID, did: Any, *, actor_id: uuid.UUID) -> None:
        row = await self._get(DesignDeliverable, project_id, did, "deliverable_not_found")
        for d in (
            await self.session.execute(select(DesignDrawing).where(DesignDrawing.deliverable_id == row.id))
        ).scalars():
            d.deliverable_id = None
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "design_deliverable", row.id, "deleted")

    # ── numbering (rules 5-8, 10) ─────────────────────────────────────────

    async def _field_values(
        self, project_id: uuid.UUID, scheme: DrawingNumbering, given: dict[str, Any], role: DesignRole | None
    ) -> dict[str, str]:
        """Fill each field from what the user typed, else its ``source_field``."""
        project = await self._project(project_id)
        wbs_code = None
        if given.get("wbs_node_id"):
            wbs_code = (await self._wbs_get(project_id, given["wbs_node_id"])).code
        source = {
            "project.code": getattr(project, "project_code", None),
            "role.originator_code": role.originator_code if role else None,
            "role.discipline_code": role.discipline_code if role else None,
            "drawing.phase_code": given.get("phase_code"),
            "drawing.sheet_size": given.get("sheet_size"),
            "wbs.code": wbs_code,
        }
        typed = given.get("fields") or {}
        out: dict[str, str] = {}
        for f in scheme.fields:
            if f.code == "number":
                continue
            value = typed.get(f.code) or source.get(f.source_field) or ""
            out[f.code] = nb.normalise(scheme, str(value))
        return out

    async def _counter_peek(self, project_id: uuid.UUID, key: str) -> int:
        stmt = select(DesignNumberCounter.next_value).where(
            DesignNumberCounter.project_id == project_id, DesignNumberCounter.scope_key == key
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() or 1

    async def _counter_row(self, project_id: uuid.UUID, key: str) -> DesignNumberCounter:
        """The counter row under a row lock, created race-free on first use (insert-on-conflict, then lock)."""
        bind = self.session.get_bind()
        dialect = getattr(getattr(bind, "dialect", None), "name", "")
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            await self.session.execute(
                pg_insert(DesignNumberCounter)
                .values(id=uuid.uuid4(), project_id=project_id, scope_key=key, next_value=1)
                .on_conflict_do_nothing(constraint="uq_oe_dsg_counter_scope")
            )
        stmt = (
            select(DesignNumberCounter)
            .where(DesignNumberCounter.project_id == project_id, DesignNumberCounter.scope_key == key)
            .with_for_update()
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = await self._add(DesignNumberCounter(project_id=project_id, scope_key=key, next_value=1))
        return row

    async def _role_for(self, project_id: uuid.UUID, role_id: Any) -> DesignRole | None:
        return await self._get(DesignRole, project_id, role_id, "role_not_found") if role_id else None

    async def preview_number(self, project_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        """The number that WOULD be allocated now; allocates nothing."""
        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        values = await self._field_values(
            project_id, scheme, data, await self._role_for(project_id, data.get("role_id"))
        )
        missing = nb.missing_values(scheme, values)
        key = nb.scope_key(scheme, values)
        code = nb.compose(scheme, values, await self._counter_peek(project_id, key))
        return {"number": code, "fields": values, "missing": missing, "validation": nb.validate(scheme, code).as_dict()}

    async def allocate_number(self, project_id: uuid.UUID, data: dict[str, Any]) -> dict[str, Any]:
        """Rule 5: allocate under a row lock; concurrent calls never return the same number."""
        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        role = await self._role_for(project_id, data.get("role_id"))
        values = await self._field_values(project_id, scheme, data, role)
        missing = nb.missing_values(scheme, values)
        if missing:
            raise DesignError(
                "numbering_field_missing",
                422,
                violations=[{"code": "numbering_field_missing", "field": m, "value": None} for m in missing],
            )
        counter = await self._counter_row(project_id, nb.scope_key(scheme, values))
        code = nb.compose(scheme, values, counter.next_value)
        result = nb.validate(scheme, code)
        if not result.valid:
            raise DesignError("numbering_invalid", 422, violations=[i.as_dict() for i in result.issues])
        counter.next_value += 1
        await self.session.flush()
        return {"number": code, "fields": values, "parts": result.parts, "scheme_id": scheme.id}

    async def validate_number(self, project_id: uuid.UUID, code: str) -> dict[str, Any]:
        setup = await self.require_setup(project_id)
        return nb.validate(await self.scheme(setup), code).as_dict()

    async def bulk_validate(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Every register drawing against the pinned scheme (rules 6, 7, 21)."""
        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        originators = await self._active_originators(project_id)
        out = []
        for drawing, c in await self._drawings_with_containers(project_id):
            result = nb.validate(scheme, c.container_code)
            mismatch = nb.parts_mismatch(scheme, c.container_code, self._stored_parts(c)) if result.valid else []
            issues = [i.as_dict() for i in result.issues]
            issues += [{"code": "numbering_parts_mismatch", "field": f, "value": None} for f in mismatch]
            if c.originator_code and originators is not None and c.originator_code.upper() not in originators:
                issues.append({"code": "originator_unknown", "field": "originator", "value": c.originator_code})
            out.append(
                {
                    "drawing_id": str(drawing.id),
                    "container_id": str(c.id),
                    "number": c.container_code,
                    "valid": not issues,
                    "legacy_scheme": drawing.legacy_scheme,
                    "issues": issues,
                }
            )
        return out

    @staticmethod
    def _stored_parts(c: Any) -> dict[str, str | None]:
        return {
            "originator_code": c.originator_code,
            "functional_breakdown": c.functional_breakdown,
            "spatial_breakdown": c.spatial_breakdown,
            "form_code": c.form_code,
            "discipline_code": c.discipline_code,
            "sequence_number": c.sequence_number,
        }

    async def _active_originators(self, project_id: uuid.UUID) -> set[str] | None:
        roles = [r for r in await self.roles(project_id) if r.status in ("appointed", "active", "planned")]
        codes = {r.originator_code.upper() for r in roles if r.originator_code}
        return codes or None

    async def check_container_code(
        self, project_id: uuid.UUID, code: str, parts: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """The CDE hook: with a pinned scheme, the code must match it, agree with its parts and pass the counter."""
        setup = await self.get_setup(project_id)
        if setup is None:
            return []
        scheme = await self.scheme(setup)
        result = nb.validate(scheme, code)
        if not result.valid:
            return [i.as_dict() for i in result.issues]
        stored = {k: parts.get(k) for k in _PART_COLUMNS}
        if any(stored.values()):
            mismatch = nb.parts_mismatch(scheme, code, stored)
            if mismatch:
                return [{"code": "numbering_parts_mismatch", "field": f, "value": None} for f in mismatch]
        # Rule 8: a typed number moves the counter past it, so the generator never hands it out again.
        seq = nb.sequence_of(scheme, code)
        if seq is not None and result.parts:
            counter = await self._counter_row(project_id, nb.scope_key(scheme, nb.scope_values(result.parts)))
            if counter.next_value <= seq:
                counter.next_value = seq + 1
                await self.session.flush()
        return []

    async def renumber_preview_drawings(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Rule 9: proposed new numbers for every legacy drawing; nothing is applied."""
        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        peeks: dict[str, int] = {}
        out = []
        for drawing, c in await self._drawings_with_containers(project_id):
            if not drawing.legacy_scheme:
                continue
            role = await self.session.get(DesignRole, drawing.role_id) if drawing.role_id else None
            values = await self._field_values(
                project_id,
                scheme,
                {
                    "fields": {
                        "originator": c.originator_code,
                        "functional": c.functional_breakdown,
                        "spatial": c.spatial_breakdown,
                        "form": c.form_code,
                        "discipline": c.discipline_code,
                    },
                    "phase_code": drawing.phase_code,
                    "sheet_size": drawing.sheet_size,
                    "wbs_node_id": drawing.wbs_node_id,
                },
                role,
            )
            key = nb.scope_key(scheme, values)
            peeks.setdefault(key, await self._counter_peek(project_id, key))
            proposed = nb.compose(scheme, values, peeks[key])
            peeks[key] += 1
            out.append(
                {
                    "drawing_id": str(drawing.id),
                    "old": c.container_code,
                    "new": proposed,
                    "missing": nb.missing_values(scheme, values),
                }
            )
        return out

    async def renumber_apply(
        self, project_id: uuid.UUID, mapping: dict[str, str], *, actor_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        """Rule 9: apply a confirmed mapping ``{drawing_id: new number}``; old numbers become aliases."""
        from app.modules.cde.models import DocumentContainer

        await self.assert_not_binding(project_id)
        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        out = []
        for did, new_code in mapping.items():
            drawing = await self._get(DesignDrawing, project_id, did, "drawing_not_found", lock=True)
            c = await self.session.get(DocumentContainer, drawing.container_id)
            result = nb.validate(scheme, new_code)
            if not result.valid:
                raise DesignError("numbering_invalid", 422, violations=[i.as_dict() for i in result.issues])
            clash = (
                await self.session.execute(
                    select(DocumentContainer.id).where(
                        DocumentContainer.project_id == project_id,
                        DocumentContainer.container_code == new_code,
                        DocumentContainer.id != c.id,
                    )
                )
            ).first()
            if clash is not None or new_code in self._all_aliases(await self._drawings_flat(project_id)):
                raise conflict("number_taken", detail=new_code)
            await self.check_container_code(project_id, new_code, {})
            columns, extra = nb.container_parts(scheme, result.parts or {})
            drawing.aliases = [*(drawing.aliases or []), c.container_code]
            c.container_code = new_code
            for col, value in columns.items():
                if scheme.field(next(k for k, v in nb.CONTAINER_PART.items() if v == col)) is not None:
                    setattr(c, col, value)
            c.metadata_ = {**(c.metadata_ or {}), "numbering": {"scheme": scheme.id, "parts": extra}}
            drawing.legacy_scheme = False
            drawing.scheme_id, drawing.scheme_version = scheme.id, scheme.version
            out.append({"drawing_id": str(drawing.id), "old": drawing.aliases[-1], "new": new_code})
        await self.session.flush()
        await self._audit(actor_id, "design_setup", setup.id, "renumbered", count=len(out))
        return out

    @staticmethod
    def _all_aliases(drawings: list[DesignDrawing]) -> set[str]:
        return {a for d in drawings for a in (d.aliases or [])}

    async def _drawings_flat(self, project_id: uuid.UUID) -> list[DesignDrawing]:
        return await self._list(DesignDrawing, project_id)

    # ── drawings: the register (rule 11) ──────────────────────────────────

    async def _drawings_with_containers(self, project_id: uuid.UUID) -> list[tuple[DesignDrawing, Any]]:
        from app.modules.cde.models import DocumentContainer

        stmt = (
            select(DesignDrawing, DocumentContainer)
            .join(DocumentContainer, DocumentContainer.id == DesignDrawing.container_id)
            .where(DesignDrawing.project_id == project_id)
            .order_by(DocumentContainer.container_code)
        )
        return [(d, c) for d, c in (await self.session.execute(stmt)).all()]

    async def register(self, project_id: uuid.UUID, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """The drawing register: number, title, revision and status from CDE, plus our attributes."""
        from app.modules.cde.models import DocumentRevision

        f = filters or {}
        rows = await self._drawings_with_containers(project_id)
        rev_ids = [c.current_revision_id for _d, c in rows if c.current_revision_id]
        revisions = {}
        if rev_ids:
            for rev in (
                await self.session.execute(select(DocumentRevision).where(DocumentRevision.id.in_(rev_ids)))
            ).scalars():
                revisions[str(rev.id)] = rev
        issues = await self._last_issues(project_id)
        out = []
        q = (f.get("q") or "").strip().casefold()
        for d, c in rows:
            if f.get("phase_code") and d.phase_code != f["phase_code"]:
                continue
            if f.get("discipline_code") and c.discipline_code != f["discipline_code"]:
                continue
            if f.get("deliverable_id") and str(d.deliverable_id) != str(f["deliverable_id"]):
                continue
            if f.get("state") and c.cde_state != f["state"]:
                continue
            if q and q not in c.container_code.casefold() and q not in (d.title or "").casefold():
                if not any(q in a.casefold() for a in d.aliases or []):
                    continue
            rev = revisions.get(str(c.current_revision_id)) if c.current_revision_id else None
            mismatch = bool(d.title_block_number) and d.title_block_number.strip() != c.container_code
            last = issues.get(str(c.current_revision_id)) if c.current_revision_id else None
            out.append(
                {
                    "drawing": d,
                    "container": c,
                    "revision_code": rev.revision_code if rev else None,
                    "title_block_mismatch": mismatch,
                    "last_issue": last,
                }
            )
        return out

    async def _last_issues(self, project_id: uuid.UUID) -> dict[str, dict[str, Any]]:
        """``{revision_id: {"at", "recipients": [...]}}`` from issued releases."""
        out: dict[str, dict[str, Any]] = {}
        for rel in await self._list(DesignRelease, project_id, DesignRelease.issued_at):
            if rel.status != "issued":
                continue
            for entry in rel.issue_plan or []:
                for rid in entry.get("revision_ids", []):
                    slot = out.setdefault(rid, {"at": None, "recipients": []})
                    slot["at"] = rel.issued_at.isoformat() if rel.issued_at else None
                    if entry.get("recipient_key") not in slot["recipients"]:
                        slot["recipients"].append(entry.get("recipient_key"))
        return out

    async def create_drawing(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        """Create the CDE container (number generated or typed) and its register row, in one transaction."""
        from app.modules.cde.schemas import ContainerCreate
        from app.modules.cde.service import CDEService

        setup = await self.require_setup(project_id)
        scheme = await self.scheme(setup)
        role = await self._role_for(project_id, data.get("role_id"))
        if role is not None and role.status == "released":
            raise DesignError("role_not_active", 422)
        await self._check_phase(project_id, data.get("phase_code"))
        wbs_node_id = await self.assert_wbs_usable(project_id, data.get("wbs_node_id"))
        if data.get("deliverable_id"):
            await self._get(DesignDeliverable, project_id, data["deliverable_id"], "deliverable_not_found")
        typed = (data.get("number") or "").strip()
        if typed:
            result = nb.validate(scheme, typed)
            if not result.valid:
                raise DesignError("numbering_invalid", 422, violations=[i.as_dict() for i in result.issues])
            code, parts = typed, result.parts or {}
        else:
            allocated = await self.allocate_number(project_id, data)
            code, parts = allocated["number"], allocated["parts"] or {}
        if code in self._all_aliases(await self._drawings_flat(project_id)):
            raise conflict("number_taken", detail=code)
        originators = await self._active_originators(project_id)
        if parts.get("originator") and originators is not None and parts["originator"].upper() not in originators:
            raise DesignError("originator_unknown", 422, detail=parts["originator"])
        columns, extra = nb.container_parts(scheme, parts)
        container = await CDEService(self.session).create_container(
            ContainerCreate(
                project_id=project_id,
                container_code=code,
                title=data.get("title") or code,
                cde_state="wip",
                metadata={"numbering": {"scheme": scheme.id, "parts": extra}},
                **{k: v for k, v in columns.items() if v},
            ),
            user_id=_s(actor_id),
        )
        drawing = await self._add(
            DesignDrawing(
                project_id=project_id,
                container_id=container.id,
                title=data.get("title") or "",
                scale=data.get("scale") or "",
                sheet_size=data.get("sheet_size") or "",
                phase_code=data.get("phase_code"),
                deliverable_id=_uuid(data.get("deliverable_id")),
                wbs_node_id=wbs_node_id,
                role_id=role.id if role else None,
                planned_first_issue=data.get("planned_first_issue"),
                forecast_issue=data.get("forecast_issue"),
                schedule_activity_id=_uuid(data.get("schedule_activity_id")),
                scheme_id=scheme.id,
                scheme_version=scheme.version,
                aliases=[],
            )
        )
        await self._audit(actor_id, "design_drawing", drawing.id, "created", number=code)
        self._publish("drawing.created", project_id=project_id, drawing_id=drawing.id, number=code)
        return drawing, container

    async def patch_drawing(self, project_id: uuid.UUID, did: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        row = await self._get(DesignDrawing, project_id, did, "drawing_not_found", lock=True)
        if "phase_code" in data:
            await self._check_phase(project_id, data["phase_code"])
        if "wbs_node_id" in data:
            row.wbs_node_id = await self.assert_wbs_usable(project_id, data["wbs_node_id"])
        if data.get("deliverable_id"):
            await self._get(DesignDeliverable, project_id, data["deliverable_id"], "deliverable_not_found")
        if data.get("role_id"):
            await self._get(DesignRole, project_id, data["role_id"], "role_not_found")
        for key in ("title", "scale", "sheet_size", "phase_code", "planned_first_issue", "forecast_issue"):
            if key in data:
                setattr(row, key, data[key] or ("" if key in ("title", "scale", "sheet_size") else None))
        for key in ("deliverable_id", "role_id", "schedule_activity_id"):
            if key in data:
                setattr(row, key, _uuid(data[key]))
        if "title_block_number" in data:
            row.title_block_number = data["title_block_number"] or None
        await self.session.flush()
        await self._audit(actor_id, "design_drawing", row.id, "updated")
        return row

    async def supersede_drawing(self, project_id: uuid.UUID, did: Any, by_container_id: Any, *, actor_id):
        from app.modules.cde.models import DocumentContainer

        row = await self._get(DesignDrawing, project_id, did, "drawing_not_found", lock=True)
        target = await self.session.get(DocumentContainer, _uuid(by_container_id))
        if target is None or target.project_id != project_id or target.id == row.container_id:
            raise not_found("container_not_found")
        row.superseded_by_container_id = target.id
        await self.session.flush()
        await self._audit(actor_id, "design_drawing", row.id, "superseded", by=target.id)
        return row

    async def read_title_block(self, project_id: uuid.UUID, did: Any, sheet_text: str, *, actor_id: uuid.UUID):
        """Rule 11: read the sheet number from title block text and compare it with the container code."""
        from app.modules.documents import sheet_fields

        row = await self._get(DesignDrawing, project_id, did, "drawing_not_found", lock=True)
        reader = getattr(sheet_fields, "extract_sheet_fields", None) or getattr(sheet_fields, "read_sheet_fields", None)
        number = None
        if reader is not None:
            try:
                fields = reader(sheet_text)
                number = (fields or {}).get("sheet_number") if isinstance(fields, dict) else None
            except Exception:
                logger.debug("design: title block reader failed", exc_info=True)
        row.title_block_number = (number or sheet_text or "").strip()[:255] or None
        await self.session.flush()
        return row

    # ── distribution and releases (rules 12-14) ───────────────────────────

    async def create_dist_rule(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        await self._check_recipient(project_id, data)
        row = DesignDistributionRule(project_id=project_id)
        self._fill_rule(row, data)
        await self._add(row)
        await self._audit(actor_id, "design_dist_rule", row.id, "created")
        return row

    async def _check_recipient(self, project_id: uuid.UUID, data: dict[str, Any]) -> None:
        from app.modules.file_distribution.models import FileDistributionList

        list_id, role_id = _uuid(data.get("recipient_list_id")), _uuid(data.get("recipient_role_id"))
        if bool(list_id) == bool(role_id):
            raise DesignError("recipient_exactly_one", 422)
        if list_id:
            lst = await self.session.get(FileDistributionList, list_id)
            if lst is None or lst.project_id not in (None, project_id):
                raise not_found("distribution_list_not_found")
        else:
            await self._get(DesignRole, project_id, role_id, "role_not_found")

    @staticmethod
    def _fill_rule(row: DesignDistributionRule, data: dict[str, Any]) -> None:
        for key in ("recipient_list_id", "recipient_role_id"):
            if key in data:
                setattr(row, key, _uuid(data[key]))
        for key in ("discipline_codes", "form_codes", "phase_codes"):
            if key in data:
                setattr(row, key, list(data[key] or []))
        if "wbs_node_ids" in data:
            row.wbs_node_ids = _uuids(data["wbs_node_ids"])
        for key in ("min_suitability", "purpose", "format", "copies_paper", "ack_required", "active"):
            if key in data:
                setattr(row, key, data[key])

    async def patch_dist_rule(self, project_id: uuid.UUID, rid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        row = await self._get(DesignDistributionRule, project_id, rid, "dist_rule_not_found", lock=True)
        merged = {
            "recipient_list_id": data.get("recipient_list_id", row.recipient_list_id),
            "recipient_role_id": data.get("recipient_role_id", row.recipient_role_id),
        }
        await self._check_recipient(project_id, merged)
        self._fill_rule(row, data)
        await self.session.flush()
        return row

    async def delete_dist_rule(self, project_id: uuid.UUID, rid: Any, *, actor_id: uuid.UUID) -> None:
        row = await self._get(DesignDistributionRule, project_id, rid, "dist_rule_not_found")
        await self.session.delete(row)
        await self.session.flush()

    @staticmethod
    def _recipient_key(rule: DesignDistributionRule) -> str:
        return f"list:{rule.recipient_list_id}" if rule.recipient_list_id else f"role:{rule.recipient_role_id}"

    async def _revision_views(self, project_id: uuid.UUID, revision_ids: list[Any]) -> list[dr.RevisionView]:
        """Revisions of THIS project only; a foreign id is 404 (rule 24)."""
        from app.modules.cde.models import DocumentContainer, DocumentRevision

        ids = [_uuid(r) for r in revision_ids]
        if not ids:
            return []
        stmt = (
            select(DocumentRevision, DocumentContainer)
            .join(DocumentContainer, DocumentContainer.id == DocumentRevision.container_id)
            .where(DocumentRevision.id.in_(ids), DocumentContainer.project_id == project_id)
        )
        rows = (await self.session.execute(stmt)).all()
        if len(rows) != len(set(ids)):
            raise not_found("revision_not_found")
        drawings = {
            d.container_id: d
            for d in (
                await self.session.execute(
                    select(DesignDrawing).where(DesignDrawing.container_id.in_([c.id for _r, c in rows]))
                )
            ).scalars()
        }
        out = []
        for rev, c in rows:
            d = drawings.get(c.id)
            # A revision carries its own status at issue time; fall back to the container's suitability.
            code = (rev.metadata_ or {}).get("suitability_code") or c.suitability_code
            out.append(
                dr.RevisionView(
                    rev.id,
                    c.id,
                    code,
                    c.discipline_code,
                    c.form_code,
                    d.phase_code if d else None,
                    d.wbs_node_id if d else None,
                )
            )
        order = {rid: i for i, rid in enumerate(ids)}
        return sorted(out, key=lambda v: order[v.revision_id])

    async def _issued_pairs(self, project_id: uuid.UUID, exclude: uuid.UUID | None = None) -> set[tuple[str, Any]]:
        out: set[tuple[str, Any]] = set()
        for rel in await self._list(DesignRelease, project_id):
            if rel.status != "issued" or rel.id == exclude:
                continue
            for entry in rel.issue_plan or []:
                for rid in entry.get("revision_ids", []):
                    out.add((entry.get("recipient_key"), uuid.UUID(rid)))
        return out

    async def release_plan(self, project_id: uuid.UUID, release: DesignRelease) -> list[dr.RecipientPlan]:
        rules = [r for r in await self._list(DesignDistributionRule, project_id) if r.active]
        matrix = [
            dr.MatrixRule(
                r.id,
                self._recipient_key(r),
                tuple(r.discipline_codes or ()),
                tuple(r.form_codes or ()),
                tuple(r.phase_codes or ()),
                tuple(uuid.UUID(x) for x in r.wbs_node_ids or ()),
                r.min_suitability,
                r.purpose,
            )
            for r in rules
        ]
        views = await self._revision_views(project_id, release.revision_ids or [])
        return dr.distribution_plan(matrix, views, already_issued=await self._issued_pairs(project_id, release.id))

    async def create_release(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        setup = await self.get_setup(project_id)
        purpose = data.get("purpose") or (setup.default_distribution_purpose if setup else "for_information")
        views = await self._revision_views(project_id, data.get("revision_ids") or [])
        code = data.get("code") or await self._next_code(DesignRelease, project_id, "REL")
        await self._unique_code(DesignRelease, project_id, code)
        row = await self._add(
            DesignRelease(
                project_id=project_id,
                code=code,
                title=data.get("title") or code,
                purpose=purpose,
                revision_ids=[str(v.revision_id) for v in views],
                status="draft",
                transmittal_ids=[],
                issue_plan=[],
                prepared_by=actor_id,
            )
        )
        await self._audit(actor_id, "design_release", row.id, "created", code=code)
        return row

    async def patch_release(self, project_id: uuid.UUID, rid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        row = await self._get(DesignRelease, project_id, rid, "release_not_found", lock=True)
        if row.status != "draft":
            raise conflict("release_not_draft")
        if "revision_ids" in data:
            row.revision_ids = [
                str(v.revision_id) for v in await self._revision_views(project_id, data["revision_ids"])
            ]
        for key in ("title", "purpose"):
            if key in data:
                setattr(row, key, data[key])
        await self.session.flush()
        return row

    async def release_transition(self, project_id: uuid.UUID, rid: Any, target: str, *, actor_id: uuid.UUID):
        row = await self._get(DesignRelease, project_id, rid, "release_not_found", lock=True)
        if target == "ready":
            await self._check_release_content(project_id, row)
        if target == "issued":
            raise conflict("use_issue")
        await self._fsm(dfsm.RELEASE_FSM, row, target, actor_id)
        await self.session.flush()
        return row

    async def _check_release_content(self, project_id: uuid.UUID, row: DesignRelease) -> None:
        if not row.revision_ids:
            raise DesignError("release_empty", 422)
        views = await self._revision_views(project_id, row.revision_ids)
        errors = dr.release_content_errors(views, row.purpose)
        if errors:
            raise DesignError(errors[0][1], 422, violations=[{"code": c, "revision_id": str(r)} for r, c in errors])

    async def _recipients_for(self, project_id: uuid.UUID, key: str) -> list[dict[str, Any]]:
        from app.modules.file_distribution.models import FileDistributionMember

        kind, _, raw = key.partition(":")
        rid = uuid.UUID(raw)
        if kind == "list":
            members = (
                await self.session.execute(select(FileDistributionMember).where(FileDistributionMember.list_id == rid))
            ).scalars()
            return [{"recipient_name": m.display_name or m.email, "recipient_email": m.email} for m in members]
        role = await self.session.get(DesignRole, rid)
        if role is None or role.project_id != project_id:
            return []
        return [{"recipient_name": role.title or role.code, "recipient_user_id": role.user_id}]

    async def issue_release(
        self, project_id: uuid.UUID, rid: Any, *, actor_id: uuid.UUID, duplicate_reason: str = ""
    ) -> DesignRelease:
        """Rule 12: one transmittal per matching recipient with the pinned revisions; rule 14 duplicates need a reason."""
        from app.modules.transmittals.models import Transmittal
        from app.modules.transmittals.schemas import ItemCreate, RecipientCreate, TransmittalCreate
        from app.modules.transmittals.service import TransmittalService

        row = await self._get(DesignRelease, project_id, rid, "release_not_found", lock=True)
        if row.status != "ready":
            raise conflict("release_not_ready")
        setup = await self.get_setup(project_id)
        if setup and setup.four_eyes_release and row.prepared_by == actor_id:
            raise forbidden("release_four_eyes")
        await self._check_release_content(project_id, row)
        plans = await self.release_plan(project_id, row)
        if not any(p.revision_ids for p in plans):
            raise DesignError("release_no_recipients", 422)
        if any(p.duplicates for p in plans) and dr.rationale_error(duplicate_reason):
            raise DesignError(
                "duplicate_issue",
                409,
                violations=[
                    {"code": "duplicate_issue", "recipient": p.recipient_key, "revision_id": str(r)}
                    for p in plans
                    for r in p.duplicates
                ],
            )
        svc = TransmittalService(self.session)
        today = _now().date().isoformat()
        issue_plan, transmittal_ids = [], []
        for plan in plans:
            if not plan.revision_ids:
                continue
            recipients = await self._recipients_for(project_id, plan.recipient_key)
            tr = await svc.create_transmittal(
                TransmittalCreate(
                    project_id=project_id,
                    subject=f"{row.code} {row.title}"[:500],
                    purpose_code=plan.purpose if plan.purpose else row.purpose,
                    issued_date=today,
                    recipients=[RecipientCreate(**r) for r in recipients] or [RecipientCreate()],
                    items=[ItemCreate(revision_id=r, item_number=i) for i, r in enumerate(plan.revision_ids, start=1)],
                    metadata={"design_release_id": str(row.id), "recipient_key": plan.recipient_key},
                ),
                user_id=_s(actor_id),
            )
            transmittal_ids.append(str(tr.id))
            issue_plan.append(
                {
                    "recipient_key": plan.recipient_key,
                    "transmittal_id": str(tr.id),
                    "revision_ids": [str(r) for r in plan.revision_ids],
                    "excluded": [{"revision_id": str(r), "reason": c} for r, c in plan.excluded],
                    "duplicates": [str(r) for r in plan.duplicates],
                }
            )
        # ``create_transmittal`` rolls the session back on a number collision and retries; that
        # rollback would silently discard what this loop already wrote. Re-read before committing.
        if row not in self.session or row.status != "ready":
            raise conflict("concurrent_issue")
        found = (
            await self.session.execute(
                select(func.count())
                .select_from(Transmittal)
                .where(Transmittal.id.in_([uuid.UUID(t) for t in transmittal_ids]))
            )
        ).scalar_one()
        if found != len(transmittal_ids):
            raise conflict("concurrent_issue")
        for tid in transmittal_ids:
            await svc.issue_transmittal(uuid.UUID(tid))
        row.transmittal_ids, row.issue_plan = transmittal_ids, issue_plan
        row.duplicate_reason = duplicate_reason or ""
        await self._fsm(dfsm.RELEASE_FSM, row, "issued", actor_id)
        row.issued_by, row.issued_at = actor_id, _now()
        await self.session.flush()
        await self._audit(actor_id, "design_release", row.id, "issued", transmittals=len(transmittal_ids))
        self._publish("release.issued", project_id=project_id, release_id=row.id, transmittal_ids=transmittal_ids)
        return row

    # ── reviews ───────────────────────────────────────────────────────────

    async def create_review(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        await self._check_phase(project_id, data.get("phase_code"))
        for did in data.get("deliverable_ids") or []:
            await self._get(DesignDeliverable, project_id, did, "deliverable_not_found")
        for rid in data.get("reviewer_role_ids") or []:
            await self._get(DesignRole, project_id, rid, "role_not_found")
        code = data.get("code") or await self._next_code(DesignReview, project_id, "REV")
        await self._unique_code(DesignReview, project_id, code)
        row = await self._add(
            DesignReview(
                project_id=project_id,
                code=code,
                title=data.get("title") or code,
                phase_code=data["phase_code"],
                deliverable_ids=_uuids(data.get("deliverable_ids")),
                reviewer_role_ids=_uuids(data.get("reviewer_role_ids")),
                status="planned",
            )
        )
        await self._audit(actor_id, "design_review", row.id, "created", code=code)
        return row

    async def review_comments(self, project_id: uuid.UUID, review_id: uuid.UUID) -> list[DesignReviewComment]:
        stmt = (
            select(DesignReviewComment)
            .where(DesignReviewComment.project_id == project_id, DesignReviewComment.review_id == review_id)
            .order_by(DesignReviewComment.created_at)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def review_transition(self, project_id: uuid.UUID, rid: Any, target: str, *, actor_id: uuid.UUID):
        row = await self._get(DesignReview, project_id, rid, "review_not_found", lock=True)
        if target == "comments_closed":
            open_ = [c for c in await self.review_comments(project_id, row.id) if c.status in ("open", "answered")]
            if open_:
                raise conflict("review_comments_open")
        if target == "concluded":
            raise conflict("use_conclude")
        await self._fsm(dfsm.REVIEW_FSM, row, target, actor_id)
        await self.session.flush()
        return row

    async def conclude_review(self, project_id: uuid.UUID, rid: Any, outcome: str, *, actor_id: uuid.UUID):
        if outcome not in ("accepted", "accepted_with_comments", "rework"):
            raise DesignError("review_outcome_invalid", 422)
        row = await self._get(DesignReview, project_id, rid, "review_not_found", lock=True)
        await self._fsm(dfsm.REVIEW_FSM, row, "concluded", actor_id)
        row.outcome, row.concluded_by, row.concluded_at = outcome, actor_id, _now()
        await self.session.flush()
        self._publish("review.concluded", project_id=project_id, review_id=row.id, outcome=outcome)
        return row

    async def add_comment(self, project_id: uuid.UUID, rid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        review = await self._get(DesignReview, project_id, rid, "review_not_found", lock=True)
        if review.status not in ("planned", "open"):
            raise conflict("review_not_open")
        container_id = None
        if data.get("revision_id"):
            view = (await self._revision_views(project_id, [data["revision_id"]]))[0]
            container_id = view.container_id
        if not (data.get("text") or "").strip():
            raise DesignError("comment_text_required", 422)
        if data.get("severity", "minor") not in ("minor", "major", "critical"):
            raise DesignError("severity_invalid", 422)
        if review.status == "planned":
            await self._fsm(dfsm.REVIEW_FSM, review, "open", actor_id)
        row = await self._add(
            DesignReviewComment(
                project_id=project_id,
                review_id=review.id,
                container_id=container_id,
                revision_id=_uuid(data.get("revision_id")),
                text=data["text"].strip(),
                severity=data.get("severity", "minor"),
                status="open",
                created_by=actor_id,
            )
        )
        return row

    async def comment_transition(
        self, project_id: uuid.UUID, cid: Any, target: str, *, actor_id: uuid.UUID, answer: str = "", role_id=None
    ):
        row = await self._get(DesignReviewComment, project_id, cid, "comment_not_found", lock=True)
        if target == "answered":
            if dr.rationale_error(answer):
                raise DesignError("answer_required", 422)
            row.answer = answer
            if role_id:
                row.answered_by_role_id = (await self._get(DesignRole, project_id, role_id, "role_not_found")).id
        await self._fsm(dfsm.COMMENT_FSM, row, target, actor_id)
        await self.session.flush()
        return row

    # ── reports (rules 17, 18) ────────────────────────────────────────────

    async def create_report(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        setup = await self.require_setup(project_id)
        catalogue = await self.reports_catalogue(setup)
        kind = catalogue.kind(data.get("kind_code") or "")
        if kind is None:
            raise DesignError("report_kind_unknown", 422)
        check = data.get("independent_check") or kind.independent_check
        overridden = check != kind.independent_check
        # Rule 18: a catalogue hint overridden needs words.
        if overridden and dr.rationale_error(data.get("rationale")):
            raise DesignError("hint_override_needs_rationale", 422)
        await self._check_phase(project_id, data.get("phase_code"))
        for key in ("author_role_id", "checker_role_id"):
            if data.get(key):
                await self._get(DesignRole, project_id, data[key], "role_not_found")
        container_id = await self._container_in_project(project_id, data.get("container_id"))
        code = data.get("code") or await self._next_code(DesignReport, project_id, "RPT")
        await self._unique_code(DesignReport, project_id, code)
        row = await self._add(
            DesignReport(
                project_id=project_id,
                code=code,
                kind_code=kind.code,
                title=data.get("title") or code,
                phase_code=data.get("phase_code"),
                author_role_id=_uuid(data.get("author_role_id")),
                checker_role_id=_uuid(data.get("checker_role_id")),
                container_id=container_id,
                external_check=bool(data.get("external_check", False)),
                required=bool(data.get("required", True)),
                required_reason="catalogue" if data.get("from_catalogue") else "manual",
                independent_check=check,
                hint_overridden=overridden,
                rationale=data.get("rationale") or "",
                status="required",
                governance_condition_ids=[],
            )
        )
        await self._audit(actor_id, "design_report", row.id, "created", kind=kind.code)
        return row

    async def _container_in_project(self, project_id: uuid.UUID, container_id: Any) -> uuid.UUID | None:
        from app.modules.cde.models import DocumentContainer

        cid = _uuid(container_id)
        if cid is None:
            return None
        c = await self.session.get(DocumentContainer, cid)
        if c is None or c.project_id != project_id:
            raise not_found("container_not_found")
        return cid

    async def patch_report(self, project_id: uuid.UUID, rid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        row = await self._get(DesignReport, project_id, rid, "report_not_found", lock=True)
        for key in ("author_role_id", "checker_role_id"):
            if key in data:
                if data[key]:
                    await self._get(DesignRole, project_id, data[key], "role_not_found")
                setattr(row, key, _uuid(data[key]))
        if "container_id" in data:
            row.container_id = await self._container_in_project(project_id, data["container_id"])
        if "review_cycle_id" in data:
            row.review_cycle_id = await self._cycle_in_project(project_id, data["review_cycle_id"])
        for key in ("title", "phase_code", "external_check", "conditions_text", "required"):
            if key in data:
                setattr(row, key, data[key])
        await self.session.flush()
        return row

    async def _cycle_in_project(self, project_id: uuid.UUID, cycle_id: Any) -> uuid.UUID | None:
        from app.modules.review_authority.models import ReviewCycle

        cid = _uuid(cycle_id)
        if cid is None:
            return None
        cycle = await self.session.get(ReviewCycle, cid)
        if cycle is None or cycle.project_id != project_id:
            raise not_found("review_cycle_not_found")
        return cid

    async def _cycle_state(self, cycle_id: uuid.UUID | None) -> str | None:
        from app.modules.review_authority.models import ReviewCycle

        if cycle_id is None:
            return None
        cycle = await self.session.get(ReviewCycle, cycle_id)
        return cycle.status if cycle else None

    async def _party(self, project_id: uuid.UUID, role_id: uuid.UUID | None) -> str | None:
        if role_id is None:
            return None
        role = await self.session.get(DesignRole, role_id)
        if role is None or role.project_id != project_id:
            return None
        return dr.party_key(contact_id=role.contact_id, originator_code=role.originator_code, party_kind=None) or (
            f"role:{role.id}"
        )

    async def report_transition(
        self, project_id: uuid.UUID, rid: Any, target: str, *, actor_id: uuid.UUID, rationale: str = ""
    ) -> DesignReport:
        row = await self._get(DesignReport, project_id, rid, "report_not_found", lock=True)
        if target == "not_required":
            if dr.rationale_error(rationale):
                raise DesignError("not_required_needs_rationale", 422)
            row.rationale = rationale
        if target == "accepted":
            error = dr.report_acceptance_error(
                independent_check=row.independent_check,
                author_party=await self._party(project_id, row.author_role_id),
                checker_party=await self._party(project_id, row.checker_role_id),
                external=row.external_check,
                cycle_state=await self._cycle_state(row.review_cycle_id),
            )
            if error:
                raise DesignError(error, 422)
        await self._fsm(dfsm.REPORT_FSM, row, target, actor_id, reason=rationale or None)
        await self.session.flush()
        self._publish("report.state_changed", project_id=project_id, report_id=row.id, state=row.status)
        return row

    async def sync_report(self, project_id: uuid.UUID, rid: Any, *, actor_id: uuid.UUID) -> DesignReport:
        """Follow the linked external check cycle (read, never typed)."""
        row = await self._get(DesignReport, project_id, rid, "report_not_found", lock=True)
        state = await self._cycle_state(row.review_cycle_id)
        target = dfsm.CYCLE_TO_REPORT.get(state or "")
        if target and target != row.status:
            path = dfsm.permit_path(dfsm.REPORT_FSM, row.status, target)
            for step in path:
                if step == "accepted":
                    return await self.report_transition(project_id, row.id, "accepted", actor_id=actor_id)
                await self._fsm(dfsm.REPORT_FSM, row, step, actor_id, reason="review cycle")
            await self.session.flush()
        return row

    async def report_hints(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        """Country hints of the pinned catalogue for this project's country (shown, never enforced)."""
        setup = await self.require_setup(project_id)
        catalogue = await self.reports_catalogue(setup)
        project = await self._project(project_id)
        country = (getattr(project, "country_code", None) or "").upper()
        region = (getattr(project, "subdivision_code", None) or "").upper()
        out = []
        for k in catalogue.report_kinds:
            for r in k.country_rules:
                if r.country != country:
                    continue
                if r.region and region and not region.endswith(r.region):
                    continue
                out.append(
                    {
                        "kind_code": k.code,
                        "region": r.region,
                        "text_key": r.text_key,
                        "condition_key": r.condition_key,
                        "source_url": r.source_url,
                        "review_status": str(r.review_status),
                    }
                )
        return out

    # ── permits (rules 19, 20) ────────────────────────────────────────────

    async def create_permit(self, project_id: uuid.UUID, data: dict[str, Any], *, actor_id: uuid.UUID):
        setup = await self.require_setup(project_id)
        catalogue = await self.reports_catalogue(setup)
        if catalogue.profile(data.get("profile_code") or "") is None:
            raise DesignError("permit_profile_unknown", 422)
        code = data.get("code") or await self._next_code(DesignPermit, project_id, "PP")
        await self._unique_code(DesignPermit, project_id, code)
        row = await self._add(
            DesignPermit(
                project_id=project_id,
                code=code,
                title=data.get("title") or code,
                profile_code=data["profile_code"],
                review_cycle_id=await self._cycle_in_project(project_id, data.get("review_cycle_id")),
                authority_submission_id=await self._submission_in_project(
                    project_id, data.get("authority_submission_id")
                ),
                permit_application_id=_uuid(data.get("permit_application_id")),
                target_submission_date=data.get("target_submission_date"),
                schedule_activity_id=_uuid(data.get("schedule_activity_id")),
                status="assembling",
                conditions=[],
            )
        )
        await self._audit(actor_id, "design_permit", row.id, "created", code=code)
        return row

    async def _submission_in_project(self, project_id: uuid.UUID, sid: Any) -> uuid.UUID | None:
        from app.modules.authority_submission.models import Submission

        sub_id = _uuid(sid)
        if sub_id is None:
            return None
        sub = await self.session.get(Submission, sub_id)
        if sub is None or sub.project_id != project_id:
            raise not_found("submission_not_found")
        return sub_id

    async def patch_permit(self, project_id: uuid.UUID, pid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        row = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        if "review_cycle_id" in data:
            row.review_cycle_id = await self._cycle_in_project(project_id, data["review_cycle_id"])
        if "authority_submission_id" in data:
            row.authority_submission_id = await self._submission_in_project(project_id, data["authority_submission_id"])
        for key in ("permit_application_id", "schedule_activity_id"):
            if key in data:
                setattr(row, key, _uuid(data[key]))
        for key in ("title", "target_submission_date"):
            if key in data:
                setattr(row, key, data[key])
        await self.session.flush()
        return row

    async def permit_items(self, project_id: uuid.UUID, permit_id: uuid.UUID) -> list[DesignPermitItem]:
        stmt = select(DesignPermitItem).where(
            DesignPermitItem.project_id == project_id, DesignPermitItem.permit_id == permit_id
        )
        return list((await self.session.execute(stmt.order_by(DesignPermitItem.created_at))).scalars().all())

    async def add_permit_item(self, project_id: uuid.UUID, pid: Any, data: dict[str, Any], *, actor_id: uuid.UUID):
        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        if permit.status not in ("assembling", "ready"):
            raise conflict("permit_locked")
        kind = data.get("kind")
        if kind not in ("drawing", "report", "form"):
            raise DesignError("permit_item_kind_invalid", 422)
        container_id = await self._container_in_project(project_id, data.get("container_id"))
        report_id = None
        if kind == "report":
            report = await self._get(DesignReport, project_id, data.get("report_id"), "report_not_found")
            report_id, container_id = report.id, report.container_id
        row = await self._add(
            DesignPermitItem(
                project_id=project_id,
                permit_id=permit.id,
                kind=kind,
                title=data.get("title") or "",
                container_id=container_id,
                report_id=report_id,
                required=bool(data.get("required", True)),
            )
        )
        if permit.status == "ready":
            await self._fsm(dfsm.PERMIT_FSM, permit, "assembling", actor_id, reason="item added")
        return row

    async def remove_permit_item(self, project_id: uuid.UUID, pid: Any, item_id: Any, *, actor_id: uuid.UUID):
        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        if permit.status not in ("assembling", "ready"):
            raise conflict("permit_locked")
        item = await self._get(DesignPermitItem, project_id, item_id, "permit_item_not_found")
        if item.permit_id != permit.id:
            raise not_found("permit_item_not_found")
        await self.session.delete(item)
        await self.session.flush()

    async def permit_check(self, project_id: uuid.UUID, permit: DesignPermit) -> list[dict[str, Any]]:
        """Rule 19: each item with whether it is present and in a state good enough to submit."""
        from app.modules.cde.models import DocumentContainer

        out = []
        for item in await self.permit_items(project_id, permit.id):
            c = await self.session.get(DocumentContainer, item.container_id) if item.container_id else None
            present = c is not None and c.current_revision_id is not None
            state_ok = present and c.cde_state in ("shared", "published")
            if item.kind == "report" and item.report_id:
                report = await self.session.get(DesignReport, item.report_id)
                state_ok = state_ok and report is not None and report.status in ("submitted", "under_check", "accepted")
            out.append(
                {
                    "item": item,
                    "present": present,
                    "state_ok": state_ok,
                    "current_revision_id": _s(c.current_revision_id) if c else None,
                }
            )
        return out

    async def permit_transition(self, project_id: uuid.UUID, pid: Any, target: str, *, actor_id: uuid.UUID):
        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        if target in ("ready", "submitted"):
            checks = await self.permit_check(project_id, permit)
            missing = dr.permit_missing(
                [
                    dr.PermitItemView(c["item"].id, c["item"].kind, c["item"].required, c["present"], c["state_ok"])
                    for c in checks
                ]
            )
            if not checks:
                raise DesignError("permit_empty", 422)
            if missing:
                raise DesignError(
                    "permit_incomplete",
                    422,
                    violations=[{"code": "permit_item_missing", "item_id": str(m)} for m in missing],
                )
            if target == "submitted":
                if permit.status == "assembling":
                    await self._fsm(dfsm.PERMIT_FSM, permit, "ready", actor_id)
                for c in checks:
                    c["item"].included_revision_id = _uuid(c["current_revision_id"])
                permit.submitted_by, permit.submitted_at = actor_id, _now()
        elif target not in ("assembling", "withdrawn"):
            raise conflict("permit_state_read_from_cycle")
        await self._fsm(dfsm.PERMIT_FSM, permit, target, actor_id)
        await self.session.flush()
        self._publish("permit.state_changed", project_id=project_id, permit_id=permit.id, state=permit.status)
        return permit

    async def sync_permit(self, project_id: uuid.UUID, pid: Any, *, actor_id: uuid.UUID) -> DesignPermit:
        """States from ``submitted`` on are read from the linked review cycle; content drift is flagged."""
        from app.modules.cde.models import DocumentContainer

        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        state = await self._cycle_state(permit.review_cycle_id)
        target = dfsm.CYCLE_TO_PERMIT.get(state or "")
        if target and permit.status not in ("assembling", "ready") and target != permit.status:
            for step in dfsm.permit_path(dfsm.PERMIT_FSM, permit.status, target):
                await self._fsm(dfsm.PERMIT_FSM, permit, step, actor_id, reason="review cycle")
        if permit.submitted_at is not None:
            items = await self.permit_items(project_id, permit.id)
            pinned = {i.container_id: i.included_revision_id for i in items if i.container_id}
            current = {}
            for cid in pinned:
                c = await self.session.get(DocumentContainer, cid)
                current[cid] = c.current_revision_id if c else None
            permit.superseded_content = bool(dr.superseded_items(pinned, current))
        await self.session.flush()
        return permit

    async def propose_conditions(self, project_id: uuid.UUID, pid: Any, texts: list[dict[str, Any]], *, actor_id):
        """Rule 20: conditions recorded on approval start as proposals; nothing is created yet."""
        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        if permit.status not in ("approved", "partially_approved"):
            raise conflict("permit_not_approved")
        added = [
            {
                "id": str(uuid.uuid4()),
                "text": t["text"].strip(),
                "owner_user_id": _s(_uuid(t.get("owner_user_id"))),
                "due_date": t.get("due_date"),
                "state": "proposed",
                "task_id": None,
            }
            for t in texts
            if (t.get("text") or "").strip()
        ]
        permit.conditions = [*(permit.conditions or []), *added]
        await self.session.flush()
        return permit

    async def confirm_condition(
        self, project_id: uuid.UUID, pid: Any, condition_id: str, *, confirm: bool, actor_id: uuid.UUID
    ) -> DesignPermit:
        """Rule 20: a person confirms ONE condition; only then a task with owner and due date is created."""
        from app.modules.tasks.schemas import TaskCreate
        from app.modules.tasks.service import TaskService

        permit = await self._get(DesignPermit, project_id, pid, "permit_not_found", lock=True)
        conditions = [dict(c) for c in permit.conditions or []]
        entry = next((c for c in conditions if c["id"] == condition_id), None)
        if entry is None:
            raise not_found("condition_not_found")
        if entry["state"] != "proposed":
            raise conflict("condition_not_proposed")
        if confirm:
            if not entry.get("owner_user_id") or not entry.get("due_date"):
                raise DesignError("condition_needs_owner_and_due_date", 422)
            task = await TaskService(self.session).create_task(
                TaskCreate(
                    project_id=project_id,
                    task_type="task",
                    title=entry["text"][:500],
                    description=f"{permit.code}: {permit.title}"[:5000],
                    responsible_id=entry["owner_user_id"],
                    due_date=entry["due_date"],
                ),
                user_id=_s(actor_id),
            )
            entry.update(state="confirmed", task_id=str(task.id))
        else:
            entry["state"] = "dismissed"
        permit.conditions = conditions
        await self.session.flush()
        await self._audit(actor_id, "design_permit", permit.id, "condition_" + entry["state"], condition=condition_id)
        return permit

    # ── readiness, frame documents, validation ────────────────────────────

    async def readiness(self, project_id: uuid.UUID, phase_code: str) -> dr.PhaseBlockers:
        """Rule 16: what still blocks a design phase."""
        deliverables = await self.deliverables(project_id)
        reports = await self._list(DesignReport, project_id)
        reviews = {r.id: r for r in await self._list(DesignReview, project_id)}
        majors = [
            reviews[c.review_id].phase_code
            for c in await self._list(DesignReviewComment, project_id)
            if c.severity in ("major", "critical") and c.status in ("open", "answered") and c.review_id in reviews
        ]
        return dr.phase_blockers(
            phase_code,
            deliverables=[(d.code, d.phase_code, d.status, d.required) for d in deliverables],
            reports=[(r.code, r.phase_code, r.status, r.required) for r in reports],
            open_major_comments=majors,
        )

    async def generate_frame_document(
        self, project_id: uuid.UUID, doc_type: str, *, actor_id: uuid.UUID, file_bytes: bytes, file_name: str
    ) -> dict[str, Any]:
        """Rule 23: write the generated register as a new CDE revision of the m07 frame document's container."""
        from app.modules.cde.schemas import ContainerCreate, RevisionCreate
        from app.modules.cde.service import CDEService
        from app.modules.project_governance.models import GovernanceArea, GovernanceDocument

        stmt = (
            select(GovernanceDocument)
            .join(GovernanceArea, GovernanceArea.id == GovernanceDocument.area_id)
            .where(GovernanceDocument.project_id == project_id, GovernanceArea.code.in_(DESIGN_AREA_CODES))
            .with_for_update(of=GovernanceDocument)
        )
        document = (await self.session.execute(stmt)).scalars().first()
        if document is None:
            raise not_found("frame_document_missing")
        if document.status == "binding":
            raise conflict("binding_requires_change_request")
        cde = CDEService(self.session)
        if document.container_id is None:
            container = await cde.create_container(
                ContainerCreate(
                    project_id=project_id,
                    container_code=f"GOV-M07-{uuid.uuid4().hex[:6].upper()}",
                    title=doc_type,
                    metadata={"design_frame_document": doc_type},
                ),
                user_id=_s(actor_id),
            )
            document.container_id = container.id
        import hashlib

        revision = await cde.create_revision(
            document.container_id,
            RevisionCreate(
                file_name=file_name,
                content_hash=hashlib.sha256(file_bytes).hexdigest(),
                file_size=str(len(file_bytes)),
                mime_type="application/pdf",
                change_summary=f"design_management:{doc_type}",
            ),
            user_id=_s(actor_id),
        )
        await self.session.flush()
        return {
            "document_id": str(document.id),
            "container_id": str(document.container_id),
            "revision_id": str(revision.id),
        }

    async def validation_payload(self, project_id: uuid.UUID) -> dict[str, Any]:
        """The one payload the ``design_management`` rule set reads."""
        setup = await self.get_setup(project_id)
        scheme = await self.scheme(setup) if setup else None
        rows = await self.wbs_rows(project_id)
        unresolved = await wbs_refs.unresolved_references(self.session, project_id, rows)
        reports_cat = await self.reports_catalogue(setup) if setup else None
        drawings = []
        for d, c in await self._drawings_with_containers(project_id):
            drawings.append(
                {
                    "id": str(d.id),
                    "number": c.container_code,
                    "parts": self._stored_parts(c),
                    "legacy_scheme": d.legacy_scheme,
                    "title_block_number": d.title_block_number,
                    "originator": c.originator_code,
                }
            )
        releases = []
        for rel in await self._list(DesignRelease, project_id):
            if rel.status in ("ready", "issued"):
                views = await self._revision_views(project_id, rel.revision_ids or [])
                releases.append(
                    {
                        "code": rel.code,
                        "purpose": rel.purpose,
                        "revisions": [{"id": str(v.revision_id), "suitability": v.suitability_code} for v in views],
                    }
                )
        deliverables = await self.deliverables(project_id)
        reports = []
        for r in await self._list(DesignReport, project_id):
            reports.append(
                {
                    "code": r.code,
                    "status": r.status,
                    "independent_check": r.independent_check,
                    "author_party": await self._party(project_id, r.author_role_id),
                    "checker_party": await self._party(project_id, r.checker_role_id),
                    "external": r.external_check,
                    "cycle_state": await self._cycle_state(r.review_cycle_id),
                    "rationale": r.rationale,
                    "hint_overridden": r.hint_overridden,
                }
            )
        permits = []
        for p in await self._list(DesignPermit, project_id):
            checks = await self.permit_check(project_id, p)
            permits.append(
                {
                    "code": p.code,
                    "status": p.status,
                    "superseded_content": p.superseded_content,
                    "missing": len(
                        dr.permit_missing(
                            [
                                dr.PermitItemView(
                                    c["item"].id, c["item"].kind, c["item"].required, c["present"], c["state_ok"]
                                )
                                for c in checks
                            ]
                        )
                    ),
                }
            )
        points = [
            {"code": a.code, "status": a.status, "decided_by": _s(a.decided_by), "submitted_by": _s(a.submitted_by)}
            for a in await self._list(DesignApprovalPoint, project_id)
        ]
        return {
            "scheme": scheme.model_dump(mode="json") if scheme else None,
            "wbs": [{"id": str(r.id), "code": r.code} for r in rows],
            "unresolved": [
                {"module": u.module, "table": u.table, "row_id": u.row_id, "value": u.value} for u in unresolved
            ],
            "drawings": drawings,
            "originators": sorted(await self._active_originators(project_id) or []),
            "releases": releases,
            "deliverables": [
                {
                    "code": d.code,
                    "phase_code": d.phase_code,
                    "status": d.status,
                    "required": d.required,
                    "planned": d.planned_count,
                }
                for d in deliverables
            ],
            "reports": reports,
            "reports_catalogue": reports_cat.model_dump(mode="json") if reports_cat else None,
            "permits": permits,
            "approval_points": points,
            "four_eyes": bool(setup.four_eyes_release) if setup else True,
        }
