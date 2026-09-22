# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""What the G703 lists, against the database.

The continuation sheet is built from the contract's schedule of values, and
three shapes of schedule used to render a certificate that disagreed with the
claim behind it (the ids are the adversarial money review's scenarios):

* rv-money s16: a roll-up parent listed beside its own children, so column C
  added the job up twice and the parent printed 0% complete against the whole
  contract.
* rv-money s12: a line that did not move this period dropped to zero, taking
  what it had already billed out of line 4 and line 8 with it.
* rv-money s13: a cost-plus or T&M claim has no SoV lines behind it, so the
  sheet had nothing to roll up and lines 4 and 8 printed zero on a claim that
  was owed its net in full.

Every figure here is read through the service the screens call, and the last
assertion of each test is the one the owner cares about: G702 line 8 is the
net the claim says it is due.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.modules.contracts.models import Contract, ContractLine, ProgressClaimLine
from app.modules.contracts.schemas import AutoGenerateClaimRequest
from app.modules.contracts.service import ContractsService
from app.modules.projects.models import Project
from app.modules.users.models import User

pytestmark = pytest.mark.asyncio

PERIODS = [("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30")]


async def _job(session, lines, *, contract_type="lump_sum"):
    """A US project with a contract, its SoV lines and 10% retention."""
    suffix = uuid.uuid4().hex[:8]
    owner = User(id=uuid.uuid4(), email=f"aia-render-{suffix}@site.example", hashed_password="x")
    session.add(owner)
    await session.flush()
    project = Project(
        id=uuid.uuid4(),
        name="Certificate rendering",
        owner_id=owner.id,
        currency="USD",
        country_code="US",
        metadata_={},
    )
    session.add(project)
    await session.flush()
    total = sum((Decimal(value) for _code, value in lines), Decimal("0"))
    contract = Contract(
        id=uuid.uuid4(),
        code=f"C-{suffix}",
        title="Main works",
        project_id=project.id,
        contract_type=contract_type,
        currency="USD",
        total_value=total,
        original_contract_value=total,
        retention_percent=Decimal("10"),
        status="active",
    )
    session.add(contract)
    await session.flush()
    built = []
    for index, (code, value) in enumerate(lines):
        line = ContractLine(
            id=uuid.uuid4(),
            contract_id=contract.id,
            code=code,
            description=f"SoV {code}",
            quantity=Decimal("1"),
            unit_rate=Decimal(value),
            total_value=Decimal(value),
            order_index=index,
        )
        session.add(line)
        built.append(line)
    await session.flush()
    return SimpleNamespace(project=project, contract=contract, lines={ln.code: ln for ln in built})


async def _claim(svc, job, month):
    start, end = PERIODS[month - 1]
    return await svc.create_progress_claim(
        SimpleNamespace(
            contract_id=job.contract.id,
            claim_number=f"PC-{month}",
            period_start=start,
            period_end=end,
            claim_date=end,
            currency="USD",
            metadata={},
        )
    )


async def _bill(svc, job, month, percents):
    claim = await _claim(svc, job, month)
    return await svc.auto_generate_claim_lines(
        claim.id,
        AutoGenerateClaimRequest(completion={str(job.lines[code].id): Decimal(pct) for code, pct in percents.items()}),
    )


def _column(app, key) -> Decimal:
    return sum((row[key] for row in app["lines"]), Decimal("0"))


# ── A schedule of values with roll-up rows ───────────────────────────────


async def test_parent_rollup_line_is_not_listed_beside_its_children_rv_s16(pg_session) -> None:
    """Column C adds up to line 3, once, and no row claims the whole contract."""
    svc = ContractsService(pg_session)
    job = await _job(pg_session, [("A", "60000"), ("B", "40000")])
    parent = ContractLine(
        id=uuid.uuid4(),
        contract_id=job.contract.id,
        code="P",
        description="Division 03 summary",
        quantity=Decimal("1"),
        unit_rate=Decimal("100000"),
        total_value=Decimal("100000"),
        order_index=-1,
    )
    pg_session.add(parent)
    await pg_session.flush()
    for code in ("A", "B"):
        await svc.line_repo.update_fields(job.lines[code].id, parent_line_id=parent.id)

    claim = await _bill(svc, job, 1, {"A": "40", "B": "40"})
    app = await svc.build_aia_application(claim.id)

    assert [row["item_number"] for row in app["lines"]] == ["A", "B"]
    assert _column(app, "scheduled_value") == app["summary"]["contract_sum_to_date"] == Decimal("100000.00")
    assert _column(app, "total_completed_stored") == app["summary"]["total_completed_stored"]
    assert app["summary"]["current_payment_due"] == Decimal(str(claim.net_due)).quantize(Decimal("0.01"))


async def test_a_parent_line_billed_by_hand_stays_on_the_sheet(pg_session) -> None:
    """Dropping a parent must not drop money the claim is holding against it.

    The generators never bill a roll-up row, but a claim line can be typed
    against one through the API. Skipping it unconditionally would take that
    money off the sheet while the claim still carries it in its gross.
    """
    svc = ContractsService(pg_session)
    job = await _job(pg_session, [("A", "60000"), ("B", "40000")])
    parent = ContractLine(
        id=uuid.uuid4(),
        contract_id=job.contract.id,
        code="P",
        description="Division 03 summary",
        quantity=Decimal("1"),
        unit_rate=Decimal("10000"),
        total_value=Decimal("10000"),
        order_index=-1,
    )
    pg_session.add(parent)
    await pg_session.flush()
    await svc.line_repo.update_fields(job.lines["A"].id, parent_line_id=parent.id)

    claim = await _bill(svc, job, 1, {"A": "40", "B": "40"})
    await svc.claim_line_repo.create(
        ProgressClaimLine(
            progress_claim_id=claim.id,
            contract_line_id=parent.id,
            period_completed_qty=Decimal("1"),
            period_completed_value=Decimal("1000"),
            period_completed_pct=Decimal("10"),
            cumulative_completed_value=Decimal("1000"),
        )
    )
    app = await svc.build_aia_application(claim.id)

    assert "P" in [row["item_number"] for row in app["lines"]]
    billed = [row for row in app["lines"] if row["item_number"] == "P"][0]
    assert billed["this_period_value"] == Decimal("1000.00")
    assert _column(app, "total_completed_stored") == app["summary"]["total_completed_stored"]


# ── A line that does not move this period ────────────────────────────────


async def test_a_line_that_did_not_move_keeps_what_it_billed_rv_s12(pg_session) -> None:
    """Month two bills only A; B still shows the 16,000 it billed in month one."""
    svc = ContractsService(pg_session)
    job = await _job(pg_session, [("A", "60000"), ("B", "40000")])
    await _bill(svc, job, 1, {"A": "40", "B": "40"})
    second = await _bill(svc, job, 2, {"A": "60"})
    app = await svc.build_aia_application(second.id)

    unmoved = [row for row in app["lines"] if row["item_number"] == "B"][0]
    assert unmoved["previous_value"] == Decimal("16000.00")
    assert unmoved["this_period_value"] == Decimal("0.00")
    assert unmoved["total_completed_stored"] == Decimal("16000.00")
    assert unmoved["balance_to_finish"] == Decimal("24000.00")
    assert app["summary"]["total_completed_stored"] == Decimal("52000.00")
    assert app["summary"]["current_payment_due"] == Decimal(str(second.net_due)).quantize(Decimal("0.01"))


# ── A contract billed without a schedule of values ───────────────────────


@pytest.mark.parametrize("contract_type", ["cost_plus", "tm"])
async def test_a_claim_with_no_sov_lines_bills_its_own_totals_rv_s13(pg_session, contract_type) -> None:
    """Cost-plus and T&M carry the claim's gross and retention on one row.

    Two months, because a single month has no previous certificates and would
    let line 8 agree with the claim by accident.
    """
    svc = ContractsService(pg_session)
    job = await _job(pg_session, [("A", "60000"), ("B", "40000")], contract_type=contract_type)

    def _request(amount: str) -> AutoGenerateClaimRequest:
        if contract_type == "cost_plus":
            return AutoGenerateClaimRequest(actual_costs_total=Decimal(amount))
        return AutoGenerateClaimRequest(time_entries_total=Decimal(amount), material_entries_total=Decimal("0"))

    first = await svc.auto_generate_claim_lines((await _claim(svc, job, 1)).id, _request("50000"))
    app = await svc.build_aia_application(first.id)
    assert len(app["lines"]) == 1
    assert app["summary"]["total_completed_stored"] == Decimal("50000.00")
    assert app["summary"]["retainage"] == Decimal("5000.00")
    assert app["summary"]["current_payment_due"] == Decimal(str(first.net_due)).quantize(Decimal("0.01"))

    second = await svc.auto_generate_claim_lines((await _claim(svc, job, 2)).id, _request("30000"))
    app2 = await svc.build_aia_application(second.id)
    row = app2["lines"][0]
    assert row["previous_value"] == Decimal("50000.00")
    assert row["this_period_value"] == Decimal("30000.00")
    # Line 4 is billed to date, line 5 the retention held on all of it, and
    # line 8 what this month adds: 30,000 less its own 3,000 of retention.
    assert app2["summary"]["total_completed_stored"] == Decimal("80000.00")
    assert app2["summary"]["retainage"] == Decimal("8000.00")
    assert app2["summary"]["previous_certificates_total"] == Decimal("45000.00")
    # Column D above is the prior claims' gross, and line 7 is only the same
    # reading of "previous" while it is rebuilt from their gross and retention.
    # A flat-retention claim stores no certificate snapshot, which is what puts
    # line 7 on that branch; if that ever changes the two stop agreeing.
    assert app2["summary"]["previous_certificates_basis"] == "reconstructed"
    assert app2["summary"]["current_payment_due"] == Decimal("27000.00")
    assert app2["summary"]["current_payment_due"] == Decimal(str(second.net_due)).quantize(Decimal("0.01"))
