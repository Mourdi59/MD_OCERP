# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Records of other modules a quality record points to: what may be picked, and what an id is called.

Three reads, all inside one project:

* :func:`options` lists what a reference field may hold. The same rule decides
  what a write accepts, so a dialog never offers a value the save refuses and a
  save never takes a value no dialog could offer.
* :func:`labels` turns the ids that findings and unmet preconditions carry
  into the names people use, one query per kind.
* :func:`hold_gates` and :func:`handover_packages` give the screens the record
  to open in construction control.

A kind whose owning module is not installed answers ``available: False`` with a
reason. It never answers an empty list, which would read as "nothing to pick".
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import or_, select

from app.modules.quality_concept import links

OPTION_KINDS: tuple[str, ...] = (
    "contact",
    "plant_item",
    "cx_system",
    "schedule_activity",
    "handover_package",
    "certificate_document",
    "retest_of",
)
# Option kinds answered by the evidence candidate lister, which is already project-scoped.
_CANDIDATE_KIND = {
    "cx_system": "cx_system",
    "handover_package": "cc_handover_package",
    "certificate_document": "cde_document",
}


def as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def _contact_name(c: Any) -> str:
    person = " ".join(x for x in (c.first_name, c.last_name) if x)
    return " / ".join(x for x in (c.company_name, person) if x) or (c.primary_email or str(c.id))


async def _is_admin(session: Any, user_id: str) -> bool:
    from app.modules.users.models import User

    uid = as_uuid(user_id)
    user = await session.get(User, uid) if uid else None
    return user is not None and user.role == "admin"


async def contact_scope(session: Any, caller_id: str | None) -> Any | None:
    """The clause that limits contacts to what ``caller_id`` sees in the contacts list.

    ``None`` means no limit: an administrator, or a call that carries no caller
    (the demo seed, an event mirror).
    """
    from app.modules.contacts.models import Contact

    if caller_id is None or await _is_admin(session, caller_id):
        return None
    return or_(Contact.tenant_id == str(caller_id), Contact.created_by == str(caller_id))


async def contact_visible(session: Any, caller_id: str | None, contact_id: uuid.UUID) -> bool:
    from app.modules.contacts.models import Contact

    stmt = select(Contact.id).where(Contact.id == contact_id)
    scope = await contact_scope(session, caller_id)
    if scope is not None:
        stmt = stmt.where(scope)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def _answer(items: list[dict[str, Any]], q: str, limit: int) -> dict[str, Any]:
    needle = q.strip().casefold()
    if needle:
        items = [i for i in items if needle in i["label"].casefold()]
    return {"items": items[:limit], "total": len(items), "available": True, "reason": None}


def _unavailable(reason: str) -> dict[str, Any]:
    return {"items": [], "total": 0, "available": False, "reason": reason}


