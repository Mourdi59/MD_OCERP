# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""One commercial change must move a contract's value exactly once.

Promoting a variation request mirrors the resulting variation order into
``oe_changeorders`` as a draft change order
(``VariationsService.convert_vr_to_vo``). Two independent wave-5
subscribers can then add money to the same contract: one on variation
order completion, one on change order approval. Each deduplicates only
against its own metadata bucket, so nothing stops the mirrored pair from
posting the same amount twice.

Reachability is the whole point of this file, so it is asserted rather
than assumed:

* the mirror as created carries no ``metadata.contract_id``, so the
  change order subscriber returns before it opens a session - the plain
  promote / complete / approve flow posts once;
* the mirror is a *draft*, and ``ChangeOrderUpdate`` accepts ``metadata``
  which ``update_order`` merges, so linking it to the very contract the
  variation order already names is one PATCH away - and that is the pair
  that used to post twice.

The events are recorded from the real publishers and handed to the real
handlers, so the payloads under test are the ones the services actually
emit. Driving the handlers directly keeps the assertions free of the
detached-publish race; ``test_subscribers_are_registered`` asserts the
wiring that production relies on to call them.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.modules.notifications._wave5_cross_module_subscribers as w5
from app.core.events import Event, event_bus
from app.modules.changeorders.models import ChangeOrder
from app.modules.changeorders.schemas import ChangeOrderCreate, ChangeOrderUpdate
from app.modules.changeorders.service import ChangeOrderService
from app.modules.contracts.models import Contract
from app.modules.projects.models import Project
from app.modules.users.models import User
from app.modules.variations.models import VariationOrder
from app.modules.variations.schemas import VariationOrderCreate, VariationRequestCreate
from app.modules.variations.service import VariationsService
from tests._pg import isolated_engine

BASE_VALUE = Decimal("100000")
VO_AMOUNT = Decimal("25000")

VO_COMPLETED_EVENT = "variations.contract_sum.updated"
CO_APPROVED_EVENT = "changeorder.approved"


