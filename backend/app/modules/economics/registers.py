# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The registers that back the economics plan: securities, insurance, tax treatment and process set-up.

They are records of the project, not figures of the plan: a guarantee runs out, a policy is renewed and a
process is set up whatever the status of the plan is, so they stay editable while the plan is proposed or
approved and are not frozen in the approval snapshot. A gate reads them through the evidence provider, and
the findings of ``rules.register_findings`` flag what ran out or is still open.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.economics.errors import conflict, not_found
from app.modules.economics.models import Insurance, ProcessSetup, Security, TaxTreatment

_AREAS = ("receivables", "payables", "administration")


def _day() -> str:
    return datetime.now(UTC).date().isoformat()


def _money(value: Any) -> str:
    return format(value, "f")


def _check_period(start: str | None, end: str | None) -> None:
    if start and end and end < start:
        raise conflict("period_invalid")


class RegistersMixin:
    """Mixed into :class:`EconomicsService`; relies on its ``repo``, ``session``, ``require_plan`` and ``_audit``."""

    repo: Any
    session: Any

    async def _names(self, ids: set[uuid.UUID]) -> dict[str, str]:
        """Display names by user id: the full name, else the e-mail address."""
        from sqlalchemy import select

        from app.modules.users.models import User

        if not ids:
            return {}
        rows = (await self.session.execute(select(User).where(User.id.in_(ids)))).scalars()
        return {str(u.id): (u.full_name or u.email or "") for u in rows}

    # ── securities ─────────────────────────────────────────────────────────

    async def add_security(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: uuid.UUID) -> Security:
        await self.require_plan(project_id)  # type: ignore[attr-defined]
        _check_period(data.get("valid_from"), data.get("valid_until"))
        row = await self.repo.add(
            Security(
                project_id=project_id,
                sort_order=await self.repo.next_sort(Security, project_id),
                **data,
            )
        )
        await self._audit(actor_id, "economics_security", row.id, "security_added")  # type: ignore[attr-defined]
        return row

    async def patch_security(
        self, project_id: uuid.UUID, row_id: uuid.UUID, changes: dict[str, Any], actor_id: uuid.UUID
    ) -> Security:
        row = await self.repo.security(project_id, row_id)
        if row is None:
            raise not_found("security_not_found")
        for key, value in changes.items():
            if value is not None:
                setattr(row, key, value)
        _check_period(row.valid_from, row.valid_until)
        await self.session.flush()
        await self._audit(actor_id, "economics_security", row.id, "security_changed")  # type: ignore[attr-defined]
        return row

    async def delete_security(self, project_id: uuid.UUID, row_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        row = await self.repo.security(project_id, row_id)
        if row is None:
            raise not_found("security_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "economics_security", row_id, "security_deleted")  # type: ignore[attr-defined]

    # ── insurance ──────────────────────────────────────────────────────────

    async def add_insurance(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: uuid.UUID) -> Insurance:
        await self.require_plan(project_id)  # type: ignore[attr-defined]
        _check_period(data.get("period_from"), data.get("period_to"))
        row = await self.repo.add(
            Insurance(
                project_id=project_id,
                sort_order=await self.repo.next_sort(Insurance, project_id),
                **data,
            )
        )
        await self._audit(actor_id, "economics_insurance", row.id, "insurance_added")  # type: ignore[attr-defined]
        return row

    async def patch_insurance(
        self, project_id: uuid.UUID, row_id: uuid.UUID, changes: dict[str, Any], actor_id: uuid.UUID
    ) -> Insurance:
        row = await self.repo.insurance(project_id, row_id)
        if row is None:
            raise not_found("insurance_not_found")
        for key, value in changes.items():
            if value is not None:
                setattr(row, key, value)
        _check_period(row.period_from, row.period_to)
        await self.session.flush()
        await self._audit(actor_id, "economics_insurance", row.id, "insurance_changed")  # type: ignore[attr-defined]
        return row

    async def delete_insurance(self, project_id: uuid.UUID, row_id: uuid.UUID, actor_id: uuid.UUID) -> None:
        row = await self.repo.insurance(project_id, row_id)
        if row is None:
            raise not_found("insurance_not_found")
        await self.session.delete(row)
        await self.session.flush()
        await self._audit(actor_id, "economics_insurance", row_id, "insurance_deleted")  # type: ignore[attr-defined]

    # ── tax treatment (one row) and process set-up (one row per area) ──────

    async def put_tax(self, project_id: uuid.UUID, data: dict[str, Any], actor_id: uuid.UUID) -> TaxTreatment:
        await self.require_plan(project_id)  # type: ignore[attr-defined]
        confirm = bool(data.pop("confirm", False))
        row = await self.repo.tax(project_id)
        if row is None:
            row = await self.repo.add(TaxTreatment(project_id=project_id, **data))
        else:
            for key, value in data.items():
                setattr(row, key, value)
        if confirm:
            row.confirmed_by = actor_id
            row.confirmed_at = datetime.now(UTC)
        else:
            # A changed treatment is no longer the one somebody confirmed.
            row.confirmed_by = None
            row.confirmed_at = None
        await self.session.flush()
        await self._audit(actor_id, "economics_tax", row.id, "tax_confirmed" if confirm else "tax_changed")  # type: ignore[attr-defined]
        return row

    async def put_process(
        self, project_id: uuid.UUID, area: str, data: dict[str, Any], actor_id: uuid.UUID
    ) -> ProcessSetup:
        await self.require_plan(project_id)  # type: ignore[attr-defined]
        if data.get("status") == "set_up" and not data.get("set_up_on"):
            data["set_up_on"] = _day()
        if data.get("status") != "set_up":
            data["set_up_on"] = None
        row = next((p for p in await self.repo.processes(project_id) if p.area == area), None)
        if row is None:
            row = await self.repo.add(ProcessSetup(project_id=project_id, area=area, **data))
        else:
            for key, value in data.items():
                setattr(row, key, value)
        await self.session.flush()
        await self._audit(actor_id, "economics_process", row.id, "process_changed")  # type: ignore[attr-defined]
        return row

    # ── views ──────────────────────────────────────────────────────────────

    async def register_payload(self, project_id: uuid.UUID) -> dict[str, Any]:
        """The slice of the validation payload the register rules read."""
        tax = await self.repo.tax(project_id)
        return {
            "today": _day(),
            "securities": [
                {
                    "id": str(s.id),
                    "description": s.description,
                    "status": s.status,
                    "valid_from": s.valid_from,
                    "valid_until": s.valid_until,
                }
                for s in await self.repo.securities(project_id)
            ],
            "insurances": [
                {
                    "id": str(i.id),
                    "label": i.policy_number or i.insurer,
                    "status": i.status,
                    "period_from": i.period_from,
                    "period_to": i.period_to,
                }
                for i in await self.repo.insurances(project_id)
            ],
            "tax": None
            if tax is None
            else {"confirmed": tax.confirmed_at is not None, "input_tax_deduction": tax.input_tax_deduction},
            "process": [{"area": p.area, "status": p.status} for p in await self.repo.processes(project_id)],
        }

    async def registers(self, project_id: uuid.UUID) -> dict[str, Any]:
        from app.modules.economics import rules

        await self.require_plan(project_id)  # type: ignore[attr-defined]
        securities = await self.repo.securities(project_id)
        insurances = await self.repo.insurances(project_id)
        tax = await self.repo.tax(project_id)
        processes = {p.area: p for p in await self.repo.processes(project_id)}
        names = await self._names({tax.confirmed_by} if tax is not None and tax.confirmed_by else set())
        payload = {"registers": await self.register_payload(project_id)}
        found = rules.register_findings(payload)
        today = payload["registers"]["today"]
        return {
            "securities": [
                {
                    "id": str(s.id),
                    "kind": s.kind,
                    "description": s.description,
                    "amount": _money(s.amount),
                    "issuer": s.issuer,
                    "beneficiary": s.beneficiary,
                    "reference": s.reference,
                    "valid_from": s.valid_from,
                    "valid_until": s.valid_until,
                    "status": s.status,
                    "lapsed": rules.lapsed(s.__dict__, "valid_until", today),
                    "notes": s.notes,
                }
                for s in securities
            ],
            "insurances": [
                {
                    "id": str(i.id),
                    "kind": i.kind,
                    "insurer": i.insurer,
                    "policy_number": i.policy_number,
                    "sum_insured": _money(i.sum_insured),
                    "deductible": _money(i.deductible),
                    "period_from": i.period_from,
                    "period_to": i.period_to,
                    "status": i.status,
                    "lapsed": rules.lapsed(i.__dict__, "period_to", today),
                    "notes": i.notes,
                }
                for i in insurances
            ],
            "tax": None
            if tax is None
            else {
                "vat_treatment": tax.vat_treatment,
                "input_tax_deduction": tax.input_tax_deduction,
                "notes": tax.notes,
                "confirmed": tax.confirmed_at is not None,
                "confirmed_by": str(tax.confirmed_by) if tax.confirmed_by else None,
                "confirmed_by_name": names.get(str(tax.confirmed_by), "") if tax.confirmed_by else "",
                "confirmed_at": tax.confirmed_at.isoformat() if tax.confirmed_at else None,
            },
            "process": [
                {
                    "area": area,
                    "description": processes[area].description if area in processes else "",
                    "owner": processes[area].owner if area in processes else "",
                    "status": processes[area].status if area in processes else "open",
                    "set_up_on": processes[area].set_up_on if area in processes else None,
                    "notes": processes[area].notes if area in processes else "",
                }
                for area in _AREAS
            ],
            "state": rules.register_state(payload),
            "findings": [f.as_dict() for f in found],
        }