async def options(
    session: Any,
    project_id: uuid.UUID,
    kind: str,
    *,
    caller_id: str | None,
    q: str = "",
    limit: int = 50,
    owner_kind: str | None = None,
    owner_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """``{items: [{id, label}], total, available, reason}`` for one reference field."""
    from app.modules.contacts.models import Contact
    from app.modules.quality_concept.models import EvidenceLink
    from app.modules.schedule.models import Activity, Schedule

    limit = max(1, min(limit, 200))
    if kind in _CANDIDATE_KIND:
        rows = await links.candidates(session, project_id, _CANDIDATE_KIND[kind], q, 200)
        return _answer([{"id": r["id"], "label": r["label"]} for r in rows], "", limit)
    if kind == "contact":
        stmt = select(Contact).where(Contact.is_active.is_(True)).limit(2000)
        scope = await contact_scope(session, caller_id)
        if scope is not None:
            stmt = stmt.where(scope)
        rows = [{"id": str(c.id), "label": _contact_name(c)} for c in (await session.execute(stmt)).scalars()]
        return _answer(sorted(rows, key=lambda r: r["label"].casefold()), q, limit)
    if kind == "schedule_activity":
        stmt = (
            select(Activity.id, Activity.wbs_code, Activity.name)
            .join(Schedule, Schedule.id == Activity.schedule_id)
            .where(Schedule.project_id == project_id)
            .order_by(Activity.wbs_code, Activity.name)
            .limit(5000)
        )
        rows = [{"id": str(i), "label": " ".join(x for x in (w, n) if x)} for i, w, n in await session.execute(stmt)]
        return _answer(rows, q, limit)
    if kind == "plant_item":
        # The plant register answers facts about one item; it offers no listing to pick from.
        return _unavailable("plant_listing_unavailable")
    if kind == "retest_of":
        if owner_kind is None or owner_id is None:
            return _unavailable("owner_required")
        stmt = (
            select(EvidenceLink)
            .where(EvidenceLink.project_id == project_id)
            .where(EvidenceLink.owner_kind == owner_kind)
            .where(EvidenceLink.owner_id == owner_id)
            .order_by(EvidenceLink.created_at)
        )
        rows = []
        for link in (await session.execute(stmt)).scalars():
            fact = await links.resolve(session, project_id, link.link_kind, link.link_id)
            names = await labels(session, project_id, [link.link_id])
            outcome = f" ({fact.outcome})" if fact is not None and fact.outcome else ""
            rows.append({"id": str(link.id), "label": f"{names.get(link.link_id, link.link_kind)}{outcome}"})
        return _answer(rows, q, limit)
    return _unavailable("unknown_option_kind")


async def retest_target_ok(
    session: Any, project_id: uuid.UUID, owner_kind: str, owner_id: uuid.UUID, retest_of: str
) -> bool:
    """A retest replaces an earlier link of the same record; nothing else can be named."""
    from app.modules.quality_concept.models import EvidenceLink

    lid = as_uuid(retest_of)
    if lid is None:
        return False
    stmt = (
        select(EvidenceLink.id)
        .where(EvidenceLink.id == lid)
        .where(EvidenceLink.project_id == project_id)
        .where(EvidenceLink.owner_kind == owner_kind)
        .where(EvidenceLink.owner_id == owner_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def labels(session: Any, project_id: uuid.UUID, refs: Iterable[Any]) -> dict[str, str]:
    """``{id: name}`` for every ref that is the id of a record this project can name."""
    from app.modules.cde.models import DocumentContainer
    from app.modules.commissioning.models import CxSystem
    from app.modules.construction_control.models import HandoverPackage, HoldGate
    from app.modules.contacts.models import Contact
    from app.modules.ncr.models import NCR
    from app.modules.quality_concept.models import (
        AcceptanceUnit,
        CertificationTarget,
        ExpertReportPlan,
        PreservationSurvey,
        ProofRequirement,
    )
    from app.modules.requirements.models import Requirement, RequirementDeliverable, RequirementSet

    ids = {u for r in refs if (u := as_uuid(r)) is not None}
    if not ids:
        return {}
    out: dict[str, str] = {}

    def _join(*parts: Any) -> str:
        return " ".join(str(p) for p in parts if p)

    scoped: tuple[tuple[Any, tuple[str, ...]], ...] = (
        (ProofRequirement, ("title",)),
        (AcceptanceUnit, ("code", "title")),
        (PreservationSurvey, ("subject_ref", "address")),
        (CertificationTarget, ("scheme_code", "target_level")),
        (ExpertReportPlan, ("subject",)),
        (CxSystem, ("name",)),
        (NCR, ("ncr_number", "title")),
        (HoldGate, ("gate_number", "title")),
        (HandoverPackage, ("package_number", "title")),
        (DocumentContainer, ("container_code", "title")),
    )
    for model, attrs in scoped:
        left = ids - {uuid.UUID(k) for k in out}
        if not left:
            return out
        stmt = select(model).where(model.project_id == project_id).where(model.id.in_(left))
        for row in (await session.execute(stmt)).scalars():
            name = _join(*(getattr(row, a, None) for a in attrs))
            # A proof without a title of its own is known by its evidence type.
            out[str(row.id)] = name or getattr(row, "evidence_type", None) or str(row.id)
    left = ids - {uuid.UUID(k) for k in out}
    if left:
        stmt = (
            select(RequirementDeliverable.id, RequirementDeliverable.deliverable_type, Requirement.entity)
            .join(Requirement, Requirement.id == RequirementDeliverable.requirement_id)
            .join(RequirementSet, RequirementSet.id == Requirement.requirement_set_id)
            .where(RequirementSet.project_id == project_id)
            .where(RequirementDeliverable.id.in_(left))
        )
        for did, kind, entity in await session.execute(stmt):
            out[str(did)] = _join(entity, kind)
    left = ids - {uuid.UUID(k) for k in out}
    if left:
        # A contact is not a project record; only ids the project already stores reach this point.
        for c in (await session.execute(select(Contact).where(Contact.id.in_(left)))).scalars():
            out[str(c.id)] = _contact_name(c)
    return out


async def hold_gates(session: Any, project_id: uuid.UUID, gate_ids: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """The hold gates behind stage rows, keyed by id: what to open in construction control."""
    from app.modules.construction_control.models import HoldGate

    ids = {u for g in gate_ids if (u := as_uuid(g)) is not None}
    if not ids:
        return {}
    stmt = select(HoldGate).where(HoldGate.project_id == project_id).where(HoldGate.id.in_(ids))
    return {
        str(g.id): {
            "kind": "cc_hold_gate",
            "id": str(g.id),
            "label": " ".join(x for x in (g.gate_number, g.title) if x),
            "gate_number": g.gate_number,
            "status": g.status,
            "required_party_role": g.required_party_role,
        }
        for g in (await session.execute(stmt)).scalars()
    }


async def handover_packages(session: Any, project_id: uuid.UUID, ids_: Iterable[Any]) -> dict[str, dict[str, Any]]:
    """The handover acts behind acceptance units, keyed by id."""
    from app.modules.construction_control.models import HandoverPackage

    ids = {u for g in ids_ if (u := as_uuid(g)) is not None}
    if not ids:
        return {}
    stmt = select(HandoverPackage).where(HandoverPackage.project_id == project_id).where(HandoverPackage.id.in_(ids))
    return {
        str(p.id): {
            "kind": "cc_handover_package",
            "id": str(p.id),
            "label": " ".join(x for x in (p.package_number, p.title) if x),
            "status": p.status,
        }
        for p in (await session.execute(stmt)).scalars()
    }
