# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Payment runs: draw up, edit, approve, execute, cancel.

The rules live in :mod:`app.modules.finance.payment_runs`; this service loads
the rows they read and writes what they decide. Executing a run records one
ordinary payment per item through :meth:`FinanceService.create_payment`, with an
idempotency key per item, so a retried execute never pays an invoice twice.

Scope: a run is drawn up from the projects its author can open, and a reader
sees a run only when every project in it is one they can open. ``project_ids``
is ``None`` for an admin, meaning every project, as everywhere in finance.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.finance.ageing import open_balance
from app.modules.finance.payment_run_models import ACTIVE_PAYMENT_RUN_STATUSES, PaymentRun, PaymentRunItem
from app.modules.finance.payment_runs import RunIssue, RunLine, check_run, has_errors, propose
from app.modules.finance.schemas import PaymentCreate
from app.modules.finance.service import FinanceService

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _issue_dicts(issues: Iterable[RunIssue]) -> list[dict[str, str | None]]:
    return [
        {
            "severity": i.severity,
            "code": i.code,
            "message": i.message,
            "item_id": i.item_id,
            "invoice_id": i.invoice_id,
        }
        for i in issues
    ]


class PaymentRunService:
    """Payment runs over the finance invoices and payments."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.finance = FinanceService(session)

    # ── reads ──────────────────────────────────────────────────────────────

    async def get(self, run_id: uuid.UUID, *, project_ids: set[uuid.UUID] | None, user_id: str | None) -> PaymentRun:
        """A run the reader may see, with its items, or 404."""
        stmt = select(PaymentRun).where(PaymentRun.id == run_id).options(selectinload(PaymentRun.items))
        run = (await self.session.execute(stmt)).scalar_one_or_none()
        if run is None or not self._visible(run, project_ids, user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment run not found")
        return run

    async def list(
        self,
        *,
        project_ids: set[uuid.UUID] | None,
        user_id: str | None,
        status_filter: str | None = None,
        legal_entity_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[PaymentRun]:
        """Runs the reader may see, newest first."""
        stmt = select(PaymentRun).options(selectinload(PaymentRun.items)).order_by(PaymentRun.created_at.desc())
        if status_filter:
            stmt = stmt.where(PaymentRun.status == status_filter)
        if legal_entity_id is not None:
            stmt = stmt.where(PaymentRun.legal_entity_id == legal_entity_id)
        runs = (await self.session.execute(stmt.limit(500))).scalars().all()
        return [run for run in runs if self._visible(run, project_ids, user_id)][:limit]

    @staticmethod
    def _visible(run: PaymentRun, project_ids: set[uuid.UUID] | None, user_id: str | None) -> bool:
        if project_ids is None:
            return True
        if not run.items:
            return bool(user_id) and run.created_by == str(user_id)
        return all(item.project_id in project_ids for item in run.items)

    async def _taken(self, *, exclude_run_id: uuid.UUID | None = None) -> set[str]:
        """Invoices already in a draft or approved run."""
        stmt = (
            select(PaymentRunItem.invoice_id)
            .join(PaymentRun, PaymentRun.id == PaymentRunItem.run_id)
            .where(PaymentRun.status.in_(ACTIVE_PAYMENT_RUN_STATUSES))
        )
        if exclude_run_id is not None:
            stmt = stmt.where(PaymentRun.id != exclude_run_id)
        return {str(i) for i in (await self.session.execute(stmt)).scalars().all()}

    async def _next_number(self) -> str:
        count = (await self.session.execute(select(func.count()).select_from(PaymentRun))).scalar_one()
        n = int(count) + 1
        while True:
            candidate = f"PAY-{n:04d}"
            exists = (
                await self.session.execute(select(PaymentRun.id).where(PaymentRun.run_number == candidate))
            ).scalar_one_or_none()
            if exists is None:
                return candidate
            n += 1

    # ── draw up and edit ───────────────────────────────────────────────────

    async def create(
        self,
        *,
        legal_entity_id: uuid.UUID | None,
        currency_code: str,
        payment_date: str,
        due_by: str,
        note: str | None,
        project_ids: set[uuid.UUID] | None,
        actor_id: str | None,
    ) -> PaymentRun:
        """Draw up a draft run from what falls due by ``due_by``.

        A run with nothing in it is refused rather than saved empty, so the
        list never fills with runs that pay no one.
        """
        invoices = await self.finance.load_ageing_invoices(
            direction="payable",
            project_ids=project_ids,
            legal_entity_id=legal_entity_id,
            unassigned_only=legal_entity_id is None,
        )
        proposals = propose(
            invoices,
            currency_code=currency_code,
            payment_date=payment_date,
            due_by=due_by,
            taken=await self._taken(),
        )
        if not proposals:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"No approved supplier invoice in {currency_code} falls due by {due_by} "
                    "with anything left to pay, outside the runs already drawn up."
                ),
            )
        run = PaymentRun(
            run_number=await self._next_number(),
            legal_entity_id=legal_entity_id,
            currency_code=currency_code,
            payment_date=payment_date,
            due_by=due_by,
            status="draft",
            note=note,
            created_by=str(actor_id) if actor_id else None,
        )
        run.items = [
            PaymentRunItem(
                invoice_id=uuid.UUID(p.invoice_id),
                project_id=uuid.UUID(p.project_id),
                contact_id=p.contact_id,
                amount=p.amount,
                open_at_proposal=p.amount,
            )
            for p in proposals
        ]
        self.session.add(run)
        await self.session.flush()
        await self._audit(run, "created", actor_id, {"items": len(run.items)})
        logger.info("Payment run %s drawn up: %d invoices", run.run_number, len(run.items))
        return run

    def _require_status(self, run: PaymentRun, *allowed: str) -> None:
        if run.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment run {run.run_number} is {run.status}; this needs it to be {' or '.join(allowed)}.",
            )

    def _item(self, run: PaymentRun, item_id: uuid.UUID) -> PaymentRunItem:
        for item in run.items:
            if item.id == item_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment run item not found")

    async def update_item(self, run: PaymentRun, item_id: uuid.UUID, amount: Decimal, actor_id: str | None) -> None:
        """Pay a different amount on one invoice of a draft run, never more than is open."""
        self._require_status(run, "draft")
        item = self._item(run, item_id)
        found = await self.finance.load_ageing_invoices(invoice_ids=[item.invoice_id])
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
        invoice = found[0]
        open_due = open_balance(invoice, as_of=run.payment_date).due
        if amount > open_due:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invoice {invoice.invoice_number}: {amount} is more than the {open_due} still open on it.",
            )
        item.amount = amount
        await self.session.flush()
        await self._audit(run, "item_changed", actor_id, {"invoice_id": str(item.invoice_id), "amount": str(amount)})

    async def remove_item(self, run: PaymentRun, item_id: uuid.UUID, actor_id: str | None) -> None:
        """Take one invoice out of a draft run."""
        self._require_status(run, "draft")
        item = self._item(run, item_id)
        run.items.remove(item)
        await self.session.flush()
        await self._audit(run, "item_removed", actor_id, {"invoice_id": str(item.invoice_id)})

    # ── checks and transitions ─────────────────────────────────────────────

    async def check(self, run: PaymentRun, *, approver: str | None = None) -> list[RunIssue]:
        """Every reason not to pay the run as it stands now."""
        invoice_ids = [item.invoice_id for item in run.items]
        invoices = await self.finance.load_ageing_invoices(invoice_ids=invoice_ids) if invoice_ids else []
        by_id = {inv.invoice_id: inv for inv in invoices}
        numbers = {inv.invoice_id: inv.invoice_number for inv in invoices}
        lines = [
            RunLine(
                item_id=str(item.id),
                invoice_id=str(item.invoice_id),
                invoice_number=numbers.get(str(item.invoice_id), ""),
                amount=Decimal(str(item.amount)),
            )
            for item in run.items
        ]
        issues = check_run(
            lines,
            currency_code=run.currency_code,
            payment_date=run.payment_date,
            invoices=by_id,
            taken_elsewhere=await self._taken(exclude_run_id=run.id),
            created_by=run.created_by,
            approver=approver,
        )
        issues.extend(await self._release_issues(run))
        return issues

    async def _release_issues(self, run: PaymentRun) -> list[RunIssue]:
        """Procurement's payment release rules, asked per invoice as paying it by hand would."""
        out: list[RunIssue] = []
        for item in run.items:
            invoice = await self.finance.invoices.get(item.invoice_id)
            if invoice is None:
                continue
            try:
                await self.finance._check_payment_release(invoice)
            except HTTPException as exc:
                out.append(
                    RunIssue(
                        "error",
                        "payment_release_blocked",
                        f"Invoice {invoice.invoice_number}: {exc.detail}",
                        item_id=str(item.id),
                        invoice_id=str(item.invoice_id),
                    )
                )
        return out

    @staticmethod
    def _refuse(run: PaymentRun, issues: list[RunIssue], verb: str) -> None:
        if has_errors(issues):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": f"Payment run {run.run_number} cannot be {verb} as it stands.",
                    "issues": _issue_dicts(issues),
                },
            )

    async def approve(self, run: PaymentRun, actor_id: str | None) -> list[RunIssue]:
        """Approve a draft run once nothing blocks it; returns the warnings."""
        self._require_status(run, "draft")
        issues = await self.check(run, approver=str(actor_id) if actor_id else None)
        self._refuse(run, issues, "approved")
        run.status = "approved"
        run.approved_by = str(actor_id) if actor_id else None
        run.approved_at = _now()
        await self.session.flush()
        await self._audit(run, "approved", actor_id, {"warnings": [i.code for i in issues]})
        return issues

    async def execute(self, run: PaymentRun, actor_id: str | None) -> None:
        """Record the payments of an approved run, all or none.

        Checks again first: an invoice paid by hand or cancelled since the
        approval blocks the run rather than being paid twice. An invoice that
        the run leaves with nothing due and no retention held is marked paid,
        the same transition as paying it by hand.
        """
        self._require_status(run, "approved")
        issues = await self.check(run)
        self._refuse(run, issues, "paid")
        settled: list[uuid.UUID] = []
        for item in run.items:
            payment = await self.finance.create_payment(
                PaymentCreate(
                    invoice_id=item.invoice_id,
                    payment_date=run.payment_date,
                    amount=format(Decimal(str(item.amount)), "f"),
                    currency_code=run.currency_code,
                    reference=run.run_number,
                    idempotency_key=f"payment-run:{item.id}",
                    metadata={"payment_run_id": str(run.id), "payment_run_number": run.run_number},
                ),
                actor_id=actor_id,
            )
            item.payment_id = payment.id
            settled.append(item.invoice_id)
        await self.session.flush()
        for inv in await self.finance.load_ageing_invoices(invoice_ids=settled):
            balance = open_balance(inv, as_of=run.payment_date)
            if inv.status in ("approved", "sent") and not balance.is_open:
                await self.finance.pay_invoice(
                    uuid.UUID(inv.invoice_id), actor_id=actor_id, reason=f"Paid in payment run {run.run_number}"
                )
        run.status = "executed"
        run.executed_by = str(actor_id) if actor_id else None
        run.executed_at = _now()
        await self.session.flush()
        await self._audit(run, "executed", actor_id, {"payments": len(settled)})
        logger.info("Payment run %s executed: %d payments", run.run_number, len(settled))

    async def cancel(self, run: PaymentRun, actor_id: str | None) -> None:
        """Drop a run that has not been paid; its invoices are free for another run."""
        self._require_status(run, "draft", "approved")
        run.status = "cancelled"
        await self.session.flush()
        await self._audit(run, "cancelled", actor_id, {})

    async def _audit(self, run: PaymentRun, action: str, actor_id: str | None, meta: dict) -> None:
        try:
            from app.core.audit_log import log_activity

            await log_activity(
                self.session,
                actor_id=actor_id,
                entity_type="payment_run",
                entity_id=str(run.id),
                action=action,
                reason=f"Payment run {run.run_number} {action}",
                metadata={"run_number": run.run_number, **meta},
            )
        except Exception as exc:
            logger.warning("Audit log FAILED for payment run %s %s: %s", run.run_number, action, exc, exc_info=True)


__all__ = ["PaymentRunService"]
