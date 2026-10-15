# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The checks of the economics module as one pure function over one payload.

The service builds the payload (``EconomicsService.validation_payload``), the
validation rules in ``validators.py`` keep the findings of their own codes, and
the gate evidence and the readiness view read the same list, so a check has one
implementation and the three surfaces cannot disagree.

Payload::

    {
      "plan": {"status", "currency", "bill_currency", "bill_count", "bill_chosen", "discount_rate_pct", "horizon_years"},
      "flow_lines": [{"id", "kind", "label", "source", "amount", "year_from", "year_to"}],
      "frame": {
        "lines": [{"id", "code", "amount", "estimate", "committed"}],
        "markup_allowance", "markups_total", "unassigned_estimate", "unassigned_count",
        "committed_available", "committed_unassigned"
      },
      "financing": {
        "requirement", "coverage": {"shortfall", "surplus", "sources_total"},
        "sources": [{"id", "name", "kind", "amount", "tranche_total", "tranche_count", "award"}]
      },
      "registers": {
        "today": "YYYY-MM-DD",
        "securities": [{"id", "description", "status", "valid_until"}],
        "insurances": [{"id", "label", "status", "period_to"}],
        "tax": {"confirmed", "input_tax_deduction"} | None,
        "process": [{"area", "status"}]
      }
    }

Amounts are decimal strings. Severity ``error`` blocks the proposal and the gate;
``warning`` is shown and never blocks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.economics.classification import overlaps

ERROR, WARNING = "error", "warning"
ZERO = Decimal("0")

#: Every code a finding can carry, with its severity. The validation rules and the messages key off these.
CODES: dict[str, str] = {
    "discount_rate_missing": ERROR,
    "no_investment": ERROR,
    "no_benefit": WARNING,
    "cash_flow_years_invalid": ERROR,
    "cash_flow_outside_horizon": ERROR,
    "frame_empty": ERROR,
    "frame_lines_overlap": ERROR,
    "frame_zero_amount": WARNING,
    "estimate_over_frame": WARNING,
    "estimate_unassigned": WARNING,
    "markups_over_allowance": WARNING,
    "no_bill": WARNING,
    "several_bills": WARNING,
    "currency_mismatch": ERROR,
    "committed_over_frame": ERROR,
    "committed_unassigned": WARNING,
    "committed_unknown": WARNING,
    "financing_shortfall": ERROR,
    "no_sources": ERROR,
    "tranches_differ_from_source": ERROR,
    "source_without_tranches": WARNING,
    "grant_over_award": WARNING,
    "grant_without_application": WARNING,
    "investment_below_frame": WARNING,
    "security_expired": WARNING,
    "insurance_expired": WARNING,
    "tax_not_confirmed": WARNING,
    "process_not_set_up": WARNING,
}

PROCESS_AREAS = ("receivables", "payables", "administration")


@dataclass(frozen=True)
class Finding:
    code: str
    ref: str = "project"
    severity: str = ERROR
    params: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "ref": self.ref, "severity": self.severity, **self.params}


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return ZERO


def _f(code: str, ref: str = "project", **params: Any) -> Finding:
    return Finding(code=code, ref=ref, severity=CODES[code], params=params)


def business_case_findings(payload: dict[str, Any]) -> list[Finding]:
    plan = payload.get("plan") or {}
    lines = payload.get("flow_lines") or []
    horizon = int(plan.get("horizon_years") or 0)
    out: list[Finding] = []
    if plan.get("discount_rate_pct") is None:
        out.append(_f("discount_rate_missing"))
    if not any(ln["kind"] == "investment" and _d(ln["amount"]) > 0 for ln in lines):
        out.append(_f("no_investment"))
    if not any(ln["kind"] in ("revenue", "residual") and _d(ln["amount"]) > 0 for ln in lines):
        out.append(_f("no_benefit"))
    for ln in lines:
        ref = ln.get("label") or ln["id"]
        if int(ln["year_to"]) < int(ln["year_from"]):
            out.append(_f("cash_flow_years_invalid", ref))
        elif int(ln["year_to"]) > horizon:
            out.append(_f("cash_flow_outside_horizon", ref, year_to=int(ln["year_to"]), horizon=horizon))
    frame_total = _d((payload.get("frame") or {}).get("total"))
    investments = [ln for ln in lines if ln["kind"] == "investment"]
    if investments and frame_total > 0 and not any(ln.get("source") == "cost_frame" for ln in investments):
        invested = sum((_d(ln["amount"]) for ln in investments), ZERO)
        if invested < frame_total:
            out.append(_f("investment_below_frame", investment=str(invested), frame=str(frame_total)))
    return out