class _Harness:
    """A throwaway database plus the events the services published into it."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self.factory = factory
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.project_id: uuid.UUID
        self.contract_id: uuid.UUID

    def last_event(self, name: str) -> dict[str, Any]:
        for published_name, data in reversed(self.published):
            if published_name == name:
                return data
        raise AssertionError(f"no {name!r} was published; saw {[n for n, _ in self.published]}")

    async def contract_state(self) -> tuple[Decimal, dict[str, Any]]:
        """Re-read the contract in a fresh session (the handlers commit their own)."""
        async with self.factory() as session:
            contract = await session.get(Contract, self.contract_id)
            assert contract is not None
            return Decimal(str(contract.total_value)), dict(contract.metadata_ or {})

    async def deliver(self, name: str) -> None:
        """Hand the last published *name* payload to its wave-5 handler."""
        handler = dict(w5._SUBSCRIPTIONS)[name]
        await handler(Event(name=name, data=self.last_event(name)))  # type: ignore[operator]


@pytest_asyncio.fixture
async def harness(monkeypatch: pytest.MonkeyPatch):
    async with isolated_engine() as engine:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        # The wave-5 handlers open their own isolated session by design; point
        # it at the same throwaway database so they read and write the rows the
        # test just committed.
        monkeypatch.setattr(w5, "async_session_factory", factory)

        h = _Harness(factory)
        monkeypatch.setattr(
            event_bus,
            "publish_detached",
            lambda name, data=None, source_module=None: h.published.append((name, dict(data or {}))),
        )

        async with factory() as session:
            user = User(
                email=f"vm-{uuid.uuid4().hex[:8]}@example.com",
                hashed_password="x",
                full_name="Variation mirror",
                role="admin",
            )
            session.add(user)
            await session.flush()
            project = Project(name=f"VM {uuid.uuid4().hex[:6]}", owner_id=user.id, currency="EUR")
            session.add(project)
            await session.flush()
            contract = Contract(
                code=f"CT-{uuid.uuid4().hex[:8]}",
                title="Main works",
                project_id=project.id,
                status="active",
                currency="EUR",
                total_value=BASE_VALUE,
            )
            session.add(contract)
            await session.commit()
            h.project_id = project.id
            h.contract_id = contract.id
            yield h


async def _promote(
    session: AsyncSession,
    harness: _Harness,
    *,
    amount: Decimal = VO_AMOUNT,
    link_contract: bool = True,
) -> tuple[VariationOrder, ChangeOrder]:
    """Run a variation request through approval into a VO plus its mirrored CO."""
    service = VariationsService(session)
    vr = await service.create_request(
        VariationRequestCreate(
            project_id=harness.project_id,
            title="Additional piling",
            estimated_cost_impact=amount,
            currency="EUR",
        )
    )
    await service.transition_variation_request(vr.id, "submitted")
    await service.transition_variation_request(vr.id, "approved")
    vo = await service.convert_vr_to_vo(
        vr.id,
        VariationOrderCreate(
            project_id=harness.project_id,
            title="Additional piling",
            final_cost_impact=amount,
            currency="EUR",
            affected_contract_id=harness.contract_id if link_contract else None,
        ),
    )
    await session.commit()
    mirror = await session.get(ChangeOrder, vo.reference_change_order_id)
    assert mirror is not None, "the promotion must mirror the VO into a change order"
    return vo, mirror


async def _complete(session: AsyncSession, harness: _Harness, vo: VariationOrder) -> None:
    """Drive the VO to completed and let the variation subscriber post its money."""
    service = VariationsService(session)
    await service.transition_variation_order(vo.id, "in_progress")
    await service.transition_variation_order(vo.id, "completed")
    await session.commit()
    await harness.deliver(VO_COMPLETED_EVENT)


async def _approve(session: AsyncSession, harness: _Harness, order: ChangeOrder) -> None:
    """Drive a CO through submit + approve and let the CO subscriber run."""
    service = ChangeOrderService(session)
    await service.submit_order(order.id, user_id=str(uuid.uuid4()))
    await service.approve_order(order.id, user_id=str(uuid.uuid4()))
    await session.commit()
    await harness.deliver(CO_APPROVED_EVENT)


async def _link_to_contract(session: AsyncSession, harness: _Harness, order: ChangeOrder) -> None:
    """Stamp ``metadata.contract_id`` on a draft CO, as the create/edit form does."""
    service = ChangeOrderService(session)
    await service.update_order(
        order.id,
        ChangeOrderUpdate(metadata={"contract_id": str(harness.contract_id)}),
    )
    await session.commit()


@pytest.mark.asyncio
async def test_mirror_carries_the_variation_link_and_no_contract_link(harness: _Harness) -> None:
    """The mirror knows which VO it came from, and names no contract.

    Both halves matter: the variation link is what the dedup keys on, and
    the absent contract link is why the plain flow never double-posts.
    """
    async with harness.factory() as session:
        vo, mirror = await _promote(session, harness)

    assert mirror.metadata_["origin"] == "variations.convert_vr_to_vo"
    assert mirror.metadata_["variation_order_id"] == str(vo.id)
    assert "contract_id" not in mirror.metadata_
    assert mirror.status == "draft"
    assert Decimal(str(mirror.cost_impact)) == VO_AMOUNT


@pytest.mark.asyncio
async def test_plain_promotion_posts_the_money_once(harness: _Harness) -> None:
    """Promote, complete, approve the mirror: the contract moves by one VO."""
    async with harness.factory() as session:
        vo, mirror = await _promote(session, harness)
        await _complete(session, harness, vo)
        await _approve(session, harness, mirror)

    total, md = await harness.contract_state()
    assert harness.last_event(CO_APPROVED_EVENT)["contract_id"] is None
    assert total == BASE_VALUE + VO_AMOUNT
    assert md["variation_ids"] == [str(vo.id)]
    assert Decimal(md["variation_total"]) == VO_AMOUNT
    # The change order path never ran - it has no contract to post against.
    assert "change_order_ids" not in md
    assert "change_order_total" not in md


@pytest.mark.asyncio
async def test_linked_mirror_posts_the_money_once(harness: _Harness) -> None:
    """The regression gate: linking the mirror to the same contract is not a second change.

    A PATCH stamping ``metadata.contract_id`` on the draft mirror is all it
    takes to put both subscribers on the same contract. The variation order
    has already posted its amount, so approving its mirror must not post it
    again.
    """
    async with harness.factory() as session:
        vo, mirror = await _promote(session, harness)
        await _link_to_contract(session, harness, mirror)
        await _complete(session, harness, vo)
        await _approve(session, harness, mirror)

    total, md = await harness.contract_state()
    assert harness.last_event(CO_APPROVED_EVENT)["contract_id"] == str(harness.contract_id)
    assert total == BASE_VALUE + VO_AMOUNT
    assert md["variation_ids"] == [str(vo.id)]
    assert Decimal(md["variation_total"]) == VO_AMOUNT
    # Skipped, not applied: the money is already on the contract via the VO.
    assert "change_order_total" not in md
    skipped = md["skipped_variation_mirror"]
    assert len(skipped) == 1
    assert skipped[0]["change_order_id"] == str(mirror.id)
    assert skipped[0]["variation_order_id"] == str(vo.id)
    # Money as Decimal, never as a string: the CO renders its impact to 2 dp.
    assert Decimal(skipped[0]["cost_impact"]) == VO_AMOUNT
    # The rollup counts change_order_ids, so a skipped post must stay out of it.
    assert "change_order_ids" not in md


@pytest.mark.asyncio
async def test_independent_change_order_still_posts(harness: _Harness) -> None:
    """A CO a user raised on the same contract is not a mirror and must post."""
    amount = Decimal("4200.50")
    async with harness.factory() as session:
        vo, mirror = await _promote(session, harness)
        await _complete(session, harness, vo)

        service = ChangeOrderService(session)
        independent = await service.create_order(
            ChangeOrderCreate(
                project_id=harness.project_id,
                title="Rock excavation",
                currency="EUR",
                cost_impact=str(amount),
                metadata={"contract_id": str(harness.contract_id)},
            )
        )
        await session.commit()
        await _approve(session, harness, independent)

    total, md = await harness.contract_state()
    assert total == BASE_VALUE + VO_AMOUNT + amount
    assert md["change_order_ids"] == [str(independent.id)]
    assert Decimal(md["change_order_total"]) == amount
    assert "skipped_variation_mirror" not in md
    assert mirror.status == "draft"


@pytest.mark.asyncio
async def test_mirror_of_an_unlinked_variation_order_still_posts(harness: _Harness) -> None:
    """A mirror is only silenced when its VO posted the money.

    When the VO names no contract the variation path never posts, so the
    mirrored CO is the only route to the contract and must take it.
    """
    async with harness.factory() as session:
        vo, mirror = await _promote(session, harness, link_contract=False)
        await _link_to_contract(session, harness, mirror)
        await _approve(session, harness, mirror)

    total, md = await harness.contract_state()
    assert total == BASE_VALUE + VO_AMOUNT
    assert md["change_order_ids"] == [str(mirror.id)]
    assert Decimal(md["change_order_total"]) == VO_AMOUNT
    assert "variation_ids" not in md
    assert vo.affected_contract_id is None


def test_subscribers_are_registered() -> None:
    """Both money paths are wired, which is what makes the pair reachable."""
    assert (VO_COMPLETED_EVENT, w5._on_variation_completed) in w5._SUBSCRIPTIONS
    assert (CO_APPROVED_EVENT, w5._on_changeorder_approved_contract) in w5._SUBSCRIPTIONS
