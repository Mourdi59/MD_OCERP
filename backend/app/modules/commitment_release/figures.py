# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Every amount the matrix shows, read from the module that owns it. Nothing is stored here.

Committed (SPEC rules 1, 1a, 7, lead decision b): whether a contract or a
purchase order counts is decided by ``CostSpineRepository.committed_by_document``,
the per-document twin of the one counting rule (``committed_by_cost_line``).
Then the once-only rules run over the WHOLE link set of the project, so a
document is counted exactly once project-wide:

* a contract that is not terminated counts at its header ``Contract.total_value``.
  The header already carries every approved change order and completed
  variation: the platform adds them there and adds no contract line. A
  terminated contract counts what was certified, as in costmodel;
* a change order (approved or executed) or a variation (completed, the only
  state in which it moves money) counts on its own link only while the header
  of a contract linked in the matrix does not carry it yet. Once it has moved
  that header it reads 0 on its own link, never twice;
* a contract line linked on its own comes out of its contract's link;
* a contract and a purchase order raised from the same award count as the
  contract plus only the part of the order above it (as in costmodel);
* a tender package link is the award's provenance, never an amount.

The header view and the cost-line view differ by exactly the changes that moved
a header without adding a line; ``tests/pg`` states that difference.

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
CHANGE_KINDS: tuple[str, ...] = ("change_order", "variation_order")
# The metadata key under which a contract or order drafted by an award names it, by award kind.
AWARD_META_KEYS: dict[str, str] = {
    "tender_package_id": "tender_package",
    "bid_package_id": "bid_package",
    "rfq_id": "rfq",
}
_CO_COUNTING = ("approved", "executed")
# A variation moves the contract sum at ``completed`` and nowhere else.
_VO_COUNTING = ("completed",)
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
    # A change: the key its contract posts it under (a variation and its mirror change order share one).
    source_key: str = ""
    award_tokens: frozenset[str] = field(default_factory=frozenset)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "link_id": str(self.link_id),
            "kind": self.kind,
            "document_id": str(self.document_id),
            "contract_id": str(self.contract_id) if self.contract_id else None,
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


def change_source_key(kind: str, document_id: uuid.UUID, metadata: dict[str, Any] | None) -> str:
    """The key a contract posts this change under; a variation and the change order mirroring it share one."""
    from app.modules.notifications._wave5_cross_module_subscribers import _contract_source_key

    if kind == "variation_order":
        return _contract_source_key(variation_order_id=document_id)
    mirrored = (metadata or {}).get("variation_order_id")
    return _contract_source_key(variation_order_id=mirrored, change_order_id=document_id)


def posted_source_keys(contract_metadata: Any) -> set[str]:
    """Every change whose money a contract header already carries, as the platform's own posting guard reads it."""
    from app.modules.notifications._wave5_cross_module_subscribers import _posted_source_keys

    return _posted_source_keys(contract_metadata if isinstance(contract_metadata, dict) else {})


@dataclass(frozen=True)
class ChangeHost:
    """Where a change order or variation lands: its contract, and whether that header carries it already."""

    contract_id: uuid.UUID | None
    posted: bool


