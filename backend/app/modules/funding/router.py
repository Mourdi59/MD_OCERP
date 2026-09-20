# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Public funding API routes - mounted at /api/v1/funding/.

Two scoping rules run through every endpoint here and are worth stating once
rather than repeating in thirty docstrings.

Anything that names a project verifies access to that project before it
reads. Anything that names a child record loads its application first and
verifies access to *that* application's project, never to a project id the
caller supplied, because a caller who may name the project can name one they
are entitled to and then ask for a record belonging to one they are not.

``today`` is a query parameter rather than the server's clock. Whether a
deadline has passed is a question about the reader's calendar, and a server
in another timezone would answer it differently for the same person on the
same afternoon. Callers that omit it get the counts without the lateness.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.dependencies import (
    CurrentUserId,
    RequirePermission,
    SessionDep,
    verify_project_access,
)
from app.modules.funding.models import (
    FundingApplication,
    FundingCostAllocation,
    FundingDisbursement,
    FundingObligation,
    FundingProofOfUse,
)
from app.modules.funding.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationSummary,
    ApplicationUpdate,
    AwardRecord,
    CostAllocationCreate,
    CostAllocationOut,
    CostAllocationUpdate,
    DisbursementCreate,
    DisbursementOut,
    DisbursementUpdate,
    ObligationCreate,
    ObligationOut,
    ObligationUpdate,
    ProgrammeCreate,
    ProgrammeOut,
    ProgrammeUpdate,
    ProjectFundingSummary,
    ProofOfUseCreate,
    ProofOfUseOut,
    ProofOfUseUpdate,
    ReceiptRecord,
)
from app.modules.funding.service import FundingService, iso_day, obligation_title_key

router = APIRouter(tags=["funding"])


def _get_service(session: SessionDep) -> FundingService:
    return FundingService(session)


class ProgrammeListResponse(BaseModel):
    """A page of the programme catalogue, and how large the catalogue is."""

    items: list[ProgrammeOut]
    total: int
    offset: int
    limit: int


class ApplicationListResponse(BaseModel):
    """Every application on one project."""

    items: list[ApplicationOut]
    total: int


class ValidationFinding(BaseModel):
    """One thing a rule noticed about an application."""

    rule_id: str
    rule_name: str
    severity: str
    category: str
    passed: bool
    message: str
    element_ref: str | None = None
    suggestion: str | None = None


class ApplicationDetailResponse(BaseModel):
    """An application, everything hanging off it, and what the rules say.

    The findings travel with the record rather than behind a second request,
    so nobody has to know that a validation screen exists in order to be
    told that the works started before the application was filed.
    """

    application: ApplicationOut
    programme: ProgrammeOut | None = None
    disbursements: list[DisbursementOut] = []
    proofs_of_use: list[ProofOfUseOut] = []
    obligations: list[ObligationOut] = []
    cost_allocations: list[CostAllocationOut] = []
    summary: ApplicationSummary
    findings: list[ValidationFinding] = []


class ObligationCalendarResponse(BaseModel):
    """Deadlines across a whole project, soonest first."""

    items: list[ObligationOut]
    total: int
    overdue: int


