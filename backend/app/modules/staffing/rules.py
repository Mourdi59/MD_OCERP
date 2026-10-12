# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""The staffing rules as pure functions (SPEC section 4). No session, no I/O.

The service builds plain dicts from its rows and calls these; the validation
rule set calls the same functions on the same payload, so every check has one
implementation and every unit test drives it without a database.

Shapes (dates are :class:`datetime.date`, FTE values :class:`~decimal.Decimal`):

* position: ``{id, role_code, phase, key_role, handover_role, required_before,
  entry_date, exit_date, fte, headcount, status}``
* fill: ``{id, position_id, roster_member_id, fte_share, from_date, to_date, status}``
* handover: ``{id, from_fill_id, to_position_id, overlap_days}``
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

ERROR = "error"
WARNING = "warning"
ONE = Decimal("1")
ZERO = Decimal("0")
HEALTH_FIT_VALUES: tuple[str, ...] = ("yes", "with_restrictions", "no")
EMPLOYMENT_BASES: tuple[str, ...] = ("employee", "posted_worker", "contractor_staff", "consultant", "agency")
# Numeric(5, 2) and Numeric(14, 2): what the columns hold. A value outside is refused, never rounded.
# Headcount is bounded by what one resource request can ask for.
MAX_HEADCOUNT = 999
MAX_MONEY = Decimal("999999999999.99")


@dataclass(frozen=True)
class Finding:
    """One rule finding: a stable code (also the message key), the element it is about, a severity."""

    code: str
    ref: str
    severity: str = ERROR
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "ref": self.ref, "severity": self.severity, "detail": self.detail}


# ── values ─────────────────────────────────────────────────────────────────


def dec(value: Any) -> Decimal:
    """An exact decimal from a string, int or Decimal. Floats and booleans are refused (rule 1: Decimal only)."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("decimal_required")
    try:
        out = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("decimal_required") from exc
    if not out.is_finite():
        raise ValueError("decimal_required")
    return out


def scale(value: Decimal) -> int:
    """Number of decimal places the value is written with (``1.250`` has three)."""
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def _fte_error(value: Any) -> str | None:
    try:
        number = dec(value)
    except ValueError:
        return "fte_out_of_range"
    if not ZERO < number <= ONE:
        return "fte_out_of_range"
    # Numeric(5, 2) would round a third decimal away; 0.004 would be stored as 0.00 and read as covered.
    if scale(number.normalize()) > 2:
        return "fte_precision"
    return None


def money_error(value: Any) -> str | None:
    """``cost_invalid`` unless the amount is a non-negative decimal with two places that the column holds."""
    try:
        number = dec(value)
    except ValueError:
        return "cost_invalid"
    if number < ZERO or number > MAX_MONEY or scale(number.normalize()) > 2:
        return "cost_invalid"
    return None


def fill_end_date(from_date: date, today: date, planned_end: date | None = None) -> date:
    """The last day of a fill that is ended today.

    A fill that never began ends on its first day, and one whose planned end has
    already passed keeps that end: ending it late does not extend it.
    """
    end = today if planned_end is None or planned_end > today else planned_end
    return end if end >= from_date else from_date


def add_months(day: date, months: int) -> date:
    """``day`` plus ``months`` calendar months, clamped to the last day of the target month."""
    total = day.month - 1 + months
    year, month = day.year + total // 12, total % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


# ── rule 1: position values ────────────────────────────────────────────────


def position_errors(fte: Any, headcount: Any, entry_date: date | None, exit_date: date | None) -> list[str]:
    """FTE in (0, 1] per head, headcount >= 1, exit not before entry."""
    errors: list[str] = []
    fte_error = _fte_error(fte)
    if fte_error:
        errors.append(fte_error)
    if isinstance(headcount, bool) or not isinstance(headcount, int) or not 1 <= headcount <= MAX_HEADCOUNT:
        errors.append("headcount_invalid")
    if entry_date is not None and exit_date is not None and exit_date < entry_date:
        errors.append("exit_before_entry")
    return errors


def fill_share_error(fte_share: Any, from_date: date, to_date: date | None) -> str | None:
    error = _fte_error(fte_share)
    if error:
        return error
    if to_date is not None and to_date < from_date:
        return "exit_before_entry"
    return None


# ── rule 2: derived filled status ──────────────────────────────────────────


def _active_on(fill: Mapping[str, Any], day: date | None) -> bool:
    if fill.get("status") != "confirmed":
        return False
    if day is None:
        return True
    start, end = fill["from_date"], fill.get("to_date")
    return start <= day and (end is None or day <= end)


def covered_fte(fills: Iterable[Mapping[str, Any]], day: date | None) -> Decimal:
    """Sum of confirmed ``fte_share`` active on ``day`` (any day when ``day`` is None)."""
    return sum((dec(f["fte_share"]) for f in fills if _active_on(f, day)), ZERO)


def required_fte(position: Mapping[str, Any]) -> Decimal:
    return dec(position["fte"]) * int(position["headcount"])


def is_filled(position: Mapping[str, Any], fills: Iterable[Mapping[str, Any]], day: date | None = None) -> bool:
    """Confirmed shares on ``day`` (default: the entry date) cover FTE x headcount."""
    own = [f for f in fills if f["position_id"] == position["id"]]
    on = day if day is not None else position.get("entry_date")
    return covered_fte(own, on) >= required_fte(position)


def effective_position_status(position: Mapping[str, Any], fills: Iterable[Mapping[str, Any]]) -> str:
    """Stored on_hold / cancelled win; otherwise ``filled`` when covered, else the stored open / recruiting."""
    stored = position["status"]
    if stored in ("on_hold", "cancelled"):
        return stored
    return "filled" if is_filled(position, fills) else stored


# ── rule 4: one person, at most 1.0 FTE on any day ─────────────────────────


def first_overallocated_day(fills: Iterable[Mapping[str, Any]], limit: Decimal = ONE) -> tuple[date, Decimal] | None:
    """The first day on which the confirmed shares of these fills exceed ``limit``, with the total.

    The total only changes on a fill's first day, so evaluating those days is exhaustive.
    """
    confirmed = [f for f in fills if f.get("status") == "confirmed"]
    for day in sorted({f["from_date"] for f in confirmed}):
        total = covered_fte(confirmed, day)
        if total > limit:
            return day, total
    return None


# ── rule 8: document requirements of a person ──────────────────────────────


def required_document_kinds(
    catalogue: Any, role_codes: Iterable[str], employment_basis: str, nationality_required: bool
) -> list[str]:
    """Union of the roles' required kinds, plus A1 for a posted worker and a work permit when a check applies."""
    from app.modules.staffing.catalogue import POSTING_KIND, WORK_PERMIT_KIND

    kinds: list[str] = []
    for code in role_codes:
        role = catalogue.role(code)
        for k in role.required_document_kinds if role else ():
            if k not in kinds:
                kinds.append(k)
    known = {d.code for d in catalogue.document_kinds}
    if employment_basis == "posted_worker" and POSTING_KIND in known and POSTING_KIND not in kinds:
        kinds.append(POSTING_KIND)
    if nationality_required and WORK_PERMIT_KIND in known and WORK_PERMIT_KIND not in kinds:
        kinds.append(WORK_PERMIT_KIND)
    return kinds