async def change_host(session: AsyncSession, project_id: uuid.UUID, kind: str, document_id: uuid.UUID) -> ChangeHost:
    """The contract a change of this project amends and whether it has moved that header."""
    from app.modules.changeorders.models import ChangeOrder
    from app.modules.contracts.models import Contract
    from app.modules.variations.models import VariationOrder

    contract_id: uuid.UUID | None = None
    meta: dict[str, Any] | None = None
    if kind == "change_order":
        co = await session.get(ChangeOrder, document_id)
        if co is None or co.project_id != project_id:
            return ChangeHost(None, False)
        meta = co.metadata_ if isinstance(co.metadata_, dict) else {}
        contract_id = _uuid(meta.get("contract_id"))
    elif kind == "variation_order":
        vo = await session.get(VariationOrder, document_id)
        if vo is None or vo.project_id != project_id:
            return ChangeHost(None, False)
        contract_id = vo.affected_contract_id
    if contract_id is None:
        return ChangeHost(None, False)
    contract = await session.get(Contract, contract_id)
    if contract is None or contract.project_id != project_id:
        return ChangeHost(None, False)
    key = change_source_key(kind, document_id, meta)
    return ChangeHost(contract_id, key in posted_source_keys(contract.metadata_))


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
    headers: dict[uuid.UUID, Any] = {}
    if contract_ids:
        headers = {
            c.id: c
            for c in (
                await session.execute(
                    select(Contract).where(Contract.id.in_(contract_ids), Contract.project_id == project_id)
                )
            ).scalars()
        }
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
        head = headers.get(f.document_id) if f.kind == "contract" else None
        if head is not None and d.counts and (d.status or "").strip().lower() != "terminated":
            # The header, not the line sum: approved changes move the header and add no line.
            f.raw = _money(head.total_value)
            f.notes.append("contract_header_value")
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
            meta = c.metadata_ if isinstance(c.metadata_, dict) else {}
            f.contract_id = _uuid(meta.get("contract_id"))
            f.source_key = change_source_key("change_order", c.id, meta)
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
            f.counts = f.status.lower() in _VO_COUNTING
            f.raw = _money(v.final_cost_impact) if f.counts else ZERO
            f.contract_id = v.affected_contract_id
            f.source_key = change_source_key("variation_order", v.id, None)
            f.closed = f.counts

    for f in [*(f for k in AWARD_KINDS for f in by_kind.get(k, [])), *by_kind.get("contingency_drawdown", [])]:
        f.counts = False
        f.notes.append("provenance_only" if f.kind in AWARD_KINDS else "drawdown_not_wired")

    for f in figs:
        f.amount = f.raw if f.counts else ZERO

    # A contract line linked on its own is inside its contract's value: take it out of the
    # contract link, so it is counted once.
    contract_fig = {f.document_id: f for f in by_kind.get("contract", [])}
    for f in by_kind.get("contract_line", []):
        host = contract_fig.get(f.contract_id) if f.contract_id else None
        if host is not None and host.counts and f.counts:
            if host.currency == f.currency:
                host.amount -= f.amount
                host.notes.append(f"net_of:{f.kind}:{f.document_id}")
            else:
                host.notes.append(f"currency_mismatch_not_netted:{f.kind}:{f.document_id}")

    # A change counts on its own link only until the header of a linked contract carries it.
    seen_keys: set[str] = set()
    for f in by_kind.get("change_order", []) + by_kind.get("variation_order", []):
        if not f.counts:
            continue
        host = contract_fig.get(f.contract_id) if f.contract_id else None
        head = headers.get(f.contract_id) if f.contract_id else None
        if host is not None and host.counts and head is not None:
            if host.status.strip().lower() == "terminated":
                f.amount = ZERO
                f.notes.append(f"contract_terminated:{f.contract_id}")
                continue
            if f.source_key in posted_source_keys(head.metadata_):
                f.amount = ZERO
                f.notes.append(f"inside_contract_value:{f.contract_id}")
                continue
        if f.source_key in seen_keys:
            f.amount = ZERO
            f.notes.append("mirror_counted_once")
            continue
        seen_keys.add(f.source_key)

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


SUNK_PARTS: tuple[str, ...] = ("paid", "invoiced_unpaid", "certified_not_invoiced", "received_not_invoiced")
_INVOICE_NOT_BILLED = ("draft", "cancelled", "credit_note_issued")