def cost_frame_findings(payload: dict[str, Any]) -> list[Finding]:
    plan = payload.get("plan") or {}
    frame = payload.get("frame") or {}
    lines = frame.get("lines") or []
    out: list[Finding] = []
    if not lines:
        out.append(_f("frame_empty"))
    for i, a in enumerate(lines):
        if _d(a["amount"]) == 0:
            out.append(_f("frame_zero_amount", a["code"]))
        for b in lines[i + 1 :]:
            if overlaps(a["code"], b["code"]):
                out.append(_f("frame_lines_overlap", a["code"], other=b["code"]))
    if plan.get("bill_count", 0) == 0:
        out.append(_f("no_bill"))
    elif plan.get("bill_count", 0) > 1 and not plan.get("bill_chosen"):
        out.append(_f("several_bills", bills=plan["bill_count"]))
    bill_ccy, ccy = (plan.get("bill_currency") or ""), (plan.get("currency") or "")
    if bill_ccy and ccy and bill_ccy != ccy:
        out.append(_f("currency_mismatch", plan=ccy, bill=bill_ccy))
    for ln in lines:
        frame_amount, est = _d(ln["amount"]), _d(ln["estimate"])
        if est > frame_amount:
            out.append(_f("estimate_over_frame", ln["code"], estimate=str(est), frame=str(frame_amount)))
        if ln.get("committed") is not None and _d(ln["committed"]) > frame_amount:
            out.append(_f("committed_over_frame", ln["code"], committed=str(ln["committed"]), frame=str(frame_amount)))
    if _d(frame.get("unassigned_estimate")) != 0:
        out.append(_f("estimate_unassigned", count=int(frame.get("unassigned_count") or 0)))
    if _d(frame.get("markups_total")) > _d(frame.get("markup_allowance")):
        out.append(_f("markups_over_allowance", markups=str(frame.get("markups_total"))))
    if not frame.get("committed_available", True):
        out.append(_f("committed_unknown"))
    elif _d(frame.get("committed_unassigned")) != 0:
        out.append(_f("committed_unassigned", amount=str(frame.get("committed_unassigned"))))
    return out


def financing_findings(payload: dict[str, Any]) -> list[Finding]:
    fin = payload.get("financing") or {}
    sources = fin.get("sources") or []
    out: list[Finding] = []
    if not sources:
        out.append(_f("no_sources"))
    cov = fin.get("coverage") or {}
    if _d(cov.get("shortfall")) > 0:
        out.append(_f("financing_shortfall", shortfall=str(cov["shortfall"]), requirement=str(fin.get("requirement"))))
    for s in sources:
        ref = s.get("name") or s["id"]
        if not s.get("tranche_count"):
            out.append(_f("source_without_tranches", ref))
        elif _d(s.get("tranche_total")) != _d(s["amount"]):
            out.append(
                _f("tranches_differ_from_source", ref, tranches=str(s["tranche_total"]), source=str(s["amount"]))
            )
        if s["kind"] in ("grant", "subsidy"):
            award = s.get("award")
            if award is None:
                out.append(_f("grant_without_application", ref))
            elif _d(s["amount"]) > _d(award.get("amount")):
                out.append(_f("grant_over_award", ref, award=str(award.get("amount")), basis=award.get("basis", "")))
    return out


def lapsed(row: dict[str, Any], end_key: str, today: str) -> bool:
    end = row.get(end_key)
    return row.get("status") == "expired" or (row.get("status") == "in_place" and bool(end) and str(end) < today)


def register_findings(payload: dict[str, Any]) -> list[Finding]:
    """Securities, insurance, tax treatment and process set-up. A payload without registers has none."""
    reg = payload.get("registers")
    if not reg:
        return []
    today = str(reg.get("today") or "")
    out: list[Finding] = []
    for sec in reg.get("securities") or []:
        if lapsed(sec, "valid_until", today):
            out.append(
                _f("security_expired", sec.get("description") or sec["id"], valid_until=str(sec.get("valid_until")))
            )
    for ins in reg.get("insurances") or []:
        if lapsed(ins, "period_to", today):
            out.append(_f("insurance_expired", ins.get("label") or ins["id"], period_to=str(ins.get("period_to"))))
    tax = reg.get("tax")
    if not tax or not tax.get("confirmed") or tax.get("input_tax_deduction") is None:
        out.append(_f("tax_not_confirmed"))
    done = {p["area"] for p in reg.get("process") or [] if p.get("status") == "set_up"}
    out.extend(_f("process_not_set_up", area) for area in PROCESS_AREAS if area not in done)
    return out


def _backed(rows: list[dict[str, Any]], good: tuple[str, ...], start_key: str, end_key: str, today: str) -> bool:
    """Is there cover now? At least one row is in place, none ran out, and a row still only requested
    does not block while its start lies ahead (a warranty guarantee that replaces the performance one at
    acceptance is asked for long before it is due)."""

    def fine(row: dict[str, Any]) -> bool:
        if row.get("status") in good:
            return not lapsed(row, end_key, today)
        start = row.get(start_key)
        return row.get("status") == "requested" and bool(start) and str(start) > today

    return any(r.get("status") in good for r in rows) and all(fine(r) for r in rows)


def register_state(payload: dict[str, Any]) -> dict[str, bool]:
    """The five register questions a gate asks, as booleans. The evidence reads this and nothing else."""
    reg = payload.get("registers") or {}
    today = str(reg.get("today") or "")
    securities = reg.get("securities") or []
    insurances = reg.get("insurances") or []
    tax = reg.get("tax")
    done = {p["area"] for p in reg.get("process") or [] if p.get("status") == "set_up"}
    return {
        "securities": _backed(securities, ("in_place", "released"), "valid_from", "valid_until", today),
        "insurance": _backed(insurances, ("in_place",), "period_from", "period_to", today),
        "tax": bool(tax and tax.get("confirmed") and tax.get("input_tax_deduction") is not None),
        "receivables_payables": {"receivables", "payables"} <= done,
        "administration": "administration" in done,
    }


def all_findings(payload: dict[str, Any]) -> list[Finding]:
    return [
        *business_case_findings(payload),
        *cost_frame_findings(payload),
        *financing_findings(payload),
        *register_findings(payload),
    ]


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == ERROR]
