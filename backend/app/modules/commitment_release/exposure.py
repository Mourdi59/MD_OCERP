# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Abort exposure: what stopping a commitment on date D would still cost (SPEC rule 14).

Pure arithmetic over figures the service gathers. Never clamped: a negative
residual loss (resale worth more than what was spent) is shown with its sign.
Unknown terms give ``residual_loss = None`` with a reason, never 0, because a
zero reads as "free to stop" and that is the one answer this view must not
invent.

::

    sunk                = paid + invoiced_unpaid + certified_not_invoiced + received_not_invoiced
    committed_not_spent = committed - sunk
    cancellation_charge = schedule entry for D (or progress), else the basis formula
    recoverable         = transfer_value + salvage_value
    residual_loss       = sunk + cancellation_charge - recoverable

Released-but-uncommitted money adds nothing: it is still avoidable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.commitment_release.catalogue import AbortBasis, parse_amount

ZERO = Decimal("0")


@dataclass(frozen=True)
class ScheduleEntry:
    """One step of a supplier's cancellation schedule: from a date or a progress, a charge."""

    milestone: str
    from_date: date | None = None
    progress_pct: Decimal | None = None
    charge_amount: Decimal | None = None
    charge_pct: Decimal | None = None


@dataclass(frozen=True)
class TermsInput:
    """The abort terms of one item or link, as the calculator needs them."""

    basis_code: str | None
    cancellation_schedule: tuple[ScheduleEntry, ...] = ()
    transfer_value: Decimal | None = None
    salvage_value: Decimal | None = None
    saved_cost: Decimal | None = None
    other_charge: Decimal | None = None
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Exposure:
    sunk: Decimal
    committed: Decimal
    committed_not_spent: Decimal
    cancellation_charge: Decimal | None
    recoverable: Decimal
    residual_loss: Decimal | None
    reason: str | None
    method: str | None
    basis_review_status: str | None
    lines: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        def s(v: Decimal | None) -> str | None:
            return None if v is None else str(v)

        return {
            "sunk": s(self.sunk),
            "committed": s(self.committed),
            "committed_not_spent": s(self.committed_not_spent),
            "cancellation_charge": s(self.cancellation_charge),
            "recoverable": s(self.recoverable),
            "residual_loss": s(self.residual_loss),
            "reason": self.reason,
            "method": self.method,
            "basis_review_status": self.basis_review_status,
            "lines": list(self.lines),
        }


def sunk_total(parts: dict[str, Decimal]) -> Decimal:
    keys = ("paid", "invoiced_unpaid", "certified_not_invoiced", "received_not_invoiced")
    return sum((parts.get(k, ZERO) for k in keys), ZERO)


def schedule_charge(
    entries: tuple[ScheduleEntry, ...], *, as_of: date, progress_pct: Decimal | None, committed: Decimal
) -> tuple[Decimal, str | None]:
    """The charge of the latest schedule step reached by date or by progress; 0 before the first."""
    reached: list[ScheduleEntry] = []
    for e in entries:
        if (
            e.from_date is not None
            and e.from_date <= as_of
            or e.progress_pct is not None
            and progress_pct is not None
            and e.progress_pct <= progress_pct
        ):
            reached.append(e)
    if not reached:
        return ZERO, None

    def charge(e: ScheduleEntry) -> Decimal:
        if e.charge_amount is not None:
            return e.charge_amount
        return committed * (e.charge_pct or ZERO)

    best = max(reached, key=charge)
    return charge(best), best.milestone


def _param(basis: AbortBasis, terms: TermsInput, name: str) -> Decimal | None:
    raw = terms.parameters.get(name)
    if raw is None:
        p = basis.parameters.get(name)
        raw = p.value if p is not None else None
    if raw is None:
        return None
    return parse_amount(raw)