async def sunk_by_link(
    session: AsyncSession, project_id: uuid.UUID, figs: list[LinkFigure], *, basis: str
) -> dict[uuid.UUID, list[tuple[str, Decimal, str]]]:
    """Money already spent or owed on each linked document: ``{link id: [(part, amount, currency)]}``.

    A contract: its progress claims, the same certified cumulative values costmodel uses for a
    terminated contract (paid, and certified but not yet paid). A purchase order: the supplier
    invoices billed against it (paid, and billed but unpaid) and the value of confirmed goods
    receipts beyond what was billed. Amounts stay in the currency of the row they were read from.
    """
    from app.modules.contracts.models import ContractLine, ProgressClaim, ProgressClaimLine
    from app.modules.finance.models import Invoice
    from app.modules.finance.po_link import invoice_po_link
    from app.modules.procurement.models import GoodsReceipt, GoodsReceiptItem, PurchaseOrderItem

    out: dict[uuid.UUID, list[tuple[str, Decimal, str]]] = {}
    contracts = {f.document_id: f for f in figs if f.kind == "contract" and f.found}
    if contracts:

        async def cumulative(statuses: tuple[str, ...]) -> dict[uuid.UUID, Decimal]:
            stmt = (
                select(
                    ContractLine.contract_id,
                    ProgressClaimLine.contract_line_id,
                    func.max(ProgressClaimLine.cumulative_completed_value),
                )
                .join(ProgressClaim, ProgressClaim.id == ProgressClaimLine.progress_claim_id)
                .join(ContractLine, ContractLine.id == ProgressClaimLine.contract_line_id)
                .where(ContractLine.contract_id.in_(list(contracts)), ProgressClaim.status.in_(statuses))
                .group_by(ContractLine.contract_id, ProgressClaimLine.contract_line_id)
            )
            totals: dict[uuid.UUID, Decimal] = {}
            for contract_id, _line, value in (await session.execute(stmt)).all():
                totals[contract_id] = totals.get(contract_id, ZERO) + _money(value)
            return totals

        certified = await cumulative(("certified", "paid"))
        paid = await cumulative(("paid",))
        for cid, f in contracts.items():
            out[f.link_id] = [
                ("paid", paid.get(cid, ZERO), f.currency),
                ("certified_not_invoiced", certified.get(cid, ZERO) - paid.get(cid, ZERO), f.currency),
            ]

    orders = {f.document_id: f for f in figs if f.kind == "purchase_order" and f.found}
    if orders:
        billed: dict[uuid.UUID, Decimal] = {}
        rows = (
            await session.execute(
                select(Invoice).where(Invoice.project_id == project_id, Invoice.invoice_direction == "payable")
            )
        ).scalars()
        for inv in rows:
            po_id = invoice_po_link(inv.purchase_order_id, inv.metadata_)
            status = (inv.status or "").strip().lower()
            if po_id not in orders or status in _INVOICE_NOT_BILLED:
                continue
            amount = _money(inv.amount_total if basis == "gross" else inv.amount_subtotal)
            currency = (inv.currency_code or "").strip().upper() or orders[po_id].currency
            out.setdefault(orders[po_id].link_id, []).append(
                ("paid" if status == "paid" else "invoiced_unpaid", amount, currency)
            )
            if currency == orders[po_id].currency:
                billed[po_id] = billed.get(po_id, ZERO) + amount
        stmt = (
            select(GoodsReceipt.po_id, GoodsReceiptItem.quantity_received, PurchaseOrderItem.unit_rate)
            .join(GoodsReceiptItem, GoodsReceiptItem.receipt_id == GoodsReceipt.id)
            .join(PurchaseOrderItem, PurchaseOrderItem.id == GoodsReceiptItem.po_item_id)
            .where(GoodsReceipt.po_id.in_(list(orders)), GoodsReceipt.status == "confirmed")
        )
        received: dict[uuid.UUID, Decimal] = {}
        for po_id, quantity, rate in (await session.execute(stmt)).all():
            received[po_id] = received.get(po_id, ZERO) + _money(quantity) * _money(rate)
        for po_id, value in received.items():
            # Only the part of the delivered value no invoice has billed yet: billed goods are
            # already in the invoice parts, and an invoice ahead of delivery leaves nothing here.
            ahead = value - billed.get(po_id, ZERO)
            if ahead > ZERO:
                out.setdefault(orders[po_id].link_id, []).append(
                    ("received_not_invoiced", ahead, orders[po_id].currency)
                )
    return out
