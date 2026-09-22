# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The G702 asks the owner for what the claim is owed, in ordinary workflows.

A money review ran real claims through the service and the endpoints and
found the certificate and the claim disagreeing in four everyday cases. The
certificate is the document the owner pays from, so each of them is money.

* A claim that bills some of the schedule of values and not the rest. The
  continuation sheet carried only the lines this claim billed, so the work
  earlier claims had already billed on the other lines vanished from line 4,
  line 8 printed zero, and the claim's own net due said something else.
* A claim's period moved after it was certified, which rewrites what every
  later claim counts as previously certified.
* A claim with no period end, which used to sort after every dated claim and
  so was invisible to the claim that followed it.
* An earlier claim regenerated after a later one exists, which leaves the
  later one's column D and previous certificates describing a world that no
  longer exists, with nothing on screen to say so.

One invariant is asserted in every scenario here: G702 line 8 is the claim's
net due. If those two disagree, one of them is asking the owner for the wrong
amount, and the sheet cannot say which.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException

from app.modules.contracts.models import Contract, ContractLine, ProgressClaim
from app.modules.contracts.router import delete_claim_line
from app.modules.contracts.schemas import AutoGenerateClaimRequest, ProgressClaimUpdate
from app.modules.contracts.service import ContractsService
from app.modules.contracts.validators import register_contracts_validation_rules
from app.modules.projects.models import Project
from app.modules.users.models import User
from tests._pg import transactional_session

pytestmark = pytest.mark.asyncio

OWNER_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def session():
    register_contracts_validation_rules()
    async with transactional_session() as s:
        s.add(User(id=OWNER_ID, email=f"cert-{uuid.uuid4().hex[:8]}@test.io", hashed_password="x"))
        await s.flush()
        yield s


@pytest_asyncio.fixture
async def world(session):
    project = Project(id=uuid.uuid4(), name="Certificate", owner_id=OWNER_ID, currency="USD", country_code="US")
    session.add(project)
    await session.flush()
    contract = Contract(
        id=uuid.uuid4(),
        code=f"C-{uuid.uuid4().hex[:8]}",
        title="Main works",
        project_id=project.id,
        contract_type="lump_sum",
        currency="USD",
        total_value=Decimal("100000"),
        original_contract_value=Decimal("100000"),
        retention_percent=Decimal("10"),
        status="active",
    )
    session.add(contract)
    await session.flush()
    lines = []
    for index, (code, value) in enumerate([("A", "60000"), ("B", "40000")]):
        line = ContractLine(
            id=uuid.uuid4(),
            contract_id=contract.id,
            code=code,
            description=f"Line {code}",
            quantity=Decimal("1"),
            unit_rate=Decimal(value),
            total_value=Decimal(value),
            order_index=index,
        )
        session.add(line)
        lines.append(line)
    await session.flush()
    return SimpleNamespace(project=project, contract=contract, a=lines[0], b=lines[1])


async def _claim(session, world, number: str, month: int | None, *, created: datetime | None = None) -> ProgressClaim:
    dates: dict = {}
    if month is not None:
        dates = {
            "period_start": f"2026-{month:02d}-01",
            "period_end": f"2026-{month:02d}-28",
            "period_from": date(2026, month, 1),
            "period_to": date(2026, month, 28),
        }
    claim = ProgressClaim(
        id=uuid.uuid4(),
        contract_id=world.contract.id,
        claim_number=number,
        currency="USD",
        status="draft",
        **dates,
    )
    if created is not None:
        claim.created_at = created
    session.add(claim)
    await session.flush()
    return claim


async def _generate(svc: ContractsService, world, claim: ProgressClaim, **completion: str) -> ProgressClaim:
    ids = {"a": str(world.a.id), "b": str(world.b.id)}
    return await svc.auto_generate_claim_lines(
        claim.id,
        AutoGenerateClaimRequest(completion={ids[key]: Decimal(value) for key, value in completion.items()}),
    )


