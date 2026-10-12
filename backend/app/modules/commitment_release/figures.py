# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Every amount the matrix shows, read from the module that owns it. Nothing is stored here.

Committed (SPEC rules 1, 1a, 7, lead decision b): contracts and purchase orders
through ``CostSpineRepository.committed_by_document``, the per-document twin of
the one counting rule (``committed_by_cost_line``). Changes and contract lines
are read from their own rows. Then the once-only rules run over the WHOLE
link set of the project, so a document is counted exactly once project-wide:

* an approved change order or variation is already folded into its contract's
  value, so the contract's link reports its value net of every change and
  every contract line linked anywhere in the matrix, and the change or line
  reports its own amount where it is linked (own item or the contract's item);
* a contract and a purchase order raised from the same award count as the
  contract plus only the part of the order above it (as in costmodel);
* a tender package link is the award's provenance, never an amount.

Amounts come back in each document's own currency; the service converts under
the matrix FX policy and refuses on a missing rate.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commitment_release.catalogue import parse_amount

ZERO = Decimal("0")
LINK_KINDS: tuple[str, ...] = (
    "contract",
    "contract_line",
    "purchase_order",
    "change_order",
    "variation_order",
    "tender_package",
    "bid_package",
    "rfq",
    "contingency_drawdown",
)
# The award a commitment was born from, in each of the three tendering modules:
# provenance, never an amount (the contract and PO the award drafts carry it).
AWARD_KINDS: tuple[str, ...] = ("tender_package", "bid_package", "rfq")
_CO_COUNTING = ("approved", "executed")
_VO_NOT_COUNTING = ("voided", "cancelled", "draft")
_CONTRACT_CLOSED = ("completed", "closed", "terminated")
_PO_CLOSED = ("completed", "cancelled")


@dataclass
class LinkFigure:
    """One linked document's committed amount after the once-only rules, in its own currency."""

    link_id: uuid.UUID
    item_id: uuid.UUID
    kind: str
    document_id: uuid.UUID
    currency: str = ""
    raw: Decimal = ZERO
    amount: Decimal = ZERO
    counts: bool = False
    closed: bool = False
    status: str = ""
    found: bool = True
    contract_id: uuid.UUID | None = None
    award_tokens: frozenset[str] = field(default_factory=frozenset)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "link_id": str(self.link_id),
            "kind": self.kind,
            "document_id": str(self.document_id),
            "currency": self.currency,
            "document_amount": str(self.raw),
            "counted_amount": str(self.amount),
            "counts": self.counts,
            "closed": self.closed,
            "status": self.status,
            "found": self.found,
            "notes": list(self.notes),
        }


def _money(raw: object) -> Decimal:
    if raw is None or raw == "":
        return ZERO
    return parse_amount(raw)


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def document_in_project(session: AsyncSession, project_id: uuid.UUID, kind: str, document_id: uuid.UUID) -> bool:
    """Whether ``document_id`` of ``kind`` belongs to ``project_id`` (rule 21: anything else is 404)."""
    from app.modules.bid_management.models import BidPackage
    from app.modules.changeorders.models import ChangeOrder
    from app.modules.contracts.models import Contract, ContractLine
    from app.modules.procurement.models import PurchaseOrder
    from app.modules.rfq_bidding.models import RFQ
    from app.modules.tendering.models import TenderPackage
    from app.modules.variations.models import VariationOrder

    if kind == "contract_line":
        stmt = (
            select(ContractLine.id)
            .join(Contract, Contract.id == ContractLine.contract_id)
            .where(ContractLine.id == document_id, Contract.project_id == project_id)
        )
        return (await session.execute(stmt)).first() is not None
    model = {
        "contract": Contract,
        "purchase_order": PurchaseOrder,
        "change_order": ChangeOrder,
        "variation_order": VariationOrder,
        "tender_package": TenderPackage,
        "bid_package": BidPackage,
        "rfq": RFQ,
    }.get(kind)
    if model is None:
        return False
    stmt = select(model.id).where(model.id == document_id, model.project_id == project_id)
    return (await session.execute(stmt)).first() is not None


