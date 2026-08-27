# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The EVM snapshot written on schedule progress uses the project's currency.

``_handle_schedule_progress`` is the second write path onto
``oe_finance_evm_snapshot``. It fires on ``schedule.progress_updated``, derives
BAC / PV / EV / AC / SV / CV and persists them. Every one of the six was
quantised to ``Decimal("0.01")`` regardless of the project currency, so a
Kuwaiti dinar reached the table with its third digit already gone and a yen
with two decimals nothing in Japan can settle. These rows are what the
forecast surfaces read, so the defect propagated rather than staying local.

The whole handler body sits inside ``try/except Exception`` with a
``logger.exception``, which means a failure in it is silent: no snapshot is
written and nothing is raised. That is also why the first assertion of every
test here is that a snapshot was produced at all. A currency lookup added to a
path like this has to be shown not to have swallowed the write.

The handler opens its own session through ``app.database.async_session_factory``
rather than receiving one, so the factory is what the tests replace. The stub
answers each statement by the entity it selects rather than by call order, so
adding or reordering a query upstream does not silently feed the wrong rows to
the wrong reader.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.core.events import Event
from app.core.money import money_quantum

_MONEY_FIELDS = ("bac", "pv", "ev", "ac", "sv", "cv")
_INDEX_FIELDS = ("spi", "cpi")


class _Result:
    """The slice of a SQLAlchemy ``Result`` this handler actually calls."""

    def __init__(self, rows: list[Any] | None = None, scalar: Any = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._rows

    def scalar(self) -> Any:
        return self._scalar

    def scalar_one_or_none(self) -> Any:
        return self._scalar


class _StubSession:
    """Answers the handler's four statements and records what it was given."""

    def __init__(self, budgets: list[Any], invoices: list[Any], currency: str | None) -> None:
        self._budgets = budgets
        self._invoices = invoices
        self._currency = currency
        self.added: list[Any] = []
        self.committed = False

    async def execute(self, statement: Any) -> _Result:
        from app.modules.finance.models import Invoice, ProjectBudget
        from app.modules.projects.models import Project

        entities = {d.get("entity") for d in statement.column_descriptions}
        if ProjectBudget in entities:
            return _Result(rows=self._budgets)
        if Invoice in entities:
            return _Result(rows=self._invoices)
        if Project in entities:
            return _Result(scalar=self._currency)
        # The coalesce/sum probe the handler issues and then discards.
        return _Result(scalar=0)

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def __aenter__(self) -> _StubSession:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


def _budget(amount: str) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(original_budget=amount)


def _invoice(amount: str) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(amount_total=amount)


async def _snapshot_for(monkeypatch: pytest.MonkeyPatch, currency: str | None) -> Any:
    """Fire the handler for a project in ``currency`` and return the row it added.

    BAC 1000000 at 47.5% progress against 52.5% elapsed gives PV, EV, SV and CV
    a fractional tail in every currency, which is what makes the quantum
    observable rather than hidden behind a round number.
    """
    import app.database as database_module
    from app.core.event_handlers import _handle_schedule_progress

    session = _StubSession(
        budgets=[_budget("1000000")],
        invoices=[_invoice("480000.005")],
        currency=currency,
    )
    monkeypatch.setattr(database_module, "async_session_factory", lambda: session)

    await _handle_schedule_progress(
        Event(
            name="schedule.progress_updated",
            data={
                "project_id": str(uuid.uuid4()),
                "progress_pct": 47.5,
                "time_elapsed_pct": 52.5,
            },
        )
    )

    assert session.added, "the handler wrote no snapshot at all, the currency lookup swallowed the write"
    assert session.committed, "the snapshot was never committed"
    return session.added[0]


def _places(text: str) -> int:
    return -Decimal(text).as_tuple().exponent


@pytest.mark.asyncio
async def test_a_three_decimal_currency_keeps_its_fils(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dinar is subdivided into 1000 fils and the row must carry all three."""
    snapshot = await _snapshot_for(monkeypatch, "KWD")

    for field in _MONEY_FIELDS:
        stored = getattr(snapshot, field)
        assert _places(stored) == 3, f"{field} stored as {stored!r}, a dinar carries three"


@pytest.mark.asyncio
async def test_a_zero_decimal_currency_is_not_stored_with_decimals(monkeypatch: pytest.MonkeyPatch) -> None:
    """A yen has no subunit, so a persisted yen amount must not claim one."""
    snapshot = await _snapshot_for(monkeypatch, "JPY")

    for field in _MONEY_FIELDS:
        stored = getattr(snapshot, field)
        assert _places(stored) == 0, f"{field} stored as {stored!r}, a yen has no subunit"


@pytest.mark.asyncio
async def test_every_money_field_matches_the_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """The written precision is whatever ``money_quantum`` says, not a literal.

    Asserting against the resolver rather than a pinned string is the point:
    the value layer has exactly one table of decimals, and this row is expected
    to agree with it for any currency it holds tomorrow as well.
    """
    for code in ("JPY", "KWD", "EUR", "CLP", "HUF", "IDR"):
        snapshot = await _snapshot_for(monkeypatch, code)
        want = -money_quantum(code).as_tuple().exponent
        for field in _MONEY_FIELDS:
            stored = getattr(snapshot, field)
            assert _places(stored) == want, f"{code}: {field} is {stored!r}, the resolver says {want} places"


@pytest.mark.asyncio
async def test_the_indices_keep_their_four_places(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPI and CPI are dimensionless ratios and no currency applies to them.

    This one passes both before and after on purpose. It pins the half of the
    handler that must not move: rounding a ratio to a currency's subdivision
    would turn a Japanese CPI into an integer and destroy the signal.
    """
    snapshot = await _snapshot_for(monkeypatch, "JPY")

    for field in _INDEX_FIELDS:
        stored = getattr(snapshot, field)
        assert _places(stored) == 4, f"{field} is {stored!r}, an index is not money"


@pytest.mark.asyncio
async def test_a_project_without_a_currency_still_gets_two_decimals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing to resolve means nothing is invented.

    Two places is what this handler always wrote, and it stays the answer when
    the project row carries no code. Guessing one would be worse than
    declining to: a mislabelled amount reads as authoritative.
    """
    snapshot = await _snapshot_for(monkeypatch, None)

    for field in _MONEY_FIELDS:
        assert _places(getattr(snapshot, field)) == 2
