# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Contingency drawdown items (SPEC rule 17).

An item of type ``contingency_drawdown`` draws on a finance contingency line.
Its released amount IS the drawdown: on each approved release the module
writes one record through finance's own writer
(``FinanceService.set_contingency_drawdown``), in the record format the risk
contingency card reads (``risk/contingency.py`` ``parse_drawdown_record``),
under the source ``commitment:<item id>``. One source holds one record, so a
second tranche replaces the record with the new cumulative amount instead of
adding to it, and the risk card counts the money once.

The line is the item's planned source when that is a contingency budget line,
otherwise the project's only (or only base-currency) contingency line; anything
else is ambiguous and refused. A request whose cumulative amount exceeds what
the line still holds (allocated minus every other drawdown) is refused with
``contingency_insufficient``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.modules.commitment_release.errors import CommitmentError

ITEM_TYPE = "contingency_drawdown"
# The coded reasons a drawdown cannot be covered; at approval each closes the request as rejected.
REFUSALS = ("contingency_insufficient", "contingency_line_required", "fx_rate_missing")


def source_of(item_id: uuid.UUID) -> str:
    return f"commitment:{item_id}"


@dataclass(frozen=True)
class LineBalance:
    budget_id: uuid.UUID
    currency: str
    allocated: Decimal
    drawn_by_others: Decimal

    @property
    def available(self) -> Decimal:
        return self.allocated - self.drawn_by_others


async def line_for(session: Any, project: Any, item: Any) -> LineBalance:
    """The contingency line this item draws on, with what the other drawdowns already took from it."""
    from app.modules.finance.service import FinanceService
    from app.modules.risk.contingency import ContingencyLine, allocated_amount, default_line, norm_code
    from app.modules.risk.service import _line_drawdowns

    base = norm_code(getattr(project, "currency", "") or "")
    budgets = await FinanceService(session).list_contingency_lines(project.id, for_update=True)
    if not budgets:
        raise CommitmentError("contingency_line_required", 422)
    chosen = None
    if item.planned_source == "budget_line" and item.planned_source_id is not None:
        chosen = next((b for b in budgets if b.id == item.planned_source_id), None)
    if chosen is None:
        lines = [
            ContingencyLine(
                budget_id=str(b.id),
                wbs_id=b.wbs_id,
                currency=norm_code(b.currency_code),
                allocated=Decimal("0"),
                drawdowns=(),
            )
            for b in budgets
        ]
        picked = default_line(lines, base)
        if picked is None:
            raise CommitmentError("contingency_line_required", 422)
        chosen = next(b for b in budgets if str(b.id) == picked.budget_id)
    currency = norm_code(chosen.currency_code) or base
    own = source_of(item.id)
    others = sum(
        (d.amount for d in _line_drawdowns(chosen, currency) if d.source != own),
        Decimal("0"),
    )
    return LineBalance(
        budget_id=chosen.id,
        currency=currency,
        allocated=allocated_amount(chosen.revised_budget, chosen.original_budget),
        drawn_by_others=others,
    )


def require_cover(balance: LineBalance, cumulative_in_line_currency: Decimal) -> None:
    if cumulative_in_line_currency > balance.available:
        raise CommitmentError(
            "contingency_insufficient",
            409,
            detail=f"{balance.available} {balance.currency}",
        )


async def write(
    session: Any,
    *,
    project_id: uuid.UUID,
    item: Any,
    balance: LineBalance,
    amount: Decimal,
    release_id: uuid.UUID,
    decided_by: uuid.UUID | None,
    decided_at: str,
) -> None:
    """Record (or replace) this item's drawdown on its line with the cumulative released amount."""
    from app.modules.finance.service import FinanceService
    from app.modules.risk.contingency import quantize_money

    record = {
        "amount": format(quantize_money(amount, balance.currency), "f"),
        "currency": balance.currency,
        "risk_id": str(item.risk_id) if item.risk_id else "",
        "risk_code": item.code,
        "risk_title": item.title,
        "confirmed_by": "" if decided_by is None else str(decided_by),
        "confirmed_at": decided_at,
        "note": f"commitment release {release_id}",
    }
    await FinanceService(session).set_contingency_drawdown(
        project_id=project_id, source=source_of(item.id), budget_id=balance.budget_id, record=record
    )