async def link_figures(
    session: AsyncSession, project_id: uuid.UUID, links: list[Any], *, basis: str
) -> list[LinkFigure]:
    """Committed per link after the once-only rules, for the WHOLE list of the project's links."""
    from app.modules.changeorders.models import ChangeOrder
    from app.modules.contracts.models import Contract, ContractLine
    from app.modules.costmodel.repository import CostSpineRepository
    from app.modules.variations.models import VariationOrder

    figs = [LinkFigure(link.id, link.item_id, link.kind, link.document_id) for link in links]
    by_kind: dict[str, list[LinkFigure]] = {}
    for f in figs:
        by_kind.setdefault(f.kind, []).append(f)

    contract_ids = [f.document_id for f in by_kind.get("contract", [])]
    po_ids = [f.document_id for f in by_kind.get("purchase_order", [])]
    docs = await CostSpineRepository(session).committed_by_document(
        project_id, contract_ids=contract_ids, purchase_order_ids=po_ids
    )
    for f in by_kind.get("contract", []) + by_kind.get("purchase_order", []):
        d = docs.get((f.kind, f.document_id))
        if d is None:
            f.found = False
            continue
        f.currency, f.counts, f.status, f.award_tokens = d.currency, d.counts, d.status, d.award_tokens
        f.raw = d.gross if basis == "gross" else d.net
        closed_set = _CONTRACT_CLOSED if f.kind == "contract" else _PO_CLOSED
        f.closed = (d.status or "").strip().lower() in closed_set

    line_ids = [f.document_id for f in by_kind.get("contract_line", [])]
    if line_ids:
        stmt = (
            select(ContractLine.id, ContractLine.contract_id, ContractLine.total_value, Contract)
            .join(Contract, Contract.id == ContractLine.contract_id)
            .where(ContractLine.id.in_(line_ids), Contract.project_id == project_id)
        )
        rows = {r[0]: r for r in (await session.execute(stmt)).all()}
        for f in by_kind.get("contract_line", []):
            r = rows.get(f.document_id)
            if r is None:
                f.found = False
                continue
            contract = r[3]
            f.contract_id = r[1]
            f.currency = (contract.currency or "").strip().upper()
            f.status = contract.status or ""
            f.counts = contract.counterparty_type == "subcontractor" and f.status.lower() not in (
                "draft",
                "cancelled",
                "void",
            )
            f.raw = _money(r[2]) if f.counts else ZERO
            f.closed = f.status.lower() in _CONTRACT_CLOSED

    co_ids = [f.document_id for f in by_kind.get("change_order", [])]
    if co_ids:
        cos = {
            c.id: c
            for c in (
                await session.execute(
                    select(ChangeOrder).where(ChangeOrder.id.in_(co_ids), ChangeOrder.project_id == project_id)
                )
            ).scalars()
        }
        for f in by_kind.get("change_order", []):
            c = cos.get(f.document_id)
            if c is None:
                f.found = False
                continue
            f.status = c.status or ""
            f.currency = (c.currency or "").strip().upper()
            f.counts = f.status.lower() in _CO_COUNTING
            f.raw = (
                (_money(c.approved_amount) if c.approved_amount is not None else _money(c.cost_impact))
                if f.counts
                else ZERO
            )
            f.contract_id = _uuid((c.metadata_ or {}).get("contract_id")) if isinstance(c.metadata_, dict) else None
            f.closed = f.status.lower() == "executed"

    vo_ids = [f.document_id for f in by_kind.get("variation_order", [])]
    if vo_ids:
        vos = {
            v.id: v
            for v in (
                await session.execute(
                    select(VariationOrder).where(VariationOrder.id.in_(vo_ids), VariationOrder.project_id == project_id)
                )
            ).scalars()
        }
        for f in by_kind.get("variation_order", []):
            v = vos.get(f.document_id)
            if v is None:
                f.found = False
                continue
            f.status = v.status or ""
            f.currency = (v.currency or "").strip().upper()
            f.counts = f.status.lower() not in _VO_NOT_COUNTING
            f.raw = _money(v.final_cost_impact) if f.counts else ZERO
            f.contract_id = v.affected_contract_id
            f.closed = f.status.lower() == "completed"

    for f in [*(f for k in AWARD_KINDS for f in by_kind.get(k, [])), *by_kind.get("contingency_drawdown", [])]:
        f.counts = False
        f.notes.append("provenance_only" if f.kind in AWARD_KINDS else "drawdown_not_wired")

    for f in figs:
        f.amount = f.raw if f.counts else ZERO

    # Changes and contract lines are inside their contract's value: take them out
    # of the contract link wherever they are linked, so each is counted once.
    contract_fig = {f.document_id: f for f in by_kind.get("contract", [])}
    for f in by_kind.get("contract_line", []) + by_kind.get("change_order", []) + by_kind.get("variation_order", []):
        host = contract_fig.get(f.contract_id) if f.contract_id else None
        if host is not None and host.counts and f.counts:
            if host.currency == f.currency:
                host.amount -= f.amount
                host.notes.append(f"net_of:{f.kind}:{f.document_id}")
            else:
                host.notes.append(f"currency_mismatch_not_netted:{f.kind}:{f.document_id}")

    # A PO from the same award as a contract counts only above the contract.
    for po in by_kind.get("purchase_order", []):
        if not po.counts or not po.award_tokens:
            continue
        pair = [
            c
            for c in by_kind.get("contract", [])
            if c.counts and c.award_tokens & po.award_tokens and c.currency == po.currency
        ]
        if pair:
            covered = sum((c.raw for c in pair), ZERO)
            po.amount = max(po.raw - covered, ZERO)
            po.notes.append("award_pair_counted_above_contract")
    return figs