async def _certificate(svc: ContractsService, claim: ProgressClaim) -> dict:
    """The claim's application, asserting line 8 is what the claim is owed."""
    application = await svc.build_aia_application(claim.id)
    summary = application["summary"]
    # net_due is stored at four places and the certificate prints cents, so
    # compare unquantized: a sub-cent divergence is exactly what this catches.
    assert summary["current_payment_due"] == Decimal(str(claim.net_due))
    # And the sheet adds up the way the form says it does.
    assert summary["total_earned_less_retainage"] == summary["total_completed_stored"] - summary["retainage"]
    assert summary["current_payment_due"] == max(
        summary["total_earned_less_retainage"] - summary["previous_certificates_total"], Decimal("0.00")
    )
    return application


def _failures(report: dict, rule_id: str) -> list[dict]:
    return [f for f in report["errors"] if f["rule_id"] == rule_id]


async def test_a_claim_that_bills_some_lines_still_carries_the_rest_of_the_schedule(session, world) -> None:
    # The most ordinary workflow there is: March bills both lines, April bills
    # only A because B was unticked in the populate preview, which leaves
    # April with no line for B at all.
    svc = ContractsService(session)
    march = await _generate(svc, world, await _claim(session, world, "PC-1", 3), a="40", b="40")
    await svc.claim_repo.update_fields(march.id, status="approved")
    april = await _generate(svc, world, await _claim(session, world, "PC-2", 4), a="60")
    unticked = next(
        ln for ln in await svc.claim_line_repo.list_for_claim(april.id) if ln.contract_line_id == world.b.id
    )
    await delete_claim_line(unticked.id, session, str(OWNER_ID))
    await session.refresh(april)

    application = await _certificate(svc, april)
    rows = {row["item_number"]: row for row in application["lines"]}
    assert set(rows) == {"A", "B"}
    # B is not billed this period, and the 16,000 it billed in March is still
    # on the sheet: it used to print zeros and a balance of the whole 40,000.
    assert (rows["B"]["previous_value"], rows["B"]["this_period_value"]) == (Decimal("16000.00"), Decimal("0.00"))
    assert (rows["B"]["total_completed_stored"], rows["B"]["balance_to_finish"]) == (
        Decimal("16000.00"),
        Decimal("24000.00"),
    )

    summary = application["summary"]
    assert summary["total_completed_stored"] == Decimal("52000.00")
    assert summary["retainage"] == Decimal("5200.00")
    assert summary["total_earned_less_retainage"] == Decimal("46800.00")
    assert summary["previous_certificates_total"] == Decimal("36000.00")
    assert summary["current_payment_due"] == Decimal("10800.00") == april.net_due

    # Nothing about this claim is a finding: it is the normal way to bill.
    report = await svc.validate_claim(april.id)
    assert report["errors"] == []


async def test_a_certified_claim_will_not_have_its_period_moved(session, world) -> None:
    svc = ContractsService(session)
    march = await _generate(svc, world, await _claim(session, world, "PC-1", 3), a="40", b="40")
    await svc.claim_repo.update_fields(march.id, status="certified")
    await session.refresh(march)
    april = await _generate(svc, world, await _claim(session, world, "PC-2", 4), a="60", b="60")
    assert april.prior_claims_total == Decimal("36000")

    # Moving March to May would put it after April in billing order, and
    # April's line 7 would drop from 36,000 to nothing.
    with pytest.raises(HTTPException) as refused:
        await svc.update_progress_claim_fields(
            march, ProgressClaimUpdate(period_end="2026-05-31").model_dump(exclude_unset=True)
        )
    assert refused.value.status_code == 409
    assert refused.value.detail["error"] == "claim_terms_locked"
    assert refused.value.detail["locked_fields"] == ["period_end"]

    await session.refresh(april)
    assert april.prior_claims_total == Decimal("36000")
    await _certificate(svc, april)

    # A draft is still free to move, and so is a field that carries no money.
    await svc.update_progress_claim_fields(
        april, ProgressClaimUpdate(period_end="2026-04-25").model_dump(exclude_unset=True)
    )
    assert april.period_to == date(2026, 4, 25)
    await svc.update_progress_claim_fields(march, {"claim_date": "2026-04-02"})
    assert march.claim_date == "2026-04-02"


