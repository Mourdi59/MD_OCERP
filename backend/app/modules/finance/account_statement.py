# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Statement of account - pure, dependency-free arithmetic.

What a customer is sent at month end, or what accounting reconciles against a
supplier's own statement: every invoice and payment with one counterparty over
a period, in date order, with a running balance, the balance brought forward
and the balance carried at the end, followed by how old what is open is.

One statement covers one counterparty, one currency, one direction and, when
given, one legal entity, because a balance across currencies or across "they
owe us" and "we owe them" means nothing. The balance is what the counterparty
owes us on a receivable statement and what we owe them on a payable one, so it
reads the same way on both.

Invoices count from their invoice date once they are posted (``pending``,
``approved``, ``sent``) or settled (``paid``). Drafts and cancelled invoices are
not on a statement. A payment counts on its own date and a refund puts money
back on the balance. Retention is part of the invoice total, so the balance
includes it; the ageing section below the lines shows it apart, because it is
owed but not yet due.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.modules.finance.ageing import POSTED_STATUSES, AgeingInvoice, AgeingReport, build_ageing

_ZERO = Decimal("0")
_CENTS = Decimal("0.01")

#: Invoice statuses that put an invoice on a statement.
STATEMENT_STATUSES = frozenset({*POSTED_STATUSES, "paid"})


def _money(value: object) -> Decimal:
    """A finite Decimal, or zero for anything that is not one."""
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO
    return parsed if parsed.is_finite() else _ZERO


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _day(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


@dataclass(frozen=True)
class StatementLine:
    """One movement on the account. ``charge`` raises the balance, ``credit`` lowers it."""

    entry_date: str
    kind: str  # invoice | payment | refund
    reference: str
    invoice_id: str
    project_id: str
    charge: Decimal
    credit: Decimal
    balance: Decimal


@dataclass
class AccountStatement:
    date_from: str | None
    date_to: str
    opening_balance: Decimal = _ZERO
    closing_balance: Decimal = _ZERO
    total_charged: Decimal = _ZERO
    total_credited: Decimal = _ZERO
    lines: list[StatementLine] = field(default_factory=list)
    ageing: AgeingReport | None = None


def build_statement(
    invoices: Iterable[AgeingInvoice],
    *,
    date_from: str | None,
    date_to: str,
) -> AccountStatement:
    """The statement of the given invoices between ``date_from`` and ``date_to``.

    The caller passes the invoices of one counterparty, currency and direction.
    Movements before ``date_from`` add up to the opening balance; movements
    after ``date_to`` are left out entirely. Within a day, invoices come before
    payments, so a same-day invoice and its payment never show a credit dip.
    """
    start = _day(date_from)
    end = _day(date_to) or date.today().isoformat()
    on_statement = [inv for inv in invoices if inv.status in STATEMENT_STATUSES]

    movements: list[tuple[str, int, str, StatementLine]] = []
    for inv in on_statement:
        issued = _day(inv.invoice_date)
        if issued is not None and issued <= end:
            amount = _q2(_money(inv.amount_total))
            movements.append(
                (
                    issued,
                    0,
                    inv.invoice_number,
                    StatementLine(
                        issued, "invoice", inv.invoice_number, inv.invoice_id, inv.project_id, amount, _ZERO, _ZERO
                    ),
                )
            )
        for pay in inv.payments:
            paid_on = _day(pay.payment_date)
            if paid_on is None or paid_on > end:
                continue
            amount = _q2(_money(pay.amount))
            if pay.is_refund:
                line = StatementLine(
                    paid_on, "refund", inv.invoice_number, inv.invoice_id, inv.project_id, amount, _ZERO, _ZERO
                )
            else:
                line = StatementLine(
                    paid_on, "payment", inv.invoice_number, inv.invoice_id, inv.project_id, _ZERO, amount, _ZERO
                )
            movements.append((paid_on, 1, inv.invoice_number, line))
    movements.sort(key=lambda m: (m[0], m[1], m[2]))

    statement = AccountStatement(date_from=start, date_to=end)
    balance = _ZERO
    for when, _, _, line in movements:
        delta = line.charge - line.credit
        if start is not None and when < start:
            statement.opening_balance = _q2(statement.opening_balance + delta)
            balance = statement.opening_balance
            continue
        balance = _q2(balance + delta)
        statement.total_charged = _q2(statement.total_charged + line.charge)
        statement.total_credited = _q2(statement.total_credited + line.credit)
        statement.lines.append(
            StatementLine(
                line.entry_date,
                line.kind,
                line.reference,
                line.invoice_id,
                line.project_id,
                line.charge,
                line.credit,
                balance,
            )
        )
    statement.closing_balance = _q2(balance)
    statement.ageing = build_ageing(on_statement, as_of=end)
    return statement


__all__ = ["STATEMENT_STATUSES", "AccountStatement", "StatementLine", "build_statement"]
