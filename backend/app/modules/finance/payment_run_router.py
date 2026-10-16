# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Payment run API routes.

Mounted as a sub-router of the finance module, so every path below lives under
``/api/v1/finance/payment-runs``:

    GET    /                           - runs the caller can see
    POST   /                           - draw up a run from what falls due
    GET    /{id}                       - one run, its items and its findings
    PATCH  /{id}/items/{item_id}       - pay a different amount (draft)
    DELETE /{id}/items/{item_id}       - take an invoice out (draft)
    POST   /{id}/approve/              - approve (MANAGER, finance.approve)
    POST   /{id}/execute/              - record the payments (finance.record_payment)
    POST   /{id}/cancel/               - drop an unpaid run (finance.approve)
    GET    /{id}/bank-file.csv         - the remittance list for the bank
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select

from app.core.content_disposition import attachment_disposition
from app.dependencies import CurrentUserId, RequirePermission, SessionDep, accessible_project_ids
from app.modules.finance.models import Invoice
from app.modules.finance.payment_run_models import PAYMENT_RUN_STATUSES, PaymentRun
from app.modules.finance.payment_run_schemas import (
    PaymentRunCreate,
    PaymentRunIssueResponse,
    PaymentRunItemResponse,
    PaymentRunItemUpdate,
    PaymentRunListResponse,
    PaymentRunResponse,
)
from app.modules.finance.payment_run_service import PaymentRunService
from app.modules.finance.payment_runs import RunIssue, bank_csv
from app.modules.finance.router import _fetch_counterparty_names, _fetch_legal_entity_names

payment_run_router = APIRouter(prefix="/payment-runs", tags=["finance-payment-runs"])

_STATUS_PATTERN = "^(" + "|".join(PAYMENT_RUN_STATUSES) + ")$"