def clearance(required: Iterable[str], documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Cleared to work: every required kind is waived or has a credential not expired on the start day.

    ``documents`` maps kind -> ``{"status_on_start": credential status on the start day or None, "waived": bool}``.
    The status comes from the credentials module (rule 9), never computed here.
    """
    missing: list[str] = []
    expired: list[str] = []
    for kind in required:
        doc = documents.get(kind)
        if doc is not None and doc.get("waived"):
            continue
        status = doc.get("status_on_start") if doc else None
        if status is None:
            missing.append(kind)
        elif status in ("expired", "revoked", "suspended"):
            expired.append(kind)
    return {"cleared": not missing and not expired, "missing": missing, "expired": expired}


# ── rule 12: document numbers ──────────────────────────────────────────────


def masked_number(value: str | None, store_number: bool) -> str | None:
    """The last four characters to store, or ``None``. A longer value is a full number and is refused."""
    if value is None or not value.strip():
        return None
    cleaned = value.strip().replace(" ", "")
    if not store_number:
        raise ValueError("number_not_stored")
    if len(cleaned) > 4:
        raise ValueError("full_number_rejected")
    if not cleaned.isalnum():
        raise ValueError("number_invalid")
    return cleaned


# ── rule 13: who may open a personnel file ─────────────────────────────────


def file_access(relation: str | None, *, can_read: bool, can_edit: bool, edit: bool) -> tuple[bool, str | None]:
    """Whether a caller with this relationship and these permissions may read or edit a file, and why not.

    The relationship is what grants access; no permission replaces it. The person
    reads their own file without any permission and never edits it.
    """
    if relation == "self":
        return (False, "own_file_read_only") if edit else (True, None)
    if relation not in ("area_owner", "position_owner"):
        return False, "no_relationship_to_person"
    if not (can_edit if edit else can_read):
        return False, "personnel_permission_missing"
    return True, None


def gate_fields_access(stored_status: str, *, can_manage: bool) -> tuple[bool, str | None]:
    """Whether what a gate reads of a position (key role, requirement, handover) may be changed, and why not.

    These fields decide what rules 5 and 6 ask for, so they need the manage
    permission and stand still once the position has left ``open``.
    """
    if not can_manage:
        return False, "manage_permission_required"
    if stored_status != "open":
        return False, "gate_fields_frozen"
    return True, None


def file_transition_refusal(action: str, status: str) -> str | None:
    """Why a file in ``status`` cannot be ended, held, released or erased; ``None`` when it can."""
    if action == "end":
        return None if status == "active" else "file_not_active"
    if action == "hold":
        if status == "retention_hold":
            return "already_in_state"
        return None if status == "ended" else "file_not_ended"
    if action == "release":
        return None if status == "retention_hold" else "file_not_held"
    if action == "erase":
        return {"anonymised": "file_anonymised", "retention_hold": "retention_hold_active"}.get(status)
    raise ValueError(action)


# ── rules 14 and 15: retention ─────────────────────────────────────────────


def retention_end(
    rule: Any, *, assignment_start: date | None, assignment_end: date | None, document_expiry: date | None = None
) -> date | None:
    """When one retention rule ends for one document; ``None`` while its trigger has not happened.

    ``end_of_employment`` is read as the end of the assignment on this project: the
    platform records the project assignment, not the employment contract's end.
    """
    if rule.trigger == "document_expiry":
        base = document_expiry or assignment_end
    else:
        base = assignment_end
    if base is None:
        return None
    end = add_months(base, rule.period_months)
    if rule.min_months_from_start and assignment_start is not None:
        end = max(end, add_months(assignment_start, rule.min_months_from_start))
    return end


def retention_due(
    catalogue: Any,
    documents: Iterable[Mapping[str, Any]],
    *,
    assignment_start: date | None,
    assignment_end: date | None,
) -> date | None:
    """Rule 14: the latest end over the file's documents' rules (the default rule when there are none)."""
    ends: list[date] = []
    docs = list(documents)
    for d in docs:
        kind = catalogue.document_kind(d["document_kind"])
        rule = catalogue.retention_rule(kind.retention_rule if kind else catalogue.default_retention_rule)
        if rule is None:
            continue
        end = retention_end(
            rule,
            assignment_start=assignment_start,
            assignment_end=assignment_end,
            document_expiry=d.get("valid_until"),
        )
        if end is not None:
            ends.append(end)
    if not docs:
        rule = catalogue.retention_rule(catalogue.default_retention_rule)
        end = retention_end(rule, assignment_start=assignment_start, assignment_end=assignment_end) if rule else None
        if end is not None:
            ends.append(end)
    return max(ends) if ends else None


def retention_action(catalogue: Any, documents: Iterable[Mapping[str, Any]]) -> str:
    """``delete`` or ``anonymise``: what the file's rules ask for once retention ends.

    A file is deleted only when every rule that applies says so. One rule that
    asks for the anonymous record keeps it: deleting would destroy what it keeps.
    """
    docs = list(documents)
    codes = [
        (kind.retention_rule if kind else catalogue.default_retention_rule)
        for kind in (catalogue.document_kind(d["document_kind"]) for d in docs)
    ] or [catalogue.default_retention_rule]
    actions = {rule.action for rule in (catalogue.retention_rule(c) for c in codes) if rule is not None}
    return "anonymise" if "anonymise" in actions or not actions else "delete"


def legal_obligation_running(
    catalogue: Any,
    documents: Iterable[Mapping[str, Any]],
    *,
    assignment_start: date | None,
    assignment_end: date | None,
    today: date,
) -> tuple[bool, date | None]:
    """Rule 15: is a retention duty with ``legal_obligation`` still running, and until when (None = open)."""
    running, latest = False, None
    for d in documents:
        kind = catalogue.document_kind(d["document_kind"])
        rule = catalogue.retention_rule(kind.retention_rule) if kind else None
        if rule is None or not rule.legal_obligation:
            continue
        end = retention_end(
            rule,
            assignment_start=assignment_start,
            assignment_end=assignment_end,
            document_expiry=d.get("valid_until"),
        )
        if end is None:
            return True, None
        if end > today:
            running = True
            latest = end if latest is None else max(latest, end)
    return running, latest


# ── rules 5 and 6: key roles, operation build-up, handover ─────────────────


def _live(positions: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [p for p in positions if p["status"] != "cancelled"]


def key_role_gate_findings(
    positions: Iterable[Mapping[str, Any]],
    fills: list[Mapping[str, Any]],
    enabled: Iterable[str],
    gate_date: date | None,
) -> list[Finding]:
    """Rule 5: every key position required before something this gate enables is filled on its planned date.

    ``enabled`` is what the phase behind the gate enables (its catalogue tags); a
    position names the tag it must be filled before, never a gate. Without a
    planned date there is nothing to compare: the position must simply be filled.
    """
    tags = set(enabled)
    out: list[Finding] = []
    for p in _live(positions):
        if not p.get("key_role") or p.get("required_before") not in tags:
            continue
        own = [f for f in fills if f["position_id"] == p["id"]]
        if covered_fte(own, gate_date) < required_fte(p):
            out.append(Finding("key_role_not_filled_before_gate", str(p["id"]), ERROR, p["role_code"]))
    return out


def submission_findings(
    catalogue: Any,
    positions: Iterable[Mapping[str, Any]],
    fills: list[Mapping[str, Any]],
    handovers: Iterable[Mapping[str, Any]],
    commissioning_date: date | None,
) -> list[Finding]:
    """Rule 6: what has to be true before the plan goes to review."""
    live = _live(positions)
    out: list[Finding] = []
    by_role: dict[str, list[Mapping[str, Any]]] = {}
    for p in live:
        by_role.setdefault(p["role_code"], []).append(p)
    for role in catalogue.roles:
        if not role.key_role:
            continue
        if any(ph in ("development", "execution") for ph in role.phases) and role.code not in by_role:
            out.append(Finding("key_role_missing", role.code))
        if "operation" in role.phases:
            dated = [p["entry_date"] for p in by_role.get(role.code, []) if p.get("entry_date")]
            if commissioning_date is None:
                out.append(Finding("commissioning_date_missing", role.code))
            elif not any(d < commissioning_date for d in dated):
                out.append(Finding("operation_role_late", role.code))
    fill_position = {f["id"]: f["position_id"] for f in fills}
    linked: set[Any] = set()
    for h in handovers:
        giver = fill_position.get(h["from_fill_id"])
        # A handover to the position the knowledge already sits on hands nothing over.
        if int(h.get("overlap_days") or 0) > 0 and giver != h["to_position_id"]:
            linked.add(h["to_position_id"])
            if giver is not None:
                linked.add(giver)
    for p in live:
        if p.get("handover_role") and p["id"] not in linked:
            out.append(Finding("handover_missing", str(p["id"]), ERROR, p["role_code"]))
    return out


# ── rules 16, 17, 18: warnings around a person ─────────────────────────────


def _overlaps(start: date, end: date, day: date) -> bool:
    return start <= day <= end


def leave_findings(
    leave: Mapping[str, Any], travels: Iterable[Mapping[str, Any]], gate_dates: Iterable[date]
) -> list[Finding]:
    """Rule 16: leave over the person's own mobilisation or a gate their key role is required for."""
    if leave.get("status") == "cancelled":
        return []
    start, end = leave["from_date"], leave["to_date"]
    ref = str(leave.get("id", ""))
    for t in travels:
        if t.get("kind") == "mobilisation" and t.get("status") != "cancelled":
            if _overlaps(start, end, t["depart_date"]):
                return [Finding("leave_conflicts_gate", ref, WARNING, "mobilisation")]
    for g in gate_dates:
        if _overlaps(start, end, g):
            return [Finding("leave_conflicts_gate", ref, WARNING, g.isoformat())]
    return []


def travel_findings(
    travels: Iterable[Mapping[str, Any]], assignment_end: date | None, file_status: str
) -> list[Finding]:
    """Rule 17: a return after the assignment ends; no demobilisation once the assignment ended."""
    live = [t for t in travels if t.get("status") != "cancelled"]
    out = [
        Finding("travel_after_assignment", str(t.get("id", "")), WARNING)
        for t in live
        if assignment_end is not None and t.get("return_date") is not None and t["return_date"] > assignment_end
    ]
    if file_status == "ended" and not any(t.get("kind") == "demobilisation" for t in live):
        out.append(Finding("demobilisation_missing", "file", WARNING))
    return out


def accommodation_finding(
    requires_accommodation: bool, start: date | None, bookings: Iterable[Mapping[str, Any]], ref: str
) -> Finding | None:
    """Rule 18: on a remote site a confirmed person needs a booking covering the first day."""
    if not requires_accommodation or start is None:
        return None
    for b in bookings:
        if b.get("status") in ("cancelled", "no_show"):
            continue
        check_in, check_out = b["check_in"], b.get("check_out")
        if check_in <= start and (check_out is None or start <= check_out):
            return None
    return Finding("no_accommodation", ref, WARNING)


def upcoming_window(today: date, days: int) -> tuple[date, date]:
    return today, today + timedelta(days=days)
