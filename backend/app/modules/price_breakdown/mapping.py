# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Map a stored BoQ position onto a :class:`PriceBreakdown`.

The platform already stores a per-position resource split under
``Position.metadata_["resources"]`` (a list of ``{type, name, unit, quantity,
unit_rate, total, currency}``), written both when a position is edited and when
an assembly is applied. This turns that split, plus the BoQ overhead/profit
markups, into the formal per-position price analysis. No new storage: it reads
what is already there.

Every resource quantity is a PER-UNIT norm: the amount one unit of the position
consumes, so ``position.unit_rate == sum(r.quantity * r.unit_rate)`` and the
whole-position demand is that product times ``position.quantity``. That is the
platform invariant, stated in :mod:`app.modules.resource_summary.aggregate` and
implemented by both writers that produce a split - the resource-driven rate
derivation in :mod:`app.modules.boq.service` and the assembly apply path, which
keeps the per-unit norm as the raw component quantity. ``r["total"]`` is written
as ``quantity * unit_rate`` and is per-unit for the same reason.

This module used to divide every amount by the position quantity, on the belief
that a second convention existed in which resource amounts were whole-position
figures. No writer produces those. The division left the sheet correct only for
positions of quantity 1 and understated every other one by a factor of its own
quantity, while still reconciling against itself, which is why nothing caught
it: a 250 m3 position at 100.00 per m3 printed 0.008 h of mason, a direct cost
of 0.40 and a position total of 100.00 instead of 25 000.00. This is a German
public-procurement sheet with a download, so those figures left the building.

If a position carries no resource split, the whole unit rate is shown as a single
"other" line so the analysis still renders.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.modules.price_breakdown.model import PriceBreakdown, build_breakdown


def _dec(value: Any, default: str = "0") -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal(default)
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        return Decimal(default)


def _markup_pct(markups: list[dict] | None, category: str) -> Decimal:
    """Sum the percentage markups of a given category (overhead/profit)."""
    total = Decimal("0")
    for m in markups or []:
        if str(m.get("category") or "").strip().lower() != category:
            continue
        if str(m.get("markup_type") or "percentage").strip().lower() != "percentage":
            continue
        total += _dec(m.get("percentage"))
    return total


def from_position(
    position: dict[str, Any],
    *,
    markups: list[dict] | None = None,
    overhead_pct: Any = None,
    profit_pct: Any = None,
    currency: str | None = None,
) -> PriceBreakdown:
    """Build a price analysis from a BoQ position dict.

    Resource quantities and amounts are read as the per-unit norms they are
    stored as, so nothing here is divided by the position quantity. There is no
    ``basis`` switch: the platform has one convention, and offering a second
    would invite a reader to reach for a reading no writer produces.

    Args:
        position: A BoQ position as a dict, carrying at least ``quantity``,
            ``unit_rate`` and its ``metadata_`` (or ``metadata``) mapping.
        markups: BoQ markup rows, used when ``overhead_pct`` / ``profit_pct``
            are not given explicitly.
        overhead_pct: Overhead percentage; wins over ``markups``.
        profit_pct: Profit percentage; wins over ``markups``.
        currency: ISO 4217 code; falls back to the position, then the first
            resource, then ``"EUR"``.

    Returns:
        The assembled :class:`PriceBreakdown` for one unit of the position.
    """
    meta = position.get("metadata_") or position.get("metadata") or {}
    resources = meta.get("resources") or []
    qty = _dec(position.get("quantity"), "1")
    cur = currency or position.get("currency") or (resources[0].get("currency") if resources else None) or "EUR"

    components: list[dict] = []
    for r in resources:
        # ``total`` is this resource's contribution to ONE unit of the position,
        # written as ``quantity * unit_rate`` by every writer that stores it.
        # Recomputed when the row carries no ``total`` at all - the flagship
        # seeder writes leaves without one.
        per_unit = _dec(r.get("total"))
        if not per_unit:
            per_unit = _dec(r.get("quantity"), "1") * _dec(r.get("unit_rate"))
        components.append(
            {
                "kind": r.get("type") or r.get("resource_type"),
                "description": r.get("name") or r.get("description") or "-",
                "unit": r.get("unit") or "",
                "quantity": _dec(r.get("quantity"), "1"),
                "unit_cost": _dec(r.get("unit_rate")),
                "amount": per_unit,
            }
        )

    if not components:
        # No stored split: show the whole unit rate as one line so the sheet
        # is never empty and still reconciles to the position total.
        components.append(
            {
                "kind": "other",
                "description": position.get("description") or "Unit rate",
                "unit": position.get("unit") or "",
                "quantity": Decimal("1"),
                "unit_cost": _dec(position.get("unit_rate")),
                "amount": _dec(position.get("unit_rate")),
            }
        )

    oh = _dec(overhead_pct) if overhead_pct is not None else _markup_pct(markups, "overhead")
    pr = _dec(profit_pct) if profit_pct is not None else _markup_pct(markups, "profit")

    return build_breakdown(
        position_ref=str(position.get("ordinal") or position.get("reference_code") or ""),
        description=str(position.get("description") or ""),
        unit=str(position.get("unit") or ""),
        position_quantity=qty,
        components=components,
        overhead_pct=oh,
        profit_pct=pr,
        risk_pct=_dec(meta.get("risk_pct")),
        currency=str(cur or "EUR"),
    )
