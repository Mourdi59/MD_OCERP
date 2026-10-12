# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Shared builders for the procurement concept PostgreSQL tests.

A world is a throwaway database with real users (a manager, an editor who owns
the procurement area, an editor who does not, an outsider), an EUR project with
team membership, module 3's package plan (built from its table contract when
module 3 itself is not installed in this tree), and a concept for a public
sub-central client under the shipped EU catalogue.

Governance is laid down as rows: one gate that releases procurement, and on
request the area and the frame document that host the concept. Their codes are
deliberately not the ones any shipped model uses. The module finds them through
catalogue tags, so the tests hand it the resolved tags (``patch_hosting``)
instead of a catalogue that happens to use familiar codes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.procurement_concept import plan_source as plan
from app.modules.procurement_concept import service as service_module
from app.modules.procurement_concept.events import handle_frame_document
from app.modules.procurement_concept.hosting import ProcurementHosting
from app.modules.procurement_concept.service import ProcurementConceptService
from tests.pg.governance_fixtures import add_project, add_user

TODAY = date(2026, 10, 11)
AREA = "zz_buying"
DOC_TYPE = "buying_plan"
RELEASE_GATE = "g_release"
OTHER_GATE = "g_other"
HOSTING = ProcurementHosting(AREA, (DOC_TYPE,), (RELEASE_GATE,))


def patch_hosting(monkeypatch: pytest.MonkeyPatch, hosting: ProcurementHosting = HOSTING) -> None:
    """What the pinned governance catalogue's tags resolve to, for every project of the test."""

    async def _hosting(_session: Any, _project_id: uuid.UUID) -> ProcurementHosting:
        return hosting

    monkeypatch.setattr(service_module, "project_hosting", _hosting)


@dataclass
class World:
    factory: async_sessionmaker[AsyncSession]
    project_id: uuid.UUID
    manager: uuid.UUID
    area_owner: uuid.UUID
    editor: uuid.UUID
    outsider: uuid.UUID
    packages: dict[str, uuid.UUID] = field(default_factory=dict)
    gates: dict[str, uuid.UUID] = field(default_factory=dict)
    area_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


async def ensure_plan_tables(factory: async_sessionmaker[AsyncSession]) -> None:
    """Module 3's two tables, created from the table contract only where module 3 did not create them."""
    async with factory() as s:
        conn = await s.connection()
        await conn.run_sync(lambda c: plan.stand_in_metadata().create_all(c, checkfirst=True))
        await s.commit()


async def add_contract_package(
    w: World, code: str, kind: str, *, parent: str | None = None, need_date: str | None = None
) -> uuid.UUID:
    pid = uuid.uuid4()
    async with w.factory() as s:
        await s.execute(
            sa.insert(plan.PACKAGE_TABLE).values(
                id=pid,
                project_id=w.project_id,
                code=code,
                title=f"{code} package",
                kind=kind,
                parent_id=w.packages.get(parent) if parent else None,
                scope=f"Scope of {code}",
                wbs_ref="",
                boq_ref="",
                need_date=need_date,
                status="planned",
                sort_order=len(w.packages),
            )
        )
        await s.commit()
    w.packages[code] = pid
    return pid


async def set_delivery_form(w: World, form: str, *, public_client: bool = True) -> None:
    async with w.factory() as s:
        await s.execute(
            sa.insert(plan.MODEL_TABLE).values(
                id=uuid.uuid4(),
                project_id=w.project_id,
                selected_form_code=form,
                status="approved",
                owner_capability={"public_client": public_client},
            )
        )
        await s.commit()


async def add_gate(w: World, code: str, sort_order: int) -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceGate

    async with w.factory() as s:
        g = GovernanceGate(
            project_id=w.project_id,
            catalogue_id="test",
            code=code,
            from_phase=f"before_{code}",
            to_phase=f"after_{code}",
            sort_order=sort_order,
        )
        s.add(g)
        await s.commit()
        w.gates[code] = g.id
        return g.id


async def add_procurement_area(w: World, owner: uuid.UUID | None, code: str = AREA) -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceArea

    async with w.factory() as s:
        area = GovernanceArea(project_id=w.project_id, code=code, sort_order=8, owner_user_id=owner)
        s.add(area)
        await s.commit()
        if code == AREA:
            w.area_id = area.id
        return area.id


async def add_frame_document(w: World, *, status: str = "draft", doc_type: str = DOC_TYPE) -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceDocument

    if w.area_id is None:
        await add_procurement_area(w, w.area_owner)
    async with w.factory() as s:
        doc = GovernanceDocument(project_id=w.project_id, area_id=w.area_id, doc_type=doc_type, status=status)
        s.add(doc)
        await s.commit()
        if doc_type == DOC_TYPE:
            w.document_id = doc.id
        return doc.id


