# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Module 3's package plan, read (and its execution link written) through its table contract only.

``delivery_model`` owns ``ContractPackage`` (``oe_delivery_model_package``)
and the project's chosen form (``oe_delivery_model_model``). This module does
not import that code: the columns below are the interface module 3's SPEC
defines (section 3, Decision 5: a typed soft link ``(link_kind, link_id)``).
The tables are declared in a private ``MetaData`` so ``create_all`` of the
platform never creates or alters them from here.

When module 3 is not installed the tables do not exist: every read answers
empty and a write refuses with ``package_plan_unavailable``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import GUID

_meta = sa.MetaData()

PACKAGE_TABLE = sa.Table(
    "oe_delivery_model_package",
    _meta,
    sa.Column("id", GUID(), primary_key=True),
    sa.Column("project_id", GUID(), nullable=False),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("title", sa.String(500), nullable=False, default=""),
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("parent_id", GUID(), nullable=True),
    sa.Column("scope", sa.Text(), nullable=False, default=""),
    sa.Column("wbs_ref", sa.String(120), nullable=False, default=""),
    sa.Column("boq_ref", sa.String(120), nullable=False, default=""),
    sa.Column("need_date", sa.String(40), nullable=True),
    sa.Column("status", sa.String(20), nullable=False, default="planned"),
    sa.Column("link_kind", sa.String(30), nullable=True),
    sa.Column("link_id", GUID(), nullable=True),
    sa.Column("sort_order", sa.Integer(), nullable=False, default=0),
)

MODEL_TABLE = sa.Table(
    "oe_delivery_model_model",
    _meta,
    sa.Column("id", GUID(), primary_key=True),
    sa.Column("project_id", GUID(), nullable=False),
    sa.Column("selected_form_code", sa.String(64), nullable=True),
    sa.Column("status", sa.String(20), nullable=False, default="draft"),
    sa.Column("owner_capability", sa.JSON(), nullable=False, default=dict),
)

# Execution vehicles this module creates (rule 15) and the link kinds mod3 knows.
LINK_BID_PACKAGE = "bid_package"
LINK_RFQ = "rfq"
LINK_TENDER_PACKAGE = "tender_package"


@dataclass(frozen=True)
class PlanPackage:
    id: uuid.UUID
    project_id: uuid.UUID
    code: str
    title: str
    kind: str
    parent_id: uuid.UUID | None
    scope: str
    boq_ref: str
    need_date: str | None
    status: str
    link_kind: str | None
    link_id: uuid.UUID | None
    sort_order: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "code": self.code,
            "title": self.title,
            "kind": self.kind,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "scope": self.scope,
            "boq_ref": self.boq_ref,
            "need_date": self.need_date,
            "status": self.status,
            "execution_link": {"kind": self.link_kind, "id": str(self.link_id)} if self.link_id else None,
        }


class PlanUnavailableError(RuntimeError):
    """Module 3's tables are not there."""


async def _guarded(session: AsyncSession, stmt: Any) -> Any:
    """Run a read in a savepoint; a missing table answers ``None`` without poisoning the transaction."""
    try:
        async with session.begin_nested():
            return await session.execute(stmt)
    except (ProgrammingError, DBAPIError) as exc:
        if "does not exist" in str(exc) or "no such table" in str(exc):
            return None
        raise


def _row(r: Any) -> PlanPackage:
    return PlanPackage(
        id=r.id,
        project_id=r.project_id,
        code=r.code,
        title=r.title or "",
        kind=r.kind,
        parent_id=r.parent_id,
        scope=r.scope or "",
        boq_ref=r.boq_ref or "",
        need_date=r.need_date,
        status=r.status,
        link_kind=r.link_kind,
        link_id=r.link_id,
        sort_order=r.sort_order or 0,
    )


async def list_packages(session: AsyncSession, project_id: uuid.UUID) -> list[PlanPackage]:
    """The project's ContractPackages in plan order (empty without module 3)."""
    t = PACKAGE_TABLE
    res = await _guarded(session, sa.select(t).where(t.c.project_id == project_id).order_by(t.c.sort_order, t.c.code))
    return [] if res is None else [_row(r) for r in res]


async def get_package(session: AsyncSession, project_id: uuid.UUID, package_id: uuid.UUID) -> PlanPackage | None:
    """One ContractPackage of this project; another project's id answers ``None``."""
    t = PACKAGE_TABLE
    res = await _guarded(session, sa.select(t).where(t.c.id == package_id, t.c.project_id == project_id))
    row = None if res is None else res.first()
    return None if row is None else _row(row)


async def existing_package_ids(session: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID] | None:
    """Which of ``ids`` are still ContractPackages; ``None`` when module 3's table is not there."""
    if not ids:
        return set()
    t = PACKAGE_TABLE
    res = await _guarded(session, sa.select(t.c.id).where(t.c.id.in_(ids)))
    return None if res is None else {r.id for r in res}


async def find_by_link(session: AsyncSession, link_kind: str, link_id: uuid.UUID) -> PlanPackage | None:
    t = PACKAGE_TABLE
    res = await _guarded(session, sa.select(t).where(t.c.link_kind == link_kind, t.c.link_id == link_id))
    row = None if res is None else res.first()
    return None if row is None else _row(row)


async def delivery_form(session: AsyncSession, project_id: uuid.UUID) -> tuple[str | None, bool | None]:
    """``(selected_form_code, public_client)`` from module 3's model, ``(None, None)`` without one."""
    t = MODEL_TABLE
    res = await _guarded(
        session, sa.select(t.c.selected_form_code, t.c.owner_capability).where(t.c.project_id == project_id)
    )
    row = None if res is None else res.first()
    if row is None:
        return None, None
    cap = row.owner_capability if isinstance(row.owner_capability, dict) else {}
    pc = cap.get("public_client")
    return row.selected_form_code, (bool(pc) if pc is not None else None)


async def set_link_once(
    session: AsyncSession, project_id: uuid.UUID, package_id: uuid.UUID, link_kind: str, link_id: uuid.UUID
) -> bool:
    """Compare-and-set the execution link: writes only while the package has none. ``False`` = already linked.

    The ``link_id IS NULL`` predicate is what makes two concurrent creations
    end with one link (rule 15): the second UPDATE matches no row.
    """
    t = PACKAGE_TABLE
    try:
        res = await session.execute(
            sa.update(t)
            .where(t.c.id == package_id, t.c.project_id == project_id, t.c.link_id.is_(None))
            .values(link_kind=link_kind, link_id=link_id)
        )
    except (ProgrammingError, DBAPIError) as exc:
        if "does not exist" in str(exc) or "no such table" in str(exc):
            raise PlanUnavailableError from exc
        raise
    return (res.rowcount or 0) == 1


def stand_in_metadata() -> sa.MetaData:
    """The private metadata (tests build module 3's tables from it when module 3 is absent)."""
    return _meta