async def planned_amount(session: AsyncSession, item: Any, base_currency: str) -> tuple[Decimal | None, str, str]:
    """``(amount, currency, note)`` from the item's planned source; ``None`` when the source is gone."""
    from app.modules.costmodel.models import BudgetLine, CostLine

    src, sid = item.planned_source, item.planned_source_id
    if src == "manual":
        if item.planned_manual_amount is None:
            return None, item.currency or base_currency, "manual_estimate_missing"
        return Decimal(item.planned_manual_amount), item.currency or base_currency, "manual_estimate"
    if sid is None:
        return None, item.currency or base_currency, "planned_source_missing"
    if src == "budget_line":
        row = await session.get(BudgetLine, sid)
        if row is None or row.project_id != item.project_id:
            return None, item.currency or base_currency, "planned_source_missing"
        return _money(row.planned_amount), (row.currency or base_currency).strip().upper(), "budget_line"
    if src == "cost_line":
        row = await session.get(CostLine, sid)
        if row is None or row.project_id != item.project_id:
            return None, item.currency or base_currency, "planned_source_missing"
        return _money(row.estimate_amount), (row.currency or base_currency).strip().upper(), "cost_line"
    if src == "boq_position":
        from app.modules.boq.models import BOQ, Position

        stmt = (
            select(Position.total)
            .join(BOQ, BOQ.id == Position.boq_id)
            .where(Position.id == sid, BOQ.project_id == item.project_id)
        )
        total = (await session.execute(stmt)).scalar_one_or_none()
        if total is None:
            return None, base_currency, "planned_source_missing"
        return _money(total), base_currency, "boq_position"
    return None, item.currency or base_currency, "planned_source_missing"


async def planned_source_in_project(session: AsyncSession, project_id: uuid.UUID, src: str, sid: uuid.UUID) -> bool:
    """Whether a planned source row belongs to the project (rule 21)."""
    from app.modules.costmodel.models import BudgetLine, CostLine

    if src == "budget_line":
        row = await session.get(BudgetLine, sid)
        return row is not None and row.project_id == project_id
    if src == "cost_line":
        row = await session.get(CostLine, sid)
        return row is not None and row.project_id == project_id
    if src == "boq_position":
        from app.modules.boq.models import BOQ, Position

        stmt = (
            select(Position.id)
            .join(BOQ, BOQ.id == Position.boq_id)
            .where(Position.id == sid, BOQ.project_id == project_id)
        )
        return (await session.execute(stmt)).first() is not None
    return False


async def activity_dates(
    session: AsyncSession, project_id: uuid.UUID, activity_id: uuid.UUID | None
) -> tuple[str | None, str | None, bool]:
    """``(late_start, start_date, found)`` of a schedule activity of this project."""
    if activity_id is None:
        return None, None, False
    from app.modules.schedule.models import Activity, Schedule

    stmt = (
        select(Activity.late_start, Activity.start_date)
        .join(Schedule, Schedule.id == Activity.schedule_id)
        .where(Activity.id == activity_id, Schedule.project_id == project_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None, None, False
    return row[0], row[1], True


async def requisition_lead_time(session: AsyncSession, project_id: uuid.UUID, req_id: uuid.UUID | None) -> int | None:
    if req_id is None:
        return None
    from app.modules.procurement.models import MaterialRequisition

    row = await session.get(MaterialRequisition, req_id)
    if row is None or row.project_id != project_id:
        return None
    return int(row.lead_time_days or 0)


async def sunk_parts(session: AsyncSession, figs: list[LinkFigure]) -> dict[str, Decimal]:
    """Performed value of the linked contracts, split paid / certified-not-paid, in contract currency.

    Read from progress claims (the same certified cumulative values costmodel
    uses for terminated contracts). Invoices and goods receipts of purchase
    orders are not read yet; their part of ``sunk`` is reported as 0 and the
    exposure lines say so.
    """
    from app.modules.contracts.models import ContractLine, ProgressClaim, ProgressClaimLine

    contract_ids = [f.document_id for f in figs if f.kind == "contract" and f.found]
    out = {"paid": ZERO, "invoiced_unpaid": ZERO, "certified_not_invoiced": ZERO, "received_not_invoiced": ZERO}
    if not contract_ids:
        return out

    async def cumulative(statuses: tuple[str, ...]) -> Decimal:
        stmt = (
            select(ProgressClaimLine.contract_line_id, func.max(ProgressClaimLine.cumulative_completed_value))
            .join(ProgressClaim, ProgressClaim.id == ProgressClaimLine.progress_claim_id)
            .join(ContractLine, ContractLine.id == ProgressClaimLine.contract_line_id)
            .where(ContractLine.contract_id.in_(contract_ids), ProgressClaim.status.in_(statuses))
            .group_by(ProgressClaimLine.contract_line_id)
        )
        return sum((_money(v) for _, v in (await session.execute(stmt)).all()), ZERO)

    certified = await cumulative(("certified", "paid"))
    paid = await cumulative(("paid",))
    out["paid"] = paid
    out["certified_not_invoiced"] = certified - paid
    return out