async def _project_names(session: SessionDep, project_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not project_ids:
        return {}
    from app.modules.projects.models import Project

    rows = (await session.execute(select(Project.id, Project.name).where(Project.id.in_(project_ids)))).all()
    return {pid: name for pid, name in rows}


async def _invoice_facts(session: SessionDep, invoice_ids: set[uuid.UUID]) -> dict[uuid.UUID, tuple[str, str | None]]:
    if not invoice_ids:
        return {}
    rows = (
        await session.execute(
            select(Invoice.id, Invoice.invoice_number, Invoice.due_date).where(Invoice.id.in_(invoice_ids))
        )
    ).all()
    return {iid: (number or "", due) for iid, number, due in rows}


async def _to_responses(
    session: SessionDep, runs: list[PaymentRun], issues: dict[uuid.UUID, list[RunIssue]] | None = None
) -> list[PaymentRunResponse]:
    items = [item for run in runs for item in run.items]
    names = await _fetch_counterparty_names(session, [i.contact_id for i in items])
    entities = await _fetch_legal_entity_names(
        session, [str(r.legal_entity_id) for r in runs if r.legal_entity_id is not None]
    )
    projects = await _project_names(session, {i.project_id for i in items})
    facts = await _invoice_facts(session, {i.invoice_id for i in items})
    out: list[PaymentRunResponse] = []
    for run in runs:
        total = sum((Decimal(str(i.amount)) for i in run.items), Decimal("0"))
        out.append(
            PaymentRunResponse(
                id=run.id,
                run_number=run.run_number,
                legal_entity_id=run.legal_entity_id,
                legal_entity_name=entities.get(str(run.legal_entity_id)) if run.legal_entity_id else None,
                currency_code=run.currency_code,
                payment_date=run.payment_date,
                due_by=run.due_by,
                status=run.status,
                note=run.note,
                created_by=run.created_by,
                approved_by=run.approved_by,
                approved_at=run.approved_at,
                executed_by=run.executed_by,
                executed_at=run.executed_at,
                created_at=run.created_at.isoformat() if run.created_at else None,
                total=format(total.quantize(Decimal("0.01")), "f"),
                item_count=len(run.items),
                items=[
                    PaymentRunItemResponse(
                        id=i.id,
                        invoice_id=i.invoice_id,
                        invoice_number=facts.get(i.invoice_id, ("", None))[0],
                        due_date=facts.get(i.invoice_id, ("", None))[1],
                        project_id=i.project_id,
                        project_name=projects.get(i.project_id),
                        contact_id=i.contact_id,
                        counterparty_name=names.get(i.contact_id) if i.contact_id else None,
                        amount=format(Decimal(str(i.amount)), "f"),
                        open_at_proposal=format(Decimal(str(i.open_at_proposal)), "f"),
                        payment_id=i.payment_id,
                    )
                    for i in run.items
                ],
                issues=[
                    PaymentRunIssueResponse(
                        severity=x.severity,
                        code=x.code,
                        message=x.message,
                        item_id=x.item_id,
                        invoice_id=x.invoice_id,
                    )
                    for x in (issues or {}).get(run.id, [])
                ],
            )
        )
    return out


async def _one(
    session: SessionDep, service: PaymentRunService, run: PaymentRun, issues: list[RunIssue] | None = None
) -> PaymentRunResponse:
    """A run with its findings: the given ones, or a fresh check while it can still change."""
    if issues is None:
        issues = await service.check(run) if run.status in ("draft", "approved") else []
    (resp,) = await _to_responses(session, [run], {run.id: issues})
    return resp


async def _load(session: SessionDep, run_id: uuid.UUID, user_id: str | None) -> tuple[PaymentRunService, PaymentRun]:
    service = PaymentRunService(session)
    scope = await accessible_project_ids(session, user_id)
    return service, await service.get(run_id, project_ids=scope, user_id=user_id)


@payment_run_router.get("/", response_model=PaymentRunListResponse, summary="List payment runs")
async def list_payment_runs(
    session: SessionDep,
    user_id: CurrentUserId,
    status_filter: str | None = Query(default=None, alias="status", pattern=_STATUS_PATTERN),
    legal_entity_id: uuid.UUID | None = Query(default=None),
    _perm: None = Depends(RequirePermission("finance.read")),
) -> PaymentRunListResponse:
    """Runs whose every project the caller can open, newest first."""
    scope = await accessible_project_ids(session, user_id)
    runs = await PaymentRunService(session).list(
        project_ids=scope, user_id=user_id, status_filter=status_filter, legal_entity_id=legal_entity_id
    )
    items = await _to_responses(session, runs)
    return PaymentRunListResponse(items=items, total=len(items))


@payment_run_router.post(
    "/",
    response_model=PaymentRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Draw up a payment run",
    description=(
        "Proposes every approved supplier invoice of the legal entity (or of the projects that name none), "
        "in the currency, that falls due by due_by, for what is still open on it as of payment_date. "
        "Retention that is held stays out. Only projects the caller can open are read."
    ),
)
async def create_payment_run(
    data: PaymentRunCreate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.record_payment")),
) -> PaymentRunResponse:
    service = PaymentRunService(session)
    run = await service.create(
        legal_entity_id=data.legal_entity_id,
        currency_code=data.currency_code,
        payment_date=data.payment_date,
        due_by=data.due_by or data.payment_date,
        note=data.note,
        project_ids=await accessible_project_ids(session, user_id),
        actor_id=user_id,
    )
    return await _one(session, service, run)


@payment_run_router.get("/{run_id}", response_model=PaymentRunResponse, summary="Get a payment run")
async def get_payment_run(
    run_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.read")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    return await _one(session, service, run)


@payment_run_router.patch(
    "/{run_id}/items/{item_id}", response_model=PaymentRunResponse, summary="Change the amount on one invoice"
)
async def update_payment_run_item(
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    data: PaymentRunItemUpdate,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.record_payment")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    await service.update_item(run, item_id, Decimal(data.amount), user_id)
    return await _one(session, service, run)


@payment_run_router.delete(
    "/{run_id}/items/{item_id}", response_model=PaymentRunResponse, summary="Take an invoice out of a run"
)
async def remove_payment_run_item(
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.record_payment")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    await service.remove_item(run, item_id, user_id)
    return await _one(session, service, run)


@payment_run_router.post("/{run_id}/approve/", response_model=PaymentRunResponse, summary="Approve a payment run")
async def approve_payment_run(
    run_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.approve")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    warnings = await service.approve(run, user_id)
    return await _one(session, service, run, warnings)


@payment_run_router.post(
    "/{run_id}/execute/",
    response_model=PaymentRunResponse,
    summary="Record the payments of an approved run",
    description=(
        "Checks the run again, then records one payment per invoice dated the run's payment date, all or none. "
        "An invoice left with nothing due and no retention held is marked paid."
    ),
)
async def execute_payment_run(
    run_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.record_payment")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    await service.execute(run, user_id)
    return await _one(session, service, run, [])


@payment_run_router.post("/{run_id}/cancel/", response_model=PaymentRunResponse, summary="Cancel an unpaid run")
async def cancel_payment_run(
    run_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.approve")),
) -> PaymentRunResponse:
    service, run = await _load(session, run_id, user_id)
    await service.cancel(run, user_id)
    return await _one(session, service, run, [])


@payment_run_router.get("/{run_id}/bank-file.csv", summary="Remittance list of a run, as CSV")
async def payment_run_bank_file(
    run_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId,
    _perm: None = Depends(RequirePermission("finance.read")),
) -> Response:
    service, run = await _load(session, run_id, user_id)
    (resp,) = await _to_responses(session, [run])
    text = bank_csv(
        {
            "run_number": resp.run_number,
            "payment_date": resp.payment_date,
            "payee": item.counterparty_name or "",
            "payee_id": item.contact_id or "",
            "invoice_number": item.invoice_number,
            "amount": item.amount,
            "currency": resp.currency_code,
            "reference": f"{resp.run_number} {item.invoice_number}".strip(),
        }
        for item in resp.items
    )
    return Response(
        content=text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment_disposition(f"{resp.run_number}.csv")},
    )
