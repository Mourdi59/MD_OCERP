# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The matrix's own currency conversion (SPEC rule 13, lead decision f).

Never ``costmodel._amount_in_base``: that keeps a foreign amount in its own
units when a rate is missing, which blends at 1:1. An authority check on a
blended amount is wrong, so here a missing rate raises :class:`FxRateMissing`.

Order (decision f): the fx module's dated rate sets when one covers the date;
otherwise the project's own ``fx_rates`` (units of base per 1 foreign unit,
crossed through the base when neither side is the base); otherwise refuse.
The quote carries its source so every converted figure can show it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from app.modules.commitment_release.catalogue import parse_amount

SOURCE_SAME = "same_currency"
SOURCE_RATE_SET = "fx_rate_set"
SOURCE_PROJECT = "project_rates"


class FxRateMissing(Exception):
    """No rate for ``from_currency -> to_currency`` on ``on_date`` under the matrix policy."""

    def __init__(self, from_currency: str, to_currency: str, on_date: date | None) -> None:
        super().__init__(f"no rate {from_currency}->{to_currency} on {on_date}")
        self.from_currency = from_currency
        self.to_currency = to_currency
        self.on_date = on_date


@dataclass(frozen=True)
class FxQuote:
    """``rate`` = units of ``to_currency`` per 1 unit of ``from_currency``."""

    from_currency: str
    to_currency: str
    rate: Decimal
    as_of: date | None
    source: str
    rate_set_id: str | None = None

    def apply(self, amount: Decimal) -> Decimal:
        return amount * self.rate

    def as_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_currency,
            "to": self.to_currency,
            "rate": str(self.rate),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "source": self.source,
            "rate_set_id": self.rate_set_id,
        }


def norm(code: str | None) -> str:
    return (code or "").strip().upper()


def project_rates_quote(
    from_currency: str, to_currency: str, base: str, rates: dict[str, str], on_date: date | None
) -> FxQuote | None:
    """A quote from the project's ``fx_rates``, crossed through the base; ``None`` when a leg is missing."""
    f, t, b = norm(from_currency), norm(to_currency), norm(base)
    if not b:
        return None

    def to_base(code: str) -> Decimal | None:
        if code == b:
            return Decimal("1")
        raw = rates.get(code)
        if raw is None:
            return None
        try:
            value = parse_amount(raw)
        except ValueError:
            return None
        return value if value > 0 else None

    rf, rt = to_base(f), to_base(t)
    if rf is None or rt is None:
        return None
    return FxQuote(f, t, rf / rt, on_date, SOURCE_PROJECT)


def same_currency_quote(code: str, on_date: date | None) -> FxQuote:
    return FxQuote(norm(code), norm(code), Decimal("1"), on_date, SOURCE_SAME)


async def resolve_quote(
    session: Any,
    *,
    from_currency: str,
    to_currency: str,
    on_date: date,
    project_id: uuid.UUID,
    base: str,
    project_rates: dict[str, str],
    policy: str = "fx_service_rate_set",
) -> FxQuote:
    """The rate the matrix applies, by policy; :class:`FxRateMissing` when there is none.

    ``fx_service_rate_set`` (default): a dated rate set from the fx module when
    it covers ``on_date``, else project rates. ``project_rates``: project rates only.
    """
    f, t = norm(from_currency), norm(to_currency)
    if not f or not t:
        raise FxRateMissing(f, t, on_date)
    if f == t:
        return same_currency_quote(f, on_date)
    if policy == "fx_service_rate_set":
        quote = await _rate_set_quote(session, f, t, on_date, project_id)
        if quote is not None:
            return quote
    quote = project_rates_quote(f, t, base, project_rates, on_date)
    if quote is None:
        raise FxRateMissing(f, t, on_date)
    return quote


async def _rate_set_quote(session: Any, f: str, t: str, on_date: date, project_id: uuid.UUID) -> FxQuote | None:
    try:
        from app.modules.fx.service import FxService

        async with session.begin_nested():
            res = await FxService(session).convert("1", f, t, on_date=on_date, project_id=project_id)
    except Exception:
        return None
    if not res.get("available", True) or not res.get("covers_requested_date"):
        return None
    try:
        rate = parse_amount(res.get("rate"))
    except ValueError:
        return None
    if rate <= 0:
        return None
    as_of = res.get("as_of")
    as_of_day = as_of if isinstance(as_of, date) else (date.fromisoformat(str(as_of)[:10]) if as_of else on_date)
    return FxQuote(f, t, rate, as_of_day, SOURCE_RATE_SET, res.get("rate_set_id"))
