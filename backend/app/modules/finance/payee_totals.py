# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What each supplier was paid over a reporting period - pure arithmetic.

Several jurisdictions make a business report, once a year, what it paid each
contractor or subcontractor, keyed by the payee's tax number: Canada's T5018
Statement of Contract Payments is the one a construction company meets. The
report is the same everywhere: payments made by one legal entity, per payee
and currency, between two dates, with the payees below a threshold left off.
What differs is data, the form, the threshold and the deadline, so it lives in
:data:`PAYEE_RETURNS` keyed by the country of the paying entity, and the
arithmetic here knows nothing about any one form.

Amounts are the cash paid in the period: a payment counts on its own date, a
refund takes money back, and retention held back at a payment is not paid
until it is released, so it counts in the period of the payment that releases
it. Only payables count.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.modules.finance.ageing import AgeingInvoice

_ZERO = Decimal("0")
_CENTS = Decimal("0.01")

#: Annual payee returns by the country of the paying legal entity. ``threshold``
#: is in ``currency``: payees paid less over the period are not reported.
PAYEE_RETURNS: dict[str, dict[str, Any]] = {
    "CA": {
        "form": "T5018",
        "name": "Statement of Contract Payments",
        "threshold": "500",
        "currency": "CAD",
        "reference": "Income Tax Regulations, C.R.C., c. 945, s. 238",
        "due_months_after_period": 6,
        "note": (
            "Filed by a business whose primary activity is construction, for payments to subcontractors for "
            "construction services. The period is the calendar year or the fiscal year, as the business chose, "
            "and the return is due six months after it ends. A payee is identified by business number or "
            "social insurance number."
        ),
    },
}


def payee_return_for(country_code: str | None) -> dict[str, Any] | None:
    """The annual payee return of a country, or None where the table has none."""
    return PAYEE_RETURNS.get((country_code or "").strip().upper())


def _money(value: object) -> Decimal:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        return _ZERO
    return parsed if parsed.is_finite() else _ZERO


def _day(value: object) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


@dataclass
class PayeeTotal:
    """What one legal entity paid one payee in one currency over the period."""

    legal_entity_id: str | None
    contact_id: str | None
    currency_code: str
    paid: Decimal = _ZERO
    refunded: Decimal = _ZERO
    payment_count: int = 0
    invoice_ids: set[str] = field(default_factory=set)
    project_ids: set[str] = field(default_factory=set)
    below_threshold: bool = False

    @property
    def total(self) -> Decimal:
        return (self.paid - self.refunded).quantize(_CENTS, rounding=ROUND_HALF_UP)


def build_payee_totals(
    invoices: Iterable[AgeingInvoice],
    *,
    date_from: str,
    date_to: str,
    threshold: Decimal | None = None,
    threshold_currency: str | None = None,
) -> list[PayeeTotal]:
    """Totals per (entity, payee, currency) of the payable payments between two dates, both included.

    ``threshold`` marks the payees paid less than it as below the threshold;
    it applies only to totals in ``threshold_currency``, since a figure in
    another currency cannot be compared without a rate. Returns the totals
    sorted by entity, currency and largest total first; a payee whose payments
    and refunds net to nothing is left out.
    """
    start, end = _day(date_from), _day(date_to)
    if start is None or end is None or start > end:
        raise ValueError("date_from and date_to must be ISO dates with date_from on or before date_to")
    totals: dict[tuple[str | None, str | None, str], PayeeTotal] = {}
    for inv in invoices:
        if inv.direction != "payable":
            continue
        for pay in inv.payments:
            paid_on = _day(pay.payment_date)
            if paid_on is None or not start <= paid_on <= end:
                continue
            key = (inv.legal_entity_id, inv.contact_id, inv.currency_code)
            row = totals.setdefault(key, PayeeTotal(inv.legal_entity_id, inv.contact_id, inv.currency_code))
            amount = _money(pay.amount)
            if pay.is_refund:
                row.refunded += amount
            else:
                row.paid += amount
            row.payment_count += 1
            row.invoice_ids.add(inv.invoice_id)
            row.project_ids.add(inv.project_id)
    rows = [row for row in totals.values() if row.total != _ZERO]
    if threshold is not None:
        for row in rows:
            row.below_threshold = (
                threshold_currency is not None
                and row.currency_code.upper() == threshold_currency.upper()
                and row.total < threshold
            )
    rows.sort(key=lambda r: (r.legal_entity_id or "", r.currency_code, -r.total, r.contact_id or ""))
    return rows


__all__ = ["PAYEE_RETURNS", "PayeeTotal", "build_payee_totals", "payee_return_for"]
