# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What the cost frame is compared with, read from the module that owns it. Nothing is stored here.

The estimate is the project's bill, read the way the bill editor reads it (every leaf converted to
the project's base currency by the bill's own helper, the markup lines from the editor's own query
and the bill's one markup engine). The commitments are what the cost spine counts under its one
rule, ``CostSpineRepository.committed_by_cost_line`` (purchase orders and subcontract contract
lines, an award counted once), attributed to a classification code through the control account of
the cost line they sit on.

Neither reading is clamped or converted a second time. A reading that cannot be had says so
(``available`` false with a reason) and is never replaced by zero.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.economics.calc import ZERO, Reading
from app.modules.economics.errors import EconomicsError


@dataclass
class MarkupLine:
    name: str
    category: str
    amount: Decimal


@dataclass
class BillReading:
    """The estimate: leaf amounts under their classification code, and the markups above them."""

    boq_id: uuid.UUID
    boq_name: str
    currency: str
    leaves: list[Reading] = field(default_factory=list)
    direct_cost: Decimal = ZERO
    markups: list[MarkupLine] = field(default_factory=list)
    bill_count: int = 1

    @property
    def markups_total(self) -> Decimal:
        return sum((m.amount for m in self.markups), ZERO)

    @property
    def grand_total(self) -> Decimal:
        return self.direct_cost + self.markups_total


@dataclass
class CommitmentReading:
    available: bool
    reason: str = ""
    readings: list[Reading] = field(default_factory=list)
    total: Decimal = ZERO


def _own_code(position: Any, standard: str) -> str | None:
    classification = position.classification if isinstance(position.classification, dict) else {}
    value = classification.get(standard)
    text = "" if value is None else str(value).strip()
    return text or None


def _inherited(positions: list[Any], standard: str) -> dict[uuid.UUID, str]:
    """For each position, the nearest ancestor's code of ``standard``; a corrupt cycle ends the walk."""
    by_id = {p.id: p for p in positions}
    out: dict[uuid.UUID, str] = {}
    for position in positions:
        seen = {position.id}
        current = position.parent_id
        while current is not None and current not in seen:
            seen.add(current)
            parent = by_id.get(current)
            if parent is None:
                break
            code = _own_code(parent, standard)
            if code is not None:
                out[position.id] = code
                break
            current = parent.parent_id
    return out


async def pick_bill(session: AsyncSession, project_id: uuid.UUID, boq_id: uuid.UUID | None) -> tuple[Any | None, int]:
    """``(bill, bill count)``: the chosen bill of the project, else its most recently changed one."""
    from app.modules.boq.models import BOQ

    bills = list(
        (await session.execute(select(BOQ).where(BOQ.project_id == project_id).order_by(BOQ.updated_at.desc())))
        .scalars()
        .all()
    )
    if boq_id is not None:
        chosen = next((b for b in bills if b.id == boq_id), None)
        return chosen, len(bills)
    return (bills[0] if bills else None), len(bills)


async def read_bill(
    session: AsyncSession, project_id: uuid.UUID, standard: str, boq_id: uuid.UUID | None
) -> BillReading | None:
    """The estimate of the chosen bill, or ``None`` when the project has no bill."""
    from app.modules.boq.service import (
        BOQService,
        _calculate_markup_amounts_scoped,
        _is_section,
        _leaf_total_base_with_resources,
        is_empty_position,
    )

    bill, count = await pick_bill(session, project_id, boq_id)
    if bill is None:
        return None
    service = BOQService(session)
    positions = await service.position_repo.list_all_for_boq(bill.id)
    base_currency, fx_map = await service._resolve_project_fx(bill.id)  # noqa: SLF001 - the bill's own FX read

    def leaf_amount(position: Any) -> Decimal:
        return _leaf_total_base_with_resources(position, fx_map, base_currency or "")

    inherited = _inherited(positions, standard)
    reading = BillReading(boq_id=bill.id, boq_name=bill.name, currency=(base_currency or "").upper(), bill_count=count)
    for position in positions:
        if _is_section(position):
            continue
        amount = leaf_amount(position)
        if amount == 0 and is_empty_position(position):
            continue
        reading.direct_cost += amount
        reading.leaves.append(Reading(_own_code(position, standard) or inherited.get(position.id), amount))
    markups = await service.markup_repo.list_for_boq(bill.id)
    try:
        escalation = await service._resolve_escalation_factors(markups)  # noqa: SLF001 - strict, as the editor
    except HTTPException as exc:
        raise EconomicsError("bill_escalation_unresolved", 409, detail=str(exc.detail)) from exc
    calculated = _calculate_markup_amounts_scoped(
        reading.direct_cost, markups, positions, leaf_amount, escalation.factors
    )
    reading.markups = [MarkupLine(m.name, m.category or "other", amount) for m, amount in calculated if m.is_active]
    return reading


async def read_commitments(session: AsyncSession, project_id: uuid.UUID) -> CommitmentReading:
    """What the project is bound to pay, by classification code, under the cost spine's counting rule.

    ``available`` is false when the project has no cost lines at all: the commitments then have no
    code to sit under and the honest answer is "not known", not zero.
    """
    from app.modules.costmodel.models import ControlAccount, CostLine
    from app.modules.costmodel.repository import CostSpineRepository

    lines = (
        await session.execute(
            select(CostLine.id, ControlAccount.code)
            .outerjoin(ControlAccount, ControlAccount.id == CostLine.control_account_id)
            .where(CostLine.project_id == project_id)
        )
    ).all()
    if not lines:
        return CommitmentReading(available=False, reason="no_cost_lines")
    code_of = {str(line_id): (code or None) for line_id, code in lines}
    committed = await CostSpineRepository(session).committed_by_cost_line(project_id)
    out = CommitmentReading(available=True)
    for line_id, amount in committed.items():
        out.readings.append(Reading(code_of.get(str(line_id)), amount))
        out.total += amount
    return out