async def _load_application(
    application_id: uuid.UUID,
    user_id: str,
    session: SessionDep,
    service: FundingService,
) -> FundingApplication:
    """Fetch an application and confirm the caller may see its project."""
    application = await service.applications.get(application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    await verify_project_access(application.project_id, user_id, session)
    return application


#: Kept under the name readers here already use. The rule itself lives in the
#: service, because the deadline list and the application summary both have to
#: answer "is this title translatable" and two copies of that answer would
#: drift the moment one of them was corrected.
_title_key = obligation_title_key


def _obligation_out(row: FundingObligation, today: str) -> ObligationOut:
    """An obligation plus whether it is late, worked out at read time."""
    due = iso_day(row.due_on)
    overdue = bool(today and due and row.status == "open" and due < today)
    out = ObligationOut.model_validate(row)
    out.overdue = overdue
    out.title_key = _title_key(row)
    return out


# ── Programmes ─────────────────────────────────────────────────────────────


@router.get("/programmes/", response_model=ProgrammeListResponse)
async def list_programmes(
    country: str | None = Query(default=None, max_length=2),
    status: str | None = Query(default=None),
    authority_level: str | None = Query(default=None),
    instrument: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ProgrammeListResponse:
    """A page of the programme catalogue.

    ``total`` counts what the filters matched rather than what the page
    holds, so a reader narrowing by country is told how many there are
    before paging to the end to find out.
    """
    rows, total = await service.programmes.list(
        country=country,
        status=status,
        authority_level=authority_level,
        instrument=instrument,
        search=search,
        limit=limit,
        offset=offset,
    )
    return ProgrammeListResponse(
        items=[ProgrammeOut.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/programmes/", response_model=ProgrammeOut, status_code=201)
async def create_programme(
    data: ProgrammeCreate,
    _perm: None = Depends(RequirePermission("funding.manage_programmes")),
    service: FundingService = Depends(_get_service),
) -> ProgrammeOut:
    existing = await service.programmes.get_by_code(data.code, data.country)
    if existing is not None:
        raise HTTPException(status_code=409, detail="A programme with this code already exists in this country")
    values = data.model_dump()
    values["country"] = values["country"].upper()
    row = await service.programmes.create(**values)
    return ProgrammeOut.model_validate(row)


@router.get("/programmes/{programme_id}", response_model=ProgrammeOut)
async def get_programme(
    programme_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ProgrammeOut:
    row = await service.programmes.get(programme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Programme not found")
    return ProgrammeOut.model_validate(row)


@router.patch("/programmes/{programme_id}", response_model=ProgrammeOut)
async def update_programme(
    programme_id: uuid.UUID,
    data: ProgrammeUpdate,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("funding.manage_programmes")),
    service: FundingService = Depends(_get_service),
) -> ProgrammeOut:
    """Edit a programme's terms.

    Editing terms does not move deadlines already derived from them. Those
    were written down when the award was recorded and communicated to people
    who diarised them, so a correction to the catalogue cannot silently pull
    a date forward under somebody who is working to it.
    """
    row = await service.programmes.get(programme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Programme not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    return ProgrammeOut.model_validate(row)


@router.delete("/programmes/{programme_id}", status_code=204)
async def delete_programme(
    programme_id: uuid.UUID,
    _perm: None = Depends(RequirePermission("funding.manage_programmes")),
    service: FundingService = Depends(_get_service),
) -> None:
    """Remove a programme nothing has applied to.

    The foreign key from applications is ``RESTRICT`` rather than cascade,
    because deleting a programme that has awards behind it would delete the
    awards, and an award is evidence. The check is made here so the caller
    is told why rather than meeting a database error.
    """
    row = await service.programmes.get(programme_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Programme not found")
    if await service.programmes.count_applications(programme_id):
        raise HTTPException(
            status_code=409,
            detail="This programme has applications and cannot be deleted. Close it instead.",
        )
    await service.programmes.delete(row)


# ── Applications ───────────────────────────────────────────────────────────


@router.get("/applications/", response_model=ApplicationListResponse)
async def list_applications(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    status: str | None = Query(default=None),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ApplicationListResponse:
    await verify_project_access(project_id, user_id, session)
    rows = await service.applications.list_for_project(project_id, status=status)
    return ApplicationListResponse(
        items=[ApplicationOut.model_validate(row) for row in rows],
        total=len(rows),
    )


@router.post("/applications/", response_model=ApplicationOut, status_code=201)
async def create_application(
    data: ApplicationCreate,
    user_id: CurrentUserId,
    session: SessionDep,
    _perm: None = Depends(RequirePermission("funding.create")),
    service: FundingService = Depends(_get_service),
) -> ApplicationOut:
    await verify_project_access(data.project_id, user_id, session)
    programme = await service.programmes.get(data.programme_id)
    if programme is None:
        raise HTTPException(status_code=404, detail="Programme not found")
    existing = await service.applications.get_by_code(data.project_id, data.code)
    if existing is not None:
        raise HTTPException(status_code=409, detail="An application with this code already exists on this project")

    values = data.model_dump()
    # The currency follows the programme unless the caller said otherwise.
    # A grant is paid in the currency the body grants in, and letting the
    # two drift makes every rollup on the page a mixed-currency sum.
    if not data.currency or data.currency == "EUR":
        values["currency"] = programme.currency
    row = await service.applications.create(**values)
    return ApplicationOut.model_validate(row)


@router.get("/applications/{application_id}", response_model=ApplicationDetailResponse)
async def get_application(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    locale: str = Query(default="en", max_length=10),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ApplicationDetailResponse:
    """One application with everything hanging off it, and its findings."""
    application = await _load_application(application_id, user_id, session, service)
    day = iso_day(today)

    programme = await service.programmes.get(application.programme_id)
    disbursements = await service.disbursements.list_for_application(application_id)
    proofs = await service.proofs.list_for_application(application_id)
    obligations = await service.obligations.list_for_application(application_id)
    allocations = await service.allocations.list_for_application(application_id)

    summary = await service.application_summary(application, today=day)
    findings = await service.validate_application(application, locale=locale, today=day)

    return ApplicationDetailResponse(
        application=ApplicationOut.model_validate(application),
        programme=ProgrammeOut.model_validate(programme) if programme else None,
        disbursements=[DisbursementOut.model_validate(row) for row in disbursements],
        proofs_of_use=[ProofOfUseOut.model_validate(row) for row in proofs],
        obligations=[_obligation_out(row, day) for row in obligations],
        cost_allocations=[CostAllocationOut.model_validate(row) for row in allocations],
        summary=ApplicationSummary(**summary),
        findings=[ValidationFinding(**finding) for finding in findings],
    )


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: uuid.UUID,
    data: ApplicationUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.update")),
    service: FundingService = Depends(_get_service),
) -> ApplicationOut:
    """Edit an application.

    ``status`` accepts every value except ``approved`` and ``rejected``.
    Those two are decisions somebody else made, they carry an amount, a
    period and conditions with them, and they generate deadlines, so they go
    through the award endpoint and its own permission rather than through a
    field edit that could set the status and leave the rest empty.
    """
    application = await _load_application(application_id, user_id, session, service)
    values = data.model_dump(exclude_unset=True)
    if values.get("status") in ("approved", "rejected"):
        raise HTTPException(
            status_code=400,
            detail="Record a decision through /applications/{id}/award, which also sets the award period",
        )
    for field, value in values.items():
        setattr(application, field, value)
    await session.flush()
    return ApplicationOut.model_validate(application)


@router.delete("/applications/{application_id}", status_code=204)
async def delete_application(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.delete")),
    service: FundingService = Depends(_get_service),
) -> None:
    """Delete an application that never received an award.

    An approved application is a record of public money being granted, and
    the draws and reports beneath it cascade. Withdrawing sets a status and
    keeps the file; deleting would remove the evidence that the file existed.
    """
    application = await _load_application(application_id, user_id, session, service)
    if application.status == "approved":
        raise HTTPException(
            status_code=409,
            detail="An approved application cannot be deleted. Set its status to withdrawn or closed instead.",
        )
    await service.applications.delete(application)


@router.post("/applications/{application_id}/award", response_model=ApplicationOut)
async def record_award(
    application_id: uuid.UUID,
    data: AwardRecord,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.record_award")),
    service: FundingService = Depends(_get_service),
) -> ApplicationOut:
    """Record the authority's decision, and diarise what follows from it."""
    application = await _load_application(application_id, user_id, session, service)
    if data.approved and not data.award_period_end:
        raise HTTPException(
            status_code=400,
            detail="An approval needs the end of its award period, because every later deadline counts from it",
        )
    await service.record_award(
        application,
        approved=data.approved,
        decided_on=data.decided_on,
        award_reference=data.award_reference,
        approved_amount=data.approved_amount,
        award_period_start=data.award_period_start,
        award_period_end=data.award_period_end,
        conditions=data.conditions,
        rejection_reason=data.rejection_reason,
    )
    return ApplicationOut.model_validate(application)


@router.get("/applications/{application_id}/summary", response_model=ApplicationSummary)
async def application_summary(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ApplicationSummary:
    application = await _load_application(application_id, user_id, session, service)
    return ApplicationSummary(**await service.application_summary(application, today=iso_day(today)))


# ── Disbursements ──────────────────────────────────────────────────────────


@router.get("/applications/{application_id}/disbursements/", response_model=list[DisbursementOut])
async def list_disbursements(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> list[DisbursementOut]:
    await _load_application(application_id, user_id, session, service)
    rows = await service.disbursements.list_for_application(application_id)
    return [DisbursementOut.model_validate(row) for row in rows]


@router.post("/applications/{application_id}/disbursements/", response_model=DisbursementOut, status_code=201)
async def create_disbursement(
    application_id: uuid.UUID,
    data: DisbursementCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.request_disbursement")),
    service: FundingService = Depends(_get_service),
) -> DisbursementOut:
    """Open a draw against an award."""
    application = await _load_application(application_id, user_id, session, service)
    if application.status != "approved":
        raise HTTPException(status_code=409, detail="Funds can only be drawn against an approved application")
    values = data.model_dump()
    values["application_id"] = application_id
    values["sequence"] = await service.disbursements.next_sequence(application_id)
    values["invoice_ids"] = [str(item) for item in data.invoice_ids]
    row = await service.disbursements.create(**values)
    return DisbursementOut.model_validate(row)


@router.patch("/disbursements/{disbursement_id}", response_model=DisbursementOut)
async def update_disbursement(
    disbursement_id: uuid.UUID,
    data: DisbursementUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.update")),
    service: FundingService = Depends(_get_service),
) -> DisbursementOut:
    """Edit a draw.

    Marking one paid goes through the receipt endpoint instead, because
    receiving money starts the clock on spending it and that deadline has to
    be written down at the moment it starts.
    """
    row: FundingDisbursement | None = await service.disbursements.get(disbursement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Disbursement not found")
    await _load_application(row.application_id, user_id, session, service)
    values = data.model_dump(exclude_unset=True)
    if values.get("status") == "paid":
        raise HTTPException(
            status_code=400,
            detail="Record receipt through /disbursements/{id}/receipt, which also sets the spending deadline",
        )
    if "invoice_ids" in values and values["invoice_ids"] is not None:
        values["invoice_ids"] = [str(item) for item in values["invoice_ids"]]
    for field, value in values.items():
        setattr(row, field, value)
    await session.flush()
    return DisbursementOut.model_validate(row)


@router.post("/disbursements/{disbursement_id}/receipt", response_model=DisbursementOut)
async def confirm_disbursement_receipt(
    disbursement_id: uuid.UUID,
    data: ReceiptRecord,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.confirm_receipt")),
    service: FundingService = Depends(_get_service),
) -> DisbursementOut:
    """Record that the money arrived, and diarise the window to spend it."""
    row: FundingDisbursement | None = await service.disbursements.get(disbursement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Disbursement not found")
    application = await _load_application(row.application_id, user_id, session, service)
    if not iso_day(data.received_on):
        raise HTTPException(status_code=400, detail="received_on must be a calendar date, as YYYY-MM-DD")
    if data.amount_received is not None:
        row.amount_received = data.amount_received
    await service.on_funds_received(application, row, data.received_on)
    return DisbursementOut.model_validate(row)


@router.delete("/disbursements/{disbursement_id}", status_code=204)
async def delete_disbursement(
    disbursement_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.delete")),
    service: FundingService = Depends(_get_service),
) -> None:
    row: FundingDisbursement | None = await service.disbursements.get(disbursement_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Disbursement not found")
    await _load_application(row.application_id, user_id, session, service)
    if row.status == "paid":
        raise HTTPException(status_code=409, detail="A draw that has been paid cannot be deleted")
    await service.disbursements.delete(row)


# ── Proof of use ───────────────────────────────────────────────────────────


@router.get("/applications/{application_id}/proofs/", response_model=list[ProofOfUseOut])
async def list_proofs(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> list[ProofOfUseOut]:
    await _load_application(application_id, user_id, session, service)
    rows = await service.proofs.list_for_application(application_id)
    return [ProofOfUseOut.model_validate(row) for row in rows]


@router.post("/applications/{application_id}/proofs/", response_model=ProofOfUseOut, status_code=201)
async def create_proof(
    application_id: uuid.UUID,
    data: ProofOfUseCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.submit_proof_of_use")),
    service: FundingService = Depends(_get_service),
) -> ProofOfUseOut:
    """Open an interim or final account of where the money went.

    When the caller names no due date the one the award already implies is
    used, so the two cannot disagree: the deadline was worked out once, when
    the award was recorded, and lives on the obligation.
    """
    await _load_application(application_id, user_id, session, service)
    values = data.model_dump()
    values["application_id"] = application_id
    if not values.get("due_on") and data.kind == "final":
        obligations = await service.obligations.list_for_application(application_id)
        derived = [row for row in obligations if row.kind == "final_report" and iso_day(row.due_on)]
        if derived:
            values["due_on"] = derived[0].due_on
    row = await service.proofs.create(**values)
    return ProofOfUseOut.model_validate(row)


@router.patch("/proofs/{proof_id}", response_model=ProofOfUseOut)
async def update_proof(
    proof_id: uuid.UUID,
    data: ProofOfUseUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.update")),
    service: FundingService = Depends(_get_service),
) -> ProofOfUseOut:
    row: FundingProofOfUse | None = await service.proofs.get(proof_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Proof of use not found")
    await _load_application(row.application_id, user_id, session, service)
    values = data.model_dump(exclude_unset=True)
    if values.get("status") == "accepted":
        raise HTTPException(
            status_code=400,
            detail="Record acceptance through /proofs/{id}/accept, which also sets the retention deadline",
        )
    for field, value in values.items():
        setattr(row, field, value)
    await session.flush()
    return ProofOfUseOut.model_validate(row)


@router.post("/proofs/{proof_id}/accept", response_model=ProofOfUseOut)
async def accept_proof(
    proof_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    accepted_on: str = Query(..., max_length=40),
    _perm: None = Depends(RequirePermission("funding.close_application")),
    service: FundingService = Depends(_get_service),
) -> ProofOfUseOut:
    """Record that the authority accepted the account, and set retention."""
    row: FundingProofOfUse | None = await service.proofs.get(proof_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Proof of use not found")
    application = await _load_application(row.application_id, user_id, session, service)
    if not iso_day(accepted_on):
        raise HTTPException(status_code=400, detail="accepted_on must be a calendar date, as YYYY-MM-DD")
    await service.on_proof_accepted(application, row, accepted_on)
    return ProofOfUseOut.model_validate(row)


# ── Obligations ────────────────────────────────────────────────────────────


@router.get("/applications/{application_id}/obligations/", response_model=list[ObligationOut])
async def list_obligations(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> list[ObligationOut]:
    await _load_application(application_id, user_id, session, service)
    rows = await service.obligations.list_for_application(application_id)
    return [_obligation_out(row, iso_day(today)) for row in rows]


@router.post("/applications/{application_id}/obligations/", response_model=ObligationOut, status_code=201)
async def create_obligation(
    application_id: uuid.UUID,
    data: ObligationCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.create")),
    service: FundingService = Depends(_get_service),
) -> ObligationOut:
    """Add an obligation by hand, usually a condition out of the notice.

    ``source`` is forced away from ``programme_rule`` because that value is
    what marks the rows this module regenerates. A hand written obligation
    carrying it would be deleted the next time an award was re-recorded, and
    the person who wrote it would never find out.
    """
    await _load_application(application_id, user_id, session, service)
    values = data.model_dump()
    values["application_id"] = application_id
    if values.get("source") == "programme_rule":
        values["source"] = "award_notice"
    row = await service.obligations.create(**values)
    return _obligation_out(row, "")


@router.patch("/obligations/{obligation_id}", response_model=ObligationOut)
async def update_obligation(
    obligation_id: uuid.UUID,
    data: ObligationUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    _perm: None = Depends(RequirePermission("funding.update")),
    service: FundingService = Depends(_get_service),
) -> ObligationOut:
    row: FundingObligation | None = await service.obligations.get(obligation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    await _load_application(row.application_id, user_id, session, service)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    return _obligation_out(row, iso_day(today))


@router.get("/obligations/", response_model=ObligationCalendarResponse)
async def list_project_obligations(
    session: SessionDep,
    project_id: uuid.UUID = Query(...),
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    open_only: bool = Query(default=True),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ObligationCalendarResponse:
    """Every deadline on a project, soonest first.

    This is the view a funding officer lives in, and it crosses
    applications on purpose. Deadlines are not a property of one grant, they
    are a property of a week.
    """
    await verify_project_access(project_id, user_id, session)
    applications = await service.applications.list_for_project(project_id)
    rows = await service.obligations.list_for_applications([row.id for row in applications])
    if open_only:
        rows = [row for row in rows if row.status == "open"]

    day = iso_day(today)
    items = [_obligation_out(row, day) for row in rows]
    # Undated obligations sort last rather than first. An empty string sorts
    # before every date, which would put the ones nobody can act on at the
    # top of the list somebody opens to find out what is urgent.
    items.sort(key=lambda item: (not iso_day(item.due_on), iso_day(item.due_on)))
    return ObligationCalendarResponse(
        items=items,
        total=len(items),
        overdue=sum(1 for item in items if item.overdue),
    )


# ── Cost allocations ───────────────────────────────────────────────────────


@router.get("/applications/{application_id}/allocations/", response_model=list[CostAllocationOut])
async def list_allocations(
    application_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> list[CostAllocationOut]:
    await _load_application(application_id, user_id, session, service)
    rows = await service.allocations.list_for_application(application_id)
    return [CostAllocationOut.model_validate(row) for row in rows]


@router.post("/applications/{application_id}/allocations/", response_model=CostAllocationOut, status_code=201)
async def create_allocation(
    application_id: uuid.UUID,
    data: CostAllocationCreate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.create")),
    service: FundingService = Depends(_get_service),
) -> CostAllocationOut:
    await _load_application(application_id, user_id, session, service)
    if data.eligible_amount > data.amount:
        raise HTTPException(status_code=400, detail="The eligible amount cannot exceed the amount")
    values = data.model_dump()
    values["application_id"] = application_id
    row = await service.allocations.create(**values)
    return CostAllocationOut.model_validate(row)


@router.patch("/allocations/{allocation_id}", response_model=CostAllocationOut)
async def update_allocation(
    allocation_id: uuid.UUID,
    data: CostAllocationUpdate,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.update")),
    service: FundingService = Depends(_get_service),
) -> CostAllocationOut:
    row: FundingCostAllocation | None = await service.allocations.get(allocation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Cost allocation not found")
    await _load_application(row.application_id, user_id, session, service)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    if row.eligible_amount > row.amount:
        raise HTTPException(status_code=400, detail="The eligible amount cannot exceed the amount")
    await session.flush()
    return CostAllocationOut.model_validate(row)


@router.delete("/allocations/{allocation_id}", status_code=204)
async def delete_allocation(
    allocation_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    _perm: None = Depends(RequirePermission("funding.delete")),
    service: FundingService = Depends(_get_service),
) -> None:
    row: FundingCostAllocation | None = await service.allocations.get(allocation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Cost allocation not found")
    await _load_application(row.application_id, user_id, session, service)
    await service.allocations.delete(row)


# ── Project rollup ─────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/summary", response_model=ProjectFundingSummary)
async def project_summary(
    project_id: uuid.UUID,
    session: SessionDep,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
    today: str = Query(default="", max_length=40),
    _perm: None = Depends(RequirePermission("funding.read")),
    service: FundingService = Depends(_get_service),
) -> ProjectFundingSummary:
    """Every application on one project, added up."""
    await verify_project_access(project_id, user_id, session)
    return ProjectFundingSummary(**await service.project_summary(project_id, today=iso_day(today)))
