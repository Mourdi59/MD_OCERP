# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure arithmetic of the business case, the cost frame and the financing plan.

Decimal end to end, no I/O. Nothing is rounded on the way: money keeps the
precision it came in with and only the ratios the screen shows are quantised by
the caller. The one exception is spreading a total over years, which splits at
four places and puts the remainder on the last year so the years add up to the
total exactly.

Sign convention of the cash flow: an investment and an operating cost are
outflows (negative), a revenue and a residual value are inflows (positive).
Lines are entered as positive amounts and the kind decides the sign.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext

from app.modules.economics.classification import most_specific

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_SPREAD = Decimal("0.0001")

KINDS = ("investment", "revenue", "operating_cost", "residual")
MODES = ("total", "per_year")
_OUT = ("investment", "operating_cost")


@dataclass(frozen=True)
class FlowLine:
    """One line of the business case with its amount already resolved (a cost frame link read)."""

    kind: str
    mode: str
    amount: Decimal
    year_from: int
    year_to: int
    escalation_pct: Decimal = ZERO


def yearly(line: FlowLine) -> dict[int, Decimal]:
    """The line's positive amount per year.

    ``total`` spreads the amount evenly over ``year_from..year_to`` (the
    remainder on the last year); ``per_year`` repeats it, compounding the
    escalation from the first year.
    """
    if line.year_to < line.year_from:
        return {}
    years = list(range(line.year_from, line.year_to + 1))
    if line.mode == "total":
        share = (line.amount / len(years)).quantize(_SPREAD, rounding=ROUND_HALF_UP)
        out = dict.fromkeys(years, share)
        out[years[-1]] = line.amount - share * (len(years) - 1)
        return out
    out: dict[int, Decimal] = {}
    factor = Decimal(1) + line.escalation_pct / HUNDRED
    with localcontext() as ctx:
        ctx.prec = 40
        for index, year in enumerate(years):
            out[year] = line.amount * factor**index
    return out


def cash_flows(lines: Iterable[FlowLine], horizon: int) -> list[Decimal]:
    """Net cash flow per year ``0..horizon``. Money outside the horizon is ignored, the rules flag it."""
    flows = [ZERO] * (horizon + 1)
    for line in lines:
        sign = -1 if line.kind in _OUT else 1
        for year, amount in yearly(line).items():
            if 0 <= year <= horizon:
                flows[year] += sign * amount
    return flows


def _discount_factor(rate: Decimal, year: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 40
        return (Decimal(1) + rate) ** year


def npv(flows: Sequence[Decimal], rate_pct: Decimal) -> Decimal:
    """Net present value of ``flows`` (year 0 undiscounted) at ``rate_pct`` percent."""
    rate = rate_pct / HUNDRED
    with localcontext() as ctx:
        ctx.prec = 40
        return sum((flow / _discount_factor(rate, year) for year, flow in enumerate(flows)), ZERO)


def irr(flows: Sequence[Decimal]) -> Decimal | None:
    """Internal rate of return in percent, or ``None`` when the flows never change sign.

    Bisection on the NPV between -99 percent and 1000 percent. Returns ``None``
    too when the root is not bracketed (more than one sign change that cancels).
    """
    if not any(f > 0 for f in flows) or not any(f < 0 for f in flows):
        return None
    low, high = Decimal("-0.99"), Decimal("10")
    f_low, f_high = npv(flows, low * HUNDRED), npv(flows, high * HUNDRED)
    if f_low == 0:
        return (low * HUNDRED).quantize(Decimal("0.01"))
    if f_low * f_high > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        f_mid = npv(flows, mid * HUNDRED)
        if f_mid == 0 or (high - low) < Decimal("0.0000001"):
            low = high = mid
            break
        if f_low * f_mid < 0:
            high = mid
        else:
            low, f_low = mid, f_mid
    return (((low + high) / 2) * HUNDRED).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def payback_year(flows: Sequence[Decimal]) -> int | None:
    """The first year whose cumulative net flow is not negative, after the investment was made."""
    total = ZERO
    spent = False
    for year, flow in enumerate(flows):
        total += flow
        if flow < 0:
            spent = True
        if spent and total >= 0:
            return year
    return None


def key_figures(lines: Sequence[FlowLine], horizon: int, rate_pct: Decimal | None) -> dict[str, Decimal | int | None]:
    """The figures the approval is read on. ``None`` marks a figure that cannot be computed, never zero."""
    flows = cash_flows(lines, horizon)

    def total(*kinds: str) -> Decimal:
        return sum((sum(yearly(ln).values(), ZERO) for ln in lines if ln.kind in kinds), ZERO)

    investment, revenue, opex, residual = (total(k) for k in KINDS)
    pv_in = pv_out = ZERO
    if rate_pct is not None:
        rate = rate_pct / HUNDRED
        for line in lines:
            for year, amount in yearly(line).items():
                if 0 <= year <= horizon:
                    value = amount / _discount_factor(rate, year)
                    if line.kind in _OUT:
                        pv_out += value
                    else:
                        pv_in += value
    stable_year = horizon
    noi = sum(
        (
            amount if ln.kind == "revenue" else -amount
            for ln in lines
            if ln.kind in ("revenue", "operating_cost")
            for year, amount in yearly(ln).items()
            if year == stable_year
        ),
        ZERO,
    )
    return {
        "total_investment": investment,
        "total_revenue": revenue,
        "total_operating_cost": opex,
        "residual_value": residual,
        "net_cash_flow": sum(flows, ZERO),
        "npv": npv(flows, rate_pct) if rate_pct is not None else None,
        "irr_pct": irr(flows),
        "payback_year": payback_year(flows),
        "benefit_cost_ratio": (pv_in / pv_out) if rate_pct is not None and pv_out > 0 else None,
        "yield_on_cost_pct": (noi / investment * HUNDRED) if investment > 0 else None,
    }


# ── cost frame ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Reading:
    """An amount of the bill or of the commitments with the classification code it sits under."""

    code: str | None
    amount: Decimal


def assign(frame_codes: Sequence[str], readings: Iterable[Reading]) -> tuple[dict[str, Decimal], Decimal, int]:
    """Sum readings onto the most specific frame line covering them.

    Returns ``(per frame code, unassigned amount, unassigned count)``. A reading without a
    code, or whose code no frame line covers, is unassigned and is never dropped.
    """
    per = dict.fromkeys(frame_codes, ZERO)
    loose, count = ZERO, 0
    for r in readings:
        home = most_specific(list(frame_codes), r.code) if r.code else None
        if home is None:
            loose += r.amount
            count += 1
        else:
            per[home] += r.amount
    return per, loose, count


def pct_of(part: Decimal, whole: Decimal) -> Decimal | None:
    """``part`` as a percentage of ``whole``; ``None`` when the whole is zero."""
    return part / whole * HUNDRED if whole != 0 else None


# ── financing ───────────────────────────────────────────────────────────────


def coverage(requirement: Decimal, sources: Sequence[Decimal]) -> dict[str, Decimal | bool | None]:
    """How much of the funding requirement the sources cover.

    ``shortfall`` is the uncovered part (zero when covered), ``surplus`` the part of the sources
    above the requirement. Both are kept apart and never netted into one signed number.
    """
    total = sum(sources, ZERO)
    shortfall = max(requirement - total, ZERO)
    return {
        "requirement": requirement,
        "sources_total": total,
        "shortfall": shortfall,
        "surplus": max(total - requirement, ZERO),
        "covered": shortfall == 0 and requirement > 0,
        "coverage_pct": pct_of(total, requirement),
    }