async def test_an_undated_claim_is_still_previous_to_the_one_after_it(session, world) -> None:
    svc = ContractsService(session)
    # A legacy row: nobody ever entered its period.
    first = await _generate(
        svc,
        world,
        await _claim(session, world, "PC-1", None, created=datetime(2026, 3, 20, tzinfo=UTC)),
        a="40",
        b="40",
    )

    # It cannot be submitted undated: its place in the billing order is a
    # guess, and the rule that used to warn about that now blocks.
    report = await svc.validate_claim(first.id)
    [finding] = _failures(report, "pay_application.period_present")
    assert finding["severity"] == "error"
    with pytest.raises(HTTPException) as refused:
        await svc.transition_claim(first.id, "submitted")
    assert refused.value.status_code == 422

    # The row is certified anyway, the way the legacy ones in the database got
    # there. It used to sort after every dated claim, so April read nothing
    # before it and billed the job for the whole 60% on top of the 40% paid.
    await svc.claim_repo.update_fields(first.id, status="certified")
    april = await _generate(svc, world, await _claim(session, world, "PC-2", 4), a="60", b="60")
    assert april.prior_claims_total == Decimal("36000")
    summary = (await _certificate(svc, april))["summary"]
    assert summary["previous_certificates_total"] == Decimal("36000.00")
    assert summary["current_payment_due"] == Decimal("18000.00")


async def test_an_earlier_claim_regenerated_leaves_the_later_one_blocked_until_it_is_too(session, world) -> None:
    svc = ContractsService(session)
    march = await _generate(svc, world, await _claim(session, world, "PC-1", 3), a="40", b="40")
    await svc.claim_repo.update_fields(march.id, status="approved")
    april = await _generate(svc, world, await _claim(session, world, "PC-2", 4), a="60", b="60")
    assert (await svc.validate_claim(april.id))["errors"] == []

    # March regenerated at 50%: April's stored column D and its previous
    # certificates now describe a world that no longer exists. April is not
    # rewritten under the person reading it; it is blocked instead.
    await svc.claim_repo.update_fields(march.id, status="draft")
    march = await _generate(svc, world, march, a="50", b="50")
    report = await svc.validate_claim(april.id)
    findings = _failures(report, "pay_application.prior_matches_earlier_claims")
    assert len(findings) == 3
    assert {f["element_ref"] for f in findings} == {str(world.a.id), str(world.b.id), str(april.id)}
    # The panel turns red and the submit button says why, which is the
    # visible half of this: nothing is corrected behind the reader's back.
    assert report["status"] == "errors"
    with pytest.raises(HTTPException) as refused:
        await svc.transition_claim(april.id, "submitted")
    assert refused.value.status_code == 422

    # Regenerating April is the one action that clears it.
    april = await _generate(svc, world, april, a="60", b="60")
    assert _failures(await svc.validate_claim(april.id), "pay_application.prior_matches_earlier_claims") == []
    assert april.prior_claims_total == Decimal("45000")
    await _certificate(svc, april)


async def test_a_claim_whose_totals_do_not_add_up_is_blocked(session, world) -> None:
    svc = ContractsService(session)
    march = await _generate(svc, world, await _claim(session, world, "PC-1", 3), a="40", b="40")
    assert _failures(await svc.validate_claim(march.id), "pay_application.totals_match_lines") == []

    # What a line write used to leave behind: the header keeps the figure the
    # generator put there while the lines say something else.
    await svc.claim_repo.update_fields(march.id, gross_amount=Decimal("40000"), net_due=Decimal("36000"))
    [line] = [ln for ln in await svc.claim_line_repo.list_for_claim(march.id) if ln.contract_line_id == world.a.id]
    await svc.claim_line_repo.update_fields(line.id, period_completed_value=Decimal("30000"))
    [finding] = _failures(await svc.validate_claim(march.id), "pay_application.totals_match_lines")
    assert finding["severity"] == "error"

    march = await svc.roll_claim_retention(march.id)
    assert march.gross_amount == Decimal("46000")
    assert _failures(await svc.validate_claim(march.id), "pay_application.totals_match_lines") == []