async def add_decision(w: World, gate_code: str, *, outcome: str = "go", by: uuid.UUID | None = None) -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceDecision

    async with w.factory() as s:
        d = GovernanceDecision(
            project_id=w.project_id,
            gate_id=w.gates[gate_code],
            gate_code=gate_code,
            attempt_no=1,
            outcome=outcome,
            decided_by=by or w.manager,
            decided_at=datetime.now(UTC),
        )
        s.add(d)
        await s.commit()
        return d.id


async def add_condition(w: World, gate_code: str, *, status: str = "open") -> uuid.UUID:
    from app.modules.project_governance.models import GovernanceCondition

    decision_id = await add_decision(w, gate_code, outcome="go_with_conditions")
    async with w.factory() as s:
        c = GovernanceCondition(
            project_id=w.project_id,
            decision_id=decision_id,
            gate_id=w.gates[gate_code],
            gate_code=gate_code,
            text="Fabrication slot reserved in writing",
            status=status,
        )
        s.add(c)
        await s.commit()
        return c.id


async def set_condition(w: World, condition_id: uuid.UUID, status: str) -> None:
    from app.modules.project_governance.models import GovernanceCondition

    async with w.factory() as s:
        (await s.get(GovernanceCondition, condition_id)).status = status
        await s.commit()


async def bind_frame_document(w: World, *, by: uuid.UUID | None = None, notify: bool = True) -> bool:
    """What a go at the release gate does in governance: the frame document becomes binding.

    Returns what the module's subscriber answered for the resulting event.
    """
    from app.modules.project_governance.models import GovernanceDocument

    if w.document_id is None:
        await add_frame_document(w, status="submitted")
    await add_decision(w, RELEASE_GATE, by=by or w.manager)
    async with w.factory() as s:
        doc = await s.get(GovernanceDocument, w.document_id)
        doc.status = "binding"
        doc.approved_gate_id = w.gates[RELEASE_GATE]
        await s.commit()
    if not notify:
        return False
    return await handle_frame_document(
        {"project_id": str(w.project_id), "document_id": str(w.document_id), "status": "binding"},
        session_factory=w.factory,
    )


async def approve(w: World, *, submitter: uuid.UUID | None = None, by: uuid.UUID | None = None) -> None:
    """Submit the concept and let governance approve it (there is no other way to an approved concept)."""
    await svc_call(w, "transition", w.project_id, "in_review", actor_id=submitter or w.manager, can_manage=True)
    assert await bind_frame_document(w, by=by) is True


async def build_world(factory: async_sessionmaker[AsyncSession], *, concept: bool = True) -> World:
    from app.modules.procurement_concept.catalogue import register_kind

    register_kind()
    await ensure_plan_tables(factory)
    async with factory() as s:
        manager = await add_user(s, "manager")
        area_owner = await add_user(s, "editor")
        editor = await add_user(s, "editor")
        outsider = await add_user(s, "manager")
        pid = await add_project(s, manager, [area_owner, editor])
        await s.commit()
    w = World(factory, pid, manager, area_owner, editor, outsider)
    await add_gate(w, OTHER_GATE, 1)
    await add_gate(w, RELEASE_GATE, 2)
    if concept:
        async with factory() as s:
            await ProcurementConceptService(s).set_concept(
                pid,
                {
                    "catalogue_source": "shipped",
                    "catalogue_id": "eu",
                    "jurisdiction": "eu",
                    "client_type": "sub_central",
                    "public_client": True,
                },
                actor_id=manager,
                can_manage=True,
                tenant_id=str(manager),
            )
            await s.commit()
    return w


async def put(
    w: World, code: str, data: dict[str, Any], *, actor: uuid.UUID | None = None, can_manage: bool = True
) -> Any:
    async with w.factory() as s:
        row = await ProcurementConceptService(s).put_package(
            w.project_id,
            w.packages[code],
            data,
            actor_id=actor or w.manager,
            can_manage=can_manage,
            tenant_id=str(w.manager),
        )
        await s.commit()
        return row


async def svc_call(w: World, fn: str, *args: Any, **kw: Any) -> Any:
    async with w.factory() as s:
        out = await getattr(ProcurementConceptService(s), fn)(*args, **kw)
        await s.commit()
        return out


async def execute(w: World, code: str, **kw: Any) -> dict[str, Any]:
    return await svc_call(
        w,
        "create_execution",
        w.project_id,
        w.packages[code],
        vehicle=kw.pop("vehicle", None),
        submission_deadline=None,
        actor_id=kw.pop("actor", w.manager),
        can_manage=kw.pop("can_manage", True),
    )