def compute_exposure(
    *,
    committed: Decimal,
    sunk_parts: dict[str, Decimal],
    terms: TermsInput | None,
    basis: AbortBasis | None,
    as_of: date,
    progress_pct: Decimal | None = None,
) -> Exposure:
    """Exposure of one item on ``as_of``; see the module docstring for the formula."""
    sunk = sunk_total(sunk_parts)
    lines: list[dict[str, Any]] = [{"code": k, "amount": str(v)} for k, v in sunk_parts.items()]
    not_spent = committed - sunk
    if committed == ZERO and sunk == ZERO:
        # Nothing is bound and nothing was spent: stopping costs nothing, whatever the terms say,
        # and there is nothing to resell either. Salvage of goods never bought is not a gain.
        lines.append({"code": "nothing_committed", "amount": "0"})
        return Exposure(ZERO, ZERO, ZERO, ZERO, ZERO, ZERO, None, None, None, tuple(lines))
    if terms is None or (terms.basis_code is None and not terms.cancellation_schedule):
        return Exposure(sunk, committed, not_spent, None, ZERO, None, "abort_terms_missing", None, None, tuple(lines))
    recoverable = (terms.transfer_value or ZERO) + (terms.salvage_value or ZERO)
    review = str(basis.review_status) if basis is not None else None
    method: str | None
    if terms.cancellation_schedule:
        charge, milestone = schedule_charge(
            terms.cancellation_schedule, as_of=as_of, progress_pct=progress_pct, committed=committed
        )
        method = "schedule"
        lines.append({"code": "schedule_milestone", "milestone": milestone, "amount": str(charge)})
    else:
        if basis is None:
            return Exposure(
                sunk, committed, not_spent, None, recoverable, None, "abort_basis_unknown", None, None, tuple(lines)
            )
        method = basis.method
        charge_or_none = _basis_charge(basis, terms, committed=committed, performed=sunk, lines=lines)
        if charge_or_none is None:
            return Exposure(
                sunk,
                committed,
                not_spent,
                None,
                recoverable,
                None,
                "abort_terms_incomplete",
                method,
                review,
                tuple(lines),
            )
        charge = charge_or_none
    residual = sunk + charge - recoverable
    return Exposure(sunk, committed, not_spent, charge, recoverable, residual, None, method, review, tuple(lines))


def combine_exposures(parts: list[Exposure]) -> Exposure:
    """The exposure of an item whose linked documents carry terms of their own: the parts added up.

    One part with an unknown residual makes the whole unknown, with that part's reason; adding
    only the known parts would show a loss that leaves a document out.
    """
    unknown = next((p for p in parts if p.residual_loss is None), None)
    charges = [p.cancellation_charge for p in parts]
    return Exposure(
        sunk=sum((p.sunk for p in parts), ZERO),
        committed=sum((p.committed for p in parts), ZERO),
        committed_not_spent=sum((p.committed_not_spent for p in parts), ZERO),
        cancellation_charge=None if any(c is None for c in charges) else sum((c for c in charges if c), ZERO),
        recoverable=sum((p.recoverable for p in parts), ZERO),
        residual_loss=None if unknown is not None else sum((p.residual_loss or ZERO for p in parts), ZERO),
        reason=unknown.reason if unknown is not None else None,
        method="combined",
        basis_review_status=next((p.basis_review_status for p in parts if p.basis_review_status), None),
        lines=tuple(line for p in parts for line in p.lines),
    )


def _basis_charge(
    basis: AbortBasis, terms: TermsInput, *, committed: Decimal, performed: Decimal, lines: list[dict[str, Any]]
) -> Decimal | None:
    unperformed = committed - performed
    if basis.method == "free":
        return ZERO
    if basis.method == "custom":
        return terms.other_charge
    if basis.method == "schedule_only":
        # A schedule basis without a schedule says nothing.
        return None
    if basis.method == "price_less_saved_costs":
        if terms.saved_cost is not None:
            lines.append({"code": "unperformed_less_saved", "amount": str(unperformed - terms.saved_cost)})
            return unperformed - terms.saved_cost
        pct = _param(basis, terms, "presumed_unperformed_pct")
        if pct is None:
            return None
        lines.append({"code": "presumed_pct_of_unperformed", "pct": str(pct), "amount": str(unperformed * pct)})
        return unperformed * pct + (terms.other_charge or ZERO)
    if basis.method == "fee_on_unperformed":
        pct = _param(basis, terms, "fee_pct")
        if pct is None:
            return None
        lines.append({"code": "fee_on_unperformed", "pct": str(pct), "amount": str(unperformed * pct)})
        return unperformed * pct + (terms.other_charge or ZERO)
    if basis.method == "profit_on_performed":
        pct = _param(basis, terms, "profit_pct")
        if pct is None:
            return None
        lines.append({"code": "profit_on_performed", "pct": str(pct), "amount": str(performed * pct)})
        return performed * pct + (terms.other_charge or ZERO)
    return None
